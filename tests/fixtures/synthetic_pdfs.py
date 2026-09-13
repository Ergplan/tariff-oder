"""SYNTHETIC FIXTURES - not real tariff orders.

Generators for small PDFs that reproduce document-level failure modes from Section 6.1 that
Milestone 1 must inventory correctly: image-only pages mixed with born-digital pages, roman
and offset page labels, and rotated pages.  Every page carries the banner
``SYNTHETIC FIXTURE - NOT A TARIFF ORDER`` so no fixture can be mistaken for a source.

Fixtures are generated on demand (deterministic content) rather than committed as binaries.
"""

from __future__ import annotations

import pymupdf

BANNER = "SYNTHETIC FIXTURE - NOT A TARIFF ORDER"


def mixed_text_and_image_pdf() -> bytes:
    """Six pages: 1-2 text with roman labels (i, ii); 3-4 text with decimal labels starting
    at 1 (printed label = index - 2); page 3 rotated 90; pages 5-6 image-only (no text layer)
    with decimal labels 3, 4.

    Failure modes exercised: scanned pages mixed with born-digital pages; printed labels that
    differ from PDF indices and use roman numerals; rotated pages inside a portrait document.
    """
    doc = pymupdf.open()
    for i in range(4):
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 72), BANNER, fontsize=10)
        page.insert_text((72, 120), f"Fixture text page {i + 1}. This page has a text layer.", fontsize=11)
        if i == 2:
            page.set_rotation(90)
    for i in range(2):
        page = doc.new_page(width=595, height=842)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 120), 0)
        pix.clear_with(200 + i * 20)
        page.insert_image(pymupdf.Rect(72, 72, 372, 192), pixmap=pix)
    doc.set_page_labels(
        [
            {"startpage": 0, "prefix": "", "style": "r", "firstpagenum": 1},
            {"startpage": 2, "prefix": "", "style": "D", "firstpagenum": 1},
        ]
    )
    doc.set_metadata(
        {"producer": "synthetic-fixture-generator", "creator": "tests/fixtures/synthetic_pdfs.py", "title": BANNER}
    )
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def text_only_pdf(pages: int = 3, seed: str = "A") -> bytes:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), BANNER, fontsize=10)
        page.insert_text((72, 120), f"Variant {seed} page {i + 1}", fontsize=11)
    doc.set_metadata({"producer": "synthetic-fixture-generator", "title": BANNER})
    data = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return data


def not_a_pdf() -> bytes:
    return b"%PDF-1.7\nthis is not really a pdf body\n"


def plain_text_bytes() -> bytes:
    return b"hello, this is not a pdf at all"


if __name__ == "__main__":
    import sys
    from pathlib import Path

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/generated")
    out.mkdir(parents=True, exist_ok=True)
    (out / "SYNTHETIC_mixed_text_and_image.pdf").write_bytes(mixed_text_and_image_pdf())
    (out / "SYNTHETIC_text_only.pdf").write_bytes(text_only_pdf())
    print(f"wrote synthetic fixtures to {out}")
