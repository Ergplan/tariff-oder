"""The optional Docling reader is an adapter behind the reader interface: its table items
convert to the pipeline's grids without the models, so the adapter logic is tested here and
the model run is measured on a machine that can fetch them (ADR-0009 addendum)."""

from __future__ import annotations

from types import SimpleNamespace

from tariff_api import readers


def _cell(text, r0, r1, c0, c1, header=False):
    return SimpleNamespace(
        text=text,
        start_row_offset_idx=r0,
        end_row_offset_idx=r1,
        start_col_offset_idx=c0,
        end_col_offset_idx=c1,
        column_header=header,
    )


def _table(page, cells, rows, cols, bbox=(60, 700, 400, 640)):
    return SimpleNamespace(
        prov=[
            SimpleNamespace(
                page_no=page,
                bbox=SimpleNamespace(l=bbox[0], t=bbox[1], r=bbox[2], b=bbox[3], coord_origin="BOTTOMLEFT"),
            )
        ],
        data=SimpleNamespace(table_cells=cells, num_rows=rows, num_cols=cols),
    )


def test_docling_tables_become_grids_with_spans_repeated_and_top_left_boxes():
    cells = [
        _cell("Category", 0, 1, 0, 1, header=True),
        _cell("Rs/kWh", 0, 1, 1, 3, header=True),  # spans two columns
        _cell("LMV-2", 1, 2, 0, 1),
        _cell("1.33", 1, 2, 1, 2),
        _cell("1.45", 1, 2, 2, 3),
    ]
    grids = readers.grids_from_docling_tables([_table(6, cells, 2, 3)], "2.128.0", {6: 842.0})
    assert len(grids) == 1
    g = grids[0]
    assert g.reader == "docling" and g.reader_version == "2.128.0" and g.strategy == "model"
    assert g.page_index == 6 and g.ordinal == 0 and g.header_rows == 1
    assert g.rows == [["Category", "Rs/kWh", "Rs/kWh"], ["LMV-2", "1.33", "1.45"]]
    assert g.bbox == (60.0, 842.0 - 700.0, 400.0, 842.0 - 640.0)  # top-left origin like the other readers


def test_two_tables_on_one_page_get_ordinals_and_a_table_without_provenance_is_dropped():
    a = _table(3, [_cell("x", 0, 1, 0, 1)], 1, 1)
    b = _table(3, [_cell("y", 0, 1, 0, 1)], 1, 1)
    orphan = SimpleNamespace(prov=[], data=SimpleNamespace(table_cells=[], num_rows=0, num_cols=0))
    grids = readers.grids_from_docling_tables([a, orphan, b], "2.128.0")
    assert [(g.page_index, g.ordinal, g.rows) for g in grids] == [(3, 0, [["x"]]), (3, 1, [["y"]])]


def test_docling_availability_is_reported_not_assumed():
    ok, why = readers.docling_available()
    assert isinstance(ok, bool) and why
