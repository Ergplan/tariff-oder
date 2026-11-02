"""Read the Commission's decisions on a reference filing from its order (R-TU-5).

    uv run python scripts/order_decisions.py uperc-npcl-fy2026-27 --pdf <order.pdf>

The order must be the document the spec names (``order/decisions.json``, by SHA-256).  Each summary
table is read row by row from the order's text layer (PyMuPDF; untrusted data, text only), each row
with its page and the text it was read from, then evaluated against the formats workbook: the
columns restating the petition or an earlier approval compared with the ARR format, and the
decision (approved − claimed) per line.  Writes ``order-decisions.json`` beside the reference.
Reading the order is not verifying it; the reviewer reads the pages.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr.decisions import evaluate_table, identities, read_rows  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--pdf", required=True, type=Path)
    args = ap.parse_args()
    import openpyxl
    import pymupdf

    folder = ROOT / "packages" / "reference-filings" / args.package
    spec = json.loads((folder / "order" / "decisions.json").read_text())
    sha = hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if sha != spec["order"]["sha256"]:
        print(f"the PDF is not the order the spec names ({sha[:12]}…)", file=sys.stderr)
        return 1
    with pymupdf.open(args.pdf) as doc:
        pages = {i + 1: p.get_text() for i, p in enumerate(doc)}
    wb = openpyxl.load_workbook(folder / spec["workbook"], data_only=True)
    tables = []
    for t in spec["tables"]:
        table = t | {"rows": read_rows(pages, t["title"], t["pages"])}
        rows = evaluate_table(table, spec["rows"], wb, spec["sheet"])
        counts = collections.Counter(c["result"] for r in rows for c in r["checks"].values())
        changed = [r for r in rows if r.get("decision") not in (None, "0", "0.00")]
        print(f"{t['proceeding']:8} {len(rows)} rows; against the format {dict(counts)}; ", end="")
        print(f"{len(changed)} lines changed by the decision")
        own = identities(rows, t["columns"])
        print(f"         the order's own arithmetic {dict(collections.Counter(i['result'] for i in own))}")
        keep = {k: t[k] for k in ("proceeding", "fiscal_year", "title", "pages", "columns")}
        tables.append(keep | {"rows": rows, "identities": own})
    report = {
        "order": spec["order"],
        "status": (
            "read from the order's text layer, each row with its page and quote — not reviewed; "
            "the decision is the Commission's, the comparison the build's"
        ),
        "note": spec["note"],
        "tables": tables,
    }
    (folder / "order-decisions.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
