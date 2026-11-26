from fastapi.testclient import TestClient

from web.app import app


def test_request_id_and_latency_headers():
    client = TestClient(app)
    resp = client.get("/api/health", headers={"X-Request-ID": "test-observe-1"})
    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "test-observe-1"
    assert int(resp.headers["x-response-time-ms"]) >= 0
    payload = resp.json()
    assert payload["uptime_seconds"] >= 0
    assert payload["requests_total"] >= 1


def test_metrics_counts_statuses():
    client = TestClient(app)
    health = client.get("/api/health")
    assert health.status_code == 200
    metrics = client.get("/api/metrics").json()
    assert metrics["ok"] is True
    assert metrics["version"]
    assert metrics["requests_total"] >= 2
    assert metrics["by_status"].get("200", 0) >= 2
