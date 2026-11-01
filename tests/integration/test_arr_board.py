"""The ARR readings board (increment 49): every order whose ARR is read, by state and
commission, with its preview, its review counts and the next human step.  SYNTHETIC fixture
data, labelled as such on the board."""

from __future__ import annotations

import shutil

import pytest
from arr_helpers import read_and_publish

from conftest import CLIENT_A, headers

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]


def test_the_board_lists_each_reading_with_its_next_step(client, runner, object_store_root):
    read_and_publish(client, runner, "SYNTH-BOARD")
    r = client.get("/arr/readings", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    b = r.json()
    (state,) = [s for s in b["states"] if any(c["code"] == "SYNTHERC" for c in s["commissions"])]
    (com,) = [c for c in state["commissions"] if c["code"] == "SYNTHERC"]
    assert com["mapping"]["id"] == "syntherc-arr" and isinstance(com["conventions_open"], int)
    order = next(o for o in com["orders"] if "SYNTH-BOARD" in o["licensees"])
    assert order["dataset"] == "fixture"  # fixture data is labelled
    assert order["arr_state"] == "published" and order["next_step"].startswith("Published")
    assert order["decided"] >= 1 and order["candidates"]
    assert b["totals"]["orders"] >= 1 and b["totals"]["states"] >= 1
    assert "facts only when a reviewer approves" in b["note"]
    assert client.get("/arr/readings").status_code in (401, 403)


def test_next_step_names_the_human_decision():
    from collections import Counter

    from tariff_api.arr.board import next_step

    assert "confirms the chapters" in next_step("chapters_proposed", Counter(), False, False)
    assert "mapping is not confirmed" in next_step("awaiting_review", Counter(pending=4), False, False)
    assert next_step("awaiting_review", Counter(pending=4), False, True).startswith("A reviewer decides the 4")
    assert next_step(None, Counter(), False, False).startswith("An administrator starts")
