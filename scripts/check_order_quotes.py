"""Check a rate record against the order it was read from.

    uv run python scripts/check_order_quotes.py --pdf <order.pdf> \
        --record packages/reference-filings/<package>/rate-schedule-<fy>.json

The PDF must be the document the record names (same SHA-256).  Every rate's quote must be found
on its page (whitespace-normalised, in PyMuPDF's text layer), with its column's header where it
has one, and the rate's figure must be in its quote.  It prints one line per rate and exits
non-zero on any failure.  Passing means each figure is printed where the record says — not that
the reading is right for its row: that is the reviewer's, with the page in hand.  The PDF is
untrusted data and is only read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr.reproduce import load_rate_record  # noqa: E402


def check(pdf: Path, record: dict) -> list[str]:
    import pymupdf

    problems: list[str] = []
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if sha != record["document"]["sha256"]:
        return [f"the PDF is not the record's document ({sha[:12]}… against {record['document']['sha256'][:12]}…)"]
    load_rate_record(record)  # every figure is in its quote, or this raises

    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s).strip()

    with pymupdf.open(pdf) as doc:
        pages = {i + 1: norm(p.get_text()) for i, p in enumerate(doc)}
    for key, r in (record.get("rates") or record.get("figures") or {}).items():
        # where several rates share a printed row, the column's header is quoted too
        ok = all(norm(q) in pages.get(r["page"], "") for q in (r["quote"], r.get("header")) if q)
        print(f"{'ok ' if ok else 'NOT'} {key:28} {r['value']:>6} {r['unit']:12} p.{r['page']}")
        if not ok:
            problems.append(f"{key}: quote or column header not found on page {r['page']}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--record", required=True, type=Path)
    args = ap.parse_args()
    problems = check(args.pdf, json.loads(args.record.read_text()))
    for p in problems:
        print(p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
