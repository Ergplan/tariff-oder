#!/usr/bin/env python3
"""Build the reference of a filed petition from its formats workbook (milestone 13, R-ACC-1).

    uv run python scripts/build_reference.py uperc-npcl-fy2026-27 --commission UPERC

Writes, next to the workbook in `packages/reference-filings/<id>/`:
- `reference.json` — every sheet the generic reader could read: rows, proposed taxonomy
  placements, and per column the year, the voice, the stored and the displayed value, or a
  state ("included", "not_applicable").  Status **unreviewed**: a person confirms it before
  any acceptance figure is computed against it.
- `formats-inventory.json` — every form of the workbook (number, sheet, title, unit) and
  whether the generic reader read it: the filing's formats as observed in this one petition
  (R-PKG-1 evidence, not the commission's mandatory list).
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

from tariff_api.arr.reference import read_sheet  # noqa: E402
from tariff_api.arr.taxonomy import load_mapping, load_taxonomy  # noqa: E402


def main() -> int:
    import openpyxl

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--commission", required=True)
    args = ap.parse_args()
    folder = ROOT / "packages" / "reference-filings" / args.package
    (book,) = [p for p in folder.glob("*.xlsx") if "Format" in p.name]
    data = book.read_bytes()
    wb = openpyxl.load_workbook(book, data_only=True, read_only=True)
    tax, mapping = load_taxonomy(), load_mapping(args.commission, fallback=True)
    sheets, inventory = [], []
    for ws in wb.worksheets:
        vals, fmts = [], []
        for row in ws.iter_rows(max_row=min(ws.max_row or 1, 400), max_col=min(ws.max_column or 60, 60)):
            vals.append([c.value for c in row])
            fmts.append([getattr(c, "number_format", None) for c in row])
        r = read_sheet(ws.title, vals, fmts, tax, mapping)
        values = sum(1 for x in r.rows for c in x.cells if c.state == "value")
        inventory.append(
            {
                "sheet": ws.title,
                "form": r.form,
                "title": r.title,
                "unit": r.unit,
                "read_by_generic_reader": bool(r.rows),
                "rows": len(r.rows),
                "values": values,
                "years": sorted({c.fiscal_year for c in r.columns}),
                "notes": r.notes,
            }
        )
        if r.rows:
            d = asdict(r)
            d["placed"] = sum(1 for x in r.rows if x.line_code)
            sheets.append(d)
    meta = {
        "package": args.package,
        "workbook": book.name,
        "workbook_sha256": hashlib.sha256(data).hexdigest(),
        "mapping": f"{mapping.id} v{mapping.version} ({mapping.status.split(';')[0]})",
        "status": "unreviewed: machine reading of the petitioner's own spreadsheet; placements are proposals",
    }
    (folder / "reference.json").write_text(json.dumps({**meta, "sheets": sheets}, indent=1, ensure_ascii=False) + "\n")
    (folder / "formats-inventory.json").write_text(
        json.dumps({**meta, "forms": inventory}, indent=1, ensure_ascii=False) + "\n"
    )
    read = sum(1 for f in inventory if f["read_by_generic_reader"])
    vals = sum(f["values"] for f in inventory)
    print(f"{len(inventory)} forms; {read} read by the generic reader; {vals} values")
    return 0


if __name__ == "__main__":
    sys.exit(main())
