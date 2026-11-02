#!/usr/bin/env python3
"""Propose, for each draft rule, the pages of a regulation where its clause may be (milestone 13).

    uv run python scripts/clause_candidates.py --commission UPERC \\
        --pdf "<the official UPERC MYT Distribution Regulations 2025>.pdf" --cites 2025 --label myt-2025

Reads the regulation's text layer (PyMuPDF), ranks its pages for every rule whose clause names a
regulation containing ``--cites``, and writes
``packages/arr-rules/<commission>/candidates/<label>.json`` (a subfolder, never read as rules)
with the PDF's SHA-256.  These are **proposals**: nothing here verifies a clause.  A reviewer opens
the proposed page, reads the clause, and records the clause, page and excerpt in the rule file;
only a person sets ``verified``.  The PDF is untrusted data: only its text is read.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr.clauses import rank  # noqa: E402
from tariff_api.arr.rules import applies_in, load_rules  # noqa: E402


def candidates(
    pdf: Path, commission: str, cites: str, kind: str = "regulation", applies: str | None = None
) -> dict:
    import pymupdf

    with pymupdf.open(pdf) as doc:
        pages = [p.get_text() for p in doc]
    rules = [r for r in load_rules(commission) if cites.lower() in r.clause.regulation.lower()]
    if applies:  # only the rules in force in that year (a 2025 regulation is no clause for a 2019-only rule)
        rules = [r for r in rules if applies_in(r, applies)]
    return {
        "status": "proposals for the reviewer — none verified; a clause is verified only by a person reading the page",
        "regulation_pdf": pdf.name,
        "kind": kind,
        "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
        "pages": len(pages),
        "pages_with_text": sum(1 for p in pages if p.strip()),
        "cites": cites,
        "applies_in": applies,
        "rules": {r.id: [asdict(c) for c in rank(pages, r)] for r in rules},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commission", required=True)
    ap.add_argument("--pdf", required=True, type=Path)
    ap.add_argument("--cites", required=True, help="text the rules' clause.regulation contains, e.g. 2025")
    ap.add_argument("--label", required=True, help="file label, e.g. myt-2025")
    ap.add_argument("--applies-in", help="only rules in force in this fiscal year, e.g. FY2025-26")
    ap.add_argument(
        "--kind",
        default="regulation",
        help="what the PDF is: 'regulation' (the text itself) or e.g. 'tariff order (quotes the regulations)'",
    )
    args = ap.parse_args()
    out = candidates(args.pdf, args.commission, args.cites, args.kind, args.applies_in)
    if not out["pages_with_text"]:
        print("the PDF has no text layer: OCR it first (the pipeline's parse stage), then rerun")
        return 1
    dest = ROOT / "packages" / "arr-rules" / args.commission.lower() / "candidates" / f"{args.label}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    found = sum(1 for c in out["rules"].values() if c)
    print(f"{len(out['rules'])} rules cite {args.cites!r}; {found} with candidate pages → {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
