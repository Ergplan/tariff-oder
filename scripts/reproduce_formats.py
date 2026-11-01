#!/usr/bin/env python3
"""Reproduce a reference filing's bound formats through the commission's rules (milestone 13).

    uv run python scripts/reproduce_formats.py uperc-npcl-fy2026-27 --commission UPERC

For each `bindings/*.json` of the filing: every column of the format is computed from its input
rows through the rules of that year and compared with the filed figures.  Writes
`reproduction.json` beside the reference and prints a summary per format.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr.blocks import read_year_blocks  # noqa: E402
from tariff_api.arr.reproduce import (  # noqa: E402
    reproduce,
    reproduce_blocks,
    reproduce_period_table,
    reproduce_row_table,
)
from tariff_api.arr.rules import load_rules  # noqa: E402


def records(folder, name, binding, rules, sheets, report, verbose) -> None:
    """A utility's year-block workings (e.g. depreciation by vintage and asset class), reproduced
    class by class, and their net tied to the filed ARR format's line where the binding says so."""
    import collections
    from decimal import Decimal

    import openpyxl

    wb = openpyxl.load_workbook(folder / binding["record"], data_only=True, read_only=True)
    net: dict[str, Decimal] = collections.defaultdict(Decimal)
    for sh in binding["sheets"]:
        blocks = read_year_blocks([list(r) for r in wb[sh].iter_rows(values_only=True)])
        checks = reproduce_blocks(blocks, binding, rules)
        counts = dict(collections.Counter(c.result for c in checks))
        print(f"{sh[:30]:30} {len(blocks):2} blocks  {counts}")
        if verbose:
            for c in checks:
                if c.result != "match":
                    what = f"{c.fiscal_year} {c.category[:28]:28} {c.output:24}"
                    print(f"   {c.result:12} {what} filed {c.filed} computed {c.computed} {c.why or ''}")
        report["records"].append(
            {"binding": name, "sheet": sh, "counts": counts, "checks": [asdict(c) for c in checks]}
        )
        for bl in blocks:
            sign = -1 if "contribution" in bl.title.lower() else 1
            net[bl.fiscal_year] += sign * Decimal(bl.totals.get(binding.get("net", {}).get("total", "gross_dep"), "0"))
    tie = binding.get("ties_to")
    if tie:
        (row,) = [r for r in sheets[tie["sheet"]]["rows"] if r["line_code"] == tie["line_code"]]
        for c in row["cells"]:
            if tie.get("to_fy") and c["fiscal_year"] > tie["to_fy"]:
                continue  # the binding says which years the workings are the filed figures for
            if c["voice"] in tie["voices"] and c["fiscal_year"] in net and c["displayed"]:
                got = net[c["fiscal_year"]].quantize(Decimal("0.01"))
                ok = got == Decimal(c["displayed"])
                where = f"{tie['sheet']} {tie['line_code']} {c['fiscal_year']} {c['words'].strip()[:12]:12}"
                print(f"   ties to {where}: working {got} filed {c['displayed']} {'match' if ok else 'DIFFERS'}")
                report["records"].append(
                    {
                        "tie": f"{tie['sheet']} {tie['line_code']}",
                        "fiscal_year": c["fiscal_year"],
                        "words": c["words"],
                        "working": str(got),
                        "filed": c["displayed"],
                        "result": "match" if ok else "differs",
                    }
                )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--commission", required=True)
    ap.add_argument("-v", "--verbose", action="store_true", help="print every check that is not a match")
    args = ap.parse_args()
    folder = ROOT / "packages" / "reference-filings" / args.package
    ref = json.loads((folder / "reference.json").read_text())
    sheets = {s["sheet"]: s for s in ref["sheets"]}
    rules = load_rules(args.commission)
    report = {"package": args.package, "reference_status": ref["status"], "formats": []}
    report["records"] = []
    for b in sorted((folder / "bindings").glob("*.json")):
        binding = json.loads(b.read_text())
        if binding.get("type") == "year_blocks":
            records(folder, b.name, binding, rules, sheets, report, args.verbose)
            continue
        if binding.get("type") == "row_table":
            import collections

            import openpyxl

            wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True, read_only=False)
            checks = reproduce_row_table(wb, binding, rules)
            counts = dict(collections.Counter(c.result for c in checks))
            print(f"{binding['sheet'][:16]:16} {binding['fiscal_year']} {counts}")
            if args.verbose:
                for c in checks:
                    if c.result != "match" or c.category.startswith("TOTAL"):
                        what = f"{c.category[:44]:44} {c.output:20}"
                        print(f"   {c.result:8} {what} filed {c.filed} computed {c.computed} {c.why or ''}")
            report["records"].append({"binding": b.name, "checks": [asdict(c) for c in checks]})
            continue
        if binding.get("type") == "period_table":
            import openpyxl

            wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True, read_only=False)
            checks = reproduce_period_table(wb, binding, rules)
            for c in checks:
                what = f"{binding['sheet'][:16]:16} {c.fiscal_year} {c.output:22} {c.result:8}"
                print(f"{what} filed {c.filed} computed {c.computed}")
            report["records"].append({"binding": b.name, "checks": [asdict(c) for c in checks]})
            continue
        rep = reproduce(sheets[binding["sheet"]], binding, rules, sheets)
        report["formats"].append(
            {
                "binding": b.name,
                "sheet": rep.sheet,
                "columns": rep.columns,
                "counts": rep.counts(),
                "checks": [asdict(c) for c in rep.checks],
            }
        )
        print(f"{rep.sheet:16} {rep.columns:2} columns  {rep.counts()}")
        if args.verbose:
            for c in rep.checks:
                if c.result != "match":
                    what = f"{c.fiscal_year} {c.voice:13} {c.output:26}"
                    print(f"   {c.result:12} {what} filed {c.filed} computed {c.computed}  {c.why or ''}")
    (folder / "reproduction.json").write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
