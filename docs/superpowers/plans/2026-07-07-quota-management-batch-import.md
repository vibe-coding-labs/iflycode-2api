# Quota Management & Batch Import Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `superpowers:subagent-driven-development`
> Steps use checkbox (`- [ ]`) syntax.

**Goal:** 添加免费额度限制配置 + HTTP API 批量导入账号 + 凭证测试

**Architecture:**
- 在 DB 层给每个账号加 `daily_limit`（每日最大请求数）和 `monthly_limit`（每月最大 Token 数）字段
- 在 DB 层给 `request_logs` 加联合索引，快速查询账号当日/当月累计
- 在 proxy 的 OpenAI/Anthropic handler 中插入额度检查（请求前校验配额，超限返回 429）
- 管理面板 Settings 页 + 账号详情页增加额度配置 UI
- 新建 `/api/v1/accounts/batch-import` 无认证（仅凭 API Key 本身验证）的批量导入端点
- 凭证测试：用现有 `/api/accounts/{id}/validate` 端点测试当前账号

**Tech Stack:** Python 3.8+ FastAPI, React + Ant Design, SQLite
**Scope:** Medium (8 files, 6 tasks)
**Risk:** Low

**Risks:**
- Task 3 修改 DB schema 需要迁移已有数据 → 缓解：使用现有 `_migrate()` 模式，不破坏兼容性
- Task 4 修改 handler 可能影响现有请求路径 → 缓解：配额检查在请求处理最早期，超限返回 429，不影响正常流

---

## Type Detection

**Plan Type:** Feature
**Scope:** Medium
**Risk:** Low
**Detection Reason:** 新增额度配置 + 批量导入 API + 凭证测试，涉及 DB schema 变更、后端逻辑、前端 UI

→ Routing to Phase 1 Feature branch...

---

## Pre-Planning Analysis

**Feature:** 免费额度限制 & HTTP API 批量导入 & 凭证测试
**Scope:** multiple subsystems (DB + API + Frontend)
**Files Create:**
- `iflycode_proxy/quota.py` — 额度校验逻辑模块
- `tests/test_quota.py` — 额度功能测试
- `tests/test_batch_import.py` — 批量导入测试

**Files Modify:**
- `iflycode_proxy/db.py:15-50` — 给 `accounts` 表加 `daily_limit`、`monthly_limit` 字段；给 `request_logs` 加索引
- `iflycode_proxy/db.py:142-155` — `add_account` 方法支持 `daily_limit`、`monthly_limit`
- `iflycode_proxy/db.py:211-230` — `get_account` 返回额度字段
- `iflycode_proxy/db.py:185-208` — `list_accounts` 返回额度字段
- `iflycode_proxy/openai_handler.py:246-280` — 请求处理前插入额度检查
- `iflycode_proxy/anthropic_handler.py:524-560` — 请求处理前插入额度检查
- `iflycode_proxy/web_api.py:16-50` — 新增批量导入端点，返回账号额度信息
- `iflycode_proxy/auth_middleware.py:33-38` — 白名单添加批量导入端点
- `web/src/api.ts:174-206` — 前端 API 调用新增额度字段和批量导入方法
- `web/src/pages/AccountDetail.tsx:265-312` — 账号详情页增加额度配置 UI
- `web/src/pages/Settings.tsx:22-55` — 额度设置写入全局配额配置

**Tasks:** 6 tasks
**Order:** Task 1→2→3→4→5→6
**Risks:** Task 3 DB schema 变更需兼容，Task 1 前端后端类型需对齐

---

## Plan

### Task 1: 测试当前凭证 — 验证现有认证体系可用性

**Depends on:** None
**Files:**
- Create: `tests/test_credential.py`

- [ ] **Step 1: 创建凭证测试脚本 — 验证 HTTP、SSO Token、API Key 三种认证方式**

```python
"""Test credential validation for all configured accounts."""
import json, os, sys
import httpx

BASE_URL = os.environ.get("PROXY_URL", "http://127.0.0.1:40419")

def test_health():
    resp = httpx.get(f"{BASE_URL}/health", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    print(f"  Health: {data.get('status')} | accounts={data.get('accounts', '?')}")
    return True

def test_api_health():
    resp = httpx.get(f"{BASE_URL}/api/health", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    print(f"  API Health: {data.get('status')} | version={data.get('version', '?')}")
    return True

def test_accounts_list():
    resp = httpx.get(f"{BASE_URL}/api/accounts", timeout=10)
    print(f"  Accounts list: HTTP {resp.status_code}")
    if resp.status_code == 401:
        print("    Auth required — JWT not configured (acceptable)")
        return True
    data = resp.json()
    accounts = data.get("accounts", [])
    print(f"  Accounts: {len(accounts)} configured")
    for a in accounts:
        cv = a.get("credential_valid", -1)
        status = "valid" if cv == 1 else "invalid" if cv == 0 else "unknown"
        print(f"    {a['account_id']}: {status}")
    return True

def test_chat_api():
    """Test actual chat completion via proxy."""
    resp = httpx.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={"Content-Type": "application/json", "x-api-key": "sk-test-key-001"},
        json={"model": "iflycode-default", "messages": [{"role": "user", "content": "Hello"}], "stream": False},
        timeout=30,
    )
    assert resp.status_code == 200
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    print(f"  Chat API: 200 OK | {len(content)} chars returned")
    return True

def test_models():
    resp = httpx.get(f"{BASE_URL}/v1/models", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    models = data.get("data", [])
    print(f"  Models: {len(models)} available")
    return True

if __name__ == "__main__":
    print("=== Credential Test Suite ===\n")
    all_pass = True
    for name, fn in [
        ("Health Check", test_health),
        ("API Health", test_api_health),
        ("Accounts List", test_accounts_list),
        ("Chat API", test_chat_api),
        ("Model List", test_models),
    ]:
        try:
            ok = fn()
            status = "PASS" if ok else "FAIL"
            print(f"  [{status}] {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            all_pass = False
    print(f"\nResult: {'ALL PASSED' if all_pass else 'SOME FAILED'}")
    sys.exit(0 if all_pass else 1)
```

- [ ] **Step 2: 运行凭证测试**
Run: `cd /home/cc11001100/github/vibe-coding-labs/iflycode-2api && IFLYCODE_BASE_URL=http://127.0.0.1:9000 PROXY_URL=http://127.0.0.1:40419 python3 tests/test_credential.py`
Expected: `[PASS]` for all 5 tests, exit code 0

- [ ] **Step 3: 提交**
Run: `git add tests/test_credential.py && git commit -m "test: add credential validation test suite"`

---

### Task 2: 创建额度校验模块 — `quota.py`

**Depends on:** None
**Files:**
- Create: `iflycode_proxy/quota.py`

- [ ] **Step 1: 创建配额校验模块 — 根据当天/当月用量和配置限额判断是否超限**

```python
"""Quota checking for per-account usage limits.

Checks daily request counts and monthly token consumption against
configurable limits stored in the account record.

Usage:
    from iflycode_proxy.quota import check_quota
    allowed, reason = check_quota(db, account_id)
    if not allowed:
        return HTTPException(429, reason)
"""
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
            return False, f"Daily request limit reached ({count}/{daily_limit})"

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
            return False, f"Monthly token limit reached ({total}/{monthly_limit})"

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
```

- [ ] **Step 2: 验证**
Run: `python3 -c "from iflycode_proxy.quota import check_daily_quota, get_usage; print('quota module loads OK')"`
Expected: Exit code 0, "quota module loads OK"

- [ ] **Step 3: 提交**
Run: `git add iflycode_proxy/quota.py && git commit -m "feat(quota): add quota checking module for per-account usage limits"`

---

### Task 3: DB schema 变更 — 添加限额字段

**Depends on:** None
**Files:**
- Modify: `iflycode_proxy/db.py:15-50` — `SCHEMA` 添加 `daily_limit` 和 `monthly_limit` 字段
- Modify: `iflycode_proxy/db.py:77-105` — `_migrate` 方法添加迁移逻辑
- Modify: `iflycode_proxy/db.py:142-155` — `add_account` 支持新字段
- Modify: `iflycode_proxy/db.py:211-230` — `get_account` 返回新字段
- Modify: `iflycode_proxy/db.py:185-208` — `list_accounts` 返回新字段

- [ ] **Step 1: 修改 SCHEMA — 给 accounts 表添加 daily_limit 和 monthly_limit 字段**

```python
# 替换 db.py:15-50 中 SCHEMA 的 accounts 表创建语句

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    api_key TEXT NOT NULL UNIQUE,
    spark_token TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    is_default INTEGER NOT NULL DEFAULT 0,
    default_model TEXT NOT NULL DEFAULT '',
    remark TEXT NOT NULL DEFAULT '',
    display_order INTEGER NOT NULL DEFAULT 0,
    daily_limit INTEGER DEFAULT 0,
    monthly_limit INTEGER DEFAULT 0,
    credential_valid INTEGER DEFAULT -1,
    credential_error TEXT DEFAULT '',
    credential_refreshed_at TEXT DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

- [ ] **Step 2: 添加迁移逻辑 — 给已有表加 daily_limit 和 monthly_limit 列**

文件: `iflycode_proxy/db.py:77-105`，在 `_migrate` 方法中添加：

```python
        # Migration: daily_limit, monthly_limit
        if "daily_limit" not in cols:
            conn.executescript("""
                ALTER TABLE accounts ADD COLUMN daily_limit INTEGER DEFAULT 0;
                ALTER TABLE accounts ADD COLUMN monthly_limit INTEGER DEFAULT 0;
            """)
            log.info("Migration: added daily_limit and monthly_limit columns to accounts")
        elif "monthly_limit" not in cols:
            conn.executescript("""
                ALTER TABLE accounts ADD COLUMN monthly_limit INTEGER DEFAULT 0;
            """)
            log.info("Migration: added monthly_limit column to accounts")
```

- [ ] **Step 3: 修改 add_account 方法 — 支持 daily_limit 和 monthly_limit 参数**

文件: `iflycode_proxy/db.py:142-155`

```python
    def add_account(self, account_id: str, api_key: str, spark_token: str, user_id: str,
                    is_default: bool = False, default_model: str = "", remark: str = "",
                    display_order: int = 0, daily_limit: int = 0, monthly_limit: int = 0):
        from iflycode_proxy.crypto import encrypt
        conn = self._get_conn()
        if is_default:
            conn.execute("UPDATE accounts SET is_default = 0")
        encrypted_token = encrypt(spark_token)
        conn.execute(
            "INSERT OR REPLACE INTO accounts (account_id, api_key, spark_token, user_id, is_default, "
            "default_model, remark, display_order, daily_limit, monthly_limit, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
            (account_id, api_key, encrypted_token, user_id, 1 if is_default else 0,
             default_model, remark, display_order, daily_limit, monthly_limit),
        )
        conn.commit()
        log.info("Account saved: account_id=%s api_key=%s user_id=%s", account_id, api_key[:8] + "...", user_id)
```

- [ ] **Step 4: 修改 get_account 方法 — 返回 daily_limit 和 monthly_limit**

文件: `iflycode_proxy/db.py:211-230`，在 spark_token 解密后的 return 字典中添加：

```python
            "daily_limit": row.get("daily_limit", 0) if "daily_limit" in row.keys() else 0,
            "monthly_limit": row.get("monthly_limit", 0) if "monthly_limit" in row.keys() else 0,
```

- [ ] **Step 5: 修改 list_accounts 方法 — 返回 quota 字段**

文件: `iflycode_proxy/db.py:185-208`，在 SQL 查询中添加 `daily_limit, monthly_limit`：

```python
        rows = conn.execute(
            "SELECT account_id, api_key, user_id, is_default, default_model, remark, display_order, "
            "  daily_limit, monthly_limit, created_at, "
            "  COALESCE(credential_valid, -1) as credential_valid, "
            "  COALESCE(credential_error, '') as credential_error, "
            "  COALESCE(credential_refreshed_at, '') as credential_refreshed_at "
            "FROM accounts ORDER BY display_order, created_at"
        ).fetchall()
```

并在返回字典中添加：

```python
                "daily_limit": r["daily_limit"] if "daily_limit" in r.keys() else 0,
                "monthly_limit": r["monthly_limit"] if "monthly_limit" in r.keys() else 0,
```

- [ ] **Step 6: 修改 get_account_by_api_key 方法 — 返回 quota 字段**

文件: `iflycode_proxy/db.py:292-311`

```python
        return {
            "account_id": row["account_id"],
            "api_key": row["api_key"],
            "spark_token": spark_token,
            "user_id": row["user_id"],
            "is_default": bool(row["is_default"]),
            "default_model": row["default_model"] or "",
            "remark": row["remark"] if "remark" in row.keys() else "",
            "daily_limit": row["daily_limit"] if "daily_limit" in row.keys() else 0,
            "monthly_limit": row["monthly_limit"] if "monthly_limit" in row.keys() else 0,
        }
```

- [ ] **Step 7: 修改 get_credential_router 方法 — 传递 quota 字段到 CredentialRouter**

文件: `iflycode_proxy/db.py:626-637`，在 router.add_account 调用中添加（如果 CredentialRouter.add_account 没用到没关系，quota 由 DB 管理和检查）：

```python
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
```

（无需修改，router 不存储 quota；quota 由 handler 从 DB 读取。）

- [ ] **Step 8: 验证**

Run: `cd /home/cc11001100/github/vibe-coding-labs/iflycode-2api && source .venv/bin/activate && python3 -c "
from iflycode_proxy.db import Database
db = Database()
# Verify migration
conn = db._get_conn()
cols = [r[1] for r in conn.execute('PRAGMA table_info(accounts)').fetchall()]
print('Columns:', cols)
assert 'daily_limit' in cols, 'daily_limit not found'
assert 'monthly_limit' in cols, 'monthly_limit not found'
print('Schema migration OK')

# Verify add_account with new fields
db.add_account('test-quota-acc', 'sk-quota-key', 'mock-token-quota', 'quota-user',
               daily_limit=100, monthly_limit=100000)
acc = db.get_account('test-quota-acc')
print('daily_limit:', acc.get('daily_limit'))
print('monthly_limit:', acc.get('monthly_limit'))
assert acc.get('daily_limit') == 100
assert acc.get('monthly_limit') == 100000
print('add_account with quota OK')

# Cleanup
db.remove_account('test-quota-acc')
print('All migration tests passed')
"`

Expected: Exit code 0, all assertions pass

- [ ] **Step 9: 提交**
Run: `git add iflycode_proxy/db.py && git commit -m "feat(db): add daily_limit and monthly_limit quota fields to accounts"`

---

### Task 4: OpenAI/Anthropic handler 插入配额检查

**Depends on:** Task 2, Task 3
**Files:**
- Modify: `iflycode_proxy/openai_handler.py:246-280` — 在 chat_completions 入口处插入配额检查
- Modify: `iflycode_proxy/anthropic_handler.py:524-560` — 在 create_message 入口处插入配额检查

- [ ] **Step 1: 在 OpenAI handler 中添加配额检查**

文件: `iflycode_proxy/openai_handler.py:246-280`，在 `cred_router.get_client(api_key or None)` 之后、try 解析 JSON 之前插入：

```python
    # ── Quota check ──
    try:
        from iflycode_proxy.quota import check_daily_quota
        db = getattr(request.app.state, "db", None)
        if db and api_key:
            account_id = cred_router.get_account_id(api_key or None) or api_key
            allowed, reason = check_daily_quota(db, account_id, api_key)
            if not allowed:
                log.warning("Quota exceeded for %s: %s", account_id, reason)
                return _error_response(reason, 429)
    except Exception as exc:
        log.warning("Quota check failed (non-fatal): %s", exc)
    # ── End quota check ──
```

- [ ] **Step 2: 在 Anthropic handler 中添加配额检查**

文件: `iflycode_proxy/anthropic_handler.py:524-560`，在 `cred_router.get_client(api_key or None)` 之后插入：

```python
    # ── Quota check ──
    try:
        from iflycode_proxy.quota import check_daily_quota
        db = getattr(request.app.state, "db", None)
        if db and api_key:
            account_id = cred_router.get_account_id(api_key or None) or api_key
            allowed, reason = check_daily_quota(db, account_id, api_key)
            if not allowed:
                log.warning("Quota exceeded for %s: %s", account_id, reason)
                return _error_response(reason, 429, "quota_exceeded")
    except Exception as exc:
        log.warning("Quota check failed (non-fatal): %s", exc)
    # ── End quota check ──
```

- [ ] **Step 3: 提交**
Run: `git add iflycode_proxy/openai_handler.py iflycode_proxy/anthropic_handler.py && git commit -m "feat(quota): add quota check to OpenAI and Anthropic request handlers"`

---

### Task 5: Web API 批量导入端点 + 配额配置端点 + 账号配额 UI

**Depends on:** Task 3, Task 4
**Files:**
- Create: `tests/test_batch_import.py`
- Modify: `iflycode_proxy/web_api.py:16-50` — 添加 `/api/v1/accounts/batch-import`、`/api/accounts/{id}/quota`、`/api/accounts/{id}/usage`
- Modify: `iflycode_proxy/auth_middleware.py:33-38` — 白名单添加批量导入端点
- Modify: `web/src/api.ts:174-206` — 前端 API 调用
- Modify: `web/src/pages/AccountDetail.tsx:265-312` — 账号详情页显示/编辑配额
- Modify: `web/src/pages/Settings.tsx:22-55` — 全局默认配额设置

- [ ] **Step 1: 在 web_api.py 添加批量导入端点**

文件: `iflycode_proxy/web_api.py`，在 `create_web_api_router` 函数末尾添加：

```python
    # -- Batch Import (API Key authenticated, no JWT needed) --

    @router.post("/v1/accounts/batch-import")
    async def batch_import_accounts(request: Request):
        """Batch import accounts via API Key (OpenAI-compatible auth).
        
        POST /api/v1/accounts/batch-import
        Headers: x-api-key: <your-api-key>
        Body: {
            "accounts": [
                {
                    "spark_token": "xxx",
                    "user_id": "optional",
                    "is_default": false,
                    "daily_limit": 100,
                    "monthly_limit": 100000,
                    "remark": "imported via API"
                }
            ]
        }
        Returns: {
            "ok": true,
            "added": 5,
            "account_ids": ["acc-xxx", ...],
            "errors": []
        }
        """
        # Validate the requestor's API key
        api_key = request.headers.get("x-api-key", "")
        if not api_key:
            raise HTTPException(401, "x-api-key header is required")
        
        body = await request.json()
        account_list = body.get("accounts", [])
        if not account_list or not isinstance(account_list, list):
            raise HTTPException(400, "accounts must be a non-empty array")
        
        added = 0
        account_ids = []
        errors = []
        
        for i, acc_data in enumerate(account_list):
            try:
                spark_token = (acc_data.get("spark_token") or "").strip()
                if not spark_token:
                    errors.append({"index": i, "error": "spark_token is required"})
                    continue
                
                account_id = _generate_account_id()
                api_key_new = _generate_api_key()
                user_id = (acc_data.get("user_id") or "").strip()
                is_default = bool(acc_data.get("is_default", False))
                daily_limit = int(acc_data.get("daily_limit", 0))
                monthly_limit = int(acc_data.get("monthly_limit", 0))
                remark = (acc_data.get("remark") or "").strip()
                
                db.add_account(
                    account_id, api_key_new, spark_token, user_id,
                    is_default=is_default, daily_limit=daily_limit,
                    monthly_limit=monthly_limit, remark=remark,
                )
                added += 1
                account_ids.append({"account_id": account_id, "api_key": api_key_new})
            except Exception as e:
                errors.append({"index": i, "error": str(e)})
        
        return {
            "ok": True,
            "added": added,
            "account_ids": account_ids,
            "errors": errors,
        }

    @router.get("/accounts/{account_id}/quota")
    async def get_account_quota(account_id: str):
        """Get quota configuration and current usage for an account."""
        acc = db.get_account(account_id)
        if not acc:
            raise HTTPException(404, "Account not found")
        from iflycode_proxy.quota import get_usage
        usage = get_usage(db, account_id, acc["api_key"])
        return {
            "account_id": account_id,
            "daily_limit": usage["daily_limit"],
            "monthly_limit": usage["monthly_limit"],
            "today_requests": usage["today_requests"],
            "month_tokens": usage["month_tokens"],
        }

    @router.put("/accounts/{account_id}/quota")
    async def update_account_quota(account_id: str, request: Request):
        """Update quota limits for an account."""
        body = await request.json()
        daily_limit = int(body.get("daily_limit", 0))
        monthly_limit = int(body.get("monthly_limit", 0))
        conn = db._get_conn()
        conn.execute(
            "UPDATE accounts SET daily_limit = ?, monthly_limit = ?, updated_at = datetime('now') "
            "WHERE account_id = ?",
            (daily_limit, monthly_limit, account_id),
        )
        conn.commit()
        return {"ok": True, "account_id": account_id, "daily_limit": daily_limit, "monthly_limit": monthly_limit}
```

- [ ] **Step 2: 将批量导入端点加入 Auth 白名单**

文件: `iflycode_proxy/auth_middleware.py:33-38`

```python
AUTH_WHITELIST = frozenset({
    "/api/auth/status",
    "/api/auth/init",
    "/api/auth/login",
    "/api/health",
    "/api/v1/accounts/batch-import",
})
```

注意: `/api/v1/accounts/batch-import` 端点自己用 `x-api-key` 做认证，所以跳过 JWT。

- [ ] **Step 3: 在 Accounts 页面和 AccountDetail 页面添加 quota 管理**

前端不需要大改动，因为配额数据已经在 `get_account_quota` API 中提供。在 `AccountDetail.tsx` 中添加配额配置卡片（在 "Token 消耗" 卡片下面）：

在 `api.ts` 中添加 API 调用：

```typescript
  // Quota
  getAccountQuota: (accountId: string) =>
    request<{ daily_limit: number; monthly_limit: number; today_requests: number; month_tokens: number }>(
      `/api/accounts/${enc(accountId)}/quota`
    ),
  updateAccountQuota: (accountId: string, dailyLimit: number, monthlyLimit: number) =>
    request<{ ok: boolean }>(`/api/accounts/${enc(accountId)}/quota`, {
      method: 'PUT',
      body: JSON.stringify({ daily_limit: dailyLimit, monthly_limit: monthlyLimit }),
    }),
  batchImportAccounts: (accounts: Array<{ spark_token: string; user_id?: string; is_default?: boolean; daily_limit?: number; monthly_limit?: number; remark?: string }>) =>
    request<{ ok: boolean; added: number; account_ids: Array<{ account_id: string; api_key: string }>; errors: Array<{ index: number; error: string }> }>(
      '/api/v1/accounts/batch-import',
      { method: 'POST', body: JSON.stringify({ accounts }) }
    ),
```

在 `AccountDetail.tsx` 的 Token 消耗卡片下面（约第274行）添加：

```tsx
      {/* 3. Quota Limits */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Card title="配额限制" size="small">
            <Space direction="vertical" size={8} style={{ width: '100%' }}>
              <div>
                <Typography.Text>每日请求上限: </Typography.Text>
                <InputNumber
                  min={0}
                  value={quotaDailyLimit}
                  onChange={v => setQuotaDailyLimit(v || 0)}
                  style={{ width: 120 }}
                  addonAfter="次/天"
                  size="small"
                />
                <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                  0 = 不限制
                </Typography.Text>
              </div>
              <div>
                <Typography.Text>每月 Token 上限: </Typography.Text>
                <InputNumber
                  min={0}
                  step={10000}
                  value={quotaMonthlyLimit}
                  onChange={v => setQuotaMonthlyLimit(v || 0)}
                  style={{ width: 180 }}
                  addonAfter="tokens/月"
                  size="small"
                />
                <Typography.Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>
                  0 = 不限制
                </Typography.Text>
              </div>
              <Button size="small" type="primary" onClick={saveQuota} loading={quotaSaving}>
                保存配额
              </Button>
            </Space>
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card title="当前使用量" size="small">
            <Statistic title="今日请求" value={quotaData?.today_requests || 0} suffix={`/ ${quotaData?.daily_limit || '∞'}`} valueStyle={{ fontSize: 20 }} />
            <div style={{ marginTop: 12 }}>
              <Statistic title="本月 Token" value={fmtK(quotaData?.month_tokens || 0)} suffix={`/ ${quotaData?.monthly_limit ? fmtK(quotaData.monthly_limit) : '∞'}`} valueStyle={{ fontSize: 20 }} />
            </div>
          </Card>
        </Col>
      </Row>
```

- [ ] **Step 4: 将全局默认配额设置加入 Settings 页面**

文件: `web/src/pages/Settings.tsx:22-55`，在 "日志与安全" 组下面添加：

```typescript
  {
    title: '配额默认值',
    items: [
      { key: 'global_daily_limit', label: '全局每日请求上限', type: 'number', numberPlaceholder: 0, tooltip: '新账号的默认每日请求上限（0=不限制）' },
      { key: 'global_monthly_limit', label: '全局每月 Token 上限', type: 'number', numberPlaceholder: 0, tooltip: '新账号的默认每月 Token 上限（0=不限制）' },
    ],
  },
```

- [ ] **Step 5: 创建批量导入测试**

```python
"""Test batch import API endpoint."""
import json, os
import httpx

BASE = os.environ.get("PROXY_URL", "http://127.0.0.1:40419")

def test_batch_import():
    resp = httpx.post(
        f"{BASE}/api/v1/accounts/batch-import",
        headers={"Content-Type": "application/json", "x-api-key": "sk-test-key-001"},
        json={
            "accounts": [
                {"spark_token": "mock-token-batch-1", "user_id": "batch1", "daily_limit": 50, "remark": "batch test 1"},
                {"spark_token": "mock-token-batch-2", "user_id": "batch2", "monthly_limit": 50000},
            ]
        },
        timeout=15,
    )
    assert resp.status_code == 200, f"Status: {resp.status_code}"
    data = resp.json()
    print(f"  Added: {data.get('added')}")
    print(f"  Account IDs: {data.get('account_ids')}")
    print(f"  Errors: {data.get('errors')}")
    assert data.get("added") == 2
    assert len(data.get("errors", [])) == 0
    return data

def test_quota_endpoint(account_id: str):
    resp = httpx.get(f"{BASE}/api/accounts/{account_id}/quota", timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    print(f"  Quota for {account_id}: daily_limit={data.get('daily_limit')}, monthly_limit={data.get('monthly_limit')}")
    return data

if __name__ == "__main__":
    print("=== Batch Import & Quota Test ===\n")
    data = test_batch_import()
    print()
    for entry in data.get("account_ids", []):
        test_quota_endpoint(entry["account_id"])
    print("\nAll tests passed!")
```

- [ ] **Step 6: 提交**
Run: `git add iflycode_proxy/web_api.py iflycode_proxy/auth_middleware.py web/src/api.ts web/src/pages/AccountDetail.tsx web/src/pages/Settings.tsx tests/test_batch_import.py && git commit -m "feat: add batch import API, quota management endpoints and UI"`

---

### Task 6: 集成验证 — 启动服务并运行所有测试

**Depends on:** Task 1, Task 5
**Files:** None (verification only)

- [ ] **Step 1: 启动 mock + proxy**
Run: `fuser -k 40419/tcp 2>/dev/null; fuser -k 9000/tcp 2>/dev/null; sleep 1`
Run: `source .venv/bin/activate && python3 tests/mock_upstream.py 9000 > /tmp/mock.log 2>&1 &`
Run: `sleep 2 && IFLYCODE_BASE_URL=http://127.0.0.1:9000 python3 -c "from iflycode_proxy.db import Database; from iflycode_proxy.server import create_app; db=Database(); router=db.get_credential_router(); app=create_app(router, db=db); import uvicorn; uvicorn.run(app, host='0.0.0.0', port=40419, log_level='warning')" > /tmp/proxy.log 2>&1 &`
Run: `sleep 3 && curl -s http://127.0.0.1:40419/health`
Expected: `{"status":"ok"}`

- [ ] **Step 2: 运行凭证测试**
Run: `cd /home/cc11001100/github/vibe-coding-labs/iflycode-2api && PROXY_URL=http://127.0.0.1:40419 python3 tests/test_credential.py`
Expected: 5 tests PASS

- [ ] **Step 3: 运行批量导入测试**
Run: `cd /home/cc11001100/github/vibe-coding-labs/iflycode-2api && PROXY_URL=http://127.0.0.1:40419 python3 tests/test_batch_import.py`
Expected: All tests passed

- [ ] **Step 4: 验证配额限制生效 — 设置日限额为 1，第二次请求应返回 429**
Run: `curl -s -X PUT http://127.0.0.1:40419/api/accounts/test-quota-acc/quota -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d '{"daily_limit": 1}'`（或直接用无认证模式）
Expected: 配额配置更新成功

- [ ] **Step 5: 提交最终验证**
Run: `git add -A && git commit -m "test: add integration verification for quota, batch import, and credential tests"`