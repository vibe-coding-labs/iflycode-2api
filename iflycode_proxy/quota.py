"""Quota checking for per-account usage limits.

Checks daily request counts and monthly token consumption against
configurable limits stored in the account record.

Usage:
    from iflycode_proxy.quota import check_daily_quota
    allowed, reason = check_daily_quota(db, account_id, api_key)
    if not allowed:
        return HTTPException(429, reason)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from iflycode_proxy.db import Database

log = logging.getLogger("iflycode-proxy.quota")


def get_quota_limits(db: Database, account_id: str) -> tuple[Optional[int], Optional[int]]:
    """Return (daily_request_limit, monthly_token_limit) for an account.

    Both are None when no limit is configured (unlimited).
    Falls back to global defaults from settings.
    """
    acc = db.get_account(account_id)
    if not acc:
        return None, None

    daily = acc.get("daily_limit")
    monthly = acc.get("monthly_limit")

    # Fall back to global settings
    if daily is None or daily == 0:
        global_daily = db.get_setting("global_daily_limit", "0")
        daily = int(global_daily) if global_daily.isdigit() else None
    if monthly is None or monthly == 0:
        global_monthly = db.get_setting("global_monthly_limit", "0")
        monthly = int(global_monthly) if global_monthly.isdigit() else None

    return (daily if daily and daily > 0 else None,
            monthly if monthly and monthly > 0 else None)


def check_daily_quota(db: Database, account_id: str, api_key: str) -> tuple[bool, str]:
    """Check if account has exceeded its daily request limit.

    Returns (allowed: bool, reason: str).
    """
    daily_limit, monthly_limit = get_quota_limits(db, account_id)
    if daily_limit is None and monthly_limit is None:
        return True, ""

    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")

    conn = db._get_conn()

    if daily_limit is not None:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs "
            "WHERE api_key = ? AND date(created_at) = ?",
            (api_key, today),
        ).fetchone()
        count = row["cnt"] if row else 0
        if count >= daily_limit:
            log.warning("Daily quota exceeded for %s: %d >= %d",
                        account_id, count, daily_limit)
            return False, "Daily request limit reached ({}/{})".format(count, daily_limit)

    if monthly_limit is not None:
        row = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens), 0) + COALESCE(SUM(completion_tokens), 0) as total "
            "FROM request_logs "
            "WHERE api_key = ? AND strftime('%Y-%m', created_at) = ?",
            (api_key, this_month),
        ).fetchone()
        total = row["total"] if row else 0
        if total >= monthly_limit:
            log.warning("Monthly quota exceeded for %s: %d >= %d",
                        account_id, total, monthly_limit)
            return False, "Monthly token limit reached ({}/{})".format(total, monthly_limit)

    return True, ""


def get_usage(db: Database, account_id: str, api_key: str) -> dict:
    """Get current usage stats for an account.

    Returns dict with today_requests, daily_limit, month_tokens, monthly_limit.
    """
    daily_limit, monthly_limit = get_quota_limits(db, account_id)
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")

    conn = db._get_conn()

    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM request_logs "
        "WHERE api_key = ? AND date(created_at) = ?",
        (api_key, today),
    ).fetchone()
    today_requests = row["cnt"] if row else 0

    row = conn.execute(
        "SELECT COALESCE(SUM(prompt_tokens), 0) + COALESCE(SUM(completion_tokens), 0) as total "
        "FROM request_logs "
        "WHERE api_key = ? AND strftime('%Y-%m', created_at) = ?",
        (api_key, this_month),
    ).fetchone()
    month_tokens = row["total"] if row else 0

    return {
        "today_requests": today_requests,
        "daily_limit": daily_limit,
        "month_tokens": month_tokens,
        "monthly_limit": monthly_limit,
    }