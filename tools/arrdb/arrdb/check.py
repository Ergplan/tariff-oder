"""Measure the reader against figures read by hand from the same orders.

The order-reproduction packages (``packages/order-reproductions``, ``packages/reference-filings``)
hold figures a person read row by row from these orders, each with its page and quote.  For
every hand-read figure on a page the reader also read, this asks: did the reader find the same
number on that page, and did it give it the same voice (claimed / approved) and licensee where
the hand-read key says so?  It reports counts, never adjusts the database.

    uv run python -m arrdb.check --db arr.sqlite --repo ../.. [--out check.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

VOICE_KEY = {
    "claimed": "claimed",
    "claim": "claimed",
    "petition": "claimed",
    "proposed": "claimed",
    "approved": "approved",
    "admitted": "approved",
    "now": "approved",
    "trued": "approved",
    "myt": "approved_earlier",
    "mytorder": "approved_earlier",
    "to": "approved_earlier",
    "order": "approved_earlier",
}
LIC_KEY = {
    "east": "MPPaKVVCL",
    "west": "MPPKVVCL",
    "central": "MPMKVVCL",
    "state": "TOTAL",
    "tpcodl": "TPCODL",
    "tpwodl": "TPWODL",
    "tpsodl": "TPSODL",
    "tpnodl": "TPNODL",
    "nbpdcl": "NBPDCL",
    "sbpdcl": "SBPDCL",
}


def hand_figures(repo: Path):
    for f in sorted(
        glob.glob(str(repo / "packages/order-reproductions/*/order/*.json"))
        + glob.glob(str(repo / "packages/reference-filings/*/order/*.json"))
    ):
        d = json.loads(Path(f).read_text())
        sha = (d.get("document") or {}).get("sha256")
        for key, fig in (d.get("figures") or {}).items():
            if not isinstance(fig, dict) or "value" not in fig or "page" not in fig:
                continue
            try:
                v = float(str(fig["value"]).replace(",", ""))
            except ValueError:
                continue
            parts = re.split(r"[._]", key.lower())
            yield {
                "file": f,
                "key": key,
                "sha": sha,
                "page": int(fig["page"]),
                "value": v,
                "voice": next((VOICE_KEY[p] for p in reversed(parts) if p in VOICE_KEY), None),
                "licensee": next((LIC_KEY[p] for p in parts if p in LIC_KEY), None),
                "what": fig.get("what", ""),
            }


def cross_order(db: sqlite3.Connection) -> dict:
    """Two reads of one printed decision: an order's approval of a year, and the same approval
    quoted in a later order ("approved in the tariff order", "MYT order").  Both are read by the
    reader independently, from different PDFs and layouts; when a DISCOM, year and head carry an
    equal figure in both, the year, DISCOM and voice of both columns were read consistently."""
    pairs = db.execute(
        """
        WITH a AS (SELECT v.discom, v.fiscal_year, v.head, v.value_crore, o.arr_year, o.commission
                   FROM arr_values v JOIN orders o USING (order_id)
                   WHERE v.voice = 'approved' AND v.is_primary = 1 AND v.head NOT IN ('other')
                     AND v.discom IS NOT NULL AND v.discom <> 'TOTAL' AND v.value_crore IS NOT NULL
                     AND v.fiscal_year = o.arr_year),
             b AS (SELECT v.discom, v.fiscal_year, v.head, v.value_crore, o.arr_year
                   FROM arr_values v JOIN orders o USING (order_id)
                   WHERE v.voice = 'approved_earlier' AND v.head NOT IN ('other')
                     AND v.discom IS NOT NULL AND v.discom <> 'TOTAL' AND v.value_crore IS NOT NULL)
        SELECT a.commission, a.discom, a.fiscal_year, a.head,
               MAX(CASE WHEN EXISTS (SELECT 1 FROM a a2 WHERE a2.discom = a.discom AND a2.fiscal_year = a.fiscal_year
                                       AND a2.head = a.head AND abs(a2.value_crore - b.value_crore) < 0.006)
                        THEN 1 ELSE 0 END) AS agrees
        FROM a JOIN b ON b.discom = a.discom AND b.fiscal_year = a.fiscal_year AND b.head = a.head
                     AND b.arr_year > a.arr_year
        GROUP BY a.commission, a.discom, a.fiscal_year, a.head
        """
    ).fetchall()
    by: dict[str, list[int]] = {}
    for comm, _d, _y, _h, ok in pairs:
        by.setdefault(comm, [0, 0])
        by[comm][0] += 1
        by[comm][1] += ok
    return {
        "pairs": len(pairs),
        "agree": sum(p[4] for p in pairs),
        "by_commission": {k: {"pairs": v[0], "agree": v[1]} for k, v in sorted(by.items())},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out")
    ap.add_argument("--write", action="store_true", help="store the summary in the database's build_info")
    a = ap.parse_args()
    db = sqlite3.connect(a.db)
    sha_to_order = {sha: oid for oid, sha in db.execute("SELECT order_id, sha256 FROM orders WHERE sha256 IS NOT NULL")}
    read_pages = {(oid, p) for oid, p in db.execute("SELECT DISTINCT order_id, page FROM arr_values")}
    tables: dict[int, set[str]] = {}
    for oid, title in db.execute("SELECT order_id, title FROM arr_tables"):
        m = re.match(r"table\s*[-–:.]*\s*([\d.\-]+\d)", title, re.I)
        if m:
            tables.setdefault(oid, set()).add(m.group(1))
    c = Counter()
    misses, wrong = [], []
    measured: set[int] = set()
    for h in hand_figures(Path(a.repo)):
        oid = sha_to_order.get(h["sha"])
        if oid is None:
            c["order_not_in_db"] += 1
            continue
        m = re.search(r"table\s*([\d.\-]+\d)", h["what"], re.I)
        if not m or m.group(1) not in tables.get(oid, set()):
            c["not_in_a_table_the_reader_read"] += 1
            continue
        if (oid, h["page"]) not in read_pages:
            c["table_read_but_page_not"] += 1
            misses.append({k: h[k] for k in ("key", "page", "value", "what")})
            continue
        c["comparable"] += 1
        measured.add(oid)
        if h["value"] == 0:
            c["zero_skipped"] += 1  # a nil printed as a dash is not stored as a value
            continue
        rows = db.execute(
            "SELECT voice, discom, label FROM arr_values WHERE order_id=? AND page=? AND abs(value - ?) < 0.006",
            (oid, h["page"], abs(h["value"])),
        ).fetchall()
        rows += db.execute(
            "SELECT voice, discom, label FROM arr_values WHERE order_id=? AND page=? AND abs(value + ?) < 0.006",
            (oid, h["page"], abs(h["value"])),
        ).fetchall()
        if not rows:
            c["value_not_found"] += 1
            misses.append({k: h[k] for k in ("key", "page", "value", "what")})
            continue
        c["value_found"] += 1
        if h["voice"]:
            c["voice_checked"] += 1
            if any(r[0] == h["voice"] for r in rows):
                c["voice_agrees"] += 1
            else:
                wrong.append(
                    {
                        "key": h["key"],
                        "page": h["page"],
                        "value": h["value"],
                        "expected_voice": h["voice"],
                        "read": [r[0] for r in rows],
                        "what": h["what"],
                    }
                )
        if h["licensee"]:
            c["licensee_checked"] += 1
            if any(r[1] == h["licensee"] for r in rows):
                c["licensee_agrees"] += 1
            else:
                wrong.append(
                    {
                        "key": h["key"],
                        "page": h["page"],
                        "value": h["value"],
                        "expected_licensee": h["licensee"],
                        "read": [r[1] for r in rows],
                        "what": h["what"],
                    }
                )
    report = {"counts": dict(c), "missed": misses, "disagreements": wrong}
    summary = {
        "orders_measured": len(measured),
        "comparable_nonzero": c["comparable"] - c["zero_skipped"],
        "found": c["value_found"],
        "voice_checked": c["voice_checked"],
        "voice_agrees": c["voice_agrees"],
        "licensee_checked": c["licensee_checked"],
        "licensee_agrees": c["licensee_agrees"],
    }
    report["summary"] = summary
    summary["cross_order"] = cross_order(db)
    print("cross-order:", json.dumps(summary["cross_order"]))
    if a.write:
        db.execute("INSERT OR REPLACE INTO build_info VALUES ('check', ?)", (json.dumps(summary),))
        db.commit()
    print(json.dumps(report["counts"], indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
