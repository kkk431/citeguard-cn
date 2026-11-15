"""Contract tests for the 48h CiteMap paper/claim/evidence graph spike."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from citeguard.evidence_map import (
    DEFAULT_DATA_DIR,
    GRAPH_EDGE_KINDS,
    GRAPH_LEVELS,
    GRAPH_NODE_TYPES,
    build_graph,
    write_graph,
)

TOPICS = ("ai_education", "medical_imaging")


@pytest.fixture(scope="module")
def graphs() -> dict[str, dict]:
    return {topic: build_graph(topic) for topic in TOPICS}


def _node_index(graph: dict) -> dict[str, dict]:
    return {node["id"]: node for node in graph["nodes"]}


def test_graph_shape_and_serializability(graphs: dict[str, dict]) -> None:
    for topic, graph in graphs.items():
        assert graph["schema_version"] == "1.0"
        assert graph["topic_id"] == topic
        assert graph["topic"]["topic_id"] == topic
        assert isinstance(graph["nodes"], list) and graph["nodes"]
        assert isinstance(graph["edges"], list) and graph["edges"]
        assert isinstance(graph["summary"], dict)
        json.dumps(graph, ensure_ascii=False)


def test_graph_has_no_dangling_references(graphs: dict[str, dict]) -> None:
    for graph in graphs.values():
        nodes = _node_index(graph)
        assert len(nodes) == len(graph["nodes"]), "节点 id 必须唯一"
        assert len({edge["id"] for edge in graph["edges"]}) == len(graph["edges"])
        for node in graph["nodes"]:
            assert node["type"] in GRAPH_NODE_TYPES
            assert node["label"].strip()
            assert isinstance(node["meta"], dict)
        for edge in graph["edges"]:
            assert edge["source"] in nodes
            assert edge["target"] in nodes
            assert nodes[edge["source"]]["type"] == "paper"
            assert nodes[edge["target"]]["type"] == "claim"
            assert edge["kind"] in GRAPH_EDGE_KINDS
            assert edge["level"] in GRAPH_LEVELS


def test_graph_summary_matches_nodes_and_edges(graphs: dict[str, dict]) -> None:
    for graph in graphs.values():
        summary = graph["summary"]
        nodes = graph["nodes"]
        edges = graph["edges"]
        assert summary["papers"] == sum(1 for n in nodes if n["type"] == "paper") == 15
        assert summary["claims"] == sum(1 for n in nodes if n["type"] == "claim")
        assert summary["evidence"] == sum(1 for n in nodes if n["type"] == "evidence")
        assert summary["edges"] == len(edges)
        assert summary["fulltext_edges"] == sum(
            1 for edge in edges if edge["level"] == "fulltext"
        )
        assert summary["abstract_edges"] == sum(
            1 for edge in edges if edge["level"] == "abstract"
        )
        assert summary["none_edges"] == sum(
            1 for edge in edges if edge["kind"] == "none"
        )
        assert summary["machine_edges"] == sum(
            1 for edge in edges if edge["level"] == "machine"
        )


def test_two_topics_have_30_papers_28_claim_nodes_and_21_atomic_claims(
    graphs: dict[str, dict],
) -> None:
    total_papers = sum(g["summary"]["papers"] for g in graphs.values())
    total_claims = sum(g["summary"]["claims"] for g in graphs.values())
    total_atomic = sum(g["summary"]["atomic_claims"] for g in graphs.values())
    total_parent = sum(g["summary"]["parent_claims"] for g in graphs.values())
    assert total_papers == 30
    assert total_atomic == 21
    assert total_parent == 7
    assert total_claims == 28  # 7 parent + 21 atomic


def test_every_topic_has_fulltext_and_none_edges(graphs: dict[str, dict]) -> None:
    for graph in graphs.values():
        assert graph["summary"]["fulltext_edges"] > 0
        assert graph["summary"]["none_edges"] > 0
        levels = {edge["level"] for edge in graph["edges"]}
        assert {"fulltext", "machine"} <= levels


def test_fulltext_edges_are_grounded(graphs: dict[str, dict]) -> None:
    for graph in graphs.values():
        nodes = _node_index(graph)
        for edge in graph["edges"]:
            if edge["level"] != "fulltext":
                continue
            assert edge["kind"] in {"supports", "contradicts", "abstract_only"}
            assert edge["evidence_id"]
            assert edge["quote"].strip()
            assert nodes[edge["evidence_id"]]["type"] == "evidence"
            assert nodes[edge["evidence_id"]]["meta"]["level"] == "fulltext"


def test_abstract_edges_never_claim_fulltext(graphs: dict[str, dict]) -> None:
    for graph in graphs.values():
        nodes = _node_index(graph)
        for edge in graph["edges"]:
            if edge["level"] != "abstract":
                continue
            assert edge["kind"] == "abstract_only"
            assert edge["evidence_id"]
            assert edge["quote"].strip()
            assert nodes[edge["evidence_id"]]["meta"]["level"] == "abstract"


def test_none_edges_have_no_fabricated_evidence(graphs: dict[str, dict]) -> None:
    for graph in graphs.values():
        for edge in graph["edges"]:
            if edge["kind"] != "none":
                continue
            assert edge["level"] == "machine"
            assert edge["evidence_id"] == ""
            assert edge["quote"] == ""
            assert edge["locator"] == ""


def test_audit_grid_has_all_105_cells(graphs: dict[str, dict]) -> None:
    total_cells = sum(g["summary"]["cells"] for g in graphs.values())
    total_fulltext = sum(g["summary"]["cells_fulltext"] for g in graphs.values())
    total_abstract = sum(
        g["summary"]["cells_abstract_only"] for g in graphs.values()
    )
    total_none = sum(g["summary"]["cells_none"] for g in graphs.values())
    assert total_cells == 105
    assert total_fulltext == 16
    assert total_abstract + total_none == 89
    assert total_none == 87

    for graph in graphs.values():
        cell_edges = [
            edge
            for edge in graph["edges"]
            if edge["meta"].get("edge_scope") == "cell"
        ]
        assert len(cell_edges) == graph["summary"]["cells"]
        assert len({edge["meta"]["cell_id"] for edge in cell_edges}) == len(
            cell_edges
        )
        for edge in cell_edges:
            assert edge["target"] in {f"med-c{i}" for i in range(1, 4)} | {
                f"edu-c{i}" for i in range(1, 5)
            }


def test_machine_issue_cells_are_not_promoted_to_evidence(
    graphs: dict[str, dict],
) -> None:
    for graph in graphs.values():
        for edge in graph["edges"]:
            meta = edge["meta"]
            if meta.get("audit_majority") != "issue":
                continue
            # A fulltext extraction can independently support the parent cell;
            # that is not the rejected machine evidence.  Everything below
            # fulltext must not smuggle the machine quote into the graph.
            if edge["level"] == "fulltext":
                continue
            assert edge["kind"] == "none"
            assert edge["evidence_id"] == ""
            assert edge["quote"] == ""


def test_known_machine_correct_cells_are_abstract_only_when_present(
    graphs: dict[str, dict],
) -> None:
    key = (
        DEFAULT_DATA_DIR.parents[1]
        / "dist"
        / "citemap_audit_full"
        / "_organizer_only_key.csv"
    )
    if not key.is_file():
        pytest.skip("105-cell organizer key is not present in this checkout")
    total_abstract = sum(
        g["summary"]["cells_abstract_only"] for g in graphs.values()
    )
    assert total_abstract == 2


def test_write_graph_round_trips(
    graphs: dict[str, dict], tmp_path: Path
) -> None:
    path = write_graph("ai_education", DEFAULT_DATA_DIR, tmp_path)
    assert path == tmp_path / "ai_education.json"
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["summary"] == graphs["ai_education"]["summary"]
    assert loaded["nodes"] == graphs["ai_education"]["nodes"]
    assert loaded["edges"] == graphs["ai_education"]["edges"]
