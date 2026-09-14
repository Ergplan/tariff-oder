"""The manifest verdict shown on a source is re-computed against the current manifest."""

from __future__ import annotations

import json
from types import SimpleNamespace

from tariff_api import golden


def _manifest(tmp_path, expected_no_text: int) -> str:
    p = tmp_path / "manifest.json"
    p.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "x",
                        "sha256": "abc",
                        "expected": {"size_bytes": 10, "page_count": 3, "pages_without_text_layer": expected_no_text},
                    }
                ]
            }
        )
    )
    golden.load_manifest.cache_clear()
    return str(p)


def test_stale_stored_check_is_superseded_by_current_manifest(tmp_path):
    src = SimpleNamespace(
        golden_id="x",
        sha256="abc",
        size_bytes=10,
        page_count=3,
        pages_without_text=0,
        manifest_check={"golden_id": "x", "checks": {"pages_without_text_layer": {"match": False}}, "all_match": False},
    )
    check = golden.current_check(_manifest(tmp_path, 0), src)
    assert check["all_match"] is True
    assert check["checked_at_read"] is True
    assert check["checks"]["pages_without_text_layer"] == {"expected": 0, "observed": 0, "match": True}


def test_not_in_manifest_or_not_inventoried_returns_stored_record(tmp_path):
    path = _manifest(tmp_path, 0)
    stored = {"golden_id": "x", "checks": {}, "all_match": True}
    unknown = SimpleNamespace(
        golden_id=None, sha256="zzz", size_bytes=1, page_count=None, pages_without_text=None, manifest_check=None
    )
    assert golden.current_check(path, unknown) is None
    registered = SimpleNamespace(
        golden_id="x", sha256="abc", size_bytes=10, page_count=None, pages_without_text=None, manifest_check=stored
    )
    assert golden.current_check(path, registered) is stored  # re-checked only once inventoried
