"""The orders the network works on: tools/arrdb/data/orders.json (a list) or a file shaped like
tools/arrdb/known-orders.json ({"orders": [...]}).  Titles, URLs and licensees are what the
commission's website said; nothing here is read from the PDF."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .arrdb_bridge import arr_year_of


def load(paths: list[str | Path] | None = None) -> list[dict[str, Any]]:
    paths = paths or [config.default_manifest()]
    out: list[dict[str, Any]] = []
    seen_url: set[str] = set()
    for p in paths:
        d = json.loads(Path(p).read_text())
        for o in d["orders"] if isinstance(d, dict) else d:
            if o["url"] in seen_url:
                continue
            seen_url.add(o["url"])
            o = dict(o)
            o["arr_year"] = arr_year_of(o)
            out.append(o)
    return out


def unique_files(orders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(orders, duplicates): the first order listed for each file; later URLs serving the same
    bytes are reported, not stored twice (the schema keeps one order per SHA-256)."""
    keep, dup = [], []
    seen: set[str] = set()
    for o in orders:
        sha = o.get("sha256")
        if sha and sha in seen:
            dup.append(o)
            continue
        if sha:
            seen.add(sha)
        keep.append(o)
    return keep, dup


def select(
    orders: list[dict[str, Any]], only: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    if only:
        wanted = {x.strip().upper() for x in only.split(",")}
        orders = [o for o in orders if o["commission"].upper() in wanted]
    return orders[:limit] if limit else orders


def pdf_path(o: dict[str, Any]) -> Path | None:
    d = config.pdf_dir()
    sha = o.get("sha256")
    if not d or not sha:
        return None
    p = d / f"{sha}.pdf"
    return p if p.exists() else None
