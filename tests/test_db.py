"""Tests for the Database layer — accounts, settings, request logs, and stats."""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from iflycode_proxy.db import Database, _generate_account_id, _generate_api_key


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db_path(tmp_path):
    return tmp_path / "test_proxy.db"


@pytest.fixture
def db(tmp_db_path):
    """Fresh database instance, auto-closed after test."""
    instance = Database(db_path=tmp_db_path)
    yield instance
    instance.close()


@pytest.fixture
def db_with_account(db):
    """Database with one account pre-inserted."""
    db.add_account(
        account_id="acc-test01",
        api_key="sk-testapikey0001",
        spark_token="spark-token-abc",
        user_id="user1",
        is_default=True,
        default_model="4.0Ultra",
    )
    return db


@pytest.fixture
def db_with_two_accounts(db):
    """Database with two accounts; the first is default."""
    db.add_account(
        account_id="acc-test01",
        api_key="sk-testapikey0001",
        spark_token="spark-token-abc",
        user_id="user1",
        is_default=True,
        default_model="4.0Ultra",
    )
    db.add_account(
        account_id="acc-test02",
        api_key="sk-testapikey0002",
        spark_token="spark-token-xyz",
        user_id="user2",
        is_default=False,
        default_model="3.5",
    )
    return db


# ---------------------------------------------------------------------------
# ID / key generation helpers
# ---------------------------------------------------------------------------


class TestGenerationHelpers:
    def test_account_id_format(self):
        aid = _generate_account_id()
        assert aid.startswith("acc-")
        # hex portion is 8 chars (4 bytes)
        assert len(aid) == 4 + 8

    def test_api_key_format(self):
        key = _generate_api_key()
        assert key.startswith("sk-")
        # hex portion is 32 chars (16 bytes)
        assert len(key) == 3 + 32

    def test_generated_ids_are_unique(self):
        ids = {_generate_account_id() for _ in range(50)}
        assert len(ids) == 50

    def test_generated_keys_are_unique(self):
        keys = {_generate_api_key() for _ in range(50)}
        assert len(keys) == 50


# ---------------------------------------------------------------------------
# Database initialization & schema
# ---------------------------------------------------------------------------


class TestDatabaseInit:
    def test_creates_db_file_on_connect(self, tmp_db_path):
        db = Database(db_path=tmp_db_path)
        db._get_conn()  # trigger lazy init
        assert tmp_db_path.exists()
        db.close()

    def test_creates_parent_directory(self, tmp_path):
        nested = tmp_path / "a" / "b" / "test.db"
        db = Database(db_path=nested)
        db._get_conn()
        assert nested.parent.exists()
        db.close()

    def test_schema_tables_exist(self, db):
        conn = db._get_conn()
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {"accounts", "settings", "request_logs"}.issubset(tables)

    def test_wal_journal_mode(self, db):
        conn = db._get_conn()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"

    def test_close_is_idempotent(self, db):
        db.close()
        db.close()  # should not raise


# ---------------------------------------------------------------------------
# Account CRUD
# ---------------------------------------------------------------------------


class TestAccountCRUD:
    def test_add_and_get_account(self, db):
        db.add_account(
            account_id="acc-001",
            api_key="sk-aaa",
            spark_token="tok1",
            user_id="u1",
        )
        acc = db.get_account("acc-001")
        assert acc is not None
        assert acc["account_id"] == "acc-001"
        assert acc["api_key"] == "sk-aaa"
        assert acc["spark_token"] == "tok1"
        assert acc["user_id"] == "u1"
        assert acc["is_default"] is False

    def test_spark_token_is_encrypted_at_rest(self, db):
        db.add_account(
            account_id="acc-002",
            api_key="sk-bbb",
            spark_token="plaintext-secret",
            user_id="u2",
        )
        conn = db._get_conn()
        row = conn.execute(
            "SELECT spark_token FROM accounts WHERE account_id = 'acc-002'"
        ).fetchone()
        stored = row["spark_token"]
        # Should NOT be plaintext
        assert stored != "plaintext-secret"
        # Should have the encryption prefix
        assert stored.startswith("enc:")

    def test_get_nonexistent_account(self, db):
        assert db.get_account("acc-nope") is None

    def test_list_accounts_empty(self, db):
        assert db.list_accounts() == []

    def test_list_accounts_returns_expected_fields(self, db_with_account):
        accounts = db_with_account.list_accounts()
        assert len(accounts) == 1
        acc = accounts[0]
        # list_accounts does NOT include spark_token
        assert "spark_token" not in acc
        assert acc["account_id"] == "acc-test01"
        assert acc["is_default"] is True

    def test_add_default_clears_previous_default(self, db):
        db.add_account("acc-a", "sk-a", "tok-a", "u1", is_default=True)
        db.add_account("acc-b", "sk-b", "tok-b", "u2", is_default=True)
        accounts = db.list_accounts()
        defaults = [a for a in accounts if a["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["account_id"] == "acc-b"

    def test_remove_account(self, db_with_account):
        removed = db_with_account.remove_account("acc-test01")
        assert removed is True
        assert db_with_account.get_account("acc-test01") is None

    def test_remove_nonexistent_account(self, db):
        assert db.remove_account("acc-nope") is False

    def test_update_account_model(self, db_with_account):
        db_with_account.update_account_model("acc-test01", "3.5")
        acc = db_with_account.get_account("acc-test01")
        assert acc["default_model"] == "3.5"

    def test_update_nonexistent_account_model_no_error(self, db):
        db.update_account_model("acc-nope", "3.5")  # should not raise

    def test_renew_api_key(self, db_with_account):
        new_key = db_with_account.renew_api_key("acc-test01")
        assert new_key is not None
        assert new_key.startswith("sk-")
        assert new_key != "sk-testapikey0001"
        # Verify old key no longer works
        assert db_with_account.get_account_by_api_key("sk-testapikey0001") is None
        # Verify new key works
        assert db_with_account.get_account_by_api_key(new_key) is not None

    def test_renew_api_key_nonexistent(self, db):
        assert db.renew_api_key("acc-nope") is None

    def test_get_account_by_api_key(self, db_with_account):
        acc = db_with_account.get_account_by_api_key("sk-testapikey0001")
        assert acc is not None
        assert acc["account_id"] == "acc-test01"

    def test_get_account_by_api_key_not_found(self, db):
        assert db.get_account_by_api_key("sk-nonexistent") is None

    def test_set_default(self, db_with_two_accounts):
        ok = db_with_two_accounts.set_default("acc-test02")
        assert ok is True
        acc = db_with_two_accounts.get_account("acc-test02")
        assert acc["is_default"] is True
        acc1 = db_with_two_accounts.get_account("acc-test01")
        assert acc1["is_default"] is False

    def test_set_default_nonexistent(self, db):
        assert db.set_default("acc-nope") is False

    def test_get_default_account_explicit(self, db_with_two_accounts):
        default = db_with_two_accounts.get_default_account()
        assert default is not None
        assert default["account_id"] == "acc-test01"

    def test_get_default_account_falls_back_to_oldest(self, db):
        # Neither account is explicitly default
        conn = db._get_conn()
        conn.execute(
            "INSERT INTO accounts (account_id, api_key, spark_token, user_id, is_default) "
            "VALUES ('acc-x', 'sk-x', 'tok-x', 'ux', 0)"
        )
        conn.commit()
        default = db.get_default_account()
        assert default is not None
        assert default["account_id"] == "acc-x"

    def test_get_default_account_empty_db(self, db):
        assert db.get_default_account() is None

    def test_add_account_upsert(self, db):
        db.add_account("acc-1", "sk-1", "tok1", "u1")
        db.add_account("acc-1", "sk-1", "tok1-updated", "u1-updated")
        acc = db.get_account("acc-1")
        assert acc["spark_token"] == "tok1-updated"
        assert acc["user_id"] == "u1-updated"

    def test_validate_account_missing(self, db):
        assert db.validate_account("acc-nope") is False


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class TestSettings:
    def test_set_and_get(self, db):
        db.set_setting("port", "8080")
        assert db.get_setting("port") == "8080"

    def test_get_missing_returns_default(self, db):
        assert db.get_setting("nonexistent") == ""
        assert db.get_setting("nonexistent", "fallback") == "fallback"

    def test_upsert_setting(self, db):
        db.set_setting("port", "8080")
        db.set_setting("port", "9090")
        assert db.get_setting("port") == "9090"

    def test_get_all_settings(self, db):
        db.set_setting("a", "1")
        db.set_setting("b", "2")
        settings = db.get_all_settings()
        assert settings == {"a": "1", "b": "2"}

    def test_get_all_settings_empty(self, db):
        assert db.get_all_settings() == {}


# ---------------------------------------------------------------------------
# Request logs
# ---------------------------------------------------------------------------


class TestRequestLogs:
    def test_log_request(self, db):
        db.log_request(
            api_key="sk-1", model="4.0Ultra", endpoint="/v1/chat",
            stream=True, status_code=200, latency_ms=150,
        )
        logs = db.get_recent_logs()
        assert len(logs) == 1
        log = logs[0]
        assert log["api_key"] == "sk-1"
        assert log["model"] == "4.0Ultra"
        assert log["stream"] == 1
        assert log["status_code"] == 200
        assert log["latency_ms"] == 150

    def test_log_request_with_tokens(self, db):
        db.log_request(
            api_key="sk-1", model="4.0Ultra", endpoint="/v1/chat",
            stream=False, status_code=200, latency_ms=50,
            prompt_tokens=100, completion_tokens=50,
        )
        logs = db.get_recent_logs()
        assert logs[0]["prompt_tokens"] == 100
        assert logs[0]["completion_tokens"] == 50

    def test_recent_logs_respects_limit(self, db):
        for i in range(10):
            db.log_request("sk-1", "m", "/e", False, 200, 10)
        assert len(db.get_recent_logs(limit=5)) == 5

    def test_recent_logs_ordered_by_id_desc(self, db):
        db.log_request("sk-1", "model-a", "/e1", False, 200, 10)
        db.log_request("sk-1", "model-b", "/e2", False, 200, 10)
        logs = db.get_recent_logs()
        assert logs[0]["model"] == "model-b"
        assert logs[1]["model"] == "model-a"

    def test_filtered_logs_by_model(self, db):
        db.log_request("sk-1", "4.0Ultra", "/e", False, 200, 10)
        db.log_request("sk-1", "3.5", "/e", False, 200, 10)
        filtered = db.get_filtered_logs(model="4.0Ultra")
        assert len(filtered) == 1
        assert filtered[0]["model"] == "4.0Ultra"

    def test_filtered_logs_by_api_key(self, db):
        db.log_request("sk-a", "m", "/e", False, 200, 10)
        db.log_request("sk-b", "m", "/e", False, 200, 10)
        filtered = db.get_filtered_logs(api_key="sk-a")
        assert len(filtered) == 1
        assert filtered[0]["api_key"] == "sk-a"

    def test_filtered_logs_by_status_success(self, db):
        db.log_request("sk-1", "m", "/e", False, 200, 10)
        db.log_request("sk-1", "m", "/e", False, 500, 10)
        # status_code=1 means "success" (code < 400)
        filtered = db.get_filtered_logs(status_code=1)
        assert len(filtered) == 1
        assert filtered[0]["status_code"] == 200

    def test_filtered_logs_by_status_error(self, db):
        db.log_request("sk-1", "m", "/e", False, 200, 10)
        db.log_request("sk-1", "m", "/e", False, 500, 10)
        # status_code=2 means "error" (code >= 400)
        filtered = db.get_filtered_logs(status_code=2)
        assert len(filtered) == 1
        assert filtered[0]["status_code"] == 500

    def test_filtered_logs_combined_filters(self, db):
        db.log_request("sk-a", "4.0Ultra", "/e", False, 200, 10)
        db.log_request("sk-a", "3.5", "/e", False, 200, 10)
        db.log_request("sk-b", "4.0Ultra", "/e", False, 200, 10)
        filtered = db.get_filtered_logs(api_key="sk-a", model="4.0Ultra")
        assert len(filtered) == 1

    def test_filtered_logs_no_filters(self, db):
        db.log_request("sk-1", "m", "/e", False, 200, 10)
        db.log_request("sk-2", "m2", "/e2", False, 200, 10)
        assert len(db.get_filtered_logs()) == 2

    def test_cleanup_logs(self, db):
        db.log_request("sk-1", "m", "/e", False, 200, 10)
        # Manually backdate the log entry
        conn = db._get_conn()
        conn.execute(
            "UPDATE request_logs SET created_at = datetime('now', '-40 days')"
        )
        conn.commit()
        deleted = db.cleanup_logs(retention_days=30)
        assert deleted == 1
        assert db.get_recent_logs() == []

    def test_cleanup_logs_preserves_recent(self, db):
        db.log_request("sk-1", "m", "/e", False, 200, 10)
        deleted = db.cleanup_logs(retention_days=30)
        assert deleted == 0
        assert len(db.get_recent_logs()) == 1


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_global_stats_empty(self, db):
        stats = db.get_stats()
        assert stats["total_requests"] == 0
        assert stats["avg_latency_ms"] == 0
        assert stats["accounts_count"] == 0
        assert stats["prompt_tokens"] == 0
        assert stats["completion_tokens"] == 0

    def test_global_stats_with_data(self, db):
        db.add_account("acc-1", "sk-1", "tok", "u1")
        db.log_request("sk-1", "4.0Ultra", "/v1/chat", True, 200, 100, 50, 25)
        db.log_request("sk-1", "4.0Ultra", "/v1/chat", True, 200, 200, 100, 50)
        db.log_request("sk-1", "3.5", "/v1/chat", False, 500, 50, 10, 0)

        stats = db.get_stats()
        assert stats["total_requests"] == 3
        assert stats["accounts_count"] == 1
        assert stats["prompt_tokens"] == 160
        assert stats["completion_tokens"] == 75
        assert len(stats["by_model"]) == 2
        assert len(stats["by_account"]) == 1

    def test_account_stats(self, db_with_account):
        db_with_account.log_request(
            "sk-testapikey0001", "4.0Ultra", "/v1/chat", True, 200, 100, 50, 25
        )
        db_with_account.log_request(
            "sk-testapikey0001", "4.0Ultra", "/v1/chat", True, 200, 200, 100, 50
        )
        db_with_account.log_request(
            "sk-testapikey0001", "3.5", "/v1/completions", False, 500, 50, 10, 0
        )

        stats = db_with_account.get_account_stats("acc-test01")
        assert stats["total_requests"] == 3
        assert stats["stream_count"] == 2
        assert stats["error_count"] == 1
        assert stats["prompt_tokens"] == 160
        assert stats["completion_tokens"] == 75
        assert len(stats["by_model"]) == 2
        assert len(stats["by_endpoint"]) == 2

    def test_account_stats_nonexistent(self, db):
        stats = db.get_account_stats("acc-nope")
        assert stats["total_requests"] == 0

    def test_account_stats_today_success_rate(self, db_with_account):
        db_with_account.log_request(
            "sk-testapikey0001", "m", "/e", False, 200, 10
        )
        db_with_account.log_request(
            "sk-testapikey0001", "m", "/e", False, 200, 10
        )
        db_with_account.log_request(
            "sk-testapikey0001", "m", "/e", False, 500, 10
        )
        stats = db_with_account.get_account_stats("acc-test01")
        assert stats["today_requests"] == 3
        assert stats["today_errors"] == 1
        assert stats["today_success_rate"] == pytest.approx(66.7, abs=0.1)

    def test_account_stats_zero_division(self, db_with_account):
        stats = db_with_account.get_account_stats("acc-test01")
        assert stats["today_success_rate"] == 0.0

    def test_account_hourly_stats(self, db_with_account):
        db_with_account.log_request(
            "sk-testapikey0001", "m", "/e", False, 200, 100, 50, 25
        )
        hourly = db_with_account.get_account_hourly_stats("acc-test01", hours=24)
        assert len(hourly) >= 1
        h = hourly[0]
        assert h["request_count"] == 1
        assert h["prompt_tokens"] == 50
        assert h["completion_tokens"] == 25

    def test_account_recent_logs(self, db_with_account):
        db_with_account.log_request(
            "sk-testapikey0001", "m", "/e", False, 200, 10
        )
        db_with_account.log_request(
            "sk-testapikey0001", "m2", "/e2", False, 200, 10
        )
        logs = db_with_account.get_account_recent_logs("acc-test01", limit=1)
        assert len(logs) == 1
        assert logs[0]["model"] == "m2"  # most recent first


# ---------------------------------------------------------------------------
# Credential router integration
# ---------------------------------------------------------------------------


class TestCredentialRouterIntegration:
    def test_get_credential_router(self, db_with_two_accounts):
        with patch("iflycode_proxy.credential_router.CredentialRouter") as MockRouter:
            mock_router = MagicMock()
            MockRouter.return_value = mock_router
            router = db_with_two_accounts.get_credential_router()
            assert mock_router.add_account.call_count == 2

    def test_get_credential_router_empty_db(self, db):
        with patch("iflycode_proxy.credential_router.CredentialRouter") as MockRouter:
            mock_router = MagicMock()
            MockRouter.return_value = mock_router
            router = db.get_credential_router()
            mock_router.add_account.assert_not_called()


# ---------------------------------------------------------------------------
# Account models (with mocked client)
# ---------------------------------------------------------------------------


class TestAccountModels:
    def test_get_account_models_success(self, db_with_account):
        fake_models = [
            {"modelCode": "4.0Ultra", "modelName": "Ultra", "modelId": "1", "checked": True},
            {"modelCode": "3.5", "modelName": "Standard", "modelId": "2"},
        ]
        with patch("iflycode_proxy.client.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_models.return_value = fake_models
            MockClient.return_value = mock_instance
            models = db_with_account.get_account_models("acc-test01")
            assert len(models) == 2
            assert models[0]["modelCode"] == "4.0Ultra"
            assert models[0]["checked"] is True
            assert models[1]["checked"] is False  # default

    def test_get_account_models_nonexistent(self, db):
        assert db.get_account_models("acc-nope") == []

    def test_get_account_models_client_exception(self, db_with_account):
        with patch("iflycode_proxy.client.Client") as MockClient:
            MockClient.return_value.list_models.side_effect = Exception("network error")
            assert db_with_account.get_account_models("acc-test01") == []


# ---------------------------------------------------------------------------
# Validate account (with mocked client)
# ---------------------------------------------------------------------------


class TestValidateAccount:
    def test_validate_account_success(self, db_with_account):
        with patch("iflycode_proxy.client.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.validate.return_value = True
            MockClient.return_value = mock_instance
            assert db_with_account.validate_account("acc-test01") is True

    def test_validate_account_invalid(self, db_with_account):
        with patch("iflycode_proxy.client.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.validate.return_value = False
            MockClient.return_value = mock_instance
            assert db_with_account.validate_account("acc-test01") is False

    def test_validate_account_exception(self, db_with_account):
        with patch("iflycode_proxy.client.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.validate.side_effect = Exception("boom")
            MockClient.return_value = mock_instance
            assert db_with_account.validate_account("acc-test01") is False


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    def test_migration_from_old_schema(self, tmp_db_path):
        """Simulate old schema (api_key as PK) and verify migration works."""
        # Create old-style DB
        conn = sqlite3.connect(str(tmp_db_path))
        conn.execute("""
            CREATE TABLE accounts (
                api_key TEXT PRIMARY KEY,
                token TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT '',
                is_default INTEGER NOT NULL DEFAULT 0,
                default_model TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute(
            "INSERT INTO accounts (api_key, token, user_id, is_default, default_model) "
            "VALUES ('sk-aaaaaaa01', 'enc:oldtoken', 'u1', 1, '4.0Ultra')"
        )
        conn.execute(
            "INSERT INTO accounts (api_key, token, user_id, is_default, default_model) "
            "VALUES ('sk-bbbbbbb02', 'enc:oldtoken2', 'u2', 0, '3.5')"
        )
        conn.commit()
        conn.close()

        # Open with Database — triggers migration
        with patch("iflycode_proxy.crypto.encrypt", side_effect=lambda x: f"enc:{x}"):
            db = Database(db_path=tmp_db_path)
            accounts = db.list_accounts()
            db.close()

        assert len(accounts) == 2
        # Old api_keys should be replaced with new ones
        for a in accounts:
            assert a["api_key"].startswith("sk-")
            assert a["api_key"] not in ("sk-aaaaaaa01", "sk-bbbbbbb02")
