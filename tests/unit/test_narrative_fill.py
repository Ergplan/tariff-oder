"""The narrative's summary tables filled from a formats workbook (increment 153): figures printed
in the cell's own style, and NPCL's nine bound tables refilled from the filed workbook — every
cell that changes is one increment 93 found differing, the one merged cell is left as filed,
the petitioner's own rows are marked, and a figure changed in the workbook reaches every table
that restates it."""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path

import pytest

from tariff_api.arr.narrative import read_docx_tables, reconcile_tables
from tariff_api.arr.narrative_fill import FILLED_SHADE, NOTE, OWN_SHADE, fill_narrative, render

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"


@pytest.mark.parametrize(
    ("value", "like", "expected"),
    [
        ("1234.567", "1,000.00", "1,234.57"),
        ("-1163.254", "(1,163.25)", "(1,163.25)"),
        ("-49.905", "(49.92)", "(49.91)"),
        ("-49.9", "-49.92", "-49.90"),
        ("0", "-", "-"),
        ("0.001", "0.00", "0.00"),
        ("-0.001", "(0.00)", "0.00"),
        ("12.345", "11.5%", "12.3%"),
        ("1234567.891", "12,34,567.89", "12,34,567.89"),
        ("1234567.891", "1,234,567.89", "1,234,567.89"),
        ("2728.765", "", "2,728.77"),
        ("452", "450", "452"),
    ],
)
def test_render_prints_in_the_cells_style(value, like, expected):
    assert render(Decimal(value), like) == expected


def _npcl():
    openpyxl = pytest.importorskip("openpyxl")
    binding = json.loads((PKG / "narrative" / "summary-tables.json").read_text())
    wb = openpyxl.load_workbook(PKG / binding["workbook"], data_only=True)
    docs = {t["document"]: (PKG / t["document"]).read_bytes() for t in binding["tables"]}
    return binding, wb, docs


def _reread(out: dict[str, bytes], tmp_path: Path) -> dict:
    for n, data in out.items():
        (tmp_path / n).write_bytes(data)
    return {n: read_docx_tables(tmp_path / n) for n in out}


def test_npcl_narrative_refilled_from_its_own_formats(tmp_path):
    binding, wb, docs = _npcl()
    before = reconcile_tables(binding, wb, {n: read_docx_tables(PKG / n) for n in docs})
    differs = {(r["document"], r["table"], r["key"], r["column"]) for r in before if r["result"] == "differs"}
    assert len(differs) == 21  # increment 93: A56, A57, A58 and last-place roundings

    out, rep = fill_narrative(binding, wb, docs)
    s = rep.summary()
    assert (s["documents"], s["tables"]) == (5, 9)
    written = {(c.document, c.table, c.key, c.column) for c in rep.cells if c.result == "written"}
    merged = [c for c in rep.cells if c.result == "merged"]
    # every cell the fill changes is one the reconciliation found differing; the one it does not
    # change is Form-1's open-access figure, one cell merged down over the NTI row (A56)
    assert written <= differs and len(written) == 20
    # the merged cell is both rows' figure: right for NTI, wrong for open access — left as filed
    assert sorted((c.key, c.before, c.value) for c in merged) == [
        ("nti", "53.01", "53.01"),
        ("open_access", "53.01", "0"),
    ]
    assert differs - written == {(m.document, m.table, m.key, m.column) for m in merged if m.key == "open_access"}
    # the rows the binding does not cover stay the petitioner's own, listed (A58's provisions among them)
    assert len(rep.own) == 7 and any("provisions" in o.label.lower() for o in rep.own)

    after = reconcile_tables(binding, wb, _reread(out, tmp_path))
    left = [r for r in after if r["result"] != "match"]
    assert len(after) == 253 and [(r["key"], r["printed"]) for r in left] == [("open_access", "53.01")]

    import docx

    d = docx.Document(io.BytesIO(out["2. Petition in Form-1 ARR FY 2026-27.docx"]))
    assert d.paragraphs[0].text == NOTE
    fills = {
        e.get("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill")
        for e in d.element.iter()
        if e.tag.endswith("}shd")
    }
    assert {FILLED_SHADE, OWN_SHADE} <= fills


def test_a_changed_format_figure_reaches_every_table_that_restates_it(tmp_path):
    binding, wb, docs = _npcl()
    wb["ARR"]["M46"].value = 9999.994  # the projected ARR, FY2026-27
    out, rep = fill_narrative(binding, wb, docs)
    arr = [c for c in rep.cells if c.key == "arr" and c.column == "Projected"]
    assert len(arr) == 3 and all(c.after == "9,999.99" and c.result == "written" for c in arr)
    tables = _reread(out, tmp_path)
    printed = [r for r in reconcile_tables(binding, wb, tables) if r["key"] == "arr" and r["column"] == "Projected"]
    assert [r["printed"] for r in printed] == ["9,999.99"] * 3


def test_a_missing_document_or_table_is_an_error():
    binding, wb, docs = _npcl()
    with pytest.raises(ValueError, match="not supplied"):
        fill_narrative(binding, wb, {k: v for k, v in docs.items() if "Form-1" not in k})
    bad = {**binding, "tables": [{**binding["tables"][0], "title": "Table 999: no such table"}]}
    with pytest.raises(ValueError, match="0 tables titled"):
        fill_narrative(bad, wb, docs)
