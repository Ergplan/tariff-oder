"""The petition fill (increment 150): the rule engine fills a formats workbook from its inputs —
blank computed cells filled, an entered figure never overwritten (checked instead), a carried
cell copying the figure it repeats, a blocked output left blank with its reason — and, on NPCL's
filed FY2026-27 workbook, the round trip: every cell the engine computes blanked, filled again,
compared with the filing."""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[2]


def _book():
    wb = openpyxl.Workbook()
    s = wb.active
    s.title = "S"
    s["A1"], s["A2"] = 2, 3  # inputs
    s["C1"], s["C2"] = 10, 1
    s["C3"] = 7  # an entered total that the lines do not give (10 + 1 = 11)
    wb.create_sheet("T")
    return wb


def _binding(checks_a, checks_c, extra=()):
    lines = lambda rows: {f"row {r}": {"inputs": {"record:line_number": [r, "number"]}} for r in rows}  # noqa: E731
    return {
        "type": "cells",
        "workbook": "x.xlsx",
        "sheet": "S",
        "places": 6,
        "evaluations": [
            {
                "fiscal_year": "FY2026-27",
                "label": "a",
                "categories": lines(["A1", "A2"]),
                "checks": {"lines_number_total": checks_a},
            },
            {
                "fiscal_year": "FY2026-27",
                "label": "c",
                "categories": lines(["C1", "C2"]),
                "checks": {"lines_number_total": checks_c},
            },
            *extra,
        ],
    }


def test_a_fill_writes_blanks_carries_ties_and_never_overwrites_an_entered_figure():
    from tariff_api.arr.petition_fill import fill
    from tariff_api.arr.rules import load_rules

    wb = _book()
    blocked = {
        "fiscal_year": "FY2026-27",
        "label": "d",
        "categories": {"row D1": {"inputs": {"record:line_number": ["D1", "number"]}}},
        "checks": {"lines_number_total": "D3"},
    }
    b = _binding(["A3", "T!B2"], "C3", [blocked])
    rep = fill(wb, {"sheets": []}, [("b.json", b)], load_rules("UPERC"), "synthetic")
    assert wb["S"]["A3"].value == 5 and wb["T"]["B2"].value == 5  # computed, and carried as A3 holds it
    assert wb["S"]["C3"].value == 7  # entered: kept
    differs = [c for c in rep.checked if c.result == "differs"]
    assert [(c.cell, c.present, c.computed) for c in differs] == [("S!C3", "7", "11")]
    assert {(w.cell, w.kind) for w in rep.written} == {("S!A3", "computed"), ("T!B2", "carried")}
    assert wb["S"]["D3"].value is None and [x.cell for x in rep.blocked] == ["S!D3"]  # D1 blank: nothing defaulted
    # a carried cell follows its format's figure as it stands — an entered one too
    wb2 = _book()
    wb2["S"]["A3"] = 6
    fill(wb2, {"sheets": []}, [("b.json", b)], load_rules("UPERC"), "synthetic")
    assert wb2["S"]["A3"].value == 6 and wb2["T"]["B2"].value == 6


def test_a_fill_map_limits_what_is_written():
    from tariff_api.arr.petition_fill import fill
    from tariff_api.arr.rules import load_rules

    wb = _book()
    rep = fill(
        wb, {"sheets": []}, [("b.json", _binding(["A3", "T!B2"], "C3"))], load_rules("UPERC"), "s", targets={"S!A3"}
    )
    assert wb["S"]["A3"].value == 5 and wb["T"]["B2"].value is None
    assert [w.cell for w in rep.written] == ["S!A3"]


def test_npcl_round_trip_every_cell_the_engine_computes_refills_as_filed():
    """Real data, NPCL's FY2026-27 formats workbook: the fill map (4,492 cells: 4,406 computed by the
    bindings, 86 carried where the filing's formula links them) blanked — but for the 49 cells whose
    reproduction already differs from the filing, kept as filed — and filled again from what is left:
    every cell equals the filing at its printed precision, no conflict, nothing left blank.  With
    none kept (fill-roundtrip.json), 4,427 / 4,492: the known differences and what follows from them."""
    from tariff_api.arr import petition_fill as pf
    from tariff_api.arr.rules import load_rules

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    book = next(p for p in folder.glob("*.xlsx") if "Format" in p.name)
    fmap = json.loads((folder / "fill-map.json").read_text())["cells"]
    rt = json.loads((folder / "fill-roundtrip.json").read_text())
    assert len(fmap) == 4492 and sum(v["kind"] == "carried" for v in fmap.values()) == 86
    assert rt["runs"]["known_kept"]["reproduced"] == rt["runs"]["known_kept"]["targets"] == 4443
    assert rt["runs"]["none_kept"]["reproduced"] == 4427 and rt["runs"]["none_kept"]["not_filled"] == 0
    rules = load_rules("UPERC")
    layout = json.loads((folder / "reference.json").read_text())
    bindings, skipped = pf.fill_bindings(folder)
    assert {s["binding"] for s in skipped} >= {"chain-arr.json", "esr2-sales-at-cagr.json", "pipeline-petition.json"}
    live = pf.round_trip(book, rules, layout, bindings, fmap, "npcl", runs=("known_kept",))
    run = live["runs"]["known_kept"]
    assert live["known_differences"] == rt["known_differences"] and len(rt["known_differences"]) == 49
    assert (run["targets"], run["reproduced"], run["not_filled"], run["conflicts"]) == (4443, 4443, 0, [])
