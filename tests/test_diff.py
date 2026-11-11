"""复检 diff 测试。"""

import json

from fastapi.testclient import TestClient

from citeguard.diff import diff_reports


def _ref(index, title, status="Exact", score=100, issues=None, support="support"):
    return {
        "index": index,
        "parsed": {"title": title},
        "verify": {"status": status},
        "compliance": {"score": score, "issues": issues or []},
        "support": {"label": support},
    }


def _warn(field="doi", message="建议补充永久标识符"):
    return {"level": "warning", "field": field, "message": message}


def test_resolved_when_issue_gone_and_exact():
    old = {"references": [_ref(1, "A", "Minor", 95, [_warn()])]}
    new = {"references": [_ref(1, "A", "Exact", 100, [])]}
    d = diff_reports(old, new)
    assert d["summary"]["resolved"] == 1
    assert d["items"][0]["kind"] == "resolved"
    assert d["items"][0]["fixed"][0]["field"] == "doi"


def test_still_and_new_issues():
    old = {"references": [_ref(1, "A", "Exact", 95, [_warn("doi")])]}
    new = {"references": [_ref(1, "A", "Exact", 95, [_warn("doi"), _warn("pages", "页码缺")])]}
    d = diff_reports(old, new)
    item = d["items"][0]
    assert item["kind"] == "new"
    assert [x["field"] for x in item["still"]] == ["doi"]
    assert [x["field"] for x in item["new"]] == ["pages"]


def test_status_change_only():
    old = {"references": [_ref(1, "A", "Unverified", 100, [])]}
    new = {"references": [_ref(1, "A", "Exact", 100, [])]}
    d = diff_reports(old, new)
    assert d["summary"]["status_changed"] == 1
    assert d["items"][0]["kind"] == "status"


def test_title_fallback_when_index_missing():
    old = {"references": [{"index": 7, "parsed": {"title": "Deep Learning"},
                           "verify": {"status": "Unverified"},
                           "compliance": {"score": 100, "issues": []}}]}
    new = {"references": [{"index": 1, "parsed": {"title": "Deep Learning!"},
                           "verify": {"status": "Exact"}, "compliance": {"score": 100, "issues": []}}]}
    d = diff_reports(old, new)
    assert d["summary"]["status_changed"] == 1
    assert d["items"][0]["status"] == {"old": "Unverified", "new": "Exact"}


def test_web_diff_endpoint(isolated_project):
    import web.app as webapp

    for jid, rep in {
        "oldjob": {"references": [_ref(1, "A", "Minor", 95, [_warn()])]},
        "newjob": {"references": [_ref(1, "A", "Exact", 100, [])]},
    }.items():
        d = isolated_project / "jobs" / jid
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text(json.dumps(rep), encoding="utf-8")

    client = TestClient(webapp.app)
    r = client.get("/api/report/newjob/diff?against=oldjob")
    assert r.status_code == 200
    assert r.json()["summary"]["resolved"] == 1
    assert client.get("/api/report/newjob/diff").status_code == 400
    assert client.get("/api/report/newjob/diff?against=nope").status_code == 404


def test_web_jobs_endpoint(isolated_project):
    import web.app as webapp

    d = isolated_project / "jobs" / "jobx"
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text("{}", encoding="utf-8")
    (isolated_project / "jobs" / "jobx.json").write_text(
        json.dumps({"id": "jobx", "name": "paper.pdf", "status": "done",
                    "created_at": "2026-11-11T19:00:00", "progress": 100}),
        encoding="utf-8",
    )
    client = TestClient(webapp.app)
    r = client.get("/api/jobs?limit=5")
    assert r.status_code == 200
    jobs = {j["id"]: j for j in r.json()["jobs"]}
    assert jobs["jobx"]["has_report"] is True
    assert jobs["jobx"]["name"] == "paper.pdf"
