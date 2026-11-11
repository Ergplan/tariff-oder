"""agent_runs rows: every agent records what it did, real or fixture, with tokens and cost."""

from __future__ import annotations

import time
from typing import Any

from . import store
from .ingest import Sink, now


class Run:
    def __init__(self, agent: str, version: str, *, order_url: str | None = None, is_real: bool = True, **kw: Any):
        self.row: dict[str, Any] = {
            "agent": agent,
            "version": version,
            "order_url": order_url,
            "is_real": is_real,
            "started_at": now(),
            "outcome": "ok",
            "rows_written": 0,
            "rows_rejected": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            **kw,
        }
        self.t0 = time.monotonic()

    def finish(self, outcome: str = "ok", note: str | None = None, **kw: Any) -> dict[str, Any]:
        self.row.update(kw)
        self.row["outcome"] = outcome
        self.row["finished_at"] = now()
        secs = time.monotonic() - self.t0
        self.row["note"] = f"{note + '; ' if note else ''}{secs:.1f} s"
        self.seconds = secs
        return {k: v for k, v in self.row.items() if v is not None}

    def post(self, sink: Sink, outcome: str = "ok", note: str | None = None, **kw: Any) -> dict[str, Any]:
        row = self.finish(outcome, note, **kw)
        sink.post("agent_runs", [row])
        store.append_jsonl("runs", [{**row, "seconds": round(self.seconds, 2), "dry_run": sink.is_dry_run}])
        return row
