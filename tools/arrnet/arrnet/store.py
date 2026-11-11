"""The local work area (ARRNET_STATE): per order, the page text and each reader's result.

The database is reached only through the ingest API, which is write-only for agents, so what
one agent hands the next (the Verifier reads every reader's readings, the Librarian the page
text) is kept here as JSON.  It is a cache of what was posted, never a second database.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import state_dir


def order_dir(sha: str) -> Path:
    d = state_dir() / "orders" / sha
    d.mkdir(parents=True, exist_ok=True)
    return d


def write(sha: str, name: str, data: Any) -> Path:
    p = order_dir(sha) / f"{name}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str))
    tmp.replace(p)
    return p


def read(sha: str, name: str) -> Any | None:
    p = state_dir() / "orders" / sha / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


def exists(sha: str, name: str) -> bool:
    return (state_dir() / "orders" / sha / f"{name}.json").exists()


def write_global(name: str, data: Any) -> Path:
    p = state_dir() / f"{name}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, default=str, indent=1))
    tmp.replace(p)
    return p


def read_global(name: str, default: Any = None) -> Any:
    p = state_dir() / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else default


def append_jsonl(name: str, rows: list[dict[str, Any]]) -> None:
    with open(state_dir() / f"{name}.jsonl", "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def read_jsonl(name: str) -> list[dict[str, Any]]:
    p = state_dir() / f"{name}.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
