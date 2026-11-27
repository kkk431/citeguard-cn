"""Human-machine consensus for CiteMap evidence cells.

The function is deliberately conservative: a cell is only promoted to
``accepted`` when all three reviewers agree it is correct.  A 2:1 majority is
``contested`` and stays in the review queue.  Machine candidates are never
promoted by their own confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

ACCEPTED = "accepted"
CONTESTED = "contested"
REJECTED = "rejected"
PENDING = "pending"
NO_EVIDENCE = "no_evidence"


@dataclass
class Consensus:
    status: str
    votes: tuple[str, ...]
    unanimous: bool

    def as_dict(self) -> dict:
        return {"status": self.status, "votes": list(self.votes), "unanimous": self.unanimous}


def _votes(row: Mapping) -> tuple[str, ...]:
    out = []
    for key in ("reviewer_1", "reviewer_2", "reviewer_3"):
        value = str(row.get(key) or "").strip().lower()
        if value:
            out.append(value)
    return tuple(out)


def consensus(row: Mapping) -> Consensus:
    votes = _votes(row)
    if not votes:
        return Consensus(PENDING, votes, False)
    correct = sum(1 for v in votes if v == "correct")
    issue = sum(1 for v in votes if v == "issue")
    if correct == len(votes):
        return Consensus(ACCEPTED, votes, True)
    if issue == len(votes):
        return Consensus(REJECTED, votes, True)
    return Consensus(CONTESTED, votes, False)


def summarize(rows: Iterable[Mapping]) -> dict:
    rows = list(rows)
    out = {
        "cells": len(rows),
        "machine_evidence": 0,
        "no_evidence": 0,
        "accepted": 0,
        "contested": 0,
        "rejected": 0,
        "pending": 0,
        "machine_accepted": 0,
        "machine_rejected": 0,
    }
    for row in rows:
        kind = row.get("cell_kind") or ""
        c = consensus(row)
        if kind == "机器证据":
            out["machine_evidence"] += 1
            if c.status == ACCEPTED:
                out["machine_accepted"] += 1
            elif c.status == REJECTED:
                out["machine_rejected"] += 1
        elif kind == "无机器证据":
            out["no_evidence"] += 1
        out[c.status] = out.get(c.status, 0) + 1
    return out


def accepted_edges(rows: Iterable[Mapping]) -> list[dict]:
    """Only unanimous-correct machine evidence is usable as an accepted edge."""
    out = []
    for row in rows:
        if row.get("cell_kind") != "机器证据":
            continue
        if consensus(row).status == ACCEPTED:
            out.append({"cell_id": row.get("cell_id"), "claim_id": row.get("claim_id"), "paper_id": row.get("paper_id")})
    return out
