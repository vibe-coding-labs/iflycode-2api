"""SQLite database for account management, settings, and request logs."""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("iflycode-proxy.db")

DATA_DIR = Path.home() / ".iflycode-proxy"
DB_PATH = DATA_DIR / "proxy.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    api_key TEXT PRIMARY KEY,
    token TEXT NOT NULL,
    user_id TEXT NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    default_model TEXT NOT NULL DEFAULT '',
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


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            self._migrate()
        return self._conn

    def _migrate(self):
        """Add columns that may not exist in older databases."""
        conn = self._conn
        try:
            conn.execute("ALTER TABLE request_logs ADD COLUMN prompt_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE request_logs ADD COLUMN completion_tokens INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # -- Account CRUD --

    def add_account(self, api_key: str, token: str, user_id: str,
                    is_default: bool = False, default_model: str = ""):
        from iflycode_proxy.crypto import encrypt
        conn = self._get_conn()
        if is_default:
            conn.execute("UPDATE accounts SET is_default = 0")
        encrypted_token = encrypt(token)
        conn.execute(
            "INSERT OR REPLACE INTO accounts (api_key, token, user_id, is_default, default_model, updated_at) "
            "VALUES (?, ?, ?, ?, ?, datetime('now'))",
            (api_key, encrypted_token, user_id, 1 if is_default else 0, default_model),
        )
        conn.commit()
        log.info("Account saved: api_key=%s user_id=%s", api_key, user_id)

    def update_account_model(self, api_key: str, default_model: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE accounts SET default_model = ?, updated_at = datetime('now') WHERE api_key = ?",
            (default_model, api_key),
        )
        conn.commit()

    def remove_account(self, api_key: str) -> bool:
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM accounts WHERE api_key = ?", (api_key,))
        conn.commit()
        return cursor.rowcount > 0

    def list_accounts(self) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT api_key, user_id, is_default, default_model, created_at FROM accounts ORDER BY created_at"
        ).fetchall()
        return [
            {
                "api_key": r["api_key"],
                "user_id": r["user_id"],
                "is_default": bool(r["is_default"]),
                "default_model": r["default_model"] or "",
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def get_account(self, api_key: str) -> Optional[Dict[str, Any]]:
        from iflycode_proxy.crypto import decrypt, is_encrypted
        conn = self._get_conn()
        row = conn.execute(
            "SELECT api_key, token, user_id, is_default, default_model FROM accounts WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        if not row:
            return None
        token = row["token"]
        if is_encrypted(token):
            token = decrypt(token)
        return {
            "api_key": row["api_key"],
            "token": token,
            "user_id": row["user_id"],
            "is_default": bool(row["is_default"]),
            "default_model": row["default_model"] or "",
        }

    def get_default_account(self) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT api_key, token, user_id FROM accounts WHERE is_default = 1"
        ).fetchone()
        if not row:
            row = conn.execute(
                "SELECT api_key, token, user_id FROM accounts ORDER BY created_at LIMIT 1"
            ).fetchone()
        if not row:
            return None
        from iflycode_proxy.crypto import decrypt, is_encrypted
        token = row["token"]
        if is_encrypted(token):
            token = decrypt(token)
        return {"api_key": row["api_key"], "token": token, "user_id": row["user_id"]}

    def set_default(self, api_key: str) -> bool:
        conn = self._get_conn()
        row = conn.execute("SELECT 1 FROM accounts WHERE api_key = ?", (api_key,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE accounts SET is_default = 0")
        conn.execute("UPDATE accounts SET is_default = 1, updated_at = datetime('now') WHERE api_key = ?", (api_key,))
        conn.commit()
        return True

    def validate_account(self, api_key: str) -> bool:
        acc = self.get_account(api_key)
        if not acc:
            return False
        from iflycode_proxy.client import Client
        try:
            client = Client(acc["token"], acc.get("user_id", ""))
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
        return {
            "total_requests": total,
            "by_model": [{"model": r["model"], "count": r["cnt"]} for r in by_model],
            "by_account": [{"api_key": r["api_key"], "count": r["cnt"]} for r in by_account],
            "avg_latency_ms": round(avg_latency or 0, 1),
            "accounts_count": conn.execute("SELECT COUNT(*) as cnt FROM accounts").fetchone()["cnt"],
            "prompt_tokens": token_row["pt"],
            "completion_tokens": token_row["ct"],
        }

    def get_account_stats(self, api_key: str) -> Dict[str, Any]:
        conn = self._get_conn()
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ?", (api_key,)
        ).fetchone()["cnt"]
        by_model = conn.execute(
            "SELECT model, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY model ORDER BY cnt DESC",
            (api_key,),
        ).fetchall()
        avg_latency = conn.execute(
            "SELECT AVG(latency_ms) as avg FROM request_logs WHERE api_key = ? AND latency_ms > 0",
            (api_key,),
        ).fetchone()["avg"]
        by_endpoint = conn.execute(
            "SELECT endpoint, COUNT(*) as cnt FROM request_logs WHERE api_key = ? GROUP BY endpoint ORDER BY cnt DESC",
            (api_key,),
        ).fetchall()
        stream_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND stream = 1",
            (api_key,),
        ).fetchone()["cnt"]
        error_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM request_logs WHERE api_key = ? AND status_code >= 400",
            (api_key,),
        ).fetchone()["cnt"]
        token_row = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens),0) as pt, COALESCE(SUM(completion_tokens),0) as ct "
            "FROM request_logs WHERE api_key = ?",
            (api_key,),
        ).fetchone()
        return {
            "api_key": api_key,
            "total_requests": total,
            "by_model": [{"model": r["model"], "count": r["cnt"]} for r in by_model],
            "by_endpoint": [{"endpoint": r["endpoint"], "count": r["cnt"]} for r in by_endpoint],
            "avg_latency_ms": round(avg_latency or 0, 1),
            "stream_count": stream_count,
            "error_count": error_count,
            "prompt_tokens": token_row["pt"],
            "completion_tokens": token_row["ct"],
        }

    def get_account_models(self, api_key: str) -> List[str]:
        acc = self.get_account(api_key)
        if not acc:
            return []
        from iflycode_proxy.client import Client
        try:
            client = Client(acc["token"], acc.get("user_id", ""))
            models_data = client.list_models()
            client.close()
            return [m.get("modelCode", m.get("name", "")) for m in models_data if m.get("modelCode") or m.get("name")]
        except Exception:
            return []

    def get_credential_router(self):
        from iflycode_proxy.credential_router import CredentialRouter
        router = CredentialRouter()
        for acc in self.list_accounts():
            full = self.get_account(acc["api_key"])
            if full:
                router.add_account(
                    full["api_key"], full["token"], full.get("user_id", ""),
                    default=full["is_default"],
                    default_model=full.get("default_model", ""),
                )
        return router
