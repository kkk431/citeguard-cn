import json

from fastapi.testclient import TestClient

import web.app as webapp
from citeguard import aggregate


def _report(score=80.0, grade="C", major=0, contradict=0, issues=None):
    return {
        "health": {
            "overall": score,
            "grade": grade,
            "confidence": 0.75,
            "dimensions": [
                {"key": "authenticity", "label": "真实性", "available": True, "score": 90},
                {"key": "support", "label": "支持度", "available": False, "score": None},
                {"key": "relevance", "label": "相关性", "available": True, "score": 75},
            ],
        },
        "stats": {
            "total": 10,
            "Exact": 6,
            "Minor": 3,
            "Unverified": 1,
            "Unknown": 0,
            "Major": major,
            "support": {"contradict": contradict, "partial": 0, "no_evidence": 0, "not_checked": 10},
        },
        "citations": {"coverage": {"uncited": [1, 2]}},
        "citation_consistency": {"missing_numbers": []},
        "references": [
            {"index": 1, "compliance": {"issues": issues or []}, "retraction": {"status": "clean"}},
        ],
    }


def _write_job(project, job_id, report):
    d = project / "jobs" / job_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")


def test_aggregate_computes_summary_and_ranking():
    data = aggregate.aggregate([
        ("a", "A.pdf", _report(90, "B", major=0)),
        ("b", "B.pdf", _report(70, "D", major=1, contradict=2,
                                issues=[{"level": "warning", "field": "volume", "message": "x"}])),
    ])
    assert data["summary"]["papers"] == 2
    assert data["summary"]["avg_health"] == 80.0
    assert data["summary"]["major"] == 1
    assert data["papers"][0]["job_id"] == "a"
    labels = [i["label"] for i in data["top_issues"]]
    assert any("Major" in label for label in labels)
    assert any("规范性：volume" in label for label in labels)
    assert any(d["key"] == "support" and d["average"] is None for d in data["dimensions"])


def test_aggregate_csv_has_rows():
    text = aggregate.to_csv(aggregate.aggregate([("a", "A.pdf", _report())]))
    assert "job_id" in text
    assert "A.pdf" in text


def test_aggregate_api_and_page(isolated_project):
    report_a = _report(90, "B", major=0)
    report_a["input"] = {"name": "A.pdf"}
    _write_job(isolated_project, "agga", report_a)
    _write_job(isolated_project, "aggb", _report(70, "D", major=1, contradict=1))
    dup_report = _report(60, "E")
    dup_report["input"] = {"name": "A.pdf"}
    _write_job(isolated_project, "aggdup", dup_report)
    client = TestClient(webapp.app)
    r = client.get("/api/aggregate?ids=agga,aggb,nope")
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["papers"] == 2
    assert data["missing"] == ["nope"]
    dup = client.get("/api/aggregate?ids=agga,aggdup").json()
    assert dup["summary"]["papers"] == 1
    assert dup["duplicates"] == ["aggdup"]
    assert "A" in client.get("/aggregate?ids=agga,aggb").text
    csv_resp = client.get("/api/aggregate.csv?ids=agga,aggb")
    assert csv_resp.status_code == 200
    assert csv_resp.content.startswith(b"\xef\xbb\xbf")
    assert "agga" in csv_resp.text
    assert client.get("/api/aggregate").status_code == 400
    assert client.get("/api/aggregate?ids=nope").status_code == 404
