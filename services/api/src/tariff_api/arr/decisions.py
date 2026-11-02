"""The Commission's decisions on a petition, line by line (R-TU-5, R-TU-1).

A tariff order summarises each proceeding in a table — for a true-up, the figure approved in the
earlier order, the figure claimed and the figure now approved.  This module reads such a table from
the order's text layer (PyMuPDF; untrusted data, text only), row by row, each row with its page and
the text it was read from, and evaluates it:

- the columns that restate the petition ("claimed") or an earlier approval are compared with the
  formats' cells — did the Commission read the petition as filed;
- the decision itself: what was approved against what was claimed, line by line.

Rows are found by their serial numbers (1, 2, 3 … in order), so a page header inside a table is
passed over; a row's label runs to its first figure and its figures are the figures that follow.
A row printing fewer figures than the table has columns (a blank cell) is read only where the spec
names its columns; a table not found or a row matched twice is an error — never a guess.
"""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .narrative import parse_figure

_FIG = re.compile(r"^(\(?[0-9][0-9,]*\.[0-9]+%?\)?|-)$")  # a rate prints with %


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def read_rows(pages: dict[int, str], title: str, on: list[int]) -> list[dict[str, Any]]:
    """The rows of the table titled ``title`` (its first page first in ``on``), across the pages
    ``on``: serial number, label, figures as printed, page and quote."""
    first = norm(pages[on[0]])
    start = first.find(title)
    if start < 0:
        raise ValueError(f"table {title!r} not on page {on[0]}")
    chunks: list[tuple[int, str]] = [(on[0], first[start + len(title) :])]
    chunks += [(p, norm(pages[p])) for p in on[1:]]
    rows: list[dict[str, Any]] = []
    expected = 1
    for page, text in chunks:
        stop = text.find(" TABLE ", 1)
        text = text if stop < 0 else text[:stop]
        tokens = text.split(" ")
        i = 0
        while i < len(tokens):
            # a serial number opens a row when a label (not a figure) follows it
            if tokens[i] == str(expected) and i + 1 < len(tokens) and not _FIG.match(tokens[i + 1]):
                j = i + 1
                label: list[str] = []
                while j < len(tokens) and not _FIG.match(tokens[j]):
                    label.append(tokens[j])
                    j += 1
                figs: list[str] = []
                while j < len(tokens) and _FIG.match(tokens[j]):
                    figs.append(tokens[j])
                    j += 1
                if figs:
                    quote = " ".join(tokens[i:j])
                    rows.append(
                        {"serial": expected, "label": " ".join(label), "figures": figs, "page": page, "quote": quote}
                    )
                    expected += 1
                    i = j
                    continue
            i += 1
    if not rows:
        raise ValueError(f"table {title!r}: no rows read")
    return rows


def _value(text: str) -> Decimal | None:
    if text == "-":
        return Decimal(0)
    p = parse_figure(text)
    return None if p is None else p.value


def evaluate_table(
    table: dict[str, Any], spec_rows: list[dict[str, Any]], wb: Any, sheet: str = "ARR"
) -> list[dict[str, Any]]:
    """Each read row matched to a key by its label (a pattern matched in full), its figures given
    to the table's columns (all of them, or the columns the spec names for a short row), compared
    with the format where a column restates a format column, and the decision (approved − claimed)
    where the table has both."""
    cols = table["columns"]
    names = [c["name"] for c in cols]
    short = {int(k): v for k, v in table.get("short_rows", {}).items()}
    patterns = [(r["key"], re.compile(r["label"], re.I)) for r in spec_rows]
    by_key = {r["key"]: r for r in spec_rows}
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in table["rows"]:
        hits = [k for k, p in patterns if p.fullmatch(row["label"])]
        if len(hits) > 1:
            raise ValueError(f"{table['title']}: row {row['serial']} matches {hits}")
        key = hits[0] if hits else None
        if key in seen:
            raise ValueError(f"{table['title']}: {key} matched twice")
        if key:
            seen.add(key)
        if len(row["figures"]) == len(names):
            given = names
        elif row["serial"] in short:
            given = short[row["serial"]]
            if len(given) != len(row["figures"]):
                raise ValueError(f"{table['title']}: row {row['serial']} prints {len(row['figures'])} figures")
        else:
            raise ValueError(
                f"{table['title']}: row {row['serial']} prints {len(row['figures'])} of {len(names)} figures "
                "and the spec names no columns for it"
            )
        values = dict(zip(given, row["figures"], strict=True))
        rec: dict[str, Any] = {k: row[k] for k in ("serial", "label", "page", "quote")} | {
            "key": key,
            "values": values,
            "checks": {},
        }
        for c in cols:
            # a table may print a line differently in one column (the order's true-up shows the
            # earlier approval's revenue gross, its regulatory discount on a row of its own)
            spec = table.get("row_overrides", {}).get(key or "", {}).get(c["name"]) or by_key.get(key or "")
            if not c.get("format_column") or c["name"] not in values or spec is None or not spec.get("rows"):
                continue
            printed = values[c["name"]]
            p = parse_figure(printed) if printed != "-" else None
            places = p.places if p else 2
            total = Decimal(0)
            refs: list[str] = []
            blank = True
            for r in spec["rows"]:
                v = wb[sheet][f"{c['format_column']}{r}"].value
                refs.append(f"{sheet}!{c['format_column']}{r}")
                if isinstance(v, int | float) and not isinstance(v, bool):
                    total += Decimal(str(v))
                    blank = False
            for r in spec.get("minus", []):
                v = wb[sheet][f"{c['format_column']}{r}"].value
                refs.append(f"-{sheet}!{c['format_column']}{r}")
                if isinstance(v, int | float) and not isinstance(v, bool):
                    total -= Decimal(str(v))
            total *= int(spec.get("sign", 1))
            q = Decimal(1).scaleb(-places)
            fmt = total.quantize(q, rounding=ROUND_HALF_UP)
            got = _value(printed)
            result = "no_format_value" if blank else ("match" if got == fmt else "differs")
            check = {"printed": printed, "format": str(fmt), "cells": refs, "result": result}
            if result == "differs":
                check["last_place_units"] = int((got - fmt) / q)
            rec["checks"][c["name"]] = check
        if "claimed" in values and "approved" in values:
            claimed, approved = _value(values["claimed"]), _value(values["approved"])
            if claimed is not None and approved is not None:
                rec["decision"] = str(approved - claimed)
        out.append(rec)
    return out


def _part(by_key: dict[str, dict[str, str]], key: str, column: str) -> Decimal:
    """A part of an identity as printed in a column; blank counts as zero."""
    return _value(by_key.get(key, {}).get(column, "")) or Decimal(0)


IDENTITIES = (
    (
        "ARR = power purchase + transmission + net O&M + interest + depreciation + tax + bad debts"
        " + other allowed lines",
        "arr_before_roe",
        [
            "power_purchase",
            "transmission",
            "om_net",
            "interest",
            "depreciation",
            "tax",
            "bad_debts",
            "loss_retired",
            "efficiency_gains",
            "contingency",
        ],
        [],
    ),
    (
        "net ARR = ARR + RoE − open access − non-tariff income − other business",
        "arr_net",
        ["arr_before_roe", "roe"],
        ["open_access", "nti", "other_business"],
    ),
    ("gap = net ARR − revenue + tariff revision impact", "gap", ["arr_net", "revision_impact"], ["revenue"]),
)


def identities(
    rows: list[dict[str, Any]], columns: list[dict[str, Any]], tolerance: Decimal = Decimal("0.02")
) -> list[dict[str, Any]]:
    """The order's own arithmetic, per column: each identity's total against the sum of its
    parts as printed, within ``tolerance`` (two units of the last place: the parts are printed
    rounded).  A part the column leaves blank counts as zero; an identity whose total is blank is
    not checked."""
    by_key = {r["key"]: r["values"] for r in rows if r["key"]}
    out: list[dict[str, Any]] = []
    for c in columns:
        name = c["name"]
        for title, total_key, plus, minus in IDENTITIES:
            total = _value(by_key.get(total_key, {}).get(name, ""))
            if total is None or not any(name in by_key.get(k, {}) for k in plus + minus):
                continue  # the total is not printed, or none of its parts is: nothing to check

            parts = sum((_part(by_key, k, name) for k in plus), Decimal(0)) - sum(
                (_part(by_key, k, name) for k in minus), Decimal(0)
            )
            diff = total - parts
            out.append(
                {
                    "column": name,
                    "identity": title,
                    "printed": str(total),
                    "parts": str(parts),
                    "difference": str(diff),
                    "result": "match" if abs(diff) <= tolerance else "differs",
                }
            )
    return out


def rows_by_position(
    words: list[tuple],
    anchors: dict[str, float],
    start: str,
    stop: str | None = None,
    code: str = r"^[A-Z](\.\d+)?$",
    label_span: float = 0,
) -> list[dict[str, Any]]:
    """The rows of a table whose blank cells make text order ambiguous (a figure printed under
    "Approved" with nothing under "Claimed"), read from one page's words with their positions
    (PyMuPDF ``get_text("words")``: x0, y0, x1, y1, text, …).  Rows run from the line holding the
    word ``start`` to the line before ``stop``; words share a line when their tops are within 3
    points.  Each figure goes to the column whose anchor (an x centre taken from the page's own
    header words) is nearest; two figures on one anchor is an error.  A line opens with its code
    (``A``, ``B.1``) when it has one; a total line has none and is named by its words.

    ``label_span``: where a table centres its figures between the lines of a wrapped label ("Add.
    Coal for FY23 (90%" / figures / "Booked in FY23)"), a line with no figures within that many
    points of a figure line belongs to the nearest one's label, in reading order; a line with no
    figures farther away (a section heading) belongs to none."""
    pat = re.compile(code)
    lines: list[list[tuple]] = []
    for w in sorted(words, key=lambda w: (round(w[1]), w[0])):
        if lines and abs(lines[-1][0][1] - w[1]) < 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    # a figure stands in the figure columns: a dash in a label ("TPTCL - PPGCL") is text
    left = min(anchors.values()) - 25
    body: list[tuple[float, list[tuple], list[tuple]]] = []
    on = False
    for line in lines:
        line.sort(key=lambda w: w[0])
        texts = [w[4] for w in line]
        if not on:
            on = start in texts
            continue
        if stop and stop in " ".join(texts):
            break
        body.append((line[0][1], line, [w for w in line if _FIG.match(w[4]) and (w[0] + w[2]) / 2 >= left]))
    rows = [(y, line, figs) for y, line, figs in body if figs]
    extra: dict[int, list[tuple[float, list[tuple]]]] = {i: [] for i in range(len(rows))}
    if label_span and rows:
        for y, line, figs in body:
            if figs:
                continue
            i = min(range(len(rows)), key=lambda k: abs(rows[k][0] - y))
            if abs(rows[i][0] - y) <= label_span:
                extra[i].append((y, line))
    out: list[dict[str, Any]] = []
    for i, (y, line, figs) in enumerate(rows):
        texts = [w[4] for w in line]
        first = texts[0]
        row_code = first if pat.match(first) else None
        own = " ".join(w[4] for w in line if w not in figs and w[4] != row_code)
        above = [" ".join(w[4] for w in ln) for yy, ln in extra[i] if yy < y]
        below = [" ".join(w[4] for w in ln) for yy, ln in extra[i] if yy > y]
        label = " ".join(t for t in [*above, own, *below] if t)
        cells: dict[str, str] = {}
        for w in figs:
            centre = (w[0] + w[2]) / 2
            name = min(anchors, key=lambda a: abs(anchors[a] - centre))
            if name in cells:
                raise ValueError(f"row {row_code or label!r}: two figures under {name}")
            cells[name] = w[4]
        quote = " ".join([*above, " ".join(texts), *below])
        out.append({"code": row_code, "label": label, "cells": cells, "quote": quote})
    return out


def source_decisions(rows: list[dict[str, Any]], skip: tuple[str, ...] = ()) -> list[dict[str, str]]:
    """The decision on each line of a source table: the approved amount against the claimed, a
    blank or "-" counting as nil; only the lines where they differ.  ``skip``: the keys of total
    lines, whose difference is the sum of the others'."""
    out: list[dict[str, str]] = []
    for r in rows:
        key = r["code"] or r["label"]
        if key in skip:
            continue
        cells = r["cells"]
        if "claimed_amount" not in cells and "approved_amount" not in cells:
            continue
        claimed = _value(cells.get("claimed_amount", "-")) or Decimal(0)
        approved = _value(cells.get("approved_amount", "-")) or Decimal(0)
        if claimed != approved:
            out.append(
                {"line": key, "claimed": str(claimed), "approved": str(approved), "decision": str(approved - claimed)}
            )
    return out


def check_sources(rows: list[dict[str, Any]], sides: list[str], sums: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A source table's own arithmetic, per side ("claimed", "approved"): each row's amount
    against its MUs × rate (Rs. crore = MU × Rs/kWh ÷ 10, within the rounding of the printed rate
    and MUs), and each subtotal against the sum of its parts as printed (two units of the last
    place).  ``sums``: ``{"total": key, "parts": [keys], "field": "amount" | "mu"}``, a key being a
    row's code or its label."""
    by = {(r["code"] or r["label"]): r["cells"] for r in rows}
    out: list[dict[str, Any]] = []
    for side in sides:
        for key, cells in by.items():
            mu, rate, amount = (_value(cells.get(f"{side}_{f}", "")) for f in ("mu", "rate", "amount"))
            if None in (mu, rate, amount) or mu == 0:
                continue
            implied = mu * rate / 10
            slack = abs(mu) * Decimal("0.005") / 10 + abs(rate) * Decimal("0.005") / 10 + Decimal("0.005")
            ok = abs(implied - amount) <= slack
            out.append(
                {
                    "side": side,
                    "check": f"{key}: amount = MU × rate",
                    "printed": str(amount),
                    "computed": str(implied.quantize(Decimal("0.01"))),
                    "result": "match" if ok else "differs",
                }
            )
        for s in sums:
            total = _value(by.get(s["total"], {}).get(f"{side}_{s.get('field', 'amount')}", ""))
            if total is None:
                continue
            parts = [_value(by.get(k, {}).get(f"{side}_{s.get('field', 'amount')}", "")) for k in s["parts"]]
            if all(p is None for p in parts):
                continue
            got = sum((p or Decimal(0) for p in parts), Decimal(0))
            diff = total - got
            out.append(
                {
                    "side": side,
                    "check": f"{s['total']} = {' + '.join(s['parts'])}",
                    "printed": str(total),
                    "computed": str(got),
                    "difference": str(diff),
                    "result": "match" if abs(diff) <= Decimal("0.02") else "differs",
                }
            )
    return out
