"""Check abstract availability and claim-support judging for the demo sample."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from citeguard.metadata_verify import verify_reference  # noqa: E402
from citeguard.pdf_extract import extract_text, split_references  # noqa: E402
from citeguard.reference_parser import parse_intext_citations, parse_reference_list  # noqa: E402
from citeguard.support import build_claims, judge_support  # noqa: E402

sample = Path(__file__).resolve().parents[1] / "web" / "static" / "samples" / "sample_paper.txt"
text = extract_text(sample)
body, refs_text = split_references(text)
refs = parse_reference_list(refs_text)
intext = parse_intext_citations(body)
claims = build_claims(body, intext, refs)
print(f"refs={len(refs)} intext={len(intext)} claims={len(claims)}")

for r in refs[:12]:
    v = verify_reference(r)
    abstract = (v.best.abstract if v.best else "") or ""
    print(f"\n[{r.index}] {v.status} abstract_len={len(abstract)}")
    print("  claim:", (claims.get(r.index) or "")[:100])
    if claims.get(r.index) and abstract:
        res = judge_support(claims[r.index], abstract, v.best.title if v.best else "", r.doi)
        print("  support:", res)
