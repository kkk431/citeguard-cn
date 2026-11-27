import csv
from pathlib import Path

from citeguard.evidence_consensus import accepted_edges, consensus, summarize


def _row(votes, kind="机器证据"):
    return {"cell_id": "c1", "claim_id": "q1", "paper_id": "p1", "cell_kind": kind,
            "reviewer_1": votes[0], "reviewer_2": votes[1], "reviewer_3": votes[2]}


def test_unanimous_correct_is_accepted():
    c = consensus(_row(("correct", "correct", "correct")))
    assert c.status == "accepted" and c.unanimous


def test_two_to_one_is_contested():
    assert consensus(_row(("correct", "correct", "issue"))).status == "contested"


def test_unanimous_issue_is_rejected():
    assert consensus(_row(("issue", "issue", "issue"))).status == "rejected"


def test_only_unanimous_machine_evidence_becomes_accepted_edge():
    rows = [
        _row(("correct", "correct", "correct")),
        _row(("correct", "correct", "issue")),
        _row(("correct", "correct", "correct"), kind="无机器证据"),
    ]
    edges = accepted_edges(rows)
    assert len(edges) == 1
    summary = summarize(rows)
    assert summary["accepted"] == 2
    assert summary["contested"] == 1
    assert summary["machine_accepted"] == 1
