"""Proxy request/response logger with file rotation and size limits."""

import json
import logging
import os
import time
import traceback
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

LOG_DIR = Path.home() / ".iflycode-proxy" / "logs"
MAX_BYTES = 50 * 1024 * 1024  # 50 MB per file
BACKUP_COUNT = 5  # keep 5 rotated files max (250 MB total)


def get_proxy_logger() -> logging.Logger:
    """Get or create the proxy request logger with RotatingFileHandler."""
    logger = logging.getLogger("iflycode-proxy.proxy-log")

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "proxy.log"

    handler = RotatingFileHandler(
        str(log_file),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


_log = get_proxy_logger()


def _truncate(text: str, max_len: int = 2000) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... (truncated, {len(text)} chars total)"


def log_request(
    protocol: str,
    endpoint: str,
    api_key: str,
    model: str,
    messages_summary: str,
    stream: bool,
    extra: Optional[Dict[str, Any]] = None,
):
    """Log incoming proxy request with context."""
    entry = {
        "event": "request",
        "protocol": protocol,
        "endpoint": endpoint,
        "api_key": api_key[:8] + "..." if len(api_key) > 8 else api_key,
        "model": model,
        "messages_summary": _truncate(messages_summary),
        "stream": stream,
        "timestamp": datetime.now().isoformat(),
    }
    if extra:
        for k, v in extra.items():
            entry[k] = _truncate(str(v)) if isinstance(v, str) else v
    _log.info(json.dumps(entry, ensure_ascii=False))


def log_response(
    protocol: str,
    endpoint: str,
    api_key: str,
    model: str,
    status_code: int,
    latency_ms: int,
    response_summary: str = "",
    stream: bool = False,
):
    """Log proxy response."""
    entry = {
        "event": "response",
        "protocol": protocol,
        "endpoint": endpoint,
        "api_key": api_key[:8] + "..." if len(api_key) > 8 else api_key,
        "model": model,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "stream": stream,
        "response_summary": _truncate(response_summary),
        "timestamp": datetime.now().isoformat(),
    }
    _log.info(json.dumps(entry, ensure_ascii=False))


def log_error(
    protocol: str,
    endpoint: str,
    api_key: str,
    model: str,
    error: Exception,
    context: Optional[Dict[str, Any]] = None,
):
    """Log proxy error with full traceback and context."""
    entry = {
        "event": "error",
        "protocol": protocol,
        "endpoint": endpoint,
        "api_key": api_key[:8] + "..." if len(api_key) > 8 else api_key,
        "model": model,
        "error_type": type(error).__name__,
        "error_message": _truncate(str(error)),
        "traceback": _truncate(traceback.format_exc(), max_len=5000),
        "timestamp": datetime.now().isoformat(),
    }
    if context:
        for k, v in context.items():
            if isinstance(v, str):
                entry[k] = _truncate(v)
            elif isinstance(v, (dict, list)):
                entry[k] = _truncate(json.dumps(v, ensure_ascii=False, default=str))
            else:
                entry[k] = v
    _log.error(json.dumps(entry, ensure_ascii=False))


def log_upstream_request(
    protocol: str,
    method: str,
    url: str,
    status_code: int,
    latency_ms: int,
    api_key: str = "",
    error: str = "",
):
    """Log upstream iFlyCode API request."""
    entry = {
        "event": "upstream",
        "protocol": protocol,
        "method": method,
        "url": url,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "api_key": api_key[:8] + "..." if len(api_key) > 8 else api_key,
        "timestamp": datetime.now().isoformat(),
    }
    if error:
        entry["error"] = _truncate(error)
    _log.info(json.dumps(entry, ensure_ascii=False))


def get_log_dir() -> Path:
    return LOG_DIR


def get_log_files() -> list:
    """List all log files with sizes."""
    if not LOG_DIR.exists():
        return []
    files = []
    for f in sorted(LOG_DIR.glob("proxy.log*")):
        try:
            size = f.stat().st_size
            files.append({"name": f.name, "size_bytes": size, "size_mb": round(size / (1024 * 1024), 2)})
        except OSError:
            pass
    return files
