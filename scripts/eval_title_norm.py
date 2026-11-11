"""Measure CJK title matching robustness: spaces/punctuation vs traditional chars.

Two perturbations of real published Chinese titles:
1. insert a space between every character + full-width period;
2. convert to Traditional Chinese (common in HK/TW citations and some OCR).
The new normalizer adds optional OpenCC t2s; the old one does not.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import opencc  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402

from citeguard.reference_parser import parse_reference_list  # noqa: E402

PUNCT = re.compile(r"[\s\-_,.;:!?\"'“”‘’()\[\]{}<>《》〈〉、。，；：！？…·—/\\|]+")
T2S = opencc.OpenCC("t2s")
S2T = opencc.OpenCC("s2t")


def has_cjk(s: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def norm_old(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return PUNCT.sub("", s)


def norm_new(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    if has_cjk(s):
        s = T2S.convert(s)
    return PUNCT.sub("", s.lower())


def sim(a: str, b: str, norm) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    return max(fuzz.ratio(na, nb), fuzz.token_set_ratio(na, nb)) / 100.0


def main() -> int:
    corpus = ROOT / "data" / "real_corpus"
    manifest = json.loads((corpus / "hanspub_manifest.json").read_text(encoding="utf-8"))
    titles: list[str] = []
    for item in manifest:
        published = Path(item["refs_file"])
        if not published.exists():
            continue
        for ref in parse_reference_list(published.read_text(encoding="utf-8")):
            t = (ref.title or "").strip()
            if has_cjk(t) and len(t) >= 6:
                titles.append(t)
    titles = list(dict.fromkeys(titles))

    spaced = [(" ".join(t) + "。", t) for t in titles]
    trad = [(S2T.convert(t), t) for t in titles]

    def rate(rows, norm):
        return round(sum(1 for noisy, clean in rows if sim(clean, noisy, norm) >= 0.95) / len(rows), 4)

    out = {
        "n": len(titles),
        "spaced_old_hit_095": rate(spaced, norm_old),
        "spaced_new_hit_095": rate(spaced, norm_new),
        "traditional_old_hit_095": rate(trad, norm_old),
        "traditional_new_hit_095": rate(trad, norm_new),
        "traditional_old_mean_sim": round(sum(sim(c, n, norm_old) for n, c in trad) / len(trad), 4),
        "traditional_new_mean_sim": round(sum(sim(c, n, norm_new) for n, c in trad) / len(trad), 4),
        "source": "20 real papers / published reference lists (206 Chinese titles)",
    }
    out_path = ROOT / "data" / "experiments" / "title_norm_cn.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
