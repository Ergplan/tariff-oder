"""A Word-exported table with a shaded heading row: the fill is a borderless rectangle inset
from the cell border, and read as a ruling it splits every column into three (NPCL page
384, nine columns for three).  The strict reading ignores borderless fills; per table the
strict twin is preferred; both readers then agree on three columns."""

from __future__ import annotations

import pymupdf

from tariff_api import readers


def _shaded_table_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    cols, rows = [60, 250, 420, 560], [100, 140, 175, 210]
    texts = [
        ["Contracted Load", "Fixed Charge", "Energy Charge"],
        ["For supply at 11kV", "Rs. 380.00 / kVA / month", "Rs. 7.70 / kVAh"],
        ["For supply above 11kV", "Rs. 360.00 / kVA / month", "Rs. 7.50/ kVAh"],
    ]
    for r in range(3):
        for c in range(3):
            x0, x1, y0, y1 = cols[c], cols[c + 1], rows[r], rows[r + 1]
            if r == 0:
                page.draw_rect(pymupdf.Rect(x0 + 5, y0 + 2, x1 - 5, y1 - 2), color=None, fill=(0.75, 0.75, 0.75))
            page.draw_rect(pymupdf.Rect(x0, y0, x1, y1), width=0.6)
            page.insert_text((x0 + (13 if r == 0 else 4), y0 + 24), texts[r][c], fontsize=9)
    return doc.tobytes()


def test_plain_ruled_reading_splits_the_columns_and_the_strict_reading_does_not():
    data = _shaded_table_pdf()
    page = pymupdf.open("pdf", data)[0]
    loose = readers.read_tables_pymupdf(page, 1, "lines")
    strict = readers.read_tables_pymupdf(page, 1, "lines_strict")
    assert loose[0].col_count == 9 and strict[0].col_count == 3
    chosen = readers.prefer_strict(loose, strict)
    assert len(chosen) == 1 and chosen[0].strategy == "lines_strict" and chosen[0].ordinal == 0
    assert chosen[0].rows[0] == ["Contracted Load", "Fixed Charge", "Energy Charge"]
    assert chosen[0].rows[1] == ["For supply at 11kV", "Rs. 380.00 / kVA / month", "Rs. 7.70 / kVAh"]
    sec = readers.prefer_strict(
        readers.read_tables_pdfplumber(data, 1, "lines"), readers.read_tables_pdfplumber(data, 1, "lines_strict")
    )
    assert sec[0].col_count == 3 and sec[0].rows[1][1] == "Rs. 380.00 / kVA / month"
    (agreement,) = readers.score_agreement(chosen, sec)
    assert agreement.classification == "high_agreement"


def test_a_table_with_no_strict_twin_keeps_the_plain_reading():
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    # borders drawn as filled thin rectangles only: the strict reading finds nothing
    for x in (60, 250, 420):
        page.draw_rect(pymupdf.Rect(x, 100, x + 0.8, 175), color=None, fill=(0, 0, 0))
    for y in (100, 140, 175):
        page.draw_rect(pymupdf.Rect(60, y, 420.8, y + 0.8), color=None, fill=(0, 0, 0))
    page.insert_text((66, 124), "Slab", fontsize=9)
    page.insert_text((256, 124), "Rate", fontsize=9)
    page.insert_text((66, 164), "0-100", fontsize=9)
    page.insert_text((256, 164), "3.00", fontsize=9)
    pg = pymupdf.open("pdf", doc.tobytes())[0]
    loose = readers.read_tables_pymupdf(pg, 1, "lines")
    assert len(loose) == 1 and loose[0].rows == [["Slab", "Rate"], ["0-100", "3.00"]]
    # when the strict reading has no twin for a table (empty, or elsewhere on the page), the
    # plain reading stands and keeps its ordinal
    chosen = readers.prefer_strict(loose, [])
    assert chosen[0].strategy == "lines" and chosen[0].rows == loose[0].rows and chosen[0].ordinal == 0
    far = readers.TableGrid("pymupdf", "x", 1, 0, "lines_strict", (10.0, 700.0, 100.0, 760.0), [["a"]], 1)
    assert readers.prefer_strict(loose, [far])[0].strategy == "lines"
