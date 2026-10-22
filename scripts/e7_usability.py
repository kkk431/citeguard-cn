"""E7: internal usability self-test of the CiteGuard-CN web workbench.

IMPORTANT (honesty note)
------------------------
This is an **internal usability self-test** run by the engineer who built the
experiment — it is *not* a user study, not a participant survey, and the timings
are single-operator wall-clock measurements, not a usability benchmark. See
``docs/experiments.md`` for the wording that must be used in slides.

What it does
------------
1. ``--prepare-papers`` builds two real-paper excerpt documents under
   ``data/experiments/papers/`` from open-access Chinese articles on Europe PMC
   (CC BY): Chinese title + abstract + the first body paragraphs whose citations
   point at references 1-12 + the first 12 references re-rendered in GB/T 7714
   style (all fields come from the article XML; only punctuation/type codes are
   normalised). The source URLs/DOIs/licenses are written to ``SOURCES.json``.
2. Default mode drives the running workbench over HTTP exactly along the UI's
   call sequence (open workbench -> upload -> submit -> poll job -> open report ->
   export), for three documents: the bundled ``sample_paper.txt`` plus the two
   paper excerpts. It records operation steps, end-to-end latency, report
   statistics and export availability.
3. It probes the UI/backend contract for two known inconsistencies (``.docx``
   accepted by the page but rejected by the API; the ``support_max`` selector is
   not honoured) and collects the experience issues found during the run.

Manual comparison helpers
-------------------------
``--manual-fetch`` retrieves the bibliographic record for the 12 references of the
sample paper from Crossref (cache under ``data/experiments/manual_cache``) and
writes ``e7_manual_records.json`` with a start timestamp; the operator then
compares the 12 references by hand and records verdicts with
``--manual-finalize``. The elapsed time is measured from ``started_at`` to the
moment the verdicts are written, i.e. it includes the manual reading time.

Usage
-----
    PYTHONPATH=src python3 scripts/e7_usability.py --prepare-papers
    # start the workbench (port 8011) in a separate shell, then:
    PYTHONPATH=src python3 scripts/e7_usability.py --base http://127.0.0.1:8011
    PYTHONPATH=src python3 scripts/e7_usability.py --manual-fetch
    PYTHONPATH=src python3 scripts/e7_usability.py --manual-finalize verdicts.json

Outputs
-------
``data/experiments/e7_usability.json`` and, when papers are prepared,
``data/experiments/papers/*.txt``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests  # noqa: E402
from lxml import etree  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OUT_DIR = ROOT / "data" / "experiments"
PAPERS_DIR = OUT_DIR / "papers"
RAW_DIR = PAPERS_DIR / "raw"
SOURCES_FILE = PAPERS_DIR / "SOURCES.json"
OUT_FILE = OUT_DIR / "e7_usability.json"
MANUAL_RECORDS = OUT_DIR / "e7_manual_records.json"
MANUAL_CACHE = OUT_DIR / "manual_cache"
SAMPLE_PAPER = ROOT / "web" / "static" / "samples" / "sample_paper.txt"
BASE_URL = "http://127.0.0.1:8011"
USER_AGENT = "CiteGuard-CN/0.1 (research prototype; usability self-test)"
EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# Two open-access Chinese articles (CC BY) used for the real-paper excerpts.
PAPER_SPECS = [
    {
        "id": "paper_b",
        "pmcid": "PMC5973012",
        "filename": "paper_b_lung_cancer_screening_2018.txt",
        "note": "中国肺癌低剂量螺旋CT筛查指南（2018年版），中国肺癌杂志",
    },
    {
        "id": "paper_c",
        "pmcid": "PMC6000694",
        "filename": "paper_c_lung_cancer_projection_2010.txt",
        "note": "中国肺癌发病与死亡估计与预测（2010），中国肺癌杂志",
    },
]
MAX_REFS = 12

# HTTP calls issued by this script itself (paper preparation / manual lookups).
# Calls made by the web service during a job are not instrumented here.
HTTP_USAGE = {"epmc": 0, "crossref": 0, "doi_handle": 0}


def _count(kind: str) -> None:
    HTTP_USAGE[kind] = HTTP_USAGE.get(kind, 0) + 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


CODE_FILES = (
    "web/app.py",
    "src/citeguard/pipeline.py",
    "src/citeguard/report.py",
    "src/citeguard/gbt7714.py",
    "src/citeguard/reference_parser.py",
    "src/citeguard/metadata_verify.py",
)


def code_snapshot() -> dict:
    """Source hashes at the time of the run (the team edits the project concurrently)."""
    out = {}
    for rel in CODE_FILES:
        path = ROOT / rel
        if path.exists():
            out[rel] = {
                "sha256_16": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
                "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
            }
    return out


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _text(el) -> str:
    return _clean("".join(el.itertext())) if el is not None else ""


# ---------------------------------------------------------------------------
# Paper preparation (Europe PMC JATS -> GB/T-styled excerpt)
# ---------------------------------------------------------------------------

def _epmc_get(url: str, params: Optional[dict] = None, timeout: int = 90):
    _count("epmc")
    return requests.get(
        url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT}
    )


def _fetch_fulltext(pmcid: str) -> Optional[bytes]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cp = RAW_DIR / f"{pmcid}.xml"
    if cp.exists():
        return cp.read_bytes()
    resp = _epmc_get(f"{EPMC}/{pmcid}/fullTextXML")
    if resp.status_code != 200 or not resp.content:
        print(f"  [warn] {pmcid}: HTTP {resp.status_code}")
        return None
    cp.write_bytes(resp.content)
    return resp.content


def _fetch_meta(pmcid: str) -> dict:
    try:
        resp = _epmc_get(
            f"{EPMC}/search",
            {"query": f"PMCID:{pmcid}", "format": "json", "resultType": "core"},
            timeout=60,
        )
        if resp.status_code == 200:
            items = (resp.json().get("resultList") or {}).get("result") or []
            if items:
                x = items[0]
                return {
                    "pmcid": pmcid,
                    "pmid": x.get("pmid"),
                    "doi": x.get("doi"),
                    "title": x.get("title"),
                    "journal": (x.get("journalInfo") or {}).get("journal", {}).get("title")
                    or x.get("journalTitle"),
                    "year": x.get("pubYear"),
                    "license": x.get("license"),
                    "is_open_access": x.get("isOpenAccess"),
                }
    except Exception as exc:
        print(f"  [warn] metadata failed for {pmcid}: {type(exc).__name__}: {exc}")
    return {"pmcid": pmcid}


def _parse_ref(ref) -> Optional[dict]:
    title = _text(ref.find(".//article-title"))
    source = _text(ref.find(".//source"))
    year = _text(ref.find(".//year"))
    if not title or not year:
        return None
    authors: list[str] = []
    for group in ref.iter("person-group"):
        for node in group.iter():
            if node.tag == "name":
                surname = _text(node.find("surname"))
                given = _text(node.find("given-names"))
                if surname:
                    authors.append(f"{surname} {given}".strip())
            elif node.tag == "string-name":
                name = _text(node)
                if name:
                    authors.append(name)
        break
    if not authors:
        for node in ref.iter("string-name"):
            name = _text(node)
            if name:
                authors.append(name)
    volume = _text(ref.find(".//volume"))
    issue = _text(ref.find(".//issue"))
    fpage = _text(ref.find(".//fpage"))
    lpage = _text(ref.find(".//lpage"))
    doi = ""
    for pub in ref.iter("pub-id"):
        if pub.get("pub-id-type") == "doi":
            doi = _text(pub)
    publisher = _text(ref.find(".//publisher-name"))
    pages = f"{fpage}-{lpage}" if fpage and lpage and lpage != fpage else fpage
    return {
        "authors": authors,
        "title": title.rstrip("."),
        "source": source,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "doi": doi,
        "publisher": publisher,
    }


def _render_ref(meta: dict) -> str:
    authors = meta["authors"]
    is_cjk = any(re.search(r"[\u4e00-\u9fff]", a) for a in authors)
    shown = authors[:3]
    author_text = ", ".join(shown)
    if len(authors) > 3:
        author_text += ", 等" if is_cjk else ", et al"
    if meta.get("publisher"):
        ref = f"{author_text}. {meta['title']}[M]. {meta['publisher']}, {meta['year']}."
    else:
        ref = f"{author_text}. {meta['title']}[J]. {meta['source']}, {meta['year']}"
        if meta["volume"] and meta["issue"]:
            ref += f", {meta['volume']}({meta['issue']})"
        elif meta["volume"]:
            ref += f", {meta['volume']}"
        if meta["pages"]:
            ref += f": {meta['pages']}"
        ref += "."
    if meta.get("doi"):
        ref += f" DOI: {meta['doi']}."
    return ref


def _body_paragraphs(root) -> list[str]:
    """Paragraphs with in-text citation markers rewritten as [n]."""
    out: list[str] = []
    body = root.find(".//body")
    if body is None:
        return out
    for p in body.iter("p"):
        skipped = False
        parent = p.getparent()
        while parent is not None:
            if parent.tag in {"table-wrap", "fig", "caption", "table"}:
                skipped = True
                break
            parent = parent.getparent()
        if skipped:
            continue
        for xref in p.iter("xref"):
            rid = xref.get("rid") or ""
            m = re.match(r"[A-Za-z]*(\d+)$", rid)
            if m:
                xref.text = f"[{m.group(1)}]"
                for child in list(xref):
                    child.getparent().remove(child)
        text = _text(p)
        # JATS keeps the brackets in the surrounding text, so we may get "[[3]]" /
        # "[[5]-[10]]" / "[[2], [3]]".
        for _ in range(3):
            text = re.sub(r"\[\[(\d+)\]-\[(\d+)\]\]", r"[\1-\2]", text)
            text = re.sub(r"\[\[(\d+)\]\]", r"[\1]", text)
            text = re.sub(
                r"\[\[(\d+)\](?:\s*[,，]\s*\[(\d+)\])+\]",
                lambda m: "[" + re.sub(r"[\[\]]", "", m.group(0)) + "]",
                text,
            )
        if not text or not re.search(r"\[\d+", text):
            continue
        nums = [int(n) for n in re.findall(r"\[(\d+)", text)]
        if not nums or max(nums) > MAX_REFS:
            continue
        if len(text) < 40:
            continue
        out.append(text)
    return out


def prepare_papers() -> dict:
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    sources: list[dict] = []
    prepared: list[dict] = []
    for spec in PAPER_SPECS:
        print(f"[paper] {spec['id']} ({spec['pmcid']}) ...")
        content = _fetch_fulltext(spec["pmcid"])
        if not content:
            print(f"  [warn] could not fetch {spec['pmcid']}; skipping")
            continue
        meta = _fetch_meta(spec["pmcid"])
        root = etree.fromstring(content)
        title_zh = ""
        for el in root.iter("article-title"):
            if re.search(r"[\u4e00-\u9fff]", _text(el)):
                title_zh = _text(el)
                break
        title_zh = title_zh or _text(root.find(".//article-title"))
        abstract = ""
        for el in root.iter("abstract"):
            text = _text(el)
            if re.search(r"[\u4e00-\u9fff]", text) and len(text) > 60:
                abstract = text
                break
        abstract = abstract or _text(root.find(".//abstract"))
        refs = [_parse_ref(r) for r in root.findall(".//ref")]
        all_ref_count = len(refs)
        refs = [r for r in refs if r][:MAX_REFS]
        paragraphs = _body_paragraphs(root)[:4]
        journal = meta.get("journal") or ""
        year = meta.get("year") or ""
        lines = [
            f"# {title_zh}",
            "",
            (
                f"> 来源：{journal} {year}｜DOI: {meta.get('doi') or '—'}｜{meta.get('pmcid')}"
                f"｜许可: {meta.get('license') or '—'}。本文件为公开论文的节选：标题/摘要/正文段落来自欧洲 PMC"
                f" 全文 XML，文后引用列表取原文文献表中可渲染的前 {len(refs)} 条（原文 {all_ref_count} 条，"
                "题名/年份缺失的政府报告等条目已跳过）并按 GB/T 7714 风格重排"
                "（字段全部来自原文，仅统一标点与类型标识）；仅用于内部可用性自测。"
            ),
            "",
            "## 摘要",
            abstract,
            "",
        ]
        if paragraphs:
            lines += ["## 1 引言", ""]
            for para in paragraphs:
                lines += [para, ""]
        else:  # pragma: no cover - defensive
            lines += ["## 1 引言", "（原文该节无与本文件引用编号对应的引注段落，正文从略。）", ""]
        lines += ["## 参考文献"]
        for i, ref in enumerate(refs, 1):
            lines.append(f"[{i}] {_render_ref(ref)}")
        text = "\n".join(lines) + "\n"
        path = PAPERS_DIR / spec["filename"]
        path.write_text(text, encoding="utf-8")
        prepared.append(
            {
                "id": spec["id"],
                "filename": spec["filename"],
                "chars": len(text),
                "references": len(refs),
                "body_paragraphs": len(paragraphs),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
        sources.append(
            {
                **spec,
                **meta,
                "fulltext_api": f"{EPMC}/{spec['pmcid']}/fullTextXML",
                "license": meta.get("license"),
                "excerpt": f"标题 + 摘要 + {len(paragraphs)} 段含引注的正文 + 前 {len(refs)} 条参考文献",
                "note": spec["note"],
            }
        )
        print(f"  wrote {path.name}: {len(text)} chars, {len(refs)} refs, {len(paragraphs)} body paragraphs")

    SOURCES_FILE.write_text(
        json.dumps(
            {
                "generated_at": _utc_now(),
                "provider": "Europe PMC (open access full-text XML)",
                "license_note": "两篇原文均为 CC BY（Europe PMC license 字段），此处仅保存节选用于内部可用性自测。",
                "papers": sources,
                "prepared": prepared,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"prepared": prepared, "sources": sources}


# ---------------------------------------------------------------------------
# Web driver
# ---------------------------------------------------------------------------

class StepLog:
    def __init__(self) -> None:
        self.steps: list[dict] = []
        self._t0 = time.perf_counter()

    def add(self, name: str, detail: str = "") -> float:
        elapsed = round((time.perf_counter() - self._t0) * 1000.0, 1)
        self.steps.append({"step": len(self.steps) + 1, "name": name, "detail": detail, "t_ms": elapsed})
        return (time.perf_counter() - self._t0) * 1000.0


def drive_document(base: str, path: Path, support_max: str = "30") -> dict:
    log = StepLog()
    started = time.perf_counter()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    log.add("打开工作台首页")
    index = session.get(base + "/", timeout=30)
    index_ok = index.status_code == 200 and "引证卫士" in index.text

    log.add("选择文件", path.name)
    content = path.read_bytes()
    t_submit = time.perf_counter()
    resp = session.post(
        base + "/api/analyze",
        files={"file": (path.name, content, "text/plain")},
        data={"support_max": support_max},
        timeout=120,
    )
    submit_ms = round((time.perf_counter() - t_submit) * 1000.0, 1)
    log.add("点击「开始体检」并上传", f"HTTP {resp.status_code}")
    if resp.status_code != 202:
        return {"filename": path.name, "error": f"submit HTTP {resp.status_code}: {resp.text[:200]}"}
    job_id = resp.json()["job_id"]

    stages: list[dict] = []
    first_poll_ms: Optional[float] = None
    while True:
        job = session.get(f"{base}/api/jobs/{job_id}", timeout=30).json()
        elapsed = (time.perf_counter() - started) * 1000.0
        if first_poll_ms is None:
            first_poll_ms = round(elapsed, 1)
            log.add("进入报告页并轮询进度", f"job={job_id}")
        stages.append(
            {"t_ms": round(elapsed, 1), "status": job.get("status"), "progress": job.get("progress"),
             "stage": job.get("stage")}
        )
        if job.get("status") in {"done", "error"}:
            break
        if elapsed > 900_000:
            return {"filename": path.name, "error": "timeout"}
        time.sleep(0.5)
    done_ms = round((time.perf_counter() - started) * 1000.0, 1)
    log.add("分析完成", f"{job.get('status')} after {done_ms} ms")

    report_page = session.get(f"{base}/report/{job_id}", timeout=60)
    log.add("阅读报告页", f"HTTP {report_page.status_code}, {len(report_page.content)} bytes")
    report = session.get(f"{base}/api/report/{job_id}", timeout=60)
    log.add("调用报告 JSON", f"HTTP {report.status_code}")
    data = report.json() if report.status_code == 200 else {}

    exports = {}
    for fmt in ("html", "md", "json"):
        r = session.get(f"{base}/api/report/{job_id}/export", params={"format": fmt}, timeout=60)
        exports[fmt] = {"status": r.status_code, "bytes": len(r.content)}
    log.add("导出报告", f"html/md/json = {[exports[f]['status'] for f in exports]}")

    stats = data.get("stats") or {}
    refs = data.get("references") or []
    issues = sum(len((r.get("compliance") or {}).get("issues") or []) for r in refs)
    return {
        "filename": path.name,
        "job_id": job_id,
        "http_index_ok": index_ok,
        "submit_status": resp.status_code,
        "submit_ms": submit_ms,
        "job_status": job.get("status"),
        "total_ms": done_ms,
        "normalized_total_s": round(done_ms / 1000.0, 2),
        "steps": log.steps,
        "step_count": len(log.steps),
        "stages": stages,
        "stage_transitions": len({(s["progress"], s["stage"]) for s in stages}),
        "report_page_status": report_page.status_code,
        "report_json_status": report.status_code,
        "exports": exports,
        "stats": stats,
        "support_meta": stats.get("support_meta"),
        "judge_available_server": bool((stats.get("support_meta") or {}).get("judge_available")),
        "reference_count": len(refs),
        "format_issue_count": issues,
        "statuses": {
            k: sum(1 for r in refs if ((r.get("verify") or {}).get("status") == k))
            for k in ("Exact", "Minor", "Major", "Unknown")
        },
        "support_counts": stats.get("support"),
    }


def probe_contract(base: str) -> dict:
    """Cheap UI/backend contract probes that expose UX inconsistencies."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    probes: dict[str, Any] = {}
    probes["health"] = session.get(base + "/api/health", timeout=30).json()

    # 1) The page advertises PDF / Word; the API's accepted suffixes should match.
    try:
        r = session.post(
            base + "/api/analyze",
            files={"file": ("demo.docx", b"PK\x03\x04 not-a-real-docx", "application/octet-stream")},
            timeout=30,
        )
        probes["docx_upload"] = {
            "status": r.status_code,
            "detail": r.text[:160],
            "ui_claim": "index.html 文案：支持 PDF / Word（.docx）/ TXT / MD",
        }
    except Exception as exc:
        probes["docx_upload"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 2) Legacy .doc is in ALLOWED_SUFFIXES but extraction rejects it; the failure
    #    therefore surfaces asynchronously, after the job was accepted.
    try:
        r = session.post(
            base + "/api/analyze",
            files={"file": ("legacy.doc", b"\xd0\xcf\x11\xe0 fake doc", "application/msword")},
            timeout=30,
        )
        probe = {"submit_status": r.status_code}
        if r.status_code == 202:
            job_id = r.json()["job_id"]
            deadline = time.time() + 120
            while time.time() < deadline:
                job = session.get(f"{base}/api/jobs/{job_id}", timeout=30).json()
                if job.get("status") in {"done", "error"}:
                    break
                time.sleep(0.4)
            probe.update(
                {
                    "job_status": job.get("status"),
                    "error": job.get("error", ""),
                    "detail": "上传被接受后异步失败；用户需要等待后才看到错误",
                }
            )
        probes["doc_legacy_upload"] = probe
    except Exception as exc:
        probes["doc_legacy_upload"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 3) "support_max" is posted by the page; it should be honoured (0 = skip judge).
    try:
        text = SAMPLE_PAPER.read_text(encoding="utf-8")
        refs_block = text.split("## 参考文献", 1)[1].strip().splitlines()[:4]
        tiny = (
            "## 1 引言\n"
            + " ".join(f"这是第{i}句用于测试的引用句[{i}]。" for i in range(1, len(refs_block) + 1))
            + "\n\n## 参考文献\n"
            + "\n".join(refs_block)
            + "\n"
        )
        r = session.post(base + "/api/analyze", data={"text": tiny, "support_max": "0"}, timeout=60)
        if r.status_code == 202:
            job_id = r.json()["job_id"]
            deadline = time.time() + 600
            while time.time() < deadline:
                job = session.get(f"{base}/api/jobs/{job_id}", timeout=30).json()
                if job.get("status") in {"done", "error"}:
                    break
                time.sleep(0.5)
            report = session.get(f"{base}/api/report/{job_id}", timeout=60).json()
            support = (report.get("stats") or {}).get("support") or {}
            meta = (report.get("stats") or {}).get("support_meta") or {}
            probes["support_max_honoured"] = {
                "requested": 0,
                "job_status": job.get("status"),
                "support_counts": support,
                "support_meta": meta,
                "judged": meta.get("judged", sum(v for k, v in support.items() if k != "not_checked")),
            }
        else:
            probes["support_max_honoured"] = {"status": r.status_code, "detail": r.text[:160]}
    except Exception as exc:
        probes["support_max_honoured"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 4) Unknown job id -> JSON error instead of a friendly page (report page is HTML).
    try:
        r = session.get(base + "/report/doesnotexist", timeout=30)
        probes["unknown_report_page"] = {"status": r.status_code, "detail": r.text[:160]}
    except Exception as exc:
        probes["unknown_report_page"] = {"error": f"{type(exc).__name__}: {exc}"}

    # 5) The front-end poll interval is fixed and there is no cancel / upload progress.
    probes["ui_polling"] = {
        "interval_ms": 1400,
        "detail": "report.js pollJob() 固定 1.4s 轮询，完成后整页 reload；无取消按钮",
    }
    return probes


# ---------------------------------------------------------------------------
# Manual 12-reference comparison helpers
# ---------------------------------------------------------------------------

def _crossref_lookup(doi: str) -> dict:
    MANUAL_CACHE.mkdir(parents=True, exist_ok=True)
    cp = MANUAL_CACHE / (hashlib.md5(doi.encode()).hexdigest() + ".json")
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    started = time.perf_counter()
    out: dict = {"doi": doi, "http": None, "record": None}
    try:
        _count("crossref")
        resp = requests.get(
            "https://api.crossref.org/works/" + doi,
            timeout=60,
            headers={"User-Agent": USER_AGENT + " mailto:citeguard@example.org"},
        )
        out["http"] = resp.status_code
        if resp.status_code == 200:
            item = (resp.json() or {}).get("message", {}) or {}
            authors = []
            for a in item.get("author") or []:
                name = " ".join(x for x in [a.get("given", ""), a.get("family", "")] if x).strip()
                if name:
                    authors.append(name)
            issued = (item.get("issued") or {}).get("date-parts") or [[None]]
            out["record"] = {
                "title": (item.get("title") or [""])[0],
                "year": issued[0][0] if issued and issued[0] else None,
                "authors": authors,
                "venue": (item.get("container-title") or [""])[0],
                "volume": item.get("volume"),
                "issue": item.get("issue"),
                "pages": item.get("page"),
            }
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    out["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 1)
    cp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def _doi_handle(doi: str) -> dict:
    """DOI existence via the authoritative handle API (doi.org), independent of Crossref."""
    MANUAL_CACHE.mkdir(parents=True, exist_ok=True)
    cp = MANUAL_CACHE / ("handle_" + hashlib.md5(doi.encode()).hexdigest() + ".json")
    if cp.exists():
        try:
            return json.loads(cp.read_text(encoding="utf-8"))
        except Exception:
            pass
    out: dict = {"doi": doi, "http": None, "exists": None}
    try:
        _count("doi_handle")  # authoritative DOI handle API (doi.org)
        resp = requests.get(
            "https://doi.org/api/handles/" + doi, timeout=45,
            headers={"User-Agent": USER_AGENT},
        )
        out["http"] = resp.status_code
        if resp.status_code == 200:
            out["exists"] = (resp.json() or {}).get("responseCode") == 1
        elif resp.status_code == 404:
            out["exists"] = False
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    cp.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def manual_fetch(base: str) -> dict:
    """Collect the 12 sample references + their Crossref records for manual review."""
    # Find the newest report for the sample paper through the local jobs folder.
    reports = sorted(
        (ROOT / "data" / "jobs").glob("*/report.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    report = None
    for path in reports:
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
        except Exception:
            continue
        # The sample paper is identified by its two constructed DOIs; the report's
        # "input" field only carries the anonymised job-id filename.
        if "10.9999/fake.0001" in text and "10.9999/fake.0002" in text:
            report = data
            break
        if str(data.get("input", "")).endswith("sample_paper.txt"):
            report = data
            break
    if report is None:
        print("[fatal] no sample-paper report found; run the web driver first", file=sys.stderr)
        return {}

    refs = (report.get("references") or [])[:12]
    rows = []
    started_at = _utc_now()
    t0 = time.perf_counter()
    for item in refs:
        parsed = item.get("parsed") or {}
        verify = item.get("verify") or {}
        doi = (parsed.get("doi") or "").strip()
        external = _crossref_lookup(doi) if doi else {"doi": "", "http": None, "record": None}
        handle = _doi_handle(doi) if doi else {"doi": "", "exists": None}
        rows.append(
            {
                "index": item.get("index"),
                "raw": item.get("raw"),
                "parsed": {
                    "title": parsed.get("title"),
                    "authors": parsed.get("authors"),
                    "year": parsed.get("year"),
                    "venue": parsed.get("venue"),
                    "volume": parsed.get("volume"),
                    "issue": parsed.get("issue"),
                    "pages": parsed.get("pages"),
                    "doi": doi,
                },
                "tool_status": verify.get("status"),
                "external": external,
                "doi_handle": handle,
            }
        )
    fetch_ms = round((time.perf_counter() - t0) * 1000.0, 1)
    payload = {
        "started_at": started_at,
        "fetch_ms": fetch_ms,
        "source": "Crossref REST API (api.crossref.org/works/{doi}), 结果缓存在 data/experiments/manual_cache",
        "n": len(rows),
        "rows": rows,
    }
    MANUAL_RECORDS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[manual] fetched {len(rows)} records in {fetch_ms} ms; rows written to {MANUAL_RECORDS.name}")
    for row in rows:
        rec = (row["external"] or {}).get("record") or {}
        print(
            f"  [{row['index']}] tool={row['tool_status']} http={(row['external'] or {}).get('http')} "
            f"handle_exists={(row.get('doi_handle') or {}).get('exists')} "
            f"| parsed: {row['parsed']['title']!r} {row['parsed']['year']} {row['parsed']['venue']!r} "
            f"{row['parsed']['volume']}({row['parsed']['issue']}):{row['parsed']['pages']}"
        )
        print(
            f"      external: {rec.get('title')!r} {rec.get('year')} {rec.get('venue')!r} "
            f"{rec.get('volume')}({rec.get('issue')}):{rec.get('pages')} | authors={rec.get('authors')}"
        )
    return payload


def manual_finalize(verdicts_path: Path) -> dict:
    records = json.loads(MANUAL_RECORDS.read_text(encoding="utf-8"))
    verdicts = json.loads(Path(verdicts_path).read_text(encoding="utf-8"))
    started = datetime.fromisoformat(records["started_at"])
    finished = datetime.now(timezone.utc)
    elapsed_s = round((finished - started).total_seconds(), 1)

    by_index = {int(k): v for k, v in verdicts.items()}
    rows = []
    agree = 0
    for row in records["rows"]:
        index = row["index"]
        verdict = by_index.get(index, {})
        manual = verdict.get("label", "")
        note = verdict.get("note", "")
        if manual and manual == row["tool_status"]:
            agree += 1
        rows.append({**{k: row[k] for k in ("index", "raw", "parsed", "tool_status")},
                     "manual_label": manual, "manual_note": note})
    return {
        "n": len(rows),
        "elapsed_s": elapsed_s,
        "per_ref_s": round(elapsed_s / len(rows), 1) if rows else 0.0,
        "fetch_ms": records.get("fetch_ms"),
        "timer": "Python datetime: started_at recorded before the first manual lookup, "
                 "finished_at written when the verdicts are saved; elapsed includes retrieval + reading + judging.",
        "operator": "single operator (the engineer running this experiment; no participants were recruited)",
        "agreement_with_tool": agree,
        "agreement_rate": round(agree / len(rows), 4) if rows else 0.0,
        "rows": rows,
        "verdicts": verdicts,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    argp = argparse.ArgumentParser(description="E7: internal usability self-test.")
    argp.add_argument("--prepare-papers", action="store_true")
    argp.add_argument("--base", default=BASE_URL)
    argp.add_argument("--docs", default="all", help="all | sample | paper_b | paper_c")
    argp.add_argument("--manual-fetch", action="store_true")
    argp.add_argument("--manual-finalize", type=Path, default=None)
    argp.add_argument("--out", type=Path, default=OUT_FILE)
    args = argp.parse_args(argv)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.prepare_papers:
        result = prepare_papers()
        print(json.dumps(result["prepared"], ensure_ascii=False, indent=2))
        return 0

    if args.manual_fetch:
        manual_fetch(args.base)
        return 0

    if args.manual_finalize:
        result = manual_finalize(args.manual_finalize)
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False, indent=2))
        # merge into the experiment file if it exists
        payload = {}
        if args.out.exists():
            payload = json.loads(args.out.read_text(encoding="utf-8"))
        payload.setdefault("experiment", "E7")
        payload["manual_check"] = result
        args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    docs: list[Path] = []
    if args.docs in {"all", "sample"}:
        docs.append(SAMPLE_PAPER)
    if args.docs in {"all", "paper_b", "paper_c"}:
        for spec in PAPER_SPECS:
            if args.docs in {"all", spec["id"]}:
                docs.append(PAPERS_DIR / spec["filename"])
    docs = [p for p in docs if p.exists()]
    if not docs:
        print("[fatal] no documents to run", file=sys.stderr)
        return 2

    print(f"[info] base={args.base} docs={[p.name for p in docs]}")
    health = requests.get(args.base + "/api/health", timeout=30)
    print(f"[info] health {health.status_code}: {health.text[:80]}")

    results = []
    for path in docs:
        print(f"[run] {path.name} ...")
        try:
            result = drive_document(args.base, path)
        except Exception as exc:
            result = {"filename": path.name, "error": f"{type(exc).__name__}: {exc}"}
        results.append(result)
        if "error" in result:
            print(f"  [error] {result['error']}")
        else:
            print(
                f"  done in {result['total_ms'] / 1000:.1f}s, refs={result['reference_count']}, "
                f"steps={result['step_count']}, statuses={result['statuses']}"
            )

    print("[probe] UI/backend contract probes ...")
    probes = probe_contract(args.base)

    sample = next((r for r in results if r["filename"] == SAMPLE_PAPER.name), results[0])
    ux_issues: list[dict] = []
    legacy = probes.get("doc_legacy_upload") or {}
    if legacy.get("submit_status") == 202 and legacy.get("job_status") == "error":
        ux_issues.append(
            {
                "id": "UX1",
                "severity": "medium",
                "title": "旧版 .doc 上传被接受后才异步失败",
                "evidence": f"POST /api/analyze(.doc) -> {legacy.get('submit_status')}，任务状态 {legacy.get('job_status')}："
                            f"{str(legacy.get('error'))[:120]}；web/app.py 允许 .doc，pdf_extract.extract_text 明确拒绝",
                "impact": "用户要等到任务跑起来才看到「请另存为 .docx」，且失败任务留在最近任务列表里，需重来一遍。",
            }
        )
    if (probes.get("support_max_honoured") or {}).get("judged", 0) > 0:
        ux_issues.append(
            {
                "id": "UX2",
                "severity": "high",
                "title": "「引用支持度判定条数」选择器不生效",
                "evidence": str(probes.get("support_max_honoured")),
                "impact": "用户以为选了「不判定」，实际仍调用 LLM judge，耗时与费用不可控。",
            }
        )
    ux_issues.append(
        {
            "id": "UX3",
            "severity": "medium",
            "title": "进度反馈粒度粗、无法取消、完成后整页刷新",
            "evidence": f"前端固定 1.4s 轮询（report.js pollJob），本次报告页共记录 {sample.get('stage_transitions')} 次进度跳变；"
                        "无取消/停止按钮；完成后 location.reload()",
            "impact": "长任务期间无法干预；刷新会丢失当前视图；大文件上传也没有上传进度条。",
        }
    )
    unknown = probes.get("unknown_report_page") or {}
    if unknown.get("status") == 404:
        ux_issues.append(
            {
                "id": "UX4",
                "severity": "low",
                "title": "未知任务 id 返回 JSON 错误而非友好页面",
                "evidence": f"GET /report/doesnotexist -> {unknown.get('status')}：{str(unknown.get('detail'))[:100]}",
                "impact": "从旧链接/被清理的任务进入时看到裸 JSON，缺少返回工作台的引导。",
            }
        )
    ux_issues.append(
        {
            "id": "UX5",
            "severity": "medium",
            "title": "「未检出问题」的呈现强于规则层真实能力",
            "evidence": "E4 实测：30 条格式漂移中 15 条（页码连字符 / 4 作者未用「等」/ 卷期互换）规则层完全无提示；"
                        "报告页对无 issue 的条目标注「新国标字段检查未发现问题」",
            "impact": "用户会把「规则没查到」理解为「格式没问题」，对合规结论过度信任；建议文案改为「未发现本规则集覆盖的问题」。",
        }
    )
    # Re-number sequentially: an issue may be dropped when a probe shows the fix.
    for i, issue in enumerate(ux_issues, 1):
        issue["id"] = f"UX{i}"

    manual = None
    if MANUAL_RECORDS.exists():
        try:
            manual = {"records_file": str(MANUAL_RECORDS.relative_to(ROOT)), "n": json.loads(MANUAL_RECORDS.read_text(encoding="utf-8"))["n"]}
        except Exception:
            manual = None

    payload = {
        "experiment": "E7",
        "title": "Web 工作台内部可用性自测",
        "disclaimer": (
            "本结果为团队内部可用性自测（internal usability self-test），不是用户实测、不是受试者调研、"
            "没有招募任何用户；操作由实验执行者通过 HTTP 客户端按前端调用序列完成，"
            "步数按前端交互步骤计，耗时为本机单次实测，不可外推为用户体验结论。"
        ),
        "generated_at": _utc_now(),
        "code_snapshot": code_snapshot(),
        "environment": {
            "base_url": args.base,
            "server": "uvicorn web.app:app --port 8011 (local)",
            "client": f"Python {sys.version.split()[0]} requests",
            # The key is configured on the *server* process; the driver may not have it.
            "llm_judge_enabled": any(
                d.get("judge_available_server") for d in results if isinstance(d, dict)
            ),
            "llm_judge_enabled_source": "server-side report.stats.support_meta.judge_available",
            "driver_env_has_key": bool(__import__("os").environ.get("DEEPSEEK_API_KEY")),
        },
        "documents": results,
        "contract_probes": probes,
        "ux_issues": ux_issues,
        "manual_check": manual,
        "experiment_requests": dict(HTTP_USAGE),
        "limitations": [
            "内部自测：单一执行者、n=1 次运行，没有真实用户参与，不能作为用户研究或 SUS 结论。",
            "通过 HTTP 客户端复现前端调用序列，未做真实浏览器点击/渲染耗时测量；步数按前端交互步骤计。",
            "两篇真实论文为节选（摘要 + 部分正文 + 前 12 条参考文献），不是全文；引用列表按 GB/T 风格重排。",
            "运行期 OpenAlex 免费额度已用尽（429），题名检索回退主要依赖 Crossref，核验结果与延迟受此影响。",
            "人工核对耗时由实验执行者单次实测，包含检索与阅读判断，样本仅 12 条。",
        ],
    }
    if manual:
        payload["manual_check_file"] = MANUAL_RECORDS.name
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
