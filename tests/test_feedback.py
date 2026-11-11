"""判错反馈队列测试。"""

import pytest
from fastapi.testclient import TestClient

from citeguard import feedback as fb


def test_record_and_load(tmp_path):
    p = tmp_path / "feedback.jsonl"
    item = fb.record_feedback(
        {"job_id": "j1", "ref_index": 2, "claim": "该方法更优",
         "predicted": "support", "corrected": "partial", "reason": "证据只覆盖一半"},
        path=p,
    )
    assert item["ref_index"] == 2
    assert item["predicted"] == "support"
    assert item["job_id"] == "j1"
    items = fb.load_feedback(p)
    assert len(items) == 1
    assert items[0]["corrected"] == "partial"
    summary = fb.summarize_feedback(items)
    assert summary["total"] == 1
    assert summary["jobs"] == 1
    assert summary["corrections"] == {"partial": 1}


def test_invalid_label_rejected(tmp_path):
    with pytest.raises(ValueError):
        fb.record_feedback({"predicted": "nope"}, path=tmp_path / "x.jsonl")


def test_corrected_is_optional(tmp_path):
    item = fb.record_feedback({"predicted": "no_evidence"}, path=tmp_path / "x.jsonl")
    assert item["corrected"] is None
    assert item["claim"] == ""


def test_web_feedback_endpoint(isolated_project):
    import web.app as webapp

    client = TestClient(webapp.app)
    resp = client.post("/api/feedback", json={
        "job_id": "job-x", "ref_index": 3, "claim": "引用句",
        "predicted": "support", "corrected": "partial", "reason": "缺条件",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["item"]["corrected"] == "partial"
    path = isolated_project / "feedback" / "feedback.jsonl"
    assert path.exists()


def test_web_feedback_rejects_bad_label(isolated_project):
    import web.app as webapp

    client = TestClient(webapp.app)
    resp = client.post("/api/feedback", json={"predicted": "wrong"})
    assert resp.status_code == 400
