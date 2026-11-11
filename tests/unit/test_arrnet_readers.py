"""ARR Network readers: the shared interpretation of cell grids (Docling, LlamaParse), Docling's
table structure, and the text-layer reader against arrdb on a synthetic page."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("arrnet")
import pymupdf  # noqa: E402

from arrnet.arrdb_bridge import stage_of  # noqa: E402
from arrnet.readers import interpret  # noqa: E402

GRID = [
    ["S. No", "Particulars", "Claimed by UPCL FY 2026-27", "Approved by the Commission FY 2026-27"],
    ["1", "Power Purchase Cost", "5,684.75", "5,678.19"],
    ["2", "O&M Expenses", "3,470.68", "3,468.46"],
    ["3", "Interest on Working Capital", "40.00", "(12.50)"],
    ["4", "Depreciation", "300.10", "-"],
    ["", "Net ARR", "9,495.53", "9,434.15"],
]


def test_grid_is_read_with_arrdb_meaning():
    t = interpret.grid_to_table(GRID, title="Table 4.52: ARR for FY 2026-27 (Rs. Crore)", page=7, row_pages=None,
                                licensees=["UPCL"], aliases={})
    assert t and t["unit"] == "crore"
    cols = {c["index"]: c for c in t["columns"]}
    assert [cols[i]["voice"] for i in sorted(cols)] == ["claimed", "approved"]
    assert all(c["licensee"] == "UPCL" and c["fiscal_year"] == "FY2026-27" for c in cols.values())
    _, vals = interpret.tables_to_rows([t], "FY2026-27", stage_of)
    by = {(v["label"], v["voice"]): v for v in vals}
    assert by[("Power Purchase Cost", "approved")]["value"] == 5678.19
    assert by[("Interest on Working Capital", "approved")]["value"] == -12.5
    assert by[("Net ARR", "approved")]["head"] == "net_arr"
    assert ("Depreciation", "approved") not in by  # a dash is not a value
    assert all(v["page"] == 7 and v["quote"] and v["stage"] == "ARR" for v in vals)
    assert by[("O&M Expenses", "claimed")]["quote"] == "2 O&M Expenses 3,470.68 3,468.46"


def test_title_filter_is_arrdbs():
    assert interpret.title_ok("Table 12: Aggregate Revenue Requirement approved for FY 2026-27", ["UPCL"], {})
    assert not interpret.title_ok("Table 13: Power purchase cost approved", ["UPCL"], {})
    assert not interpret.title_ok("Table 14: ARR of the Wires business", ["UPCL"], {})
    assert not interpret.title_ok("Table 15: ARR of the generating company UJVN", ["UPCL"], {})


def test_markdown_tables_are_found_and_separators_dropped():
    md = "Table 4: ARR (Rs crore)\n\n| Particulars | Approved |\n|---|---|\n| O&M | 12.50 |\n\ntext"
    (start, grid), = interpret.markdown_tables(md)
    assert start == 2 and grid == [["Particulars", "Approved"], ["O&M", "12.50"]]


def test_docling_table_grid_repeats_spanning_header_cells():
    from arrnet.readers.docling_reader import table_grid

    def cell(r, c, text, header=False, cspan=1):
        return SimpleNamespace(start_row_offset_idx=r, end_row_offset_idx=r + 1, start_col_offset_idx=c,
                               end_col_offset_idx=c + cspan, text=text, column_header=header)

    cells = [cell(0, 0, "Particulars", True), cell(0, 1, "NBPDCL", True, 2), cell(1, 1, "Claimed", True),
             cell(1, 2, "Approved", True), cell(2, 0, "O&M"), cell(2, 1, "10.5"), cell(2, 2, "9.5")]
    tb = SimpleNamespace(data=SimpleNamespace(num_rows=3, num_cols=3, table_cells=cells))
    grid, n_head = table_grid(tb)
    assert n_head == 2 and grid[0] == ["Particulars", "NBPDCL", "NBPDCL"] and grid[2] == ["O&M", "10.5", "9.5"]


def test_textlayer_reader_emits_what_arrdb_build_stores(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_arrdb_reader import _page  # the synthetic order page of the arrdb reader's test

    from arrnet.readers.textlayer import TextLayerReader

    pdf = tmp_path / "order.pdf"
    _page(pdf)
    res = TextLayerReader().read({"licensees": ["NBPDCL", "SBPDCL"], "arr_year": "FY2026-27"}, pdf)
    assert res.status == "ok" and res.tables and res.values
    from arrnet.arrdb_bridge import infer_units, read_tables

    raw = read_tables(str(pdf), ["NBPDCL", "SBPDCL"], {})
    infer_units(raw["tables"])
    assert len(res.values) == sum(len(t["lines"]) for t in raw["tables"])
    assert all(v["page"] >= 1 and v["quote"] for v in res.values)
    assert pymupdf.open(str(pdf)).page_count == res.pages_parsed
