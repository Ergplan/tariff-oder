"""Build the ARR database (SQLite) from the downloaded orders.

Every value row carries its order, page and the line as printed.  Nothing is reviewed: the
database says what the reader found where, and how it read each column (from the header, the
title, or the sentence above the table).  A value whose unit the order does not print near the
table is kept with ``value_crore`` NULL rather than guessed.

    uv run python -m arrdb.build --orders orders.json [--orders more.json] --cache DIR --out arr.sqlite
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any

from .heads import HEAD_NAMES
from .reader import read_tables, years_in

HERE = Path(__file__).resolve().parent.parent
READER_VERSION = "arrdb-reader 1"

SCHEMA = """
CREATE TABLE commissions (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL, website TEXT,
  website_reachable INTEGER NOT NULL      -- 1 if this build could reach the site, 0 if not
);
CREATE TABLE discoms (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, commission TEXT NOT NULL REFERENCES commissions(code),
  state TEXT NOT NULL, ownership TEXT NOT NULL,  -- state, private, municipal
  aliases TEXT NOT NULL DEFAULT '[]'             -- JSON: other names orders and readers use
);
CREATE TABLE heads (code TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE orders (
  order_id INTEGER PRIMARY KEY, commission TEXT NOT NULL REFERENCES commissions(code),
  title TEXT NOT NULL,                     -- as the commission's website lists it
  url TEXT NOT NULL, sha256 TEXT, pages INTEGER, pages_without_text INTEGER,
  arr_year TEXT,                           -- the year whose ARR the order approves (FY2026-27)
  years_decided TEXT,                      -- every year the title says it decides, comma-separated
  kind TEXT, listing TEXT, found_by TEXT, fetched_on TEXT,
  read_status TEXT NOT NULL                -- read, no_tables_found, no_text_layer, not_downloaded
);
CREATE TABLE order_discoms (order_id INTEGER REFERENCES orders(order_id), discom TEXT REFERENCES discoms(code));
CREATE TABLE arr_tables (
  table_id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL REFERENCES orders(order_id),
  title TEXT NOT NULL, page INTEGER NOT NULL, pages TEXT NOT NULL,
  unit TEXT, unit_from TEXT, columns_json TEXT NOT NULL
);
CREATE TABLE arr_values (
  value_id INTEGER PRIMARY KEY,
  table_id INTEGER NOT NULL REFERENCES arr_tables(table_id),
  order_id INTEGER NOT NULL REFERENCES orders(order_id),
  discom TEXT,                             -- a discom code, TOTAL (state total), or NULL (not printed)
  fiscal_year TEXT,                        -- FY2026-27, or NULL when the table does not say
  voice TEXT,                              -- claimed, approved, approved_earlier, actual, or NULL
  stage TEXT,                              -- ARR, APR, True-up, MYT projection (year vs the order's ARR year)
  head TEXT NOT NULL REFERENCES heads(code),
  label TEXT NOT NULL,                     -- the row label as printed
  group_label TEXT,                        -- a heading row above it, if any
  value_printed TEXT NOT NULL, value REAL NOT NULL,
  unit TEXT, value_crore REAL,             -- NULL when the unit is not printed
  page INTEGER NOT NULL, quote TEXT NOT NULL,
  column_header TEXT, year_from TEXT, voice_from TEXT,
  is_primary INTEGER NOT NULL DEFAULT 0    -- 1: from the order's main table for this discom/year/voice
);
CREATE TABLE arr_headline (
  order_id INTEGER NOT NULL REFERENCES orders(order_id), discom TEXT NOT NULL, fiscal_year TEXT NOT NULL,
  voice TEXT NOT NULL, stage TEXT, value_crore REAL, value_id INTEGER REFERENCES arr_values(value_id),
  why TEXT NOT NULL,
  set_aside TEXT                           -- why this bottom line is not used (NULL: it is used)
);
CREATE TABLE build_info (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX v_lookup ON arr_values(discom, fiscal_year, voice, head);

-- One row per value with everything a question needs; the view queries should use.
CREATE VIEW v_values AS
SELECT v.value_id, v.discom, d.name AS discom_name, c.state, c.code AS commission,
       d.ownership, v.fiscal_year, v.voice, v.stage, v.head, h.name AS head_name, v.label,
       v.value_crore, v.value_printed, v.unit, v.page, v.quote, t.title AS table_title,
       o.order_id, o.title AS order_title, o.url AS order_url, o.arr_year AS order_arr_year,
       v.is_primary, v.column_header, v.year_from, v.voice_from
FROM arr_values v
JOIN arr_tables t ON t.table_id = v.table_id
JOIN orders o ON o.order_id = v.order_id
LEFT JOIN discoms d ON d.code = v.discom
LEFT JOIN commissions c ON c.code = o.commission
JOIN heads h ON h.code = v.head;

-- The bottom-line ARR per order, discom, year and voice.
CREATE VIEW v_arr AS
SELECT a.discom, d.name AS discom_name, c.state, o.commission, d.ownership, a.fiscal_year, a.voice,
       a.stage, a.value_crore AS arr_crore, v.label, v.page, v.quote, t.title AS table_title,
       o.order_id, o.title AS order_title, o.url AS order_url, o.arr_year AS order_arr_year, a.why,
       a.value_id, 1 AS is_primary
FROM arr_headline a
JOIN orders o ON o.order_id = a.order_id
LEFT JOIN discoms d ON d.code = a.discom
JOIN commissions c ON c.code = o.commission
LEFT JOIN arr_values v ON v.value_id = a.value_id
LEFT JOIN arr_tables t ON t.table_id = v.table_id
WHERE a.set_aside IS NULL;

-- The latest decision on each year: approved values from the newest order that approves it
-- (a true-up supersedes the APR, which supersedes the ARR approval).
CREATE VIEW v_latest_approved AS
SELECT x.* FROM v_values x
WHERE x.voice = 'approved' AND x.is_primary = 1 AND x.order_arr_year = (
  SELECT MAX(y.order_arr_year) FROM v_values y
  WHERE y.voice = 'approved' AND y.is_primary = 1 AND y.discom = x.discom AND y.fiscal_year = x.fiscal_year);
"""


def fy_start(y: str | None) -> int | None:
    return int(y[2:6]) if y else None


def stage_of(fy: str | None, arr_year: str | None) -> str | None:
    if not fy or not arr_year:
        return None
    d = fy_start(fy) - fy_start(arr_year)
    if d == 0:
        return "ARR"
    if d == -1:
        return "APR"
    if d < -1:
        return "True-up"
    return "MYT projection"


def arr_year_of(o: dict[str, Any]) -> str | None:
    """The year whose ARR the order approves: given, or from what discovery read in the title
    (the first year it approves), or from the title: the first year of a control period, else
    the year named after "ARR / tariff for", else the latest year the title names."""
    if o.get("arr_year"):
        return o["arr_year"]
    approved = [d["fy"] for d in o.get("decides") or [] if d.get("value_type") == "approved" and d.get("fy")]
    if approved:
        return min(approved)
    title = o.get("title", "")
    m = re.search(r"(control period|multi[- ]year|myt)[^.]{0,80}?((?:fy\s*)?20\d\d\s*[-–]\s*\d\d)", title, re.I)
    if m and years_in(m.group(2)):
        return years_in(m.group(2))[0]
    m = re.search(
        r"(?:arr|tariff|revenue requirement)[^.]{0,60}?for (?:the )?((?:fy\s*)?20\d\d\s*[-–]\s*\d\d)", title, re.I
    )
    if m and years_in(m.group(1)):
        return years_in(m.group(1))[0]
    ys = years_in(title) or sorted(o.get("years") or [])
    return max(ys) if ys else None


def infer_units(tables: list[dict[str, Any]]) -> None:
    """A table without a printed unit takes the unit of another table of the same order that
    prints three or more of the same figures (OERC's Table 82 and its Rs crore Table 83).
    Small or round numbers are not evidence; a table with no such match keeps no unit."""

    def distinctive(v: float) -> bool:
        return abs(v) >= 100 and round(v, 2) != round(v)

    known: dict[float, tuple[str, float, str]] = {}
    for t in tables:
        if t["unit"]:
            for ln in t["lines"]:
                if distinctive(ln["value"]):
                    known.setdefault(ln["value"], (t["unit"], t["factor"], t["title"]))
    for t in tables:
        if t["unit"]:
            t["unit_from"] = "printed with the table"
            continue
        hits = [known[ln["value"]] for ln in t["lines"] if distinctive(ln["value"]) and ln["value"] in known]
        if len(hits) >= 3 and len({h[0] for h in hits}) == 1:
            t["unit"], t["factor"] = hits[0][0], hits[0][1]
            src = sorted({h[2] for h in hits})[0]
            t["unit_from"] = f"not printed; {len(hits)} of its figures are printed in {hits[0][0]} in {src[:80]}"
        else:
            t["unit_from"] = None


def build(orders: list[dict[str, Any]], cache: Path, out: Path, log: list[str]) -> dict[str, int]:
    reg = json.loads((HERE / "registry.json").read_text())
    if out.exists():
        out.unlink()
    db = sqlite3.connect(out)
    db.executescript(SCHEMA)
    states = {c["code"]: c["state"] for c in reg["commissions"]}
    db.executemany(
        "INSERT INTO commissions VALUES (?,?,?,?,?)",
        [(c["code"], c["name"], c["state"], c["website"], int(c["website_reachable"])) for c in reg["commissions"]],
    )
    db.executemany(
        "INSERT INTO discoms VALUES (?,?,?,?,?,?)",
        [
            (
                d["code"],
                d["name"],
                d["commission"],
                states[d["commission"]],
                d["ownership"],
                json.dumps(d.get("aliases", []), ensure_ascii=False),
            )
            for d in reg["discoms"]
        ],
    )
    db.executemany("INSERT INTO heads VALUES (?,?)", list(HEAD_NAMES.items()))
    aliases = {d["code"]: d["aliases"] for d in reg["discoms"]}
    seen_sha: set[str] = set()
    counts = defaultdict(int)
    for o in orders:
        sha = o.get("sha256")
        path = cache / f"{sha}.pdf" if sha else None
        status = "not_downloaded"
        ay = arr_year_of(o)
        if sha and sha in seen_sha:
            log.append(f"skip duplicate file {sha[:12]} ({o['title'][:60]})")
            continue
        cur = db.execute(
            "INSERT INTO orders (commission,title,url,sha256,arr_year,years_decided,kind,listing,found_by,"
            "fetched_on,read_status) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                o["commission"],
                o["title"],
                o["url"],
                sha,
                ay,
                ",".join(o.get("years") or []),
                str(o.get("kind")),
                o.get("listing"),
                o.get("found_by"),
                o.get("fetched_on"),
                status,
            ),
        )
        oid = cur.lastrowid
        lic = [x for x in o.get("licensees", [])]
        db.executemany("INSERT INTO order_discoms VALUES (?,?)", [(oid, x) for x in lic])
        counts["orders"] += 1
        if not path or not path.exists():
            continue
        seen_sha.add(sha)
        try:
            res = read_tables(str(path), lic, {k: aliases.get(k, []) for k in lic})
        except Exception as e:  # a damaged PDF is reported, not fatal
            log.append(f"order {oid}: could not be read ({type(e).__name__}: {e})")
            db.execute("UPDATE orders SET read_status='unreadable' WHERE order_id=?", (oid,))
            continue
        tables = res["tables"]
        infer_units(tables)
        status = (
            "read"
            if tables
            else ("no_text_layer" if res["pages_without_text"] > 0.5 * res["pages"] else "no_tables_found")
        )
        db.execute(
            "UPDATE orders SET pages=?, pages_without_text=?, read_status=? WHERE order_id=?",
            (res["pages"], res["pages_without_text"], status, oid),
        )
        counts[f"orders_{status}"] += 1
        for t in tables:
            cur = db.execute(
                "INSERT INTO arr_tables (order_id,title,page,pages,unit,unit_from,columns_json) VALUES (?,?,?,?,?,?,?)",
                (
                    oid,
                    t["title"],
                    t["page"],
                    ",".join(map(str, t["pages"])),
                    t["unit"],
                    t.get("unit_from"),
                    json.dumps(t["columns"], ensure_ascii=False),
                ),
            )
            tid = cur.lastrowid
            cols = {c["index"]: c for c in t["columns"]}
            for ln in t["lines"]:
                c = cols.get(ln["column"])
                if c is None:
                    continue
                fy = ln.get("row_year") or c["fiscal_year"]
                voice = ln.get("row_voice") or c["voice"]
                vc = round(ln["value"] * t["factor"], 4) if t["factor"] else None
                db.execute(
                    "INSERT INTO arr_values (table_id,order_id,discom,fiscal_year,voice,stage,head,label,group_label,"
                    "value_printed,value,unit,value_crore,page,quote,column_header,year_from,voice_from)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        tid,
                        oid,
                        c["licensee"],
                        fy,
                        voice,
                        stage_of(fy, ay),
                        ln["head"],
                        ln["label"],
                        ln.get("group"),
                        ln["value_printed"],
                        ln["value"],
                        t["unit"],
                        vc,
                        ln["page"],
                        ln["quote"],
                        c["header"],
                        "row label" if ln.get("row_year") else c.get("year_from"),
                        "row label" if ln.get("row_voice") else c.get("voice_from"),
                    ),
                )
                counts["values"] += 1
        headlines(db, oid, ay)
    set_aside_outliers(db)
    db.execute("INSERT INTO build_info VALUES ('reader', ?)", (READER_VERSION,))
    db.execute("INSERT INTO build_info VALUES ('built_on', ?)", (dt.date.today().isoformat(),))
    db.execute("INSERT INTO build_info VALUES ('orders_read', ?)", (str(counts.get("orders_read", 0)),))
    db.execute(
        "INSERT INTO build_info VALUES ('status', ?)",
        ("machine-read from the orders' text layers; not reviewed by a person",),
    )
    db.commit()
    db.execute("VACUUM")
    db.close()
    return dict(counts)


def headlines(db: sqlite3.Connection, oid: int, arr_year: str | None) -> None:
    """Choose, per discom / year / voice, the order's main summary table and its bottom-line ARR row."""
    rows = db.execute(
        "SELECT v.value_id, v.table_id, v.discom, v.fiscal_year, v.voice, v.head, v.label, v.value_crore,"
        " t.title, v.page, (SELECT COUNT(*) FROM arr_values w WHERE w.table_id = v.table_id AND w.discom IS v.discom"
        "  AND w.fiscal_year IS v.fiscal_year AND w.voice IS v.voice) AS n"
        " FROM arr_values v JOIN arr_tables t ON t.table_id = v.table_id WHERE v.order_id = ?",
        (oid,),
    ).fetchall()
    groups: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r[2] and r[3] and r[4]:
            groups[(r[2], r[3], r[4])].append(r)
    for (discom, fy, voice), rs in groups.items():
        by_table: dict[int, list] = defaultdict(list)
        for r in rs:
            by_table[r[1]].append(r)

        def score(tid: int, by_table: dict[int, list] = by_table) -> tuple:
            trs = by_table[tid]
            title = trs[0][8].lower()
            has_total = any(r[5] in ("net_arr", "arr") for r in trs)
            summary = bool(re.search(r"summary|aggregate revenue requirement|approved|admitted|final", title))
            return (has_total, len(trs) >= 6, summary, len(trs), trs[0][9])

        best = max(by_table, key=score)
        db.execute(
            "UPDATE arr_values SET is_primary = 1 WHERE table_id = ? AND discom = ? AND fiscal_year = ? AND voice = ?",
            (best, discom, fy, voice),
        )
        trs = by_table[best]
        net = [r for r in trs if r[5] == "net_arr" and r[7] is not None]
        tot = [r for r in trs if r[5] == "arr" and r[7] is not None]
        pick, why = None, ""
        if net:
            pick = net[-1]
            why = f"the 'net ARR' row ({pick[6][:60]}) of {pick[8][:90]}, page {pick[9]}"
        elif tot:
            pick = tot[-1]
            why = f"the last ARR / total revenue requirement row ({pick[6][:60]}) of {pick[8][:90]}, page {pick[9]}"
        if pick:
            db.execute(
                "INSERT INTO arr_headline VALUES (?,?,?,?,?,?,?,?,NULL)",
                (oid, discom, fy, voice, stage_of(fy, arr_year), pick[7], pick[0], why),
            )


def set_aside_outliers(db: sqlite3.Connection) -> None:
    """A DISCOM's bottom line more than five times above or below the median of all its bottom
    lines is almost always another entity's table (a generation company's, in a combined order)
    or a unit misread: it is set aside with the reason, and kept for a person to look at."""
    import statistics

    for (discom,) in db.execute("SELECT DISTINCT discom FROM arr_headline WHERE discom <> 'TOTAL'").fetchall():
        vals = [
            v
            for (v,) in db.execute(
                "SELECT value_crore FROM arr_headline WHERE discom = ? AND value_crore > 0", (discom,)
            )
        ]
        if len(vals) < 3:
            continue
        med = statistics.median(vals)
        db.execute(
            "UPDATE arr_headline SET set_aside = printf('%.2f is more than five times away from the median of this "
            "DISCOM''s %d bottom lines (%.2f)', value_crore, ?, ?) WHERE discom = ? AND (value_crore <= 0 OR "
            "value_crore < ? / 5.0 OR value_crore > ? * 5.0)",
            (len(vals), med, discom, med, med),
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", action="append", required=True)
    ap.add_argument("--cache", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--log")
    a = ap.parse_args()
    orders: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in a.orders:
        for o in json.loads(Path(f).read_text()):
            if o["url"] not in seen:
                seen.add(o["url"])
                orders.append(o)
    log: list[str] = []
    counts = build(orders, Path(a.cache), Path(a.out), log)
    print(json.dumps(counts, indent=1))
    if a.log:
        Path(a.log).write_text("\n".join(log) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
