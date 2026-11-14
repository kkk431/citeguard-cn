"""Build a CycloneDX-style SBOM for the core runtime dependencies.

The SBOM is intentionally small: it lists the Python distributions that the
server imports at runtime (``requirements.txt``), not every transitive wheel
that happens to be installed in a developer virtualenv.  Run with ``--check``
to fail when a core dependency is missing from the generated file.
"""
from __future__ import annotations

import argparse
import importlib.metadata as md
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
APP = ROOT / "web" / "app.py"
DEFAULT_OUT = ROOT / "docs" / "sbom.json"

_LICENSE_CLASSIFIERS = {
    "MIT License": "MIT",
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "ISC License (ISCL)": "ISC",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
}


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def core_dependencies() -> list[str]:
    names: list[str] = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        name = re.split(r"[<>=!~;\[ ]", line, maxsplit=1)[0].strip()
        if name:
            names.append(_normalise(name))
    return names


def app_version() -> str:
    text = APP.read_text(encoding="utf-8")
    match = re.search(r'FastAPI\([^)]*version="([^"]+)"', text)
    if not match:
        raise SystemExit("cannot find the FastAPI version in web/app.py")
    return match.group(1)


def _license_id(meta: md.PackageMetadata) -> str:
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    for classifier in meta.get_all("Classifier") or []:
        if classifier.startswith("License :: OSI Approved ::"):
            leaf = classifier.rsplit("::", 1)[-1].strip()
            return _LICENSE_CLASSIFIERS.get(leaf, leaf)
    field = (meta.get("License") or "").strip()
    if field and field.upper() != "UNKNOWN" and len(field) <= 80:
        return field
    return "NOASSERTION"


def build() -> dict:
    components = []
    for name in core_dependencies():
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            raise SystemExit(f"core dependency not installed: {name}")
        meta = dist.metadata
        version = dist.version
        components.append(
            {
                "type": "library",
                "name": meta.get("Name") or name,
                "version": version,
                "purl": f"pkg:pypi/{_normalise(meta.get('Name') or name)}@{version}",
                "licenses": [{"license": {"id": _license_id(meta)}}],
            }
        )
    components.sort(key=lambda item: item["name"].lower())
    version = app_version()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "component": {
                "type": "application",
                "name": "citeguard-cn",
                "version": version,
                "licenses": [{"license": {"id": "Apache-2.0"}}],
            },
            "tools": [{"name": "make_sbom.py", "version": version}],
        },
        "components": components,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate or check docs/sbom.json")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true", help="verify the checked-in SBOM matches requirements")
    args = parser.parse_args(argv)

    data = build()
    if args.check:
        if not args.out.exists():
            print(f"missing SBOM: {args.out}", file=sys.stderr)
            return 1
        current = json.loads(args.out.read_text(encoding="utf-8"))
        expected = {item["name"] for item in data["components"]}
        actual = {item.get("name") for item in current.get("components", [])}
        missing = sorted(expected - actual)
        if missing:
            print(f"SBOM is missing core dependencies: {', '.join(missing)}", file=sys.stderr)
            return 1
        if current.get("metadata", {}).get("component", {}).get("version") != data["metadata"]["component"]["version"]:
            print("SBOM application version is stale", file=sys.stderr)
            return 1
        print(f"SBOM OK: {len(actual)} components, app {data['metadata']['component']['version']}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out} ({len(data['components'])} components)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
