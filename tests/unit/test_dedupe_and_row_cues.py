"""Rules 3: a fact printed twice (table and clause, or a table repeated under a second
heading) is one candidate citing both; a bare number under no charge heading is never a
tariff; a column heading that names the voltage becomes the row's voltage; block text
stops at the table; BHP and HP, 7.5 and 7.50 are the same to the channel comparison;
the model's placeholder category is cleared."""

from __future__ import annotations

from tariff_api.extraction import StructureInput, _rate_block_for, compare_channels, merge_duplicates, rules_extract
from tariff_api.grid_integrity import GridInput, analyse_grids
from tariff_api.providers import coerce_candidates
from tariff_api.tariff_schema import Applicability, Candidate, EvidenceRef, ExtractionOutput


def _cells(grids, role="approved_schedule"):
    out = []
    for r in analyse_grids(grids):
        for c in r.cells:
            d = c.to_dict()
            d["value_state"] = d["normalised"]["value_state"]
            d["region_role"] = role
            out.append(d)
    return out


def _inp(cells, texts, clauses=None, headings=None):
    return StructureInput(
        source_sha="a" * 64,
        profile_id="uperc-npcl",
        schedule_heading_kind="rate_schedule",
        region_role="approved_schedule",
        region_ordinal=1,
        page_indices=sorted(texts),
        cells=cells,
        clauses=clauses or [],
        headings=headings or [],
        page_texts=texts,
        period="FY2026-27",
        utility="NPCL",
        utilities=["NPCL"],
        category_code_pattern=r"\b(?:LMV|HV)\s*[-–]\s*\d+[A-Z]?\b",
    )


def _c(
    value,
    *,
    kind="cell",
    page=374,
    block=None,
    desc=None,
    tb=None,
    unit="percent",
    sign=None,
    comp="tod_adjustment",
    cat="LMV-6",
    line=None,
    grid=0,
):
    return Candidate(
        family="retail_tariff",
        category_code=cat,
        component_type=comp,
        value=value,
        value_state="value",
        original_text=value,
        per_unit=unit,
        sign=sign,
        applicability=Applicability(rate_block=block, description=desc, time_band=tb),
        evidence=[
            EvidenceRef(
                page_index=page,
                kind=kind,
                grid_ordinal=grid if kind == "cell" else None,
                row=1,
                col=1,
                line_no=line,
                excerpt=value,
            )
        ],
    )


def test_a_tod_rate_read_from_the_table_and_the_clause_is_one_candidate_citing_both():
    table = _c(
        "15",
        block="(A) Consumers getting supply other than Rural Schedule",
        desc="19:00 hrs – 02:00 hrs",
        tb="19:00-02:00",
        sign=1,
    )
    clause = _c("15", kind="clause", desc="19:00-02:00", tb="19:00-02:00", sign=1, line=12)
    other_band = _c("15", kind="clause", desc="06:00-10:00", tb="06:00-10:00", sign=1, line=14)
    minus = _c("15", kind="clause", desc="19:00-02:00", tb="19:00-02:00", sign=-1, line=13)
    out = merge_duplicates([clause, table, other_band, minus])
    assert len(out) == 3
    merged = next(c for c in out if c.applicability.time_band == "19:00-02:00" and c.sign == 1)
    assert (
        merged.evidence[0].kind == "cell"
        and len(merged.evidence) == 2
        and "Also printed at page 374 line 12" in merged.notes
    )
    assert merged.applicability.rate_block.startswith("(A)")


def test_the_same_table_under_two_headings_merges_but_different_blocks_with_equal_values_do_not():
    a = _c(
        "300.00",
        page=371,
        block="(A) Public Institutions",
        desc="(A) Public Institutions",
        unit="kW",
        comp="fixed",
        cat="LMV-4",
    )
    b = _c(
        "300.00",
        page=371,
        block="LMV- 4 (A) - PUBLIC INSTITUTIONS:",
        desc="(A) Public Institutions",
        unit="kW",
        comp="fixed",
        cat="LMV-4",
        grid=1,
    )
    c = _c("300.00", page=371, block=None, desc="(A) Public Institutions", unit="kW", comp="fixed", cat="LMV-4", grid=2)
    assert len(merge_duplicates([a, b, c])) == 1
    x = _c("110.00", page=365, block="(a) Rural", desc="Metered", unit="kW", comp="fixed", cat="LMV-1")
    y = _c("110.00", page=365, block="(b) Urban", desc="Metered", unit="kW", comp="fixed", cat="LMV-1", grid=1)
    assert len(merge_duplicates([x, y])) == 2  # equal values under different blocks are two facts
    z = _c("120.00", page=365, block="(a) Rural", desc="Metered", unit="kW", comp="fixed", cat="LMV-1", grid=1)
    assert len(merge_duplicates([x, z])) == 2  # different values never merge


def test_serial_numbers_are_not_charges_and_a_voltage_heading_becomes_the_row_voltage():
    serial = GridInput(400, 0, [["Sl. No.", "Industry"], ["1", "Cement"], ["2", "Steel"]], 1)
    hv2 = GridInput(
        387,
        0,
        [
            ["", "For supply up to 11 kV", "For supply above 11 kV and up to 66 kV"],
            ["Demand Charges", "Rs. 300.00 / kVA / month", "Rs. 290.00 / kVA / month"],
            ["Energy Charges", "Rs. 7.10 / kVAh", "Rs. 6.80 / kVAh"],
        ],
        1,
    )
    texts = {
        400: "1. Cement\n2. Steel\n",
        387: "RATE SCHEDULE HV – 2\n(A) Urban Schedule:\nFor supply up to 11 kV For supply above 11 kV and up to 66 kV\nDemand Charges Rs. 300.00 / kVA / month Rs. 290.00 / kVA / month\n",
    }
    headings = [
        {"page_index": 387, "kind": "rate_schedule", "code_canonical": "HV-2", "text": "RATE SCHEDULE HV – 2"},
        {"page_index": 393, "kind": "rate_schedule", "code_canonical": "HV-4", "text": "RATE SCHEDULE HV – 4"},
    ]
    out = rules_extract(_inp(_cells([serial, hv2]), texts, headings=headings))
    assert not [c for c in out.candidates if c.evidence[0].page_index == 400]
    assert any("unitless number" in m for m in out.missing)
    by = {(c.component_type, c.applicability.voltage): c.value for c in out.candidates if c.category_code == "HV-2"}
    assert (
        by[("demand", "For supply up to 11 kV")] == "300.00"
        and by[("energy", "For supply above 11 kV and up to 66 kV")] == "6.80"
    )
    # the block stops before the voltage header line
    blocks = {c.applicability.rate_block for c in out.candidates if c.category_code == "HV-2"}
    assert blocks == {"(A) Urban Schedule:"}


def test_block_text_never_swallows_a_table_row():
    inp = _inp(
        [{"page_index": 5, "grid_ordinal": 0, "row": 1, "col": 1, "row_path": ["Metered"], "raw": "Rs. 8.50 / kWh"}],
        {
            5: "(b) Metered Supply\nfor all such consumers\nDescription Fixed Charge Energy Charge\nMetered Rs. 250.00 / kW / month Rs. 8.50 / kWh\n"
        },
    )
    assert _rate_block_for(inp, inp.cells[0]) == "(b) Metered Supply for all such consumers"


def test_channels_agree_across_unit_spellings_and_trailing_zeros():
    s = ExtractionOutput(
        candidates=[_c("170.00", page=372, block="(A)", desc="Un-Metered", unit="BHP", comp="fixed", cat="LMV-5")]
    )
    i = ExtractionOutput(
        candidates=[_c("170.0", page=372, block="(A)", desc="Un-Metered", unit="HP", comp="fixed", cat="LMV-5")]
    )
    cmp = compare_channels(s, i)
    assert len(cmp) == 1 and cmp[0].agreement == "agree"
    i.candidates[0].value = "175.00"
    assert compare_channels(s, i)[0].disagreeing_fields == ["value"]


def test_model_placeholder_category_is_cleared():
    obj = {
        "candidates": [
            {
                "family": "retail_tariff",
                "category_code": "<UNKNOWN>",
                "component_type": "rebate",
                "value": "1.00",
                "value_state": "value",
                "original_text": "1.00%",
                "per_unit": "percent",
                "evidence": [{"page_index": 358, "kind": "prose", "excerpt": "1.00 %"}],
            }
        ]
    }
    shaped, rejected = coerce_candidates(obj)
    assert rejected == [] and shaped["candidates"][0]["category_code"] is None


def test_table_and_clause_readings_with_different_row_labels_merge_and_all_families_dedupe():
    from tariff_api.extraction import merge_duplicates

    grid = _c("3.85", page=363, block=None, desc="Metered", unit="kWh", comp="energy", cat="LMV-1")
    grid.applicability.slab = __import__("tariff_api.tariff_schema", fromlist=["Slab"]).Slab(
        original_text="101 - 150 kWh / month"
    )
    clause = _c(
        "3.85",
        kind="clause",
        page=363,
        block="(a) Consumers getting supply as per Rural Schedule",
        desc="101 - 150 kWh / month",
        unit="kWh",
        comp="energy",
        cat="LMV-1",
        line=8,
    )
    out = merge_duplicates([grid, clause])
    assert len(out) == 1 and out[0].evidence[0].kind == "cell" and out[0].applicability.rate_block.startswith("(a)")
    # green tariff: "per unit" from prose and "per kWh" from the clause are one premium
    a = _c("0.34", page=359, block=None, desc="HV category consumers", unit="unit", comp="green_premium", cat=None)
    a.family = "green_tariff"
    b = _c(
        "0.34",
        kind="clause",
        page=359,
        block=None,
        desc="Green Energy Tariff for HV category consumers",
        unit="kWh",
        comp="green_premium",
        cat=None,
        line=3,
    )
    b.family = "green_tariff"
    assert len(merge_duplicates([a, b])) == 1
    # a different row label that is not contained stays separate
    c = _c(
        "0.34",
        kind="clause",
        page=359,
        block=None,
        desc="LMV category consumers",
        unit="kWh",
        comp="green_premium",
        cat=None,
        line=4,
    )
    c.family = "green_tariff"
    assert len(merge_duplicates([a, c])) == 2


def test_serial_columns_are_skipped_even_with_a_unit_bound_from_the_notes_and_group_headings_qualify_rows():
    serial = GridInput(
        400, 0, [["S. No.", "Industry"], ["1", "Cement"], ["2", "Steel"], ["3", "Paper"]], 1, title_lines=["Rs. / kVA"]
    )
    lmv3 = GridInput(
        369,
        0,
        [
            ["Description", "Nagar Nigam", "Nagar Palika"],
            ["Metered", "Rs. 8.50 / kWh", "Rs. 7.50 / kWh"],
        ],
        1,
    )
    texts = {
        400: "1 Cement\n2 Steel\n3 Paper\n",
        369: "RATE SCHEDULE LMV - 3\n(b) Metered Supply:\nDescription Nagar Nigam Nagar Palika\nMetered Rs. 8.50 / kWh Rs. 7.50 / kWh\n",
    }
    headings = [
        {"page_index": 369, "kind": "rate_schedule", "code_canonical": "LMV-3", "text": "RATE SCHEDULE LMV - 3"},
        {"page_index": 393, "kind": "rate_schedule", "code_canonical": "HV-4", "text": "RATE SCHEDULE HV – 4"},
    ]
    out = rules_extract(_inp(_cells([serial, lmv3]), texts, headings=headings))
    assert not [c for c in out.candidates if c.evidence[0].page_index == 400]
    rows = {c.applicability.description: c.value for c in out.candidates if c.category_code == "LMV-3"}
    assert rows == {"Metered · Nagar Nigam": "8.50", "Metered · Nagar Palika": "7.50"}
