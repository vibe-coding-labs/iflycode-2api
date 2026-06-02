"""FastAPI app assembly with keepalive, session tracking, and structured logging."""

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from iflycode_proxy.credential_router import CredentialRouter
from iflycode_proxy.openai_handler import create_openai_router
from iflycode_proxy.anthropic_handler import create_anthropic_router
from iflycode_proxy.sessions import session_stats

# Will be imported conditionally to avoid circular dependency
_auth_middleware_added = False

log = logging.getLogger("iflycode-proxy")

_janitor_task: Optional[object] = None
_START_TIME = time.time()
_VERSION = "1.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = app.state.db
    if db:
        from iflycode_proxy.janitor import start_janitor
        global _janitor_task
        _janitor_task = start_janitor(
            db_path=str(db.db_path),
            get_setting_fn=db.get_setting,
            cleanup_fn=db.cleanup_logs,
        )
        # Start keepalive service
        from iflycode_proxy.keepalive import KeepaliveService
        keeper = KeepaliveService(
            get_stale_fn=lambda ttl, bmult: db.get_stale_accounts(normal_ttl_hours=ttl // 3600, backoff_multiplier=bmult),
            set_status_fn=db.set_credential_status,
            validate_fn=db.validate_account,
        )
        keeper.start()
        app.state.keeper = keeper
    yield
    if _janitor_task:
        _janitor_task.cancel()
        log.info("Janitor stopped")
    keeper = getattr(app.state, "keeper", None)
    if keeper:
        keeper.stop()
        log.info("Keepalive stopped")


def create_app(router: CredentialRouter, db=None):
    app = FastAPI(title="iFlyCode Proxy", version=_VERSION, lifespan=lifespan)
    app.state.db = db

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    if db:
        # Add auth middleware to protect /api/* endpoints
        from iflycode_proxy.auth_middleware import AuthMiddleware
        app.add_middleware(AuthMiddleware, db=db)

        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            start = time.time()
            response = await call_next(request)
            latency = int((time.time() - start) * 1000)
            path = request.url.path

            if path.startswith("/v1/"):
                api_key = request.headers.get("x-api-key", request.headers.get("authorization", "").replace("Bearer ", ""))
                model = getattr(request.state, "model", "")
                prompt_tokens = getattr(request.state, "prompt_tokens", 0)
                completion_tokens = getattr(request.state, "completion_tokens", 0)

                # Resolve account_id from api_key for consistent logging
                account_id = api_key
                if db:
                    acc = db.get_account_by_api_key(api_key)
                    if acc:
                        account_id = acc.get("account_id", api_key)

                db.log_request(
                    api_key=account_id, model=model, endpoint=path,
                    stream=False, status_code=response.status_code,
                    latency_ms=latency,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            return response

        from iflycode_proxy.web_api import create_web_api_router
        app.include_router(create_web_api_router(db, cred_router=router))

    app.include_router(create_openai_router(router))
    app.include_router(create_anthropic_router(router))

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        from starlette.responses import FileResponse

        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            file = static_dir / path
            if file.is_file():
                return FileResponse(str(file))
            return FileResponse(str(static_dir / "index.html"))

    # Extra endpoints outside the db-conditional block so they always exist
    @app.get("/health")
    async def health():
        acc_count = 0
        if db:
            acc_count = len(db.list_accounts())
        uptime = int(time.time() - _START_TIME)
        s = session_stats()
        return {
            "status": "ok",
            "service": "iflycode-proxy",
            "version": _VERSION,
            "uptime_seconds": uptime,
            "accounts": acc_count,
            "active_users": s.get("total_users", 0),
            "active_sessions": s.get("active_sessions", 0),
            "endpoints": [
                "/v1/chat/completions",
                "/v1/messages",
                "/v1/models",
                "/health",
            ],
        }

    return app