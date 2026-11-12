"""Evaluate GROBID reference parsing on the three blind-test PDFs.

Requires a running GROBID container:
  docker run -d --rm --name grobid -p 8070:8070 grobid/grobid:0.8.1

Writes data/experiments/grobid_eval.json:
  per paper -> grobid biblStruct count vs our layout parser count.
"""
import json
import re
import time
import urllib.request
import uuid
from pathlib import Path

BASE = "http://127.0.0.1:8070"
PDFS = sorted(Path("out/blind_test5").glob("*.pdf"))
OURS = {"2505.09388": 73, "2501.12948": 92, "2401.04088": 27}
OURS_BY_STEM = {"qwen3": 73, "deepseek_r1": 92, "mixtral": 27}


def wait_ready(timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(BASE + "/api/isalive", timeout=5) as r:
                if r.status == 200 and b"true" in r.read().lower():
                    return True
        except Exception:
            pass
        time.sleep(3)
    return False


def post_pdf(path):
    boundary = "----" + uuid.uuid4().hex
    body = b""
    body += f"--{boundary}\r\n".encode()
    body += f'Content-Disposition: form-data; name="input"; filename="{path.name}"\r\n'.encode()
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += path.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        BASE + "/api/processReferences",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read().decode("utf-8", "replace")


def main():
    out = []
    if not wait_ready():
        raise SystemExit("GROBID not ready on :8070")
    for pdf in PDFS:
        try:
            xml = post_pdf(pdf)
            n = len(re.findall(r"<biblStruct\b", xml))
            m = re.search(r"(\d{4}\.\d{4,5})", pdf.name)
            key = m.group(1) if m else pdf.stem
            ours = OURS.get(key) if key in OURS else OURS_BY_STEM.get(pdf.stem)
            out.append({"paper": pdf.name, "arxiv": key, "grobid_refs": n, "ours_refs": ours})
        except Exception as exc:
            out.append({"paper": pdf.name, "error": str(exc)})
    dest = Path("data/experiments/grobid_eval.json")
    dest.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "items": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
