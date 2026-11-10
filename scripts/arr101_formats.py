#!/usr/bin/env python3
"""Write apps/arr-101/formats.js: the 74 formats of a real UPERC petition, for the ARR 101 walkthrough.

    uv run python scripts/arr101_formats.py

Source: NPCL's filed FY2026-27 formats workbook (packages/reference-filings/uperc-npcl-fy2026-27), a public
filing.  For each format the script MEASURES, from this repository's own records:

- entered: numeric cells no rule computes — the petitioner types them;
- computed: cells a draft rule works out from the others (the fill map), every one of them recomputed in the
  experiment below;
- checked / agree: the round-trip experiment (fill-roundtrip.json): every cell a rule computes is blanked,
  recomputed and compared with the filed figure at its printed precision.  A difference is a difference
  from DRAFT rules: it does not say the filing is
  wrong.

No figure of the petition is published — only counts.  The plain-words purpose and the step of each format are
written here by hand, from the format's title.
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api" / "src"))

from tariff_api.arr import petition as pt  # noqa: E402
from tariff_api.arr.rules import load_rules  # noqa: E402

PACKAGE = "uperc-npcl-fy2026-27"

# format code prefix → (walkthrough step, what the format is for, in plain words)
PURPOSE: list[tuple[str, str, str]] = [
    ("BS1", "filing", "The audited profit and loss account, three years. The starting point for every actual figure."),
    ("BS2", "filing", "The audited balance sheet, three years."),
    ("BS3", "filing", "The audited cash flow statement, three years."),
    ("Energy Balance", "balance", "Sales, losses and energy purchased for every year in the petition, on one page."),
    ("ARR snapshot", "arr", "The ARR year at a glance, against the last approval and the previous year."),
    ("ARR", "arr", "The summary of the whole petition: every cost head, revenue and the gap, for each year and voice."),
    ("True up-snapshot", "arr", "The true-up year at a glance: approved against actual, head by head."),
    ("APR Snapshot", "arr", "The current year at a glance: approved against the revised estimate."),
    (
        "ESR1",
        "revenue",
        "Revenue from open access customers: wheeling charges, cross-subsidy surcharge, additional surcharge.",
    ),
    ("ESR2", "sales", "Past sales, consumers and load by category, and the growth rate used to forecast them."),
    ("ESR3", "revenue", "Revenue at the current tariff, category by category and slab by slab, for one year."),
    ("ESR4A", "revenue", "The proposed rate schedule: every rate the petitioner asks for."),
    ("ESR4", "revenue", "Revenue the proposed tariff would bring, category by category."),
    ("ESR5", "sales", "Consumers, connected load, sales and revenue by category: the billing determinants."),
    ("ESR6", "revenue", "Revenue from the State Government's tariff subsidy. Blank where there is none."),
    ("ESR7", "sales", "Billing determinants month by month."),
    ("F10", "power", "Bulk supply tariff details. Blank where the licensee buys no bulk supply."),
    ("F11", "capital", "Assets taken out of use, with their cost and written-down value."),
    ("F12", "capital", "What consumers and grants paid towards assets. This part earns no depreciation or return."),
    ("F13", "capital", "The investment plan: each scheme, its cost and how it is financed."),
    ("F14", "capital", "The capital cost statement: opening assets, additions, retirements, closing assets."),
    ("F15", "capital", "Capital works in progress: spent but not yet in use, so not yet in the asset base."),
    ("F16", "capital", "Capital expenditure and capitalisation by type of project."),
    ("F17", "om", "Consumer price inflation: the index that escalates employee cost."),
    ("F18", "om", "Wholesale price inflation: the index that escalates A&G expenses."),
    ("F19A", "om", "Employee, A&G and R&M expenses built up on the norms, year by year."),
    ("F19", "om", "The base year for employee and A&G expenses: the five-year average and its escalation."),
    ("F1_", "power", "Power purchase for the year, source by source: energy, fixed, energy and other charges."),
    ("F20", "om", "Employee numbers and expenses over the years."),
    ("F21", "om", "Employee expenses component by component: salaries, allowances, terminal benefits."),
    ("F22", "om", "Repair and maintenance expenses by asset type, against the norm."),
    ("F23", "om", "Administration and general expenses component by component."),
    ("F24", "capital", "Depreciation: gross assets and accumulated depreciation by asset class, year by year."),
    ("F25", "capital", "Interest on the normative loan: opening, addition, repayment, average, rate, interest."),
    ("F26", "capital", "Return on equity: opening, addition, average equity and the return."),
    ("F27", "wc", "Working capital requirement and the interest on it."),
    ("F28", "wc", "Non-tariff income, item by item."),
    ("F29", "capital", "Income tax: the tax on the return on equity."),
    ("F2_", "power", "The assumptions behind the power purchase projection, in words."),
    ("F30A", "wc", "Consumer security deposits held, and the interest paid on them."),
    ("F30", "wc", "Consumer security deposits month by month for the true-up year."),
    ("F31", "wc", "Receivables from consumers."),
    ("F32", "arr", "The ARR split between the wires (wheeling) business and the supply business."),
    ("F33", "arr", "The cross-subsidy surcharge worked out for open access consumers."),
    ("F3_", "power", "Power purchase month by month and station by station, for one year."),
    ("F4_", "power", "Merit order despatch: sources ranked by cost, and how much is taken from each."),
    ("F5_", "power", "Renewable energy bought, agreement by agreement."),
    ("F6_", "power", "The renewable purchase obligation: required against met."),
    ("F7_", "power", "Power bought through competitive bidding in the true-up year."),
    ("F8_", "power", "Short-term power purchases: seller, period, quantity, cost."),
    ("F9_", "power", "The power procurement plan in MW: long, medium and short term, month by month."),
    (
        "PPC",
        "power",
        "The power purchase cost sheet for one year: every supplier's energy, losses, charges and cost per unit.",
    ),
    ("P10", "checks", "Court and regulatory cases pending on the date of filing."),
    ("P11", "capital", "Land owned: each parcel, its area and value."),
    ("P1A", "balance", "Distribution losses separately for the high-voltage and low-voltage systems."),
    ("P1_", "balance", "Distribution loss claimed against approved, year by year."),
    ("P2_", "sales", "Average hours of supply a day, by category."),
    ("P3_", "wc", "Bad debts, write-offs and provisions."),
    ("P4_", "capital", "The network in numbers: line lengths, substations, transformers, added and withdrawn."),
    ("P5_", "wc", "Revenue arrears: opening, billed, collected, closing."),
    ("P6_", "checks", "Consumer complaints received and resolved."),
    ("P7_", "checks", "Transformer failures as a share of transformers installed."),
    ("P8_", "checks", "Electrical accidents, fatal and non-fatal."),
    ("P9_", "sales", "Peak demand in MW."),
]
STATUS = {
    "reproduced": "checked",
    "no_arithmetic": "no arithmetic",
    "blank": "filed blank",
    "missing": "not filed",
}


def tidy(title: str) -> str:
    return title.replace("INR_crore", "Rs crore").replace("INR_lakh", "Rs lakh")


def purpose(code: str) -> tuple[str, str]:
    for prefix, step, text in PURPOSE:
        if code.startswith(prefix):
            return step, text
    raise SystemExit(f"no purpose written for format {code!r}")


def main() -> int:
    p = pt._package(PACKAGE)
    rules = {r.output: r.title for r in load_rules("UPERC")}
    rep = json.loads((p["folder"] / "reproduction.json").read_text())
    inputs, _ = pt._inputs_of_filing(PACKAGE)

    def sheet_of(cell: str) -> str:
        return cell.rpartition("!")[0]

    n_inputs = collections.Counter(sheet_of(c) for c in inputs)
    n_map = collections.Counter(sheet_of(c) for c in p["map"])
    outputs: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for cell, v in p["map"].items():
        outputs[sheet_of(cell)][v["output"]] += 1
    # the round-trip experiment (fill-roundtrip.json, run "none_kept"): every fill-map cell blanked,
    # recomputed by the rules and compared with the filed figure at its printed precision
    trip = json.loads((p["folder"] / "fill-roundtrip.json").read_text())["runs"]["none_kept"]
    n_differ = collections.Counter(sheet_of(d["cell"]) for d in trip["differing"])
    assert trip["targets"] == len(p["map"]) and not trip["blank"]

    out, seen_sheets = [], set()
    index = list(rep["accounting"]["formats"])
    # a working sheet of the workbook that the petition's own index does not list
    index.append(
        {
            "format": "F19A-O&M Normative",
            "title": "O&M expenses on the norms (a working sheet, not in the petition's index)",
            "sheet": "F19A-O&M Normative",
            "status": "reproduced",
            "why": None,
        }
    )
    for a in index:
        code, sheet = a["format"], a["sheet"]
        step, text = purpose(code)
        first = sheet not in seen_sheets  # two index entries can name one sheet: count it once
        seen_sheets.add(sheet)
        s = sheet if (sheet and first) else None
        checked = n_map.get(s, 0) if s else 0
        agree = checked - (n_differ.get(s, 0) if s else 0)
        out.append(
            {
                "code": code,
                "title": " ".join(a["title"].split()),
                "step": step,
                "purpose": text,
                "status": STATUS[a["status"]],
                "why": a.get("why"),
                "entered": n_inputs.get(s, 0) if s else 0,
                "computed": n_map.get(s, 0) if s else 0,
                "checked": checked,
                "agree": agree,
                "sameSheetAs": None if first or not sheet else sheet.strip(),
                "computes": [tidy(rules.get(o, o)) for o, _ in outputs.get(s, collections.Counter()).most_common(4)]
                if s
                else [],
            }
        )
    totals = {k: sum(f[k] for f in out) for k in ("entered", "computed", "checked", "agree")}
    assert totals["checked"] == trip["targets"] and totals["agree"] == trip["reproduced"], (totals, trip["reproduced"])
    doc = {
        "source": "The formats workbook of a filed petition: Noida Power Company Limited (NPCL), Uttar Pradesh, "
        "true-up FY 2024-25, APR FY 2025-26, ARR FY 2026-27. A public filing.",
        "method": "Counts measured from that workbook by this project's draft rules. Entered: numeric cells the "
        "petitioner types. Worked out: cells a rule computes from the others. Experiment: every worked-out cell was "
        "blanked, recomputed by the rules and compared with the filed figure at its printed precision.",
        "caveat": "The rules are drafts, not approved by anyone. A recomputed figure that does not match is a "
        "difference from a draft rule; it does not say the filing is wrong. No figure of the petition is "
        "shown here, only counts.",
        "totals": {"formats": len(out) - 1, "workingSheets": 1, **totals},
        "formats": out,
    }
    body = json.dumps(doc, indent=1, ensure_ascii=False)
    (ROOT / "apps" / "arr-101" / "formats.js").write_text(
        "// Generated by scripts/arr101_formats.py — do not edit by hand.\nexport const FORMATS = " + body + ";\n"
    )
    by_step = collections.Counter(f["step"] for f in out)
    print(doc["totals"], dict(by_step), collections.Counter(f["status"] for f in out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
