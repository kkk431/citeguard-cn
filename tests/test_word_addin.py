import xml.etree.ElementTree as ET
from pathlib import Path

NS = {"o": "http://schemas.microsoft.com/office/appforoffice/1.1"}

def test_manifest_is_valid_task_pane():
    root = ET.parse("word-addin/manifest.xml").getroot()
    assert root.tag.endswith("OfficeApp")
    assert root.get("{http://www.w3.org/2001/XMLSchema-instance}type") == "TaskPaneApp"
    display = root.find("o:DisplayName", NS).get("DefaultValue")
    assert display.startswith("引证卫士")
    assert root.findtext("o:Permissions", namespaces=NS) == "ReadDocument"
    src = root.find("o:DefaultSettings/o:SourceLocation", NS).get("DefaultValue")
    assert src.endswith("/word/taskpane")

def test_taskpane_loads_office_and_calls_check_api():
    html = Path("web/templates/word_taskpane.html").read_text(encoding="utf-8")
    js = Path("web/static/js/word_taskpane.js").read_text(encoding="utf-8")
    assert "appsforoffice.microsoft.com/lib/1/hosted/office.js" in html
    assert "/static/js/word_taskpane.js" in html
    assert 'fetch("/api/support/check"' in js
    assert "getSelectedDataAsync" in js

def test_word_route_registered():
    src = Path("web/app.py").read_text(encoding="utf-8")
    assert '@app.get("/word/taskpane"' in src
