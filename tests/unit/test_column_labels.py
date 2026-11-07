"""Column labels for NPCL's formats workbook (increment 154): every fill-map cell's column carries a
year and a voice — read from a header by ``reference.py`` or written by hand in
``column-labels.json`` — and the inputs template keeps as filed exactly the cells that are the
Commission's figures, the tariff rates, and the petitioner's own methods.

Guards: a hand label quotes cells whose text really is in the workbook (no label rests on words
the sheet does not print); every order-quoted column, from either source, has an order word in its
own header (an index off by one would point at the column next door — the slip increment 153 made);
and a label with a row range wins over the column's (the ARR snapshot's column D is the Commission's
approval above row 79 and the petitioner's claim below)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tariff_api.arr import petition

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27"
ORDER_WORDS = re.compile(r"approv|trued|current tariffs", re.I)


@pytest.fixture(scope="module")
def book():
    openpyxl = pytest.importorskip("openpyxl")
    return openpyxl.load_workbook(PKG / "4. Appendix-II MYT Tariff Formats ARR FY 2026-27.xlsx", data_only=True)


@pytest.fixture(scope="module")
def pkg():
    return petition._package(PKG.name)


def _text(v) -> str:
    return re.sub(r"\s+", " ", str(v)).strip()


def test_every_fill_map_cell_has_a_column_label(pkg):
    missing = [c for c in pkg["map"] if petition.label_of(pkg["labels"], c) is None]
    assert missing == [] and len(pkg["map"]) == 4492


def test_hand_labels_quote_what_the_sheet_prints(book):
    labels = json.loads((PKG / "column-labels.json").read_text())["labels"]
    assert len(labels) == 100
    for lab in labels:
        ws = book[lab["sheet"]]
        quotes = re.findall(r"([A-Z]{1,3}\d+): (.*?)(?=; [A-Z]{1,3}\d+: | — |$)", lab["basis"])
        assert quotes, lab
        for ref, text in quotes:
            assert _text(ws[ref].value) == text.strip(), (lab["sheet"], ref, text)


def test_order_quoted_columns_carry_an_order_word_in_their_own_header(book, pkg):
    for lab in pkg["labels"]:
        if not lab["restated"]:
            continue
        ws = book[lab["sheet"]]
        if lab["source"] == "hand":
            assert ORDER_WORDS.search(lab["words"]), lab
            continue
        # the header reader's column, by its own letter: the printed header above the figures
        head = " ".join(_text(ws[f"{lab['column']}{r}"].value) for r in range(1, 11) if ws[f"{lab['column']}{r}"].value)
        assert ORDER_WORDS.search(head), (lab["sheet"], lab["column"], head)


def test_the_template_keeps_the_commissions_figures_the_rates_and_the_petitioners_methods(pkg):
    kept = pkg["kept"]
    by = {
        v: sum(1 for x in kept.values() if x == v)
        for v in (petition.ORDER_FIGURE, petition.TARIFF_RATE, petition.OWN_METHOD)
    }
    assert (by[petition.ORDER_FIGURE], by[petition.TARIFF_RATE], by[petition.OWN_METHOD]) == (182, 504, 31)
    # ARR: the trued-up FY2021-22 column is C ("Trued- Up" at C7), never B (the labels)
    assert kept.get("ARR!C46") == petition.ORDER_FIGURE and "ARR!B46" not in kept
    # the current tariff's rates are the Commission's, entered; the proposed tariff's the petitioner's, entered
    assert kept.get("ESR_3 Curr Tariff FY27!G14") == petition.TARIFF_RATE
    assert kept.get("ESR4_Prop Tariff!G14") == petition.TARIFF_RATE
    # the trued-up billing determinants of FY2022-23 (ESR5's "Previous Year Trued-Up")
    assert sum(1 for c, v in kept.items() if c.startswith("ESR5_BD&Rev!") and v == petition.ORDER_FIGURE) == 48


def test_a_row_range_label_wins_over_the_columns(pkg):
    lab = petition.label_of(pkg["labels"], "ARR snapshot!D90")
    assert lab["voice"] == "petitioned" and not lab["restated"] and lab["rows"] == [79, 200]
    assert "ARR snapshot!D90" not in pkg["kept"]


def test_unprinted_voices_are_left_to_the_reviewer(pkg):
    unprinted = {(lab["sheet"], lab["column"]) for lab in pkg["labels"] if lab["voice"] == "not_printed"}
    assert ("F19_O&M_EE n AG base", "C") in unprinted and ("P7_Trans Failure", "C") in unprinted
    # not guessed into the kept set
    assert not any(
        petition.label_of(pkg["labels"], c)["voice"] == "not_printed" and v != petition.OWN_METHOD
        for c, v in pkg["kept"].items()
    )
