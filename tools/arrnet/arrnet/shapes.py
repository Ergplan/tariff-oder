"""The row shapes of docs/arr-network/INGEST.md, checked on the client side.

The application validates every row; this copy lets the dry-run sink reject what the API would
reject (unknown fields, a missing page or quote, a review field) so that a pipeline run without
the application is still an honest rehearsal.  The API stays the authority.
"""

from __future__ import annotations

import math
from typing import Any

# kind -> (required fields, optional fields)
SHAPES: dict[str, tuple[set[str], set[str]]] = {
    "states": ({"code", "name", "kind"}, set()),
    "commissions": ({"code", "name", "states"}, {"website", "website_reachable", "checked_on"}),
    "utilities": ({"code", "name", "kind", "commission", "state", "ownership"}, {"aliases"}),
    "heads": ({"code", "name"}, {"sort"}),
    "parameter_defs": ({"code", "name", "unit", "grp"}, {"sort"}),
    "orders": (
        {"commission", "title", "url", "utilities"},
        {
            "sha256",
            "bytes",
            "pages",
            "pages_without_text",
            "arr_year",
            "years_decided",
            "kind",
            "utility_kind",
            "order_date",
            "found_by",
            "fetched_on",
            "read_status",
        },
    ),
    "pages": ({"order_url", "page", "text", "has_text_layer"}, set()),
    "parses": (
        {"order_url", "reader", "reader_version", "is_real", "status"},
        {"provider", "model", "pages_parsed", "cost_usd", "note"},
    ),
    "parsed_tables": (
        {"order_url", "reader", "reader_version", "page", "columns"},
        {"pages", "title", "unit", "unit_from", "cells", "markdown", "replace"},
    ),
    "arr_values": (
        {"order_url", "reader", "reader_version", "head", "label", "value_printed", "value", "page", "quote"},
        {
            "table_page",
            "table_title",
            "utility",
            "fiscal_year",
            "voice",
            "stage",
            "group_label",
            "unit",
            "value_crore",
            "column_header",
            "year_from",
            "voice_from",
            "is_primary",
            "replace",
        },
    ),
    "parameters": (
        {"order_url", "reader", "reader_version", "code", "label", "value_printed", "value", "unit", "page", "quote"},
        {"utility", "fiscal_year", "voice", "replace"},
    ),
    "facts": (
        {
            "order_url",
            "utility",
            "fiscal_year",
            "voice",
            "head",
            "label",
            "value",
            "page",
            "quote",
            "consensus",
            "readers",
            "readings",
        },
        {"stage", "value_crore", "unit", "is_headline", "headline_why", "set_aside", "replace_order"},
    ),
    "paragraphs": ({"order_url", "page", "seq", "text"}, {"kind", "kind_by", "utility", "topic", "summary"}),
    "chunks": ({"order_url", "page", "text"}, {"paragraph_seq", "embedding", "embedding_model"}),
    "work_items": ({"kind", "target"}, {"priority", "created_by"}),
    "agent_runs": (
        {"agent", "version", "is_real", "started_at", "outcome"},
        {
            "order_url",
            "provider",
            "model",
            "finished_at",
            "rows_written",
            "rows_rejected",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "note",
        },
    ),
    "metrics": ({"measured_on", "name"}, {"scope", "numerator", "denominator", "value", "detail"}),
    "findings": ({"raised_by", "severity", "title", "detail"}, {"order_url"}),
    "briefs": ({"written_by", "is_real", "body"}, {"decisions"}),
    "gold_figures": ({"order_sha256", "key", "source", "page", "value"}, {"voice", "utility", "what"}),
    "section_tables": (
        {"order_url", "section", "seq", "title", "page", "pages", "columns", "rows", "reader_version", "is_real"},
        {"kind", "label", "category", "fiscal_year", "replace_order"},
    ),
}

REVIEW_FIELDS = {"reviewed_by", "reviewed_at", "review_note"}
VOICES = {"claimed", "approved", "approved_earlier", "actual"}
STAGES = {"ARR", "APR", "True-up", "MYT projection"}
CONSENSUS = {"single", "agreed_2", "agreed_3", "conflict"}
READERS = {"textlayer", "docling", "llamaparse", "llm"}
PARSE_STATUS = {"ok", "partial", "failed", "skipped"}
PARAGRAPH_KINDS = {"text", "ruling", "directive", "reasoning", "submission", "heading"}
READ_STATUS = {"listed", "downloaded", "read", "no_tables_found", "no_text_layer", "unreadable"}


def check(kind: str, row: dict[str, Any]) -> str | None:
    """The reason the row would be refused, or None."""
    if kind not in SHAPES:
        return f"unknown kind {kind}"
    req, opt = SHAPES[kind]
    keys = set(row)
    if keys & REVIEW_FIELDS:
        return "review fields are written by people only"
    missing = req - {k for k in keys if row[k] is not None}
    if missing:
        return f"missing {sorted(missing)}"
    extra = keys - req - opt
    if extra:
        return f"unknown fields {sorted(extra)}"
    if kind in ("arr_values", "parameters", "facts"):
        if not isinstance(row["page"], int) or row["page"] < 1:
            return "page must be >= 1"
        if not str(row["quote"]).strip():
            return "quote is empty"
        v = row["value"]
        if not isinstance(v, int | float) or not math.isfinite(v):
            return "value is not a finite number"
    if row.get("voice") is not None and kind in ("arr_values", "parameters", "facts") and row["voice"] not in VOICES:
        return f"voice {row['voice']!r} not allowed"
    if row.get("stage") is not None and row["stage"] not in STAGES:
        return f"stage {row['stage']!r} not allowed"
    if kind == "facts":
        if row["consensus"] not in CONSENSUS:
            return f"consensus {row['consensus']!r} not allowed"
        need = {"single": 1, "agreed_2": 2, "agreed_3": 3, "conflict": 2}[row["consensus"]]
        if len(set(row["readers"])) < need:
            return f"consensus {row['consensus']} needs {need} distinct readers"
        differ = any(g.get("agrees") is False for g in row["readings"])
        if (row["consensus"] == "conflict") != differ:
            return "a conflict needs a reading that does not agree, and only a conflict has one"
    if kind in ("parses", "parsed_tables", "arr_values", "parameters") and row["reader"] not in READERS:
        return f"reader {row['reader']!r} not allowed"
    if kind == "parses" and row["status"] not in PARSE_STATUS:
        return f"status {row['status']!r} not allowed"
    if kind == "paragraphs" and row.get("kind") is not None and row["kind"] not in PARAGRAPH_KINDS:
        return f"paragraph kind {row['kind']!r} not allowed"
    if kind == "orders" and row.get("read_status") is not None and row["read_status"] not in READ_STATUS:
        return f"read_status {row['read_status']!r} not allowed"
    if kind == "chunks" and row.get("embedding") is not None and len(row["embedding"]) != 384:
        return "embedding must have 384 numbers"
    return None
