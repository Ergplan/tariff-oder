#!/usr/bin/env python3
"""Fill a petition's formats workbook with the rule engine (tariff_api.arr.petition_fill).

    uv run python scripts/petition_fill.py map uperc-npcl-fy2026-27 --commission UPERC
        writes packages/reference-filings/<id>/fill-map.json — the cells a fill writes
    uv run python scripts/petition_fill.py template uperc-npcl-fy2026-27 --commission UPERC -o inputs.xlsx
        the filed workbook with every fill-map cell blanked: what a petitioner enters
    uv run python scripts/petition_fill.py fill uperc-npcl-fy2026-27 --commission UPERC -i inputs.xlsx -o filled.xlsx
        fills a workbook laid out as the filing (shaded cells, a 'Fill trace' sheet) and writes the report
    uv run python scripts/petition_fill.py roundtrip uperc-npcl-fy2026-27 --commission UPERC
        template → fill → compare with the filing, twice: with the cells whose reproduction already
        differs from the filing kept as filed (what the fill itself does) and with none kept; writes
        fill-roundtrip.json

A filled workbook is a working draft from draft rules: nothing verified, approved or filed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr import petition_fill as pf  # noqa: E402
from tariff_api.arr.rules import load_rules  # noqa: E402


def _workbook(folder: Path) -> Path:
    (book,) = [p for p in folder.glob("*.xlsx") if "Format" in p.name]
    return book


def main() -> int:
    import openpyxl

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["map", "template", "fill", "roundtrip"])
    ap.add_argument("package")
    ap.add_argument("--commission", required=True)
    ap.add_argument("-i", "--input", type=Path)
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args()
    folder = ROOT / "packages" / "reference-filings" / args.package
    rules = load_rules(args.commission)
    layout = json.loads((folder / "reference.json").read_text())
    bindings, skipped = pf.fill_bindings(folder)
    book = _workbook(folder)
    if args.command == "map":
        fmap = pf.fill_map(
            openpyxl.load_workbook(book, data_only=True), openpyxl.load_workbook(book), layout, bindings, rules
        )
        doc = {
            "package": args.package,
            "workbook": book.name,
            "status": "derived from the filed workbook by the draft rules: the cells a fill writes; nothing reviewed",
            "bindings": [n for n, _ in bindings],
            "skipped": skipped,
            "cells": fmap,
        }
        (folder / "fill-map.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
        kinds = {k: sum(v["kind"] == k for v in fmap.values()) for k in ("computed", "carried")}
        print(f"fill map: {len(fmap)} cells {kinds}; {len(bindings)} bindings run, {len(skipped)} left out")
        return 0
    fmap = json.loads((folder / "fill-map.json").read_text())["cells"]
    if args.command == "template":
        wb = pf.inputs_template(openpyxl.load_workbook(book, data_only=True), fmap)
        args.output.write_bytes(pf.to_bytes(wb))
        print(f"{args.output}: {len(fmap)} cells blanked")
        return 0
    if args.command == "fill":
        wb = openpyxl.load_workbook(args.input, data_only=True)
        rep = pf.fill(wb, layout, bindings, rules, args.package, targets=set(fmap))
        pf.mark(wb, rep)
        args.output.write_bytes(pf.to_bytes(wb))
        args.output.with_suffix(".report.json").write_text(
            json.dumps(rep.as_dict(), indent=1, ensure_ascii=False) + "\n"
        )
        print(json.dumps({k: v for k, v in rep.summary().items() if k != "by_sheet"}))
        return 0
    out = pf.round_trip(_workbook(folder), rules, layout, bindings, fmap, folder.name)
    (folder / "fill-roundtrip.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n")
    for label, r in out["runs"].items():
        print(
            f"{label}: {r['reproduced']} / {r['targets']} reproduced, {r['differs']} differ, "
            f"{r['not_filled']} not filled, {len(r['conflicts'])} conflicts, {r['passes']} passes"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
