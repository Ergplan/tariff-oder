"""The Extractor answered by session agents (arrnet.session_extract).

FIXTURE: the reply below is hand-written in the Extractor's schema for a hand-made page.  It
tests the plumbing — packets out, replies in, the unchanged filter and evidence check — and the
provenance recorded (provider claude-code-session, never the Anthropic API, no API cost).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("arrnet")
from arrnet import session_extract as se  # noqa: E402
from arrnet import store  # noqa: E402

PAGE = (
    "Table 4.52: Aggregate Revenue Requirement approved for FY 2026-27 (Rs. Crore)\n"
    "Particulars Claimed Approved\nNet ARR 9,675.43 9,646.75\n"
    "4.3 The Commission approves the distribution loss of 12.50% for FY 2026-27.\n"
)


@pytest.fixture()
def order(tmp_path, monkeypatch):
    monkeypatch.setenv("ARRNET_STATE", str(tmp_path / "state"))
    sha = "c" * 64
    pages = [{"page": i, "text": PAGE if i == 2 else "word " * 30, "has_text_layer": True} for i in range(1, 4)]
    store.write(sha, "pages", {"order": {}, "pages": pages})
    store.write(sha, "textlayer", {"tables": [{"page": 2, "pages": [2]}]})
    return {"url": "https://example.org/o.pdf", "sha256": sha, "licensees": ["UPCL"], "arr_year": "FY2026-27",
            "commission": "UERC"}  # fmt: skip


def test_packets_replies_and_provenance(order, tmp_path):
    d = tmp_path / "session"
    index = se.prepare(d, [order])
    assert [x["page"] for x in index] == [2]
    key = index[0]["key"]
    assert "untrusted" in (d / "system.txt").read_text()
    reply = {
        "lines": [{"utility": "UPCL", "fiscal_year": "FY2026-27", "voice": "approved", "head": "net_arr",
                   "label": "Net ARR", "value_printed": "9,646.75", "unit": "Rs. Crore", "page": 2,
                   "quote": "Net ARR 9,675.43 9,646.75"}],
        "parameters": [
            {"code": "distribution_loss_pct", "utility": "UPCL", "fiscal_year": "FY2026-27", "voice": "approved",
             "label": "distribution loss", "value_printed": "12.50%", "unit": "%", "page": 2,
             "quote": "The Commission approves the distribution loss of 12.50% for FY 2026-27."},
            # a number not on the page: the evidence check must reject it
            {"code": "avg_cost_of_supply", "utility": "UPCL", "fiscal_year": "FY2026-27", "voice": "approved",
             "label": "ACoS", "value_printed": "7.77", "unit": "Rs/kWh", "page": 2, "quote": "ACoS 7.77"},
        ],
        "paragraphs": [],
    }  # fmt: skip
    if "net_arr" not in se.extractor(d).heads:
        reply["lines"][0]["head"] = se.extractor(d).heads[0]
    (d / "replies" / f"{key}.json").write_text(json.dumps(reply))
    rep = se.check(d, key)
    assert rep["ok"] and rep["kept"]["parameters"] == 2  # "12.50%" is parsed, not dropped
    assert rep["dropped_by_filter"] == 0
    assert rep["fail_evidence_count"] == 1 and rep["fail_evidence"][0]["value_printed"] == "7.77"

    res = se.extractor(d).read(order)
    assert res.status == "ok" and res.pages_parsed == 1
    assert res.provider == "claude-code-session" and res.model == "session agent"
    assert res.cost_usd == 0.0 and res.is_real
    row = res.parse_row(order["url"])
    assert row["reader"] == "llm" and row["provider"] == "claude-code-session"


def test_missing_reply_is_a_page_not_read(order, tmp_path):
    d = tmp_path / "session"
    se.prepare(d, [order])
    res = se.extractor(d).read(order)
    assert res.status == "partial" and res.pages_parsed == 0
    assert not res.values and not res.parameters
