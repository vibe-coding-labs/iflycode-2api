"""Background janitor service — periodically cleans up old logs based on storage settings."""

import asyncio
import logging
import os
from typing import Optional

log = logging.getLogger("iflycode-proxy.janitor")

_DEFAULT_RETENTION_DAYS = 30
_DEFAULT_MAX_MB = 1024
_CHECK_INTERVAL_SECONDS = 3600  # 1 hour


def get_db_file_size_mb(db_path: str) -> float:
    """Return the size of the SQLite database file in megabytes."""
    try:
        return os.path.getsize(db_path) / (1024 * 1024)
    except OSError:
        return 0.0


async def janitor_loop(db_path: str, get_setting_fn, cleanup_fn) -> None:
    """Run the janitor loop forever, checking once per hour."""
    while True:
        await asyncio.sleep(_CHECK_INTERVAL_SECONDS)
        try:
            retention_days = int(get_setting_fn("log_retention_days") or str(_DEFAULT_RETENTION_DAYS))
            max_mb = int(get_setting_fn("storage_max_mb") or str(_DEFAULT_MAX_MB))
        except (ValueError, TypeError):
            retention_days = _DEFAULT_RETENTION_DAYS
            max_mb = _DEFAULT_MAX_MB

        removed_by_age = 0
        try:
            removed_by_age = cleanup_fn(retention_days)
            if removed_by_age > 0:
                log.info("Janitor: removed %d logs older than %d days", removed_by_age, retention_days)
        except Exception as e:
            log.error("Janitor: age-based cleanup failed: %s", e)

        db_size_mb = get_db_file_size_mb(db_path)
        if db_size_mb > max_mb:
            try:
                removed_by_size = cleanup_fn(retention_days=1)
                log.info(
                    "Janitor: DB size %.1f MB exceeds limit %d MB, removed %d recent logs",
                    db_size_mb, max_mb, removed_by_size,
                )
            except Exception as e:
                log.error("Janitor: size-based cleanup failed: %s", e)
        else:
            if removed_by_age == 0:
                log.debug("Janitor: no cleanup needed (DB %.1f MB / %d MB, retention %d days)", db_size_mb, max_mb, retention_days)


def start_janitor(db_path: str, get_setting_fn, cleanup_fn) -> Optional[asyncio.Task]:
    """Start the janitor background task. Returns the asyncio Task."""
    try:
        task = asyncio.create_task(janitor_loop(db_path, get_setting_fn, cleanup_fn))
        log.info("Janitor started (checking every %d seconds)", _CHECK_INTERVAL_SECONDS)
        return task
    except Exception as e:
        log.error("Failed to start janitor: %s", e)
        return None
