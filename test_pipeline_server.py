"""Smoke test for pipeline_server.py — run while server is on port 9090."""
import httpx, json, sys

BASE = "http://127.0.0.1:9090"

def test(name, fn):
    try:
        fn()
        print(f"  [PASS] {name}")
        return True
    except Exception as e:
        print(f"  [FAIL] {name}: {e}")
        return False

def test_health():
    r = httpx.get(f"{BASE}/health", timeout=5)
    assert r.status_code == 200
    h = r.json()
    assert h["status"] in ("ok", "degraded")

def test_models():
    r = httpx.get(f"{BASE}/v1/models", timeout=5)
    ids = [d["id"] for d in r.json()["data"]]
    assert ids == ["foundry-monitor", "foundry-dag", "foundry-manifest"]

def test_pipelines():
    r = httpx.get(f"{BASE}/pipelines", timeout=5)
    ids = [p["id"] for p in r.json()["data"]]
    assert ids == ["foundry-monitor", "foundry-dag", "foundry-manifest"]

def test_inlet_dashboard():
    r = httpx.post(f"{BASE}/pipeline/inlet", json={
        "user_message": "show dashboard",
        "messages": [{"role": "user", "content": "show dashboard"}],
    }, timeout=15)
    d = r.json()
    assert d["pass_through"] is False
    assert d["pipeline"] == "dashboard"
    assert "Foundry Manager Dashboard" in d["messages"][0]["content"]

def test_inlet_dag():
    r = httpx.post(f"{BASE}/pipeline/inlet", json={
        "user_message": "/dag",
        "messages": [{"role": "user", "content": "/dag"}],
    }, timeout=15)
    d = r.json()
    assert d["pass_through"] is False
    assert d["pipeline"] == "dag"
    assert "```mermaid" in d["messages"][0]["content"]

def test_inlet_manifest():
    r = httpx.post(f"{BASE}/pipeline/inlet", json={
        "user_message": "/manifest",
        "messages": [{"role": "user", "content": "/manifest"}],
    }, timeout=15)
    d = r.json()
    assert d["pass_through"] is False
    assert d["pipeline"] == "manifest"
    assert "Foundry Manifest" in d["messages"][0]["content"]

def test_inlet_passthrough():
    r = httpx.post(f"{BASE}/pipeline/inlet", json={
        "user_message": "hello world",
        "messages": [{"role": "user", "content": "hello world"}],
    }, timeout=10)
    assert r.json()["pass_through"] is True

def test_owui_filter():
    r = httpx.post(f"{BASE}/foundry-monitor/filter/inlet", json={
        "user": {"id": "t", "name": "t"},
        "body": {"messages": [{"role": "user", "content": "system status"}], "model": "x"},
    }, timeout=15)
    d = r.json()
    assert len(d["messages"]) == 2
    assert d["messages"][-1]["role"] == "system"

def test_owui_filter_passthrough():
    r = httpx.post(f"{BASE}/foundry-dag/filter/inlet", json={
        "user": {"id": "t", "name": "t"},
        "body": {"messages": [{"role": "user", "content": "hi"}], "model": "x"},
    }, timeout=10)
    assert len(r.json()["messages"]) == 1

def test_upload():
    r = httpx.post(f"{BASE}/pipelines/upload",
                   files={"file": ("test.py", b"print(1)", "text/x-python")}, timeout=10)
    assert r.json() == {"id": "test", "status": "uploaded"}

if __name__ == "__main__":
    results = [
        test("health", test_health),
        test("/v1/models", test_models),
        test("/pipelines", test_pipelines),
        test("inlet dashboard", test_inlet_dashboard),
        test("inlet dag", test_inlet_dag),
        test("inlet manifest", test_inlet_manifest),
        test("inlet pass-through", test_inlet_passthrough),
        test("OWUI filter inlet", test_owui_filter),
        test("OWUI filter pass-through", test_owui_filter_passthrough),
        test("upload", test_upload),
    ]
    passed = sum(results)
    print(f"\n{'='*50}\n  {passed}/{len(results)} PASSED\n{'='*50}")
    sys.exit(0 if passed == len(results) else 1)
