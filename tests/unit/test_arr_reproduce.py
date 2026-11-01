"""Reproducing a filed format through the rules (milestone 13).  The first test is SYNTHETIC; the
second reproduces NPCL's real filed formats from the reference in packages/reference-filings
(no database: the reference and the rules are files)."""

from __future__ import annotations

import json
from pathlib import Path

from tariff_api.arr.reference import unit_word
from tariff_api.arr.reproduce import reproduce
from tariff_api.arr.rules import Rule

ROOT = Path(__file__).resolve().parents[2]


def _cell(fy, voice, value, displayed, unit="INR_crore", state="value"):
    return {
        "fiscal_year": fy,
        "voice": voice,
        "words": voice,
        "restated": False,
        "value": value,
        "displayed": displayed,
        "state": state,
        "printed": displayed or "NA",
        "unit": unit,
        "percent_from_fraction": False,
    }


def test_match_differs_blocked_and_states():
    double = Rule.model_validate(
        {
            "id": "dbl",
            "version": 1,
            "title": "double",
            "output": "y",
            "unit": "INR_crore",
            "formula": "x * 2",
            "inputs": {"x": {"unit": "INR_crore", "source": "record:x"}},
            "clause": {"regulation": "Synthetic Regulations, 2030"},
            "applies": {"commission": "SYNTHERC", "from_fy": "FY2030-31"},
        }
    )
    sheet = {
        "sheet": "S",
        "rows": [
            {
                "row": 5,
                "label": "x",
                "unit": "INR_crore",
                "cells": [
                    _cell("FY2030-31", "petitioned", "1.004", "1.00"),
                    _cell("FY2031-32", "petitioned", "2", "2.00"),
                    _cell("FY2029-30", "approved", "3", "3.00"),
                    _cell("FY2032-33", "petitioned", None, None, state="included"),
                ],
            },
            {
                "row": 6,
                "label": "y",
                "unit": "INR_crore",
                "cells": [
                    _cell("FY2030-31", "petitioned", "2.008", "2.01"),
                    _cell("FY2031-32", "petitioned", "4.5", "4.50"),
                    _cell("FY2029-30", "approved", "6", "6.00"),
                    _cell("FY2032-33", "petitioned", None, None, state="not_applicable"),
                ],
            },
        ],
    }
    rep = reproduce(sheet, {"sheet": "S", "inputs": {"record:x": 5}, "outputs": {"y": 6}}, [double])
    got = {(c.fiscal_year, c.result) for c in rep.checks}
    assert got == {
        ("FY2030-31", "match"),
        ("FY2031-32", "differs"),
        ("FY2029-30", "blocked"),
        ("FY2032-33", "not_a_value"),
    }
    blocked = next(c for c in rep.checks if c.result == "blocked")
    assert "no rule for y applies in FY2029-30" in blocked.why  # the rule's years, not a default


def test_units_column_words():
    assert unit_word("MU") == "MU" and unit_word("%") == "percent" and unit_word("Rs. Crore") == "INR_crore"
    assert unit_word("Rs/kWh") == "INR_per_kWh" and unit_word("tonnes") is None


def test_npcl_filed_formats_are_reproduced_by_the_draft_rules():
    """Regression on real data: NPCL's FY2026-27 filed formats, every column, from their input
    rows through the UPERC draft rules.  The Energy Balance and F14 (capital cost) reproduce in
    full.  F25 and F26 take their additions and reductions from F14's inputs (cross-format):
    every column F14 covers matches, except FY2023-24 "Claimed", where NPCL's F25/F26 carry
    figures that are not F14's (equity added 21.21 against 30 % of F14's net capitalisation,
    22.73) — a cross-schedule inconsistency in the filing, for the reviewer (R-SCH-16, ledger
    A29).  Columns F14 does not have (FY2022-23; the Commission's approval) are blocked."""
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    ref = json.loads((folder / "reference.json").read_text())
    sheets = {s["sheet"]: s for s in ref["sheets"]}
    rules = load_rules("UPERC")
    seen = {}
    for b in sorted((folder / "bindings").glob("*.json")):
        binding = json.loads(b.read_text())
        if binding.get("type") in ("year_blocks", "period_table"):
            continue  # the utility's workings and the rate table: their own tests
        rep = reproduce(sheets[binding["sheet"]], binding, rules, sheets)
        seen["chain" if b.name == "chain-arr.json" else rep.sheet] = rep
        for c in rep.checks:
            col = (c.fiscal_year, c.voice)
            if b.name == "chain-arr.json":
                # the chain from base records: the petition's three columns in full (12 / 12 each);
                # FY2023-24 carries the filing's own F14 / F25 / F26 inconsistency (A29); a Commission
                # column is never fed a petitioner's figure (blocked, never differs — A36)
                if col in (("FY2024-25", "petitioned"), ("FY2025-26", "petitioned"), ("FY2026-27", "petitioned")):
                    assert c.result == "match", c
                elif col[1] == "approved":
                    assert c.result in ("blocked", "no_filed_value", "match"), c
                continue
            if rep.sheet == "ARR":
                # the petition's own columns (estimated, projected) reproduce in full; differences
                # are the Commission's restated approvals (a surplus carried at the full rate —
                # ledger A35 — and figures typed from rounded parts), NPCL's audited FY2023-24
                # carrying cost copied from the claimed column, and one half-boundary rounding
                if c.result == "differs":
                    assert c.voice in ("approved", "actual") or (c.fiscal_year, c.output) == (
                        "FY2023-24",
                        "arr_gap_cumulative",
                    ), c
                elif c.result == "blocked":
                    assert c.fiscal_year == "FY2021-22", c
                else:
                    assert c.result == "match", c
                if c.fiscal_year in ("FY2025-26", "FY2026-27") and c.voice == "petitioned":
                    assert c.result == "match", c
                continue
            if rep.sheet in ("F17_O&M_CPI", "F18_O&M_WPI", "F19A-O&M Normative"):
                # O&M: nothing differs; blocked only where the sheet lacks the inputs (escalations
                # before three increases exist, projected years without a monthly index, and the
                # FY2020-21 base whose previous year the format prints under formula words)
                assert c.result in ("match", "blocked", "no_filed_value"), (rep.sheet, c)
                continue
            if rep.sheet == "F27_Work Cap":
                # receivables of a true-up year are the petitioner's record (given); the restated
                # FY2022-23 true-up uses an O&M the ARR format does not (13.46 vs 159.88 / 12); the
                # Commission's FY2025-26 approval takes receivables on tariff revenue alone; the
                # FY2024-25 audited surplus is blank in the filing (ledger A32)
                if c.result == "differs":
                    assert col in (("FY2022-23", "final_true_up"), ("FY2025-26", "approved")), c
                elif c.result == "blocked":
                    assert col == ("FY2024-25", "actual"), c
                else:
                    assert c.result in ("match", "given"), c
                continue
            if c.result == "differs":
                assert rep.sheet in ("F25_IOL", "F26_ROE") and col == ("FY2023-24", "petitioned"), (rep.sheet, c)
            elif c.result == "blocked":
                assert rep.sheet in ("F25_IOL", "F26_ROE") and (col[0] == "FY2022-23" or col[1] == "approved"), (
                    rep.sheet,
                    c,
                )
            else:
                assert c.result == "match", (rep.sheet, c)
    assert seen["Energy Balance"].counts() == {"match": 55}
    assert seen["F14_CAP_Cap Cost"].counts() == {"match": 60}
    assert seen["F27_Work Cap"].counts()["match"] >= 34
    assert seen["ARR"].counts()["match"] >= 106
    assert seen["F29_Income Tax"].counts() == {"match": 24}
    assert seen["chain"].counts()["match"] >= 56
    assert seen["F17_O&M_CPI"].counts()["match"] >= 15 and seen["F18_O&M_WPI"].counts()["match"] >= 15
    assert seen["F25_IOL"].counts()["match"] >= 21 and seen["F26_ROE"].counts()["match"] >= 22


def test_year_blocks_are_read_by_their_headers_and_blanks_stay_absent():
    from tariff_api.arr.blocks import read_year_blocks

    rows = [
        [None, "Depreciation for", None, "FY 2020-21", None, None, None, None, "Depreciation for", None, "FY 2021-22"],
        [
            None,
            "S.No.",
            "Particulars",
            "Opening GFA",
            "Addition to GFA",
            "Depreciation Rate",
            "Allowable Gross Dep",
            None,
            "S.No.",
            "Particulars",
            "Balance Depreciable value",
            "Addition to GFA",
            "Depreciation Rate",
            "Allowable Gross Dep",
        ],
        [None, 1, "Lines & Cables", 0, 60.87, 0.0528, 1.607, None, 1, "Lines & Cables", 60.87, 146.6, 0.0528, 7.08],
        [None, 2, "Vehicles", 0, None, 0.095, 0, None, 2, "Vehicles", 0, 1.58, 0.095, 0.075],
        [
            None,
            10,
            "Total Fixed Assets",
            0,
            60.87,
            None,
            1.607,
            None,
            10,
            "Total Fixed Assets",
            60.87,
            148.18,
            None,
            7.155,
        ],
    ]
    a, b = read_year_blocks(rows)
    assert (a.fiscal_year, b.fiscal_year) == ("FY2020-21", "FY2021-22")
    assert b.columns["opening_gfa"] == 11  # "Balance Depreciable value" is the opening, by its words
    assert "additions" not in a.rows[1].values  # a blank is absent, never zero
    assert a.totals["gross_dep"] == "1.607" and len(a.rows) == 2


def test_npcl_depreciation_workings_reproduce_and_tie_to_the_filed_arr():
    """Real data: NPCL's depreciation workings (Annexure-21), by vintage and asset class, own and
    consumer-contribution assets, FY2020-21 to FY2026-27, through the draft depreciation rules.
    Post-2020 assets reproduce in full; pre-2020 assets except land (NPCL excludes non-depreciable
    land rights from the base — a class exception the draft rule does not have), one office-
    equipment year, and two classes with no rate.  The net (own − contribution) equals the ARR
    format's depreciation in every true-up year."""
    import collections
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.blocks import read_year_blocks
    from tariff_api.arr.reproduce import reproduce_blocks
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "records-annexure-21-depreciation.json").read_text())
    wb = openpyxl.load_workbook(folder / binding["record"], data_only=True, read_only=True)
    rules = load_rules("UPERC")
    net: dict[str, Decimal] = collections.defaultdict(Decimal)
    results = {}
    for sh in binding["sheets"]:
        blocks = read_year_blocks([list(r) for r in wb[sh].iter_rows(values_only=True)])
        checks = reproduce_blocks(blocks, binding, rules)
        results[sh] = checks
        for bl in blocks:
            net[bl.fiscal_year] += (-1 if "contribution" in bl.title.lower() else 1) * Decimal(bl.totals["gross_dep"])
    after, before = results["Depreciation after 1 Apr 20-25"], results["Depreciation before 1 Apr 2020"]
    assert all(c.result == "match" for c in after) and len(after) == 686
    for c in before:
        if c.result == "differs":
            assert c.category in ("Land", "Office Equipments", "TOTAL"), c
        elif c.result == "blocked":
            assert "rate" in (c.why or "") or "depreciation_class" in (c.why or ""), c
    assert sum(c.result == "match" for c in before) >= 672
    filed = {
        "FY2021-22": "56.37",
        "FY2022-23": "62.09",
        "FY2023-24": "66.33",
        "FY2024-25": "74.75",
    }  # ARR format, C.DEP
    assert {fy: str(net[fy].quantize(Decimal("0.01"))) for fy in filed} == filed


def test_npcl_reference_rates_from_the_mclr_revisions():
    """Real data: the SBI MCLR revisions NPCL lists under F27, weighted by days, give the
    weighted MCLR it prints (FY2024-25, FY2025-26), the true-up working-capital rate (+2.5 %) and
    the normative-loan rate F25 uses (+1 %), to six decimals."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_period_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "f27-mclr-rates.json").read_text())
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_period_table(wb, binding, load_rules("UPERC"))
    assert [(c.fiscal_year, c.output, c.result) for c in checks] == [
        ("FY2024-25", "mclr_weighted", "match"),
        ("FY2024-25", "wc_rate_trueup", "match"),
        ("FY2025-26", "mclr_weighted", "match"),
        ("FY2025-26", "loan_rate_reference", "match"),
    ]
