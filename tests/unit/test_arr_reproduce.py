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
        rep = reproduce(sheets[binding["sheet"]], binding, rules, sheets)
        seen[rep.sheet] = rep
        for c in rep.checks:
            col = (c.fiscal_year, c.voice)
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
    assert seen["F25_IOL"].counts()["match"] >= 21 and seen["F26_ROE"].counts()["match"] >= 22
