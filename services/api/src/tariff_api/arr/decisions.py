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
