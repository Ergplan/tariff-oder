"""Courier: for each order of the manifest, the order row, every page's text and whether the page
has a text layer.  Downloading reuses ``arrdb.scrape.download`` (same cache naming: <sha256>.pdf).

A page has a text layer when PyMuPDF finds 15 or more words on it (the threshold arrdb.reader
uses for ``pages_without_text``).  Page text is stored as PyMuPDF's plain ``page.get_text()``.
"""

from __future__ import annotations

from typing import Any

import pymupdf

from . import config, manifest, store
from .ingest import Sink
from .runs import Run

VERSION = "courier 1"
MIN_WORDS = 15


def order_row(o: dict[str, Any], **extra: Any) -> dict[str, Any]:
    row = {
        "commission": o["commission"],
        "title": o["title"],
        "url": o["url"],
        "sha256": o.get("sha256"),
        "bytes": o.get("bytes"),
        "arr_year": o.get("arr_year"),
        "years_decided": list(o.get("years") or []),
        "kind": str(o["kind"]) if o.get("kind") else None,
        "utility_kind": "discom",
        "found_by": o.get("found_by"),
        "fetched_on": o.get("fetched_on"),
        "read_status": "downloaded" if o.get("sha256") else "listed",
        "utilities": list(o.get("licensees") or []),
    }
    row.update(extra)
    return {k: v for k, v in row.items() if v is not None}


def clean(text: str) -> str:
    return text.replace("\x00", "")  # Postgres text cannot hold NUL


def read_pages(path: str) -> list[dict[str, Any]]:
    doc = pymupdf.open(path)
    out = []
    for i, pg in enumerate(doc):
        words = len(pg.get_text("words"))
        out.append({"page": i + 1, "text": clean(pg.get_text()), "has_text_layer": words >= MIN_WORDS})
    return out


def fetch(o: dict[str, Any]) -> dict[str, Any] | None:
    """Download an order that is not in the cache yet (arrdb.scrape.download)."""
    d = config.pdf_dir()
    if d is None:
        return None
    from arrdb.scrape import download

    d.mkdir(parents=True, exist_ok=True)
    m = download(o, d)
    if m.get("sha256"):
        o.update({k: m.get(k) for k in ("sha256", "bytes", "fetched_on")})
    return m


def run(orders: list[dict[str, Any]], sink: Sink, *, download: bool = False) -> dict[str, Any]:
    orders, dups = manifest.unique_files(orders)
    stats = {"orders": 0, "pages": 0, "pages_without_text": 0, "not_downloaded": 0, "duplicates": len(dups)}
    for o in orders:
        r = Run("courier", VERSION, order_url=o["url"])
        path = manifest.pdf_path(o)
        if path is None and download:
            fetch(o)
            path = manifest.pdf_path(o)
        if path is None:
            sink.post("orders", [order_row(o, read_status="listed")])
            stats["not_downloaded"] += 1
            r.post(sink, "skipped", "file not in the cache", rows_written=1)
            continue
        try:
            pages = read_pages(str(path))
        except Exception as e:  # a damaged file is reported, not fatal
            sink.post("orders", [order_row(o, read_status="unreadable")])
            r.post(sink, "failed", f"could not open: {type(e).__name__}: {e}"[:300])
            continue
        no_text = sum(1 for p in pages if not p["has_text_layer"])
        row = order_row(
            o,
            bytes=o.get("bytes") or path.stat().st_size,
            pages=len(pages),
            pages_without_text=no_text,
            read_status="no_text_layer" if no_text > 0.5 * len(pages) else "downloaded",
        )
        store.write(o["sha256"], "pages", {"order": row, "pages": pages})
        res_o = sink.post("orders", [row])
        res_p = sink.post("pages", [{"order_url": o["url"], **p} for p in pages])
        stats["orders"] += 1
        stats["pages"] += len(pages)
        stats["pages_without_text"] += no_text
        r.post(
            sink,
            "ok" if not res_p.rejected else "partial",
            f"{len(pages)} pages, {no_text} without a text layer",
            rows_written=res_o.written + res_p.written,
            rows_rejected=len(res_o.rejected) + len(res_p.rejected),
        )
    return stats
