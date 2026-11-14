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


def test_a_schedule_without_per_category_headings_and_two_line_captions(tmp_path):
    """Another commission's layout: no list of tables, a caption 'Table – 7' with its title on the next
    line, and a 'Chapter 9: TARIFF SCHEDULE' whose categories are headings such as 'Domestic Service (DS):'."""
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 60), "Table - 7", fontsize=10)
    p1.insert_text((72, 75), "Cross Subsidy Surcharge for FY 2099-00", fontsize=10)
    ruled(p1, 60, 90, [200, 150], [["Category", "CSS (Rs./kWh)"], ["HT Industrial", "1.11"]])
    p2 = doc.new_page()
    p2.insert_text((72, 60), "Chapter 9: TARIFF SCHEDULE", fontsize=11)
    p2.insert_text((72, 90), "Domestic Service (DS): AC, 50 Cycles, Single Phase", fontsize=9)
    y = ruled(
        p2,
        60,
        100,
        [150, 150, 150],
        [["Slab", "Fixed Charge", "Energy Charge"], ["0-100 units", "Rs. 75 / month", "Rs. 6.30 / kWh"]],
    )
    p2.insert_text((72, y + 25), "HTS (General) - I (11 kV)", fontsize=9)
    ruled(
        p2,
        60,
        y + 35,
        [200, 150],
        [["Time", "Rebate / surcharge"], ["05:00 am - 09:00 am", "(-) 20%"], ["05:00 pm - 11:00 pm", "(+) 20%"]],
    )
    p3 = doc.new_page()
    p3.insert_text((72, 60), "Chapter 10: DIRECTIVES", fontsize=11)
    ruled(p3, 60, 80, [200, 150], [["Directive", "Due by"], ["Smart meters 100%", "31.03.2100"]])
    path = tmp_path / "other.pdf"
    doc.save(str(path))
    pages = [{"page": i + 1, "text": pg.get_text(), "has_text_layer": True} for i, pg in enumerate(doc)]

    tables, _ = S.read(path, pages)
    assert S.check(tables, pages)["rows_failed"] == 0
    css = [t for t in tables if t.label == "Table 7"]
    assert css and css[0].section == "wheeling" and css[0].title == "Cross Subsidy Surcharge for FY 2099-00"
    ds = [t for t in tables if t.section == "tariff_schedule"]
    assert len(ds) == 1 and ds[0].category == "Domestic Service (DS)"
    assert ds[0].rows[0]["cells"] == ["0-100 units", "Rs. 75 / month", "Rs. 6.30 / kWh"]
    tod = [t for t in tables if t.section == "tod"]
    assert tod and tod[0].category == "HTS (General) - I (11 kV)"
    assert not any("Smart meters" in " ".join(r["cells"]) for t in tables for r in t.rows)  # the schedule ended


def test_charges_of_stations_or_in_crore_are_power_purchase():
    assert S.classify("Fixed cost and Energy charges of MPPMCL allocated stations for FY 2099-00") == "power_purchase"
    assert S.classify("Fixed Charges and Energy Charges as Claimed by Petitioners (Rs. Crore)") == "power_purchase"
    assert S.classify("Approved tariff for EV charging stations") == "tariff_schedule"
    assert S.classify("Energy charges for LT domestic consumers") == "tariff_schedule"
    assert S.classify("Annual Fixed Charges (AFC) of Generation Projects for FY 2099-00") == "power_purchase"


def test_a_tariff_sheet_with_no_schedule_heading(tmp_path):
    """A licensee's published tariff of a few pages (CESC-style): no schedule heading, no list of
    tables; every ruled table is the schedule, and a table of consumer categories with TOD rows among
    them stays in the tariff schedule (only a table whose every row is timed is TOD)."""
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 60), "LOW AND MEDIUM VOLTAGE CONSUMERS", fontsize=11)
    ruled(
        p1,
        60,
        80,
        [150, 150, 150],
        [
            ["Type of Consumer", "Monthly consumption", "Energy Charge P/kWh"],
            ["Domestic", "First 25", "111"],
            ["Domestic", "Next 35", "122"],
            ["Commercial TOD", "06.00 hrs to 17.00 hrs", "133"],
        ],
    )
    p1.insert_text((72, 250), "Time of day rates", fontsize=10)
    ruled(
        p1,
        60,
        270,
        [150, 150, 150],
        [["Type of Consumer", "Period", "Energy Charge P/kWh"], ["Emergency", "06.00 hrs to 17.00 hrs", "144"],
         ["Emergency", "17.00 hrs to 23.00 hrs", "155"]],
    )  # fmt: skip
    path = tmp_path / "sheet.pdf"
    doc.save(str(path))
    pages = [{"page": 1, "text": p1.get_text(), "has_text_layer": True}]

    tables, notes = S.read(path, pages)
    assert S.check(tables, pages)["rows_failed"] == 0
    assert [t.section for t in sorted(tables, key=lambda t: t.rows[0]["cells"][-1])] == ["tariff_schedule", "tod"]


def test_invisible_marks_and_headings():
    """Bidi marks around every word (an APERC order) are not text; a body sentence naming the schedule
    is not its heading; an appendix's own running head does not end it."""
    assert S._ws("‭RETAIL‬ ‭SUPPLY‬​") == "RETAIL SUPPLY"
    assert S.SCHEDULE_START.search("APPENDIX A: ABSTRACT OF THE RETAIL SUPPLY TARIFF FOR FY 2099-00")
    assert S.SCHEDULE_START.search("SCHEDULES OF TARIFF")
    assert S.SCHEDULE_START.search("SCHEDULE – COMMERCIAL SUPPLY (CS)")
    assert not S.SCHEDULE_START.search("Schedule I of the Act")
    assert S._headline("Schedule of Tariff and Charges")
    assert S._headline("11 Annexure 6: Tariff Schedule for 5th MYT Control Period – FY 2025-26 to FY 2029-30")
    assert not S._headline("Retail Supply Tariff for FY 2021-22 in accordance with the guidelines laid down in Section")
    assert not S._headline("Schedule of Tariff to the residential units registered under the Tourism Policy of Govt.")
    assert S._part_tag("Appendix A") == S._part_tag("APPENDIX A: ABSTRACT") == "APPENDIX A"
    assert S.is_tod(["Category", "Rate"], [["Domestic", "5.00"], ["Peak 18:00 hrs to 22:00 hrs", "6.00"]]) is False
    assert S.is_tod(["Period", "Rate"], [["06:00 hrs to 18:00 hrs", "5.00"], ["18:00 hrs to 22:00 hrs", "6.00"]])


def test_an_ocr_layer_over_scans_is_not_read(tmp_path):
    """Invisible text (render mode 3) on most pages is a recogniser's guesses over pictures: no tables."""
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 60), "Table 1: Power purchase 4.05] |Alpha", fontsize=10, render_mode=3)
    assert S.ocr_layer(doc)
    path = tmp_path / "scan.pdf"
    doc.save(str(path))
    pages = [{"page": i + 1, "text": pg.get_text(), "has_text_layer": True} for i, pg in enumerate(doc)]
    tables, notes = S.read(path, pages)
    assert tables == [] and "OCR" in notes[0]
