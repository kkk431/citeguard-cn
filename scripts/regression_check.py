"""H1：一键回归（测试 + 自检 + 证据 + 可选 e2e），写 JSON/日志。

用法：
  python scripts/regression_check.py
  python scripts/regression_check.py --base http://127.0.0.1:8013 --pdf data/real_corpus/hanspub_152575.pdf
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "experiments"


def run(name, cmd, timeout=900):
    started = time.time()
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        code = p.returncode
        tail = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()[-1600:]
    except subprocess.TimeoutExpired as exc:
        code = 124
        tail = f"timeout after {timeout}s: {exc}"
    return {
        "name": name,
        "command": " ".join(str(x) for x in cmd),
        "exit_code": code,
        "duration_seconds": round(time.time() - started, 2),
        "tail": tail,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="", help="有则跑 e2e_smoke")
    ap.add_argument("--pdf", default="data/real_corpus/hanspub_152575.pdf")
    args = ap.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    steps = [
        run("pytest", [sys.executable, "-m", "pytest", "tests", "-q"]),
        run("verify_artifacts", [sys.executable, "scripts/verify_artifacts.py"]),
        run("audit_evidence", [sys.executable, "scripts/audit_evidence.py"]),
        run("licenses", [sys.executable, "-m", "pytest", "tests/test_licenses.py", "-q"]),
    ]
    if args.base:
        steps.append(run("e2e_smoke", [
            sys.executable, "scripts/e2e_smoke.py", "--base", args.base, "--pdf", args.pdf,
        ]))
    ok = all(x["exit_code"] == 0 for x in steps)
    payload = {
        "timestamp": stamp,
        "ok": ok,
        "version": (ROOT / "web" / "app.py").read_text(encoding="utf-8").split("version=", 1)[1].split(",", 1)[0].strip('"'),
        "steps": steps,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"opt_h1_regression_{stamp}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / f"opt_tests_{stamp}.txt").write_text(
        "\n\n".join(f"$ {x['command']}\nexit={x['exit_code']}\n{x['tail']}" for x in steps),
        encoding="utf-8",
    )
    print(json.dumps({"ok": ok, "steps": [{k: x[k] for k in ("name", "exit_code", "duration_seconds")} for x in steps]}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
