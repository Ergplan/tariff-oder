"""Replay a dry-run directory into a live ingest API.

A dry run writes every batch the agents would have posted to <dir>/<kind>.jsonl, appending
across runs.  This sends them to INGEST_URL in dependency order, de-duplicated by each
kind's natural key (the last row written wins, as an upsert would), so a database can be
loaded from a run that was made before the application existed.

    INGEST_URL=https://... INGEST_TOKEN=... python -I -m arrnet.replay DIR [--kinds a,b] [--skip c,d]

Nothing is computed here: rows go out exactly as the agents wrote them.  A row the API
refuses is reported with the API's reason.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .ingest import HttpSink

ORDER = [
    "states", "commissions", "utilities", "heads", "parameter_defs", "orders", "pages", "parses",
    "parsed_tables", "arr_values", "parameters", "facts", "paragraphs", "chunks", "gold_figures",
    "metrics", "findings", "agent_runs", "work_items", "briefs",
]  # fmt: skip

# rows of these kinds are a set per key: later rows replace earlier ones
KEYS: dict[str, tuple[str, ...]] = {
    "states": ("code",),
    "commissions": ("code",),
    "utilities": ("code",),
    "heads": ("code",),
    "parameter_defs": ("code",),
    "orders": ("url",),
    "pages": ("order_url", "page"),
    "parses": ("order_url", "reader", "reader_version"),
    "facts": ("order_url", "utility", "fiscal_year", "voice", "head", "label", "page"),
    "paragraphs": ("order_url", "page", "seq"),
    "chunks": ("order_url", "page", "paragraph_seq"),
    "gold_figures": ("order_sha256", "source", "key"),
    "metrics": ("measured_on", "name", "scope"),
    "work_items": ("kind", "target"),
}
# rows of these kinds belong to a parse and are replaced as a whole: keep the last run's rows
PER_PARSE = {"parsed_tables", "arr_values", "parameters"}


def load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]


def dedupe(kind: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if kind in KEYS:
        last: dict[tuple, dict[str, Any]] = {}
        for r in rows:
            last[tuple(r.get(k) for k in KEYS[kind])] = r
        out = list(last.values())
        if kind == "facts":
            # one replace_order marker per order, on its first fact
            seen: set[str] = set()
            for r in out:
                r.pop("replace_order", None)
                if r["order_url"] not in seen:
                    seen.add(r["order_url"])
                    r["replace_order"] = True
        return out
    if kind in PER_PARSE:
        # a parse's rows from the last run that posted it, starting at its replace marker
        by_parse: dict[tuple, list[dict[str, Any]]] = {}
        for r in rows:
            key = (r["order_url"], r["reader"], r["reader_version"])
            if r.get("replace") or key not in by_parse:
                by_parse[key] = []
            by_parse[key].append(r)
        out = []
        for rs in by_parse.values():
            for i, r in enumerate(rs):
                r.pop("replace", None)
                if i == 0:
                    r["replace"] = True
                out.append(r)
        return out
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--kinds", help="only these kinds, comma-separated")
    ap.add_argument("--skip", help="leave out these kinds, comma-separated")
    ap.add_argument("--max-rows", type=int, default=250, help="rows per request (each row is its own savepoint)")
    ap.add_argument("--all-paragraphs", action="store_true", help="send every paragraph, not only those chunks use")
    a = ap.parse_args()
    d = Path(a.dir)
    only = set(a.kinds.split(",")) if a.kinds else None
    skip = set(a.skip.split(",")) if a.skip else set()
    sink = HttpSink(max_rows=a.max_rows)
    # paragraphs are kept only where a chunk points at them: the rest are unclassified plain text
    # (no LLM classified them) and their words are already in the chunks
    wanted: set[tuple] | None = None
    if (d / "chunks.jsonl").exists() and not a.all_paragraphs:
        wanted = {(r["order_url"], r["page"], r.get("paragraph_seq")) for r in load(d / "chunks.jsonl")}
    print("health:", sink.health())
    for kind in ORDER:
        if (only and kind not in only) or kind in skip:
            continue
        p = d / f"{kind}.jsonl"
        if not p.exists():
            continue
        rows = dedupe(kind, load(p))
        if kind == "paragraphs" and wanted is not None:
            rows = [
                r for r in rows if (r["order_url"], r["page"], r["seq"]) in wanted or r.get("kind", "text") != "text"
            ]
        if not rows:
            continue
        res = sink.post(kind, rows)
        print(f"{kind}: {len(rows)} rows, {res.written} written, {len(res.rejected)} rejected", flush=True)
        for r in res.rejected[:5]:
            print("   rejected:", str(r)[:300])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
