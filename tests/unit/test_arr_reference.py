"""Reading a filed format sheet into a reference (milestone 13, R-ACC-1).  SYNTHETIC rows in the
shape of UPERC's "Form No: ARR"; the real workbook is exercised by the reference build, not here."""

from __future__ import annotations

from tariff_api.arr.reference import column_voice, decimals_of, fiscal_year, read_columns, read_sheet
from tariff_api.arr.taxonomy import load_mapping, load_taxonomy

ROWS = [
    ["Form No: ARR", None, None, None, None, None],
    ["Synthetic Power Company Limited", None, None, None, None, None],
    ["Annual Revenue Requirement", None, None, None, None, None],
    [None, None, None, None, None, "Rs. Crores"],
    ["S.No", "Particulars", "True- Up", None, "APR", "ARR"],
    [None, None, "FY 23-24", None, "FY25-26", "FY26-27"],
    [None, None, "Approved\n (in TO)", "Claimed", "Estimated", "Projected"],
    ["II.", "Sale of Power (MU)", 3315.59, 3130.4000000000015, 3951.43, 4399.8428195000015],
    ["III.", "Distribution Loss (%)", 0.0775, 0.0719, 0.0718, 0.06970036526137036],
    ["B", "Expenditure", None, None, None, None],
    ["d", "Depreciation", 52.5, 66.33, 90.09, 106.75180844074569],
    ["g", "Finance Charges", "Incl. in A&G", "Incl. in A&G", 3.96, 4.32],
    ["vi", "Provisions", "NA", "NA", 2.26, 3.0],
    ["b", "Less: Regulatory Discount @10%", -268.14, -254.71, -322.64, -357.07],
]
FMT = [[None] * 6 for _ in ROWS]
for i in range(7, len(ROWS)):
    FMT[i] = [None, None, "0.00", "0.00", "0.00", "0.00"]
FMT[8] = [None, None, "0.00%", "0.00%", "0.00%", "0.00%"]


def test_years_voices_and_formats():
    assert fiscal_year("FY 21-22") == "FY2021-22" and fiscal_year("FY2024-25") == "FY2024-25"
    assert fiscal_year("FY 21-23") is None and fiscal_year("Approved") is None
    assert column_voice("Trued- Up") == ("final_true_up", True)
    assert column_voice("Approved\n (in TO)") == ("approved", True)
    assert column_voice("Audited") == ("actual", False)
    assert column_voice("Projected") == ("petitioned", False)
    assert decimals_of("0.00") == 2 and decimals_of("#,##0") == 0 and decimals_of("0.0%") == 1
    assert decimals_of("General") is None


def test_header_carries_the_year_over_its_group():
    last, cols, notes = read_columns(ROWS)
    assert last == 6 and not notes
    assert [(c.fiscal_year, c.voice, c.restated) for c in cols] == [
        ("FY2023-24", "approved", True),
        ("FY2023-24", "petitioned", False),  # "Claimed" sits under the year printed once to its left
        ("FY2025-26", "petitioned", False),
        ("FY2026-27", "petitioned", False),
    ]


def test_values_states_units_and_display():
    r = read_sheet("ARR", ROWS, FMT, load_taxonomy(), load_mapping("UPERC"))
    assert r.form == "ARR" and r.unit == "INR_crore" and r.title == "Annual Revenue Requirement"
    rows = {x.label: x for x in r.rows}
    assert "Expenditure" not in rows  # a heading row carries no value
    sales = rows["Sale of Power (MU)"].cells[-1]
    assert sales.unit == "MU" and sales.value == "4399.8428195000015" and sales.displayed == "4399.84"
    loss = rows["Distribution Loss (%)"].cells[-1]
    assert loss.unit == "percent" and loss.percent_from_fraction and loss.displayed == "6.97"
    fin = rows["Finance Charges"].cells
    assert fin[0].state == "included" and fin[0].value is None  # a state, never a zero
    assert rows["Provisions"].cells[0].state == "not_applicable"
    assert rows["Less: Regulatory Discount @10%"].unit == "INR_crore"  # "@10%" is not a unit
    assert rows["Depreciation"].line_code == "C.DEP"  # a proposed placement
    restated = [c for c in rows["Depreciation"].cells if c.restated]
    assert [c.voice for c in restated] == ["approved"]  # the petitioner's restatement of the order
