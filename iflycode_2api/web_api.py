"""Web API endpoints for frontend management."""

import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from iflycode_2api.auth import get_login_url, poll_login_status
from iflycode_2api.auth_middleware import hash_password, check_password, generate_token, _jwt_secret
from iflycode_2api.db import Database, _generate_account_id, _generate_api_key
from iflycode_2api.sessions import get_active_sessions, get_all_active_counts, session_stats

log = logging.getLogger("iflycode-2api.web-api")


def create_web_api_router(db: Database, cred_router=None) -> APIRouter:
    router = APIRouter(prefix="/api")

    def _get_keeper(request: Request):
        return getattr(request.app.state, "keeper", None)

    # -- Accounts --

    @router.get("/accounts")
    async def list_accounts():
        accounts = db.list_accounts()
        # Enrich with active sessions
        active_counts = get_all_active_counts()
        for acc in accounts:
            acc_id = acc.get("account_id", "")
            acc["active_sessions"] = active_counts.get(acc_id, 0)
        return {"accounts": accounts}

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

        # Trigger immediate credential check (fire-and-forget)
        k = _get_keeper(request)
        if k:
            import threading
            threading.Thread(target=k.trigger_immediate_check, args=(account_id,), daemon=True).start()

        return {"ok": True, "account_id": account_id, "api_key": api_key}

    @router.delete("/accounts/{account_id}")
    async def remove_account(account_id: str):
        if not db.remove_account(account_id):
            raise HTTPException(404, f"Account '{account_id}' not found")
        return {"ok": True}

    @router.put("/accounts/{account_id}/default")
    async def set_default(account_id: str):
        if not db.set_default(account_id):
            raise HTTPException(404, f"Account '{account_id}' not found")
        return {"ok": True}

    @router.post("/accounts/{account_id}/validate")
    async def validate_account(request: Request, account_id: str):
        k = _get_keeper(request)
        if k:
            cached = k.get_cached_status(account_id)
            if cached["age_seconds"] < 60 and cached["valid"] is not None:
                return {"account_id": account_id, "valid": cached["valid"], "error": cached.get("error", ""), "cached": True}
            # Force re-check
            valid = k.trigger_immediate_check(account_id)
            if valid is not None:
                error = "" if valid else "credential check failed"
                return {"account_id": account_id, "valid": valid, "error": error, "cached": False}
        # Fallback: direct check
        valid = db.validate_account(account_id)
        return {"account_id": account_id, "valid": valid, "cached": False}

    @router.get("/accounts/{account_id}/credential-status")
    async def get_credential_status(request: Request, account_id: str):
        """Return the current credential validation status."""
        status = {"valid": None, "error": "", "last_checked": "", "cached": False}
        k = _get_keeper(request)
        if k:
            cached = k.get_cached_status(account_id)
            if cached["valid"] is not None:
                status["valid"] = cached["valid"]
                status["error"] = cached.get("error", "")
                status["cached"] = True
        # Fallback: read from DB
        if status["valid"] is None:
            conn = db._get_conn()
            row = conn.execute(
                "SELECT credential_valid, credential_error, credential_refreshed_at "
                "FROM accounts WHERE account_id = ?", (account_id,)
            ).fetchone()
            if row:
                cv = row["credential_valid"]
                status["valid"] = cv == 1 if cv != -1 else None
                # sqlite3.Row doesn't support .get(), use try/except
                try:
                    status["error"] = row["credential_error"] or ""
                except (KeyError, IndexError):
                    status["error"] = ""
                try:
                    status["last_checked"] = row["credential_refreshed_at"] or ""
                except (KeyError, IndexError):
                    status["last_checked"] = ""
        return status

    @router.post("/accounts/{account_id}/trigger-validation")
    async def trigger_validation(request: Request, account_id: str):
        """Force an immediate credential check and return result."""
        k = _get_keeper(request)
        if k:
            valid = k.trigger_immediate_check(account_id)
            if valid is not None:
                return {"account_id": account_id, "valid": valid}
        # Fallback
        valid = db.validate_account(account_id)
        db.set_credential_status(account_id, valid, "" if valid else "credential check failed")
        return {"account_id": account_id, "valid": valid}

    @router.get("/accounts/{account_id}/sessions")
    async def get_account_sessions(account_id: str):
        count = get_active_sessions(account_id)
        return {"account_id": account_id, "active_sessions": count}

    @router.get("/accounts/{account_id}/models")
    async def list_account_models(account_id: str):
        models = db.get_account_models(account_id)
        return {"models": models}

    @router.put("/accounts/{account_id}/model")
    async def update_account_model(account_id: str, request: Request):
        body = await request.json()
        default_model = body.get("default_model", "").strip()
        db.update_account_model(account_id, default_model)
        if cred_router:
            cred_router.set_default_model(account_id, default_model)
        return {"ok": True, "account_id": account_id, "default_model": default_model}

    @router.get("/accounts/{account_id}/stats")
    async def get_account_stats(account_id: str):
        return db.get_account_stats(account_id)

    @router.get("/accounts/{account_id}/hourly-stats")
    async def get_account_hourly_stats(account_id: str, hours: int = 24):
        if hours < 1 or hours > 720:
            hours = 24
        return {"hours": hours, "data": db.get_account_hourly_stats(account_id, hours)}

    @router.get("/accounts/{account_id}/recent-logs")
    async def get_account_recent_logs(account_id: str, limit: int = 20):
        if limit < 1 or limit > 100:
            limit = 20
        return {"logs": db.get_account_recent_logs(account_id, limit)}

    @router.post("/accounts/{account_id}/renew-key")
    async def renew_api_key(account_id: str):
        new_key = db.renew_api_key(account_id)
        if not new_key:
            raise HTTPException(404, f"Account '{account_id}' not found")
        return {"ok": True, "account_id": account_id, "api_key": new_key}

    @router.put("/accounts/{account_id}/remark")
    async def update_account_remark(account_id: str, request: Request):
        """Update the remark/alias for an account."""
        body = await request.json()
        remark = body.get("remark", "").strip()
        db.update_account_remark(account_id, remark)
        return {"ok": True, "account_id": account_id, "remark": remark}

    @router.post("/accounts-export")
    async def export_accounts():
        """Export all accounts with decrypted credentials."""
        accounts = db.export_accounts()
        # Strip spark_token from response for security
        safe = [{k: v for k, v in a.items() if k != "spark_token"} for a in accounts]
        return {"ok": True, "accounts": safe, "count": len(safe)}

    @router.post("/accounts-import")
    async def import_accounts(request: Request):
        """Import accounts from exported data."""
        body = await request.json()
        account_list = body.get("accounts", [])
        result = db.import_accounts(account_list)
        return {"ok": True, **result}

    @router.put("/accounts/reorder")
    async def reorder_accounts(request: Request):
        """Reorder accounts by providing ordered list of account_ids."""
        body = await request.json()
        account_ids = body.get("account_ids", [])
        if not account_ids:
            raise HTTPException(400, "account_ids list is required")
        db.reorder_accounts(account_ids)
        return {"ok": True}

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

    # -- Auth (password/JWT login) --

    @router.get("/auth/status")
    async def auth_status():
        """Return whether the proxy has been initialized with a password."""
        password_hash = db.get_setting("auth_password_hash")
        return {"initialized": bool(password_hash), "auth_enabled": bool(password_hash)}

    @router.post("/auth/init")
    async def auth_init(request: Request):
        """Initialize the proxy with a root password (one-time setup)."""
        if db.get_setting("auth_password_hash"):
            raise HTTPException(400, "Already initialized")
        body = await request.json()
        password = body.get("password", "")
        if len(password) < 6:
            raise HTTPException(400, "Password must be at least 6 characters")
        hashed = hash_password(password)
        secret = _jwt_secret()
        db.set_setting("auth_password_hash", hashed)
        db.set_setting("auth_jwt_secret", secret)
        token = generate_token("root", secret)
        log.info("Auth initialized with password hash")
        return {"ok": True, "token": token}

    @router.post("/auth/login")
    async def auth_login(request: Request):
        """Authenticate with root password and receive a JWT token."""
        password_hash = db.get_setting("auth_password_hash")
        jwt_secret = db.get_setting("auth_jwt_secret")
        if not password_hash or not jwt_secret:
            raise HTTPException(400, "Not initialized. Visit /setup first.")
        body = await request.json()
        password = body.get("password", "")
        if not check_password(password, password_hash):
            raise HTTPException(401, "Invalid password")
        token = generate_token("root", jwt_secret)
        return {"ok": True, "token": token}

    @router.post("/auth/change-password")
    async def auth_change_password(request: Request):
        """Change the root password (requires old password)."""
        password_hash = db.get_setting("auth_password_hash")
        jwt_secret = db.get_setting("auth_jwt_secret")
        if not password_hash or not jwt_secret:
            raise HTTPException(400, "Not initialized")
        body = await request.json()
        old = body.get("old_password", "")
        new_pw = body.get("new_password", "")
        if not check_password(old, password_hash):
            raise HTTPException(401, "Invalid current password")
        if len(new_pw) < 6:
            raise HTTPException(400, "New password must be at least 6 characters")
        hashed = hash_password(new_pw)
        new_secret = _jwt_secret()
        db.set_setting("auth_password_hash", hashed)
        db.set_setting("auth_jwt_secret", new_secret)
        return {"ok": True, "message": "Password changed. Please re-login."}

    # -- Web Search --

    @router.post("/v1/web-search")
    async def web_search(request: Request):
        """Web search endpoint (currently unavailable for iFlyCode upstream)."""
        return {"search_result": [], "note": "Web search requires upstream search API support"}

    @router.post("/v1/rerank")
    async def rerank(request: Request):
        """Document reranking endpoint (currently unavailable for iFlyCode upstream)."""
        return {"result": [], "note": "Reranking requires upstream rerank API support"}

    @router.post("/api/auth/change-password")
    async def api_change_password(request: Request):
        return await auth_change_password(request)

    @router.get("/api/github-stars")
    async def github_stars():
        """Return the project's GitHub star count."""
        try:
            import httpx
            resp = httpx.get("https://api.github.com/repos/vibe-coding-labs/iflycode-2api", timeout=5)
            data = resp.json()
            stars = data.get("stargazers_count", 0)
            return {"stars": stars}
        except Exception:
            return {"stars": 0}

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
        from iflycode_2api.proxy_logger import get_log_dir
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
        from iflycode_2api.proxy_logger import get_log_files
        return {"logs": log_lines, "files": get_log_files()}

    # -- Sessions --

    @router.get("/sessions")
    async def get_session_stats():
        return session_stats()

    # -- Keepalive --

    @router.get("/keepalive/statuses")
    async def get_keepalive_statuses(request: Request):
        k = _get_keeper(request)
        if k:
            return {"statuses": k.get_all_cached_statuses()}
        return {"statuses": {}}

    @router.post("/keepalive/trigger")
    async def trigger_keepalive_now(request: Request, account_id: str = ""):
        """Trigger an immediate keepalive check round.

        If account_id is provided, only that account is checked.
        Otherwise all stale accounts are checked.
        """
        k = _get_keeper(request)
        if k:
            import threading
            if account_id:
                threading.Thread(target=k.trigger_immediate_check, args=(account_id,), daemon=True).start()
                return {"ok": True, "message": f"Keepalive check triggered for {account_id}"}
            else:
                # Trigger a full round by running check_round in background
                def _run_round():
                    try:
                        stale = db.get_stale_accounts()
                        for acc in stale:
                            aid = acc.get("account_id") or acc.get("id", "")
                            if aid:
                                k.trigger_immediate_check(aid)
                                import time
                                time.sleep(2)
                    except Exception:
                        pass
                threading.Thread(target=_run_round, daemon=True).start()
                return {"ok": True, "message": "Full keepalive round triggered"}
        return {"ok": False, "message": "Keepalive not available"}

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
        s = session_stats()
        return {
            "status": "ok",
            "accounts": len(accounts),
            "version": "1.0.0",
            "db_size_mb": round(db_size_mb, 2),
            "active_sessions": s.get("active_sessions", 0),
        }

    # -- Batch Import (API Key authenticated, no JWT needed) --

    @router.post("/v1/accounts/batch-import")
    async def batch_import_accounts(request: Request):
        """Batch import accounts via API Key (OpenAI-compatible auth).

        The caller must provide a valid x-api-key header that belongs to
        an already-configured account in this proxy. This ensures only
        authenticated users can import new accounts.
        """
        api_key = request.headers.get("x-api-key", "")
        if not api_key:
            raise HTTPException(401, "x-api-key header is required")
        # Validate API key against known accounts
        owner = db.get_account_by_api_key(api_key)
        if not owner:
            raise HTTPException(403, "Unknown API key — batch import requires a valid key from an existing account")
        body = await request.json()
        account_list = body.get("accounts", [])
        if not account_list or not isinstance(account_list, list):
            raise HTTPException(400, "accounts must be a non-empty array")
        added = 0
        account_ids = []
        errors = []
        for i, acc_data in enumerate(account_list):
            try:
                spark_token = (acc_data.get("spark_token") or "").strip()
                if not spark_token:
                    errors.append({"index": i, "error": "spark_token is required"})
                    continue
                account_id = _generate_account_id()
                api_key_new = _generate_api_key()
                user_id = (acc_data.get("user_id") or "").strip()
                is_default = bool(acc_data.get("is_default", False))
                daily_limit = int(acc_data.get("daily_limit", 0))
                monthly_limit = int(acc_data.get("monthly_limit", 0))
                remark = (acc_data.get("remark") or "").strip()
                db.add_account(
                    account_id, api_key_new, spark_token, user_id,
                    is_default=is_default, daily_limit=daily_limit,
                    monthly_limit=monthly_limit, remark=remark,
                )
                added += 1
                account_ids.append({"account_id": account_id, "api_key": api_key_new})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
        return {"ok": True, "added": added, "account_ids": account_ids, "errors": errors}

    @router.get("/accounts/{account_id}/quota")
    async def get_account_quota(account_id: str):
        """Get quota configuration and current usage for an account."""
        acc = db.get_account(account_id)
        if not acc:
            raise HTTPException(404, "Account not found")
        from iflycode_2api.quota import get_usage
        usage = get_usage(db, account_id, acc["api_key"])
        return {
            "account_id": account_id,
            "daily_limit": usage["daily_limit"],
            "monthly_limit": usage["monthly_limit"],
            "today_requests": usage["today_requests"],
            "month_tokens": usage["month_tokens"],
        }

    @router.put("/accounts/{account_id}/quota")
    async def update_account_quota(account_id: str, request: Request):
        """Update quota limits for an account."""
        body = await request.json()
        daily_limit = int(body.get("daily_limit", 0))
        monthly_limit = int(body.get("monthly_limit", 0))
        conn = db._get_conn()
        conn.execute(
            "UPDATE accounts SET daily_limit = ?, monthly_limit = ?, updated_at = datetime('now') "
            "WHERE account_id = ?",
            (daily_limit, monthly_limit, account_id),
        )
        conn.commit()
        return {"ok": True, "account_id": account_id, "daily_limit": daily_limit, "monthly_limit": monthly_limit}

    return router