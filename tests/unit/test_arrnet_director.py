"""ARR Network Director: the planning rules, attempts and parking, the spend cap, the brief."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("arrnet")

from arrnet import director, store  # noqa: E402
from arrnet.ingest import DryRunSink  # noqa: E402
from arrnet.spend import Budget  # noqa: E402


def pol(cap=0.0):
    from arrnet.spend import policy

    p = json.loads(json.dumps(policy()))
    p["budget"] = {"daily_usd": cap, "per_agent_daily_usd": {}}
    return p


@pytest.fixture()
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("ARRNET_STATE", str(tmp_path))
    return tmp_path


def order(c: str) -> dict:
    return {"url": f"https://example.org/{c}.pdf", "sha256": c * 64, "commission": "UERC", "title": c, "licensees": ["UPCL"]}


def kinds(q: director.Queue, target: str) -> set[str]:
    return {i["kind"] for i in q.items.values() if i["target"] == target and i["state"] == "queued"}


def test_rules_follow_the_pipeline(state):
    a, b, c, d = order("a"), order("b"), order("c"), order("d")
    store.write(b["sha256"], "pages", {"order": {"pages_without_text": 0}, "pages": []})
    store.write(c["sha256"], "pages", {"order": {"pages_without_text": 0}, "pages": []})
    store.write(c["sha256"], "textlayer", {"tables": []})
    store.write(d["sha256"], "pages", {"order": {"pages_without_text": 3}, "pages": []})
    store.write(d["sha256"], "textlayer", {"tables": [{"page": 1}]})
    q = director.Queue(pol())
    planned = director.plan([a, b, c, d], q, keys={"llamaparse": False, "extractor": False})
    assert kinds(q, a["sha256"]) == {"fetch"}
    assert kinds(q, b["sha256"]) == {"parse:textlayer"}
    assert kinds(q, c["sha256"]) == {"parse:docling", "verify", "index"}  # the text layer found no table
    assert kinds(q, d["sha256"]) == {"parse:docling", "verify", "index"}  # scanned pages
    assert ("audit|all") in q.items
    assert planned["blocked"] == {"extract: no key": 1}
    assert all(dd["reason"] for dd in q.decisions)


def test_llamaparse_where_two_readers_disagree_only_with_key_and_budget(state):
    o = order("e")
    sha = o["sha256"]
    store.write(sha, "pages", {"order": {"pages_without_text": 0}, "pages": []})
    store.write(sha, "textlayer", {"tables": [{"page": 5}]})
    store.write(sha, "docling", {"tables": []})
    store.write(sha, "llm", {})
    facts = [{"page": 5, "consensus": "conflict"}] * 3 + [{"page": 5, "consensus": "agreed_2"}] * 2
    store.write(sha, "verified", {"facts": facts, "readers": {"docling": {"pages": [5]}}})
    store.write(sha, "index", {})
    q = director.Queue(pol(cap=0.0))
    p = director.plan([o], q, Budget(q.pol), keys={"llamaparse": True, "extractor": True})
    assert "parse:llamaparse" not in kinds(q, sha) and p["blocked"] == {"parse:llamaparse: budget": 1}
    q = director.Queue(pol(cap=5.0))
    director.plan([o], q, Budget(q.pol), keys={"llamaparse": False, "extractor": True})
    assert "parse:llamaparse" not in kinds(q, sha)
    q = director.Queue(pol(cap=5.0))
    director.plan([o], q, Budget(q.pol), keys={"llamaparse": True, "extractor": True})
    assert "parse:llamaparse" in kinds(q, sha)


def test_paid_work_is_not_planned_past_the_cap(state):
    os_ = [order(c) for c in "fghij"]
    for o in os_:
        store.write(o["sha256"], "pages", {"order": {"pages_without_text": 0}, "pages": []})
        store.write(o["sha256"], "textlayer", {"tables": [{"page": 1}]})
    p = pol(cap=1.25)  # the planner's estimate is 0.05 $ a page x 12 pages = 0.60 $ an order
    q = director.Queue(p)
    planned = director.plan(os_, q, Budget(p), keys={"llamaparse": False, "extractor": True})
    assert sum(1 for i in q.items.values() if i["kind"] == "extract") == 2
    assert planned["blocked"]["extract: budget"] == 3


def test_failures_are_retried_then_parked(state):
    q = director.Queue(pol())
    q.enqueue("verify", "t", "first")
    for _ in range(3):
        (it,) = q.claim()
        q.complete(it["kind"], it["target"], False, "boom")
        q.enqueue("verify", "t", "retry")
    assert q.items["verify|t"]["state"] == "parked" and "failed 3 times" in q.items["verify|t"]["error"]
    assert not q.enqueue("verify", "t", "again")


def test_brief_without_a_model_is_labelled_not_real(state, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sink = DryRunSink(state / "dry")
    out = director.direct([order("k")], sink)
    b = json.loads((state / "dry" / "briefs.jsonl").read_text())
    assert b["is_real"] is False and b["written_by"] == "director"
    assert "rule-based planner (no model)" in out["brief"] and "## Next" in out["brief"]
    items = [json.loads(x) for x in (state / "dry" / "work_items.jsonl").read_text().splitlines()]
    assert {i["kind"] for i in items} == {"fetch", "audit"}


def test_model_may_only_reorder_or_park_planned_items(state):
    from types import SimpleNamespace

    reply = {"narrative": "Fixture narrative.", "priorities": [{"kind": "fetch", "target": "l" * 64, "priority": 1,
                                                                 "reason": "first"},
                                                                {"kind": "parse:llamaparse", "target": "zzz", "priority": 1,
                                                                 "reason": "not planned"}],
             "park": [{"kind": "audit", "target": "all", "reason": "wait"}]}

    class Fake:  # FIXTURE: Messages API shape, not a model's output
        def count_tokens(self, **r):
            return SimpleNamespace(input_tokens=10)

        def create(self, **r):
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(reply))],
                                   usage=SimpleNamespace(input_tokens=10, output_tokens=10))

    q = director.Queue(pol(cap=1.0))
    o = order("l")
    o["sha256"] = None
    o["url"] = "l" * 64
    director.plan([o], q, keys={})
    narrative, _ = director.llm_direct(q, {}, SimpleNamespace(messages=Fake()), Budget(q.pol), is_real=False)
    assert narrative == "Fixture narrative."
    assert q.items["fetch|" + "l" * 64]["priority"] == 1
    assert "parse:llamaparse|zzz" not in q.items
    assert q.items["audit|all"]["state"] == "parked"
