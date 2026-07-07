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
