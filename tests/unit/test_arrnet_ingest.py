"""ARR Network ingest client: batching, retries, per-row rejections, against a stub server."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("arrnet")
import httpx  # noqa: E402
from arrnet import ingest, shapes  # noqa: E402


def test_batches_respect_row_and_byte_limits():
    rows = [{"i": i, "pad": "x" * 100} for i in range(2500)]
    bs = list(ingest.batches(rows))
    assert [len(b) for b in bs] == [1000, 1000, 500]
    small = list(ingest.batches(rows, max_bytes=10_000))
    assert all(sum(len(json.dumps(r)) + 1 for _, r in b) <= 10_000 for b in small)
    assert sum(len(b) for b in small) == 2500 and [i for b in small for i, _ in b] == list(range(2500))


def stub(handler):
    calls = []

    def h(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return handler(req, len(calls))

    return httpx.MockTransport(h), calls


def test_retries_on_5xx_and_network_errors_then_succeeds():
    def handler(req, n):
        if n == 1:
            raise httpx.ConnectError("down")
        if n == 2:
            return httpx.Response(503, text="busy")
        body = json.loads(req.content)
        return httpx.Response(200, json={"kind": body["kind"], "written": len(body["rows"]), "rejected": []})

    t, calls = stub(handler)
    sink = ingest.HttpSink("http://stub", "tok", transport=t, sleep=lambda s: None)
    res = sink.post("states", [{"code": "UP", "name": "Uttar Pradesh", "kind": "state"}])
    assert res.written == 1 and len(calls) == 3
    assert calls[-1].headers["authorization"] == "Bearer tok"
    assert calls[-1].url.path == "/api/ingest/batch"


def test_gives_up_after_the_retries():
    t, calls = stub(lambda req, n: httpx.Response(500, text="no"))
    sink = ingest.HttpSink("http://stub", "tok", transport=t, retries=2, sleep=lambda s: None)
    with pytest.raises(ingest.IngestError):
        sink.post("states", [{"code": "UP", "name": "x", "kind": "state"}])
    assert len(calls) == 3


def test_per_row_rejections_are_surfaced_with_their_row_across_batches():
    def handler(req, n):
        rows = json.loads(req.content)["rows"]
        return httpx.Response(
            200, json={"written": len(rows) - 1, "rejected": [{"index": 1, "reason": "number not on page"}]}
        )

    t, calls = stub(handler)
    sink = ingest.HttpSink("http://stub", "tok", transport=t, max_rows=3)
    rows = [{"n": i} for i in range(5)]
    res = sink.post("arr_values", rows)
    assert res.batches == 2 and res.written == 3
    assert [r["index"] for r in res.rejected] == [1, 4]  # indexes in the caller's list
    assert res.rejected[1]["row"] == {"n": 4} and res.rejected[0]["reason"] == "number not on page"


def test_bad_token_raises():
    t, _ = stub(lambda req, n: httpx.Response(401, text="no"))
    with pytest.raises(ingest.IngestError, match="401"):
        ingest.HttpSink("http://stub", "bad", transport=t).post(
            "states", [{"code": "UP", "name": "x", "kind": "state"}]
        )


def test_needs_url_and_token(monkeypatch):
    monkeypatch.delenv("INGEST_URL", raising=False)
    monkeypatch.delenv("INGEST_TOKEN", raising=False)
    with pytest.raises(ingest.IngestError):
        ingest.HttpSink()


def test_review_fields_are_never_sent(tmp_path):
    with pytest.raises(ingest.IngestError):
        ingest.DryRunSink(tmp_path).post("facts", [{"reviewed_by": "agent"}])
    t, calls = stub(lambda req, n: httpx.Response(200, json={"written": 1, "rejected": []}))
    with pytest.raises(ingest.IngestError):
        ingest.HttpSink("http://stub", "tok", transport=t).post("facts", [{"review_note": "ok"}])
    assert calls == []


def test_dry_run_writes_jsonl_and_rejects_what_the_api_would(tmp_path):
    sink = ingest.DryRunSink(tmp_path, {"heads": {"om"}, "utilities": {"UPCL"}, "parameter_defs": set()})
    good = {
        "order_url": "u",
        "reader": "textlayer",
        "reader_version": "1",
        "head": "om",
        "label": "O&M",
        "value_printed": "12.5",
        "value": 12.5,
        "page": 3,
        "quote": "O&M 12.5",
        "utility": "UPCL",
    }
    res = sink.post(
        "arr_values",
        [
            good,
            {**good, "page": 0},
            {**good, "quote": " "},
            {**good, "head": "x"},
            {**good, "utility": "NOPE"},
            {**good, "extra": 1},
            {**good, "value": float("nan")},
        ],
    )
    assert res.written == 1 and len(res.rejected) == 6
    assert (tmp_path / "arr_values.jsonl").read_text().count("\n") == 1
    assert (tmp_path / "rejected.jsonl").read_text().count("\n") == 6
    assert json.loads((tmp_path / "batches.jsonl").read_text())["rows"] == 7


def test_every_ingest_kind_has_a_shape():
    for kind in (
        "states",
        "commissions",
        "utilities",
        "heads",
        "parameter_defs",
        "orders",
        "pages",
        "parses",
        "parsed_tables",
        "arr_values",
        "parameters",
        "facts",
        "paragraphs",
        "chunks",
        "work_items",
        "agent_runs",
        "metrics",
        "findings",
        "briefs",
        "gold_figures",
    ):
        assert kind in shapes.SHAPES


def test_dry_run_applies_the_consensus_rules_of_the_api(tmp_path):
    sink = ingest.DryRunSink(tmp_path)
    fact = {
        "order_url": "u",
        "utility": "UPCL",
        "fiscal_year": "FY2026-27",
        "voice": "approved",
        "head": "om",
        "label": "O&M",
        "value": 1.0,
        "page": 1,
        "quote": "O&M 1.0",
        "consensus": "agreed_2",
        "readers": ["textlayer", "docling"],
        "readings": [
            {"reader": "textlayer", "reader_version": "1", "page": 1, "value_printed": "1.0", "agrees": True},
            {"reader": "docling", "reader_version": "1", "page": 1, "value_printed": "1.0", "agrees": True},
        ],
    }
    lonely_conflict = {**fact, "consensus": "conflict", "readers": ["textlayer"]}
    agreed_with_dissent = {**fact, "readings": [*fact["readings"][:1], {**fact["readings"][1], "agrees": False}]}
    res = sink.post("facts", [fact, lonely_conflict, agreed_with_dissent])
    assert res.written == 1 and [r["index"] for r in res.rejected] == [1, 2]
