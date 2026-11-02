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
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr.decisions import (  # noqa: E402
    check_sources,
    evaluate_table,
    identities,
    read_rows,
    rows_by_position,
    source_decisions,
)


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
    sources = []
    for t in spec.get("source_tables", []):
        rows = []
        with pymupdf.open(args.pdf) as doc:
            for pno in t["pages"]:
                words = doc[pno - 1].get_text("words")
                # the page's own header words, each printed twice: claimed left, approved right
                named = t.get("anchor_words", {"mu": "MUs", "amount": "Amount"})
                xs = {f: sorted((w[0] + w[2]) / 2 for w in words if w[4] == word) for f, word in named.items()}
                anchors = {}
                for i, side in enumerate(("claimed", "approved")):
                    for f in ("mu", "rate", "amount"):
                        anchors[f"{side}_{f}"] = xs[f][i] if f in xs else (xs["mu"][i] + xs["amount"][i]) / 2
                stop = t["stop"] if pno == t["pages"][-1] else None
                found = rows_by_position(words, anchors, t["start"], stop, label_span=t.get("label_span", 0))
                rows += [r | {"page": pno} for r in found]
        own = check_sources(rows, ["claimed", "approved"], t["sums"])
        decided = source_decisions(rows, skip=tuple(x["total"] for x in t["sums"]))
        fmt = []
        for f in t.get("format", []):
            row = next(r for r in rows if (r["code"] or r["label"]) == f["row"])
            vals = [wb[c.split("!")[0]][c.split("!")[1]].value for c in f["cells"]]
            total = sum(Decimal(str(v)) for v in vals if isinstance(v, int | float)).quantize(Decimal("0.01"))
            printed = row["cells"]["claimed_amount"].replace(",", "")
            fmt.append(
                {
                    "row": f["row"],
                    "cells": f["cells"],
                    "printed": printed,
                    "format": str(total),
                    "result": "match" if Decimal(printed) == total else "differs",
                }
            )
        counts = collections.Counter(c["result"] for c in own)
        print(f"sources  {len(rows)} rows; the table's own arithmetic {dict(counts)}; ", end="")
        print(f"against the format {[x['result'] for x in fmt]}; {len(decided)} lines changed by the decision")
        keep = {k: t[k] for k in ("proceeding", "fiscal_year", "title", "pages", "anchors")}
        sources.append(keep | {"rows": rows, "arithmetic": own, "against_format": fmt, "decisions": decided})
    report = {
        "order": spec["order"],
        "status": (
            "read from the order's text layer, each row with its page and quote — not reviewed; "
            "the decision is the Commission's, the comparison the build's"
        ),
        "note": spec["note"],
        "tables": tables,
        "source_tables": sources,
    }
    (folder / "order-decisions.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
