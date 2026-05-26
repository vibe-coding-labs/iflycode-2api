"""iFlyCode SSO authentication service — handles login URL and token retrieval."""

import logging
import re
import uuid
from typing import Optional

import httpx

log = logging.getLogger("iflycode-proxy.auth")

BASE_URL = "https://iflycode-xfsaas.xfyun.cn"
LOGIN_URL_ENDPOINT = "/api/starspark/v1/agent/authSetting/query"
LOGIN_STATUS_ENDPOINT = "/api/starspark/v1/user/authorizationQuery"

# Pending login sessions: clientId -> {login_url, status}
_pending_sessions: dict[str, dict] = {}


def _safe_json(resp: httpx.Response) -> tuple[dict, str]:
    """Try to parse response as JSON. Returns (data, error_msg).

    If the response is not valid JSON (e.g. HTML from a gateway), returns
    ({}, error_msg) with a clean Chinese error message.
    """
    try:
        return resp.json(), ""
    except Exception:
        # Clean up HTML/tag fragments from error snippet
        snippet = re.sub(r'<[^>]+>', '', resp.text[:150])
        snippet = re.sub(r'\s+', ' ', snippet).strip()
        return {}, f"上游服务异常 (HTTP {resp.status_code})"


def get_login_url() -> dict:
    """Fetch SSO login URL from iFlyCode and return it with a generated clientId."""
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10) as http:
            resp = http.get(LOGIN_URL_ENDPOINT)
            data, err = _safe_json(resp)
            if err:
                log.error("Failed to fetch login URL: %s", err)
                return {"ok": False, "error": err}
    except Exception as e:
        log.error("Failed to fetch login URL: %s", e)
        return {"ok": False, "error": f"无法连接上游服务: {e}"}

    code = str(data.get("resCode", data.get("code", "")))
    if code not in ("0", "200"):
        msg = data.get("message", f"API returned code {code}")
        return {"ok": False, "error": msg}

    obj = data.get("obj") or data.get("data") or {}
    login_url = obj.get("loginUrl", "")
    if not login_url:
        return {"ok": False, "error": "loginUrl not found in response"}

    client_id = str(uuid.uuid4())
    separator = "&" if "?" in login_url else "?"
    full_url = f"{login_url}{separator}clientId={client_id}&type=ide&ideType=IDEA"

    _pending_sessions[client_id] = {"login_url": full_url, "status": "pending"}

    return {
        "ok": True,
        "login_url": full_url,
        "client_id": client_id,
    }


def poll_login_status(client_id: str) -> dict:
    """Poll login status using clientId. Returns token if authenticated."""
    if client_id not in _pending_sessions:
        return {"ok": False, "status": "unknown", "error": "Invalid clientId"}

    try:
        with httpx.Client(base_url=BASE_URL, timeout=10) as http:
            resp = http.get(
                LOGIN_STATUS_ENDPOINT,
                headers={"Content-Type": "application/json", "clientId": client_id},
            )
            data, err = _safe_json(resp)
            if err:
                log.warning("Login status poll failed: %s", err)
                return {"ok": False, "status": "pending", "error": err}
    except Exception as e:
        log.warning("Login status poll failed: %s", e)
        return {"ok": False, "status": "pending", "error": str(e)}

    code = str(data.get("resCode", data.get("code", "")))
    if code not in ("0", "200"):
        return {"ok": False, "status": "pending"}

    token = data.get("token") or data.get("obj", {}).get("token") if isinstance(data.get("obj"), dict) else None
    if not token:
        token = data.get("token")

    if token:
        user_id = data.get("userId") or data.get("obj", {}).get("userId", "") if isinstance(data.get("obj"), dict) else ""
        _pending_sessions.pop(client_id, None)
        return {
            "ok": True,
            "status": "authenticated",
            "token": token,
            "user_id": str(user_id or ""),
        }

    return {"ok": False, "status": "pending"}