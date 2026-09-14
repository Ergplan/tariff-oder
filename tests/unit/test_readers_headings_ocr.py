"""Milestone 2b rules as pure functions, then over the fixtures: multi-reader table grids and
agreement classes (Section 6.4), the heading inventory, and OCR parsing/agreement."""

from __future__ import annotations

import shutil

import pymupdf
import pytest

from fixtures.synthetic_pdfs import labelled_order_pdf, readers_and_headings_pdf
from tariff_api import headings as H
from tariff_api import ocr as O
from tariff_api.readers import (
    TableGrid,
    compare_grids,
    normalise_cell,
    read_tables_pdfplumber,
    read_tables_pymupdf,
    score_agreement,
)

# ------------------------------------------------------------------ readers


def _grid(rows, reader="pymupdf", ordinal=0, bbox=(0, 0, 100, 100), header_rows=1, page=1):
    return TableGrid(reader, "x", page, ordinal, "lines", bbox, rows, header_rows)


def test_normalisation_drops_empty_rows_and_columns_but_keeps_text_as_is():
    g = _grid([["  Fixed  Charge ", "", None], ["", "", ""], ["Rs.145/-", "", "580"]])
    n = g.normalised()
    assert n.rows == [["Fixed Charge", ""], ["Rs.145/-", "580"]]  # empty middle column and spacer row dropped
    assert normalise_cell("  6.50 \n/kWh ") == "6.50 /kWh"  # no case folding, no number parsing here


def test_agreement_classes():
    a = _grid([["h1", "h2"], ["1", "2"], ["3", "4"]])
    identical = _grid([["h1", "h2"], ["1", "2"], ["3", "4"]], reader="pdfplumber")
    assert compare_grids(a, identical).classification == "high_agreement"

    one_cell = _grid([["h1", "h2"], ["1", "2"], ["3", "9"]], reader="pdfplumber")
    r = compare_grids(a, one_cell)
    assert r.classification == "minority_cell_disagreement"
    assert r.disagreeing_cells == [{"row": 2, "col": 1, "primary": "4", "secondary": "9"}]
    assert "reader_disagreement" in r.risk_tags

    shape = _grid([["h1", "h2", "h3"], ["1", "2", "3"]], reader="pdfplumber")
    r = compare_grids(a, shape)
    assert r.classification == "structure_disagreement" and not r.structure_match
    assert "structure_disagreement" in r.risk_tags

    mostly_wrong = _grid([["h1", "h2"], ["x", "y"], ["z", "w"]], reader="pdfplumber")
    assert compare_grids(a, mostly_wrong).classification == "structure_disagreement"

    header_only = _grid([["h1", "h2"], ["1", "2"], ["3", "4"]], reader="pdfplumber", header_rows=0)
    r = compare_grids(a, header_only)
    assert r.classification == "minority_cell_disagreement" and not r.header_match


def test_pairing_by_overlap_and_the_silent_empty_table():
    p = [_grid([["a", "b"]], bbox=(0, 0, 100, 50)), _grid([["c"]], ordinal=1, bbox=(0, 200, 100, 250))]
    empty = _grid([["", ""], ["", ""]], reader="pdfplumber", ordinal=0, bbox=(300, 300, 400, 400))
    twin = _grid([["a", "b"]], reader="pdfplumber", ordinal=1, bbox=(0, 0, 100, 52))
    results = score_agreement(p, [empty, twin])
    by = {(r.primary_ordinal, r.secondary_ordinal): r for r in results}
    assert by[(0, 1)].classification == "high_agreement"
    assert by[(1, None)].classification == "secondary_missing"
    silent = by[(None, 0)]
    assert silent.classification == "primary_missing"
    assert "empty_grid" in silent.risk_tags  # failure mode P1: a parser silently returned an empty table


def test_readers_agree_on_ruled_table_and_disagree_on_vector_page():
    data = labelled_order_pdf()
    doc = pymupdf.open(stream=data, filetype="pdf")
    # ruled rate table, page 6
    prim = read_tables_pymupdf(doc[5], 6)
    sec = read_tables_pdfplumber(data, 6)
    assert len(prim) == 1 and len(sec) == 1
    assert prim[0].rows[0] == ["Description", "Fixed Charge", "Energy Charge", "Slab"]
    r = score_agreement(prim, sec)
    assert [x.classification for x in r] == ["high_agreement"]
    assert r[0].cell_equality == 1.0 and r[0].structure_match
    # vector-drawn page 7: pdfplumber returns a 20x6 grid of nothing; pymupdf returns none
    prim = read_tables_pymupdf(doc[6], 7)
    sec = read_tables_pdfplumber(data, 7)
    assert prim == [] and len(sec) == 1 and sec[0].is_empty
    r = score_agreement(prim, sec)
    assert r[0].classification == "primary_missing" and "empty_grid" in r[0].risk_tags


def test_text_strategy_recovers_unruled_table_and_both_readers_agree():
    data = readers_and_headings_pdf()
    doc = pymupdf.open(stream=data, filetype="pdf")
    assert read_tables_pymupdf(doc[0], 1, "lines") == []  # no rulings on the KERC-style page
    prim = read_tables_pymupdf(doc[0], 1, "text")
    sec = read_tables_pdfplumber(data, 1, "text")
    assert len(prim) == 1 and len(sec) == 1
    n = prim[0].normalised()
    # The whitespace strategy sweeps every column-aligned line on the page, so the grid begins
    # at the banner rather than at the table: a known looseness of text-strategy boundaries,
    # recorded rather than hidden.  What matters for routing is that both readers agree.
    assert any("Particulars" in row for row in n.rows) and any("580" in row for row in n.rows)
    assert score_agreement(prim, sec)[0].classification == "high_agreement"


# ------------------------------------------------------------------ headings


@pytest.mark.parametrize(
    ("line", "kind", "canonical"),
    [
        ("RATE SCHEDULE LMV – 1", "rate_schedule", "LMV-1"),
        ("RATE SCHEDULE LMV - 3", "rate_schedule", "LMV-3"),
        ("RATE SCHEDULE LMV1", "rate_schedule", "LMV-1"),
        ("RATE SCHEDULE LMV-4 (A)", "rate_schedule", "LMV-4(A)"),
        ("RATE SCHEDULE LMV - 1 (continued)", "rate_schedule", "LMV-1"),  # v2: a continued page is the same schedule
        ("RATE SCHEDULE LMV-1 (Contd.)", "rate_schedule", "LMV-1"),
        ("RATE SCHEDULE HV-2", "rate_schedule", "HV-2"),
        ("TARIFF SCHEDULE LT-1", "tariff_schedule", "LT-1"),
        ("TARIFF SCHEDULE LT-3(a)", "tariff_schedule", "LT-3(A)"),
        ("TARIFF SCHEDULE HT-2(c)(ii)", "tariff_schedule", "HT-2(C)(II)"),
        ("TARIFF SCHEDULE LT-6(c)/HT", "tariff_schedule", "LT-6(C)/HT"),
        ("1. RATE: RGP", "rate_clause", "RGP"),
        ("11. RATE: HTP-1", "rate_clause", "HTP-1"),
        ("6. RATE: LTP- LIFT IRRIGATION", "rate_clause", "LTP-LIFTIRRIGATION"),
        ("ANNEXURE - I", "annexure", "I"),
        ("ANNEXURE: TARIFF SCHEDULE", "annexure", None),
        ("CHAPTER - 6", "chapter", "6"),
        ("CHAPTER 6: DISTRIBUTION LOSS TRAJECTORY", "chapter", "6"),
        ("Table 6-7 Approved distribution loss trajectory", "table_caption", "6-7"),
        ("Table 6.3A Approved tariff FY2025-26", "table_caption", "6.3A"),
    ],
)
def test_heading_patterns_and_canonical_codes(line, kind, canonical):
    found = H.scan_headings(1, line)
    assert len(found) == 1, found
    assert found[0].kind == kind
    assert found[0].code_canonical == canonical


def test_prose_and_long_lines_are_not_headings():
    text = (
        "The rate schedule for LMV-1 consumers is given in Annexure-I which the Commission approves.\n"
        "as per the tariff schedule applicable to the licensee the rate schedule lmv-1 shall apply to all\n"
        "Chapter 3 the commission shall determine the tariff for supply of electricity ...... 6\n"
        "CHAPTER 4 ........................................................ 12\n"
    )
    assert H.scan_headings(1, text) == []  # contents entries and sentences are not chapter headings


def test_kerc_duplicate_heading_counts_once_and_variants_unify():
    text = "TARIFF SCHEDULE LT-1\nApplicable to...\nTARIFF SCHEDULE LT-1\nParticulars\n"
    found = H.dedupe_consecutive(H.scan_headings(3, text))
    assert [h.code_canonical for h in found] == ["LT-1"]
    variants = H.scan_headings(1, "RATE SCHEDULE LMV – 1") + H.scan_headings(9, "RATE SCHEDULE LMV - 1")
    inv = H.inventory(variants)
    assert inv["counts"] == {"rate_schedule": 2}
    assert inv["unique_codes"] == {"rate_schedule": ["LMV-1"]}
    assert inv["repeated_codes"] == {"rate_schedule": ["LMV-1"]}  # same schedule seen twice: a finding to show


def test_headings_over_the_fixture():
    doc = pymupdf.open(stream=readers_and_headings_pdf(), filetype="pdf")
    found: list[H.Heading] = []
    for i in range(doc.page_count):
        found += H.dedupe_consecutive(H.scan_headings(i + 1, doc[i].get_text("text")))
    assert [(h.page_index, h.kind, h.code_canonical) for h in found] == [
        (1, "tariff_schedule", "LT-1"),
        (2, "rate_clause", "RGP"),
        (3, "rate_schedule", "LMV-1"),
        (5, "chapter", "6"),
        (5, "table_caption", "6-7"),
    ]


# ------------------------------------------------------------------ OCR

SAMPLE_TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "1\t1\t0\t0\t0\t0\t0\t0\t2480\t3508\t-1\t\n"
    "4\t1\t1\t1\t1\t0\t300\t400\t900\t40\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t300\t400\t200\t40\t96.5\tRATE\n"
    "5\t1\t1\t1\t1\t2\t520\t400\t300\t40\t95.0\tSCHEDULE\n"
    "5\t1\t1\t1\t2\t1\t300\t460\t200\t40\t91.0\tLMV-1\n"
    "5\t1\t2\t1\t1\t1\t300\t600\t200\t40\t40.0\tDomestic\n"
    "5\t1\t2\t1\t1\t2\t520\t600\t200\t40\t-1\t\n"
)


def test_tsv_parsing_and_text_assembly():
    words = O.parse_tsv(SAMPLE_TSV)
    assert [w.text for w in words] == ["RATE", "SCHEDULE", "LMV-1", "Domestic"]
    assert words[0].conf == 96.5 and words[0].left == 300
    assert O.assemble_text(words) == "RATE SCHEDULE\nLMV-1\n\nDomestic"


def test_text_agreement_is_token_jaccard():
    assert O.text_agreement("Rate Schedule LMV-1", "RATE SCHEDULE lmv 1") == 1.0
    assert O.text_agreement("xqzvbn ptkrsd", "rate schedule") == 0.0
    assert O.text_agreement("", "") == 1.0
    # {rate, schedule} shared, six distinct tokens in the union
    assert O.text_agreement("rate schedule lmv domestic", "rate schedule hv industrial") == 0.3333


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract binary not installed")
def test_ocr_reads_a_scanned_page_and_reports_nothing_on_vector_strokes():
    doc = pymupdf.open(stream=readers_and_headings_pdf(), filetype="pdf")
    scanned = doc[3]  # page 4 is a raster of page 3
    assert not scanned.get_text("text").strip()
    res = O.ocr_page(scanned, lang="eng", dpi=300, psm=4, min_confidence=60.0)
    assert res.engine == "tesseract" and res.engine_version and res.engine_version != "unknown"
    assert res.word_count > 20 and res.mean_confidence > 60 and not res.low_confidence
    assert "RATE SCHEDULE" in res.text and "Description" in res.text
    # OCR of the scan agrees with the text layer of the page it was rendered from
    assert O.text_agreement(doc[2].get_text("text"), res.text) > 0.8

    vector = pymupdf.open(stream=labelled_order_pdf(), filetype="pdf")[6]
    res = O.ocr_page(vector, lang="eng", dpi=300, psm=4, min_confidence=60.0)
    assert res.word_count == 0 and res.low_confidence  # honestly unreadable, never a guessed table
