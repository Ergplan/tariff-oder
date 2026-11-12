"""The Section Reader on a synthetic order built here (ruled tables drawn with PyMuPDF).

FIXTURE: every figure below is invented for the test (station names "Alpha", "Beta" …,
values such as 111.11); none is a figure from an order.  The page is the evidence: the reader's
cells come from its text layer, and ``check`` drops any row whose number is not on its page.
"""

from __future__ import annotations

import pytest

pytest.importorskip("arrnet")
import pymupdf  # noqa: E402
from arrnet import sections as S  # noqa: E402


def ruled(page, x0, y0, widths, rows, h=18):
    """Draw a ruled table: every cell boxed, its text inside."""
    y = y0
    for r in rows:
        x = x0
        for w, text in zip(widths, r, strict=True):
            page.draw_rect(pymupdf.Rect(x, y, x + w, y + h), color=(0, 0, 0), width=0.7)
            if text:
                page.insert_text((x + 3, y + 12), text, fontsize=8)
            x += w
        y += h
    return y


@pytest.fixture()
def order(tmp_path):
    doc = pymupdf.open()
    toc = doc.new_page()
    toc.insert_text((72, 60), "LIST OF TABLES", fontsize=11)
    toc.insert_text((72, 90), "TABLE 9-1: APPROVED POWER PURCHASE FOR FY 2099-00 ........ 2", fontsize=9)
    toc.insert_text((72, 105), "TABLE 9-2: RPO COMPLIANCE FOR FY 2099-00 ........ 4", fontsize=9)
    toc.insert_text((72, 120), "TABLE 9-3: CROSS SUBSIDY SURCHARGE APPROVED FOR FY 2099-00 ........ 4", fontsize=9)
    toc.insert_text((72, 135), "TABLE 9-4: SALES FOR FY 2099-00 ........ 4", fontsize=9)
    toc.insert_text((72, 150), "TABLE 9-5: TABLE ONE TABLE TWO TABLE THREE ........ 4", fontsize=9)
    toc.insert_text((72, 165), "TABLE 9-6: TABLE ONE TABLE TWO ........ 4", fontsize=9)
    p2 = doc.new_page()
    p2.insert_text((72, 60), "Table 9-1: Approved Power Purchase for FY 2099-00", fontsize=10)
    body = [
        ["SN", "Source of Power", "Units (MU)", "Total Cost (Rs. Cr.)"],
        ["A", "Long term", "", ""],
        ["", "Sources", "", ""],
    ]
    body += [[str(i), f"Station {i}", f"{100 + i}.11", f"{200 + i}.22"] for i in range(1, 37)]
    end = ruled(p2, 60, 80, [40, 200, 120, 120], body)
    assert end > p2.rect.height * 0.8
    p3 = doc.new_page()  # the continuation: same frame, a repeated header, no new title
    ruled(p3, 60, 50, [40, 200, 120, 120], [["SN", "Source of Power", "Units (MU)", "Total Cost (Rs. Cr.)"]]
          + [[str(i), f"Station {i}", f"{100 + i}.11", f"{200 + i}.22"] for i in range(37, 40)])  # fmt: skip
    p4 = doc.new_page()
    p4.insert_text((72, 60), "Table 9-2: RPO Compliance for FY 2099-00", fontsize=10)
    y = ruled(
        p4, 60, 80, [200, 150], [["Particular", "Quantum (MU)"], ["Solar RPO", "1,234.56"], ["Non-solar RPO", "13.07%"]]
    )
    p4.insert_text((72, y + 30), "Table 9-3: Cross Subsidy Surcharge approved for FY 2099-00", fontsize=10)
    ruled(p4, 60, y + 50, [200, 150], [["Category", "CSS (Rs./kWh)"], ["HV-1 (Supply at 11 kV)", "1.53"]])
    p5 = doc.new_page()
    p5.insert_text((72, 60), "ANNEXURE-I (RATE SCHEDULE)", fontsize=10)
    p5.insert_text((72, 80), "RATE SCHEDULE LMV - 1 DOMESTIC LIGHT, FAN & POWER", fontsize=10)
    p5.insert_text((72, 100), "(a) Consumers getting supply as per Rural Schedule:", fontsize=9)
    y = ruled(
        p5,
        60,
        110,
        [150, 150, 150],
        [["Description", "Fixed Charge", "Energy Charge"], ["Metered", "Rs. 90.00 / kW / month", "Rs. 3.35 / kWh"]],
    )
    p5.insert_text((72, y + 25), "TOD Structure and Rates:", fontsize=9)
    ruled(
        p5,
        60,
        y + 35,
        [200, 150],
        [["Hours", "% of Energy Charges"], ["05:00 hrs - 10:00 hrs", "(-) 15%"], ["19:00 hrs - 03:00 hrs", "(+) 15%"]],
    )
    p6 = doc.new_page()
    p6.insert_text((72, 60), "RATE SCHEDULE HV - 2 LARGE AND HEAVY POWER", fontsize=10)
    p6.insert_text(
        (72, 90), "3. RATE: Demand charge Rs. 300.00 / kVA / month; energy charge Rs. 7.10 / kVAh.", fontsize=9
    )
    path = tmp_path / "order.pdf"
    doc.save(str(path))
    pages = [{"page": i + 1, "text": pg.get_text(), "has_text_layer": True} for i, pg in enumerate(doc)]
    return path, pages


def test_classify_by_title():
    assert S.classify("APPC OF RENEWABLE SOURCES FOR FY 2026-27") == "re_portfolio"
    assert S.classify("APPROVED BULK SUPPLY TARIFF FOR FY 2026-27") == "power_purchase"
    assert S.classify("CSS APPROVED BY THE COMMISSION") == "wheeling"
    assert S.classify("TOD STRUCTURE") == "tod"
    assert S.classify("SALES FOR FY 2099-00") is None


def test_sections_read_and_checked(order):
    path, pages = order
    idx = S.table_index(pages)
    assert [x["label"] for x in idx][:3] == ["Table 9-1", "Table 9-2", "Table 9-3"]
    tables, notes = S.read(path, pages)
    ck = S.check(tables, pages)
    assert ck["rows_failed"] == 0
    by = {(t.section, t.label): t for t in tables}

    pp = by[("power_purchase", "Table 9-1")]
    assert pp.pages == [2, 3] and pp.fiscal_year == "FY2099-00"
    assert pp.columns == ["SN", "Source of Power", "Units (MU)", "Total Cost (Rs. Cr.)"]
    assert pp.rows[0]["cells"] == ["A", "Long term Sources", "", ""]  # a wrapped label is one row
    assert len(pp.rows) == 1 + 39 and pp.rows[-1] == {"cells": ["39", "Station 39", "139.11", "239.22"], "page": 3}

    assert by[("re_portfolio", "Table 9-2")].rows[1]["cells"] == ["Non-solar RPO", "13.07%"]
    assert by[("wheeling", "Table 9-3")].rows == [{"cells": ["HV-1 (Supply at 11 kV)", "1.53"], "page": 4}]
    assert not any(t.label == "Table 9-4" for t in tables)  # sales: not a section

    lmv = [t for t in tables if t.category == "LMV-1" and t.section == "tariff_schedule"]
    assert lmv and lmv[0].rows[0]["cells"] == ["Metered", "Rs. 90.00 / kW / month", "Rs. 3.35 / kWh"]
    assert lmv[0].title.startswith("(a) Consumers getting supply as per Rural Schedule")
    tod = [t for t in tables if t.section == "tod"]
    assert tod and tod[0].category == "LMV-1" and tod[0].rows[0]["cells"] == ["05:00 hrs - 10:00 hrs", "(-) 15%"]

    hv2 = [t for t in tables if t.category == "HV-2"]  # no ruled table: its RATE text, as printed
    assert hv2 and hv2[0].kind == "text" and "Rs. 300.00 / kVA / month" in hv2[0].rows[0]["cells"][0]


def test_check_drops_a_row_whose_number_is_not_on_its_page(order):
    path, pages = order
    tables, _ = S.read(path, pages)
    t = next(t for t in tables if t.label == "Table 9-3")
    t.rows.append({"cells": ["HV-2 (invented)", "9.99"], "page": 4})
    ck = S.check(tables, pages)
    assert ck["rows_failed"] == 1 and all(r["cells"][1] != "9.99" for r in t.rows)
