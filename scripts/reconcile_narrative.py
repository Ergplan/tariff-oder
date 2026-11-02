"""Reconcile a reference filing's narrative to its formats (R-ACC-5).

    uv run python scripts/reconcile_narrative.py uperc-npcl-fy2026-27

Reads every DOCX of the package (the narrative; untrusted data, text only) and the formats
workbook with the package's record workbooks, then writes ``narrative.json`` beside the
reference:

- ``trace``: every figure of every narrative table classified traced / near / opposite sign /
  untraced / uninformative against the workbooks' cells (``tariff_api.arr.narrative``);
- ``tables``: the explicit bindings in ``narrative/*.json`` — summary tables row by row against
  the formats — each figure ``match`` / ``differs`` / ``not_printed`` / ``no_format_value``.

It prints a summary per document and per binding.  A trace is where a figure also appears, not a
proof it is the same quantity; the reviewer decides.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr.narrative import FormatIndex, read_docx_tables, reconcile, reconcile_tables  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    args = ap.parse_args()
    import openpyxl

    folder = ROOT / "packages" / "reference-filings" / args.package
    bindings = [(b.name, json.loads(b.read_text())) for b in sorted((folder / "narrative").glob("*.json"))]
    formats = {b["workbook"] for _, b in bindings} or {"4. Appendix-II MYT Tariff Formats ARR FY 2026-27.xlsx"}
    books = {Path(w).stem: openpyxl.load_workbook(folder / w, data_only=True) for w in sorted(formats)}
    for x in sorted((folder / "records").glob("*.xlsx")):
        books[x.stem] = openpyxl.load_workbook(x, data_only=True)
    docs = sorted(folder.glob("*.docx"))
    tables = {d.name: read_docx_tables(d) for d in docs}
    trace = reconcile([t for d in docs for t in tables[d.name]], FormatIndex(books))
    # the uninformative figures are counted in the summary; listing each one adds nothing
    trace["figures"] = [f for f in trace["figures"] if f["result"] != "uninformative"]
    for doc, s in trace["summary"].items():
        print(f"{doc[:48]:48} {s}")
    out_tables = []
    for name, b in bindings:
        checks = reconcile_tables(b, books[Path(b["workbook"]).stem], tables)
        print(f"{name:32} {dict(collections.Counter(c['result'] for c in checks))}")
        out_tables.append({"binding": name, "note": b.get("note"), "checks": checks})
    report = {
        "package": args.package,
        "status": (
            "a trace says where a printed figure also appears in the formats; a binding compares a "
            "narrative row with the format cells it restates — neither decides that a figure is right"
        ),
        "documents": [d.name for d in docs],
        "trace": trace,
        "tables": out_tables,
    }
    (folder / "narrative.json").write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
