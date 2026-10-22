"""Probe OpenAlex for Chinese works (used to build CiteBench-CN and to test the verifier)."""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from citeguard.metadata_verify import verify_reference  # noqa: E402
from citeguard.reference_parser import parse_reference  # noqa: E402


def main() -> None:
    r = requests.get(
        "https://api.openalex.org/works",
        params={
            "filter": "language:zh,has_doi:true",
            "per-page": 5,
            "select": "id,doi,title,publication_year,authorships,primary_location,biblio,type,language",
            "mailto": "citeguard@example.org",
        },
        timeout=30,
    )
    data = r.json()
    print("count:", data.get("meta", {}).get("count"))
    for w in data.get("results", []):
        src = ((w.get("primary_location") or {}).get("source") or {})
        authors = [(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])]
        print(json.dumps({
            "title": w.get("title"),
            "doi": w.get("doi"),
            "year": w.get("publication_year"),
            "authors": authors[:4],
            "venue": src.get("display_name"),
            "biblio": w.get("biblio"),
        }, ensure_ascii=False))

    # Test parse + verify on the first result
    w = data["results"][0]
    src = ((w.get("primary_location") or {}).get("source") or {})
    authors = [(a.get("author") or {}).get("display_name", "") for a in (w.get("authorships") or [])]
    biblio = w.get("biblio") or {}
    ref_str = (
        f"[1] {', '.join(authors[:3])}. {w.get('title')}[J]. {src.get('display_name', '')}, "
        f"{w.get('publication_year')}, {biblio.get('volume', '')}({biblio.get('issue', '')}): "
        f"{biblio.get('first_page', '')}-{biblio.get('last_page', '')}. DOI: {w.get('doi', '').replace('https://doi.org/', '')}."
    )
    print("\nREF:", ref_str)
    ref = parse_reference(ref_str)
    print("PARSED:", json.dumps(ref.to_dict(), ensure_ascii=False, indent=1))
    v = verify_reference(ref)
    print("VERIFY:", json.dumps(v.to_dict(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
