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
        if binding.get("type") in ("year_blocks", "period_table", "row_table", "cells", "pipeline", "ledger"):
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
            if rep.sheet == "F22_O&M_R&M after FY25" and c.result == "not_a_value":
                # no GNIDA hand-over assets yet in FY2025-26: NPCL prints a dash, read as no value
                assert (c.fiscal_year, c.row, c.filed) == ("FY2025-26", 15, "-"), c
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
    assert seen["ARR"].counts()["match"] >= 128
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


def test_npcl_power_purchase_by_source_reproduces_the_totals():
    """Real data: NPCL's power purchase summaries (PPC FY 26, FY 27), one row per source, through
    the draft rules: every per-source figure and the totals that are the ARR's power purchase and
    transmission lines; a source with no energy (REC certificates) has no rate — blocked, not 0."""
    import collections

    import openpyxl

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    wb = None
    for name, expect_totals in (
        ("ppc-fy27.json", {"pp_cost_total": "2448.33", "pp_tx_total": "446.36"}),
        ("ppc-fy26.json", {"pp_cost_total": "2239.68", "pp_tx_total": "389.77"}),
    ):
        binding = json.loads((folder / "bindings" / name).read_text())
        wb = wb or openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
        checks = reproduce_row_table(wb, binding, rules)
        counts = collections.Counter(c.result for c in checks)
        assert counts["differs"] == 0, [c for c in checks if c.result == "differs"][:3]
        for c in checks:
            if c.result == "blocked":
                assert c.output == "pp_rate" and c.why == "division by zero", c
        totals = {c.output: c.computed for c in checks if c.category.startswith("TOTAL")}
        assert {k: totals[k] for k in expect_totals} == expect_totals


def test_npcl_om_of_the_apr_and_arr_years_from_the_2025_base_year():
    """Real data: NPCL's base-year determination (F19 EE n AG base) through the draft 2025-regime
    rules — A&G less finance charges, the five-year average as the middle year, the CPI / WPI
    escalation year by year, the growth factors and the employee and A&G expenses of FY2025-26
    and FY2026-27, each checked on the sheet and where F21, F23 and the ARR format carry it; the
    R&M of the same years ties to the ARR's row 26."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    base = json.loads((folder / "bindings" / "f19-om-base-2025.json").read_text())
    wb = openpyxl.load_workbook(folder / base["workbook"], data_only=True)
    checks = reproduce_cells(wb, base, rules)
    assert [c for c in checks if c.result != "match"] == []
    assert len(checks) == 40
    arr = {(c.fiscal_year, c.output): c.computed for c in checks if c.category.endswith(("27", "31"))}
    assert arr == {
        ("FY2025-26", "om25_employee"): "95.627439",
        ("FY2026-27", "om25_employee"): "99.978446",
        ("FY2025-26", "om25_ag"): "28.752731",
        ("FY2026-27", "om25_ag"): "29.250923",
    }
    ties = json.loads((folder / "bindings" / "f22-rm-ties.json").read_text())
    rm = reproduce_cells(wb, ties, rules)
    assert [(c.fiscal_year, c.category, c.result) for c in rm] == [
        ("FY2025-26", "R&M G16", "match"),
        ("FY2025-26", "R&M ARR!L26", "match"),
        ("FY2026-27", "R&M H16", "match"),
        ("FY2026-27", "R&M ARR!M26", "match"),
    ]


def test_cells_a_blank_input_blocks_and_a_blank_filed_cell_is_no_value():
    """The cell reader: a blank input is absent (the output blocks with its reason), never 0."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "S"
    ws["A1"], ws["B1"], ws["C1"] = 10.0, None, 9.0
    ws["A2"] = 0.1
    binding = {
        "sheet": "S",
        "evaluations": [
            {
                "fiscal_year": "FY2025-26",
                "inputs": {"prior:om25_level": ["A1", "INR_crore"], "assumption:om25_index_change": ["A2", "fraction"]},
                "checks": {"om25_escalated": ["C1", "B1"]},
            },
            {
                "fiscal_year": "FY2025-26",
                "inputs": {"prior:om25_level": ["B1", "INR_crore"], "assumption:om25_index_change": ["A2", "fraction"]},
                "checks": {"om25_escalated": "C1"},
            },
        ],
    }
    got = [(c.category, c.result, c.computed) for c in reproduce_cells(wb, binding, load_rules("UPERC"))]
    assert got[0] == ("C1", "differs", "11.000000")
    assert got[1] == ("B1", "no_filed_value", "11.00")
    assert got[2][:2] == ("C1", "blocked")


def test_npcl_depreciation_by_class_rolls_forward_and_ties_to_the_arr():
    """Real data: F24 by asset class, five years.  FY2022-23 prints each class's rate, so its
    depreciation is computed (average gross block × rate); later years type the year's figure,
    taken as given (ledger A39: the projection years' working is not in the filing).  Every
    closing gross block and accumulated depreciation, the implied rate, the total and the net of
    consumer contribution match, and the net is the ARR's row 36 in every year.  A class with no
    gross block has no rate: blocked, never 0."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    wb = None
    net = {}
    for yy in ("23", "24", "25", "26", "27"):
        binding = json.loads((folder / "bindings" / f"f24-dep-fy{yy}.json").read_text())
        wb = wb or openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
        checks = reproduce_row_table(wb, binding, rules)
        for c in checks:
            if c.result == "blocked":
                assert c.output == "depreciation_rate_implied" and c.why == "division by zero", c
            else:
                assert c.result == "match", c
        if yy == "23":
            assert sum(1 for c in checks if c.output == "depreciation_class" and c.result == "match") == 17
        net[binding["fiscal_year"]] = {c.category: c.computed for c in checks if c.output == "depreciation_net"}
    assert {fy: v[next(k for k in v if "ARR" in k)] for fy, v in net.items()} == {
        "FY2022-23": "62.0887",
        "FY2023-24": "66.3275",
        "FY2024-25": "74.7480",
        "FY2025-26": "90.0943",
        "FY2026-27": "106.7518",
    }


def test_npcl_security_deposit_interest_bad_debts_and_receivables():
    """Real data: interest on security deposit month by month (FY2024-25) and on the year's
    average (FY2025-26, FY2026-27, at the 6.5 % stated in NPCL's formula); receivables, bad debts
    and other items (F31, P3).  Everything matches except the true-up year's March interest, which
    NPCL types (1.8901) where its own formula gives 2.0802 — so the year's total is 24.79, not the
    24.98 the balances give (ledger A40, for the reviewer)."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    isd = json.loads((folder / "bindings" / "f30-security-deposit.json").read_text())
    wb = openpyxl.load_workbook(folder / isd["workbook"], data_only=True)
    checks = reproduce_cells(wb, isd, rules)
    differs = [c for c in checks if c.result != "match"]
    assert {(c.category, c.computed) for c in differs} == {
        ("ISD Mar 2025 M10", "2.0802"),
        ("ISD N10", "24.9801"),
        ("ISD F30A_CSD!H22", "24.9801"),
        ("ISD F25_IOL!G16", "24.9801"),
        ("ISD ARR!J38", "24.9801"),
    }
    assert {(c.fiscal_year, c.category, c.computed) for c in checks if "ARR" in c.category and c.result == "match"} == {
        ("FY2025-26", "ISD ARR!L38", "23.2629"),
        ("FY2026-27", "ISD ARR!M38", "24.2379"),
    }
    bd = json.loads((folder / "bindings" / "p3-bad-debts.json").read_text())
    checks = reproduce_cells(wb, bd, rules)
    assert [c for c in checks if c.result != "match"] == []
    arr = {(c.fiscal_year, c.output): c.computed for c in checks if "ARR!" in c.category}
    assert arr[("FY2025-26", "bad_debts_claimed")] == "12.4390"
    assert arr[("FY2026-27", "bad_debts_claimed")] == "13.7640"
    assert arr[("FY2024-25", "other_items")] == "5.4278"


def test_cells_constants_need_a_reason_and_declared_blanks_are_zero():
    import openpyxl
    import pytest

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "S"
    ws["A1"], ws["C1"] = 10.0, 11.0
    rate = {"value": "0.1", "unit": "fraction"}
    binding = {
        "sheet": "S",
        "evaluations": [
            {
                "fiscal_year": "FY2025-26",
                "inputs": {"prior:om25_level": ["A1", "INR_crore"], "assumption:om25_index_change": rate},
                "checks": {"om25_escalated": "C1"},
            }
        ],
    }
    with pytest.raises(ValueError, match="reason"):
        reproduce_cells(wb, binding, load_rules("UPERC"))
    rate["why"] = "a literal in the utility's formula"
    assert [c.result for c in reproduce_cells(wb, binding, load_rules("UPERC"))] == ["match"]
    binding["evaluations"][0]["inputs"]["prior:om25_level"] = {"cell": "B1", "unit": "INR_crore"}
    assert [c.result for c in reproduce_cells(wb, binding, load_rules("UPERC"))] == ["blocked"]
    binding["evaluations"][0]["inputs"]["prior:om25_level"]["blank_is_zero"] = "declared"
    assert [c.computed for c in reproduce_cells(wb, binding, load_rules("UPERC"))] == ["0.000000"]


def test_npcl_revenue_from_the_current_tariff_by_category():
    """Real data: ESR-3 for the true-up, APR and ARR years, one row per category / slab / ToD
    block: every row total and implied rate matches; the revenue and units totals are the ARR's
    rows 15 and 9 in all three years.  The one difference is NPCL's FY2024-25 regulatory-discount
    total, whose formula subtracts a typed 0.04 from the sum of its rows (ledger A41).  A slab with
    no units has no implied rate: blocked, never 0."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    wb = None
    arr = {}
    for yy in ("25", "26", "27"):
        binding = json.loads((folder / "bindings" / f"esr3-revenue-fy{yy}.json").read_text())
        wb = wb or openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
        for c in reproduce_row_table(wb, binding, rules):
            if c.result == "blocked":
                assert c.output in ("revenue_energy_rate", "revenue_fixed_rate") and c.why == "division by zero", c
            elif c.result == "differs":
                # the typed 0.04 (A41), in the format's total and where the ARR carries it (row 14)
                assert yy == "25" and c.category in ("TOTAL N136", "TOTAL ARR!J14"), c
                assert (c.filed, c.computed) == ("-288.1762", "-288.1362"), c
            else:
                assert c.result == "match", c
            # the discount, as carried and as computed, is the next test's
            if "ARR!" in c.category and c.output not in ("revenue_discount_total", "revenue_regulatory_discount"):
                arr[(binding["fiscal_year"], c.output)] = c.computed
    assert arr == {
        ("FY2024-25", "revenue_tariff_total"): "2634.6026",
        ("FY2024-25", "units_sold_total"): "3597.6293",
        ("FY2025-26", "revenue_tariff_total"): "2884.7645",
        ("FY2025-26", "units_sold_total"): "3951.4319",
        ("FY2026-27", "revenue_tariff_total"): "3192.0383",
        ("FY2026-27", "units_sold_total"): "4399.8428",
    }


def test_npcl_true_up_power_purchase_as_billed_ties_to_the_arr():
    """Real data: PPC FY 25, the true-up year's bills — per source billed, net of rebate, with
    transmission, the rates and the losses; transmission and earlier years' claims bound
    separately because the ARR carries them on their own lines.  Power purchase 2,047.91 (row 20),
    transmission 294.40 (row 23), arrears 127.73 (row 22), energy at the bus 3,888.46 (row 8)."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    wb = None
    arr = {}
    for name in ("ppc-fy25.json", "ppc-fy25-transmission.json", "ppc-fy25-arrears.json"):
        binding = json.loads((folder / "bindings" / name).read_text())
        wb = wb or openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
        for c in reproduce_row_table(wb, binding, rules):
            if c.result == "blocked":
                assert c.category.startswith("REC Purchase") and c.why == "division by zero", c
            else:
                assert c.result == "match", c
            if "ARR!" in c.category:
                arr[c.category] = c.computed
    contingency = json.loads((folder / "bindings" / "arr-contingency.json").read_text())
    from tariff_api.arr.reproduce import reproduce_cells

    got = [(c.fiscal_year, c.result, c.computed) for c in reproduce_cells(wb, contingency, rules)]
    assert got == [("FY2023-24", "match", "5.2324"), ("FY2024-25", "match", "5.6149")]
    assert arr == {
        "TOTAL ARR!J20": "2047.9078",
        "TOTAL ARR!J8": "3888.4552",
        "TOTAL ARR!J23": "294.3991",
        "TOTAL ARR!J22": "127.7317",
    }


def test_npcl_petition_computed_end_to_end_from_the_schedules():
    """Real data, the milestone's point: the chain for the petition's columns fed not by the ARR
    format's own rows but by what each schedule's reproduction computes (PPC, F22, F19 base, F24,
    F30, P3, ESR-3, the contingency fund), and each year's opening regulatory asset is the year
    before's closing as computed.  The true-up year differs by exactly the security-deposit
    interest NPCL types for March (A40: 0.19), carried to the net ARR and the gap; the APR and ARR
    years reproduce their net ARR and gap, and A40's effect travels into their carried gap with
    carrying cost (0.22, then 0.25) — the computation shows the finding's effect, never hides it."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import (
        reproduce_cells,
        reproduce_period_table,
        reproduce_pipeline,
        reproduce_row_table,
    )
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    ref = json.loads((folder / "reference.json").read_text())
    sheets = {s["sheet"]: s for s in ref["sheets"]}
    rules = load_rules("UPERC")
    pipe = json.loads((folder / "bindings" / "pipeline-petition.json").read_text())
    chain = json.loads((folder / "bindings" / pipe["chain"]).read_text())
    wb = None
    results = {}
    for name in sorted({f["binding"] for feeds in pipe["columns"].values() for f in feeds.values() if "binding" in f}):
        binding = json.loads((folder / "bindings" / name).read_text())
        wb = wb or openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
        fn = {"cells": reproduce_cells, "period_table": reproduce_period_table}.get(
            binding["type"], reproduce_row_table
        )
        results[name] = fn(wb, binding, rules)
    out = reproduce_pipeline(pipe, chain, rules, sheets, results)
    cols = {c["fiscal_year"]: c for c in out["columns"]}
    carried = {"FY2025-26": "0.22", "FY2026-27": "0.25"}
    for fy in ("FY2026-27", "FY2025-26"):
        assert cols[fy]["counts"] == {"match": 10, "differs": 2}, cols[fy]["checks"]
        assert not cols[fy]["not_fed"]
        # the opening is the previous column's computed closing, and only the carried gap differs
        assert "column" in cols[fy]["fed"]["record:gap_accumulated_opening"]
        off = {c["output"]: c for c in cols[fy]["checks"] if c["result"] == "differs"}
        assert set(off) == {"arr_carrying_cost", "arr_gap_cumulative"}
        closing = off["arr_gap_cumulative"]
        assert str(Decimal(closing["filed"]) - Decimal(closing["computed"])) == carried[fy]
        # the loan rate from the MCLR revisions (the ARR year carries the APR year's, as NPCL does)
        assert cols[fy]["fed"]["assumption:loan_interest_rate"]["output"] == "loan_rate_reference"
    assert cols["FY2026-27"]["fed"]["assumption:loan_interest_rate"]["fiscal_year"] == "FY2025-26"
    # capitalisation from the capital plan's schemes and the CWIP movement (F16 after FY25)
    assert Decimal(cols["FY2026-27"]["fed"]["record:capitalisation"]["value"]).quantize(Decimal("0.01")) == Decimal(
        "493.69"
    )
    assert [c.result for c in results["f16-capitalisation.json"]] == ["match"] * 8
    # the true-up year's capitalisation from its schemes (F16 till FY25), = F14's
    assert [c.result for c in results["f16-capitalisation-till25.json"]] == ["match"] * 4
    assert cols["FY2024-25"]["fed"]["record:capitalisation"]["binding"] == "f16-capitalisation-till25.json"
    assert {c["output"]: c["computed"] for c in cols["FY2026-27"]["checks"]}["arr_net"] == "3481.83"
    true_up = {c["output"]: c for c in cols["FY2024-25"]["checks"]}
    assert {o for o, c in true_up.items() if c["result"] == "differs"} == {
        "arr_total_expenditure",
        "arr_net",
        "arr_gap",
        "arr_carrying_cost",
        "arr_gap_cumulative",
    }
    gap = Decimal(true_up["arr_total_expenditure"]["computed"]) - Decimal(true_up["arr_total_expenditure"]["filed"])
    assert gap == Decimal("0.19")  # A40, and nothing else


def test_npcl_average_cost_of_supply_and_billing_rate():
    """Real data: the snapshots' average cost of supply (net ARR / sales) and average billing
    rate (revenue / sales) for the true-up, APR (estimated and approved) and ARR years."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    b = json.loads((folder / "bindings" / "snapshots-acos.json").read_text())
    wb = openpyxl.load_workbook(folder / b["workbook"], data_only=True)
    checks = reproduce_cells(wb, b, load_rules("UPERC"))
    assert [c.result for c in checks] == ["match"] * 8
    got = {
        (c.category.split(" ARR")[0], c.output): c.computed for c in checks if c.category.startswith("ARR projected")
    }
    assert got == {
        ("ARR projected", "average_cost_of_supply"): "7.9135",
        ("ARR projected", "average_billing_rate"): "7.2549",
    }


def test_npcl_power_purchase_reconciled_to_the_audited_accounts():
    """Real data across two workbooks: Annexure-14 bridges the audited accounts to the true-up
    power purchase.  Its own total reproduces; against the claim (PPC FY 25, the ARR's rows
    20 + 22 + 23) it differs by 1.50 — the FY2023-24 carrying cost (ledger A44)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    b = json.loads((folder / "bindings" / "annexure-14-pp-reconciliation.json").read_text())
    wb = openpyxl.load_workbook(folder / b["workbook"], data_only=True)
    others = {k: openpyxl.load_workbook(folder / v, data_only=True) for k, v in b["workbooks"].items()}
    own, claim = reproduce_cells(wb, b, load_rules("UPERC"), others)
    assert (own.category, own.result) == ("reconciliation J24", "match")
    assert claim.result == "differs" and Decimal(claim.computed) - Decimal(claim.filed) == Decimal("1.5022")
    import pytest

    with pytest.raises(Exception, match="not loaded"):
        reproduce_cells(wb, b, load_rules("UPERC"))


def test_npcl_true_up_reconciled_to_the_trial_balance():
    """Real data across three workbooks: the trial balance's profit-and-loss accounts (rupees),
    summed by their own financial-statement groupings through the rules (to Rs crore by the
    units), against the true-up claims.  Power purchase, transmission, deposit interest, finance
    charges, bad debts, loss on retired assets, employee capitalisation, R&M (five groupings) and
    A&G (seven groupings and finance charges; CSR not claimed) agree; employee benefits differ by
    exactly 0.0105 crore (ledger A46)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import reproduce_ledger
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    b = json.loads((folder / "bindings" / "annexure-41-trial-balance.json").read_text())
    wb = openpyxl.load_workbook(folder / b["workbook"], data_only=True)
    others = {k: openpyxl.load_workbook(folder / v, data_only=True) for k, v in b["workbooks"].items()}
    checks = reproduce_ledger(wb, b, load_rules("UPERC"), others)
    differs = [c for c in checks if c.result != "match"]
    assert len(checks) == 13 and len(differs) == 2
    # the true-up's R&M and A&G, records until now, agree with the books by their groupings
    agree = {c.category.split(":")[0] for c in checks if c.result == "match"}
    assert {"R&M", "A&G"} <= agree
    assert {c.category.split(" formats")[0] for c in differs} == {
        "employee benefits, before capitalisation",
        "employee benefits, net",
    }
    for c in differs:
        assert Decimal(c.filed) - Decimal(c.computed) == Decimal("0.01")  # 0.0105 at 2 decimals
    gross = next(c for c in differs if "before" in c.category)
    assert Decimal("95.419846859") - Decimal(gross.exact) == Decimal("0.0105")


def test_npcl_revenue_fy2023_24_in_the_earlier_layout():
    """Real data: ESR-3 FY2023-24 (seven charge columns; category subtotals that subtract rows
    blank in every column): every row's revenue matches, and the totals are the ARR's rows 15
    and 9 (2,320.97, 3,130.40 MU).  A slab with no units has no implied rate (blocked)."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    b = json.loads((folder / "bindings" / "esr3-revenue-fy24.json").read_text())
    wb = openpyxl.load_workbook(folder / b["workbook"], data_only=True)
    checks = reproduce_row_table(wb, b, load_rules("UPERC"))
    for c in checks:
        if c.result == "blocked":
            assert c.why == "division by zero" and c.output.endswith("_rate"), c
        else:
            assert c.result == "match", c
    arr = {c.category: c.computed for c in checks if "ARR!" in c.category}
    assert arr == {"TOTAL ARR!G15": "2320.9739", "TOTAL ARR!G9": "3130.4048"}


def test_npcl_wheeling_supply_allocation_and_cross_subsidy_surcharge():
    """Real data: F32 splits each ARR item between wheeling and supply by its share (34 / 34);
    F33 computes per-unit charges, the cost of supply by voltage, each category's ABR, the
    surcharge capped at 20 % of the tariff and never negative, and the petitioner's proposal
    (the lower of computed and its own) — all match; a category with no sales has no ABR."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells, reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    f32 = json.loads((folder / "bindings" / "f32-allocation.json").read_text())
    wb = openpyxl.load_workbook(folder / f32["workbook"], data_only=True)
    assert [c.result for c in reproduce_row_table(wb, f32, rules)] == ["match"] * 34
    f33 = json.loads((folder / "bindings" / "f33-css.json").read_text())
    checks = reproduce_cells(wb, f33, rules)
    blocked = [c for c in checks if c.result == "blocked"]
    assert [(c.category, c.why) for c in blocked] == [("ABR row 112 D112", "division by zero")]
    assert all(c.result == "match" for c in checks if c.result != "blocked") and len(checks) == 49
    css = {c.category: c.computed for c in checks if c.output == "css_capped" and c.category.startswith("CSS row 10")}
    assert css["CSS row 107 G107"] == "1.206252" and css["CSS row 109 G109"] == "0.000000"  # HV-2 below cost: 0


def test_npcl_renewable_purchase_obligation():
    """Real data: F6 over three years — consumption at the periphery net of hydro, the solar,
    non-solar and hydro obligations, purchases through the (typed, declared) transmission
    losses, balances netted across categories and the closing obligation after RECs: 54 / 54."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    b = json.loads((folder / "bindings" / "f6-rpo.json").read_text())
    wb = openpyxl.load_workbook(folder / b["workbook"], data_only=True)
    checks = reproduce_cells(wb, b, load_rules("UPERC"))
    assert [c.result for c in checks] == ["match"] * 54
    closing = {c.fiscal_year: c.computed for c in checks if c.output == "rpo_closing"}
    assert closing["FY2026-27"] == "-147.251651"  # a net surplus carried forward (A48)


def test_npcl_fy2023_24_power_purchase_in_four_parts():
    """Real data: PPC FY 24 (no transmission columns): sources, transmission, earlier years'
    claims and their transmission, each tied to its ARR line for FY2023-24; the unlabelled
    row 79 is declared and counted, as NPCL's total counts it."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    wb = None
    arr = {}
    for name in ("ppc-fy24.json", "ppc-fy24-transmission.json", "ppc-fy24-arrears.json", "ppc-fy24-tx-arrears.json"):
        b = json.loads((folder / "bindings" / name).read_text())
        wb = wb or openpyxl.load_workbook(folder / b["workbook"], data_only=True)
        for c in reproduce_row_table(wb, b, rules):
            assert c.result == "match" or (c.result == "blocked" and c.why == "division by zero"), c
            if "ARR!" in c.category:
                arr[c.category] = c.computed
    assert arr == {
        "TOTAL ARR!G20": "1740.9174",
        "TOTAL ARR!G8": "3383.9580",
        "TOTAL ARR!G23": "197.0075",
        "TOTAL ARR!G22": "8.9724",
        "TOTAL ARR!G24": "0.3542",
    }


def test_npcl_proposed_tariff_revenue_and_revision_impact():
    """Real data: ESR4 (revenue at the proposed tariff) reproduces like ESR-3; NPCL proposes no
    revision, so proposed less current is 0 — the ARR's row 55."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells, reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    b = json.loads((folder / "bindings" / "esr4-proposed-fy27.json").read_text())
    wb = openpyxl.load_workbook(folder / b["workbook"], data_only=True)
    for c in reproduce_row_table(wb, b, rules):
        assert c.result == "match" or (c.result == "blocked" and c.why == "division by zero"), c
    r = json.loads((folder / "bindings" / "arr-revision-impact.json").read_text())
    (impact,) = reproduce_cells(wb, r, rules)
    assert (impact.result, impact.computed) == ("match", "0.0000")


def test_npcl_distribution_loss_carried_across_formats():
    """Real data: the Energy Balance's loss is the ARR's in every petition year; P1_DL's
    'claimed' loss is not, in three of them (ledger A50)."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    b = json.loads((folder / "bindings" / "p1-distribution-loss.json").read_text())
    wb = openpyxl.load_workbook(folder / b["workbook"], data_only=True)
    checks = reproduce_cells(wb, b, load_rules("UPERC"))
    assert all(c.result == "match" for c in checks if "ARR!" in c.category)
    assert {c.fiscal_year for c in checks if c.result == "differs"} == {"FY2024-25", "FY2025-26", "FY2026-27"}


def _rate_record(**rates):
    return {"document": {"sha256": "0" * 64}, "rates": rates}


def _rate(value, quote, unit="INR_per_kWh", page=1):
    return {"value": value, "unit": unit, "page": page, "quote": quote, "what": "a synthetic slab"}


def test_a_rate_record_refuses_a_figure_that_is_not_in_its_quote():
    """A rate is read with its page and the text it was read from; a figure that is not in that
    text could only have been typed, so the record is refused — as is a rate with no page, or a
    record that does not name its document."""
    import pytest

    from tariff_api.arr.reproduce import load_rate_record
    from tariff_api.arr.rules import RuleError

    ok = _rate_record(base=_rate("7.30", "BASE RATE Rs. 7.30 / kWh"), off=_rate("-15", "(-) 15%", "percent"))
    assert load_rate_record(ok) == {"base": ("7.30", "INR_per_kWh"), "off": ("-15", "percent")}
    with pytest.raises(RuleError, match="not in its quote"):
        load_rate_record(_rate_record(base=_rate("7.40", "BASE RATE Rs. 7.30 / kWh")))
    with pytest.raises(RuleError, match="not in its quote"):  # 7.3 inside 17.30 is not the figure
        load_rate_record(_rate_record(base=_rate("7.3", "Rs. 17.30 / kWh")))
    with pytest.raises(RuleError, match="missing page"):
        load_rate_record(_rate_record(base={"value": "7.30", "unit": "INR_per_kWh", "quote": "7.30", "what": "x"}))
    with pytest.raises(RuleError, match="SHA-256"):
        load_rate_record({"document": {}, "rates": {}})


def test_cells_take_a_rate_from_the_record_with_its_time_of_day_percentage():
    """Energy charges from units and the order's rate: 10 MU at 7.30 Rs/kWh less 15 % is 6.205
    crore.  A rate the record does not have is an error, never a blank or a zero."""
    import openpyxl
    import pytest

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import RuleError, load_rules

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "S"
    ws["F1"], ws["K1"], ws["K2"] = 10.0, 6.205, 7.0
    rates = {"base": ("7.30", "INR_per_kWh"), "off": ("-15", "percent")}
    cat = {
        "inputs": {
            "record:units_sold": ["F1", "MU"],
            "order:energy_rate": {"rate": "base"},
            "order:energy_adjustment": {"rate": "off"},
        },
        "checks": {"revenue_energy_from_rate": ["K1", "K2"]},
    }
    binding = {"sheet": "S", "places": 4, "evaluations": [{"fiscal_year": "FY2026-27", "categories": {"slot": cat}}]}
    got = [(c.category, c.result, c.computed) for c in reproduce_cells(wb, binding, load_rules("UPERC"), rates=rates)]
    assert got == [("slot K1", "match", "6.2050"), ("slot K2", "differs", "6.2050")]
    with pytest.raises(RuleError, match="not in the rate record"):
        reproduce_cells(wb, binding, load_rules("UPERC"), rates={"base": rates["base"]})


def test_npcl_esr3_energy_charges_from_the_orders_rate_schedule():
    """Real data: 45 slab rows of ESR-3 (FY2026-27, current tariff) computed from the units sold
    and the rates of the UPERC order's Annexure-I, each read with its page and quote.  40 match
    to the paisa-crore (4 places), the LMV-6 time-of-day slots and the rural rebate included;
    the four urban domestic slabs (A53) and the registered societies (A54) differ — findings for
    the petitioner, not fitted away."""
    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "esr3-energy-from-rates-fy27.json").read_text())
    record = json.loads((folder / binding["rates"]).read_text())
    rates = load_rate_record(record)
    assert record["document"]["sha256"].startswith("ff36813e")
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=rates)
    assert len(checks) == 45
    differs = sorted(c.category.rsplit(" ", 1)[-1] for c in checks if c.result != "match")
    assert differs == ["K20", "K23", "K24", "K25", "K26"]
    k20 = next(c for c in checks if c.category.endswith("K20"))
    assert (k20.filed, k20.computed) == ("390.5230", "430.7347")
    # the existing rates NPCL states in its own rate-schedule format (ESR4A column C) are the
    # order's: ESR-3's revenue is at the rates the order kept (LT per kWh, HV per kVAh)
    esr4a = json.loads((folder / "bindings" / "esr4a-existing-rates.json").read_text())
    existing = reproduce_cells(wb, esr4a, load_rules("UPERC"), rates=rates)
    assert len(existing) == 47 and {c.result for c in existing} == {"match"}
    assert len(rates) == 58


def test_a_kvah_rate_is_never_multiplied_by_kwh():
    """HV energy is billed per kVAh.  Fed to the per-kWh energy rule, a kVAh rate blocks with a
    unit reason — the engine does not turn kWh sold into kVAh revenue."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "S"
    ws["F1"], ws["K1"] = 10.0, 8.32
    binding = {
        "sheet": "S",
        "evaluations": [
            {
                "fiscal_year": "FY2026-27",
                "categories": {
                    "hv": {
                        "inputs": {
                            "record:units_sold": ["F1", "MU"],
                            "order:energy_rate": {"rate": "hv"},
                            "order:energy_adjustment": {"value": "0", "unit": "percent", "why": "none"},
                        },
                        "checks": {"revenue_energy_from_rate": "K1"},
                    }
                },
            }
        ],
    }
    (check,) = reproduce_cells(wb, binding, load_rules("UPERC"), rates={"hv": ("8.32", "INR_per_kVAh")})
    assert check.result == "blocked" and "rate" in (check.why or "")


def test_the_quote_checker_finds_each_quote_and_its_column_header_on_its_page(tmp_path):
    """`scripts/check_order_quotes.py` on a PDF made in the test: the record's quotes and the
    header of a shared row are found on their page; a quote on the wrong page, a header that is not
    printed, or another document (hash) is reported."""
    import hashlib
    import importlib.util

    import pymupdf

    pdf = tmp_path / "order.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Rate Schedule")
    page = doc.new_page()
    page.insert_text((72, 72), "Up to 11 kV Above 11 kV")
    page.insert_text((72, 100), "Energy Charges Rs. 7.10 / kVAh Rs. 6.80 / kVAh")
    doc.save(pdf)
    spec = importlib.util.spec_from_file_location("coq", ROOT / "scripts" / "check_order_quotes.py")
    coq = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(coq)
    row = "Energy Charges Rs. 7.10 / kVAh Rs. 6.80 / kVAh"
    rate = {"value": "6.80", "unit": "INR_per_kVAh", "page": 2, "quote": row, "what": "second column"}
    record = {"document": {"sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}}
    assert coq.check(pdf, {**record, "rates": {"a": {**rate, "header": "Up to 11 kV Above 11 kV"}}}) == []
    assert coq.check(pdf, {**record, "rates": {"a": {**rate, "page": 1}}}) == [
        "a: quote or column header not found on page 1"
    ]
    assert coq.check(pdf, {**record, "rates": {"a": {**rate, "header": "Above 66 kV"}}}) == [
        "a: quote or column header not found on page 2"
    ]
    other = coq.check(pdf, {"document": {"sha256": "0" * 64}, "rates": {"a": rate}})
    assert len(other) == 1 and "not the record's document" in other[0]


def test_a_pipeline_column_feeds_a_later_one_only_with_a_reason_and_never_in_a_cycle():
    import pytest

    from tariff_api.arr.reproduce import reproduce_pipeline
    from tariff_api.arr.rules import RuleError, load_rules

    feed = {"column": "FY2025-26|petitioned", "output": "arr_gap_cumulative"}
    cycle = {
        "chain": "c.json",
        "columns": {
            "FY2026-27|petitioned": {"record:gap_accumulated_opening": feed | {"why": "w"}},
            "FY2025-26|petitioned": {
                "record:gap_accumulated_opening": feed | {"column": "FY2026-27|petitioned", "why": "w"}
            },
        },
    }
    with pytest.raises(RuleError, match="cycle"):
        reproduce_pipeline(cycle, {"sheet": "ARR", "inputs": {}}, load_rules("UPERC"), {}, {})
    unexplained = {
        "chain": "c.json",
        "columns": {
            "FY2026-27|petitioned": {"record:gap_accumulated_opening": feed | {"column": "FY2024-25|petitioned"}},
            "FY2024-25|petitioned": {},
        },
    }
    unknown = {
        "chain": "c.json",
        "columns": {"FY2026-27|petitioned": {"record:gap_accumulated_opening": feed | {"why": "w"}}},
    }
    with pytest.raises(RuleError, match="not a column of this pipeline"):
        reproduce_pipeline(unknown, {"sheet": "ARR", "inputs": {}}, load_rules("UPERC"), {}, {})
    with pytest.raises(RuleError, match="without a reason"):
        reproduce_pipeline(
            unexplained, {"sheet": "ARR", "inputs": {}}, load_rules("UPERC"), {"ARR": {"sheet": "ARR", "rows": []}}, {}
        )


def test_npcl_regulatory_asset_rolls_forward_along_the_petitions_chain():
    """Real data: each column's gap brought forward (ARR row 59) is the closing (row 63) of the
    column it continues — 7 ties along the petition's chain; the approved columns, each a
    different order's, are not one chain and are not tied."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "arr-gap-roll-forward.json").read_text())
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"))
    assert [c.result for c in checks] == ["match"] * 7
    assert not any(c.category.split(" ")[0][0] in "EHK" for c in checks)


def test_cells_carry_a_chain_of_years_unrounded_and_check_against_an_order_figure():
    """A year fed what the previous evaluation computed (unrounded), checked against a figure of
    the order's record: 74.152 escalated 5.19 % is 78.0005 — printed 78.00 — and the next year
    starts from 78.0005, not from the printed 78.00.  A computed input naming no earlier
    evaluation is an error."""
    import openpyxl
    import pytest

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import RuleError, load_rules

    record = {
        "document": {"sha256": "0" * 64},
        "figures": {
            "base": {"value": "74.152", "unit": "INR_crore", "page": 1, "quote": "Avg. 74.152", "what": "w"},
            "cpi": {"value": "5.19", "unit": "percent", "page": 1, "quote": "CPI 5.19%", "what": "w"},
            "fy24": {
                "value": "78.00",
                "unit": "INR_crore",
                "page": 1,
                "quote": "Normative 1,078.00 78.00",
                "what": "w",
            },
        },
    }
    figures = load_rate_record(record)
    wb = openpyxl.Workbook()
    wb.active.title = "S"
    binding = {
        "sheet": "S",
        "places": 2,
        "evaluations": [
            {
                "fiscal_year": "FY2022-23",
                "label": "base",
                "inputs": {f"record:om25_actual_y{i}": {"rate": "base"} for i in range(1, 6)},
            },
            {
                "fiscal_year": "FY2023-24",
                "label": "y1",
                "inputs": {
                    "prior:om25_level": {"computed": "base", "output": "om25_base_average"},
                    "assumption:om25_index_change": {"rate": "cpi"},
                },
                "checks": {"om25_escalated": "order:fy24"},
            },
        ],
    }
    (check,) = reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    assert (check.result, check.computed) == ("match", "78.00") and check.exact.startswith("78.0004")
    bad = {**binding, "evaluations": [binding["evaluations"][1]]}
    with pytest.raises(RuleError, match="no earlier evaluation"):
        reproduce_cells(wb, bad, load_rules("UPERC"), rates=figures)


def test_npcl_the_commissions_om_approval_reproduces_with_the_same_rules():
    """Real data: the order's O&M approval for FY2026-27 (employee 87.63, A&G 28.87, R&M 111.04)
    from the order's own figures and the same draft rules as NPCL's claim; one intermediate year
    is one unit off (the order prints its CPI change rounded) — A60."""
    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-om-fy27.json").read_text())
    figures = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    assert len(checks) == 13
    off = [(c.category, c.filed, c.computed) for c in checks if c.result != "match"]
    assert off == [("employee FY2025-26 order:employee.normative.fy26", "84.57", "84.56")]
    finals = {c.category.split(" order:")[1]: c.computed for c in checks if c.fiscal_year == "FY2026-27"}
    assert finals == {"employee.normative.fy27": "87.63", "ag.normative.fy27": "28.87", "rm.approved": "111.04"}


def test_npcl_the_commissions_capital_and_interest_approval_reproduces_with_the_same_rules():
    """Real data: funding, normative loan, equity, RoE, tax and security-deposit interest approved
    for FY2026-27, from the order's figures and the same draft rules as NPCL's claim — the loan
    at NPCL's own rate, which the order accepts (A62); one last-place difference from the order's
    rounded opening equity."""
    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-capital-fy27.json").read_text())
    figures = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    assert len(checks) == 14
    assert [(c.output, c.filed, c.computed) for c in checks if c.result != "match"] == [
        ("equity_average", "755.20", "755.21")
    ]
    got = {c.output: c.computed for c in checks}
    assert (got["return_on_equity"], got["interest_on_loan"], got["tax_on_roe"], got["isd_interest_annual"]) == (
        "113.28",
        "85.60",
        "38.10",
        "20.51",
    )


def test_npcl_the_commissions_depreciation_reproduces_class_by_class():
    """Real data: 36 asset classes in three parts (Tables 6-62 to 6-64) from the order's figures
    and the same depreciation rules as NPCL's F24: every class's depreciation matches; closings
    and totals within two units of the last place (the order prints its GFA rounded)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-depreciation-fy27.json").read_text())
    figures = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    assert {c.result for c in checks if c.output == "depreciation_class"} == {"match"}
    assert sum(1 for c in checks if c.output == "depreciation_class") == 36
    off = [c for c in checks if c.result != "match"]
    assert len(off) == 8 and all(abs(Decimal(c.filed) - Decimal(c.computed)) <= Decimal("0.02") for c in off)


def test_a_record_figure_of_zero_may_be_printed_as_a_dash_and_only_so():
    import pytest

    from tariff_api.arr.reproduce import load_rate_record
    from tariff_api.arr.rules import RuleError

    rec = {
        "document": {"sha256": "0" * 64},
        "figures": {
            "z": {"value": "0", "unit": "INR_crore", "page": 1, "quote": "6 Furniture - - - 6.33% -", "what": "w"}
        },
    }
    assert load_rate_record(rec) == {"z": ("0", "INR_crore")}
    rec["figures"]["z"]["quote"] = "6 Furniture 6.33%"
    with pytest.raises(RuleError, match="not in its quote"):
        load_rate_record(rec)


def test_npcl_the_trueup_om_approval_reproduces_from_the_monthly_indices():
    """Real data: the order's true-up of O&M for FY2024-25 — CPI and WPI averages and increases
    from the monthly indices exactly (an order figure printed in percent compared in percent),
    each component escalated from its FY2023-24 norm and the lower of normative and actual taken
    (R&M exact, employee and A&G one unit off the rounded bases; A65)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-trueup-om-fy25.json").read_text())
    figures = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    index = [c for c in checks if c.output.startswith("index_")]
    assert len(index) == 6 and {c.result for c in index} == {"match"}
    assert {c.computed for c in index if c.output == "index_increase"} == {"3.38", "2.27"}
    rm = [c for c in checks if c.category.startswith("rm ")]
    assert {c.result for c in rm} == {"match"}
    assert all(abs(Decimal(c.filed) - Decimal(c.computed)) <= Decimal("0.01") for c in checks)


def test_npcl_the_trueup_capital_approval_shows_where_the_draft_rules_depart():
    """Real data: the true-up of FY2024-25's funding, loan, equity, tax and working capital from
    the order's figures.  The working capital reproduces; one draft rule (the equity deleted on
    retirement: WDV 1.85 against the order's 30 % of the gross, 2.03) shows as differences, the
    rest one unit of rounding (A66) — the build does not bend a rule to fit an order."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-trueup-capital-fy25.json").read_text())
    figures = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    assert {c.result for c in checks if c.category.startswith("working capital")} == {"match"}
    dele = next(c for c in checks if c.output == "equity_reduction_on_retirement")
    assert (dele.filed, dele.computed) == ("2.03", "1.85")
    small = [
        c
        for c in checks
        if c.result != "match"
        and c.output not in ("equity_reduction_on_retirement", "equity_closing", "equity_average")
    ]
    assert all(abs(Decimal(c.filed) - Decimal(c.computed)) <= Decimal("0.01") for c in small)


def test_npcl_the_trueup_depreciation_reproduces_class_by_class():
    """Real data: the true-up of FY2024-25's depreciation (Tables 4-99 to 4-101) from the order's
    figures and the same rules as NPCL's F24: all 24 classes, the gross 95.03 and the net 69.97
    match; the rest is half-paisa averages, except one row of the order that does not add (Part B
    Lines & Cables 573.03 against 573.00; A69).  The approved additions are the funding table's
    317.18 and the net is the loan repayment (A68)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-trueup-depreciation-fy25.json").read_text())
    figures = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    dep = [c for c in checks if c.output == "depreciation_class"]
    assert len(dep) == 24 and {c.result for c in dep} == {"match"}
    assert {c.result for c in checks if c.output == "depreciation_net"} == {"match"}
    lc = next(c for c in checks if c.output == "gfa_closing" and "B4 Lines & Cables" in c.category)
    assert (lc.filed, lc.computed) == ("573.03", "573.00")
    off = [c for c in checks if c.result != "match" and c is not lc]
    assert len(off) == 7 and all(abs(Decimal(c.filed) - Decimal(c.computed)) <= Decimal("0.01") for c in off)
    capital = load_rate_record(json.loads((folder / "order" / "figures-trueup-capital-fy2024-25.json").read_text()))
    assert figures["dep.B.13.addition"] == capital["fund.investment"] == figures["gfa.addition"]
    assert figures["dep.net"] == capital["loan.repayment"]


def test_npcl_the_trueup_excess_energy_disallowed_reproduces():
    """Real data: the one computed line of the true-up's power purchase decision — 1.32 MU beyond
    the energy balance at the weighted average energy charge of DIL, TPTCL and JITPL (2.57): 0.34
    (paras 4.4.82–4.4.83).  The order's totals of Table 4-51 are one unit off the sum of its rows."""
    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-trueup-power-purchase-fy25.json").read_text())
    figures = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    got = {
        c.output: (c.result, c.filed, c.computed)
        for c in reproduce_cells(wb, binding, load_rules("UPERC"), rates=figures)
    }
    assert got["pp_excess_rate"] == ("match", "2.57", "2.57")
    assert got["pp_excess_disallowed"] == ("match", "0.34", "0.34")
    assert got["pp_energy_total"] == ("differs", "663.60", "663.61")


def test_npcl_the_apr_carries_the_trueup_closings_and_reproduces():
    """Real data: the Commission's APR of FY2025-26 from its own figures with the MYT 2025 rules —
    loan, equity, RoE, tax, working capital (nil against the surplus NPCL holds) and R&M on the
    inferred base (A73) — each opening the true-up's approved closing, the supplementary DIL
    claim NPCL's own arithmetic (A72)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-apr-fy26.json").read_text())
    apr = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=apr)
    got = {c.output: c for c in checks}
    assert {o for o, c in got.items() if c.result != "match"} == {"normative_loan_closing", "wc_total"}
    assert all(abs(Decimal(c.filed) - Decimal(c.computed)) <= Decimal("0.01") for c in checks)
    assert (got["interest_on_working_capital"].computed, got["wc_net"].computed) == ("0.00", "-434.00")
    assert got["rm_norm_total"].computed == "98.14"

    def record(name):
        return load_rate_record(json.loads((folder / "order" / name).read_text()))

    trueup = record("figures-trueup-capital-fy2024-25.json")
    assert apr["loan.opening"] == trueup["loan.closing"] and apr["roe.opening"] == trueup["roe.closing"]
    assert apr["gfa.opening"] == record("figures-trueup-depreciation-fy2024-25.json")["gfa.closing"]
    assert Decimal(apr["wc.surplus"][0]) == -Decimal(apr["gap.fy25_closing"][0])
    assert apr["dep.B"] == record("figures-depreciation-fy2026-27.json")["dep.B.13.allowable"]
    om27 = record("figures-om-fy2026-27.json")
    assert apr["om.employee"] == om27["employee.normative.fy26"] and apr["om.ag"] == om27["ag.normative.fy26"]
    claim, carrying, allowed, total = (Decimal(apr[f"dil.{k}"][0]) for k in ("claim", "carrying", "allowed", "total"))
    assert claim + carrying - allowed == total == Decimal("118.55")
    rep = json.loads((folder / "order-decisions.json").read_text())
    summary = {r["key"]: r for r in next(t for t in rep["tables"] if t["proceeding"] == "apr")["rows"]}
    assert summary["power_purchase"]["decision"] == "118.55" and summary["arr_net"]["decision"] == "92.64"


def test_npcl_the_gap_and_its_carrying_cost_reproduce_on_one_convention():
    """Real data: one draft rule — (opening + half the year's addition) × rate — reproduces NPCL's
    format (ARR rows 62–63) and the order's carrying costs (Tables 7-1, 8-4), the APR's and the
    ARR year's on the opening left after the working capital the surplus funds; the order's
    closings add the carrying cost to the unadjusted opening (A74)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-gap.json").read_text())
    g = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=g)
    assert {c.result for c in checks if c.output == "gap_carrying_cost"} == {"match"}
    assert sum(1 for c in checks if c.output == "gap_carrying_cost") == 8
    off = [c for c in checks if c.result != "match"]
    assert len(off) == 1 and abs(Decimal(off[0].filed) - Decimal(off[0].computed)) == Decimal("0.01")

    def v(key):
        return Decimal(g[key][0])

    # the surplus funds the year's working capital first (Tables 5-32, 6-69, 8-4; each figure
    # printed rounded, so the sums hold within a unit)
    assert abs(v("gap.fy26.computed.opening") + v("wc.fy26.total") - v("wc.fy26.net")) <= Decimal("0.01")
    assert abs(v("gap.fy27.opening") + v("wc.fy27.total") - v("wc.fy27.net")) <= Decimal("0.01")
    assert v("wc.fy27.surplus") == v("gap.fy26.computed.closing") == v("gap.fy27.opening")
    assert v("wc.fy27.net") == v("gap.fy27.opening_after_wc")
    # the closings carry from the unadjusted opening: I = A + E + H
    for c in ("fy26.computed", "fy27"):
        a, e, h, i = (v(f"gap.{c}.{k}") for k in ("opening", "addition", "carrying", "closing"))
        assert abs(a + e + h - i) <= Decimal("0.01")
    assert v("gap.fy25.approved.closing") == v("gap.fy26.computed.opening")


def test_npcl_the_tariff_design_summary_reproduces_within_its_inputs_precision():
    """Real data: the order's ABR by category, ACoS and cross-subsidy levels (Table 8-6) from its
    sales and revenue (Table 8-5) and ARR (Table 8-4).  Where a figure differs, the difference is
    within what the order's own rounding of revenue and sales (two places in crore and MU)
    allows; the monthly sales for FPPAS add to the year's (A75)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-tariff-fy27.json").read_text())
    t = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=t)
    got = {c.category.split(" order:")[-1]: c for c in checks}
    for key in (
        "acos",
        "total.abr",
        "total.cross_subsidy",
        "acos_minus_abr",
        "lmv1.cross_subsidy",
        "hv2.cross_subsidy",
    ):
        assert got[key].result == "match", key
    half = Decimal("0.005")
    for c in checks:
        if c.result == "match":
            continue
        ref = c.category.split(" order:")[-1]
        cat = ref.split(".")[0]
        if cat in ("total", "monthly"):  # eleven rounded categories add a unit off the printed total
            assert abs(Decimal(c.filed) - Decimal(c.computed)) == Decimal("0.01")
            continue
        rev, sales = Decimal(t[f"{cat}.revenue"][0]), Decimal(t[f"{cat}.sales"][0])
        relative = half / rev + half / sales  # the printed inputs' rounding, relative
        value = Decimal(c.exact)
        scale = abs(value) if c.output == "tariff_abr_category" else (abs(value) + 100)
        assert abs(Decimal(c.filed) - Decimal(c.computed)) <= relative * scale + Decimal("0.01"), ref
    months = [v for k, v in t.items() if k.startswith("monthly.") and k != "monthly.total"]
    assert len(months) == 12 and sum(Decimal(v[0]) for v in months) == Decimal(t["monthly.total"][0])


def test_a_shared_input_may_sum_named_cells_with_a_reason():
    """A row table's shared input can be the sum of several named cells (a charge spread over a
    few rows) — only with its reason, and only over cells that hold numbers."""
    import openpyxl
    import pytest

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "S"
    for r, (label, units, fixed, energy, discount) in enumerate(
        [("A", 10.0, 4.0, 40.0, -4.4), ("B", 5.0, 0.0, 20.0, -2.0), ("PCS", 1.0, 0.5, 6.0, -0.6)], start=2
    ):
        ws[f"A{r}"], ws[f"B{r}"], ws[f"C{r}"], ws[f"D{r}"], ws[f"E{r}"] = label, units, fixed, energy, discount
        ws[f"F{r}"] = fixed + energy + discount
    ws["E6"] = -7.0
    binding = {
        "sheet": "S",
        "fiscal_year": "FY2026-27",
        "rows": [2, 4],
        "label_col": "A",
        "inputs": {
            "record:units_sold": "B",
            "record:rev_fixed": "C",
            "record:rev_energy": "D",
            "record:rev_discount": "E",
        },
        "units": {"B": "MU"},
        "shared": {
            "record:rev_minimum": {"value": "0", "why": "none"},
            "record:rev_other": {"value": "0", "why": "none"},
            "assumption:regulatory_discount_share": {"value": "0.10", "unit": "fraction", "why": "10 %"},
            "record:rev_fixed_not_demand": {"cells": ["C4"], "why": "PCS: no demand charge"},
        },
        "outputs": {"revenue_category": "F"},
        "totals": {"revenue_regulatory_discount": "E6"},
        "places": 2,
    }
    rules = load_rules("UPERC")
    got = {c.output: c for c in reproduce_row_table(wb, binding, rules)}
    # 10 % of (4 + 40 + 0 + 20 + 0.5 + 6 − 0.5): the PCS fixed column is not discounted
    assert (got["revenue_regulatory_discount"].result, got["revenue_regulatory_discount"].computed) == (
        "match",
        "-7.00",
    )
    del binding["shared"]["record:rev_fixed_not_demand"]["why"]
    with pytest.raises(ValueError, match="needs its reason"):
        reproduce_row_table(wb, binding, rules)


def test_npcl_the_regulatory_discount_is_ten_percent_of_the_demand_and_energy_charges():
    """Real data: NPCL's regulatory discount in ESR-3 for FY2025-26 and FY2026-27 is 10 % of the
    fixed / demand and energy charges exactly, once the public charging stations' fixed column —
    no demand charge in their schedule (p.381) — is left out, as NPCL leaves it."""
    import openpyxl

    from tariff_api.arr.reproduce import reproduce_row_table
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rules = load_rules("UPERC")
    for name, total in (("esr3-revenue-fy26.json", "-322.6380"), ("esr3-revenue-fy27.json", "-357.0702")):
        binding = json.loads((folder / "bindings" / name).read_text())
        wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
        disc = [c for c in reproduce_row_table(wb, binding, rules) if c.output == "revenue_regulatory_discount"]
        assert len(disc) == 2 and {(c.result, c.computed) for c in disc} == {("match", total)}, name


def test_npcl_fixed_charges_sit_above_the_billable_demand_floor_except_lmv2():
    """Real data: ESR-3's fixed charges against the schedule's fixed / demand charges (read with
    their quotes) at the full contracted load: every category at or above the 75 % floor of
    billable demand (General Provision 6, p.354) except LMV-2, at 58–66 % (A77).  An analysis —
    the billable demand that would reproduce the charges is not in the filing."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    rates = load_rate_record(json.loads((folder / "order" / "figures-fixed-charges-fy2026-27.json").read_text()))
    ws = openpyxl.load_workbook(folder / "4. Appendix-II MYT Tariff Formats ARR FY 2026-27.xlsx", data_only=True)[
        "ESR_3 Curr Tariff FY27"
    ]
    rows = {
        13: "lmv1.rural", 20: "lmv1.bulk", 21: "lmv1.other", 29: "lmv2.rural", 31: "lmv2.upto4kw",
        32: "lmv2.above4kw", 41: "lmv4.public", 42: "lmv4.private", 52: "lmv6.base", 57: "lmv6.base",
        78: "lmv7.urban", 81: "lmv9.irc", 82: "lmv9.others", 92: "hv1.commercial.11kv",
        93: "hv1.commercial.above11kv", 95: "hv1.public.11kv", 96: "hv1.public.above11kv",
        100: "hv2.upto11kv", 112: "hv2.11_66kv", 124: "hv2.66_132kv",
    }  # fmt: skip
    floor = Decimal(rates["billable.floor"][0]) / 100
    share, short = {}, Decimal(0)
    for r, key in rows.items():
        rate, unit = rates[f"fixed.{key}"]
        assert unit == ("INR_per_kVA_month" if key.startswith("hv") else "INR_per_kW_month")
        contract = Decimal(repr(ws[f"E{r}"].value)) * 1000 * Decimal(rate) * 12 / Decimal(10) ** 7
        billed = Decimal(repr(ws[f"J{r}"].value))
        share[key] = billed / contract
        if key.startswith("lmv2"):
            short += contract * floor - billed
    low = {k for k, s in share.items() if s < floor}
    assert low == {"lmv2.rural", "lmv2.upto4kw", "lmv2.above4kw"}
    assert max(share.values()) < Decimal("0.94") and round(short, 2) == Decimal("4.71")


def test_npcl_the_arr_years_working_capital_is_nil_against_the_surplus():
    """Real data: the Commission's working capital for FY2026-27 (Table 6-69) with the same rules
    as NPCL's F27 — one month of the approved O&M, 1.5 months of the revenue with the open-access
    charges, the spares, less the deposits — and the APR's closing surplus set against it: the net
    is negative, the interest nil (A62)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-wc-fy27.json").read_text())
    wc = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    got = {c.output: c for c in reproduce_cells(wb, binding, load_rules("UPERC"), rates=wc)}
    assert {o for o, c in got.items() if c.result != "match"} == {"wc_net"}
    assert (got["wc_net"].filed, got["wc_net"].computed) == ("-11.03", "-11.04")
    assert got["interest_on_working_capital"].computed == "0.00"
    gap = load_rate_record(json.loads((folder / "order" / "figures-gap-fy2026-27.json").read_text()))
    assert Decimal(wc["wc.surplus"][0]) == -Decimal(gap["gap.fy26.computed.closing"][0])


def test_npcl_the_trueup_bad_debts_and_non_tariff_income_reproduce():
    """Real data: bad debts at NPCL's own provisioning ratio on the approved revenue net of duty
    (10.79); non-tariff income as the audited 50.78 less the lower of the shareholders' fund's
    income and the interest earned (37.99) and three small items (12.38).  The fund's income is
    two units off, the order printing the average investment in whole crore."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_rate_record, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-trueup-nti-fy25.json").read_text())
    n = load_rate_record(json.loads((folder / binding["rates"]).read_text()))
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=n)
    assert [(c.output, c.filed, c.computed) for c in checks if c.result != "match"] == [
        ("nti_fund_income", "39.07", "39.05")
    ]
    # the stated exclusions are the record's rows 15-17, not a typed figure that could drift
    stated = binding["evaluations"][1]["inputs"]["record:nti_other_excluded"]["value"]
    assert Decimal(stated) == sum(Decimal(n[k][0]) for k in ("nti.emi", "nti.telecom", "nti.emi_prior"))


def test_a_binding_may_draw_on_several_records_and_take_one_figure_less_another(tmp_path):
    """Records under aliases never collide; an input may be one recorded figure less another (a
    year's deduction between two printed balances), never a typed difference, and only between
    figures in the same unit."""
    import pytest

    from tariff_api.arr.reproduce import load_binding_rates, reproduce_cells
    from tariff_api.arr.rules import RuleError, load_rules

    def record(figures):
        return {
            "document": {"sha256": "0" * 64},
            "figures": {
                k: {"value": v, "unit": u, "page": 1, "quote": f"row {v}", "what": k} for k, (v, u) in figures.items()
            },
        }

    (tmp_path / "a.json").write_text(json.dumps(record({"gfa.closing": ("100.00", "INR_crore")})))
    (tmp_path / "b.json").write_text(
        json.dumps(
            record({"gfa.closing": ("90.00", "INR_crore"), "rate": ("5.00", "percent"), "dep": ("4.75", "INR_crore")})
        )
    )
    binding = {
        "sheet": "S",
        "rates": {"tu": "a.json", "next": "b.json"},
        "places": 2,
        "evaluations": [
            {
                "fiscal_year": "FY2025-26",
                "categories": {
                    "Lines": {
                        "inputs": {
                            "record:gfa_opening": {"rate": "tu:gfa.closing"},
                            "record:gfa_deductions": {"rate": "tu:gfa.closing", "minus": "next:gfa.closing"},
                            "record:gfa_additions": {"value": "0", "unit": "INR_crore", "why": "none"},
                            "record:gfa_grants": {"value": "0", "unit": "INR_crore", "why": "none"},
                            "record:dep_rate": {"rate": "next:rate"},
                        },
                        "checks": {"gfa_closing": "order:next:gfa.closing", "depreciation_class": "order:next:dep"},
                    }
                },
            }
        ],
    }
    rates = load_binding_rates(tmp_path, binding)
    assert set(rates) == {"tu:gfa.closing", "next:gfa.closing", "next:rate", "next:dep"}
    got = {c.output: (c.result, c.computed) for c in reproduce_cells(None, binding, load_rules("UPERC"), rates=rates)}
    assert got == {"gfa_closing": ("match", "90.00"), "depreciation_class": ("match", "4.75")}  # avg 95 × 5 %
    binding["evaluations"][0]["categories"]["Lines"]["inputs"]["record:gfa_deductions"]["minus"] = "next:rate"
    with pytest.raises(RuleError, match="minus"):
        reproduce_cells(None, binding, load_rules("UPERC"), rates=rates)


def test_npcl_the_apr_depreciation_reproduces_between_two_printed_balances():
    """Real data: Table 5-40 prints only the APR's part totals; each class opened at the true-up's
    closing and closed at the ARR year's opening, at the 2025 class rates, gives every total
    exactly — Part A 54.05, B 54.09, C 9.81, gross 117.95, net 87.01 (A72)."""
    import openpyxl

    from tariff_api.arr.reproduce import load_binding_rates, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-apr-depreciation-fy26.json").read_text())
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=load_binding_rates(folder, binding))
    assert len(checks) == 5 and {c.result for c in checks} == {"match"}


def test_npcl_the_arr_years_power_purchase_reproduces_source_by_source():
    """Real data: the Commission's FY2026-27 power purchase from its own tables — energy from the
    contracted capacity at its PLF, the two losses to NPCL's periphery, charges at the approved
    rates, the landed cost; DIL and the renewables on the loss chain and their approved cost; the
    exchange; GNA from the base cost.  Where a figure differs, the difference is within what the
    order's printed inputs allow (rates to two places, losses to two places of a percent, small
    costs to two places); the parts are Table 6-35's lines (A64)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_binding_rates, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-pp-fy27.json").read_text())
    rec = load_binding_rates(folder, binding)
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=rec)
    assert len(checks) == 77

    def v(key):
        return Decimal(rec[key][0])

    half_rate = Decimal("0.005") / 10  # a rate printed to two places, Rs/kWh, per MU in crore
    half_loss = Decimal("0.00005")  # a loss printed to two places of a percent
    for c in checks:
        if c.result == "match":
            continue
        key = c.category.split(" order:")[-1].rsplit(".", 1)[0]
        diff = abs(Decimal(c.filed) - Decimal(c.computed))
        if key.endswith("total"):
            bound = Decimal("0.16")  # five to eight rounded sources
        elif c.output in ("ppp_fixed", "ppp_energy"):
            bound = v(f"{key}.units") * half_rate + Decimal("0.005")
        elif c.output == "ppp_cost":
            bound = 2 * v(f"{key}.units") * half_rate + Decimal("0.005")
        elif c.output in ("ppp_at_state", "ppp_at_periphery"):
            units = v("px.units") if key == "px" else v(f"{key}.units")
            bound = 2 * units * half_loss + Decimal("0.005")
        elif c.output == "ppp_landed_given":
            bound = Decimal("0.005") / v(f"{key}.at_periphery") * 10 + Decimal("0.005")
        else:
            raise AssertionError(c)
        assert diff <= bound, (c.category, c.output, diff, bound)
    # JITPL, at 95 MW, to the last place; GNA from the base cost exactly
    assert all(c.result == "match" for c in checks if "JITPL" in c.category or c.output.startswith("gna"))
    # the parts are Table 6-35's lines
    rep = json.loads((folder / "order-decisions.json").read_text())
    rows = {r["code"]: r["cells"] for r in next(t for t in rep["source_tables"] if t["proceeding"] == "arr")["rows"]}
    assert rows["A"]["approved_amount"] == rec["dil.cost"][0] and rows["A"]["approved_mu"] == "1,188.64"
    assert rows["B"]["approved_amount"] == rec["mt.total.cost"][0]
    assert rows["E"]["approved_amount"] == rec["re.total.cost"][0]
    assert rows["C.22"]["approved_mu"] == rec["px.at_periphery"][0]
    exchange = v("px.units") * v("px.rate") / 10
    assert abs(exchange - Decimal(rows["C.22"]["approved_amount"])) <= v("px.units") * half_rate
    assert v("gna.charges") + v("tgna.charges") == v("gna.total") == Decimal(rows["I"]["approved_amount"])


def test_npcl_the_arr_years_energy_balance_reproduces_claimed_and_approved():
    """Real data: Table 6-9's energy balance in both columns with the same rules — sales grossed up
    for the distribution loss, less what is delivered at NPCL's bus, the intra-state loss, less what
    is connected at the STU bus, the inter-state loss.  Differences are within the printed
    precision of the losses; the approved requirement at NPCL's bus is Table 6-35's import, and the
    GNA table's energy is the claimed total, not the approved (A78)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_binding_rates, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-energy-balance-fy27.json").read_text())
    rec = load_binding_rates(folder, binding)
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=rec)
    assert len(checks) == 14
    for c in checks:
        assert c.result == "match" or c.output in ("eb_at_state", "eb_net_at_state", "eb_at_ctu", "eb_total"), c
        # two losses printed to two places of a percent, on about 5,000 MU
        assert abs(Decimal(c.filed) - Decimal(c.computed)) <= Decimal(c.filed) * 2 * Decimal("0.00005") / Decimal(
            "0.96"
        )
    rep = json.loads((folder / "order-decisions.json").read_text())
    rows = {r["code"]: r["cells"] for r in next(t for t in rep["source_tables"] if t["proceeding"] == "arr")["rows"]}
    assert rows["F"]["approved_mu"].replace(",", "") == rec["eb.approved.requirement"][0]
    pp = load_binding_rates(folder, {"rates": "order/figures-pp-fy2026-27.json"})
    assert pp["gna.scheduled"][0] == rec["eb.claimed.total"][0] != rec["eb.approved.total"][0]


def test_npcl_the_trueup_energy_balance_shows_the_excess_energy_disallowed():
    """Real data: Table 4-19 in its three columns with the ARR year's rules — the original
    approval to the last place; the claim and the true-up within the printed precision of the
    losses.  The claimed and approved totals differ only by the intra-state loss (3.21 % against
    3.18 %), and the computed difference is the 1.32 MU disallowed from the power purchase (A70)."""
    from decimal import Decimal

    import openpyxl

    from tariff_api.arr.reproduce import load_binding_rates, reproduce_cells
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "bindings" / "approval-energy-balance-fy25.json").read_text())
    rec = load_binding_rates(folder, binding)
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    checks = reproduce_cells(wb, binding, load_rules("UPERC"), rates=rec)
    assert {c.result for c in checks if "before" in c.category} == {"match"}
    for c in checks:
        bound = Decimal(c.filed) * 2 * Decimal("0.00005") / Decimal("0.96") + Decimal("0.01")
        assert abs(Decimal(c.filed) - Decimal(c.computed)) <= bound, c
    total = {
        ("claimed" if "claimed" in c.category else "approved"): Decimal(c.exact)
        for c in checks
        if c.output == "eb_total" and "before" not in c.category
    }
    excess = (total["claimed"] - total["approved"]).quantize(Decimal("0.01"))
    pp = load_binding_rates(folder, {"rates": "order/figures-trueup-power-purchase-fy2024-25.json"})
    assert excess == Decimal(rec["eb25.excess"][0]) == Decimal(pp["excess.mu"][0]) == Decimal("1.32")
