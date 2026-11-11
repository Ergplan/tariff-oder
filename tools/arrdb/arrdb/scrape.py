"""Collect the DISCOM tariff orders found by discovery and download them.

Input: the discovery runs (``tariff-api library-discover --registry`` output, one JSON per
commission) and, optionally, a hand-collected list of order URLs for commissions that have no
discovery profile yet (``extra-sites.json``).  Output: ``orders.json`` — one entry per order URL
with what the website said about it (title, listing, licensees, years) and what downloading it
found (HTTP status, SHA-256, pages, size), never anything inferred about its figures.

    uv run python -m arrdb.scrape --discovery DIR [--extra FILE] --cache DIR --out orders.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

HERE = Path(__file__).resolve().parent.parent
KINDS = {"tariff_order", "arr_true_up_order", "myt_order", "mid_term_review"}
SKIP_TITLE = re.compile(
    r"hindi|scanned|rate schedule|business plan|generic|renewable energy|green energy|open access|"
    r"cross subsidy surcharge|revision of tariff for domestic|supplementary|corrigendum$",
    re.I,
)


def registry() -> dict[str, Any]:
    return json.loads((HERE / "registry.json").read_text())


def collect(discovery_dir: str, extra: str | None, since: str = "FY2022-23") -> list[dict[str, Any]]:
    codes = {d["code"] for d in registry()["discoms"]}
    by: dict[str, dict[str, Any]] = {}
    for f in sorted(glob.glob(str(Path(discovery_dir) / "*.json"))):
        comm = Path(f).stem
        if comm == "extra-sites":
            continue
        run = json.loads(Path(f).read_text())
        for p in run.get("proposals", []):
            if p.get("utility_code") not in codes or str(p.get("document_kind")) not in KINDS:
                continue
            title = p.get("title") or ""
            if SKIP_TITLE.search(title):
                continue
            o = by.setdefault(
                p["url"],
                {
                    "url": p["url"],
                    "commission": comm,
                    "title": title,
                    "kind": p["document_kind"],
                    "listing": p.get("listing"),
                    "licensees": [],
                    "years": [],
                    "decides": p.get("decides") or [],
                    "found_by": f"discovery profile {run['profile']['id']} v{run['profile']['version']}",
                },
            )
            if p["utility_code"] not in o["licensees"]:
                o["licensees"].append(p["utility_code"])
            for y in p.get("years") or []:
                if y not in o["years"]:
                    o["years"].append(y)
    if extra and Path(extra).exists():
        from .reader import years_in

        names = {d["name"].lower(): d["code"] for d in registry()["discoms"]}
        names.update({a.lower(): d["code"] for d in registry()["discoms"] for a in d.get("listing_names", [])})
        ex = json.loads(Path(extra).read_text())
        for site in ex.get("sites", []):
            for o in site.get("orders", []):
                if o.get("http") not in (200, 206, None):
                    continue
                if re.search(r"review|corrigendum", str(o.get("kind") or ""), re.I):
                    continue
                lic = [x if x in codes else names.get(x.lower()) for x in o.get("licensees", [])]
                lic = [x for x in lic if x]
                if not lic or SKIP_TITLE.search(o.get("title", "")):
                    continue
                ys = years_in(str(o.get("fiscal_year_of_arr") or ""))
                by.setdefault(
                    o["url"],
                    {
                        "url": o["url"],
                        "commission": site["commission"],
                        "title": o.get("title", ""),
                        "kind": o.get("kind") or "tariff_order",
                        "listing": ", ".join(site.get("listing_urls", [])[:1]),
                        "licensees": lic,
                        "years": ys,
                        "decides": [],
                        "found_by": f"listing page read on {ex.get('checked_on')} (no discovery profile yet)",
                    },
                )
    known = HERE / "known-orders.json"
    if known.exists():
        for o in json.loads(known.read_text())["orders"]:
            by.setdefault(o["url"], dict(o))
    out = [o for o in by.values() if not o["years"] or max(o["years"]) >= since]
    for o in out:
        o["years"].sort()
    return out


def download(o: dict[str, Any], cache: Path) -> dict[str, Any]:
    key = hashlib.sha256(o["url"].encode()).hexdigest()[:16]
    meta = cache / f"{key}.json"
    if meta.exists():
        m = json.loads(meta.read_text())
        if m.get("sha256") and (cache / f"{m['sha256']}.pdf").exists():
            return m
    m: dict[str, Any] = {"http": None, "error": None}
    for attempt in range(3):
        try:
            with httpx.Client(
                follow_redirects=True, timeout=180, headers={"User-Agent": "Mozilla/5.0 (compatible; arr-database/0.1)"}
            ) as c:
                r = c.get(o["url"])
            m["http"] = r.status_code
            if r.status_code != 200:
                m["error"] = f"HTTP {r.status_code}"
                break
            data = r.content
            if not data.startswith(b"%PDF"):
                m["error"] = f"not a PDF ({r.headers.get('content-type')})"
                break
            sha = hashlib.sha256(data).hexdigest()
            (cache / f"{sha}.pdf").write_bytes(data)
            m.update({"sha256": sha, "bytes": len(data), "error": None, "fetched_on": dt.date.today().isoformat()})
            break
        except httpx.HTTPError as e:
            m["error"] = f"{type(e).__name__}: {e}"[:200]
            time.sleep(4 * (attempt + 1))
    meta.write_text(json.dumps(m))
    return m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery", required=True)
    ap.add_argument("--extra")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="FY2022-23")
    a = ap.parse_args()
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    orders = collect(a.discovery, a.extra, a.since)
    print(f"{len(orders)} orders to fetch")
    for i, o in enumerate(orders, 1):
        m = download(o, cache)
        o.update({k: m.get(k) for k in ("http", "error", "sha256", "bytes", "fetched_on")})
        print(f"[{i}/{len(orders)}] {o['commission']} {o['title'][:60]!r}: {m.get('error') or m.get('bytes')}")
    Path(a.out).write_text(json.dumps(orders, indent=1, ensure_ascii=False) + "\n")
    ok = sum(1 for o in orders if o.get("sha256"))
    print(f"{ok} of {len(orders)} downloaded; written to {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
