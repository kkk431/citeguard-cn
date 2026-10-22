"""Inspect parsed fields and verification for the demo sample references."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from citeguard.metadata_verify import verify_reference  # noqa: E402
from citeguard.pdf_extract import extract_text, split_references  # noqa: E402
from citeguard.reference_parser import parse_reference_list  # noqa: E402

sample = Path(__file__).resolve().parents[1] / "web" / "static" / "samples" / "sample_paper.txt"
text = extract_text(sample)
body, refs_text = split_references(text)
refs = parse_reference_list(refs_text)
print(f"body={len(body)} refs={len(refs)}")
for r in refs:
    print(f"\n[{r.index}] type={r.doc_type} year={r.year} doi={r.doi}")
    print(f"  authors={r.authors}")
    print(f"  title={r.title}")
    print(f"  venue={r.venue} vol={r.volume} issue={r.issue} pages={r.pages}")
    if r.index in {1, 5, 9, 10}:
        v = verify_reference(r)
        print(f"  -> {v.status} sim={v.title_sim} notes={v.notes}")
        if v.best:
            print(f"     best={v.best.source} | {v.best.title[:60]} | {v.best.year} | {v.best.doi}")
