"""The Commission's decisions read from its order (R-TU-5): rows by serial number across pages,
short rows only where the spec names their columns, the claimed column checked against the
petition's format, the decision per line, and the order's own arithmetic."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tariff_api.arr.decisions import evaluate_table, identities, read_rows

ROOT = Path(__file__).resolve().parents[2]

PAGES = {
    1: "Some text. TABLE 1 SUMMARY (IN RS. CR.) Sl. No. Particulars Claimed Approved 1 Annual Revenue Requirement 100.00 90.00 2 Add: Return on Equity 10.00 9.50 3 Less: Non-Tariff Income 2.00",
    2: "SUMMARY Page 2 of 9 Sl. No. Particulars Claimed Approved 4 Net Annual Revenue Requirement 108.00 97.50 5 Less: Revenue from Existing Tariff 100.00 100.00 6 Revenue Gap / (Surplus) 8.00 (2.50) 4.1. The text goes on. TABLE 2 OTHER",
}
SPEC_ROWS = [
    {"key": "arr_before_roe", "label": r"annual revenue requirement", "rows": [46], "minus": [43]},
    {"key": "roe", "label": r"add: return on equity", "rows": [43]},
    {"key": "nti", "label": r"less: non-tariff income", "rows": [50]},
    {"key": "arr_net", "label": r"net annual revenue requirement", "rows": [53]},
    {"key": "revenue", "label": r"less: revenue from existing tariff", "rows": [17]},
    {"key": "gap", "label": r"revenue gap ?/ ?\(surplus\)", "rows": [58], "sign": -1},
]


def _book():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "ARR"
    for ref, v in {"M46": 110.0, "M43": 10.0, "M50": 2.0, "M53": 108.004, "M17": 100.0, "M58": -8.0}.items():
        ws[ref] = v
    return wb


def _table(**extra):
    rows = read_rows(PAGES, "TABLE 1 SUMMARY (IN RS. CR.)", [1, 2])
    cols = [{"name": "claimed", "header": "Claimed", "format_column": "M"}, {"name": "approved", "header": "Approved"}]
    return {"title": "TABLE 1", "columns": cols, "rows": rows} | extra


def test_rows_are_read_by_serial_number_across_pages_with_their_quotes():
    rows = read_rows(PAGES, "TABLE 1 SUMMARY (IN RS. CR.)", [1, 2])
    assert [r["serial"] for r in rows] == [1, 2, 3, 4, 5, 6]
    assert rows[3] == {
        "serial": 4,
        "label": "Net Annual Revenue Requirement",
        "figures": ["108.00", "97.50"],
        "page": 2,
        "quote": "4 Net Annual Revenue Requirement 108.00 97.50",
    }
    assert rows[5]["figures"] == ["8.00", "(2.50)"]  # stops at the next table's title
    with pytest.raises(ValueError, match="not on page"):
        read_rows(PAGES, "TABLE 9", [1])


def test_a_short_row_is_read_only_where_the_spec_names_its_columns():
    with pytest.raises(ValueError, match="names no columns"):
        evaluate_table(_table(), SPEC_ROWS, _book())
    rows = evaluate_table(_table(short_rows={"3": ["claimed"]}), SPEC_ROWS, _book())
    by = {r["key"]: r for r in rows}
    assert by["nti"]["values"] == {"claimed": "2.00"} and "decision" not in by["nti"]
    # the claimed column against the format: ARR before RoE is row 46 less row 43; the gap reversed
    assert by["arr_before_roe"]["checks"]["claimed"]["result"] == "match"
    assert by["gap"]["checks"]["claimed"]["result"] == "match"
    assert by["arr_net"]["checks"]["claimed"]["result"] == "match"  # 108.004 printed 108.00
    assert by["arr_net"]["decision"] == "-10.50" and by["gap"]["decision"] == "-10.50"
    # an override for one column of one table
    over = {"revenue": {"claimed": {"rows": [46], "why": "printed gross"}}}
    rows = evaluate_table(_table(short_rows={"3": ["claimed"]}, row_overrides=over), SPEC_ROWS, _book())
    assert next(r for r in rows if r["key"] == "revenue")["checks"]["claimed"]["result"] == "differs"


def test_the_orders_own_arithmetic_is_checked_per_column():
    rows = evaluate_table(_table(short_rows={"3": ["claimed"]}), SPEC_ROWS, _book())
    got = {(i["column"], i["identity"][:7]): i["result"] for i in identities(rows, _table()["columns"])}
    # claimed: 100 + 10 − 2 = 108 and 108 − 100 = 8; approved: 90 + 9.5 = 99.5, printed 97.50
    assert got == {
        ("claimed", "net ARR"): "match",
        ("claimed", "gap = n"): "match",
        ("approved", "net ARR"): "differs",
        ("approved", "gap = n"): "match",
    }


def test_npcl_order_decisions_on_the_three_proceedings():
    """Real data: the FY2026-27 order's summary tables (true-up, APR, ARR) as read with their
    pages: the claimed and earlier-approved columns agree with the petition's format to the last
    printed place; the order's own arithmetic holds; the decision on the ARR year is +29.51."""
    rep = json.loads(
        (ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27" / "order-decisions.json").read_text()
    )
    tables = {t["proceeding"]: t for t in rep["tables"]}
    assert [len(tables[p]["rows"]) for p in ("true_up", "apr", "arr")] == [25, 21, 22]
    for t in tables.values():
        assert all(
            c["result"] == "match" or abs(c["last_place_units"]) <= 2 for r in t["rows"] for c in r["checks"].values()
        )
    # the order's own arithmetic holds in every column but one: the ARR year's approved lines add
    # to 3,420.65 against the printed 3,420.27 — the interest line misprinted (110.80; Table 6-72
    # approves 110.43; A61)
    off = [
        (p, i["column"], i["difference"]) for p, t in tables.items() for i in t["identities"] if i["result"] != "match"
    ]
    assert off == [("arr", "approved", "-0.38")]
    assert sum(len(t["identities"]) for t in tables.values()) == 24
    arr = {r["key"]: r for r in tables["arr"]["rows"]}
    assert arr["arr_net"]["decision"] == "29.51" and arr["arr_net"]["page"] == 294
    assert tables["true_up"]["rows"][2]["values"] == {
        "approved_before": "36.56",
        "claimed": "95.42",
        "approved": "37.64",
    }


def _w(x0, y, text):
    return (x0, y, x0 + 6 * len(text), y + 9, text)


def test_a_table_with_blank_cells_is_read_by_word_position():
    """A figure under "Approved" with nothing under "Claimed" is the approved one: the text order
    cannot tell, the position can.  A dash inside a label is not a blank cell."""
    from tariff_api.arr.decisions import rows_by_position

    anchors = {
        "claimed_mu": 330,
        "claimed_rate": 370,
        "claimed_amount": 415,
        "approved_mu": 460,
        "approved_rate": 500,
        "approved_amount": 545,
    }
    words = [
        _w(320, 100, "MUs"),
        _w(400, 100, "Amount"),
        _w(40, 120, "A"),
        _w(60, 120, "Long"),
        _w(310, 120, "100.00"),
        _w(360, 120, "4.50"),
        _w(400, 120, "45.00"),
        _w(440, 120, "100.00"),
        _w(490, 120, "4.89"),
        _w(530, 120, "48.90"),
        _w(40, 140, "C.8"),
        _w(60, 140, "TPTCL"),
        _w(100, 140, "-"),
        _w(110, 140, "PPGCL"),
        _w(440, 140, "10.00"),
        _w(490, 140, "5.57"),
        _w(530, 140, "5.57"),
        _w(40, 160, "E.6"),
        _w(60, 160, "Solar"),
        _w(310, 160, "1.00"),
        _w(360, 160, "5.49"),
        _w(400, 160, "0.55"),
        _w(455, 160, "-"),
        _w(495, 160, "-"),
        _w(540, 160, "-"),
        _w(40, 180, "6.6."),
        _w(70, 180, "OPERATION"),
    ]
    rows = rows_by_position(words, anchors, "Amount", "6.6. OPERATION")
    by = {r["code"]: r["cells"] for r in rows}
    assert set(by) == {"A", "C.8", "E.6"}
    assert set(by["C.8"]) == {"approved_mu", "approved_rate", "approved_amount"}  # nothing claimed
    assert by["E.6"]["approved_amount"] == "-" and by["E.6"]["claimed_amount"] == "0.55"
    assert next(r for r in rows if r["code"] == "C.8")["label"] == "TPTCL - PPGCL"


def test_a_source_tables_arithmetic_is_checked_per_side():
    from tariff_api.arr.decisions import check_sources

    rows = [
        {
            "code": "A",
            "label": "",
            "cells": {
                "claimed_mu": "100.00",
                "claimed_rate": "4.50",
                "claimed_amount": "45.00",
                "approved_mu": "100.00",
                "approved_rate": "4.89",
                "approved_amount": "48.90",
            },
        },
        {
            "code": "B",
            "label": "",
            "cells": {"claimed_mu": "660.36", "claimed_rate": "5.62", "claimed_amount": "370.66"},
        },
        {"code": "F", "label": "", "cells": {"claimed_amount": "415.96", "approved_amount": "48.90"}},
    ]
    got = {
        (c["side"], c["check"][:1]): c["result"]
        for c in check_sources(rows, ["claimed", "approved"], [{"total": "F", "parts": ["A", "B"]}])
    }
    assert got == {
        ("claimed", "A"): "match",
        ("claimed", "B"): "differs",
        ("claimed", "F"): "differs",
        ("approved", "A"): "match",
        ("approved", "F"): "match",
    }


def test_npcl_power_purchase_approval_by_source():
    """Real data: Table 6-35 read by position — 51 rows; the approved side's arithmetic holds
    throughout; the claimed side has the order's two transcription slips (A63)."""
    rep = json.loads(
        (ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27" / "order-decisions.json").read_text()
    )
    (t,) = rep["source_tables"]
    assert len(t["rows"]) == 51
    assert {c["result"] for c in t["arithmetic"] if c["side"] == "approved"} == {"match"}
    off = sorted(c["check"].split(":")[0].split(" =")[0] for c in t["arithmetic"] if c["result"] != "match")
    assert off == ["B.1", "C", "F"]
    rows = {r["code"]: r["cells"] for r in t["rows"] if r["code"]}
    assert "claimed_mu" not in rows["C.8"] and rows["C.8"]["approved_mu"] == "102.29"
    assert (rows["A"]["claimed_rate"], rows["A"]["approved_rate"]) == ("4.50", "4.89")
