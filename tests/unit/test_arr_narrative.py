"""The narrative reconciled to the formats (R-ACC-5): figures parsed as printed, traced among the
formats' cells without calling a chance match a trace, and summary tables bound row by row."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from tariff_api.arr.narrative import (
    FormatIndex,
    Printed,
    Table,
    parse_figure,
    read_docx_tables,
    reconcile,
    reconcile_tables,
)

ROOT = Path(__file__).resolve().parents[2]


def test_figures_are_parsed_as_printed():
    assert parse_figure("1,234.56") == Printed(Decimal("1234.56"), 2, False)
    assert parse_figure("(1,082.18)") == Printed(Decimal("-1082.18"), 2, False)
    assert parse_figure("-12.5") == Printed(Decimal("-12.5"), 1, False)
    assert parse_figure("12%") == Printed(Decimal("12"), 0, True)
    assert parse_figure("Rs. 5") == Printed(Decimal("5"), 0, False)
    for text in ("", "-", "NA", "FY 24-25", "1,2,3", "(12", "05:00– 11:00 hrs", "Table 58"):
        assert parse_figure(text) is None, text
    assert Printed(Decimal("452.58"), 2, False).digits == 5
    assert Printed(Decimal("0.05"), 2, False).digits == 1


def _book(cells: dict[str, float]):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ARR"
    for ref, v in cells.items():
        ws[ref] = v
    return wb


def test_a_figure_is_traced_near_opposite_or_untraced_and_a_short_one_is_never_traced():
    idx = FormatIndex({"f": _book({"A1": 2728.7687, "A2": -289.7869, "A3": 12.0, "A4": 0.125})})
    rows = [
        ["ARR", "2,728.77"],
        ["ARR", "2,728.76"],
        ["Gap", "289.79"],
        ["Other", "5,555.55"],
        ["Pct", "12%"],
        ["Share", "12.50%"],
    ]
    out = reconcile([Table("d.docx", 0, "T", rows)], idx)
    got = [(f["text"], f["result"]) for f in out["figures"]]
    assert got == [
        ("2,728.77", "traced"),
        ("2,728.76", "near"),
        ("289.79", "opposite_sign"),
        ("5,555.55", "untraced"),
        ("12%", "uninformative"),  # two digits: a large workbook holds a 12 somewhere by chance
        ("12.50%", "traced"),  # a percentage is found as a fraction too (0.125)
    ]
    assert out["figures"][0]["cells"] == ["f::ARR!A1"]
    assert out["summary"]["d.docx"]["traced"] == 2


def test_docx_tables_keep_a_merged_cell_once_and_take_their_title(tmp_path):
    import docx

    d = docx.Document()
    d.add_paragraph("Table 9: Summary of ARR (Rs. Cr.)")
    t = d.add_table(rows=2, cols=3)
    t.cell(0, 0).merge(t.cell(0, 2)).text = "merged heading"
    t.cell(1, 0).text, t.cell(1, 1).text, t.cell(1, 2).text = "1", "Depreciation", "106.75"
    d.save(tmp_path / "n.docx")
    (table,) = read_docx_tables(tmp_path / "n.docx")
    assert table.rows == [["merged heading"], ["1", "Depreciation", "106.75"]]
    assert table.title == "merged heading"  # a first row of one merged cell is the title


BINDING = {
    "sheet": "ARR",
    "rows": [
        {"key": "interest", "label": r"interest charges", "rows": [37, 38]},
        {"key": "gap", "label": r"revenue gap", "rows": [58], "sign": -1},
        {"key": "other", "label": r"other business", "rows": [49]},
        {"key": "nti", "label": r"non-tariff income", "rows": [50]},
    ],
    "tables": [{"document": "d.docx", "title": "Table 1", "columns": {"2": {"column": "M", "header": "Projected"}}}],
}


def _tables(rows):
    return {"d.docx": [Table("d.docx", 0, "Table 1: Summary", [["S. No.", "Particulars", "Projected"], *rows])]}


def test_a_summary_table_is_bound_row_by_row_with_sums_signs_and_dashes():
    wb = _book({"M37": 83.875, "M38": 35.436, "M58": -289.7869, "M49": 0.0, "M50": 10.2903})
    rows = [
        ["1", "Interest Charges", "119.31"],
        ["2", "Revenue Gap", "289.79"],
        ["3", "Other business", "-"],
        ["4", "Non-Tariff Income", "10.30"],
    ]
    got = {c["key"]: (c["result"], c.get("last_place_units")) for c in reconcile_tables(BINDING, wb, _tables(rows))}
    assert got == {"interest": ("match", None), "gap": ("match", None), "other": ("match", None), "nti": ("differs", 1)}
    blank = reconcile_tables(BINDING, wb, _tables([["4", "Non-Tariff Income", ""]]))
    assert blank[0]["result"] == "not_printed"


def test_a_binding_never_guesses_a_table_a_column_or_a_row():
    wb = _book({"M50": 1.0})
    with pytest.raises(ValueError, match="0 tables"):
        reconcile_tables({**BINDING, "tables": [{**BINDING["tables"][0], "title": "Table 2"}]}, wb, _tables([]))
    wrong = {**BINDING, "tables": [{**BINDING["tables"][0], "columns": {"2": {"column": "M", "header": "Approved"}}}]}
    with pytest.raises(ValueError, match="not headed"):
        reconcile_tables(wrong, wb, _tables([]))
    with pytest.raises(ValueError, match="matches rows"):
        reconcile_tables(BINDING, wb, _tables([["1", "Non-Tariff Income", "1.00"], ["2", "Non-Tariff Income", "1.00"]]))


def test_npcl_narrative_summary_tables_against_the_arr_format():
    """Real data: nine summary tables (Appendices III–V, the executive summary, Form-1) bound to the
    ARR format: every claimed, estimated and projected figure matches; the differences are in the
    approved columns — Form-1's approved ARR and open-access revenue (A56), the APR's opening
    surplus (A57), the true-up's carried-forward after provisions (A58), and last-place roundings."""
    import openpyxl

    folder = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
    binding = json.loads((folder / "narrative" / "summary-tables.json").read_text())
    wb = openpyxl.load_workbook(folder / binding["workbook"], data_only=True)
    docs = {t["document"] for t in binding["tables"]}
    checks = reconcile_tables(binding, wb, {d: read_docx_tables(folder / d) for d in docs})
    assert len(checks) == 253
    differs = [c for c in checks if c["result"] != "match"]
    assert len(differs) == 21 and all(c["column"] == "Approved" for c in differs)
    form1 = {c["key"]: c["last_place_units"] for c in differs if c["table"].startswith("Table-II:")}
    assert form1["arr"] == -1031 and form1["open_access"] == 5301
