"""FastAPI app assembly."""

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

log = logging.getLogger("iflycode-proxy")

_janitor_task: Optional[object] = None


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
    yield
    if _janitor_task:
        _janitor_task.cancel()
        log.info("Janitor stopped")


def create_app(router: CredentialRouter, db=None):
    app = FastAPI(title="iFlyCode Proxy", lifespan=lifespan)
    app.state.db = db

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    if db:
        @app.middleware("http")
        async def log_requests(request: Request, call_next):
            start = time.time()
            response = await call_next(request)
            latency = int((time.time() - start) * 1000)
            path = request.url.path
            if path.startswith("/v1/"):
                api_key = request.headers.get("x-api-key", "")
                model = ""
                if request.method == "POST":
                    try:
                        body_bytes = await request.body()
                        if body_bytes:
                            import json
                            body = json.loads(body_bytes)
                            model = body.get("model", "")
                    except Exception:
                        pass
                db.log_request(
                    api_key=api_key, model=model, endpoint=path,
                    stream=False, status_code=response.status_code,
                    latency_ms=latency,
                )
            return response

        from iflycode_proxy.web_api import create_web_api_router
        app.include_router(create_web_api_router(db))

    app.include_router(create_openai_router(router))

    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        from starlette.responses import FileResponse

        @app.get("/{path:path}")
        async def spa_fallback(path: str):
            file = static_dir / path
            if file.is_file():
                return FileResponse(str(file))
            return FileResponse(str(static_dir / "index.html"))

    return app
