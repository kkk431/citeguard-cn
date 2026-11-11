import json

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from citeguard.annotate import annotate_pdf, locate_page


def _pdf(tmp_path, pages):
    """Minimal text PDF without reportlab (CI only installs core deps)."""
    writer = PdfWriter()
    font = DictionaryObject(
        {NameObject("/Type"): NameObject("/Font"),
         NameObject("/Subtype"): NameObject("/Type1"),
         NameObject("/BaseFont"): NameObject("/Helvetica")}
    )
    for lines in pages:
        page = writer.add_blank_page(width=595, height=842)
        parts = []
        for line in lines:
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            parts.append(f"({safe}) Tj 0 -18 Td")
        stream = StreamObject()
        stream.set_data(("BT /F1 12 Tf 40 800 Td " + " ".join(parts) + " ET").encode("latin-1", "replace"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
    path = tmp_path / "in.pdf"
    writer.write(path)
    return path


def test_locate_page_title_and_index():
    pages = ["x", "References\n[1] Deep Learning. Nature 2015.", "more"]
    assert locate_page(pages, {"parsed": {"title": "Deep Learning"}}) == 1
    assert locate_page(pages, {"index": 1}) == 1
    assert locate_page(pages, {"parsed": {"title": "Nothing Here"}}) is None


def test_annotate_pins_note(tmp_path):
    src = _pdf(tmp_path, [["References", "page two"], ["[1] Deep Learning. Nature 2015."]])
    report = {"references": [{
        "index": 1,
        "parsed": {"title": "Deep Learning"},
        "verify": {"status": "Unverified"},
        "compliance": {"issues": [{"level": "warning", "field": "volume", "message": "建议补充卷"}]},
    }]}
    out = tmp_path / "out.pdf"
    stats = annotate_pdf(src, report, out)
    assert stats["annotated"] == 1 and stats["unmapped"] == 0
    reader = PdfReader(str(out))
    assert len(reader.pages) == 2
    annots = reader.pages[1].get("/Annots") or []
    assert len(annots) == 1


def test_annotate_counts_unmapped(tmp_path):
    src = _pdf(tmp_path, [["[1] Something Else"]])
    report = {"references": [{"index": 9, "parsed": {"title": "Missing Title"},
                              "verify": {"status": "Unverified"}, "compliance": {"issues": []}}]}
    stats = annotate_pdf(src, report, tmp_path / "out.pdf")
    assert stats["annotated"] == 0 and stats["unmapped"] == 1


def test_annotated_endpoint_serves_cached_copy(isolated_project):
    from fastapi.testclient import TestClient

    import web.app as webapp

    d = isolated_project / "jobs" / "annotjob"
    d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text("{}", encoding="utf-8")
    (d / "report.annotated.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    client = TestClient(webapp.app)
    r = client.get("/api/report/annotjob/annotated")
    assert r.status_code == 200
    assert r.headers["x-annotated"] == "0"
    assert client.get("/api/report/missing/annotated").status_code == 404


def test_reports_zip_bundles_several(isolated_project):
    import io
    import zipfile

    from fastapi.testclient import TestClient

    import web.app as webapp

    for job_id in ("batcha", "batchb"):
        d = isolated_project / "jobs" / job_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "report.json").write_text("{}", encoding="utf-8")
        (d / "report.html").write_text("<html></html>", encoding="utf-8")
        (d / "report.ris").write_text(f"TY  - JOUR\nTI  - {job_id}\nER  - \n", encoding="utf-8")
    client = TestClient(webapp.app)
    r = client.get("/api/reports/zip?ids=batcha,batchb,missing")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
    assert {"batcha/report.json", "batcha/report.html", "batchb/report.json", "all.ris"} <= names
    assert "manifest.json" in names
    assert client.get("/api/reports/zip?ids=").status_code == 400
    assert client.get("/api/reports/zip?ids=none").status_code == 404
