"""Fetch open-access full text for the static CiteMap topics.

Stores plain text under ``data/evidence_map/fulltext/<paper_id>.txt`` and a
manifest with URL/status/size. PDFs are downloaded to a temp file, parsed with
the project extractor, then deleted so the repository keeps only text.
"""
from __future__ import annotations

import argparse
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from citeguard.pdf_extract import extract_text

ROOT = Path(__file__).resolve().parents[1]
MAP_DIR = ROOT / "data" / "evidence_map"
TOPICS = ("ai_education", "medical_imaging")
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36 CiteGuard/1.7.25"
)


def load_papers(topic: str) -> list[dict]:
    data = json.loads((MAP_DIR / "corpus" / f"{topic}.json").read_text(encoding="utf-8"))
    return list(data.get("papers") or [])


def download(url: str, target: Path, timeout: float = 45.0) -> bool:
    try:
        with requests.get(url, headers={"User-Agent": UA}, timeout=timeout, stream=True) as resp:
            if resp.status_code != 200:
                return False
            ctype = (resp.headers.get("content-type") or "").lower()
            if "pdf" not in ctype and not url.lower().endswith(".pdf"):
                return False
            with target.open("wb") as fh:
                for chunk in resp.iter_content(64 * 1024):
                    if chunk:
                        fh.write(chunk)
        return target.stat().st_size > 10_000
    except Exception:
        return False


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def jats_text(xml_bytes: bytes) -> str:
    root = ET.fromstring(xml_bytes)
    parent = {child: node for node in root.iter() for child in node}
    parts: list[str] = []
    seen: set[str] = set()
    for node in root.iter():
        name = _local(node.tag)
        if name == "ref-list":
            continue
        if name not in {"article-title", "title", "p", "caption"}:
            continue
        ancestor = parent.get(node)
        skip = False
        while ancestor is not None:
            if _local(ancestor.tag) in {"ref-list", "back"}:
                skip = True
                break
            ancestor = parent.get(ancestor)
        if skip:
            continue
        text = " ".join("".join(node.itertext()).split())
        if len(text) < 20 or text in seen:
            continue
        seen.add(text)
        parts.append(text)
    return "\n".join(parts)


def europepmc_text(doi: str) -> tuple[str, str] | None:
    if not doi:
        return None
    try:
        resp = requests.get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={"query": f'DOI:"{doi}"', "format": "json", "pageSize": 1},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        rows = resp.json().get("resultList", {}).get("result", [])
        if not rows:
            return None
        pmcid = rows[0].get("pmcid") or ""
        if not pmcid:
            return None
        full = requests.get(
            f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML",
            timeout=45,
        )
        if full.status_code != 200 or len(full.content) < 5000:
            return None
        text = jats_text(full.content)
        if len(text) < 2000:
            return None
        return text, pmcid
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", action="append", choices=TOPICS)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    topics = args.topic or list(TOPICS)
    outdir = ROOT / "data" / "cache" / "citemap_fulltext"
    outdir.mkdir(parents=True, exist_ok=True)
    manifest_path = outdir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    for topic in topics:
        for paper in load_papers(topic):
            pid = paper["paper_id"]
            text_path = outdir / f"{pid}.txt"
            old = manifest.get(pid, {})
            if text_path.exists() and not args.force:
                print(f"[skip] {pid} ({old.get('status', 'existing')})")
                continue
            url = paper.get("oa_url") or paper.get("url") or ""
            if not url:
                manifest[pid] = {"status": "no_url", "topic": topic}
                continue
            tmp = outdir / f"_{pid}.pdf"
            ok = download(url, tmp)
            if not ok:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
                fallback = europepmc_text(paper.get("doi") or "")
                if fallback:
                    text, pmcid = fallback
                    text_path.write_text(text, encoding="utf-8")
                    manifest[pid] = {
                        "status": "ok",
                        "source": "europepmc",
                        "pmcid": pmcid,
                        "doi": paper.get("doi") or "",
                        "url": f"https://europepmc.org/articles/{pmcid}",
                        "topic": topic,
                        "chars": len(text),
                        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    }
                    print(f"[ok:pmc] {pid} {pmcid} {len(text)} chars")
                    time.sleep(0.4)
                    continue
                manifest[pid] = {"status": "download_failed", "url": url, "topic": topic}
                print(f"[fail] {pid} {url[:80]}")
                time.sleep(0.8)
                continue
            try:
                text = extract_text(tmp)
            except Exception as exc:  # noqa: BLE001
                manifest[pid] = {"status": "parse_failed", "url": url, "topic": topic, "error": str(exc)[:200]}
                text = ""
            tmp.unlink(missing_ok=True)
            if len(text.strip()) < 2000:
                manifest[pid] = {"status": "too_short", "url": url, "topic": topic, "chars": len(text)}
                print(f"[short] {pid} {len(text)}")
                time.sleep(0.8)
                continue
            text_path.write_text(text, encoding="utf-8")
            manifest[pid] = {
                "status": "ok",
                "url": url,
                "topic": topic,
                "chars": len(text),
                "sentences": text.count(".") + text.count("。"),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            print(f"[ok] {pid} {len(text)} chars")
            time.sleep(0.8)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = sum(1 for v in manifest.values() if v.get("status") == "ok")
    print(f"manifest: {len(manifest)} papers, {ok} full texts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
