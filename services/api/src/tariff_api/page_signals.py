"""Extract the primitives page triage looks at, from a PyMuPDF page.

Kept separate from :mod:`tariff_api.triage` so the classification rules stay pure functions
over :class:`PageSignals` and are testable without a PDF.  Everything here is observation:
counts, areas and positions.  Nothing here decides anything.
"""

from __future__ import annotations

from collections import Counter

import pymupdf

from .triage import PageSignals, assess_text

TOOL_NAME = "pymupdf"
TOOL_VERSION = str(getattr(pymupdf, "__version__", None) or pymupdf.VersionBind)


def extract_signals(page: pymupdf.Page) -> PageSignals:
    text = page.get_text("text") or ""
    chars = len("".join(text.split()))
    lines = _lines_in_order(page)
    quality = assess_text(text, lines) if chars else None

    page_area = max(1.0, float(page.rect.width * page.rect.height))
    image_area = 0.0
    images = page.get_images(full=True)
    for img in images:
        try:
            for rect in page.get_image_rects(img[0]):
                image_area += float(rect.width * rect.height)
        except Exception:  # noqa: BLE001 - an unplaceable image contributes no area
            continue

    drawings = page.get_cdrawings()
    ruling = _ruling_lines(drawings, page.rect)
    columns = _aligned_columns(lines)

    return PageSignals(
        text_chars=chars,
        line_count=len(lines),
        image_count=len(images),
        image_area_ratio=min(1.0, image_area / page_area),
        drawing_count=len(drawings),
        ruling_line_count=ruling,
        aligned_column_count=columns,
        rotation=int(page.rotation),
        text=text,
        quality=quality,
    )


def _lines_in_order(page: pymupdf.Page) -> list[tuple[float, float, str]]:
    """[(y_top, x_left, text)] in extraction order — the order a text-only reader would see."""
    out: list[tuple[float, float, str]] = []
    try:
        d = page.get_text("dict")
    except Exception:  # noqa: BLE001
        return out
    for block in d.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            txt = "".join(s.get("text", "") for s in spans).strip()
            if not txt:
                continue
            x0, y0 = line["bbox"][0], line["bbox"][1]
            out.append((float(y0), float(x0), txt))
    return out


def _ruling_lines(drawings: list[dict], rect: pymupdf.Rect) -> int:
    """Count long, thin horizontal or vertical strokes — table rulings.  Short ticks, glyph
    outlines and logos have neither the length nor the aspect ratio."""
    min_len = 0.15 * min(float(rect.width), float(rect.height))
    count = 0
    for d in drawings:
        r = d.get("rect")
        if not r:
            continue
        x0, y0, x1, y1 = r
        w, h = abs(x1 - x0), abs(y1 - y0)
        if (w >= min_len and h <= 3.0) or (h >= min_len and w <= 3.0):
            count += 1
    return count


def _aligned_columns(lines: list[tuple[float, float, str]], tolerance: float = 2.0) -> int:
    """Distinct x positions at which at least four lines start — the signature of a table
    without rulings, or of a two-column layout.  Rounded to `tolerance` points."""
    if len(lines) < 8:
        return 0
    buckets = Counter(round(x / tolerance) for _, x, _ in lines)
    return sum(1 for _, n in buckets.items() if n >= 4)
