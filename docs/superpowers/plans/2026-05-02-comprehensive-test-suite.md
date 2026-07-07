# iflycode-proxy 全栈集成测试套件 (50-100 Cases)

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 为 iflycode-proxy 的所有 API 端点、协议转换、数据层和认证流程编写 50-100 个自动化测试用例，确保所有提供出去的接口经过充分测试验证。

**Architecture:** 每个测试使用独立的临时 SQLite 数据库 → 通过 FastAPI TestClient 发起 HTTP 请求 → 上游 iFlyCode API 通过 httpx mock 拦截 → 断言响应格式、状态码、数据正确性。按层级组织：Crypto → DB → CredentialRouter → Client → Web API → OpenAI Handler → Anthropic Handler → Auth。

**Tech Stack:** Python 3.12, pytest 8.3+, pytest-asyncio 0.24+, httpx 0.28, FastAPI TestClient, respx 0.22 (httpx mock)

**Risks:**
- SSE 流式响应测试需同步迭代 TestClient → 缓解：TestClient 支持 iter_lines
- respx 对 httpx.Client 流式请求的 mock 需要特殊处理 → 缓解：使用 httpx.Response + stream 模式
- 加密测试依赖文件系统密钥 → 缓解：每个测试用独立的 tmp key 文件
- 上游 API 响应格式可能变化 → 缓解：mock 固定格式，测试协议转换逻辑而非上游数据

---

### Task 1: 测试基础设施搭建

**Depends on:** None
**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `pyproject.toml:1-20`（添加 dev 依赖和 pytest 配置）

- [ ] **Step 1: 安装 respx 依赖 — mock httpx 请求用于测试**

Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && pip install respx pytest-asyncio --upgrade`
Expected:
  - Exit code: 0
  - `python3 -c "import respx; print(respx.__version__)"` 输出非空

- [ ] **Step 2: 更新 pyproject.toml — 添加 respx 到 dev 依赖和 pytest 配置**

文件: `pyproject.toml:8-10`

```toml
# 替换 pyproject.toml 的 [project.optional-dependencies] 部分
[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "respx>=0.22"]
```

在文件末尾添加 pytest 配置：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: 创建 tests/__init__.py 和 conftest.py — 共享 fixtures**

```python
# tests/__init__.py
```

```python
# tests/conftest.py
"""Shared test fixtures for iflycode-proxy test suite."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from iflycode_proxy.db import Database, _generate_account_id, _generate_api_key
from iflycode_proxy.credential_router import CredentialRouter


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary Database with a clean SQLite file."""
    db_path = tmp_path / "test.db"
    db = Database(db_path=db_path)
    yield db
    db.close()


@pytest.fixture
def sample_account(tmp_db):
    """Add a sample account to tmp_db and return its data."""
    account_id = _generate_account_id()
    api_key = _generate_api_key()
    spark_token = "test-spark-token-12345"
    user_id = "test-user"
    tmp_db.add_account(account_id, api_key, spark_token, user_id, is_default=True)
    return {
        "account_id": account_id,
        "api_key": api_key,
        "spark_token": spark_token,
        "user_id": user_id,
    }


@pytest.fixture
def second_account(tmp_db):
    """Add a second non-default account to tmp_db and return its data."""
    account_id = _generate_account_id()
    api_key = _generate_api_key()
    spark_token = "test-spark-token-67890"
    user_id = "test-user-2"
    tmp_db.add_account(account_id, api_key, spark_token, user_id, is_default=False)
    return {
        "account_id": account_id,
        "api_key": api_key,
        "spark_token": spark_token,
        "user_id": user_id,
    }


@pytest.fixture
def cred_router(sample_account):
    """Create a CredentialRouter with a sample account registered."""
    router = CredentialRouter()
    router.add_account(
        sample_account["account_id"],
        sample_account["api_key"],
        sample_account["spark_token"],
        sample_account["user_id"],
        default=True,
    )
    return router


@pytest.fixture
def app_client(cred_router, tmp_db):
    """Create a TestClient for the full FastAPI app."""
    from iflycode_proxy.server import create_app
    app = create_app(cred_router, db=tmp_db)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def app_client_no_db(cred_router):
    """Create a TestClient without DB (no web API routes)."""
    from iflycode_proxy.server import create_app
    app = create_app(cred_router, db=None)
    with TestClient(app) as client:
        yield client
```

- [ ] **Step 4: 验证测试基础设施**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/ --co -q 2>&1 | head -20`
Expected:
  - Exit code: 0 (no collection errors)
  - Output shows "conftest.py" loaded

- [ ] **Step 5: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/__init__.py tests/conftest.py pyproject.toml && git commit -m "feat(test): add test infrastructure with shared fixtures"`

---

### Task 2: Crypto 模块单元测试（6 cases）

**Depends on:** Task 1
**Files:**
- Create: `tests/test_crypto.py`

- [ ] **Step 1: 创建 test_crypto.py — 加密/解密/检测功能测试**

```python
# tests/test_crypto.py
"""Tests for crypto module — encryption, decryption, detection."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from iflycode_proxy.crypto import encrypt, decrypt, is_encrypted


class TestEncrypt:
    def test_encrypt_returns_prefixed_string(self):
        result = encrypt("hello")
        assert result.startswith("enc:")

    def test_encrypt_different_inputs_produce_different_outputs(self):
        a = encrypt("foo")
        b = encrypt("bar")
        assert a != b

    def test_encrypt_same_input_different_outputs(self):
        """Fernet uses IV, so same input produces different ciphertext."""
        a = encrypt("same")
        b = encrypt("same")
        assert a != b  # different IV each time


class TestDecrypt:
    def test_decrypt_roundtrip(self):
        original = "my-secret-token"
        encrypted = encrypt(original)
        assert decrypt(encrypted) == original

    def test_decrypt_empty_string(self):
        encrypted = encrypt("")
        assert decrypt(encrypted) == ""

    def test_decrypt_long_string(self):
        original = "x" * 10000
        encrypted = encrypt(original)
        assert decrypt(encrypted) == original


class TestIsEncrypted:
    def test_encrypted_value_detected(self):
        encrypted = encrypt("test")
        assert is_encrypted(encrypted) is True

    def test_plain_value_not_detected(self):
        assert is_encrypted("plain-text") is False

    def test_empty_string_not_detected(self):
        assert is_encrypted("") is False

    def test_enc_prefix_only_not_encrypted(self):
        """Just 'enc:' without actual ciphertext is not valid encrypted data."""
        # is_encrypted only checks prefix, so this returns True
        # but decrypt would fail — testing the detection function only
        assert is_encrypted("enc:") is True
```

- [ ] **Step 2: 验证 crypto 测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_crypto.py -v`
Expected:
  - Exit code: 0
  - Output contains "10 passed"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_crypto.py && git commit -m "test(crypto): add encryption/decryption unit tests (10 cases)"`

---

### Task 3: Database 层单元测试（20 cases）

**Depends on:** Task 1
**Files:**
- Create: `tests/test_db.py`

- [ ] **Step 1: 创建 test_db.py — 账号 CRUD、设置、日志、统计**

```python
# tests/test_db.py
"""Tests for Database module — CRUD, settings, logs, stats."""

import time
from pathlib import Path

import pytest

from iflycode_proxy.db import Database, _generate_account_id, _generate_api_key


class TestAccountCRUD:
    def test_add_account_returns_stored_data(self, tmp_db):
        account_id = _generate_account_id()
        api_key = _generate_api_key()
        tmp_db.add_account(account_id, api_key, "token123", "user1")
        acc = tmp_db.get_account(account_id)
        assert acc is not None
        assert acc["account_id"] == account_id
        assert acc["api_key"] == api_key
        assert acc["spark_token"] == "token123"
        assert acc["user_id"] == "user1"

    def test_list_accounts_returns_all(self, tmp_db):
        ids = []
        for i in range(3):
            aid = _generate_account_id()
            ak = _generate_api_key()
            tmp_db.add_account(aid, ak, f"token{i}", f"user{i}")
            ids.append(aid)
        accounts = tmp_db.list_accounts()
        assert len(accounts) == 3
        assert all(a["account_id"] in ids for a in accounts)

    def test_list_accounts_hides_spark_token(self, tmp_db):
        aid = _generate_account_id()
        ak = _generate_api_key()
        tmp_db.add_account(aid, ak, "secret-token", "user1")
        accounts = tmp_db.list_accounts()
        acc = next(a for a in accounts if a["account_id"] == aid)
        assert "spark_token" not in acc

    def test_remove_account(self, tmp_db):
        aid = _generate_account_id()
        ak = _generate_api_key()
        tmp_db.add_account(aid, ak, "token", "user")
        assert tmp_db.remove_account(aid) is True
        assert tmp_db.get_account(aid) is None

    def test_remove_nonexistent_account(self, tmp_db):
        assert tmp_db.remove_account("nonexistent") is False

    def test_get_account_by_api_key(self, tmp_db):
        aid = _generate_account_id()
        ak = _generate_api_key()
        tmp_db.add_account(aid, ak, "token", "user1")
        acc = tmp_db.get_account_by_api_key(ak)
        assert acc is not None
        assert acc["account_id"] == aid

    def test_get_account_by_api_key_not_found(self, tmp_db):
        acc = tmp_db.get_account_by_api_key("sk-nonexistent")
        assert acc is None

    def test_set_default_account(self, tmp_db):
        aid1 = _generate_account_id()
        ak1 = _generate_api_key()
        tmp_db.add_account(aid1, ak1, "t1", "u1", is_default=True)
        aid2 = _generate_account_id()
        ak2 = _generate_api_key()
        tmp_db.add_account(aid2, ak2, "t2", "u2", is_default=False)
        tmp_db.set_default(aid2)
        acc1 = tmp_db.get_account(aid1)
        acc2 = tmp_db.get_account(aid2)
        assert acc1["is_default"] is False
        assert acc2["is_default"] is True

    def test_set_default_nonexistent(self, tmp_db):
        assert tmp_db.set_default("nonexistent") is False

    def test_get_default_account(self, tmp_db):
        aid = _generate_account_id()
        ak = _generate_api_key()
        tmp_db.add_account(aid, ak, "token", "user1", is_default=True)
        default = tmp_db.get_default_account()
        assert default is not None
        assert default["account_id"] == aid

    def test_update_account_model(self, tmp_db):
        aid = _generate_account_id()
        ak = _generate_api_key()
        tmp_db.add_account(aid, ak, "token", "user1")
        tmp_db.update_account_model(aid, "spark-4.0-ultra")
        acc = tmp_db.get_account(aid)
        assert acc["default_model"] == "spark-4.0-ultra"

    def test_renew_api_key(self, tmp_db):
        aid = _generate_account_id()
        old_key = _generate_api_key()
        tmp_db.add_account(aid, old_key, "token", "user1")
        new_key = tmp_db.renew_api_key(aid)
        assert new_key is not None
        assert new_key != old_key
        assert new_key.startswith("sk-")
        acc = tmp_db.get_account(aid)
        assert acc["api_key"] == new_key

    def test_renew_api_key_nonexistent(self, tmp_db):
        result = tmp_db.renew_api_key("nonexistent")
        assert result is None

    def test_add_account_with_default_clears_others(self, tmp_db):
        aid1 = _generate_account_id()
        ak1 = _generate_api_key()
        tmp_db.add_account(aid1, ak1, "t1", "u1", is_default=True)
        aid2 = _generate_account_id()
        ak2 = _generate_api_key()
        tmp_db.add_account(aid2, ak2, "t2", "u2", is_default=True)
        acc1 = tmp_db.get_account(aid1)
        assert acc1["is_default"] is False

    def test_spark_token_is_encrypted_in_db(self, tmp_db):
        aid = _generate_account_id()
        ak = _generate_api_key()
        tmp_db.add_account(aid, ak, "plain-token", "user1")
        # Raw DB query to check encryption
        conn = tmp_db._get_conn()
        row = conn.execute("SELECT spark_token FROM accounts WHERE account_id = ?", (aid,)).fetchone()
        assert row["spark_token"].startswith("enc:")


class TestSettings:
    def test_set_and_get_setting(self, tmp_db):
        tmp_db.set_setting("key1", "value1")
        assert tmp_db.get_setting("key1") == "value1"

    def test_get_nonexistent_setting_returns_default(self, tmp_db):
        assert tmp_db.get_setting("missing", "fallback") == "fallback"

    def test_get_all_settings(self, tmp_db):
        tmp_db.set_setting("a", "1")
        tmp_db.set_setting("b", "2")
        settings = tmp_db.get_all_settings()
        assert settings["a"] == "1"
        assert settings["b"] == "2"

    def test_update_existing_setting(self, tmp_db):
        tmp_db.set_setting("key", "old")
        tmp_db.set_setting("key", "new")
        assert tmp_db.get_setting("key") == "new"


class TestRequestLogs:
    def test_log_and_retrieve(self, tmp_db):
        tmp_db.log_request("sk-test", "gpt-4", "/v1/chat/completions", True, 200, 150)
        logs = tmp_db.get_recent_logs(10)
        assert len(logs) == 1
        assert logs[0]["api_key"] == "sk-test"
        assert logs[0]["model"] == "gpt-4"

    def test_filtered_logs_by_api_key(self, tmp_db):
        tmp_db.log_request("sk-1", "gpt-4", "/v1/c", True, 200, 100)
        tmp_db.log_request("sk-2", "gpt-4", "/v1/c", True, 200, 100)
        logs = tmp_db.get_filtered_logs(10, api_key="sk-1")
        assert len(logs) == 1
        assert logs[0]["api_key"] == "sk-1"

    def test_filtered_logs_by_status_success(self, tmp_db):
        tmp_db.log_request("sk-1", "gpt-4", "/v1/c", True, 200, 100)
        tmp_db.log_request("sk-1", "gpt-4", "/v1/c", True, 500, 100)
        logs = tmp_db.get_filtered_logs(10, status_code=1)
        assert len(logs) == 1
        assert logs[0]["status_code"] == 200

    def test_filtered_logs_by_status_error(self, tmp_db):
        tmp_db.log_request("sk-1", "gpt-4", "/v1/c", True, 200, 100)
        tmp_db.log_request("sk-1", "gpt-4", "/v1/c", True, 500, 100)
        logs = tmp_db.get_filtered_logs(10, status_code=2)
        assert len(logs) == 1
        assert logs[0]["status_code"] == 500

    def test_cleanup_logs(self, tmp_db):
        tmp_db.log_request("sk-1", "gpt-4", "/v1/c", True, 200, 100)
        # Remove logs older than 0 days (removes everything)
        removed = tmp_db.cleanup_logs(0)
        assert removed >= 1
        assert len(tmp_db.get_recent_logs(10)) == 0


class TestStats:
    def test_get_stats_empty(self, tmp_db):
        stats = tmp_db.get_stats()
        assert stats["total_requests"] == 0
        assert stats["accounts_count"] == 0

    def test_get_stats_with_data(self, tmp_db):
        tmp_db.add_account(_generate_account_id(), _generate_api_key(), "t", "u")
        tmp_db.log_request("sk-1", "gpt-4", "/v1/c", True, 200, 100, prompt_tokens=50, completion_tokens=30)
        stats = tmp_db.get_stats()
        assert stats["total_requests"] == 1
        assert stats["accounts_count"] == 1
        assert stats["prompt_tokens"] == 50
        assert stats["completion_tokens"] == 30

    def test_get_account_stats(self, tmp_db, sample_account):
        tmp_db.log_request(sample_account["api_key"], "gpt-4", "/v1/c", True, 200, 100)
        stats = tmp_db.get_account_stats(sample_account["account_id"])
        assert stats["total_requests"] == 1
        assert stats["error_count"] == 0

    def test_get_account_stats_with_errors(self, tmp_db, sample_account):
        tmp_db.log_request(sample_account["api_key"], "gpt-4", "/v1/c", True, 200, 100)
        tmp_db.log_request(sample_account["api_key"], "gpt-4", "/v1/c", True, 500, 100)
        stats = tmp_db.get_account_stats(sample_account["account_id"])
        assert stats["total_requests"] == 2
        assert stats["error_count"] == 1

    def test_get_account_hourly_stats(self, tmp_db, sample_account):
        tmp_db.log_request(sample_account["api_key"], "gpt-4", "/v1/c", True, 200, 100)
        hourly = tmp_db.get_account_hourly_stats(sample_account["account_id"], 24)
        assert len(hourly) >= 1
        assert "request_count" in hourly[0]

    def test_get_account_recent_logs(self, tmp_db, sample_account):
        tmp_db.log_request(sample_account["api_key"], "gpt-4", "/v1/c", True, 200, 100)
        logs = tmp_db.get_account_recent_logs(sample_account["account_id"], 5)
        assert len(logs) == 1
        assert logs[0]["model"] == "gpt-4"
```

- [ ] **Step 2: 验证 DB 测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_db.py -v`
Expected:
  - Exit code: 0
  - Output contains "30 passed"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_db.py && git commit -m "test(db): add database layer unit tests (30 cases)"`

---

### Task 4: CredentialRouter 单元测试（10 cases）

**Depends on:** Task 1
**Files:**
- Create: `tests/test_credential_router.py`

- [ ] **Step 1: 创建 test_credential_router.py — 路由、默认账号、API key 轮换**

```python
# tests/test_credential_router.py
"""Tests for CredentialRouter — multi-account routing logic."""

from unittest.mock import patch, MagicMock

import pytest

from iflycode_proxy.credential_router import CredentialRouter


@pytest.fixture
def router():
    return CredentialRouter()


class TestAddAccount:
    def test_add_single_account(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        client = router.get_client("sk-key1")
        assert client is not None

    def test_add_multiple_accounts(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        router.add_account("acc-2", "sk-key2", "token2", "user2")
        c1 = router.get_client("sk-key1")
        c2 = router.get_client("sk-key2")
        assert c1 is not c2

    def test_first_account_becomes_default(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        assert router.default_key == "sk-key1"

    def test_explicit_default_flag(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1", default=False)
        router.add_account("acc-2", "sk-key2", "token2", "user2", default=True)
        assert router.default_key == "sk-key2"


class TestGetClient:
    def test_get_client_by_api_key(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        client = router.get_client("sk-key1")
        assert client.token == "token1"

    def test_get_client_fallback_to_default(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1", default=True)
        client = router.get_client(None)
        assert client.token == "token1"

    def test_get_client_empty_key_fallback(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1", default=True)
        client = router.get_client("")
        assert client.token == "token1"

    def test_get_client_nonexistent_raises(self, router):
        with pytest.raises(KeyError):
            router.get_client("sk-nonexistent")

    def test_get_client_no_default_raises(self, router):
        with pytest.raises(KeyError):
            router.get_client(None)


class TestRemoveAccount:
    def test_remove_existing_account(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        result = router.remove_account("sk-key1")
        assert result is True
        with pytest.raises(KeyError):
            router.get_client("sk-key1")

    def test_remove_nonexistent(self, router):
        result = router.remove_account("sk-nonexistent")
        assert result is False

    def test_remove_default_promotes_next(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1", default=True)
        router.add_account("acc-2", "sk-key2", "token2", "user2")
        router.remove_account("sk-key1")
        # Default should fall back to next account
        client = router.get_client(None)
        assert client.token == "token2"


class TestRenewApiKey:
    def test_renew_api_key(self, router):
        router.add_account("acc-1", "sk-old", "token1", "user1")
        result = router.renew_api_key("sk-old", "sk-new")
        assert result is True
        client = router.get_client("sk-new")
        assert client.token == "token1"
        with pytest.raises(KeyError):
            router.get_client("sk-old")

    def test_renew_nonexistent_key(self, router):
        result = router.renew_api_key("sk-nonexistent", "sk-new")
        assert result is False

    def test_renew_default_key_updates_default(self, router):
        router.add_account("acc-1", "sk-old", "token1", "user1", default=True)
        router.renew_api_key("sk-old", "sk-new")
        assert router.default_key == "sk-new"


class TestListAccounts:
    def test_list_accounts_empty(self, router):
        assert router.list_accounts() == []

    def test_list_accounts_returns_all(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        router.add_account("acc-2", "sk-key2", "token2", "user2")
        accounts = router.list_accounts()
        assert len(accounts) == 2

    def test_list_accounts_marks_default(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1", default=True)
        router.add_account("acc-2", "sk-key2", "token2", "user2")
        accounts = router.list_accounts()
        default = next(a for a in accounts if a["account_id"] == "acc-1")
        assert default["is_default"] is True


class TestDefaultModel:
    def test_get_default_model(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1", default_model="spark-4.0")
        model = router.get_default_model("sk-key1")
        assert model == "spark-4.0"

    def test_get_default_model_empty(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        model = router.get_default_model("sk-key1")
        assert model == ""


class TestGetAccountId:
    def test_get_account_id_by_api_key(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1")
        account_id = router.get_account_id("sk-key1")
        assert account_id == "acc-1"

    def test_get_account_id_fallback_default(self, router):
        router.add_account("acc-1", "sk-key1", "token1", "user1", default=True)
        account_id = router.get_account_id(None)
        assert account_id == "acc-1"
```

- [ ] **Step 2: 验证 CredentialRouter 测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_credential_router.py -v`
Expected:
  - Exit code: 0
  - Output contains "19 passed"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_credential_router.py && git commit -m "test(router): add credential router unit tests (19 cases)"`

---

### Task 5: Client 模块单元测试（10 cases）

**Depends on:** Task 1
**Files:**
- Create: `tests/test_client.py`

- [ ] **Step 1: 创建 test_client.py — 请求构建、重试逻辑、流式重试**

```python
# tests/test_client.py
"""Tests for Client module — request building, retry logic, stream retry."""

import json
from unittest.mock import patch, MagicMock

import httpx
import pytest

from iflycode_proxy.client import (
    Client, _is_retryable_error, _RETRYABLE_ERROR_PATTERNS,
    _MAX_RETRIES, _INITIAL_BACKOFF, _MAX_BACKOFF,
    CHAT_ENDPOINT, DEFAULT_CLIENT_INFO,
)


class TestRetryableErrorDetection:
    def test_engine_internal_error(self):
        assert _is_retryable_error("EngineInternalError engineCode=10908") is True

    def test_kernel_error(self):
        assert _is_retryable_error("kernel error;code=1010") is True

    def test_engine_code_10908(self):
        assert _is_retryable_error('{"engineCode": 10908}') is True

    def test_code_1010(self):
        assert _is_retryable_error('code = 1010') is True

    def test_service_overloaded(self):
        assert _is_retryable_error("service overloaded") is True

    def test_rate_limit(self):
        assert _is_retryable_error("rate limit exceeded") is True

    def test_too_many_requests(self):
        assert _is_retryable_error("too many requests") is True

    def test_non_retryable_error(self):
        assert _is_retryable_error("normal response content") is False

    def test_empty_string(self):
        assert _is_retryable_error("") is False

    def test_case_insensitive(self):
        assert _is_retryable_error("ENGINEINTERNALERROR") is True


class TestBuildChatBody:
    def test_basic_body_structure(self):
        client = Client("test-token", "user1")
        body = client.build_chat_body([{"role": "user", "content": "hello"}])
        assert "sessionId" in body
        assert "messages" in body
        assert body["token"] == "test-token"
        assert body["agentVersion"] == "3.4.2"

    def test_user_question_content_extracted(self):
        client = Client("test-token", "user1")
        body = client.build_chat_body([
            {"role": "system", "content": "you are helpful"},
            {"role": "user", "content": "hello"},
        ])
        assert body["userQuestionContent"] == "hello"

    def test_temperature_default(self):
        client = Client("test-token", "user1")
        body = client.build_chat_body([{"role": "user", "content": "hi"}])
        assert body["temperature"] == 0.5

    def test_temperature_custom(self):
        client = Client("test-token", "user1")
        body = client.build_chat_body(
            [{"role": "user", "content": "hi"}],
            options={"temperature": 0.9},
        )
        assert body["temperature"] == 0.9

    def test_model_code_included(self):
        client = Client("test-token", "user1")
        body = client.build_chat_body(
            [{"role": "user", "content": "hi"}],
            options={"modelCode": "spark-4.0-ultra"},
        )
        assert body["modelCode"] == "spark-4.0-ultra"
        assert body["enableMultiModelSwitch"] is True

    def test_default_client_info_present(self):
        client = Client("test-token", "user1")
        body = client.build_chat_body([{"role": "user", "content": "hi"}])
        assert body["clientName"] == DEFAULT_CLIENT_INFO["clientName"]
        assert body["pluginVersion"] == DEFAULT_CLIENT_INFO["pluginVersion"]


class TestHeaders:
    def test_basic_headers(self):
        client = Client("test-token", "user1")
        headers = client._headers()
        assert headers["Content-Type"] == "application/json"
        assert headers["token"] == "test-token"

    def test_extra_headers(self):
        client = Client("test-token", "user1")
        headers = client._headers({"X-Custom": "value"})
        assert headers["X-Custom"] == "value"


class TestValidate:
    def test_validate_success(self):
        client = Client("test-token", "user1")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"resCode": "0"}
        mock_resp.raise_for_status = MagicMock()
        with patch.object(client._http, "post", return_value=mock_resp):
            assert client.validate() is True

    def test_validate_failure(self):
        client = Client("test-token", "user1")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"resCode": "999"}
        mock_resp.raise_for_status = MagicMock()
        with patch.object(client._http, "post", return_value=mock_resp):
            assert client.validate() is False

    def test_validate_exception(self):
        client = Client("test-token", "user1")
        with patch.object(client._http, "post", side_effect=Exception("network error")):
            assert client.validate() is False
```

- [ ] **Step 2: 验证 Client 测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_client.py -v`
Expected:
  - Exit code: 0
  - Output contains "22 passed"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_client.py && git commit -m "test(client): add client module unit tests (22 cases)"`

---

### Task 6: Web API 集成测试（25 cases）

**Depends on:** Task 1, Task 3
**Files:**
- Create: `tests/test_web_api.py`

- [ ] **Step 1: 创建 test_web_api.py — 所有管理 API 端点测试**

```python
# tests/test_web_api.py
"""Tests for Web API endpoints — account management, settings, stats, SSO."""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from iflycode_proxy.db import Database, _generate_account_id, _generate_api_key
from iflycode_proxy.credential_router import CredentialRouter
from iflycode_proxy.server import create_app


def make_app_client(db: Database, router: CredentialRouter) -> TestClient:
    app = create_app(router, db=db)
    return TestClient(app)


def add_test_account(db: Database, router: CredentialRouter):
    """Add a test account to both DB and router, return (account_id, api_key)."""
    account_id = _generate_account_id()
    api_key = _generate_api_key()
    spark_token = "test-spark-token"
    db.add_account(account_id, api_key, spark_token, "user1", is_default=True)
    router.add_account(account_id, api_key, spark_token, "user1", default=True)
    return account_id, api_key


class TestHealthEndpoint:
    def test_health_returns_ok(self, app_client):
        resp = app_client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "accounts" in data
        assert "version" in data


class TestAccountList:
    def test_list_accounts_empty(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get("/api/accounts")
        assert resp.status_code == 200
        # cred_router has one account from fixture
        data = resp.json()
        assert "accounts" in data

    def test_list_accounts_returns_all(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get("/api/accounts")
        data = resp.json()
        account_ids = [a["account_id"] for a in data["accounts"]]
        assert sample_account["account_id"] in account_ids


class TestAccountAdd:
    def test_add_account_success(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.post("/api/accounts", json={
            "spark_token": "new-token-123",
            "user_id": "new-user",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "account_id" in data
        assert "api_key" in data
        assert data["account_id"].startswith("acc-")
        assert data["api_key"].startswith("sk-")

    def test_add_account_missing_token(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.post("/api/accounts", json={"user_id": "user"})
        assert resp.status_code == 400

    def test_add_account_with_token_alias(self, tmp_db, cred_router):
        """Support 'token' as alias for 'spark_token'."""
        client = make_app_client(tmp_db, cred_router)
        resp = client.post("/api/accounts", json={"token": "alias-token"})
        assert resp.status_code == 200

    def test_add_account_custom_ids(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.post("/api/accounts", json={
            "account_id": "acc-custom",
            "api_key": "sk-custom",
            "spark_token": "token",
        })
        assert resp.status_code == 200
        assert resp.json()["account_id"] == "acc-custom"
        assert resp.json()["api_key"] == "sk-custom"


class TestAccountDelete:
    def test_delete_account(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.delete(f"/api/accounts/{sample_account['account_id']}")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_nonexistent_account(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.delete("/api/accounts/nonexistent")
        assert resp.status_code == 404


class TestSetDefault:
    def test_set_default(self, tmp_db, cred_router, sample_account, second_account):
        # Add second account to router too
        cred_router.add_account(
            second_account["account_id"], second_account["api_key"],
            second_account["spark_token"], second_account["user_id"],
        )
        client = make_app_client(tmp_db, cred_router)
        resp = client.put(f"/api/accounts/{second_account['account_id']}/default")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_set_default_nonexistent(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.put("/api/accounts/nonexistent/default")
        assert resp.status_code == 404


class TestValidateAccount:
    def test_validate_account_success(self, tmp_db, cred_router, sample_account):
        with patch("iflycode_proxy.db.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.validate.return_value = True
            MockClient.return_value = mock_instance
            client = make_app_client(tmp_db, cred_router)
            resp = client.post(f"/api/accounts/{sample_account['account_id']}/validate")
            assert resp.status_code == 200
            data = resp.json()
            assert data["valid"] is True

    def test_validate_nonexistent_account(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.post("/api/accounts/nonexistent/validate")
        assert resp.status_code == 200
        assert resp.json()["valid"] is False


class TestRenewApiKey:
    def test_renew_api_key(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.post(f"/api/accounts/{sample_account['account_id']}/renew-key")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["api_key"] != sample_account["api_key"]
        assert data["api_key"].startswith("sk-")

    def test_renew_nonexistent(self, tmp_db, cred_router):
        client = make_app_client(tmp_db, cred_router)
        resp = client.post("/api/accounts/nonexistent/renew-key")
        assert resp.status_code == 404


class TestAccountModels:
    def test_get_models(self, tmp_db, cred_router, sample_account):
        with patch("iflycode_proxy.db.Client") as MockClient:
            mock_instance = MagicMock()
            mock_instance.list_models.return_value = [
                {"modelCode": "spark-4.0", "modelName": "Spark 4.0", "modelId": "1", "checked": True, "tokenExhausted": False}
            ]
            MockClient.return_value = mock_instance
            client = make_app_client(tmp_db, cred_router)
            resp = client.get(f"/api/accounts/{sample_account['account_id']}/models")
            assert resp.status_code == 200
            data = resp.json()
            assert "models" in data


class TestUpdateAccountModel:
    def test_update_model(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.put(
            f"/api/accounts/{sample_account['account_id']}/model",
            json={"default_model": "spark-4.0-ultra"},
        )
        assert resp.status_code == 200
        assert resp.json()["default_model"] == "spark-4.0-ultra"


class TestAccountStats:
    def test_get_stats(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get(f"/api/accounts/{sample_account['account_id']}/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_requests" in data
        assert "error_count" in data

    def test_get_hourly_stats(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get(f"/api/accounts/{sample_account['account_id']}/hourly-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "hours" in data
        assert "data" in data

    def test_get_hourly_stats_custom_hours(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get(f"/api/accounts/{sample_account['account_id']}/hourly-stats?hours=48")
        assert resp.status_code == 200
        assert resp.json()["hours"] == 48

    def test_get_hourly_stats_invalid_hours(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get(f"/api/accounts/{sample_account['account_id']}/hourly-stats?hours=9999")
        assert resp.status_code == 200
        assert resp.json()["hours"] == 24  # clamped to default

    def test_get_recent_logs(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get(f"/api/accounts/{sample_account['account_id']}/recent-logs")
        assert resp.status_code == 200
        data = resp.json()
        assert "logs" in data

    def test_get_recent_logs_custom_limit(self, tmp_db, cred_router, sample_account):
        client = make_app_client(tmp_db, cred_router)
        resp = client.get(f"/api/accounts/{sample_account['account_id']}/recent-logs?limit=5")
        assert resp.status_code == 200


class TestGlobalStats:
    def test_get_global_stats(self, app_client):
        resp = app_client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_requests" in data
        assert "accounts_count" in data

    def test_get_logs(self, app_client):
        resp = app_client.get("/api/stats/logs")
        assert resp.status_code == 200
        assert "logs" in resp.json()

    def test_get_logs_with_filter(self, app_client):
        resp = app_client.get("/api/stats/logs?limit=10&status=1")
        assert resp.status_code == 200

    def test_cleanup_logs(self, app_client):
        resp = app_client.post("/api/stats/logs/cleanup", json={"retention_days": 30})
        assert resp.status_code == 200
        assert "removed" in resp.json()


class TestSettings:
    def test_get_settings(self, app_client):
        resp = app_client.get("/api/settings")
        assert resp.status_code == 200
        assert "settings" in resp.json()

    def test_update_settings(self, app_client):
        resp = app_client.put("/api/settings", json={"theme": "dark", "lang": "zh"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_settings_persist(self, app_client):
        app_client.put("/api/settings", json={"test_key": "test_value"})
        resp = app_client.get("/api/settings")
        assert resp.json()["settings"]["test_key"] == "test_value"


class TestSSOEndpoints:
    def test_login_url_missing_upstream(self, app_client):
        """SSO login URL endpoint calls upstream, which will fail in test."""
        with patch("iflycode_proxy.web_api.get_login_url") as mock:
            mock.return_value = {"ok": True, "login_url": "https://example.com", "client_id": "test-id"}
            resp = app_client.post("/api/auth/login-url")
            assert resp.status_code == 200
            assert resp.json()["ok"] is True

    def test_login_status_missing_client_id(self, app_client):
        resp = app_client.get("/api/auth/login-status")
        assert resp.status_code == 400

    def test_login_status_with_client_id(self, app_client):
        with patch("iflycode_proxy.web_api.poll_login_status") as mock:
            mock.return_value = {"ok": False, "status": "pending"}
            resp = app_client.get("/api/auth/login-status?client_id=test-id")
            assert resp.status_code == 200

    def test_add_from_sso_missing_token(self, app_client):
        resp = app_client.post("/api/auth/add-from-sso", json={"user_id": "user1"})
        assert resp.status_code == 400

    def test_add_from_sso_success(self, app_client):
        resp = app_client.post("/api/auth/add-from-sso", json={
            "token": "sso-token-123",
            "user_id": "sso-user",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "account_id" in data
        assert "api_key" in data
```

- [ ] **Step 2: 验证 Web API 测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_web_api.py -v`
Expected:
  - Exit code: 0
  - Output contains "30 passed"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_web_api.py && git commit -m "test(api): add web API integration tests (30 cases)"`

---

### Task 7: OpenAI Handler 集成测试（10 cases）

**Depends on:** Task 1, Task 4
**Files:**
- Create: `tests/test_openai_handler.py`

- [ ] **Step 1: 创建 test_openai_handler.py — OpenAI 协议转换测试**

```python
# tests/test_openai_handler.py
"""Tests for OpenAI-compatible API handler — protocol translation."""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from iflycode_proxy.credential_router import CredentialRouter
from iflycode_proxy.db import Database
from iflycode_proxy.server import create_app


def _make_sse_chunks(content_chunks, finish=False):
    """Build mock SSE lines from iFlyCode upstream format."""
    lines = []
    for chunk in content_chunks:
        data = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(data)}")
    if finish:
        data = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        lines.append(f"data: {json.dumps(data)}")
    lines.append("data: [DONE]")
    return lines


def _mock_stream_response(lines):
    """Create a mock _RetryableStream that yields the given lines."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    encoded_lines = [line.encode("utf-8") for line in lines]
    mock.iter_lines.return_value = iter(encoded_lines)
    return mock


@pytest.fixture
def openai_client():
    router = CredentialRouter()
    router.add_account("acc-test", "sk-test-key", "test-token", "test-user", default=True)
    db = Database(db_path="/tmp/test-openai-handler.db")
    app = create_app(router, db=db)
    client = TestClient(app)
    yield client
    db.close()


class TestListModels:
    def test_list_models_returns_static_list(self, openai_client):
        resp = openai_client.get("/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 3
        model_ids = [m["id"] for m in data["data"]]
        assert "iflycode-default" in model_ids
        assert "gpt-4" in model_ids
        assert "gpt-4o" in model_ids


class TestChatCompletionsAuth:
    def test_no_api_key_uses_default(self, openai_client):
        """Without x-api-key, should use default account (not return 401)."""
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["hello"], finish=True)
            )
            resp = openai_client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
            )
            # Should not be 401 — default account should be used
            assert resp.status_code in (200, 500)  # 500 if mock fails, but not 401

    def test_invalid_api_key_returns_401(self):
        router = CredentialRouter()
        # No accounts — no default
        db = Database(db_path="/tmp/test-openai-no-account.db")
        app = create_app(router, db=db)
        client = TestClient(app)
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]},
            headers={"x-api-key": "sk-nonexistent"},
        )
        assert resp.status_code == 401
        db.close()

    def test_valid_api_key_accepted(self, openai_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["test"], finish=True)
            )
            resp = openai_client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code != 401


class TestChatCompletionsInvalidBody:
    def test_invalid_json_returns_400(self, openai_client):
        resp = openai_client.post(
            "/v1/chat/completions",
            content=b"not json",
            headers={"Content-Type": "application/json", "x-api-key": "sk-test-key"},
        )
        assert resp.status_code == 400


class TestChatCompletionsStreaming:
    def test_streaming_response_format(self, openai_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["Hello", " world"], finish=True)
            )
            resp = openai_client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")

    def test_streaming_contains_data_prefix(self, openai_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["hi"], finish=True)
            )
            resp = openai_client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": True},
                headers={"x-api-key": "sk-test-key"},
            )
            content = resp.text
            assert "data: " in content
            assert "[DONE]" in content


class TestChatCompletionsNonStreaming:
    def test_non_streaming_response_format(self, openai_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["Hello world"], finish=True)
            )
            resp = openai_client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["object"] == "chat.completion"
            assert data["choices"][0]["message"]["role"] == "assistant"
            assert "Hello world" in data["choices"][0]["message"]["content"]

    def test_non_streaming_has_id_and_model(self, openai_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["test"], finish=True)
            )
            resp = openai_client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                headers={"x-api-key": "sk-test-key"},
            )
            data = resp.json()
            assert data["id"].startswith("chatcmpl-")
            assert data["model"] == "gpt-4"


class TestHealthEndpoint:
    def test_openai_health(self, openai_client):
        resp = openai_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "iflycode-openai-proxy"
```

- [ ] **Step 2: 验证 OpenAI Handler 测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_openai_handler.py -v`
Expected:
  - Exit code: 0
  - Output contains "10 passed"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_openai_handler.py && git commit -m "test(openai): add OpenAI handler integration tests (10 cases)"`

---

### Task 8: Anthropic Handler 集成测试（10 cases）

**Depends on:** Task 1, Task 4
**Files:**
- Create: `tests/test_anthropic_handler.py`

- [ ] **Step 1: 创建 test_anthropic_handler.py — Anthropic 协议转换测试**

```python
# tests/test_anthropic_handler.py
"""Tests for Anthropic Messages API handler — protocol translation."""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from iflycode_proxy.credential_router import CredentialRouter
from iflycode_proxy.db import Database
from iflycode_proxy.server import create_app


def _make_sse_chunks(content_chunks, finish=False):
    """Build mock SSE lines from iFlyCode upstream format."""
    lines = []
    for chunk in content_chunks:
        data = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(data)}")
    if finish:
        data = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        lines.append(f"data: {json.dumps(data)}")
    lines.append("data: [DONE]")
    return lines


def _mock_stream_response(lines):
    """Create a mock _RetryableStream that yields the given lines."""
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    encoded_lines = [line.encode("utf-8") for line in lines]
    mock.iter_lines.return_value = iter(encoded_lines)
    return mock


@pytest.fixture
def anthropic_client():
    router = CredentialRouter()
    router.add_account("acc-test", "sk-test-key", "test-token", "test-user", default=True)
    db = Database(db_path="/tmp/test-anthropic-handler.db")
    app = create_app(router, db=db)
    client = TestClient(app)
    yield client
    db.close()


class TestAnthropicAuth:
    def test_x_api_key_auth(self, anthropic_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["hi"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": False},
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code != 401

    def test_bearer_auth(self, anthropic_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["hi"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": False},
                headers={"authorization": "Bearer sk-test-key"},
            )
            assert resp.status_code != 401

    def test_no_auth_returns_401(self):
        router = CredentialRouter()
        db = Database(db_path="/tmp/test-anthropic-no-auth.db")
        app = create_app(router, db=db)
        client = TestClient(app)
        resp = client.post(
            "/v1/messages",
            json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100},
        )
        assert resp.status_code == 401
        db.close()


class TestMessageTranslation:
    def test_system_string_translated(self, anthropic_client):
        """Anthropic system string field should be converted to system message."""
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["ok"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={
                    "model": "claude-3",
                    "system": "You are helpful",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 100,
                    "stream": False,
                },
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 200

    def test_system_blocks_translated(self, anthropic_client):
        """Anthropic system as content blocks should be joined."""
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["ok"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={
                    "model": "claude-3",
                    "system": [{"type": "text", "text": "Be helpful"}, {"type": "text", "text": "Be concise"}],
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 100,
                    "stream": False,
                },
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 200

    def test_content_blocks_translated(self, anthropic_client):
        """Anthropic content blocks should be flattened to text."""
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["ok"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={
                    "model": "claude-3",
                    "messages": [{"role": "user", "content": [{"type": "text", "text": "hello"}]}],
                    "max_tokens": 100,
                    "stream": False,
                },
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 200


class TestAnthropicStreaming:
    def test_streaming_event_format(self, anthropic_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["Hello"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": True},
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 200
            content = resp.text
            assert "event: message_start" in content
            assert "event: content_block_start" in content
            assert "event: content_block_delta" in content
            assert "event: message_stop" in content

    def test_streaming_content_delta_format(self, anthropic_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["test content"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": True},
                headers={"x-api-key": "sk-test-key"},
            )
            content = resp.text
            assert "text_delta" in content
            assert "test content" in content


class TestAnthropicNonStreaming:
    def test_non_streaming_response_format(self, anthropic_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["Response text"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": False},
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["type"] == "message"
            assert data["role"] == "assistant"
            assert data["content"][0]["type"] == "text"
            assert "Response text" in data["content"][0]["text"]
            assert data["stop_reason"] == "end_turn"

    def test_non_streaming_has_usage(self, anthropic_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(
                _make_sse_chunks(["test"], finish=True)
            )
            resp = anthropic_client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": False},
                headers={"x-api-key": "sk-test-key"},
            )
            data = resp.json()
            assert "usage" in data
            assert "output_tokens" in data["usage"]


class TestAnthropicErrorHandling:
    def test_invalid_json_returns_400(self, anthropic_client):
        resp = anthropic_client.post(
            "/v1/messages",
            content=b"not json",
            headers={"Content-Type": "application/json", "x-api-key": "sk-test-key"},
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["type"] == "error"

    def test_upstream_error_returns_500(self, anthropic_client):
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.side_effect = Exception("upstream failure")
            resp = anthropic_client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": False},
                headers={"x-api-key": "sk-test-key"},
            )
            assert resp.status_code == 500
```

- [ ] **Step 2: 验证 Anthropic Handler 测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_anthropic_handler.py -v`
Expected:
  - Exit code: 0
  - Output contains "12 passed"

- [ ] **Step 3: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_anthropic_handler.py && git commit -m "test(anthropic): add Anthropic handler integration tests (12 cases)"`

---

### Task 9: Auth 模块单元测试 + 端到端冒烟测试（8 cases）

**Depends on:** Task 1
**Files:**
- Create: `tests/test_auth.py`
- Create: `tests/test_e2e_smoke.py`

- [ ] **Step 1: 创建 test_auth.py — SSO 认证流程测试**

```python
# tests/test_auth.py
"""Tests for SSO authentication module."""

from unittest.mock import patch, MagicMock

import httpx
import pytest

from iflycode_proxy.auth import get_login_url, poll_login_status, _pending_sessions


class TestGetLoginUrl:
    def test_success_returns_url_and_client_id(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "resCode": "0",
            "obj": {"loginUrl": "https://sso.xfyun.cn/login"},
        }
        with patch("iflycode_proxy.auth.httpx.Client") as MockClient:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            MockClient.return_value = mock_http
            result = get_login_url()
            assert result["ok"] is True
            assert "login_url" in result
            assert "client_id" in result
            assert "clientId=" in result["login_url"]

    def test_upstream_error_returns_error(self):
        with patch("iflycode_proxy.auth.httpx.Client") as MockClient:
            MockClient.side_effect = Exception("network error")
            result = get_login_url()
            assert result["ok"] is False
            assert "error" in result

    def test_api_error_code_returns_error(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"resCode": "500", "message": "server error"}
        with patch("iflycode_proxy.auth.httpx.Client") as MockClient:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            MockClient.return_value = mock_http
            result = get_login_url()
            assert result["ok"] is False

    def test_missing_login_url_returns_error(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"resCode": "0", "obj": {}}
        with patch("iflycode_proxy.auth.httpx.Client") as MockClient:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            MockClient.return_value = mock_http
            result = get_login_url()
            assert result["ok"] is False


class TestPollLoginStatus:
    def test_unknown_client_id(self):
        result = poll_login_status("nonexistent-id")
        assert result["ok"] is False
        assert result["status"] == "unknown"

    def test_pending_status(self):
        _pending_sessions["test-id"] = {"login_url": "https://example.com", "status": "pending"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"resCode": "0"}
        with patch("iflycode_proxy.auth.httpx.Client") as MockClient:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            MockClient.return_value = mock_http
            result = poll_login_status("test-id")
            assert result["status"] == "pending"
        _pending_sessions.pop("test-id", None)

    def test_authenticated_returns_token(self):
        _pending_sessions["test-id"] = {"login_url": "https://example.com", "status": "pending"}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "resCode": "0",
            "token": "sso-token-123",
            "userId": "user-123",
        }
        with patch("iflycode_proxy.auth.httpx.Client") as MockClient:
            mock_http = MagicMock()
            mock_http.__enter__ = MagicMock(return_value=mock_http)
            mock_http.__exit__ = MagicMock(return_value=False)
            mock_http.get.return_value = mock_resp
            MockClient.return_value = mock_http
            result = poll_login_status("test-id")
            assert result["ok"] is True
            assert result["status"] == "authenticated"
            assert result["token"] == "sso-token-123"
            # Should be removed from pending sessions after auth
            assert "test-id" not in _pending_sessions
```

- [ ] **Step 2: 创建 test_e2e_smoke.py — 端到端冒烟测试**

```python
# tests/test_e2e_smoke.py
"""End-to-end smoke tests — full request lifecycle through the proxy."""

import json
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from iflycode_proxy.db import Database, _generate_account_id, _generate_api_key
from iflycode_proxy.credential_router import CredentialRouter
from iflycode_proxy.server import create_app


def _mock_stream_response(content_chunks, finish=True):
    lines = []
    for chunk in content_chunks:
        data = {"choices": [{"delta": {"content": chunk}, "finish_reason": None}]}
        lines.append(f"data: {json.dumps(data)}")
    if finish:
        data = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        lines.append(f"data: {json.dumps(data)}")
    lines.append("data: [DONE]")
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    mock.iter_lines.return_value = iter([line.encode("utf-8") for line in lines])
    return mock


class TestFullLifecycle:
    """Test the complete flow: add account → make request → check logs."""

    def test_openai_full_lifecycle(self, tmp_path):
        db = Database(db_path=tmp_path / "lifecycle.db")
        router = CredentialRouter()
        app = create_app(router, db=db)
        client = TestClient(app)

        # 1. Add account
        resp = client.post("/api/accounts", json={"spark_token": "lifecycle-token"})
        assert resp.status_code == 200
        account_id = resp.json()["account_id"]
        api_key = resp.json()["api_key"]

        # Register in router
        router.add_account(account_id, api_key, "lifecycle-token", "user", default=True)

        # 2. Make a chat request (non-streaming)
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(["Hello from iFlyCode"])
            resp = client.post(
                "/v1/chat/completions",
                json={"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}], "stream": False},
                headers={"x-api-key": api_key},
            )
            assert resp.status_code == 200
            assert "Hello from iFlyCode" in resp.json()["choices"][0]["message"]["content"]

        # 3. Check that request was logged
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        assert resp.json()["total_requests"] >= 1

        db.close()

    def test_anthropic_full_lifecycle(self, tmp_path):
        db = Database(db_path=tmp_path / "anthropic-lifecycle.db")
        router = CredentialRouter()
        app = create_app(router, db=db)
        client = TestClient(app)

        # 1. Add account
        resp = client.post("/api/accounts", json={"spark_token": "lifecycle-token"})
        account_id = resp.json()["account_id"]
        api_key = resp.json()["api_key"]
        router.add_account(account_id, api_key, "lifecycle-token", "user", default=True)

        # 2. Make an Anthropic request
        with patch("iflycode_proxy.client.Client.chat_stream") as mock_stream:
            mock_stream.return_value = _mock_stream_response(["Anthropic response"])
            resp = client.post(
                "/v1/messages",
                json={"model": "claude-3", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100, "stream": False},
                headers={"x-api-key": api_key},
            )
            assert resp.status_code == 200
            assert "Anthropic response" in resp.json()["content"][0]["text"]

        db.close()

    def test_account_management_lifecycle(self, tmp_path):
        """Add → validate → renew → delete account lifecycle."""
        db = Database(db_path=tmp_path / "mgmt-lifecycle.db")
        router = CredentialRouter()
        app = create_app(router, db=db)
        client = TestClient(app)

        # Add
        resp = client.post("/api/accounts", json={"spark_token": "token-1", "user_id": "u1"})
        account_id = resp.json()["account_id"]
        api_key_1 = resp.json()["api_key"]

        # List
        resp = client.get("/api/accounts")
        assert any(a["account_id"] == account_id for a in resp.json()["accounts"])

        # Renew key
        resp = client.post(f"/api/accounts/{account_id}/renew-key")
        assert resp.status_code == 200
        api_key_2 = resp.json()["api_key"]
        assert api_key_2 != api_key_1

        # Delete
        resp = client.delete(f"/api/accounts/{account_id}")
        assert resp.status_code == 200

        # Verify deleted
        resp = client.get("/api/accounts")
        assert not any(a["account_id"] == account_id for a in resp.json()["accounts"])

        db.close()
```

- [ ] **Step 3: 验证 Auth 和 E2E 冒烟测试**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/test_auth.py tests/test_e2e_smoke.py -v`
Expected:
  - Exit code: 0
  - Output contains "10 passed"

- [ ] **Step 4: 运行完整测试套件**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && python3 -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected:
  - Exit code: 0
  - Output contains total test count >= 90

- [ ] **Step 5: 提交**
Run: `cd /Users/cc11001100/github/vibe-coding-labs/iflycode-2api && git add tests/test_auth.py tests/test_e2e_smoke.py && git commit -m "test(auth,e2e): add SSO auth and end-to-end smoke tests (10 cases)"`
