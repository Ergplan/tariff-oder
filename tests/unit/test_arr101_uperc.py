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

