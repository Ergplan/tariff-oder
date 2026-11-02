"""Filing checklists as data (R-PKG-1): each requirement quoted from its regulation and checked
against the PDF; evidence looked for in a filing; evidence found is never called compliance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tariff_api.arr.checklist import check_quotes, evaluate, load_checklist

ROOT = Path(__file__).resolve().parents[2]
UPERC = ROOT / "packages" / "filing-checklists" / "uperc" / "myt-2025.json"


def test_every_quote_of_the_uperc_checklist_is_on_its_page_of_the_regulation():
    data = load_checklist(json.loads(UPERC.read_text()))
    assert check_quotes(data, ROOT / data["regulation"]["path"]) == []
    assert all(it["page"] for it in data["items"]) and len(data["items"]) == 17


def test_a_checklist_names_its_regulation_and_every_piece_of_evidence_has_a_reason():
    item = {"id": "x", "clause": "1", "page": 1, "quote": "q", "requirement": "r", "proceedings": ["arr"]}
    with pytest.raises(ValueError, match="SHA-256"):
        load_checklist({"regulation": {}, "items": []})
    reg = {"regulation": {"sha256": "0" * 64}}
    with pytest.raises(ValueError, match="no evidence"):
        load_checklist(reg | {"items": [item | {"evidence": []}]})
    with pytest.raises(ValueError, match="known kind"):
        load_checklist(reg | {"items": [item | {"evidence": [{"kind": "document", "ref": "a"}]}]})
    with pytest.raises(ValueError, match="statement or a mention"):
        load_checklist(reg | {"items": [item | {"evidence": [{"kind": "text", "ref": "a", "why": "w"}]}]})


def _item(i, *evidence):
    return {
        "id": i,
        "clause": "c",
        "page": 1,
        "quote": "q",
        "requirement": "r",
        "proceedings": ["arr"],
        "evidence": list(evidence),
    }


def test_evidence_is_graded_and_a_mention_is_never_evidence_enough():
    E = {"kind": "document", "ref": "Appendix-I", "why": "w"}
    S = {"kind": "sheet", "ref": "ARR", "why": "w"}
    M = {"kind": "text", "ref": "load factor", "why": "w", "weight": "mention"}
    T = {"kind": "text", "ref": r"Verified at \w+ on \d+", "why": "w", "weight": "statement"}
    OUT = {"kind": "outside", "why": "a portal filing"}
    data = {
        "items": [_item("a", S, T), _item("b", S, M), _item("c", M), _item("d", E), _item("e", OUT), _item("f", S, E)]
    }
    docs = [
        {"name": "4. Appendix-II MYT Formats.xlsx", "sha256": "x"},
        {"name": "Appendix-I(b) Board.pdf", "sha256": None},
    ]
    texts = {"form.docx": "Verified at Noida on 14 ... with the load factor projections"}
    got = {i["id"]: i["result"] for i in evaluate(data, docs, ["ARR"], texts)}
    # "Appendix-I" is not "Appendix-II", and a document listed without its bytes is not present
    assert got == {
        "a": "evidenced",
        "b": "partly",
        "c": "mentioned",
        "d": "not_found",
        "e": "outside_package",
        "f": "partly",
    }


def test_npcl_against_the_2025_regulations_filing_requirements():
    """Real data: 17 requirements of Regs. 4–8; the Board's resolution is cited but its copy is not
    among the documents, load factor and the metering status only mentioned, three requirements
    outside what documents can show."""
    rep = json.loads((ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27" / "checklist.json").read_text())
    got = {i["id"]: i["result"] for i in rep["items"]}
    assert got["U25-5.1-board"] == "partly" and got["U25-8.2-sales"] == "partly"
    assert got["U25-8.4a"] == "mentioned"
    assert sorted(k for k, v in got.items() if v == "outside_package") == ["U25-5.1-efiling", "U25-5.2", "U25-5.5"]
    assert list(got.values()).count("evidenced") == 11
