"""Web API endpoints for frontend management."""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, Request

from iflycode_proxy.auth import get_login_url, poll_login_status
from iflycode_proxy.db import Database, _generate_account_id, _generate_api_key

log = logging.getLogger("iflycode-proxy.web-api")


def create_web_api_router(db: Database, cred_router=None) -> APIRouter:
    router = APIRouter(prefix="/api")

    # -- Accounts --

    @router.get("/accounts")
    async def list_accounts():
        return {"accounts": db.list_accounts()}

    @router.post("/accounts")
    async def add_account(request: Request):
        body = await request.json()
        account_id = body.get("account_id", "").strip() or _generate_account_id()
        api_key = body.get("api_key", "").strip() or _generate_api_key()
        spark_token = body.get("spark_token", body.get("token", "")).strip()
        user_id = body.get("user_id", "").strip()
        is_default = body.get("is_default", False)
        default_model = body.get("default_model", "").strip()
        if not spark_token:
            raise HTTPException(400, "spark_token (or token) is required")
        db.add_account(account_id, api_key, spark_token, user_id, is_default=is_default, default_model=default_model)
        return {"ok": True, "account_id": account_id, "api_key": api_key}

    @router.delete("/accounts/{account_id:path}")
    async def remove_account(account_id: str):
        if not db.remove_account(account_id):
            raise HTTPException(404, f"Account '{account_id}' not found")
        return {"ok": True}

    @router.put("/accounts/{account_id:path}/default")
    async def set_default(account_id: str):
        if not db.set_default(account_id):
            raise HTTPException(404, f"Account '{account_id}' not found")
        return {"ok": True}

    @router.post("/accounts/{account_id:path}/validate")
    async def validate_account(account_id: str):
        valid = db.validate_account(account_id)
        return {"account_id": account_id, "valid": valid}

    @router.get("/accounts/{account_id:path}/models")
    async def list_account_models(account_id: str):
        models = db.get_account_models(account_id)
        return {"models": models}

    @router.put("/accounts/{account_id:path}/model")
    async def update_account_model(account_id: str, request: Request):
        body = await request.json()
        default_model = body.get("default_model", "").strip()
        db.update_account_model(account_id, default_model)
        if cred_router:
            cred_router.set_default_model(account_id, default_model)
        return {"ok": True, "account_id": account_id, "default_model": default_model}

    @router.get("/accounts/{account_id:path}/stats")
    async def get_account_stats(account_id: str):
        return db.get_account_stats(account_id)

    @router.get("/accounts/{account_id:path}/hourly-stats")
    async def get_account_hourly_stats(account_id: str, hours: int = 24):
        if hours < 1 or hours > 720:
            hours = 24
        return {"hours": hours, "data": db.get_account_hourly_stats(account_id, hours)}

    @router.get("/accounts/{account_id:path}/recent-logs")
    async def get_account_recent_logs(account_id: str, limit: int = 20):
        if limit < 1 or limit > 100:
            limit = 20
        return {"logs": db.get_account_recent_logs(account_id, limit)}

    @router.post("/accounts/{account_id:path}/renew-key")
    async def renew_api_key(account_id: str):
        new_key = db.renew_api_key(account_id)
        if not new_key:
            raise HTTPException(404, f"Account '{account_id}' not found")
        return {"ok": True, "account_id": account_id, "api_key": new_key}

    # -- SSO Auth --

    @router.post("/auth/login-url")
    async def auth_login_url():
        result = get_login_url()
        if not result.get("ok"):
            raise HTTPException(502, result.get("error", "Failed to get login URL"))
        return result

    @router.get("/auth/login-status")
    async def auth_login_status(client_id: str = ""):
        if not client_id:
            raise HTTPException(400, "client_id is required")
        return poll_login_status(client_id)

    @router.post("/auth/add-from-sso")
    async def auth_add_from_sso(request: Request):
        body = await request.json()
        token = body.get("token", "").strip()
        user_id = body.get("user_id", "").strip()
        if not token:
            raise HTTPException(400, "token is required")
        account_id = _generate_account_id()
        api_key = _generate_api_key()
        is_default = body.get("is_default", False)
        db.add_account(account_id, api_key, token, user_id, is_default=is_default)
        return {"ok": True, "account_id": account_id, "api_key": api_key}

    # -- Settings --

    @router.get("/settings")
    async def get_settings():
        return {"settings": db.get_all_settings()}

    @router.put("/settings")
    async def update_settings(request: Request):
        body = await request.json()
        for key, value in body.items():
            db.set_setting(key, str(value))
        return {"ok": True}

    # -- Stats --

    @router.get("/stats")
    async def get_stats():
        return db.get_stats()

    @router.get("/stats/logs")
    async def get_logs(limit: int = 100, api_key: str = "", model: str = "", status: int = 0):
        if api_key or model or status:
            return {"logs": db.get_filtered_logs(limit, api_key=api_key, model=model, status_code=status)}
        return {"logs": db.get_recent_logs(limit)}

    @router.post("/stats/logs/cleanup")
    async def cleanup_logs(request: Request):
        body = await request.json()
        days = body.get("retention_days", 30)
        removed = db.cleanup_logs(days)
        return {"ok": True, "removed": removed}

    # -- Proxy Logs --

    @router.get("/proxy-logs")
    async def get_proxy_logs(lines: int = 100):
        from iflycode_proxy.proxy_logger import get_log_dir
        log_dir = get_log_dir()
        log_file = log_dir / "proxy.log"
        if not log_file.exists():
            return {"logs": [], "files": []}
        try:
            import subprocess
            result = subprocess.run(
                ["tail", "-n", str(min(lines, 1000)), str(log_file)],
                capture_output=True, text=True, timeout=5,
            )
            log_lines = result.stdout.strip().split("\n") if result.stdout.strip() else []
        except Exception:
            log_lines = []
        from iflycode_proxy.proxy_logger import get_log_files
        return {"logs": log_lines, "files": get_log_files()}

    # -- Health --

    @router.get("/health")
    async def health():
        accounts = db.list_accounts()
        db_size_mb = 0.0
        try:
            import os
            db_size_mb = os.path.getsize(str(db.db_path)) / (1024 * 1024)
        except OSError:
            pass
        return {"status": "ok", "accounts": len(accounts), "version": "1.0.0", "db_size_mb": round(db_size_mb, 2)}

    return router
