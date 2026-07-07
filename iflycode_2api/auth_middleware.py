"""JWT authentication middleware for management API.

Protects /api/* endpoints (except whitelisted auth paths).
Uses bcrypt password hashing and JWT tokens.

Reference: JoyCodeProxy pkg/auth/middleware.go, jwt.go, password.go
"""

import logging
import secrets
import time
from typing import Callable, Optional

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None  # type: ignore[assignment]

try:
    import bcrypt
except ImportError:
    bcrypt = None  # type: ignore[assignment]

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from iflycode_2api.db import Database

log = logging.getLogger("iflycode-2api.auth")

# Endpoints that don't require authentication
AUTH_WHITELIST = frozenset({
    "/api/auth/status",
    "/api/auth/init",
    "/api/auth/login",
    "/api/health",
})

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_SECONDS = 86400 * 7  # 7 days


def _jwt_secret() -> str:
    """Generate a random JWT secret."""
    return secrets.token_hex(32)


def hash_password(password: str) -> str:
    """Hash a password with bcrypt."""
    if bcrypt is None:
        raise RuntimeError("bcrypt is required for password auth: pip install bcrypt")
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash."""
    if bcrypt is None:
        raise RuntimeError("bcrypt is required for password auth: pip install bcrypt")
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except Exception:
        return False


def generate_token(username: str, secret: str) -> str:
    """Generate a JWT token for the given username."""
    if pyjwt is None:
        raise RuntimeError("pyjwt is required for auth: pip install pyjwt")
    payload = {
        "username": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_SECONDS,
        "iss": "iflycode-2api",
    }
    return pyjwt.encode(payload, secret, algorithm=JWT_ALGORITHM)


def validate_token(token_str: str, secret: str) -> Optional[dict]:
    """Validate a JWT token and return its claims, or None on failure."""
    if pyjwt is None:
        raise RuntimeError("pyjwt is required for auth: pip install pyjwt")
    try:
        payload = pyjwt.decode(token_str, secret, algorithms=[JWT_ALGORITHM])
        return payload
    except pyjwt.ExpiredSignatureError:
        return None
    except pyjwt.InvalidTokenError:
        return None


class AuthMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that requires JWT auth for /api/* endpoints."""

    def __init__(self, app: FastAPI, db: Database):
        super().__init__(app)
        self.db = db

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path

        # Only protect /api/* endpoints
        if not path.startswith("/api/"):
            return await call_next(request)

        # Skip whitelisted paths
        if path in AUTH_WHITELIST:
            return await call_next(request)

        # OPTIONS (CORS preflight) always passes
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check if password auth is configured
        password_hash = self.db.get_setting("auth_password_hash")
        jwt_secret = self.db.get_setting("auth_jwt_secret")

        # No password set → auth not configured, allow access
        if not password_hash:
            return await call_next(request)

        # No JWT secret → misconfiguration
        if not jwt_secret:
            return JSONResponse(
                status_code=500,
                content={"detail": "Server configuration error: JWT secret not set"},
            )

        # Extract Bearer token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid authorization header"},
            )

        token_str = auth_header[7:]
        claims = validate_token(token_str, jwt_secret)
        if claims is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Store username in request state for downstream handlers
        request.state.auth_username = claims.get("username", "")
        return await call_next(request)
