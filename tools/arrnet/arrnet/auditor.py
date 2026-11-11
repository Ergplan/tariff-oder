"""Auditor — deterministic.  Measures the network after a run and posts ``metrics`` (and the
hand-read ``gold_figures`` it measures against); raises ``findings`` when a measure falls against
the previous run.

- gold accuracy per reader (port of arrdb.check): for each figure a person read from an order
  (packages/order-reproductions, packages/reference-filings), in a table the reader read and on a
  page it read: did it find the number on that page, with the same voice and utility where the
  hand-read key says so?  Also on one common set — figures the text-layer reader could be
  measured on, on pages Docling converted — so that the two readers are compared like for like.
- cross-order agreement (port of arrdb.check.cross_order): an order's approval of a year and the
  same approval quoted in a later order, read independently, carry the same figure.
- reader agreement: the share of facts in each consensus class, by commission, and the share of
  text-layer facts on Docling's pages that Docling also gave.
- evidence rejections per reader; coverage (utilities with a headline ARR per year, against the
  DISCOMs listed); spend by agent, provider and day; time per agent.

The previous run is kept in the state directory (``auditor-last.json``): the ingest API has no
read endpoint for metrics that this client can rely on.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import config, store
from .ingest import Sink
from .reference import rows as ref_rows
from .runs import Run

VERSION = "auditor 1"
HIGHER_IS_BETTER = (
    "gold_values_found",
    "gold_voice_agrees",
    "gold_utility_agrees",
    "cross_order_agreement",
    "coverage_utilities",
)


def hand_figures() -> list[dict[str, Any]]:
    from arrdb.check import hand_figures as hf

    out = []
    for h in hf(config.REPO):
        h = dict(h)
        h["source"] = str(Path(h["file"]).resolve().relative_to(config.REPO.resolve()))
        out.append(h)
    return out


def _table_numbers(tables: list[dict[str, Any]]) -> set[str]:
    out = set()
    for t in tables:
        m = re.match(r"table\s*[-–:.]*\s*([\d.\-]+\d)", t.get("title") or "", re.I)
        if m:
            out.add(m.group(1))
    return out


def gold(
    verified: dict[str, dict[str, Any]],
    figures: list[dict[str, Any]],
    reader: str,
    restrict_pages: dict[str, set[int]] | None = None,
    table_reader: str | None = None,
) -> dict[str, Any]:
    """arrdb.check's measure for one reader.  ``restrict_pages`` limits it to those pages of each
    order; ``table_reader`` takes the "in a table the reader read" test from another reader (the
    common set)."""
    c: Counter = Counter()
    wrong, misses = [], []
    measured = set()
    for h in figures:
        v = verified.get(h["sha"] or "")
        if v is None:
            c["order_not_verified"] += 1
            continue
        pr = v["readers"].get(reader)
        tr = v["readers"].get(table_reader or reader)
        if pr is None or tr is None:
            c["reader_did_not_run"] += 1
            continue
        if restrict_pages is not None and h["page"] not in restrict_pages.get(h["sha"], set()):
            c["page_outside_the_set"] += 1
            continue
        m = re.search(r"table\s*([\d.\-]+\d)", h["what"], re.I)
        if not m or m.group(1) not in _table_numbers(tr["tables"]):
            c["not_in_a_table_the_reader_read"] += 1
            continue
        tr_pages = {x["page"] for x in tr["values"]}
        if h["page"] not in tr_pages:
            c["table_read_but_page_not"] += 1
            continue
        c["comparable"] += 1
        measured.add(h["sha"])
        if h["value"] == 0:
            c["zero_skipped"] += 1
            continue
        rows = [x for x in pr["values"] if x["page"] == h["page"] and abs(abs(x["value"]) - abs(h["value"])) < 0.006]
        if not rows:
            c["value_not_found"] += 1
            misses.append({k: h[k] for k in ("key", "page", "value", "what")})
            continue
        c["value_found"] += 1
        if h["voice"]:
            c["voice_checked"] += 1
            if any(r.get("voice") == h["voice"] for r in rows):
                c["voice_agrees"] += 1
            else:
                wrong.append(
                    {
                        "key": h["key"],
                        "page": h["page"],
                        "expected_voice": h["voice"],
                        "read": sorted({str(r.get("voice")) for r in rows}),
                    }
                )
        if h["licensee"]:
            c["licensee_checked"] += 1
            if any(r.get("utility") == h["licensee"] for r in rows):
                c["licensee_agrees"] += 1
            else:
                wrong.append(
                    {
                        "key": h["key"],
                        "page": h["page"],
                        "expected_utility": h["licensee"],
                        "read": sorted({str(r.get("utility")) for r in rows}),
                    }
                )
    return {
        "counts": dict(c),
        "orders_measured": len(measured),
        "comparable_nonzero": c["comparable"] - c["zero_skipped"],
        "found": c["value_found"],
        "voice_checked": c["voice_checked"],
        "voice_agrees": c["voice_agrees"],
        "licensee_checked": c["licensee_checked"],
        "licensee_agrees": c["licensee_agrees"],
        "missed": misses[:50],
        "disagreements": wrong[:50],
    }


def cross_order(verified: dict[str, dict[str, Any]], reader: str = "textlayer") -> dict[str, Any]:
    """arrdb.check.cross_order over one reader's verified values."""
    a, b = [], []
    for v in verified.values():
        pr = v["readers"].get(reader)
        if not pr:
            continue
        ay, comm = v["order"].get("arr_year"), v["order"].get("commission")
        for x in pr["values"]:
            if (
                x.get("head") == "other"
                or not x.get("utility")
                or x["utility"] == "TOTAL"
                or x.get("value_crore") is None
            ):
                continue
            if x.get("voice") == "approved" and x.get("is_primary") and x.get("fiscal_year") == ay:
                a.append((x["utility"], x["fiscal_year"], x["head"], x["value_crore"], ay, comm))
            elif x.get("voice") == "approved_earlier":
                b.append((x["utility"], x["fiscal_year"], x["head"], x["value_crore"], ay))
    a_by = defaultdict(list)
    for r in a:
        a_by[(r[0], r[1], r[2])].append(r)
    groups: dict[tuple, int] = {}
    for rb in b:
        for ra in a_by.get((rb[0], rb[1], rb[2]), []):
            if rb[4] and ra[4] and rb[4] > ra[4]:
                k = (ra[5], ra[0], ra[1], ra[2])
                ok = int(any(abs(a2[3] - rb[3]) < 0.006 for a2 in a_by[(rb[0], rb[1], rb[2])]))
                groups[k] = max(groups.get(k, 0), ok)
    by: dict[str, list[int]] = {}
    for (comm, *_), ok in groups.items():
        by.setdefault(comm, [0, 0])
        by[comm][0] += 1
        by[comm][1] += ok
    return {
        "pairs": len(groups),
        "agree": sum(groups.values()),
        "by_commission": {k: {"pairs": p, "agree": q} for k, (p, q) in sorted(by.items())},
    }


def load_verified(orders: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for o in orders:
        if o.get("sha256"):
            v = store.read(o["sha256"], "verified")
            if v:
                out[o["sha256"]] = v
    return out


def measure(orders: list[dict[str, Any]], on: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    on = on or dt.date.today().isoformat()
    verified = load_verified(orders)
    figs = hand_figures()
    metrics: list[dict[str, Any]] = []

    def m(name: str, scope: str, num: float | None, den: float | None, detail: Any = None) -> None:
        val = (num / den) if (num is not None and den) else None
        metrics.append(
            {
                "measured_on": on,
                "name": name,
                "scope": scope,
                "numerator": num,
                "denominator": den,
                "value": round(val, 6) if val is not None else None,
                "detail": detail,
            }
        )

    readers = sorted({r for v in verified.values() for r in v["readers"]})
    report: dict[str, Any] = {"orders_verified": len(verified), "gold": {}, "gold_common_set": {}}
    for r in readers:
        g = gold(verified, figs, r)
        report["gold"][r] = g
        m("gold_values_found", r, g["found"], g["comparable_nonzero"], {k: g[k] for k in ("counts", "orders_measured")})
        m("gold_voice_agrees", r, g["voice_agrees"], g["voice_checked"])
        m("gold_utility_agrees", r, g["licensee_agrees"], g["licensee_checked"])
    if "docling" in readers and "textlayer" in readers:
        dpages = {
            sha: set(v["readers"]["docling"]["pages"]) for sha, v in verified.items() if "docling" in v["readers"]
        }
        for r in ("textlayer", "docling"):
            g = gold(verified, figs, r, restrict_pages=dpages, table_reader="textlayer")
            report["gold_common_set"][r] = g
            m(
                "gold_values_found_common_set",
                r,
                g["found"],
                g["comparable_nonzero"],
                {"set": "figures the text layer can be measured on, on pages Docling converted", **g["counts"]},
            )
            m("gold_voice_agrees_common_set", r, g["voice_agrees"], g["voice_checked"])
            m("gold_utility_agrees_common_set", r, g["licensee_agrees"], g["licensee_checked"])
    report["cross_order"] = {}
    for r in readers:
        co = cross_order(verified, r)
        report["cross_order"][r] = co
        m("cross_order_agreement", r, co["agree"], co["pairs"], co["by_commission"])
    # consensus classes by commission; and, for each reader that read a sample of pages, how often
    # it and the text layer gave the same figure on those pages
    cls: dict[str, Counter] = defaultdict(Counter)
    pair: dict[str, Counter] = defaultdict(Counter)
    for v in verified.values():
        comm = v["order"]["commission"]
        for f in v["facts"]:
            cls[comm][f["consensus"]] += 1
            cls["all"][f["consensus"]] += 1
        for other in ("docling", "llamaparse", "llm"):
            op = set((v["readers"].get(other) or {}).get("pages") or [])
            if not op:
                continue
            c = pair[other]
            for f in v["facts"]:
                if f["page"] not in op:
                    continue
                agree = {r["reader"] for r in f["readings"] if r["agrees"]}
                tl, ot = "textlayer" in agree, other in agree
                c["textlayer_facts"] += tl
                c[f"{other}_facts"] += ot
                c["both"] += tl and ot
                differ = {r["reader"] for r in f["readings"] if not r["agrees"]}
                # a conflict between the two: one of them gave the fact's value, the other a different one
                c["conflicts"] += ("textlayer" in agree and other in differ) or (
                    other in agree and "textlayer" in differ
                )
    for comm, c in sorted(cls.items()):
        total = sum(c.values())
        for k in ("single", "agreed_2", "agreed_3", "conflict"):
            m(f"consensus_{k}_share", comm, c[k], total)
    report["consensus"] = {k: dict(v) for k, v in cls.items()}
    report["reader_agreement"] = {}
    for other, c in sorted(pair.items()):
        m(f"textlayer_facts_{other}_also_gave", f"{other}_pages", c["both"], c["textlayer_facts"], dict(c))
        m(f"{other}_facts_textlayer_also_gave", f"{other}_pages", c["both"], c[f"{other}_facts"])
        m("reader_conflicts", f"textlayer_vs_{other}", c["conflicts"], c["both"] + c["conflicts"])
        report["reader_agreement"][other] = dict(c)
    # evidence rejections
    rej = Counter()
    vals = Counter()
    for v in verified.values():
        for r, pr in v["readers"].items():
            rej[r] += pr["rejected_values"] + pr["rejected_parameters"]
            vals[r] += len(pr["values"]) + len(pr["parameters"]) + pr["rejected_values"] + pr["rejected_parameters"]
    for r in readers:
        m("evidence_rejections", r, rej[r], vals[r])
    report["evidence_rejections"] = {r: {"rejected": rej[r], "readings": vals[r]} for r in readers}
    # coverage: utilities with a headline ARR (not set aside), per year, against those listed
    util = ref_rows()["utilities"]
    report["coverage"] = {}
    for kind, scope in (("discom", "all"), ("transco", "transco")):
        listed = [u["code"] for u in util if u["kind"] == kind]
        years: dict[str, set[str]] = defaultdict(set)
        for v in verified.values():
            for f in v["facts"]:
                if f.get("is_headline") and not f.get("set_aside") and f["utility"] in listed:
                    years[f["fiscal_year"]].add(f["utility"])
        with_any = {u for s_ in years.values() for u in s_}
        m("coverage_utilities", scope, len(with_any), len(listed), {y: sorted(x) for y, x in sorted(years.items())})
        report["coverage"][kind] = {
            "utilities_with_headline": len(with_any),
            "listed": len(listed),
            "by_year": {y: len(x) for y, x in sorted(years.items())},
        }
    # spend and time
    spend = defaultdict(float)
    for r in store.read_jsonl("spend"):
        if r.get("is_real"):
            spend[(r["agent"], r["provider"], r["day"])] += float(r["cost_usd"])
    total = sum(spend.values())
    m(
        "spend_usd",
        "all",
        round(total, 6),
        None,
        {f"{a}/{p}/{d}": round(c, 6) for (a, p, d), c in sorted(spend.items())},
    )
    metrics[-1]["value"] = round(total, 6)
    secs = defaultdict(float)
    nruns = Counter()
    for r in store.read_jsonl("runs"):
        secs[r["agent"]] += float(r.get("seconds", 0))
        nruns[r["agent"]] += 1
    report["seconds_by_agent"] = {a: round(s, 1) for a, s in sorted(secs.items())}
    report["runs_by_agent"] = dict(nruns)
    return metrics, report


def findings(metrics: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prev = {(x["name"], x["scope"]): x for x in previous}
    out = []
    for x in metrics:
        p = prev.get((x["name"], x["scope"]))
        if not p or x["value"] is None or p.get("value") is None:
            continue
        if x["name"] in HIGHER_IS_BETTER and x["value"] < p["value"] - 0.005:
            out.append(
                {
                    "raised_by": "auditor",
                    "severity": "warn",
                    "title": f"{x['name']} ({x['scope']}) fell from {p['value']:.3f} to {x['value']:.3f}",
                    "detail": f"{p.get('numerator')}/{p.get('denominator')} on {p['measured_on']} -> "
                    f"{x['numerator']}/{x['denominator']} on {x['measured_on']}",
                }
            )
        if x["name"] == "evidence_rejections" and x["value"] > p["value"] + 0.005:
            out.append(
                {
                    "raised_by": "auditor",
                    "severity": "info",
                    "title": f"evidence rejections ({x['scope']}) rose from {p['value']:.3f} to {x['value']:.3f}",
                    "detail": f"{p.get('numerator')}/{p.get('denominator')} -> {x['numerator']}/{x['denominator']}",
                }
            )
    return out


def run(orders: list[dict[str, Any]], sink: Sink) -> dict[str, Any]:
    r = Run("auditor", VERSION)
    metrics, report = measure(orders)
    previous = store.read_global("auditor-last", {}).get("metrics", [])
    found = findings(metrics, previous)
    figs = hand_figures()
    gold_rows = [
        {
            "order_sha256": h["sha"],
            "key": h["key"],
            "source": h["source"],
            "page": h["page"],
            "value": h["value"],
            "voice": h["voice"],
            "utility": h["licensee"],
            "what": (h["what"] or "")[:500],
        }
        for h in figs
        if h["sha"]
    ]
    gold_rows = [{k: v for k, v in g.items() if v is not None} for g in gold_rows]
    rows = [{k: v for k, v in x.items() if v is not None} for x in metrics]
    w = sink.post("metrics", rows).written + sink.post("gold_figures", gold_rows).written
    if found:
        w += sink.post("findings", found).written
    store.write_global("auditor-last", {"metrics": metrics, "report": report})
    r.post(sink, "ok", f"{len(metrics)} metrics, {len(gold_rows)} gold figures, {len(found)} findings", rows_written=w)
    report["findings"] = found
    return report
