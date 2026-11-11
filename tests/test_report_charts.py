"""报告图表数据测试。"""

from citeguard.report_charts import build_charts


def _report():
    return {
        "stats": {
            "total": 4,
            "Exact": 2, "Minor": 1, "Major": 0, "Unverified": 1, "Unknown": 0,
            "support": {"support": 1, "partial": 1, "contradict": 0,
                        "no_evidence": 0, "not_checked": 2},
        },
        "references": [
            {"compliance": {"issues": [
                {"level": "warning", "field": "doi", "message": "x"},
                {"level": "info", "field": "pages", "message": "y"},
            ]}},
            {"compliance": {"issues": [
                {"level": "error", "field": "doi", "message": "z"},
                {"level": "warning", "field": "authors", "message": "w"},
            ]}},
        ],
    }


def test_status_chart_rows_and_percentages():
    charts = build_charts(_report())
    status = charts[0]
    assert status["id"] == "status"
    assert status["total"] == 4
    rows = {r["key"]: r for r in status["rows"]}
    assert rows["Exact"]["value"] == 2
    assert rows["Exact"]["pct"] == 50.0
    assert round(sum(r["pct"] for r in status["rows"]), 1) == 100.0


def test_support_chart_includes_not_checked():
    charts = build_charts(_report())
    support = charts[1]
    assert support["id"] == "support"
    labels = {r["key"]: r["value"] for r in support["rows"]}
    assert labels["support"] == 1
    assert labels["not_checked"] == 2


def test_compliance_chart_ignores_info_and_sorts():
    charts = build_charts(_report())
    comp = charts[2]
    assert comp["id"] == "compliance"
    keys = [r["key"] for r in comp["rows"]]
    assert keys[0] == "doi"  # 2 条 warning/error
    assert "pages" not in keys  # info 不计入
    assert comp["total"] == 3


def test_empty_report_does_not_crash():
    charts = build_charts({"stats": {}, "references": []})
    assert len(charts) == 3
    assert charts[0]["total"] == 0
    assert all(r["pct"] == 0.0 for r in charts[0]["rows"])
