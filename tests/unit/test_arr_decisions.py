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
    t = next(t for t in rep["source_tables"] if t["proceeding"] == "arr")
    assert len(t["rows"]) == 51
    assert {c["result"] for c in t["arithmetic"] if c["side"] == "approved"} == {"match"}
    off = sorted(c["check"].split(":")[0].split(" =")[0] for c in t["arithmetic"] if c["result"] != "match")
    assert off == ["B.1", "C", "F"]
    rows = {r["code"]: r["cells"] for r in t["rows"] if r["code"]}
    assert "claimed_mu" not in rows["C.8"] and rows["C.8"]["approved_mu"] == "102.29"
    assert (rows["A"]["claimed_rate"], rows["A"]["approved_rate"]) == ("4.50", "4.89")


def test_a_wrapped_label_centred_on_its_figures_is_joined_and_a_heading_is_not():
    """A source name wrapped over two lines with its figures centred between them (Table 4-52)
    belongs to that row; a section heading farther away belongs to none.  The decision per line
    counts a blank or "-" as nil and leaves out the totals."""
    from tariff_api.arr.decisions import rows_by_position, source_decisions

    anchors = {
        "claimed_mu": 270,
        "claimed_rate": 320,
        "claimed_amount": 375,
        "approved_mu": 430,
        "approved_rate": 470,
        "approved_amount": 530,
    }
    words = [
        _w(300, 100, "kWh"),
        _w(40, 120, "Others"),
        _w(40, 133, "Change"),
        _w(80, 133, "in"),
        _w(95, 133, "Law"),
        _w(360, 139, "4.98"),
        _w(530, 139, "-"),
        _w(40, 145, "(Booked"),
        _w(90, 145, "FY24)"),
        _w(40, 158, "Carrying"),
        _w(360, 164, "11.37"),
        _w(515, 164, "9.07"),
        _w(40, 170, "Cost"),
        _w(40, 183, "Total"),
        _w(360, 183, "16.35"),
        _w(515, 183, "9.07"),
    ]
    rows = rows_by_position(words, anchors, "kWh", label_span=7)
    assert [r["label"] for r in rows] == ["Change in Law (Booked FY24)", "Carrying Cost", "Total"]
    assert rows[0]["quote"] == "Change in Law 4.98 - (Booked FY24)"
    assert [r["label"] for r in rows_by_position(words, anchors, "kWh")] == ["", "", "Total"]
    got = source_decisions(rows, skip=("Total",))
    assert [(d["line"], d["decision"]) for d in got] == [
        ("Change in Law (Booked FY24)", "-4.98"),
        ("Carrying Cost", "-2.30"),
    ]


def test_npcl_trueup_power_purchase_decision_line_by_line():
    """Real data: Table 4-52 read by position, wrapped labels joined: the table's own arithmetic
    holds on both sides, the claimed side is NPCL's format (ARR!J20:J24), and the decision is five
    lines — two amounts deferred to FY2025-26's true-up, two carrying costs, the excess energy (A70)."""
    rep = json.loads(
        (ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27" / "order-decisions.json").read_text()
    )
    t = next(t for t in rep["source_tables"] if t["proceeding"] == "true_up")
    assert {c["result"] for c in t["arithmetic"]} == {"match"} and len(t["arithmetic"]) == 44
    assert [f["result"] for f in t["against_format"]] == ["match", "match"]
    assert {d["line"]: d["decision"] for d in t["decisions"]} == {
        "TPTCL(Source-JITPL) - Thermal incentive": "-1.02",
        "Carrying Cost on above for FY23": "-3.37",
        "Change in Law for FY24 (100% Booked in FY24)": "-4.98",
        "Carrying Cost for FY24 (Booked in FY25)": "-2.30",
        "Energy Disallowed": "-0.34",
    }
    summary = {r["key"]: r for r in next(x for x in rep["tables"] if x["proceeding"] == "true_up")["rows"]}
    sub = next(r for r in t["rows"] if r["label"] == "Sub-Total of Power Purchase Cost")
    assert summary["power_purchase"]["values"]["approved"] == sub["cells"]["approved_amount"] == "2,163.65"
    assert summary["power_purchase"]["decision"] == "-11.99"


def test_every_changed_line_needs_its_reason_and_the_reasons_add_to_the_net():
    """A changed line without a reason is listed, never dropped; a deduction moves the net the other
    way; a claim the approved column leaves blank is a change; a misprint is carried by the
    reason's as-approved figure; a reason for a line that did not change is stale."""
    from tariff_api.arr.decisions import explain

    rows = [
        {"key": "om", "values": {"claimed": "10.00", "approved": "8.00"}, "decision": "-2.00"},
        {"key": "interest", "values": {"claimed": "5.00", "approved": "5.50"}, "decision": "0.50"},
        {"key": "nti", "values": {"claimed": "1.00", "approved": "1.50"}, "decision": "0.50"},
        {"key": "other_business", "values": {"claimed": "0.20"}, "decision": None},
        {"key": "arr_net", "values": {"claimed": "14.20", "approved": "12.00"}, "decision": "-2.20"},
    ]
    spec = {"deductions": ["nti", "other_business"], "totals": ["arr_net"], "net": "arr_net"}
    lines = {
        "om": {"reason": "norm", "parts": [{"amount": "-1.50", "what": "a"}, {"amount": "-0.50", "what": "b"}]},
        "interest": {"reason": "rate", "as_approved": "0.10"},
        "other_business": {"reason": "one business"},
        "tax": {"reason": "stale"},
    }
    got = explain(rows, spec, lines)
    assert got["unexplained"] == ["nti"] and got["stale"] == ["tax"]
    by = {x["key"]: x for x in got["lines"]}
    assert by["om"]["parts_result"] == "match"
    assert (by["other_business"]["decision"], by["other_business"]["effect"]) == ("-0.20", "0.20")
    # −2.00 + 0.10 (as approved) + 0.20; the unexplained nti's −0.50 is missing from the sum
    assert (got["effect_sum"], got["difference"]) == ("-1.70", "0.50")


def test_npcl_every_line_of_the_three_decisions_has_its_reason():
    """Real data: every line the Commission changed in the true-up, the APR and the ARR year has a
    reason with its pages and finding; each line's parts add to it; the reasons' effects add to the
    net ARR's decision within the rounding of the printed lines — the ARR year exactly, once the
    summary's misprinted interest is taken as approved (A61)."""
    from decimal import Decimal

    rep = json.loads(
        (ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27" / "order-decisions.json").read_text()
    )
    findings = {
        f["id"]
        for f in json.loads(
            (ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27" / "findings.json").read_text()
        )["findings"]
    }
    for t in rep["tables"]:
        ex = t["explanation"]
        assert ex["unexplained"] == [] and ex["stale"] == [], t["proceeding"]
        assert abs(Decimal(ex["difference"])) <= Decimal("0.02"), t["proceeding"]
        for line in ex["lines"]:
            assert line["finding"] in findings and line["where"] and line["reason"], line["key"]
            assert line["status"] in ("reproduced", "read", "refused", "deferred", "provisional")
            assert line.get("parts_result", "match") == "match", line["key"]
    arr = next(t for t in rep["tables"] if t["proceeding"] == "arr")["explanation"]
    assert arr["difference"] == "0.00"
    statuses = [x["status"] for t in rep["tables"] for x in t["explanation"]["lines"]]
    assert len(statuses) == 36 and statuses.count("reproduced") == 22  # 9 + 6 + 7


def test_npcl_the_apr_estimate_holds_its_arithmetic_and_moves_2_47():
    """Real data: Table 5-18, NPCL's APR estimate the Commission took provisionally, read by
    position with its own sides (the original approval, the estimate): the estimate's arithmetic
    holds throughout and its sub-total is the format's plus the 118.55 supplement (A72); the
    restated approval's power purchase sub-total is 2.47 below its rows (A79)."""
    from decimal import Decimal

    rep = json.loads(
        (ROOT / "packages" / "reference-filings" / "uperc-npcl-fy2026-27" / "order-decisions.json").read_text()
    )
    t = next(t for t in rep["source_tables"] if t["proceeding"] == "apr")
    assert t["sides"] == ["approved_before", "claimed"] and t["decisions"] == []
    assert {c["result"] for c in t["arithmetic"] if c["side"] == "claimed"} == {"match"}
    off = [c for c in t["arithmetic"] if c["result"] != "match"]
    assert len(off) == 1 and off[0]["side"] == "approved_before" and off[0]["difference"] == "-2.47"
    sub, trans = t["against_format"]
    assert Decimal(sub["printed"]) - Decimal(sub["format"]) == Decimal("118.55") and trans["result"] == "match"
