"""ARR 101's UPERC checks (apps/arr-101/uperc.js): every check cites a regulation number and a page
of the UPERC MYT Distribution Regulations, 2025 and carries a short verbatim quote.  Each quote must
be on its page of the regulation's text, and the regulation number must be printed there too — no
check rests on words the regulation does not print.  Every step of the guide has checks."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "packages" / "regulations" / "uperc" / "myt-distribution-2025-english.pdf"
APP = ROOT / "apps" / "arr-101"


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace("’", "'").replace("‘", "'")).strip()


def test_every_uperc_quote_is_on_its_page():
    pymupdf = pytest.importorskip("pymupdf")
    pages = [_norm(p.get_text()) for p in pymupdf.open(PDF)]
    src = (APP / "uperc.js").read_text()
    cites = re.findall(r'reg: "([\d.]+)", page: (\d+), quote: "((?:[^"\\]|\\.)*)"', src)
    assert len(cites) >= 40 and len(cites) == src.count("reg: ")
    for reg, page, quote in cites:
        text = pages[int(page) - 1]
        assert _norm(quote) in text, (reg, page, quote)
        # the page prints its own number, and the regulation's number (or its clause's) is on it or the page before
        assert re.search(rf"\b{int(page)}\b", text[:80]), page
        near = pages[int(page) - 2] + " " + text
        assert re.search(rf"(?<![\d.]){re.escape(reg)}(?![\d.])", near) or re.search(
            rf"(?<![\d.]){re.escape(reg.split('.')[0])}(?![\d.])", near
        ), (reg, page)


def test_every_step_has_uperc_checks():
    steps = re.findall(r'^    id: "(\w+)",', (APP / "steps.js").read_text(), re.M)
    src = (APP / "uperc.js").read_text()
    assert len(steps) == 10
    for s in steps:
        block = re.search(rf"^  {s}: \[(.*?)^  \],", src, re.M | re.S)
        assert block and block.group(1).count("reg: ") >= 3, s


def test_formats_evidence_matches_the_round_trip_experiment():
    """apps/arr-101/formats.js (scripts/arr101_formats.py): all 74 formats of the petition's index and the one
    working sheet, each placed in a step of the guide; the recomputed / reproduced totals are the round-trip
    experiment's own (fill-roundtrip.json), and no figure of the petition is in the file — only counts."""
    import json

    src = (APP / "formats.js").read_text()
    doc = json.loads(src[src.index("{") : src.rindex("}") + 1])
    steps = set(re.findall(r'^    id: "(\w+)",', (APP / "steps.js").read_text(), re.M))
    fs = doc["formats"]
    assert doc["totals"]["formats"] == 74 and len(fs) == 75
    assert {f["step"] for f in fs} == steps
    trip = json.loads(
        (PDF.parents[2] / "reference-filings" / "uperc-npcl-fy2026-27" / "fill-roundtrip.json").read_text()
    )
    run = trip["runs"]["none_kept"]
    assert sum(f["checked"] for f in fs) == run["targets"] == doc["totals"]["checked"]
    assert sum(f["agree"] for f in fs) == run["reproduced"] == doc["totals"]["agree"]
    assert all(f["purpose"] and 0 <= f["agree"] <= f["checked"] for f in fs)
    allowed = {"code", "title", "step", "purpose", "status", "why", "entered", "computed", "checked", "agree"}
    assert all(set(f) == allowed | {"sameSheetAs", "computes"} for f in fs)
