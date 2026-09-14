"""Section 6.6 table integrity over synthetic grids shaped like the hazards in Parts D and E:
continuation with the header repeated or omitted (S10), merged cells spanning a page break
(D.2 hazard 1, S12), multi-level headers with units in the header (S11, E.1), a row unit
column (E.1), units in cells (D.1), footnotes (S16), mixed units in one table (V1),
Nil / - / NA / blank (V2), Indian numbers (V3), signed percentages (V4), ambiguous slabs (V5),
and the rule that an unresolved cell is listed, never defaulted."""

from __future__ import annotations

from tariff_api.grid_integrity import GRID_VERSION, GridInput, analyse_grids, header_paths, summarise

HDR = ["Description", "Fixed Charge", "Energy Charge", "Slab"]


def _uperc_pages():
    g1 = GridInput(
        362,
        0,
        [HDR, ["Metered", "Rs. 90.00/ kW / month", "Rs. 3.00/ kWh", "Up to 100 kWh / month"]],
        1,
        title_lines=["RATE SCHEDULE LMV - 1", "(a) Consumers getting supply as per 'Rural Schedule'"],
    )
    g2 = GridInput(
        363,
        0,
        [
            HDR,  # header repeated on the continuation page
            ["", "", "Rs. 3.50/ kWh", "101 - 150 kWh / month"],
            ["", "", "Rs. 4.00/ kWh", "151 - 300 kWh / month"],
            ["", "", "Rs. 5.00/ kWh *", "Above 300 kWh / month"],
        ],
        1,
        footnote_lines=["* subject to the regulatory discount of general provision 21"],
    )
    g3 = GridInput(364, 0, [["", "", "Rs. 5.50/ kWh", "Above 500 kWh / month"]], 0)  # no header at all
    return g1, g2, g3


def test_continuation_inherits_header_and_propagates_merged_cells_across_the_page_break():
    r1, r2, r3 = analyse_grids(list(_uperc_pages()))
    assert r1.continuation_of is None and r1.label_columns == [0, 3]
    assert r2.continuation_of == (362, 0) and "header_repeated" in r2.flags and not r2.header_inherited
    assert r3.continuation_of == (363, 0) and r3.header_inherited and "header_inherited" in r3.flags
    # every slab row on page 363 carries Metered and the fixed charge from page 362, marked
    fixed = [c for c in r2.cells if c.col == 1]
    assert [c.raw for c in fixed] == ["Rs. 90.00/ kW / month"] * 3
    assert all("merged_cell_propagated" in c.flags for c in fixed)
    assert [c.row_path for c in r2.cells if c.col == 2] == [
        ["Metered", "101 - 150 kWh / month"],
        ["Metered", "151 - 300 kWh / month"],
        ["Metered", "Above 300 kWh / month"],
    ]
    assert all(c.header_path == ["Energy Charge"] for c in r2.cells if c.col == 2)
    page3 = [c for c in r3.cells if c.col == 2]
    assert page3[0].row_path == ["Metered", "Above 500 kWh / month"]
    assert {"header_inherited", "merged_cell_propagated"} <= set(page3[0].flags)
    assert all(c.resolved for r in (r1, r2, r3) for c in r.cells)


def test_units_bound_from_cells_with_the_source_recorded_and_slabs_parsed():
    r1, r2, _ = analyse_grids(list(_uperc_pages()))
    fixed = next(c for c in r1.cells if c.col == 1)
    assert (fixed.currency, fixed.per_unit, fixed.frequency, fixed.unit_source) == ("rupees", "kW", "per_month", "cell")
    energy = next(c for c in r1.cells if c.col == 2)
    assert (energy.currency, energy.per_unit, energy.unit_source) == ("rupees", "kWh", "cell")
    assert energy.slab["upper"] == "100" and energy.slab["unit"] == "kWh"
    assert "mixed_units_in_grid" in r1.flags  # kW beside kWh: adjacent columns with different denominators (S18)
    starred = next(c for c in r2.cells if c.raw.endswith("*"))
    assert starred.footnotes == ["subject to the regulatory discount of general provision 21"]
    assert "footnote_attached" in starred.flags and starred.normalised["value"] == "5.00"


def test_kerc_units_from_header_and_billing_unit_column_with_spanning_super_header():
    k = GridInput(
        238,
        0,
        [
            [
                "Category",
                "Description",
                "Fixed Charges Billing Unit",
                "Fixed Charges (In Rupees)",
                "",
                "Energy Charges (Paise/Unit)",
                "",
            ],
            ["", "", "", "FY2025-26", "FY2026-27", "FY2025-26", "FY2026-27"],
            ["LT-1", "Bhagya Jyothi", "per KW", "145", "150", "580", "590"],
            ["LT-4(a)", "IP sets up to 10 HP", "per HP", "-", "-", "610", "620"],
        ],
        2,
        title_lines=["Table 6.3A Approved tariff for FY2025-26"],
    )
    (r,) = analyse_grids([k])
    assert r.label_columns == [0, 1] and r.row_unit_column == 2
    assert r.header_paths[4] == ["Fixed Charges (In Rupees)", "FY2026-27"]  # super-header spans the year columns
    by = {(c.row, c.col): c for c in r.cells}
    fixed = by[(2, 3)]
    assert (fixed.currency, fixed.per_unit, fixed.unit_source) == ("rupees", "kW", "row_unit_column")
    assert fixed.row_path == ["LT-1", "Bhagya Jyothi"] and fixed.header_path == [
        "Fixed Charges (In Rupees)",
        "FY2025-26",
    ]
    assert "header_span_inherited" in by[(2, 4)].flags and "header_span_inherited" not in fixed.flags
    energy = by[(2, 5)]
    assert (energy.currency, energy.per_unit, energy.unit_source) == ("paise", "unit", "header")
    ip = by[(3, 3)]
    assert ip.normalised["value_state"] == "not_applicable" and ip.normalised["value"] is None  # E.1: `-` is never zero
    assert (by[(3, 5)].per_unit, by[(3, 5)].currency) == ("unit", "paise")
    assert all(c.resolved for c in r.cells)


def test_mixed_units_nil_na_blank_indian_numbers_and_signed_percent():
    m = GridInput(
        10,
        0,
        [
            ["Category", "Fixed (Rs/kVA/month)", "Energy (paise/kWh)", "TOD (% of Energy Charges)", "Minimum"],
            ["HV-1", "430", "650", "(+) 15%", "1,00,000"],
            ["HV-2", "Nil", "NA", "0", "–"],
            ["HV-3", "", "7.50", "(-) 15%", "12"],
        ],
        1,
    )
    (r,) = analyse_grids([m])
    by = {(c.row, c.col): c for c in r.cells}
    assert "mixed_units_in_grid" in r.flags  # V1: Rs/kVA/month beside paise/kWh
    assert (by[(1, 1)].currency, by[(1, 1)].per_unit, by[(1, 1)].frequency) == ("rupees", "kVA", "per_month")
    assert (by[(1, 2)].currency, by[(1, 2)].per_unit) == ("paise", "kWh")
    assert by[(1, 3)].per_unit == "percent" and by[(1, 3)].normalised["sign"] == 1
    assert by[(3, 3)].normalised["sign"] == -1
    assert by[(2, 3)].normalised["value_state"] == "zero" and by[(2, 3)].per_unit == "percent"  # bare 0 in a % column
    assert (
        by[(1, 4)].normalised["value"] == "100000" and "unit_unresolved" in by[(1, 4)].flags
    )  # V3, and no unit anywhere
    assert by[(2, 1)].normalised["value_state"] == "zero" and "nil_word" in by[(2, 1)].flags
    assert by[(2, 2)].normalised["value_state"] == "not_applicable"
    assert by[(2, 4)].normalised["value_state"] == "not_applicable"
    assert (3, 1) not in by  # a blank cell with nothing to propagate is not a cell
    s = summarise([r])
    assert s["version"] == GRID_VERSION and s["cells"] == 11 and s["unresolved"] == 3
    assert s["unit_sources"] == {
        "header": 8,
        "none": 3,
    }  # % base named in the header; three cells have no unit anywhere


def test_unresolved_header_and_row_are_flagged_never_defaulted():
    g = GridInput(5, 0, [["", "", ""], ["", "6.50", "7.00"]], 1)  # empty header row, empty label
    (r,) = analyse_grids([g])
    assert all({"unresolved_header", "unresolved_row", "unit_unresolved"} <= set(c.flags) for c in r.cells)
    assert not any(c.resolved for c in r.cells)
    assert summarise([r])["unresolved"] == 2


def test_adjacent_slab_rows_claiming_a_boundary_are_ambiguous():
    g = GridInput(
        7,
        0,
        [
            ["Slab", "Energy Charge"],
            ["up to 100", "Rs. 3.00/kWh"],
            ["100 - 300", "Rs. 4.00/kWh"],
            ["above 300", "Rs. 5.00/kWh"],
        ],
        1,
    )
    (r,) = analyse_grids([g])
    incl = [c.slab["inclusivity"] for c in r.cells]
    assert incl == ["ambiguous", "ambiguous", "inferred"]
    assert "slab_inclusivity_ambiguous" in r.cells[0].flags and "slab_inclusivity_ambiguous" not in r.cells[2].flags


def test_header_paths_join_levels_and_report_spans():
    paths, inherited = header_paths([["Energy Charge", "", "Fixed"], ["Rs/kWh", "Peak", "Rs/kW"]], 2)
    assert paths == [["Energy Charge", "Rs/kWh"], ["Energy Charge", "Peak"], ["Fixed", "Rs/kW"]]
    assert inherited == [False, True, False]
