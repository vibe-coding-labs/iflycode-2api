"""iFlyCode SSO authentication service — handles login URL and token retrieval."""

import logging
import uuid
from typing import Optional

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

log = logging.getLogger("iflycode-proxy.auth")

BASE_URL = "https://iflycode-xfsaas.xfyun.cn"
LOGIN_URL_ENDPOINT = "/api/starspark/v1/agent/authSetting/query"
LOGIN_STATUS_ENDPOINT = "/api/starspark/v1/user/authorizationQuery"
LOGIN_BY_ACCOUNT_ENDPOINT = "/api/usercenter/v1/user/common/login"

# Fallback domains for account login (usercenter service may not be on all gateways)
ACCOUNT_LOGIN_BASES = [
    "https://iflycode-xfsaas.xfyun.cn",
    "https://iflycode.xfyun.cn",
]

RSA_PUB_KEY_PEM = (
    "-----BEGIN PUBLIC KEY-----\r\n"
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCFMVCHyq4CNE0sHQj5O3o6SFxo"
    "5yKK6/tpOC/zbpcomixQ17X7BBccZPyDcruIUkfNhlAeQHxFDn2NCOn2zdm3+6kes"
    "6KqHyjziBpHzjz9cQtvvEb8oT6ZvB2Ffsqr3JygMwDyPDHt0BmMo5CsuCvQvpmu7o"
    "9Qf5mkSx2UFIxlGQIDAQAB\r\n"
    "-----END PUBLIC KEY-----"
)


def _rsa_encrypt(plaintext: str) -> str:
    """Encrypt plaintext with iFlyCode's RSA public key (PKCS1, 64-byte blocks)."""
    public_key = serialization.load_pem_public_key(
        RSA_PUB_KEY_PEM.encode(), backend=default_backend()
    )
    data = plaintext.encode("utf-8")
    block_size = 64
    parts = []
    for i in range(0, len(data), block_size):
        chunk = data[i:i + block_size]
        encrypted = public_key.encrypt(chunk, padding.PKCS1v15())
        import base64
        parts.append(base64.b64encode(encrypted).decode())
    return ",".join(parts)

# Pending login sessions: clientId -> {login_url, status}
_pending_sessions: dict[str, dict] = {}


def get_login_url() -> dict:
    """Fetch SSO login URL from iFlyCode and return it with a generated clientId."""
    try:
        with httpx.Client(base_url=BASE_URL, timeout=10) as http:
            resp = http.get(LOGIN_URL_ENDPOINT)
            data = resp.json()
    except Exception as e:
        log.error("Failed to fetch login URL: %s", e)
        return {"ok": False, "error": str(e)}

    code = str(data.get("resCode", data.get("code", "")))
    if code not in ("0", "200"):
        return {"ok": False, "error": data.get("message", f"API returned code {code}")}

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
            data = resp.json()
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


def login_by_account(username: str, password: str) -> dict:
    """Login with iFlyCode username and password. Returns token on success."""
    client_id = str(uuid.uuid4())
    encrypted_user = _rsa_encrypt(username)
    encrypted_pw = _rsa_encrypt(password)

    last_error = None
    for base in ACCOUNT_LOGIN_BASES:
        try:
            with httpx.Client(base_url=base, timeout=15, verify=False) as http:
                resp = http.post(
                    f"{LOGIN_BY_ACCOUNT_ENDPOINT}?clientId={client_id}",
                    headers={"Content-Type": "application/json"},
                    json={"user": encrypted_user, "pwCode": encrypted_pw},
                )
            if resp.status_code == 404:
                log.warning("Login endpoint 404 on %s, trying next base", base)
                last_error = f"登录服务在 {base} 上不可用 (404)"
                continue
            if resp.status_code == 405:
                log.warning("Login endpoint 405 on %s, trying next base", base)
                last_error = f"登录服务在 {base} 上方法不允许 (405)"
                continue
            data = resp.json()
            break
        except Exception as e:
            log.warning("Account login failed on %s: %s", base, e)
            last_error = str(e)
            continue
    else:
        log.error("Account login failed on all bases: %s", last_error)
        return {"ok": False, "error": f"登录失败：所有服务器均不可用（{last_error}）。该接口可能需要在内网环境或通过 IDE 客户端访问，建议使用 SSO 登录方式。"}

    code = str(data.get("resCode", data.get("code", "")))
    if code not in ("0", "200"):
        msg = data.get("message", data.get("resMsg", f"Login failed (code {code})"))
        return {"ok": False, "error": msg}

    token = data.get("token") or data.get("obj", {}).get("token", "") if isinstance(data.get("obj"), dict) else ""
    if not token:
        token = data.get("token", "")

    if not token:
        return {"ok": False, "error": "登录失败：未获取到 token"}

    user_id = ""
    enterprise_dto = data.get("enterpriseDto") or data.get("obj", {}).get("enterpriseDto", {})
    if isinstance(enterprise_dto, dict):
        user_id = enterprise_dto.get("userId", "")
    if not user_id:
        user_id = data.get("userId", "")

    return {
        "ok": True,
        "token": token,
        "user_id": str(user_id),
        "username": username,
    }
