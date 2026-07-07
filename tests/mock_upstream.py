"""Mock iFlyCode upstream — produces realistic, non-trivial responses for stress testing.

Usage:
    python tests/mock_upstream.py [port]
    IFLYCODE_BASE_URL=http://localhost:9000 iflycode-2api serve
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
import uuid
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [MOCK] %(message)s")
log = logging.getLogger("mock-upstream")

app = FastAPI(title="Mock iFlyCode Upstream")

_valid_tokens: set[str] = set()
_model_responses: dict[str, list[dict]] = {}

_valid_tokens.add("mock-token-001")
_valid_tokens.add("mock-token-002")

# ── Rich response banks ─────────────────────────────────────────

BIG_CODE_RESPONSE = """好的，我来帮你实现这个功能。

首先，我们需要考虑几个关键设计原则：
1. 单一职责原则 — 每个类只负责一件事
2. 接口隔离原则 — 不强迫调用方依赖不需要的方法
3. 依赖倒置原则 — 依赖抽象而非具体实现

下面是完整的实现：

```python
import json
import threading
import time
from typing import Any, Optional
from pathlib import Path


class KVStore:
    \"\"\"A simple in-memory key-value store with optional persistence.\"\"\"

    def __init__(self, persist_path: Optional[str] = None):
        self._data: dict[str, Any] = {}
        self._ttl: dict[str, float] = {}
        self._lock = threading.RLock()
        self._persist_path = Path(persist_path) if persist_path else None
        self._loaded = False
        self._load()

    # ── Core operations ──

    def get(self, key: str, default: Any = None) -> Any:
        \"\"\"Retrieve a value by key. Returns default if key not found or expired.\"\"\"
        with self._lock:
            self._evict_expired()
            return self._data.get(key, default)

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        \"\"\"Set a key-value pair with optional TTL.\"\"\"
        with self._lock:
            self._data[key] = value
            if ttl_seconds is not None:
                self._ttl[key] = time.time() + ttl_seconds
            self._save()

    def delete(self, key: str) -> bool:
        \"\"\"Delete a key. Returns True if it existed.\"\"\"
        with self._lock:
            existed = key in self._data
            self._data.pop(key, None)
            self._ttl.pop(key, None)
            if existed:
                self._save()
            return existed

    def keys(self, pattern: Optional[str] = None) -> list[str]:
        \"\"\"List all keys, optionally filtered by prefix pattern.\"\"\"
        with self._lock:
            self._evict_expired()
            if pattern:
                return [k for k in self._data if k.startswith(pattern)]
            return list(self._data.keys())

    def clear(self) -> None:
        \"\"\"Remove all keys.\"\"\"
        with self._lock:
            self._data.clear()
            self._ttl.clear()
            self._save()

    def size(self) -> int:
        \"\"\"Return the number of stored keys.\"\"\"
        with self._lock:
            self._evict_expired()
            return len(self._data)

    # ── Persistence ──

    def _load(self) -> None:
        if self._persist_path and self._persist_path.exists():
            try:
                raw = self._persist_path.read_text()
                blob = json.loads(raw)
                self._data = blob.get("data", {})
                self._ttl = blob.get("ttl", {})
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self) -> None:
        if self._persist_path:
            try:
                self._persist_path.parent.mkdir(parents=True, exist_ok=True)
                blob = json.dumps({"data": self._data, "ttl": self._ttl})
                self._persist_path.write_text(blob)
            except OSError:
                pass

    # ── TTL ──

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [k for k, expiry in self._ttl.items() if expiry <= now]
        for k in expired:
            del self._data[k]
            del self._ttl[k]

    def __len__(self) -> int:
        return self.size()

    def __contains__(self, key: str) -> bool:
        return self.get(key, _sentinel) is not _sentinel


_sentinel = object()


# ── Background cleanup thread ──

class BackgroundCleanup:
    \"\"\"Periodically removes expired keys from a KVStore.\"\"\"

    def __init__(self, store: KVStore, interval: int = 60):
        self._store = store
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            _ = self._store.size()  # triggers eviction

    def stop(self) -> None:
        self._stop.set()


# ── Usage example ──

if __name__ == '__main__':
    store = KVStore("kvstore.json")
    store.set("user:1", {"name": "Alice", "role": "admin"}, ttl_seconds=3600)
    store.set("user:2", {"name": "Bob", "role": "user"})
    store.set("config:theme", "dark")

    cleaner = BackgroundCleanup(store, interval=60)

    print(f\"Users: {store.keys('user:')}\")
    print(f\"Config: {store.get('config:theme')}\")
    print(f\"Deleted user:1? {store.delete('user:1')}\")
    print(f\"Final size: {store.size()}\")
```

这个实现涵盖了：
- 线程安全的读写操作
- 可选的 TTL 过期机制
- JSON 文件持久化
- 后台自动清理过期键
- 完整的类型注解和文档字符串

每个方法都考虑到了边界情况，比如获取不存在的键时返回默认值、并发安全、文件读写异常处理等。""".strip()

BIG_CODE_RESPONSE_2 = """好的，我来进一步扩展这个 KV 存储实现，添加更多企业级特性：

```python
import json
import threading
import time
import hashlib
from typing import Any, Callable, Optional
from collections import defaultdict


class AdvancedKVStore:
    \"\"\"Enhanced key-value store with namespaces, events, and metrics.\"\"\"

    def __init__(self, namespace: str = "default"):
        self._namespace = namespace
        self._data: dict[str, Any] = {}
        self._ttl: dict[str, float] = {}
        self._meta: dict[str, dict] = {}
        self._lock = threading.RLock()
        self._listeners: dict[str, list[Callable]] = defaultdict(list)
        self._metrics = {"sets": 0, "gets": 0, "deletes": 0, "evictions": 0}

    # ── Namespace support ──

    def _ns_key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    # ── Event system ──

    def on(self, event: str, callback: Callable) -> None:
        \"\"\"Register a listener for 'set', 'delete', or 'expire' events.\"\"\"
        self._listeners[event].append(callback)

    def _emit(self, event: str, key: str, value: Any = None) -> None:
        for cb in self._listeners.get(event, []):
            try:
                cb(key, value)
            except Exception:
                pass

    # ── Core operations ──

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            self._metrics["gets"] += 1
            nskey = self._ns_key(key)
            if nskey in self._ttl and time.time() > self._ttl[nskey]:
                del self._data[nskey]
                del self._ttl[nskey]
                self._metrics["evictions"] += 1
                self._emit("expire", key)
                return None
            return self._data.get(nskey)

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            self._metrics["sets"] += 1
            nskey = self._ns_key(key)
            self._data[nskey] = value
            if ttl is not None:
                self._ttl[nskey] = time.time() + ttl
            self._meta[nskey] = {
                "created_at": time.time(),
                "updated_at": time.time(),
                "size_bytes": len(json.dumps(value)),
            }
            self._emit("set", key, value)

    def delete(self, key: str) -> bool:
        with self._lock:
            nskey = self._ns_key(key)
            if nskey in self._data:
                self._metrics["deletes"] += 1
                del self._data[nskey]
                self._ttl.pop(nskey, None)
                self._meta.pop(nskey, None)
                self._emit("delete", key)
                return True
            return False

    # ── Batch operations ──

    def mget(self, *keys: str) -> list[Optional[Any]]:
        return [self.get(k) for k in keys]

    def mset(self, mapping: dict[str, Any], ttl: Optional[int] = None) -> None:
        for k, v in mapping.items():
            self.set(k, v, ttl=ttl)

    # ── Query / Search ──

    def search(self, query: str) -> list[dict]:
        \"\"\"Simple substring search across keys and values.\"\"\"
        results = []
        with self._lock:
            for nskey, value in self._data.items():
                key = nskey.split(":", 1)[1] if ":" in nskey else nskey
                if query.lower() in key.lower() or query.lower() in str(value).lower():
                    results.append({"key": key, "value": value, "meta": self._meta.get(nskey)})
        return results

    # ── Metrics ──

    def get_metrics(self) -> dict:
        with self._lock:
            return dict(self._metrics)

    def snapshot(self) -> dict:
        \"\"\"Return a point-in-time snapshot of all data.\"\"\"
        with self._lock:
            return {
                "namespace": self._namespace,
                "keys": len(self._data),
                "data": dict(self._data),
                "metrics": dict(self._metrics),
            }
```

这个高级版本增加了：
- **命名空间隔离** — 不同业务数据可以隔离存储
- **事件监听系统** — set/delete/expire 事件回调
- **批量操作** — mget/mset 提升性能
- **键值搜索** — 简单的全文搜索能力
- **运行指标** — 统计操作次数和缓存命中
- **元数据追踪** — 记录每个键的创建时间、更新时间、大小

这种设计模式适用于微服务架构中的本地缓存层，也适合作为 Redis 的轻量级替代方案进行原型开发。""".strip()

BIG_CODE_RESPONSE_3 = """好的！下面是完整的 pytest 测试套件：

```python
import pytest
import time
import json
import tempfile
from pathlib import Path
from kvstore import KVStore, BackgroundCleanup, AdvancedKVStore


class TestKVStore:
    \"\"\"Tests for the basic KVStore implementation.\"\"\"

    def test_set_and_get(self):
        store = KVStore()
        store.set("name", "Alice")
        assert store.get("name") == "Alice"

    def test_get_default(self):
        store = KVStore()
        assert store.get("nonexistent") is None
        assert store.get("nonexistent", 42) == 42

    def test_overwrite(self):
        store = KVStore()
        store.set("key", "value1")
        store.set("key", "value2")
        assert store.get("key") == "value2"

    def test_delete_existing(self):
        store = KVStore()
        store.set("key", "value")
        assert store.delete("key") is True
        assert store.get("key") is None

    def test_delete_nonexistent(self):
        store = KVStore()
        assert store.delete("nonexistent") is False

    def test_size(self):
        store = KVStore()
        assert store.size() == 0
        store.set("a", 1)
        store.set("b", 2)
        assert store.size() == 2
        store.delete("a")
        assert store.size() == 1

    def test_keys(self):
        store = KVStore()
        store.set("user:1", "Alice")
        store.set("user:2", "Bob")
        store.set("config:theme", "dark")
        users = store.keys("user:")
        assert len(users) == 2
        assert "user:1" in users

    def test_clear(self):
        store = KVStore()
        store.set("a", 1)
        store.set("b", 2)
        store.clear()
        assert store.size() == 0

    def test_ttl_expiry(self):
        store = KVStore()
        store.set("temp", "value", ttl_seconds=0.1)
        assert store.get("temp") == "value"
        time.sleep(0.2)
        assert store.get("temp") is None

    def test_ttl_not_expired(self):
        store = KVStore()
        store.set("temp", "value", ttl_seconds=10)
        assert store.get("temp") == "value"

    def test_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "store.json"
            store1 = KVStore(str(path))
            store1.set("key", "persistent-value")
            del store1

            store2 = KVStore(str(path))
            assert store2.get("key") == "persistent-value"

    def test_concurrent_access(self):
        import threading
        store = KVStore()
        errors = []

        def worker(n):
            try:
                for i in range(100):
                    store.set(f"k{n}_{i}", i)
                    assert store.get(f"k{n}_{i}") == i
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0
        assert store.size() == 1000

    def test_contains(self):
        store = KVStore()
        store.set("a", 1)
        assert "a" in store
        assert "b" not in store


class TestBackgroundCleanup:
    \"\"\"Tests for the background cleanup thread.\"\"\"

    def test_cleanup_evicts_expired(self):
        store = KVStore()
        store.set("expire_soon", "x", ttl_seconds=0.05)
        cleaner = BackgroundCleanup(store, interval=1)
        time.sleep(0.1)
        assert store.get("expire_soon") is None
        cleaner.stop()


class TestAdvancedKVStore:
    \"\"\"Tests for the advanced KV store features.\"\"\"

    def test_namespace_isolation(self):
        ns1 = AdvancedKVStore("users")
        ns2 = AdvancedKVStore("config")
        ns1.set("admin", "Alice")
        ns2.set("admin", "true")
        assert ns1.get("admin") == "Alice"
        assert ns2.get("admin") == "true"

    def test_event_listener(self):
        store = AdvancedKVStore()
        events = []
        store.on("set", lambda k, v: events.append(("set", k, v)))
        store.on("delete", lambda k, v: events.append(("del", k, v)))
        store.set("x", 1)
        store.delete("x")
        assert len(events) == 2
        assert events[0] == ("set", "x", 1)

    def test_batch_operations(self):
        store = AdvancedKVStore()
        store.mset({"a": 1, "b": 2, "c": 3})
        results = store.mget("a", "b", "c")
        assert results == [1, 2, 3]

    def test_search(self):
        store = AdvancedKVStore()
        store.set("user:alice", {"email": "alice@example.com"})
        store.set("user:bob", {"email": "bob@test.com"})
        results = store.search("alice")
        assert len(results) >= 1
        assert any("user:alice" in r["key"] for r in results)

    def test_metrics(self):
        store = AdvancedKVStore()
        store.set("a", 1)
        store.get("a")
        store.get("b")  # miss
        store.delete("a")
        metrics = store.get_metrics()
        assert metrics["sets"] >= 1
        assert metrics["gets"] >= 2
        assert metrics["deletes"] >= 1
```

测试覆盖了：
- 基本 CRUD 操作（get/set/delete）
- 边界条件（不存在键、默认值、覆盖写）
- TTL 过期机制（精确到 100ms 级别）
- JSON 文件持久化读写
- 并发安全性（10线程 × 100次操作）
- 事件监听系统
- 命名空间隔离
- 搜索功能和指标统计

运行方式：`pytest test_kvstore.py -v`""".strip()

CHAT_RESPONSES = [
    "你好！我是智能编程助手，可以帮你完成各种编码任务。请问你今天想解决什么问题？",
    "很高兴为你服务！我可以帮你写代码、调试 bug、做代码审查、设计架构，或者回答技术问题。请告诉我你的需求。",
    "你好！我是基于星火大模型的 AI 编程助手。你可以问我任何编程相关的问题，我会尽力帮你解决。",
    "嘿，我在呢！有什么需要帮忙的吗？从写一个函数到设计整个系统，我都可以协助你。",
    "欢迎！作为你的编程搭档，我可以帮你理解复杂代码、优化性能、编写测试，甚至学习新技术。开始吧！",
]

CHAT_RESPONSES_MAP = {
    "hi": "你好！我是智能编程助手，很高兴为你服务！有什么代码问题我可以帮你解决吗？",
    "hello": "Hello! I'm your AI programming assistant. How can I help you with your code today?",
    "你好": "你好！我是编程助手，可以帮你写代码、调试、审查等。请告诉我你想做什么！",
    "default": "好的，我理解了你的问题。让我来分析一下。\n\n从技术角度来看，这个问题涉及几个关键方面：\n1. 数据结构的选择\n2. 算法的复杂度分析\n3. 边界条件处理\n\n下面是我的方案："
}

CODING_TASKS = [
    # task description, code content
    ("LRU 缓存", """```python
from collections import OrderedDict
import threading

class LRUCache:
    def __init__(self, capacity: int = 128):
        self.cache = OrderedDict()
        self.capacity = capacity
        self.lock = threading.Lock()

    def get(self, key: str):
        with self.lock:
            if key not in self.cache:
                return -1
            self.cache.move_to_end(key)
            return self.cache[key]

    def put(self, key: str, value) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def __len__(self) -> int:
        return len(self.cache)

    def invalidate(self, pattern: str) -> int:
        with self.lock:
            before = len(self.cache)
            self.cache = OrderedDict(
                (k, v) for k, v in self.cache.items() if not k.startswith(pattern)
            )
            return before - len(self.cache)
```"""),
    ("线程池", """```python
import threading
import queue
import time
from typing import Callable

class ThreadPool:
    def __init__(self, num_workers: int = 4):
        self.tasks = queue.Queue()
        self.workers = []
        self._stop = threading.Event()
        for _ in range(num_workers):
            t = threading.Thread(target=self._worker, daemon=True)
            t.start()
            self.workers.append(t)

    def _worker(self):
        while not self._stop.is_set():
            try:
                fn, args, kwargs = self.tasks.get(timeout=1)
                try:
                    fn(*args, **kwargs)
                except Exception as e:
                    print(f"Task error: {e}")
            except queue.Empty:
                continue

    def submit(self, fn: Callable, *args, **kwargs):
        self.tasks.put((fn, args, kwargs))

    def shutdown(self, wait: bool = True):
        self._stop.set()
        if wait:
            for w in self.workers:
                w.join(timeout=5)
```"""),
    ("二分搜索", """```python
def binary_search(arr: list[int], target: int) -> int:
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = left + (right - left) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1

def lower_bound(arr: list[int], target: int) -> int:
    left, right = 0, len(arr)
    while left < right:
        mid = left + (right - left) // 2
        if arr[mid] < target:
            left = mid + 1
        else:
            right = mid
    return left

def upper_bound(arr: list[int], target: int) -> int:
    left, right = 0, len(arr)
    while left < right:
        mid = left + (right - left) // 2
        if arr[mid] <= target:
            left = mid + 1
        else:
            right = mid
    return left
""" + "\n\n# 测试\nassert binary_search([1,2,3,4,5], 3) == 2\nassert binary_search([1,2,3,4,5], 6) == -1\nassert lower_bound([1,2,2,2,3], 2) == 1\nassert upper_bound([1,2,2,2,3], 2) == 4"),
    ("速率限制器", """```python
import time
import threading
from collections import deque

class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window = window_seconds
        self.timestamps = deque()
        self.lock = threading.Lock()

    def allow(self) -> bool:
        now = time.time()
        with self.lock:
            while self.timestamps and now - self.timestamps[0] > self.window:
                self.timestamps.popleft()
            if len(self.timestamps) >= self.max_requests:
                return False
            self.timestamps.append(now)
            return True

    def wait_and_allow(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.allow():
                return True
            time.sleep(0.05)
        return False
""" + "\n\n# 测试：1秒内最多5次\nlimiter = RateLimiter(5, 1.0)\nfor i in range(10):\n    print(f\"Request {i}: {'✓' if limiter.allow() else '✗'}\")\n    time.sleep(0.1)"),
]


# ── SSE helpers ──

def _make_chunk(content: str, finish_reason: Optional[str] = None) -> str:
    choice = {"index": 0, "delta": {"content": content} if content else {}}
    if finish_reason:
        choice["finish_reason"] = finish_reason
    data = json.dumps({"choices": [choice]}, ensure_ascii=False)
    return f"data: {data}\n\n"


def _make_done() -> str:
    return "data: [DONE]\n\n"


# ── Token validation ──

@app.post("/api/starspark/v1/chat/user/valid")
async def validate_token(request: Request):
    body: dict = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    token = request.headers.get("token", "") or body.get("token", "")
    valid = token in _valid_tokens
    return {"resCode": "0" if valid else "1001"}


@app.post("/api/starspark/v1/agent/permission/queryUserFuncModelList")
async def list_models(request: Request):
    return {
        "resCode": "0",
        "obj": [
            {"modelCode": "4.0Ultra", "modelName": "星火 4.0 Ultra", "permissionCode": "INLINE_CHAT", "checked": True, "tokenExhausted": False, "language": "all"},
            {"modelCode": "max-32k", "modelName": "星火 Max-32K", "permissionCode": "INLINE_CHAT", "checked": True, "tokenExhausted": False, "language": "all"},
            {"modelCode": "generalv3.5", "modelName": "星火 Max", "permissionCode": "INLINE_CHAT", "checked": True, "tokenExhausted": False, "language": "all"},
            {"modelCode": "pro-128k", "modelName": "星火 Pro-128K", "permissionCode": "TALK_INTELLIGENT", "checked": True, "tokenExhausted": False, "language": "all"},
            {"modelCode": "generalv3", "modelName": "星火 Pro", "permissionCode": "TALK_INTELLIGENT", "checked": True, "tokenExhausted": False, "language": "all"},
            {"modelCode": "lite", "modelName": "星火 Lite", "permissionCode": "TALK_INTELLIGENT", "checked": True, "tokenExhausted": False, "language": "all"},
        ],
    }


# ── Content detection ──

_DETECTIONS = [
    ("quick_sort", "快排", "快速排序", "quick sort"),
    ("lru", "LRU", "缓存", "cache"),
    ("threadpool", "线程池", "thread pool", "ThreadPool"),
    ("binary_search", "二分", "binary search"),
    ("ratelimit", "速率限制", "rate limit", "RateLimiter"),
    ("kvstore", "kv", "key-value", "KVStore"),
    ("kvstore2", "AdvancedKV", "高级", "namespace"),
    ("test", "pytest", "test_", "单元测试"),
]

def _detect_task(message_text: str) -> Optional[str]:
    text = message_text.lower()
    for task_id, *keywords in _DETECTIONS:
        if any(kw.lower() in text for kw in keywords):
            return task_id
    return None

def _make_response(text: str, model_code: str, messages: list, cmd_type: str) -> tuple[list[str], bool]:
    """Return (chunks, has_tool_calls)"""
    # Find the last user message
    user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_msg = m.get("content", "")
            break

    # Detect task
    task = _detect_task(user_msg)

    if task == "quick_sort":
        code = BIG_CODE_RESPONSE
        chunks = [code]
    elif task == "kvstore2":
        code = BIG_CODE_RESPONSE_2
        chunks = [code]
    elif task in ("test",):
        code = BIG_CODE_RESPONSE_3
        chunks = [code]
    elif task in ("lru", "threadpool", "binary_search", "ratelimit"):
        for tname, code in CODING_TASKS:
            if task in tname.lower().replace(" ", ""):
                chunks = [code]
                break
        else:
            chunks = [BIG_CODE_RESPONSE]
    elif cmd_type == "INLINE_CHAT" or model_code.endswith("-coding"):
        chunks = [BIG_CODE_RESPONSE]
    else:
        import random
        reply = CHAT_RESPONSES_MAP.get(user_msg.strip().lower(), CHAT_RESPONSES_MAP["default"])
        chunks = [reply]

    return chunks, False


@app.post("/api/starspark/v1/agent/chat/async/ask")
async def chat_ask(request: Request):
    body: dict = await request.json()
    token = request.headers.get("token", "") or body.get("token", "")
    messages = body.get("messages", [])
    stream = body.get("stream", True)
    model_code = body.get("modelCode", "generalv3")
    cmd_type = body.get("commandType", "TALK_INTELLIGENT")

    if token not in _valid_tokens:
        return {"resCode": "1001", "message": "invalid token"}

    chunks, has_tools = _make_response("", model_code, messages, cmd_type)

    if not stream:
        full_text = "".join(chunks)
        return {"choices": [{"index": 0, "message": {"role": "assistant", "content": full_text}, "finish_reason": "stop"}]}

    async def _generate():
        try:
            for i, chunk in enumerate(chunks):
                is_last = i == len(chunks) - 1
                batch_size = 300
                for start in range(0, len(chunk), batch_size):
                    group = chunk[start:start+batch_size]
                    yield _make_chunk(group)
                    await asyncio.sleep(0.001)
                if is_last:
                    yield _make_chunk("", finish_reason="stop")
                    yield _make_done()
                else:
                    await asyncio.sleep(0.01)
        except Exception as e:
            log.error("Stream error: %s", e)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "close"},
    )


@app.get("/mock/ping")
async def ping():
    return {"status": "ok"}


@app.post("/mock/register-token")
async def register_token(request: Request):
    body = await request.json()
    token = body.get("token", "")
    if token:
        _valid_tokens.add(token)
        return {"ok": True}
    return {"ok": False}


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9000
    print(f"Mock upstream on http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")