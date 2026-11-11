"""Reader: Docling — layout and table structure from the page image, and OCR for pages without a
text layer.  CPU only, no key.

Docling is slow on CPU (about 10 s a page here), so only the pages that matter are converted:
the pages where the text-layer reader found ARR tables, one page either side, and the pages
without a text layer, capped per order (``max_pages``).  When the text-layer reader found no
table, pages whose text names an ARR table title are taken instead.  The selected pages are
copied into a temporary PDF that Docling converts in one pass; its page numbers are mapped back.

Cells are interpreted by :mod:`arrnet.readers.interpret` — arrdb's title filter, column meaning,
heads and number parsing — so the two readers differ in how they find cells, not in how they read
them.  Every value keeps its page and a quote (the row's cell texts joined).
"""

from __future__ import annotations

import importlib.metadata as md
import re
import tempfile
import time
from pathlib import Path
from typing import Any

import pymupdf

from .. import store
from ..arrdb_bridge import TITLE, stage_of
from ..reference import aliases as all_aliases
from ..reference import reader_kind
from .base import ParseResult, Reader
from .interpret import grid_to_table, tables_to_rows, title_ok

TITLE_LINE = re.compile(r"^\s*table\b.{0,200}$", re.I | re.M)


def docling_version() -> str | None:
    try:
        return md.version("docling")
    except md.PackageNotFoundError:
        return None


def select_pages(
    order: dict[str, Any],
    n_pages: int,
    max_pages: int,
    licensees: list[str],
    aliases: dict[str, list[str]],
    max_ocr_pages: int | None = None,
    neighbours: int = 1,
    kind: str = "discom",
) -> tuple[list[int], dict[str, Any]]:
    """The pages to convert and why: text-layer pages (ARR table pages first, then ``neighbours``
    pages either side) up to ``max_pages``, and pages without a text layer up to ``max_ocr_pages``."""
    sha = order.get("sha256") or ""
    tl = store.read(sha, "textlayer") or {}
    pages_doc = store.read(sha, "pages") or {}
    no_text = [p["page"] for p in pages_doc.get("pages", []) if not p["has_text_layer"]]
    table_pages = sorted({p for t in tl.get("tables", []) for p in t.get("pages", [t["page"]])})
    why = f"text-layer table pages ±{neighbours}"
    if not table_pages:
        why = "pages whose text names an ARR table title"
        for p in pages_doc.get("pages", []):
            if any(title_ok(m.group(0).strip(), licensees, aliases, kind) for m in TITLE_LINE.finditer(p["text"])):
                table_pages.append(p["page"])
    chosen: list[int] = []
    skip = set(no_text)

    def add(p: int) -> None:
        if 1 <= p <= n_pages and p not in chosen and p not in skip:
            chosen.append(p)

    for p in table_pages:
        add(p)
    for d in range(1, neighbours + 1):
        for p in table_pages:
            add(p - d)
            add(p + d)
    max_ocr = max_pages if max_ocr_pages is None else max_ocr_pages
    capped = len(chosen) > max_pages or len(no_text) > max_ocr
    ocr = sorted(no_text[:max_ocr])
    return sorted(chosen[:max_pages]) + ocr, {
        "why": why,
        "table_pages": len(table_pages),
        "pages_without_text": len(no_text),
        "ocr_pages": ocr,
        "capped": capped,
    }


_CONVERTERS: dict[bool, Any] = {}


def converter(ocr: bool):
    if ocr not in _CONVERTERS:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        opts = PdfPipelineOptions()
        opts.do_ocr = ocr
        opts.do_table_structure = True
        _CONVERTERS[ocr] = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
    return _CONVERTERS[ocr]


def table_grid(tb: Any) -> tuple[list[list[str]], int]:
    """(grid, header rows) from a Docling TableItem.  A header cell spanning several columns is
    repeated over each (a licensee or a year over its columns); a body cell is kept once."""
    data = tb.data
    nr, nc = data.num_rows, data.num_cols
    grid = [[""] * nc for _ in range(nr)]
    header_rows: set[int] = set()
    for c in data.table_cells:
        r0, r1 = c.start_row_offset_idx, c.end_row_offset_idx
        c0, c1 = c.start_col_offset_idx, c.end_col_offset_idx
        if c.column_header:
            header_rows.update(range(r0, r1))
            for r in range(r0, min(r1, nr)):
                for k in range(c0, min(c1, nc)):
                    grid[r][k] = c.text
        elif 0 <= r0 < nr and 0 <= c0 < nc:
            grid[r0][c0] = c.text
    n_head = 0
    while n_head in header_rows:
        n_head += 1
    return grid, n_head


class DoclingReader(Reader):
    name = "docling"

    def __init__(self, max_pages: int = 24, max_ocr_pages: int = 6) -> None:
        self.max_pages, self.max_ocr_pages = max_pages, max_ocr_pages
        v = docling_version()
        self.version = f"docling {v}" if v else "docling (not installed)"

    def read(self, order: dict[str, Any], pdf_path: str | Path | None) -> ParseResult:
        if docling_version() is None:
            return self.skipped("docling is not installed (uv pip install -e 'tools/arrnet[docling]')")
        if not pdf_path:
            return self.skipped("the order's file is not in the cache")
        t0 = time.monotonic()
        lic = list(order.get("licensees") or [])
        al = all_aliases()
        aliases = {k: al.get(k, []) for k in lic}
        src = pymupdf.open(str(pdf_path))
        kind = reader_kind(order)
        pages, why = select_pages(order, len(src), self.max_pages, lic, aliases, self.max_ocr_pages, kind=kind)
        if not pages:
            return ParseResult(self.name, self.version, "ok", note="no page to convert: no ARR table title found", extra=why)
        ocr_pages = set(why["ocr_pages"])
        raw: list[dict[str, Any]] = []  # candidate tables before the title filter
        page_texts: dict[str, str] = {}
        status = "ok"
        # two passes: pages with a text layer without OCR (fast), pages without one with OCR
        for ocr, group in ((False, [p for p in pages if p not in ocr_pages]), (True, sorted(ocr_pages))):
            if not group:
                continue
            try:
                doc, ok = self._convert(src, group, ocr)
            except Exception as e:
                return ParseResult(self.name, self.version, "failed", note=f"{type(e).__name__}: {e}"[:300], pages=pages)
            if not ok:
                status = "partial"
            self._collect(doc, group, raw)
            if ocr:
                for i, p in enumerate(group):
                    page_texts[str(p)] = doc.export_to_markdown(page_no=i + 1)
        tables = []
        for r in raw:
            if not r["title"] or not title_ok(r["title"], lic, aliases, kind):
                continue
            t = grid_to_table(
                r["grid"],
                title=r["title"],
                page=r["page"],
                row_pages=r["row_pages"],
                licensees=lic,
                aliases=aliases,
                above=r["above"],
                header_rows=r["header_rows"] or None,
            )
            if t:
                t["unit_from"] = "printed with the table" if t["unit"] else None
                t["cells"] = r["grid"]
                t["markdown"] = r["markdown"]
                tables.append(t)
        trows, vrows = tables_to_rows(tables, order.get("arr_year"), stage_of)
        return ParseResult(
            self.name,
            self.version,
            status,
            pages_parsed=len(pages),
            tables=trows,
            values=vrows,
            page_texts=page_texts,
            pages=pages,
            seconds=time.monotonic() - t0,
            note=(
                f"{len(pages)} pages converted ({why['why']}{', capped' if why['capped'] else ''}; "
                f"{len(ocr_pages)} without a text layer, with OCR); "
                f"{len(raw)} tables found, {len(trows)} ARR tables, {len(vrows)} values"
            ),
            extra={**why, "tables_found": len(raw)},
        )

    def _convert(self, src: Any, group: list[int], ocr: bool) -> tuple[Any, bool]:
        """Convert the given pages (copied into a temporary PDF, in this order) in one pass."""
        sub = pymupdf.open()
        for p in group:
            sub.insert_pdf(src, from_page=p - 1, to_page=p - 1)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pages.pdf"
            sub.save(str(path))
            res = converter(ocr).convert(str(path), raises_on_error=False)
        return res.document, str(res.status).endswith("SUCCESS")

    @staticmethod
    def _collect(doc: Any, group: list[int], raw: list[dict[str, Any]]) -> None:
        """Tables of a converted document, in reading order, with their titles (the caption, or
        the nearest 'Table ...' text above on the page) and the text above them.  A table at the
        top of the page after a table, without a title and with as many columns, continues it."""
        from docling_core.types.doc import TableItem

        real_page = {i + 1: p for i, p in enumerate(group)}
        recent: dict[int, list[str]] = {}
        for item, _lvl in doc.iterate_items():
            prov = getattr(item, "prov", None)
            if not prov:
                continue
            pg = real_page.get(prov[0].page_no)
            if pg is None:
                continue
            if not isinstance(item, TableItem):
                text = getattr(item, "text", "") or ""
                if text.strip():
                    recent.setdefault(pg, []).append(re.sub(r"\s+", " ", text).strip())
                continue
            grid, n_head = table_grid(item)
            if not grid:
                continue
            cap = item.caption_text(doc) if hasattr(item, "caption_text") else ""
            before = recent.get(pg, [])
            title = cap.strip() if cap and TITLE.match(cap.strip()) else ""
            if not title:
                title = next((t for t in reversed(before[-4:]) if TITLE.match(t)), "")
            if (
                not title
                and raw
                and raw[-1]["last_page"] == pg - 1
                and not any(TITLE.match(t) for t in before)
                and len(grid[0]) == raw[-1]["width"]
            ):
                prev = raw[-1]
                body = grid[n_head:]
                prev["grid"].extend(body)
                prev["row_pages"].extend([pg] * len(body))
                prev["last_page"] = pg
                prev["markdown"] += "\n\n" + item.export_to_markdown(doc=doc)
                continue
            raw.append(
                {
                    "title": title,
                    "page": pg,
                    "last_page": pg,
                    "grid": grid,
                    "row_pages": [pg] * len(grid),
                    "header_rows": n_head,
                    "width": len(grid[0]),
                    "above": " ".join(before[-3:]),
                    "markdown": item.export_to_markdown(doc=doc),
                }
            )
