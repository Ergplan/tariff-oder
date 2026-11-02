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
