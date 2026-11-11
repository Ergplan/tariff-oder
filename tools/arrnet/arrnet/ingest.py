"""Client for the application's ingest API (docs/arr-network/INGEST.md).

    POST {INGEST_URL}/api/ingest/batch   Authorization: Bearer {INGEST_TOKEN}
    { "kind": "...", "rows": [...] }  ->  { "kind", "written", "rejected": [{index, reason}] }

Rows are sent in batches of at most 1,000 rows and 4 MB (half the API's limits), retried with
backoff on a 5xx or a network error, and every per-row rejection is surfaced to the caller with
its row.  ``DryRunSink`` writes the same batches as JSONL to a directory instead, applying the
client-side shape check of :mod:`arrnet.shapes`, so the pipeline can be run and inspected
without the application.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import shapes

MAX_ROWS = 1000
MAX_BYTES = 4 * 1024 * 1024


class IngestError(RuntimeError):
    pass


@dataclass
class Result:
    kind: str
    written: int = 0
    rejected: list[dict[str, Any]] = field(default_factory=list)  # {index, reason, row}
    batches: int = 0

    def add(self, other: Result) -> None:
        self.written += other.written
        self.rejected.extend(other.rejected)
        self.batches += other.batches


def _encode(row: dict[str, Any]) -> bytes:
    return json.dumps(row, ensure_ascii=False, default=str, allow_nan=False).encode()


def _size(row: dict[str, Any]) -> int:
    return len(json.dumps(row, ensure_ascii=False, default=str).encode())


def batches(rows: list[dict[str, Any]], max_rows: int = MAX_ROWS, max_bytes: int = MAX_BYTES):
    """Split rows into lists of at most max_rows rows and max_bytes of JSON.  A single row larger
    than max_bytes is still sent alone (the API will answer for it)."""
    cur: list[tuple[int, dict[str, Any]]] = []
    size = 0
    overhead = 64
    for i, r in enumerate(rows):
        n = _size(r) + 1
        if cur and (len(cur) >= max_rows or size + n + overhead > max_bytes):
            yield cur
            cur, size = [], 0
        cur.append((i, r))
        size += n
    if cur:
        yield cur


def _strip_review(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        if set(r) & shapes.REVIEW_FIELDS:
            raise IngestError("an agent never sends review fields")  # a bug, not a row to drop
        out.append(r)
    return out


class Sink:
    """Where rows go.  ``post`` returns what was written and what was rejected (with the row)."""

    is_dry_run = False

    def post(self, kind: str, rows: list[dict[str, Any]]) -> Result:
        raise NotImplementedError

    def get(self, path: str) -> Any | None:  # a read endpoint, when the sink has one
        return None


class HttpSink(Sink):
    def __init__(
        self,
        url: str | None = None,
        token: str | None = None,
        *,
        retries: int = 4,
        backoff: float = 1.5,
        timeout: float = 320.0,  # longer than the API's 300 s limit: a retry never overlaps a running batch
        transport: httpx.BaseTransport | None = None,
        max_rows: int = MAX_ROWS,
        max_bytes: int = MAX_BYTES,
        sleep=time.sleep,
    ) -> None:
        self.url = (url or os.environ.get("INGEST_URL") or "").rstrip("/")
        self.token = token or os.environ.get("INGEST_TOKEN") or ""
        if not self.url or not self.token:
            raise IngestError("INGEST_URL and INGEST_TOKEN must be set (or use --dry-run DIR)")
        self.retries, self.backoff, self.sleep = retries, backoff, sleep
        self.max_rows, self.max_bytes = max_rows, max_bytes
        self.client = httpx.Client(
            timeout=timeout, transport=transport, headers={"Authorization": f"Bearer {self.token}"}
        )

    def _send(self, method: str, path: str, body: Any | None = None) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                if method == "POST":
                    r = self.client.post(
                        f"{self.url}{path}",
                        content=json.dumps(body, ensure_ascii=False, default=str, allow_nan=False).encode(),
                        headers={"Content-Type": "application/json"},
                    )
                else:
                    r = self.client.get(f"{self.url}{path}")
            except httpx.TransportError as e:  # network: retry
                last = e
            else:
                if r.status_code < 500:
                    return r
                last = IngestError(f"HTTP {r.status_code}: {r.text[:300]}")
            if attempt < self.retries:
                self.sleep(self.backoff * (2**attempt))
        raise IngestError(f"{method} {path} failed after {self.retries + 1} attempts: {last}")

    def post(self, kind: str, rows: list[dict[str, Any]]) -> Result:
        rows = _strip_review(rows)
        total = Result(kind)
        for b in batches(rows, self.max_rows, self.max_bytes):
            r = self._send("POST", "/api/ingest/batch", {"kind": kind, "rows": [x for _, x in b]})
            if r.status_code == 401:
                raise IngestError("the ingest API refused the token (401)")
            if r.status_code != 200:
                raise IngestError(f"batch of {kind} refused: HTTP {r.status_code}: {r.text[:500]}")
            d = r.json()
            res = Result(kind, int(d.get("written", 0)), batches=1)
            for rej in d.get("rejected") or []:
                i = int(rej.get("index", -1))
                row = b[i][1] if 0 <= i < len(b) else None
                res.rejected.append(
                    {"index": b[i][0] if row is not None else i, "reason": rej.get("reason"), "row": row}
                )
            total.add(res)
        return total

    def get(self, path: str) -> Any | None:
        try:
            r = self._send("GET", path)
        except IngestError:
            return None
        if r.status_code != 200:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    def health(self) -> Any | None:
        return self.get("/api/ingest/health")


class DryRunSink(Sink):
    """Writes every batch to <dir>/<kind>.jsonl (one row per line) and logs each batch to
    <dir>/batches.jsonl.  Rows the API would refuse on shape are rejected here with the reason,
    and also written to <dir>/rejected.jsonl."""

    is_dry_run = True

    def __init__(self, directory: str | Path, known: dict[str, set[str]] | None = None) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.known = known or {}  # heads, parameter_defs, utilities: codes the API would know

    def _reason(self, kind: str, row: dict[str, Any]) -> str | None:
        why = shapes.check(kind, row)
        if why:
            return why
        if kind in ("arr_values", "facts") and "heads" in self.known and row["head"] not in self.known["heads"]:
            return f"unknown head {row['head']}"
        if kind == "parameters" and "parameter_defs" in self.known and row["code"] not in self.known["parameter_defs"]:
            return f"unknown parameter {row['code']}"
        u = row.get("utility")
        if (
            kind in ("arr_values", "parameters", "facts")
            and u is not None
            and "utilities" in self.known
            and u != "TOTAL"
            and u not in self.known["utilities"]
        ):
            return f"unknown utility {u}"
        return None

    def post(self, kind: str, rows: list[dict[str, Any]]) -> Result:
        rows = _strip_review(rows)
        total = Result(kind)
        with (
            open(self.dir / f"{kind}.jsonl", "a", encoding="utf-8") as out,
            open(self.dir / "rejected.jsonl", "a", encoding="utf-8") as rej,
            open(self.dir / "batches.jsonl", "a", encoding="utf-8") as log,
        ):
            for b in batches(rows):
                res = Result(kind, batches=1)
                for i, r in b:
                    why = self._reason(kind, r)
                    if why:
                        res.rejected.append({"index": i, "reason": why, "row": r})
                        rej.write(
                            json.dumps({"kind": kind, "reason": why, "row": r}, ensure_ascii=False, default=str) + "\n"
                        )
                    else:
                        out.write(_encode(r).decode() + "\n")
                        res.written += 1
                log.write(
                    json.dumps(
                        {
                            "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                            "kind": kind,
                            "rows": len(b),
                            "bytes": sum(_size(r) for _, r in b),
                            "written": res.written,
                            "rejected": len(res.rejected),
                        }
                    )
                    + "\n"
                )
                total.add(res)
        return total


def make_sink(dry_run: str | None, known: dict[str, set[str]] | None = None) -> Sink:
    if dry_run:
        return DryRunSink(dry_run, known)
    return HttpSink()


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
