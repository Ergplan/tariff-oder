"""Golden-corpus manifest lookup (Section 6.12).

The manifest lists real reviewed orders by content hash with expected structural facts.
Registration never copies these values; it re-verifies them and records the result.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=4)
def load_manifest(path: str) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    return {entry["sha256"]: entry for entry in data.get("entries", [])}


def find_by_sha256(path: str, sha256: str) -> dict[str, Any] | None:
    return load_manifest(path).get(sha256)


def compare_inventory(entry: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Compare observed inventory to the manifest's expectations; every mismatch is reported."""
    checks: dict[str, Any] = {}
    for key in ("page_count", "size_bytes"):
        if key in entry.get("expected", {}):
            checks[key] = {
                "expected": entry["expected"][key],
                "observed": observed.get(key),
                "match": entry["expected"][key] == observed.get(key),
            }
    exp_no_text = entry.get("expected", {}).get("pages_without_text_layer")
    if exp_no_text is not None and "pages_without_text" in observed:
        checks["pages_without_text_layer"] = {
            "expected": exp_no_text,
            "observed": observed["pages_without_text"],
            "match": exp_no_text == observed["pages_without_text"],
        }
    return {"golden_id": entry["id"], "checks": checks, "all_match": all(c["match"] for c in checks.values())}


def current_check(path: str, src: Any) -> dict[str, Any] | None:
    """Re-verify a registered source against the manifest as it is *now*.

    The stored ``manifest_check`` is the record made at registration and inventory time; the
    manifest is versioned with the code and its expectations can be corrected later (the NPCL
    entry's text-layer count was).  Every read re-compares the persisted inventory facts with
    the current manifest so the page never shows a stale verdict; the stored record is kept
    as history and returned when the source is not in the manifest or not yet inventoried.
    """
    if not src.golden_id or src.page_count is None:
        return src.manifest_check
    entry = find_by_sha256(path, src.sha256)
    if entry is None:
        return src.manifest_check
    observed: dict[str, Any] = {"size_bytes": src.size_bytes, "page_count": src.page_count}
    if src.pages_without_text is not None:
        observed["pages_without_text"] = src.pages_without_text
    check = compare_inventory(entry, observed)
    check["checked_at_read"] = True
    return check
