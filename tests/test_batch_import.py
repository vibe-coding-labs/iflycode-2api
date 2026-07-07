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