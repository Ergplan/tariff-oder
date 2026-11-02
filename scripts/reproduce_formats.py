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
    load_binding_rates,
    reproduce,
    reproduce_blocks,
    reproduce_cells,
    reproduce_ledger,
    reproduce_period_table,
    reproduce_pipeline,
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


def pipeline(name: str, binding: dict, folder: Path, rules: list, sheets: dict, results: dict) -> dict:
    chain = json.loads((folder / "bindings" / binding["chain"]).read_text())
    return {"binding": name, **reproduce_pipeline(binding, chain, rules, sheets, results)}


def accounting(folder: Path, sheets: dict) -> dict | None:
    """Every format the filing's index lists, accounted for (R-ACC-3): **missing** (no sheet),
    **blank** (a sheet with no number), **present** (numbers, not read), **read** (the reference
    reads it), **reproduced** (a binding computes from or checks it) — and the sheets the index
    does not list.  Names are matched exactly or through the declared aliases, each with its
    reason; never by resemblance."""
    import re

    import openpyxl

    path = folder / "formats-index.json"
    if not path.exists():
        return None
    cfg = json.loads(path.read_text())
    wb = openpyxl.load_workbook(folder / cfg["workbook"], data_only=True, read_only=True)
    idx = wb[cfg["index_sheet"]]
    col = openpyxl.utils.column_index_from_string
    entries = []
    for r in idx.iter_rows(min_row=cfg["first_row"], values_only=True):
        name, title = r[col(cfg["name_col"]) - 1], r[col(cfg["title_col"]) - 1]
        if name:
            entries.append((str(name).strip(), str(title or "").strip()))
    norm = lambda s: re.sub(r"[^a-z0-9]", "", s.lower().replace("fy 20", "fy").replace("fy20", "fy"))  # noqa: E731
    by_norm = {norm(n): n for n in wb.sheetnames}
    used: set[str] = set()
    for b in (folder / "bindings").glob("*.json"):
        text = b.read_text()
        for n in wb.sheetnames:
            if json.dumps(n)[1:-1] in text:
                used.add(n)
    numbers = {}
    for n in wb.sheetnames:
        numbers[n] = any(
            isinstance(v, int | float) and not isinstance(v, bool)
            for row in wb[n].iter_rows(values_only=True)
            for v in row
        )
    out, listed = [], set()
    for name, title in entries:
        alias = cfg.get("aliases", {}).get(name)
        sheet = alias["sheet"] if alias else by_norm.get(norm(name))
        if sheet:
            listed.add(sheet)
        if not sheet or sheet not in wb.sheetnames:
            status = "missing"
        elif sheet in used:
            status = "reproduced"
        elif sheet in sheets:
            status = "read"
        else:
            status = "present" if numbers[sheet] else "blank"
        out.append(
            {"format": name, "title": title, "sheet": sheet, "alias_why": alias and alias["why"], "status": status}
        )
    extra = [n for n in wb.sheetnames if n not in listed and n != cfg["index_sheet"]]
    counts: dict[str, int] = {}
    for e in out:
        counts[e["status"]] = counts.get(e["status"], 0) + 1
    return {"list": cfg["list"], "formats": out, "not_in_index": extra, "counts": counts}


def coverage(ref_sheet: dict, report: dict) -> dict:
    """How each figure of the ARR format is established, column by column: **computed** by the
    chain from base records, **tied** (a schedule's binding reproduces the figure the ARR
    carries), **given** (a filed figure standing in), **differs** (a computation or tie that does
    not match), or **record** (an input nobody reproduces yet).  For the reviewer and the
    independent checker: what the reproduction covers, and what it takes on trust."""
    import collections
    import re

    letter = {(c["fiscal_year"], c["words"]): chr(65 + c["index"]) for c in ref_sheet["columns"]}
    status: dict[tuple[int, str], dict] = {}
    rank = {"differs": 4, "computed": 3, "tied": 2, "given": 1}

    def put(row: int, col: str, st: str, source: str, computed: str | None = None) -> None:
        old = status.get((row, col))
        if old and rank[old["status"]] >= rank[st]:
            return
        status[(row, col)] = {"status": st, "source": source, "computed": computed}

    for f in report["formats"]:
        if f["sheet"] != ref_sheet["sheet"]:
            continue  # the chain and the format's own identities (from the format's input rows)
        what = "chain" if f["binding"] == "chain-arr.json" else f["binding"]
        for c in f["checks"]:
            if not isinstance(c["row"], int):
                continue
            col = letter.get((c["fiscal_year"], c["words"]))
            st = {"match": "computed", "differs": "differs", "given": "given"}.get(c["result"])
            if col and st:
                put(c["row"], col, st, f"{what}: {c['output']}", c.get("computed"))
    for r in report["records"]:
        for c in r.get("checks", []):
            m = re.search(r"ARR!([A-Z])(\d+)", c.get("category", ""))
            if m and c["result"] in ("match", "differs"):
                st = "tied" if c["result"] == "match" else "differs"
                put(int(m.group(2)), m.group(1), st, f"{r['binding']}: {c['output']}", c.get("computed"))
    lines = []
    summary: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for row in ref_sheet["rows"]:
        cells = {}
        for cell in row["cells"]:
            col = letter.get((cell["fiscal_year"], cell["words"]))
            if not col:
                continue
            st = status.get((row["row"], col))
            if st is None:
                if cell.get("state") != "value":
                    continue
                st = {"status": "record", "source": None, "computed": None}
            cells[col] = {**st, "filed": cell.get("displayed")}
            summary[col][st["status"]] += 1
        if cells:
            lines.append({"row": row["row"], "label": row["label"], "line_code": row.get("line_code"), "cells": cells})
    columns = [
        {
            "column": chr(65 + c["index"]),
            "fiscal_year": c["fiscal_year"],
            "words": c["words"].strip(),
            "voice": c["voice"],
        }
        for c in ref_sheet["columns"]
    ]
    return {
        "sheet": ref_sheet["sheet"],
        "columns": columns,
        "lines": lines,
        "summary": {k: dict(v) for k, v in summary.items()},
    }


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
    results: dict[str, list] = {}  # binding → its checks, for a pipeline to feed from
    pipelines = []
    for b in sorted((folder / "bindings").glob("*.json")):
        binding = json.loads(b.read_text())
        if binding.get("type") == "pipeline":
            pipelines.append((b.name, binding))
            continue
        if binding.get("type") == "year_blocks":
            records(folder, b.name, binding, rules, sheets, report, args.verbose)
            continue
        if binding.get("type") == "row_table":
            import collections

            import openpyxl

            wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True, read_only=False)
            checks = reproduce_row_table(wb, binding, rules)
            results[b.name] = checks
            counts = dict(collections.Counter(c.result for c in checks))
            print(f"{binding['sheet'][:16]:16} {binding['fiscal_year']} {counts}")
            if args.verbose:
                for c in checks:
                    if c.result != "match" or c.category.startswith("TOTAL"):
                        what = f"{c.category[:44]:44} {c.output:20}"
                        print(f"   {c.result:8} {what} filed {c.filed} computed {c.computed} {c.why or ''}")
            report["records"].append({"binding": b.name, "checks": [asdict(c) for c in checks]})
            continue
        if binding.get("type") == "ledger":
            import collections

            import openpyxl

            wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True, read_only=False)
            others = {
                name: openpyxl.load_workbook(folder / path, data_only=True, read_only=False)
                for name, path in binding.get("workbooks", {}).items()
            }
            checks = reproduce_ledger(wb, binding, rules, others)
            results[b.name] = checks
            print(f"{binding['sheet'][:24]:24} ledger {dict(collections.Counter(c.result for c in checks))}")
            if args.verbose:
                for c in checks:
                    print(f"   {c.result:8} {c.category[:70]:70} filed {c.filed} books {c.computed} ({c.why})")
            report["records"].append({"binding": b.name, "checks": [asdict(c) for c in checks]})
            continue
        if binding.get("type") == "cells":
            import collections

            import openpyxl

            wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True, read_only=False)
            others = {
                name: openpyxl.load_workbook(folder / path, data_only=True, read_only=False)
                for name, path in binding.get("workbooks", {}).items()
            }
            # a commission order's figures, each with its page and quote (one record, or several)
            rates = load_binding_rates(folder, binding)
            checks = reproduce_cells(wb, binding, rules, others, rates)
            results[b.name] = checks
            counts = dict(collections.Counter(c.result for c in checks))
            print(f"{binding['sheet'][:24]:24} cells {counts}")
            if args.verbose:
                for c in checks:
                    if c.result != "match":
                        what = f"{c.fiscal_year} {c.category[:40]:40} {c.output:22}"
                        print(f"   {c.result:8} {what} filed {c.filed} computed {c.computed} {c.why or ''}")
            report["records"].append({"binding": b.name, "checks": [asdict(c) for c in checks]})
            continue
        if binding.get("type") == "period_table":
            import openpyxl

            wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True, read_only=False)
            checks = reproduce_period_table(wb, binding, rules)
            results[b.name] = checks
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
    report["pipeline"] = [pipeline(name, p, folder, rules, sheets, results) for name, p in pipelines]
    for p in report["pipeline"]:
        for col in p["columns"]:
            print(f"pipeline {col['fiscal_year']} {col['voice']:10} fed {len(col['fed'])} {col['counts']}")
            if args.verbose:
                for c in col["checks"]:
                    print(f"   {c['result']:8} {c['output']:28} filed {c['filed']} computed {c['computed']}")
    report["accounting"] = accounting(folder, sheets)
    if report["accounting"]:
        print("formats accounted", report["accounting"]["counts"], "not in index", report["accounting"]["not_in_index"])
    if "ARR" in sheets:
        report["coverage"] = coverage(sheets["ARR"], report)
        for c in report["coverage"]["columns"]:
            if c["voice"] in ("petitioned", "actual"):
                got = report["coverage"]["summary"].get(c["column"], {})
                print(f"coverage {c['fiscal_year']} {c['words'][:12]:12} {got}")
    (folder / "reproduction.json").write_text(json.dumps(report, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
