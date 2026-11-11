"""Reader: text layer — ``arrdb.reader.read_tables`` and arrdb.build's unit inference, emitting
exactly the tables and values arrdb.build stores (same labels, columns, units, value_crore,
stage, year_from / voice_from)."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..arrdb_bridge import infer_units, read_tables, stage_of
from ..reference import aliases as all_aliases
from ..reference import reading_groups
from .base import ParseResult, Reader
from .interpret import tables_to_rows

READER_VERSION = "arrdb-reader 1"  # arrdb.build.READER_VERSION


class TextLayerReader(Reader):
    name = "textlayer"
    version = READER_VERSION

    def read(self, order: dict[str, Any], pdf_path: str | Path | None) -> ParseResult:
        if not pdf_path:
            return self.skipped("the order's file is not in the cache")
        t0 = time.monotonic()
        al = all_aliases()
        tables: list[dict[str, Any]] = []
        seen: set[tuple] = set()
        try:
            for lic, kind in reading_groups(order):
                res = read_tables(str(pdf_path), lic, {k: al.get(k, []) for k in lic}, kind=kind)
                for t in res["tables"]:
                    if (t["page"], t["title"]) not in seen:  # a table both passes keep is read once
                        seen.add((t["page"], t["title"]))
                        tables.append(t)
        except Exception as e:  # a damaged PDF is reported, not fatal
            return ParseResult(self.name, self.version, "failed", note=f"{type(e).__name__}: {e}"[:300])
        infer_units(tables)
        trows, vrows = tables_to_rows(tables, order.get("arr_year"), stage_of)
        status_read = (
            "read" if tables else ("no_text_layer" if res["pages_without_text"] > 0.5 * res["pages"] else "no_tables_found")
        )
        return ParseResult(
            self.name,
            self.version,
            "ok",
            pages_parsed=res["pages"],
            tables=trows,
            values=vrows,
            pages=list(range(1, res["pages"] + 1)),
            seconds=time.monotonic() - t0,
            note=f"{len(trows)} ARR tables, {len(vrows)} values; {res['pages_without_text']} pages without text",
            extra={"read_status": status_read, "pages_without_text": res["pages_without_text"]},
        )
