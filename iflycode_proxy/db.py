"""SQLite database for account management, settings, and request logs."""

import json
import logging
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("iflycode-proxy.db")

DATA_DIR = Path.home() / ".iflycode-proxy"
DB_PATH = DATA_DIR / "proxy.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL UNIQUE,
    spark_token TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    default_model TEXT NOT NULL DEFAULT '',
    credential_valid INTEGER DEFAULT -1,
    credential_error TEXT DEFAULT '',
    credential_refreshed_at TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS request_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key TEXT,
    model TEXT,
    endpoint TEXT,
    stream INTEGER,
    status_code INTEGER,
    latency_ms INTEGER,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def _generate_account_id() -> str:
    return f"acc-{secrets.token_hex(4)}"


def _generate_api_key() -> str:
    return f"sk-{secrets.token_hex(16)}"


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._migrate()
        return self._conn

    def _migrate(self):
        """Migrate schema as needed."""
        conn = self._get_conn()
        # Migration 1: account_id as PK
        cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        if "account_id" not in cols:
            self._migrate_account_pk(conn)
        # Migration 2: credential_valid, credential_error, credential_refreshed_at
        if "credential_valid" not in cols:
            conn.executescript("""
                ALTER TABLE accounts ADD COLUMN credential_valid INTEGER DEFAULT -1;
                ALTER TABLE accounts ADD COLUMN credential_error TEXT DEFAULT '';
                ALTER TABLE accounts ADD COLUMN credential_refreshed_at TEXT DEFAULT '';
            """)
            log.info("Migration: added credential_status columns to accounts")

    def _migrate_account_pk(self, conn):
        """Migrate old schema (api_key as PK) to new schema (account_id as PK)."""

        rows = conn.execute("SELECT api_key, token, user_id, is_default, default_model, created_at, updated_at FROM accounts").fetchall()

        conn.execute("DROP TABLE IF EXISTS accounts")
        conn.executescript(SCHEMA)

        from iflycode_proxy.crypto import encrypt
        for r in rows:
            old_api_key = r["api_key"]
            token = r["token"]
            account_id = f"acc-{old_api_key[:8]}" if old_api_key else _generate_account_id()
            api_key = _generate_api_key()
            user_id = r["user_id"] or ""
            is_default = r["is_default"]
            default_model = r["default_model"] or ""
            created_at = r["created_at"]
            updated_at = r["updated_at"]
            # token is already encrypted from old schema
            conn.execute(
                "INSERT INTO accounts (account_id, api_key, spark_token, user_id, is_default, default_model, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (account_id, api_key, token, user_id, is_default, default_model, created_at, updated_at),
            )
        conn.commit()
        log.info("Migration complete: %d accounts migrated", len(rows))

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- Account CRUD --

    def add_account(self, account_id: str, api_key: str, spark_token: str, user_id: str,
                    is_default: bool = False, default_model: str = ""):
        from iflycode_proxy.crypto import encrypt
        conn = self._get_conn()
        if is_default:
            conn.execute("UPDATE accounts SET is_default = 0")
        encrypted_token = encrypt(spark_token)
        conn.execute(
            "INSERT OR REPLACE INTO accounts (account_id, api_key, spark_token, user_id, is_default, default_model, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (account_id, api_key, encrypted_token, user_id, 1 if is_default else 0, default_model),
        )
        conn.commit()
        log.info("Account saved: account_id=%s api_key=%s user_id=%s", account_id, api_key[:8] + "...", user_id)

    def update_account_model(self, account_id: str, default_model: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE accounts SET default_model = ?, updated_at = datetime('now') WHERE account_id = ?",
            (default_model, account_id),
        )
        conn.commit()

    def renew_api_key(self, account_id: str) -> Optional[str]:
        conn = self._get_conn()
        row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            return None
        new_key = _generate_api_key()
        conn.execute(
            "UPDATE accounts SET api_key = ?, updated_at = datetime('now') WHERE account_id = ?",
            (new_key, account_id),
        )
        conn.commit()
        log.info("API key renewed for account_id=%s", account_id)
        return new_key

    def remove_account(self, account_id: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM accounts WHERE account_id = ?", (account_id,))
        conn.commit()
        return cursor.rowcount > 0

    def list_accounts(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT account_id, api_key, user_id, is_default, default_model, created_at, "
            "  COALESCE(credential_valid, -1) as credential_valid, "
            "  COALESCE(credential_error, '') as credential_error, "
            "  COALESCE(credential_refreshed_at, '') as credential_refreshed_at "
            "FROM accounts ORDER BY created_at"
        ).fetchall()
        return [
            {
                "account_id": r["account_id"],
                "api_key": r["api_key"],
                "user_id": r["user_id"],
                "is_default": bool(r["is_default"]),
                "default_model": r["default_model"] or "",
                "created_at": r["created_at"],
                "credential_valid": r["credential_valid"],
                "credential_error": r["credential_error"],
                "credential_refreshed_at": r["credential_refreshed_at"],
            }
            for r in rows
        ]

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        from iflycode_proxy.crypto import decrypt, is_encrypted
        conn = self._get_conn()
        row = conn.execute(
            "SELECT account_id, api_key, spark_token, user_id, is_default, default_model FROM accounts WHERE account_id = ?",
            (account_id,),
        ).fetchone()
        if not row:
            return None
        spark_token = row["spark_token"]
        if is_encrypted(spark_token):
            spark_token = decrypt(spark_token)
        return {
            "account_id": row["account_id"],
            "api_key": row["api_key"],
            "spark_token": spark_token,
            "user_id": row["user_id"],
            "is_default": bool(row["is_default"]),
            "default_model": row["default_model"] or "",
        }

    def get_account_by_api_key(self, api_key: str) -> Optional[Dict[str, Any]]:
        from iflycode_proxy.crypto import decrypt, is_encrypted
        conn = self._get_conn()
        row = conn.execute(
            "SELECT account_id, api_key, spark_token, user_id, is_default, default_model FROM accounts WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        if not row:
            return None
        spark_token = row["spark_token"]
        if is_encrypted(spark_token):
            spark_token = decrypt(spark_token)
        return {
            "account_id": row["account_id"],
            "api_key": row["api_key"],
            "spark_token": spark_token,
            "user_id": row["user_id"],
            "is_default": bool(row["is_default"]),
            "default_model": row["default_model"] or "",
        }

    def get_default_account(self) -> Optional[Dict[str, Any]]:
        from iflycode_proxy.crypto import decrypt, is_encrypted
        conn = self._get_conn()
        row = conn.execute(
            "SELECT account_id, api_key, spark_token, user_id FROM accounts WHERE is_default = 1"
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT account_id, api_key, spark_token, user_id FROM accounts ORDER BY created_at LIMIT 1"
            ).fetchone()
        if not row:
            return None
        spark_token = row["spark_token"]
        if is_encrypted(spark_token):
            spark_token = decrypt(spark_token)
        return {
            "account_id": row["account_id"],
            "api_key": row["api_key"],
            "spark_token": spark_token,
            "user_id": row["user_id"],
        }

    def set_default(self, account_id: str) -> bool:
        conn = self._get_conn()
        row = conn.execute("SELECT 1 FROM accounts WHERE account_id = ?", (account_id,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE accounts SET is_default = 0")
        conn.execute("UPDATE accounts SET is_default = 1, updated_at = datetime('now') WHERE account_id = ?", (account_id,))
        conn.commit()
        return True

    def validate_account(self, account_id: str) -> bool:
        acc = self.get_account(account_id)
        if not acc:
            return False
        from iflycode_proxy.client import Client
        try:
            client = Client(acc["spark_token"], acc.get("user_id", ""))
            valid = client.validate()
            client.close()
            return valid
        except Exception:
            return False

    # -- Settings --

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value),
        )
        conn.commit()

    def get_all_settings(self) -> Dict[str, str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # -- Request logs --

    def log_request(self, api_key: str, model: str, endpoint: str, stream: bool,
                    status_code: int, latency_ms: int,
                    prompt_tokens: int = 0, completion_tokens: int = 0):
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO request_logs (api_key, model, endpoint, stream, status_code, latency_ms, prompt_tokens, completion_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (api_key, model, endpoint, 1 if stream else 0, status_code, latency_ms, prompt_tokens, completion_tokens),
        )
        conn.commit()

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM request_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def get_filtered_logs(self, limit: int = 100, api_key: str = "",
                          model: str = "", status_code: int = 0) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        conditions: list[str] = []
        params: list[Any] = []
        if api_key:
            conditions.append("api_key = ?")
            params.append(api_key)
        if model:
            conditions.append("model = ?")
            params.append(model)
        if status_code > 0:
            if status_code == 1:
                conditions.append("status_code < 400")
            elif status_code == 2:
                conditions.append("status_code >= 400")
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = conn.execute(
            f"SELECT * FROM request_logs {where} ORDER BY id DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def cleanup_logs(self, retention_days: int = 30) -> int:
        conn = self._get_conn()
        cursor = conn.execute(
            "DELETE FROM request_logs WHERE created_at < datetime('now', ?)",
            (f"-{retention_days} days",),
        )
        conn.commit()
        return cursor.rowcount

    def get_stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        # All-time totals
        total = conn.execute("SELECT COUNT(*) as cnt FROM request_logs").fetchone()["cnt"]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt FROM request_logs GROUP BY model ORDER BY cnt DESC"
        ).fetchall()
        by_account = conn.execute(
            "SELECT api_key, COUNT(*) as cnt FROM request_logs GROUP BY api_key ORDER BY cnt DESC"
        ).fetchall()
        avg_latency = conn.execute(
            "SELECT AVG(latency_ms) as avg FROM request_logs WHERE latency_ms > 0"
        ).fetchone()["avg"]
        token_row = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct FROM request_logs"
        ).fetchone()
        all_time_errors = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE status_code >= 400"
        ).fetchone()["cnt"]

        # 24h / today stats
        h24 = "created_at >= datetime('now', '-24 hours')"
        today_requests = conn.execute(f"SELECT COUNT(*) as cnt FROM request_logs WHERE {h24}").fetchone()["cnt"]
        today_errors = conn.execute(f"SELECT COUNT(*) as cnt FROM request_logs WHERE {h24} AND status_code >= 400").fetchone()["cnt"]
        today_success = today_requests - today_errors
        today_stream = conn.execute(f"SELECT COUNT(*) as cnt FROM request_logs WHERE {h24} AND stream = 1").fetchone()["cnt"]
        today_latency = conn.execute(f"SELECT AVG(latency_ms) as avg FROM request_logs WHERE {h24} AND latency_ms > 0").fetchone()["avg"]
        today_tokens = conn.execute(
            f"SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct FROM request_logs WHERE {h24}"
        ).fetchone()
        today_by_model = conn.execute(
            f"SELECT model, COUNT(*) as cnt FROM request_logs WHERE {h24} AND model != '' GROUP BY model ORDER BY cnt DESC"
        ).fetchall()
        today_by_account = conn.execute(
            f"SELECT api_key, COUNT(*) as cnt FROM request_logs WHERE {h24} GROUP BY api_key ORDER BY cnt DESC"
        ).fetchall()

        # Hourly stats (24h)
        hourly = conn.execute(
            "SELECT strftime('%H', created_at) as hour, "
            "  COUNT(*) as count, "
            "  COALESCE(SUM(prompt_tokens),0) as input_tokens, "
            "  COALESCE(SUM(completion_tokens),0) as output_tokens, "
            "  SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as errors "
            f"FROM request_logs WHERE {h24} GROUP BY hour ORDER BY hour"
        ).fetchall()

        return {
            "total_requests": total,
            "by_model": [{"model": r["model"], "count": r["cnt"]} for r in by_model],
            "by_account": [{"api_key": r["api_key"], "count": r["cnt"]} for r in by_account],
            "avg_latency_ms": round(avg_latency or 0, 1),
            "accounts_count": conn.execute("SELECT COUNT(*) as cnt FROM accounts").fetchone()["cnt"],
            "prompt_tokens": token_row["pt"],
            "completion_tokens": token_row["ct"],
            "all_time": {
                "total_requests": total,
                "prompt_tokens": token_row["pt"],
                "completion_tokens": token_row["ct"],
                "error_count": all_time_errors,
            },
            "today_requests": today_requests,
            "today_success_count": today_success,
            "today_error_count": today_errors,
            "today_stream_count": today_stream,
            "today_avg_latency_ms": round(today_latency or 0, 1),
            "today_prompt_tokens": today_tokens["pt"],
            "today_completion_tokens": today_tokens["ct"],
            "today_by_model": [{"model": r["model"], "count": r["cnt"]} for r in today_by_model],
            "today_by_account": [{"api_key": r["api_key"], "count": r["cnt"]} for r in today_by_account],
            "hourly": [{"hour": r["hour"], "count": r["count"], "input_tokens": r["input_tokens"],
                         "output_tokens": r["output_tokens"], "errors": r["errors"]} for r in hourly],
        }

    def get_account_stats(self, account_id: str) -> Dict[str, Any]:
        conn = self._get_conn()
        # Get api_key for this account (used as log key)
        acc = self.get_account(account_id)
        log_key = acc["api_key"] if acc else account_id
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ?", (log_key,)
        ).fetchone()["cnt"]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY model ORDER BY cnt DESC",
            (log_key,),
        ).fetchall()
        avg_latency = conn.execute(
            "SELECT AVG(latency_ms) as avg FROM request_logs WHERE api_key = ? AND latency_ms > 0",
            (log_key,),
        ).fetchone()["avg"]
        by_endpoint = conn.execute(
            "SELECT endpoint, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY endpoint ORDER BY cnt DESC",
            (log_key,),
        ).fetchall()
        stream_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND stream = 1",
            (log_key,),
        ).fetchone()["cnt"]
        error_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND status_code >= 400",
            (log_key,),
        ).fetchone()["cnt"]
        token_row = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct "
            "FROM request_logs WHERE api_key = ?",
            (log_key,),
        ).fetchone()
        # Today's stats
        today_requests = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND date(created_at) = date('now')",
            (log_key,),
        ).fetchone()["cnt"]
        today_errors = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND status_code >= 400 AND date(created_at) = date('now')",
            (log_key,),
        ).fetchone()["cnt"]
        # 24h token consumption
        token_24h = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct "
            "FROM request_logs WHERE api_key = ? AND created_at >= datetime('now', '-24 hours')",
            (log_key,),
        ).fetchone()
        return {
            "account_id": account_id,
            "total_requests": total,
            "by_model": [{"model": r["model"], "count": r["cnt"]} for r in by_model],
            "by_endpoint": [{"endpoint": r["endpoint"], "count": r["cnt"]} for r in by_endpoint],
            "avg_latency_ms": round(avg_latency or 0, 1),
            "stream_count": stream_count,
            "error_count": error_count,
            "prompt_tokens": token_row["pt"],
            "completion_tokens": token_row["ct"],
            "today_requests": today_requests,
            "today_errors": today_errors,
            "today_success_rate": round((today_requests - today_errors) / today_requests * 100, 1) if today_requests > 0 else 0.0,
            "prompt_tokens_24h": token_24h["pt"],
            "completion_tokens_24h": token_24h["ct"],
        }

    def get_account_hourly_stats(self, account_id: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Return hourly request and token stats for the last N hours."""
        conn = self._get_conn()
        acc = self.get_account(account_id)
        log_key = acc["api_key"] if acc else account_id
        rows = conn.execute(
            "SELECT strftime('%Y-%m-%d %H:00', created_at) as hour, "
            "  COUNT(*) as request_count, "
            "  SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END) as error_count, "
            "  AVG(CASE WHEN latency_ms > 0 THEN latency_ms END) as avg_latency_ms, "
            "  COALESCE(SUM(prompt_tokens), 0) as prompt_tokens, "
            "  COALESCE(SUM(completion_tokens), 0) as completion_tokens "
            "FROM request_logs WHERE api_key = ? AND created_at >= datetime('now', ?) "
            "GROUP BY hour ORDER BY hour",
            (log_key, f"-{hours} hours"),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_account_recent_logs(self, account_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Return the most recent request logs for an account."""
        conn = self._get_conn()
        acc = self.get_account(account_id)
        log_key = acc["api_key"] if acc else account_id
        rows = conn.execute(
            "SELECT id, model, endpoint, stream, status_code, latency_ms, "
            "  prompt_tokens, completion_tokens, created_at "
            "FROM request_logs WHERE api_key = ? ORDER BY id DESC LIMIT ?",
            (log_key, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_account_models(self, account_id: str) -> List[Dict]:
        acc = self.get_account(account_id)
        if not acc:
            return []
        from iflycode_proxy.client import Client
        try:
            client = Client(acc["spark_token"], acc.get("user_id", ""))
            models_data = client.list_models()
            client.close()
            result = []
            for m in models_data:
                if not isinstance(m, dict):
                    continue
                result.append({
                    "modelCode": m.get("modelCode", m.get("name", "")),
                    "modelName": m.get("modelName", m.get("name", "")),
                    "modelId": m.get("modelId", ""),
                    "checked": m.get("checked", False),
                    "tokenExhausted": m.get("tokenExhausted", False),
                    "permissionCode": m.get("permissionCode", ""),
                    "permissionName": m.get("permissionName", ""),
                    "language": m.get("language", ""),
                })
            return result
        except Exception:
            return []

    def get_credential_router(self):
        from iflycode_proxy.credential_router import CredentialRouter
        router = CredentialRouter()
        for acc in self.list_accounts():
            full = self.get_account(acc["account_id"])
            if full:
                router.add_account(
                    full["account_id"], full["api_key"], full["spark_token"], full.get("user_id", ""),
                    default=full["is_default"],
                    default_model=full.get("default_model", ""),
                )
        return router

    # -- Credential status --

    def set_credential_status(self, account_id: str, valid: bool, error: str = ""):
        """Update credential validation result for an account."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE accounts SET credential_valid = ?, credential_error = ?, "
            "  credential_refreshed_at = datetime('now'), updated_at = datetime('now') "
            "WHERE account_id = ?",
            (1 if valid else 0, error, account_id),
        )
        conn.commit()

    def get_stale_accounts(self, normal_ttl_hours: int = 1, backoff_multiplier: int = 4) -> List[Dict[str, Any]]:
        """Return accounts that need credential re-validation.

        - valid accounts (credential_valid=1): last refreshed > normal_ttl_hours ago
        - failed accounts (credential_valid=0): last refreshed > normal_ttl_hours * backoff_multiplier ago
        - unknown accounts (credential_valid=-1 or never refreshed): always included
        """
        conn = self._get_conn()
        normal_cutoff = f"-{normal_ttl_hours} hours"
        backoff_cutoff = f"-{normal_ttl_hours * backoff_multiplier} hours"
        rows = conn.execute(
            "SELECT account_id, api_key, user_id, is_default, default_model, credential_valid, credential_refreshed_at "
            "FROM accounts WHERE "
            "  credential_refreshed_at = '' OR credential_refreshed_at IS NULL "
            "  OR credential_valid = -1 "
            "  OR (credential_valid = 1 AND credential_refreshed_at < datetime('now', ?)) "
            "  OR (credential_valid = 0 AND credential_refreshed_at < datetime('now', ?)) "
            "ORDER BY created_at",
            (normal_cutoff, backoff_cutoff),
        ).fetchall()
        return [dict(r) for r in rows]
