"""The orders the network works on: tools/arrdb/data/orders.json (a list) or a file shaped like
tools/arrdb/known-orders.json ({"orders": [...]}).  Titles, URLs and licensees are what the
commission's website said; nothing here is read from the PDF."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import config
from .arrdb_bridge import arr_year_of


# a manifest's licensee name -> the utility code; None: not a utility (the order is skipped)
LICENSEE_CODES: dict[str, str | None] = {"JSPL": "JSPL-T", "STU": None}
SKIPPED: list[dict[str, Any]] = []


def load(paths: list[str | Path] | None = None) -> list[dict[str, Any]]:
    """Orders of the manifests (default: the DISCOM and the TRANSCO manifests of tools/arrdb).
    A TRANSCO manifest's ``years_text`` becomes ``years``; MERC's pooled State Transmission
    Utility orders are skipped (the STU is not a utility) and listed in ``SKIPPED``."""
    paths = paths or config.default_manifests()
    out: list[dict[str, Any]] = []
    seen_url: set[str] = set()
    SKIPPED.clear()
    for p in paths:
        d = json.loads(Path(p).read_text())
        for o in d["orders"] if isinstance(d, dict) else d:
            if o["url"] in seen_url:
                continue
            seen_url.add(o["url"])
            o = dict(o)
            lic = [LICENSEE_CODES.get(x, x) for x in o.get("licensees") or []]
            if any(x is None for x in lic):
                SKIPPED.append({"url": o["url"], "title": o.get("title"), "why": "licensee is not a utility (STU)"})
                continue
            o["licensees"] = lic
            if not o.get("years") and o.get("years_text"):
                o["years"] = [y.strip() for y in str(o["years_text"]).split(",") if y.strip()]
            o.setdefault("utility_kind", "discom")
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
