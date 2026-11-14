"""The checked-in SBOM must match requirements.txt and the app version."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SBOM = ROOT / "docs" / "sbom.json"


def test_sbom_is_current():
    result = subprocess.run(
        [sys.executable, "scripts/make_sbom.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr + result.stdout


def test_sbom_lists_every_core_dependency_with_a_version():
    data = json.loads(SBOM.read_text(encoding="utf-8"))
    assert data["bomFormat"] == "CycloneDX"
    assert data["specVersion"] == "1.5"
    components = {item["name"].lower(): item for item in data["components"]}
    requirements = [
        re.split(r"[<>=!~;\[ ]", line.split("#", 1)[0].strip(), maxsplit=1)[0].lower()
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.split("#", 1)[0].strip()
    ]
    for name in requirements:
        component = components.get(name)
        if component is None:
            component = next((item for key, item in components.items() if key.replace("-", "_") == name.replace("-", "_")), None)
        assert component is not None, f"{name} missing from SBOM"
        assert component["version"], f"{name} has no version"
        assert component["licenses"], f"{name} has no license entry"


def test_sbom_records_the_application_version():
    data = json.loads(SBOM.read_text(encoding="utf-8"))
    app = (ROOT / "web" / "app.py").read_text(encoding="utf-8")
    version = re.search(r'FastAPI\([^)]*version="([^"]+)"', app).group(1)
    assert data["metadata"]["component"]["version"] == version
