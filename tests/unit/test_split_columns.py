"""A schedule table whose logical columns arrive as several reader columns (NPCL page 384:
nine columns for three) is collapsed before header binding, so each number sits under its own
heading, and cells still cite the reader's column."""

from __future__ import annotations

from tariff_api.grid_integrity import GridInput, analyse_grid, collapse_split_columns

NINE = [
    ["", "Contracted Load", "", "", "Fixed Charge", "", "", "Energy Charge", ""],
    ["For supply at 11kV", "", "", "Rs. 380.00 / kVA / month", "", "", "Rs. 7.70 / kVAh", "", ""],
    ["For supply above 11kV", "", "", "Rs. 360.00 / kVA / month", "", "", "Rs. 7.50/ kVAh", "", ""],
]


def test_split_columns_collapse_to_the_logical_three():
    rows, groups = collapse_split_columns(NINE, 1)
    assert groups == [[0, 1, 2], [3, 4, 5], [6, 7, 8]]
    assert rows[0] == ["Contracted Load", "Fixed Charge", "Energy Charge"]
    assert rows[1] == ["For supply at 11kV", "Rs. 380.00 / kVA / month", "Rs. 7.70 / kVAh"]


def test_columns_that_co_occur_are_never_merged():
    rows = [["Slab", "Fixed", "Energy"], ["0-100", "50", "3.00"], ["101-300", "", "4.00"]]
    merged, groups = collapse_split_columns(rows, 1)
    assert groups == [[0], [1], [2]] and merged == rows


def test_sparse_grids_without_the_shaded_heading_signature_are_left_alone():
    # a continuation grid with no header row and a merged (empty) label column
    cont = [["", "Rs. 90.00/ kW / month", "Rs. 4.00 / kWh", "Above 500 kWh / month"]]
    assert collapse_split_columns(cont, 0)[1] == [[0], [1], [2], [3]]
    # an empty remarks column next to a full one: heading and numbers share a column, so no merge
    remarks = [["Slab", "Rate", "Remarks"], ["0-100", "3.00", ""], ["101-300", "4.00", ""]]
    assert collapse_split_columns(remarks, 1)[1] == [[0], [1], [2]]


def test_numbers_bind_to_their_own_heading_and_cite_the_reader_column():
    rec = analyse_grid(GridInput(page_index=384, ordinal=1, rows=NINE, header_rows=1), None)
    assert "split_columns_merged" in rec.flags
    by_raw = {c.raw: c for c in rec.cells}
    fixed = by_raw["Rs. 380.00 / kVA / month"]
    energy = by_raw["Rs. 7.70 / kVAh"]
    assert fixed.header_path == ["Fixed Charge"] and fixed.per_unit == "kVA" and fixed.frequency == "per_month"
    assert energy.header_path == ["Energy Charge"] and energy.per_unit == "kVAh"
    assert fixed.row_path == ["For supply at 11kV"] == energy.row_path
    assert (fixed.row, fixed.col) == (1, 3) and (energy.row, energy.col) == (1, 6)  # reader columns, not merged ones
