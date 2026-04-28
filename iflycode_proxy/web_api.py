"""Web API endpoints for frontend management."""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException, Request

from iflycode_proxy.db import Database

log = logging.getLogger("iflycode-proxy.web-api")


def create_web_api_router(db: Database) -> APIRouter:
    router = APIRouter(prefix="/api")

    # -- Accounts --

    @router.get("/accounts")
    async def list_accounts():
        return {"accounts": db.list_accounts()}

    @router.post("/accounts")
    async def add_account(request: Request):
        body = await request.json()
        api_key = body.get("api_key", "").strip()
        token = body.get("token", "").strip()
        user_id = body.get("user_id", "").strip()
        is_default = body.get("is_default", False)
        default_model = body.get("default_model", "").strip()
        if not api_key or not token:
            raise HTTPException(400, "api_key and token are required")
        db.add_account(api_key, token, user_id, is_default=is_default, default_model=default_model)
        return {"ok": True, "api_key": api_key}

    @router.delete("/accounts/{api_key:path}")
    async def remove_account(api_key: str):
        if not db.remove_account(api_key):
            raise HTTPException(404, f"Account '{api_key}' not found")
        return {"ok": True}

    @router.put("/accounts/{api_key:path}/default")
    async def set_default(api_key: str):
        if not db.set_default(api_key):
            raise HTTPException(404, f"Account '{api_key}' not found")
        return {"ok": True}

    @router.post("/accounts/{api_key:path}/validate")
    async def validate_account(api_key: str):
        valid = db.validate_account(api_key)
        return {"api_key": api_key, "valid": valid}

    @router.get("/accounts/{api_key:path}/models")
    async def list_account_models(api_key: str):
        models = db.get_account_models(api_key)
        return {"models": models}

    @router.put("/accounts/{api_key:path}/model")
    async def update_account_model(api_key: str, request: Request):
        body = await request.json()
        default_model = body.get("default_model", "").strip()
        db.update_account_model(api_key, default_model)
        return {"ok": True, "api_key": api_key, "default_model": default_model}

    @router.get("/accounts/{api_key:path}/stats")
    async def get_account_stats(api_key: str):
        return db.get_account_stats(api_key)

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
    async def get_logs(limit: int = 100):
        return {"logs": db.get_recent_logs(limit)}

    # -- Health --

    @router.get("/health")
    async def health():
        accounts = db.list_accounts()
        return {"status": "ok", "accounts": len(accounts), "version": "1.0.0"}

    return router
