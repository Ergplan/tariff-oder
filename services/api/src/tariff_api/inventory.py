"""Per-page text-layer inventory (Milestone 1).

Observations only: page count, PDF page-label entries, rotation, size, text-layer presence,
image and drawing counts, font embedding.  No classification (Milestone 2) and no numbers are
derived here.  The tool and its version are recorded on every artefact this produces.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pymupdf

TOOL_NAME = "pymupdf"
TOOL_VERSION = pymupdf.__version__ if hasattr(pymupdf, "__version__") else pymupdf.VersionBind


class NotAPdf(Exception):
    pass


@dataclass
class PageInventory:
    page_index: int  # 1-based
    printed_label: str | None
    width_pt: float
    height_pt: float
    rotation: int
    text_chars: int
    has_text_layer: bool
    image_count: int
    drawing_count: int


@dataclass
class DocumentInventory:
    page_count: int
    pdf_version: str | None
    producer: str | None
    creator: str | None
    is_encrypted: bool
    is_tagged: bool
    fonts_total: int
    fonts_not_embedded: list[str] = field(default_factory=list)
    tool: str = TOOL_NAME
    tool_version: str = str(TOOL_VERSION)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def open_document(data: bytes) -> pymupdf.Document:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as e:  # noqa: BLE001
        raise NotAPdf(str(e)) from e
    if not doc.is_pdf:
        raise NotAPdf("not a PDF container")
    return doc


def document_inventory(doc: pymupdf.Document) -> DocumentInventory:
    meta = doc.metadata or {}
    fonts_total = 0
    not_embedded: set[str] = set()
    for i in range(doc.page_count):
        try:
            fonts = doc.get_page_fonts(i, full=False)
        except Exception:  # noqa: BLE001 - a damaged page's fonts are simply unknown
            continue
        for f in fonts:
            fonts_total += 1
            # tuple: (xref, ext, type, basefont, name, encoding); ext == "n/a" => not embedded
            ext = f[1] if len(f) > 1 else ""
            basefont = f[3] if len(f) > 3 else ""
            if ext == "n/a" and basefont:
                not_embedded.add(str(basefont))
    is_tagged = False
    try:
        cat = doc.pdf_catalog()
        mark = doc.xref_get_key(cat, "MarkInfo")
        is_tagged = bool(mark and mark[0] == "dict" and "/Marked true" in mark[1])
    except Exception:  # noqa: BLE001
        is_tagged = False
    return DocumentInventory(
        page_count=doc.page_count,
        pdf_version=(meta.get("format") or None),
        producer=(meta.get("producer") or None),
        creator=(meta.get("creator") or None),
        is_encrypted=bool(doc.is_encrypted),
        is_tagged=is_tagged,
        fonts_total=fonts_total,
        fonts_not_embedded=sorted(not_embedded)[:200],
    )


def page_inventory(doc: pymupdf.Document, page_index0: int) -> PageInventory:
    page = doc[page_index0]
    text = page.get_text("text") or ""
    chars = len("".join(text.split()))
    try:
        label = page.get_label() or None
    except Exception:  # noqa: BLE001
        label = None
    try:
        images = len(page.get_images(full=True))
    except Exception:  # noqa: BLE001
        images = 0
    try:
        drawings = len(page.get_cdrawings())
    except Exception:  # noqa: BLE001
        drawings = 0
    rect = page.rect
    return PageInventory(
        page_index=page_index0 + 1,
        printed_label=label,
        width_pt=float(rect.width),
        height_pt=float(rect.height),
        rotation=int(page.rotation),
        text_chars=chars,
        has_text_layer=chars > 0,
        image_count=images,
        drawing_count=drawings,
    )
