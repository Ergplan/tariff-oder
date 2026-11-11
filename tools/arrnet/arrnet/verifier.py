"""Verifier — deterministic.

(a) Evidence.  For every value and parameter from every reader: each numeric token of the quote
    must be on that page, and the printed value must be in the quote.  "On the page" means the
    PDF's text layer (Courier's page text) when the page has one, else the reader's own text of
    that page (OCR) — the source is recorded with the check.  A reading that fails is counted
    as a rejection for its reader and is not posted as a value.
(b) Consensus.  Readings of one order are grouped by utility, year, voice and head; within a
    group two readers' readings are the same figure when their values are equal within 0.005 (in
    the printed unit) on the same page or under the same label.  Readings with the same label on
    the same page but different values are one figure in ``conflict``; all candidates are kept.
    Class: single / agreed_2 / agreed_3 / conflict.
(c) Headline and outliers, ported from arrdb.build: per utility, year and voice, the order's main
    summary table and its bottom-line ARR row; a utility's bottom line more than five times above
    or below the median of all its bottom lines is set aside with the reason.

Fixture results (``is_real: false``) are never verified into real output.
"""

from __future__ import annotations

import re
import statistics
from collections import defaultdict
from typing import Any

from . import store

VERSION = "verifier 1"
TOL = 0.005
READER_ORDER = ["textlayer", "docling", "llamaparse", "llm"]
NUM_TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")
SUMMARY_TITLE = re.compile(r"summary|aggregate revenue requirement|approved|admitted|final", re.I)


def _tokens(text: str) -> list[str]:
    return [t.rstrip(",") for t in NUM_TOKEN.findall(text or "")]


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


class PageIndex:
    """Numeric tokens of each page's text layer, built once per order."""

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.has_layer = {p["page"]: p["has_text_layer"] for p in pages}
        self.tokens: dict[int, set[str]] = {}
        self.text = {p["page"]: p["text"] for p in pages}

    def tokens_of(self, page: int, text: str | None = None) -> set[str]:
        if text is not None:
            ts = _tokens(text)
            return set(ts) | {t.replace(",", "") for t in ts}
        if page not in self.tokens:
            ts = _tokens(self.text.get(page, ""))
            self.tokens[page] = set(ts) | {t.replace(",", "") for t in ts}
        return self.tokens[page]


def evidence(item: dict[str, Any], idx: PageIndex, reader_texts: dict[str, str]) -> tuple[bool, str, str | None]:
    """(passes, reason, source) for one reading."""
    page, quote, printed = (
        item.get("page"),
        _ws(str(item.get("quote") or "")),
        _ws(str(item.get("value_printed") or "")),
    )
    if not isinstance(page, int) or page < 1:
        return False, "no page", None
    if not quote:
        return False, "no quote", None
    if page not in idx.has_layer:
        return False, "page not in the order", None
    if idx.has_layer[page]:
        toks, source = idx.tokens_of(page), "text layer"
    elif str(page) in reader_texts:
        toks, source = idx.tokens_of(page, reader_texts[str(page)]), "reader's own page text (OCR)"
    else:
        return False, "page has no text layer and the reader gave no text for it", None
    for t in _tokens(quote):
        if t not in toks and t.replace(",", "") not in toks:
            return False, f"number {t} of the quote is not on page {page} ({source})", source
    if printed not in quote:
        core = _tokens(printed)
        if not core or not all(c in _tokens(quote) for c in core):
            return False, f"value {printed} is not in the quote", source
    return True, "", source


def norm_label(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _results(sha: str, include_fixtures: bool = False) -> list[dict[str, Any]]:
    out = []
    for name in READER_ORDER:
        r = store.read(sha, name)
        if r and r.get("status") in ("ok", "partial") and (r.get("is_real") or include_fixtures):
            out.append(r)
    return out


def primary_keys(values: list[dict[str, Any]]) -> set[tuple]:
    """arrdb.build.headlines' table choice for one reader: per (utility, year, voice), the table
    with a total row, six or more rows, a summary title, the most rows, the latest page."""
    groups: dict[tuple, dict[tuple, list]] = defaultdict(lambda: defaultdict(list))
    for v in values:
        if v.get("utility") and v.get("fiscal_year") and v.get("voice"):
            groups[(v["utility"], v["fiscal_year"], v["voice"])][(v.get("table_page"), v.get("table_title"))].append(v)
    keys = set()
    for g, by_table in groups.items():
        best = max(by_table, key=lambda t: _score(t, by_table[t]))
        keys.add((*best, *g))
    return keys


def _score(tkey: tuple, rows: list[dict[str, Any]]) -> tuple:
    title = (tkey[1] or "").lower()
    has_total = any(r["head"] in ("net_arr", "arr") for r in rows)
    return (has_total, len(rows) >= 6, bool(SUMMARY_TITLE.search(title)), len(rows), rows[0]["page"])


def consensus(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Facts from readings ({reader, reader_version, ...arr_values fields}) of one order."""
    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in readings:
        if r.get("utility") and r.get("fiscal_year") and r.get("voice"):
            buckets[(r["utility"], r["fiscal_year"], r["voice"], r["head"])].append(r)
    rank = {n: i for i, n in enumerate(READER_ORDER)}
    facts = []
    for key, rs in buckets.items():
        rs = sorted(rs, key=lambda r: rank.get(r["reader"], 9))
        clusters: list[dict[str, Any]] = []
        for r in rs:
            nl = norm_label(r["label"])
            best, best_score = None, -1
            for c in clusters:
                if r["reader"] in c["readers"] or abs(c["value"] - r["value"]) > TOL:
                    continue
                same_page, same_label = c["page"] == r["page"], c["nlabel"] == nl
                if not (same_page or same_label):
                    continue
                s = 2 * same_page + same_label
                if s > best_score:
                    best, best_score = c, s
            if best is None:
                clusters.append(
                    {
                        "value": r["value"],
                        "page": r["page"],
                        "nlabel": nl,
                        "readers": {r["reader"]},
                        "agree": [r],
                        "differ": [],
                    }
                )
            else:
                best["readers"].add(r["reader"])
                best["agree"].append(r)
        # same label, same page, different value, no reader in common: one figure in conflict
        merged: set[int] = set()
        for i, a in enumerate(clusters):
            if i in merged:
                continue
            for j in range(i + 1, len(clusters)):
                b = clusters[j]
                if j in merged or a["readers"] & b["readers"]:
                    continue
                if a["page"] == b["page"] and a["nlabel"] == b["nlabel"] and abs(a["value"] - b["value"]) > TOL:
                    a["differ"].extend(b["agree"])
                    a["readers_differ"] = a.get("readers_differ", set()) | b["readers"]
                    merged.add(j)
        for i, c in enumerate(clusters):
            if i in merged:
                continue
            rep = c["agree"][0]
            n = len(c["readers"])
            cls = "conflict" if c["differ"] else ("single" if n == 1 else "agreed_2" if n == 2 else "agreed_3")
            facts.append(
                {
                    "utility": key[0],
                    "fiscal_year": key[1],
                    "voice": key[2],
                    "stage": rep.get("stage"),
                    "head": key[3],
                    "label": rep["label"],
                    "value_crore": rep.get("value_crore"),
                    "value": rep["value"],
                    "unit": rep.get("unit"),
                    "page": rep["page"],
                    "quote": rep["quote"],
                    "consensus": cls,
                    # the readers behind the fact; in a conflict, every reader involved (``readings``
                    # says which gave this value: the application needs two readers for a conflict)
                    "readers": sorted(c["readers"] | {x["reader"] for x in c["differ"]}, key=lambda x: rank.get(x, 9)),
                    "readings": [
                        {
                            "reader": x["reader"],
                            "reader_version": x["reader_version"],
                            "page": x["page"],
                            "value_printed": x["value_printed"],
                            "agrees": ok,
                        }
                        for ok, xs in ((True, c["agree"]), (False, c["differ"]))
                        for x in xs
                    ],
                    "_table": (rep["reader"], rep.get("table_page"), rep.get("table_title")),
                    "_seq": rep.get("_seq", 0),
                }
            )
    return facts


def headlines(facts: list[dict[str, Any]]) -> None:
    """arrdb.build.headlines on facts: the main table per utility / year / voice and its 'net ARR'
    row, else its last ARR / total revenue requirement row."""
    groups: dict[tuple, dict[tuple, list]] = defaultdict(lambda: defaultdict(list))
    for f in facts:
        groups[(f["utility"], f["fiscal_year"], f["voice"])][f["_table"]].append(f)
    for _g, by_table in groups.items():
        best = max(by_table, key=lambda t: _score((t[1], t[2]), sorted(by_table[t], key=lambda f: f["_seq"])))
        trs = sorted(by_table[best], key=lambda f: f["_seq"])
        net = [f for f in trs if f["head"] == "net_arr" and f["value_crore"] is not None]
        tot = [f for f in trs if f["head"] == "arr" and f["value_crore"] is not None]
        title = (best[2] or "")[:90]
        if net:
            pick = net[-1]
            pick["headline_why"] = f"the 'net ARR' row ({pick['label'][:60]}) of {title}, page {pick['page']}"
        elif tot:
            pick = tot[-1]
            pick["headline_why"] = (
                f"the last ARR / total revenue requirement row ({pick['label'][:60]}) of {title}, page {pick['page']}"
            )
        else:
            continue
        pick["is_headline"] = True


def set_aside_outliers(all_facts: list[dict[str, Any]]) -> int:
    """arrdb.build.set_aside_outliers over the headline facts of every order verified together."""
    by: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in all_facts:
        if f.get("is_headline") and f["utility"] != "TOTAL":
            by[f["utility"]].append(f)
    n = 0
    for _u, fs in by.items():
        vals = [f["value_crore"] for f in fs if f["value_crore"] is not None and f["value_crore"] > 0]
        if len(vals) < 3:
            continue
        med = statistics.median(vals)
        for f in fs:
            v = f["value_crore"]
            if v is not None and (v <= 0 or v < med / 5.0 or v > med * 5.0):
                f["set_aside"] = (
                    f"{v:.2f} is more than five times away from the median of this DISCOM's {len(vals)} "
                    f"bottom lines ({med:.2f})"
                )
                n += 1
    return n


def verify_order(order: dict[str, Any], include_fixtures: bool = False) -> dict[str, Any] | None:
    sha = order.get("sha256")
    if not sha:
        return None
    pages = (store.read(sha, "pages") or {}).get("pages")
    if pages is None:
        return None
    idx = PageIndex(pages)
    results = _results(sha, include_fixtures)
    readings: list[dict[str, Any]] = []
    per_reader: dict[str, dict[str, Any]] = {}
    rejections: list[dict[str, Any]] = []
    seq = 0
    for r in results:
        name, ver = r["reader"], r["reader_version"]
        texts = r.get("page_texts") or {}
        ok_values, ok_params = [], []
        srcs: dict[str, int] = defaultdict(int)
        for kind, items, keep in (("value", r["values"], ok_values), ("parameter", r.get("parameters", []), ok_params)):
            for v in items:
                passed, why, src = evidence(v, idx, texts)
                if passed:
                    srcs[src] += 1
                    keep.append(v)
                else:
                    rejections.append(
                        {
                            "order_url": order["url"],
                            "reader": name,
                            "kind": kind,
                            "page": v.get("page"),
                            "label": v.get("label"),
                            "value_printed": v.get("value_printed"),
                            "reason": why,
                        }
                    )
        prim = primary_keys(ok_values)
        for v in ok_values:
            v["is_primary"] = (
                v.get("table_page"),
                v.get("table_title"),
                v.get("utility"),
                v.get("fiscal_year"),
                v.get("voice"),
            ) in prim
            seq += 1
            readings.append({**v, "reader": name, "reader_version": ver, "_seq": seq})
        per_reader[name] = {
            "reader_version": ver,
            "values": ok_values,
            "parameters": ok_params,
            "tables": r["tables"],
            "rejected_values": sum(1 for x in rejections if x["reader"] == name and x["kind"] == "value"),
            "rejected_parameters": sum(1 for x in rejections if x["reader"] == name and x["kind"] == "parameter"),
            "evidence_sources": dict(srcs),
            "pages": r.get("pages") or [],
            "parse": {
                k: r.get(k) for k in ("status", "provider", "model", "is_real", "pages_parsed", "cost_usd", "note")
            },
        }
    facts = consensus(readings)
    headlines(facts)
    # the facts' natural key (utility, year, voice, head, label, page) holds one figure: the same
    # figure printed in two tables of a page is one fact; two columns of one voice in a table (an
    # "MTR order" and a "revised" column both read as approved) cannot both be facts — the first
    # (a headline first) is kept and the others stay as readings in arr_values, counted here
    seen: dict[tuple, float] = {}
    unique, dup_same, dup_diff = [], 0, 0
    for f in sorted(facts, key=lambda f: (not f.get("is_headline"), f["_seq"])):
        k = (f["utility"], f["fiscal_year"], f["voice"], f["head"], f["label"], f["page"])
        if k in seen:
            if abs(seen[k] - f["value"]) <= TOL:
                dup_same += 1
            else:
                dup_diff += 1
            continue
        seen[k] = f["value"]
        unique.append(f)
    unique.sort(key=lambda f: f["_seq"])
    return {
        "order": {k: order.get(k) for k in ("url", "sha256", "commission", "arr_year")},
        "readers": per_reader,
        "facts": unique,
        "duplicate_fact_keys": dup_same + dup_diff,
        "duplicate_same_value": dup_same,
        "duplicate_other_value": dup_diff,
        "rejections": rejections,
    }


def fact_row(order_url: str, f: dict[str, Any]) -> dict[str, Any]:
    row = {k: v for k, v in f.items() if not k.startswith("_")}
    row["order_url"] = order_url
    row.setdefault("is_headline", False)
    return {k: v for k, v in row.items() if v is not None}


def post_order(sink, result: dict[str, Any]) -> dict[str, int]:
    """Post one order's verified rows: per parse its tables (the first row replacing the parse's
    earlier rows), its values and parameters; then the order's facts (replacing the facts no
    person has reviewed)."""
    url = result["order"]["url"]
    n = {"written": 0, "rejected": 0}

    def post(kind: str, rows: list[dict[str, Any]]) -> None:
        if rows:
            res = sink.post(kind, rows)
            n["written"] += res.written
            n["rejected"] += len(res.rejected)
            if res.rejected:
                store.append_jsonl("api_rejections", [{"kind": kind, **x} for x in res.rejected])

    for name, pr in result["readers"].items():
        base = {"order_url": url, "reader": name, "reader_version": pr["reader_version"]}
        parse = {k: v for k, v in pr["parse"].items() if v is not None}
        post("parses", [{**base, **parse, "cost_usd": round(float(parse.get("cost_usd") or 0), 6)}])
        tables = [{**base, **t} for t in pr["tables"]]
        values = [{**base, **{k: v for k, v in x.items() if not k.startswith("_")}} for x in pr["values"]]
        params = [{**base, **x} for x in pr["parameters"]]
        values = [{k: v for k, v in x.items() if v is not None} for x in values]
        first = tables or values or params
        if first:
            first[0]["replace"] = True
        post("parsed_tables", tables)
        post("arr_values", values)
        post("parameters", params)
    facts = [fact_row(url, f) for f in result["facts"]]
    if facts:
        facts[0]["replace_order"] = True
    post("facts", facts)
    return n
