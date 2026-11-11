"""Director — the manager.  A rule-based planner that works with no key:

    fetch -> parse:textlayer -> parse:docling (the text layer found no ARR table, or the order has
    scanned pages) -> parse:llamaparse (two readers disagree) -> extract -> verify -> index

It respects the daily budget (paid work is not enqueued beyond what the cap leaves, and the cap
is enforced again in code at the call), gives a failed item ``max_attempts`` tries and then parks
it for a person, and writes a brief: what was done, what failed, coverage, spend, and what it
will do next.  The brief is ``is_real: false`` when no model wrote it.

With ``ANTHROPIC_API_KEY`` set, a model (policy: models.director) writes the brief's narrative
and may reorder priorities or park items — only through ``Queue.enqueue`` / ``Queue.park``, and
only for items the rules already planned.  It never writes a value, a consensus class or a
review; it sees counts and codes, never document text.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from collections import Counter
from typing import Any

from . import store
from .ingest import Sink
from .runs import Run
from .spend import Budget, BudgetExceeded, policy, token_cost

VERSION = "director 1"
PAID = {"parse:llamaparse": "llamaparse", "extract": "extractor"}


class Queue:
    """The work queue, kept in the state directory and mirrored to ``work_items`` through the
    ingest API.  Only these functions change it."""

    def __init__(self, pol: dict[str, Any] | None = None, name: str = "queue") -> None:
        self.pol = pol or policy()
        self.name = name
        self.items: dict[str, dict[str, Any]] = store.read_global(name, {})
        self.decisions: list[dict[str, Any]] = []

    @staticmethod
    def key(kind: str, target: str) -> str:
        return f"{kind}|{target}"

    def save(self) -> None:
        store.write_global(self.name, self.items)

    def enqueue(self, kind: str, target: str, reason: str, priority: int | None = None, by: str = "director") -> bool:
        k = self.key(kind, target)
        it = self.items.get(k)
        prio = priority if priority is not None else int(self.pol["queue"]["priorities"].get(kind, 100))
        if it and it["state"] in ("queued", "claimed"):
            if priority is not None and priority != it["priority"]:
                it["priority"] = priority
                self.decisions.append(
                    {
                        "action": "reprioritise",
                        "kind": kind,
                        "target": target,
                        "priority": priority,
                        "reason": reason,
                        "by": by,
                    }
                )
            return False
        if it and it["state"] == "parked":
            return False
        if it and it["state"] == "failed" and it["attempts"] >= int(self.pol["queue"]["max_attempts"]):
            self.park(kind, target, f"failed {it['attempts']} times: {it.get('error')}", by=by)
            return False
        self.items[k] = {
            "kind": kind,
            "target": target,
            "state": "queued",
            "priority": prio,
            "attempts": (it or {}).get("attempts", 0),
            "error": (it or {}).get("error"),
            "created_by": by,
        }
        self.decisions.append(
            {"action": "enqueue", "kind": kind, "target": target, "priority": prio, "reason": reason, "by": by}
        )
        return True

    def park(self, kind: str, target: str, reason: str, by: str = "director") -> None:
        k = self.key(kind, target)
        it = self.items.setdefault(
            k, {"kind": kind, "target": target, "priority": 100, "attempts": 0, "created_by": by}
        )
        it["state"] = "parked"
        it["error"] = reason
        self.decisions.append({"action": "park", "kind": kind, "target": target, "reason": reason, "by": by})

    def claim(self, kinds: list[str] | None = None, limit: int = 1) -> list[dict[str, Any]]:
        ready = sorted(
            (i for i in self.items.values() if i["state"] == "queued" and (not kinds or i["kind"] in kinds)),
            key=lambda i: (i["priority"], i["kind"], i["target"]),
        )[:limit]
        for i in ready:
            i["state"] = "claimed"
            i["attempts"] = i.get("attempts", 0) + 1
        return ready

    def complete(self, kind: str, target: str, ok: bool, error: str | None = None) -> None:
        it = self.items[self.key(kind, target)]
        it["state"] = "done" if ok else "failed"
        it["error"] = error
        it["finished_at"] = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def order_state(o: dict[str, Any]) -> dict[str, Any]:
    sha = o.get("sha256")
    if not sha:
        return {"listed": True}
    pages = store.read(sha, "pages")
    tl = store.read(sha, "textlayer")
    v = store.read(sha, "verified")
    st: dict[str, Any] = {
        "fetched": pages is not None,
        "pages_without_text": (pages or {}).get("order", {}).get("pages_without_text", 0),
        "textlayer": tl is not None,
        "textlayer_tables": len((tl or {}).get("tables", [])),
        "docling": store.exists(sha, "docling"),
        "llamaparse": store.exists(sha, "llamaparse"),
        "llm": store.exists(sha, "llm"),
        "verified": v is not None,
        "indexed": store.exists(sha, "index"),
    }
    if v:
        c = Counter(f["consensus"] for f in v["facts"])
        st["conflicts"] = c["conflict"]
        st["facts"] = sum(c.values())
        # disagreement: on Docling's pages, figures one reader gave and the other did not
        dp = set((v["readers"].get("docling") or {}).get("pages") or [])
        single = [f for f in v["facts"] if f["page"] in dp and f["consensus"] == "single"]
        st["single_on_shared_pages"] = len(single)
        st["facts_on_shared_pages"] = sum(1 for f in v["facts"] if f["page"] in dp)
    # a reader newer than the verification needs verifying again
    d = store.state_dir() / "orders" / sha
    if v is not None:
        vt = (d / "verified.json").stat().st_mtime
        st["stale"] = any(
            (d / f"{r}.json").exists() and (d / f"{r}.json").stat().st_mtime > vt
            for r in ("textlayer", "docling", "llamaparse", "llm")
        )
    return st


def plan(
    orders: list[dict[str, Any]], q: Queue, budget: Budget | None = None, keys: dict[str, bool] | None = None
) -> dict[str, Any]:
    """Apply the rules; return what was planned and what is blocked, with reasons."""
    pol = q.pol
    budget = budget or Budget(pol)
    keys = (
        keys
        if keys is not None
        else {
            "llamaparse": bool(os.environ.get("LLAMA_CLOUD_API_KEY")),
            "extractor": bool(os.environ.get("ANTHROPIC_API_KEY")),
        }
    )
    blocked: Counter = Counter()
    lp = pol["llamaparse"]
    est = {
        "llamaparse": lp["max_pages_per_order"]
        * lp["credits_per_page"][lp["tier"]]
        * lp["usd_per_1000_credits"]
        / 1000,
        "extractor": 0.05 * pol["extractor"]["max_pages_per_order"],
    }  # rough per-order estimates for planning
    planned_cost = Counter()

    def paid(kind: str, target: str, reason: str) -> None:
        agent = PAID[kind]
        if not keys.get(agent):
            blocked[f"{kind}: no key"] += 1
            return
        if planned_cost[agent] + est[agent] > budget.remaining(agent):
            blocked[f"{kind}: budget"] += 1
            return
        if q.enqueue(kind, target, reason):
            planned_cost[agent] += est[agent]

    for o in orders:
        t = o.get("sha256")
        if not t:
            q.enqueue("fetch", o["url"], "listed, not downloaded")
            continue
        s = order_state(o)
        if not s["fetched"]:
            q.enqueue("fetch", t, "no page text yet")
            continue
        if not s["textlayer"]:
            q.enqueue("parse:textlayer", t, "not read yet")
            continue
        if not s["docling"] and (s["textlayer_tables"] == 0 or s["pages_without_text"] > 0):
            why = (
                "the text layer found no ARR table"
                if s["textlayer_tables"] == 0
                else f"{s['pages_without_text']} pages without a text layer"
            )
            q.enqueue("parse:docling", t, why)
        if s.get("verified") and s["docling"] and not s["llamaparse"]:
            disagree = s.get("conflicts", 0) + s.get("single_on_shared_pages", 0)
            if s.get("facts_on_shared_pages") and disagree > 0.2 * s["facts_on_shared_pages"]:
                paid(
                    "parse:llamaparse",
                    t,
                    f"text layer and Docling disagree on {disagree} of {s['facts_on_shared_pages']} figures",
                )
        if not s["llm"] and s["textlayer_tables"] > 0:
            paid("extract", t, "ARR tables read; key parameters and paragraphs not extracted")
        if not s["verified"] or s.get("stale"):
            q.enqueue(
                "verify",
                t,
                "readings not verified yet" if not s["verified"] else "a reader ran after the last verification",
            )
        if not s["indexed"]:
            q.enqueue("index", t, "paragraphs not indexed")
    q.enqueue("audit", "all", "after every run")
    return {"blocked": dict(blocked), "planned_cost_usd": {k: round(v, 4) for k, v in planned_cost.items()}}


def brief(orders: list[dict[str, Any]], q: Queue, planned: dict[str, Any], narrative: str | None = None) -> str:
    states = [order_state(o) for o in orders]
    runs = store.read_jsonl("runs")
    last_day = max((r["started_at"][:10] for r in runs), default=None)
    today_runs = [r for r in runs if r["started_at"][:10] == last_day]
    by_agent = Counter(r["agent"] for r in today_runs)
    failed = [r for r in today_runs if r["outcome"] == "failed"]
    audit = store.read_global("auditor-last", {}).get("report", {})
    budget = Budget(q.pol)
    queued = Counter(i["kind"] for i in q.items.values() if i["state"] == "queued")
    parked = [i for i in q.items.values() if i["state"] == "parked"]
    lines = [
        "# ARR Network — Director's brief",
        "",
        f"Written {dt.datetime.now(dt.UTC).isoformat(timespec='minutes')} by "
        + (
            "the rule-based planner (no model)."
            if narrative is None
            else f"{q.pol['models']['director']} (narrative) and the rule-based planner."
        ),
        "Nothing here is reviewed: consensus classes are machine agreement, not a person's check.",
        "",
    ]
    if narrative:
        lines += ["## Summary", "", narrative.strip(), ""]
    lines += ["## Done", ""]
    lines += [f"- {a}: {n} runs" for a, n in sorted(by_agent.items())] or ["- nothing yet"]
    lines += ["", "## Failed", ""]
    lines += [f"- {r['agent']} {r.get('order_url', '')}: {r.get('note', '')[:160]}" for r in failed[:20]] or ["- none"]
    cov = (audit.get("coverage") or {}).get("discom") or {}
    lines += [
        "",
        "## Coverage",
        "",
        f"- orders: {len(orders)}; read by the text layer: {sum(1 for s in states if s.get('textlayer'))}; "
        f"by Docling: {sum(1 for s in states if s.get('docling'))}; "
        f"verified: {sum(1 for s in states if s.get('verified'))}; "
        f"indexed: {sum(1 for s in states if s.get('indexed'))}",
    ]
    if cov:
        lines.append(f"- DISCOMs with a headline ARR: {cov.get('utilities_with_headline')} of {cov.get('listed')}")
        tcov = (audit.get("coverage") or {}).get("transco") or {}
        if tcov:
            lines.append(
                f"- TRANSCOs with a headline ARR: {tcov.get('utilities_with_headline')} of {tcov.get('listed')}"
            )
    g = (audit.get("gold") or {}).get("textlayer")
    if g:
        lines.append(
            f"- text layer on hand-read figures: {g['found']}/{g['comparable_nonzero']} found, "
            f"voice {g['voice_agrees']}/{g['voice_checked']}, utility {g['licensee_agrees']}/{g['licensee_checked']}"
        )
    lines += [
        "",
        "## Spend",
        "",
        f"- today: ${budget.spent():.4f} of the daily cap ${float(q.pol['budget']['daily_usd']):.2f}",
    ]
    lines += ["", "## Next", ""]
    lines += [f"- {k}: {n} queued" for k, n in sorted(queued.items())] or ["- nothing queued"]
    for k, n in sorted((planned.get("blocked") or {}).items()):
        lines.append(f"- blocked — {k}: {n} orders")
    if parked:
        lines += ["", "## Parked for a person", ""]
        lines += [f"- {i['kind']} {i['target'][:16]}: {str(i.get('error'))[:160]}" for i in parked[:30]]
    return "\n".join(lines) + "\n"


DIRECTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "narrative": {"type": "string"},
        "priorities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string"},
                    "target": {"type": "string"},
                    "priority": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["kind", "target", "priority", "reason"],
                "additionalProperties": False,
            },
        },
        "park": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"kind": {"type": "string"}, "target": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["kind", "target", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["narrative", "priorities", "park"],
    "additionalProperties": False,
}

DIRECTOR_SYSTEM = """You manage a network of programs that read Indian electricity ARR tariff orders. \
You are given the rule-based plan, the queue, failures, coverage, accuracy measures and spend, as \
JSON. Write a short narrative for the operator (what was done, what failed, what matters next), \
and optionally reorder queued items (priority: lower runs first) or park items that should wait \
for a person, each with a reason. You may only refer to items in the queue you are given. You \
cannot change any figure, consensus class or review."""


def llm_direct(
    q: Queue, summary: dict[str, Any], client: Any, budget: Budget, *, is_real: bool = True
) -> tuple[str | None, dict]:
    pol = q.pol
    model = pol["models"]["director"]
    req = {
        "model": model,
        "system": DIRECTOR_SYSTEM,
        "messages": [{"role": "user", "content": json.dumps(summary, default=str)[:200000]}],
    }
    n_in = client.messages.count_tokens(**req).input_tokens
    if is_real:
        budget.reserve("director", token_cost(pol, model, {"input_tokens": n_in, "output_tokens": 4000}))
    resp = client.messages.create(
        **req,
        max_tokens=8000,
        output_config={
            "effort": (pol.get("effort") or {}).get("director", "medium"),
            "format": {"type": "json_schema", "schema": DIRECTOR_SCHEMA},
        },
    )
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}
    cost = token_cost(pol, model, usage)
    budget.record("director", "anthropic", model, cost, is_real=is_real, **usage)
    if resp.stop_reason in ("refusal", "max_tokens"):
        return None, {"cost_usd": cost, **usage, "note": f"stop_reason {resp.stop_reason}"}
    data = json.loads(next(b.text for b in resp.content if getattr(b, "type", "") == "text"))
    queued = {Queue.key(i["kind"], i["target"]) for i in q.items.values() if i["state"] == "queued"}
    for p in data.get("priorities", []):
        if Queue.key(p["kind"], p["target"]) in queued:  # only items the rules planned
            q.enqueue(
                p["kind"], p["target"], f"model: {p['reason'][:200]}", priority=int(p["priority"]), by="director:llm"
            )
    for p in data.get("park", []):
        if Queue.key(p["kind"], p["target"]) in queued:
            q.park(p["kind"], p["target"], f"model: {p['reason'][:200]}", by="director:llm")
    return data.get("narrative"), {"cost_usd": cost, **usage}


def direct(orders: list[dict[str, Any]], sink: Sink, *, client: Any = None) -> dict[str, Any]:
    q = Queue()
    budget = Budget(q.pol)
    run = Run("director", VERSION)
    planned = plan(orders, q, budget)
    narrative, extra = None, {}
    if client is None and os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic

        client = anthropic.Anthropic()
    if client is not None:
        summary = {
            "planned": planned,
            "decisions": q.decisions[-200:],
            "queue": [i for i in q.items.values() if i["state"] in ("queued", "failed", "parked")][:300],
            "audit": store.read_global("auditor-last", {}).get("report", {}).get("coverage"),
            "spent_today": budget.spent(),
        }
        try:
            narrative, extra = llm_direct(q, summary, client, budget)
        except BudgetExceeded as e:
            extra = {"note": f"model not called: {e}"}
    body = brief(orders, q, planned, narrative)
    q.save()
    items = [
        {"kind": d["kind"], "target": d["target"], "priority": d.get("priority", 100), "created_by": d["by"]}
        for d in q.decisions
        if d["action"] == "enqueue"
    ]
    w = sink.post("work_items", items).written if items else 0
    w += sink.post(
        "briefs",
        [{"written_by": "director", "is_real": narrative is not None, "body": body, "decisions": q.decisions[:500]}],
    ).written
    store.write_global("brief", {"body": body, "decisions": q.decisions})
    run.post(
        sink,
        "ok",
        extra.get("note") or f"{len(q.decisions)} decisions",
        is_real=True,
        rows_written=w,
        provider="anthropic" if narrative else None,
        model=q.pol["models"]["director"] if narrative else None,
        input_tokens=extra.get("input_tokens", 0),
        output_tokens=extra.get("output_tokens", 0),
        cost_usd=round(extra.get("cost_usd", 0.0), 6),
    )
    return {"planned": planned, "decisions": len(q.decisions), "brief": body}
