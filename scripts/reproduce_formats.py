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

from tariff_api.arr.reproduce import reproduce  # noqa: E402
from tariff_api.arr.rules import load_rules  # noqa: E402


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
    for b in sorted((folder / "bindings").glob("*.json")):
        binding = json.loads(b.read_text())
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
