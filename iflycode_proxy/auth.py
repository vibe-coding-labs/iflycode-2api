"""iFlyCode SSO authentication service — handles login URL and token retrieval."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

import httpx

log = logging.getLogger("iflycode-proxy.auth")

BASE_URL = "https://iflycode-xfsaas.xfyun.cn"
FALLBACK_LOGIN_URL = "https://iflycode.xfyun.cn/chooseIdentity"
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
    """Fetch SSO login URL from iFlyCode and return it with a generated clientId.

    Falls back to a hardcoded URL when the upstream API is unavailable.
    """
    import time

    login_url = ""
    last_error = ""

    for attempt in range(2):
        try:
            with httpx.Client(base_url=BASE_URL, timeout=10) as http:
                resp = http.get(LOGIN_URL_ENDPOINT)
                data, err = _safe_json(resp)
                if err:
                    last_error = err
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    break
                code = str(data.get("resCode", data.get("code", "")))
                if code not in ("0", "200"):
                    msg = data.get("message", f"API returned code {code}")
                    last_error = msg
                    if attempt == 0:
                        time.sleep(1)
                        continue
                    break
                obj = data.get("obj") or data.get("data") or {}
                login_url = obj.get("loginUrl", "")
                if not login_url:
                    last_error = "loginUrl not found in response"
                    if attempt == 0:
                        time.sleep(1)
                        continue
                break
        except Exception as e:
            last_error = f"无法连接上游服务: {e}"
            if attempt == 0:
                time.sleep(1)
                continue

    # Fallback: use hardcoded login URL when API fails
    is_fallback = not login_url
    if is_fallback:
        login_url = FALLBACK_LOGIN_URL
        log.warning("Using fallback login URL (upstream error: %s)", last_error)

    client_id = str(uuid.uuid4())
    separator = "&" if "?" in login_url else "?"
    full_url = f"{login_url}{separator}clientId={client_id}&type=ide&ideType=IDEA"

    _pending_sessions[client_id] = {"login_url": full_url, "status": "pending"}

    result = {
        "ok": True,
        "login_url": full_url,
        "client_id": client_id,
    }
    if is_fallback:
        result["fallback"] = True
        result["upstream_error"] = last_error
    return result


def poll_login_status(client_id: str) -> dict:
    """Poll login status using clientId. Returns token if authenticated."""
    if client_id not in _pending_sessions:
        return {"ok": False, "status": "unknown", "error": "Invalid clientId"}

    data = None
    last_error = ""

    for attempt in range(2):
        try:
            with httpx.Client(base_url=BASE_URL, timeout=10) as http:
                resp = http.get(
                    LOGIN_STATUS_ENDPOINT,
                    headers={"Content-Type": "application/json", "clientId": client_id},
                )
                data, err = _safe_json(resp)
                if err:
                    last_error = err
                    data = None  # reset so we know it failed
                    if attempt == 0:
                        import time
                        time.sleep(1)
                        continue
                    break
        except Exception as e:
            last_error = str(e)
            data = None
            if attempt == 0:
                import time
                time.sleep(1)
                continue

    if data is None:
        log.warning("Login status poll failed after retries: %s", last_error)
        return {"ok": False, "status": "pending", "error": last_error}

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