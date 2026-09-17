"""Readers 3 / grid 3 / CSS keying: a ruled row whose numeric cells stack several printed
lines is several rows (NPCL page 316, the CSS computation table read as one row per voltage
group); a voltage-only divider row scopes the rows under it; the CSS parameter table keyed
by category and voltage pairs with the approved row for that category and band, and its
`L` column is a formula input, never an open-access loss."""

from __future__ import annotations

from tariff_api import css_formula
from tariff_api.extraction import StructureInput, network_extract
from tariff_api.grid_integrity import GridInput, analyse_grids
from tariff_api.readers import split_tall_rows

PAT = r"\b(?:LMV|HV)\s*-\s*\d+[A-Z]?\b"


def test_stacked_numeric_lines_split_into_printed_rows_and_a_group_label_spans_them():
    rows = [
        ["----- 33 kV -----", "", "", "", "", "", ""],
        [
            "1\n2\n3",
            "HV-1\nHV-2\nHV-3",
            "7.70\n7.50\n6.90",
            "1.10\n1.10\n1.10",
            "0.00\n0.00\n0.00",
            "4.50\n4.50\n4.50",
            "15.56\n15.56\n15.56",
        ],
    ]
    out, n = split_tall_rows(rows)
    assert n == 1 and len(out) == 4
    assert out[1] == ["1", "HV-1", "7.70", "1.10", "0.00", "4.50", "15.56"]
    assert out[3][1:3] == ["HV-3", "6.90"]


def test_two_line_headings_and_wrapped_prose_never_split():
    heading = [["Fixed charge\n(Rs/kVA/month)", "Energy charge\n(Rs/kWh)"]]
    assert split_tall_rows(heading) == (heading, 0)
    prose = [["Consumers getting supply\nat 11 kV", "380.00", "7.70"]]
    assert split_tall_rows(prose) == (prose, 0)
    # a stacked cell next to prose that also stacks two lines but is not numeric: not a split
    mixed = [["a\nb", "1.0\n2.0", "text"]]
    assert split_tall_rows(mixed) == (mixed, 0)


def _computation_grid():
    return GridInput(
        316,
        0,
        [
            ["Sl", "Category", "T", "D", "R", "C", "L", "[C/(1-L/100)+D+R]", "S"],
            ["----- 33 kV -----", "", "", "", "", "", "", "", ""],
            ["1", "HV-1", "7.70", "1.10", "0.00", "4.50", "10.00", "6.10", "1.60"],
            ["2", "HV-2", "7.50", "1.10", "0.00", "4.50", "10.00", "6.10", "1.40"],
            ["----- 11 kV -----", "", "", "", "", "", "", "", ""],
            ["3", "HV-1", "7.70", "1.30", "0.00", "4.50", "15.56", "6.63", "1.07"],
        ],
        1,
    )


def _cells(records, role):
    out = []
    for r in records:
        for c in r.cells:
            d = c.to_dict()
            d["value_state"] = d["normalised"]["value_state"]
            d["region_role"] = role
            out.append(d)
    return out


def test_divider_rows_scope_the_rows_below_and_emit_no_cells():
    cells = _cells(analyse_grids([_computation_grid()]), "network_charges")
    assert not any(c["row"] == 1 for c in cells) and not any(c["row"] == 4 for c in cells)
    paths = {(c["row"], tuple(c["row_path"])) for c in cells}
    assert (2, ("HV-1", "33 kV")) in paths and (5, ("HV-1", "11 kV")) in paths


def test_parameters_are_keyed_by_category_and_band_and_pair_with_the_approved_row():
    cells = _cells(analyse_grids([_computation_grid()]), "network_charges")
    params, consumed = css_formula.read_parameters(cells, PAT)
    assert consumed == {(316, 0)}
    assert set(params) == {"HV-1 @ 33 kV", "HV-2 @ 33 kV", "HV-1 @ 11 kV"}
    p = params["HV-1 @ 11 kV"]
    assert p["L"]["unit"] == "percent" and p["L"]["value"] == "15.56" and p["S"]["value"] == "1.07"
    comp = css_formula.compute(p)
    # 7.70 - (4.50 / (1 - 0.1556) + 1.30 + 0) = 1.0710...
    assert comp["computed"].startswith("1.07") and comp["missing"] == []
    assert css_formula.lookup_keys("HV-1", "11 kV") == ["HV-1 @ 11 kV", "11 kV", "HV-1"]

    # the approved CSS table on the next page: the HV-1 rows pair by category AND band, and
    # the L column above was consumed as a formula input, never filed as an open-access loss
    approved = GridInput(
        317,
        0,
        [
            ["Category", "Voltage", "Approved CSS (Rs/kWh)"],
            ["HV-1", "33 kV", "1.60"],
            ["HV-1", "11 kV", "1.07"],
        ],
        1,
    )
    all_cells = cells + _cells(analyse_grids([approved]), "network_charges")
    inp = StructureInput(
        source_sha="c" * 64,
        profile_id="uperc-npcl",
        schedule_heading_kind="rate_schedule",
        region_role="network_charges",
        region_ordinal=3,
        page_indices=[316, 317],
        cells=all_cells,
        page_texts={316: "S = T - [C/(1-L/100)+D+R]\nwhere T is the tariff payable by the category\n"},
        period="FY2026-27",
        utility="NPCL",
        utilities=["NPCL"],
        category_code_pattern=PAT,
    )
    out = network_extract(inp, "cross_subsidy_surcharge")
    assert not [c for c in out.candidates if c.family == "oa_loss"]
    css = {
        (c.category_code, c.applicability.voltage): c for c in out.candidates if c.family == "cross_subsidy_surcharge"
    }
    assert set(css) == {("HV-1", "33 kV"), ("HV-1", "11 kV"), ("HV-2", "33 kV")}  # HV-2: formula candidate
    d11 = css[("HV-1", "11 kV")].derivation["formula"]
    assert d11["level"] == "HV-1 @ 11 kV" and d11["inputs"]["L"]["value"] == "15.56"
    assert d11["computed"].startswith("1.07") and d11["formula_as_printed"]["page_index"] == 316
    d33 = css[("HV-1", "33 kV")].derivation["formula"]
    assert d33["inputs"]["D"]["value"] == "1.10" and d33["printed_computed"] == "1.60"
    # HV-2 has inputs and a printed S but no approved row: a formula candidate of its own
    assert any(
        c.category_code == "HV-2" and c.value == "1.40" and c.derivation.get("rule") == "css_formula"
        for c in out.candidates
    )
