"""RIS / EndNote export mapping (used for NoteExpress, EndNote, Zotero)."""

from __future__ import annotations

from citeguard.exporters import ref_to_enw, ref_to_ris, refs_from_parsed, refs_to_enw, refs_to_ris
from citeguard.reference_parser import Reference


def _journal() -> Reference:
    return Reference(
        raw="[1] 张三, 李四. 中文引文核验方法[J]. 情报学报, 2024, 12(3): 10-20. DOI:10.1/x.",
        index=1,
        authors=["张三", "李四"],
        title="中文引文核验方法",
        doc_type="J",
        venue="情报学报",
        year=2024,
        volume="12",
        issue="3",
        pages="10-20",
        doi="10.1/x",
    )


def test_ris_journal_fields():
    text = ref_to_ris(_journal())
    assert text.startswith("TY  - JOUR")
    assert "AU  - 张三" in text and "AU  - 李四" in text
    assert "TI  - 中文引文核验方法" in text
    assert "JO  - 情报学报" in text
    assert "PY  - 2024" in text
    assert "VL  - 12" in text and "IS  - 3" in text
    assert "SP  - 10" in text and "EP  - 20" in text
    assert "DO  - 10.1/x" in text
    assert text.rstrip().endswith("ER  -")


def test_ris_maps_thesis_and_webpage_types():
    thesis = Reference(raw="[D] 某. 题名[D]. 北京: 某大学, 2020.", doc_type="D", title="题名", year=2020)
    assert ref_to_ris(thesis).startswith("TY  - THES")
    page = Reference(raw="[EB/OL] 某. 题名[EB/OL]. (2023)[2024-01-01].", doc_type="EB", title="题名")
    assert ref_to_ris(page).startswith("TY  - ELEC")


def test_ris_unknown_type_falls_back_to_generic():
    bare = Reference(raw="无标记的条目", title="无标记")
    assert ref_to_ris(bare).startswith("TY  - GEN")


def test_ris_fields_cannot_break_record_layout():
    ref = Reference(raw="x", title="第一行\n第二行", doc_type="J", venue="刊\n名")
    text = ref_to_ris(ref)
    assert "第一行 第二行" in text
    assert "刊 名" in text
    # Every line starts with a known tag: a balanced record needs exactly
    # one ER terminator and no embedded newline that would split a field.
    tags = {line[:2].strip() for line in text.splitlines() if line.strip()}
    assert tags <= {"TY", "TI", "AU", "JO", "T2", "PY", "VL", "IS", "SP", "EP", "PB", "CY", "DO", "UR", "SN", "M1", "Y2", "N1", "ER"}


def test_enw_has_bom_and_fields():
    text = refs_to_enw([_journal()])
    assert text.startswith("\ufeff%0 Journal Article")
    assert "%A 张三" in text and "%T 中文引文核验方法" in text
    assert "%R 10.1/x" in text


def test_ris_accepts_iterables():
    text = refs_to_ris([_journal(), _journal()])
    assert text.count("TY  - ") == 2 and text.count("ER  - ") == 2


def test_refs_from_parsed_roundtrip():
    ref = _journal()
    item = {"index": 1, "raw": ref.raw, "parsed": ref.to_dict()}
    rebuilt = refs_from_parsed([item])
    assert len(rebuilt) == 1
    assert rebuilt[0].title == ref.title
    assert rebuilt[0].authors == ref.authors
    assert rebuilt[0].doc_type == "J"
    assert refs_from_parsed([{"raw": "no parsed"}]) == []
