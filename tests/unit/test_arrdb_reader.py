"""The ARR database's table reader, on a synthetic order page built here (no real order needed).

The page has what real orders print: a two-line title with its unit, a header grouping two
DISCOMs over claimed / approved columns, a wrapped label whose values sit on the middle line,
a nil printed as a dash, a negative in brackets, and a footer.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "arrdb"))

from arrdb.build import arr_year_of, stage_of  # noqa: E402
from arrdb.heads import head_of  # noqa: E402
from arrdb.reader import read_tables, voice_of, years_in  # noqa: E402


def _page(path: Path) -> None:
    doc = pymupdf.open()
    pg = doc.new_page(width=595, height=842)

    def put(x: float, y: float, text: str) -> None:
        pg.insert_text((x, y), text, fontsize=9)

    put(72, 80, "6.12 Based on the above, the ARR approved for FY 2026-27 is summarised below:")
    put(100, 110, "Table 6.84: ARR approved by the Commission for FY 2026-27")
    put(100, 122, "(Rs. Crore)")
    put(330, 145, "North DISCOM")
    put(450, 145, "South DISCOM")
    put(80, 160, "Particulars")
    put(310, 160, "Claimed")
    put(370, 160, "Approved")
    put(430, 160, "Claimed")
    put(490, 160, "Approved")
    rows = [
        ("Power Purchase Cost", ["4,597.53", "4,763.25", "3,187.25", "3,060.91"]),
        ("O&M Expenses", ["623.34", "551.63", "610.92", "548.84"]),
        ("Depreciation", ["191.68", "142.17", "-", "128.42"]),
        ("Less: Non-Tariff Income", ["(417.43)", "(567.15)", "(195.60)", "(225.79)"]),
        ("Aggregate Revenue Requirement", ["4,995.12", "4,889.90", "3,602.57", "3,512.38"]),
    ]
    y = 178.0
    for label, vals in rows:
        put(80, y, label)
        for x, v in zip((315, 375, 435, 495), vals, strict=True):
            put(x, y, v)
        y += 16
    # a label wrapped over three lines, its values on the middle one
    put(80, y, "Interest on Working")
    put(80, y + 16, "")
    for x, v in zip((315, 375, 435, 495), ["44.54", "70.53", "18.63", "8.82"], strict=True):
        put(x, y + 9, v)
    put(80, y + 18, "Capital")
    put(250, 800, "Electricity Regulatory Commission Page 471")
    doc.save(path)


@pytest.fixture()
def order_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "order.pdf"
    _page(p)
    return p


def test_reads_a_combined_order_table(order_pdf: Path) -> None:
    out = read_tables(str(order_pdf), ["NDC", "SDC"], {"NDC": ["North DISCOM"], "SDC": ["South DISCOM"]})
    assert out["pages"] == 1
    assert len(out["tables"]) == 1
    t = out["tables"][0]
    assert t["unit"] == "crore"
    cols = {c["index"]: (c["licensee"], c["voice"], c["fiscal_year"]) for c in t["columns"]}
    assert sorted(cols.values()) == sorted(
        [
            ("NDC", "claimed", "FY2026-27"),
            ("NDC", "approved", "FY2026-27"),
            ("SDC", "claimed", "FY2026-27"),
            ("SDC", "approved", "FY2026-27"),
        ]
    )
    by = {(ln["label"], cols[ln["column"]][0], cols[ln["column"]][1]): ln for ln in t["lines"]}
    assert by[("Power Purchase Cost", "SDC", "approved")]["value"] == 3060.91
    assert by[("Aggregate Revenue Requirement", "NDC", "approved")]["head"] == "arr"
    assert by[("Less: Non-Tariff Income", "NDC", "claimed")]["value"] == -417.43
    assert by[("Less: Non-Tariff Income", "NDC", "claimed")]["head"] == "nti"
    # the dash is a nil, not a value, and does not shift the columns after it
    assert ("Depreciation", "SDC", "claimed") not in by
    assert by[("Depreciation", "SDC", "approved")]["value"] == 128.42
    # every value keeps its page and the line as printed
    pp = by[("Power Purchase Cost", "NDC", "claimed")]
    assert pp["page"] == 1 and "4,597.53" in pp["quote"]
    # a wrapped label is joined around the values printed on its middle line
    assert by[("Interest on Working Capital", "NDC", "approved")]["value"] == 70.53
    assert by[("Interest on Working Capital", "NDC", "approved")]["head"] == "interest_wc"
    # the footer is not a row
    assert not any("Commission" in ln["label"] for ln in t["lines"])


def test_heads_follow_the_printed_label() -> None:
    assert head_of("Power Purchase Cost including Inter-State Transmission Charges") == "power_purchase"
    assert head_of("Intra-State Transmission including SLDC Charges") == "transmission"
    assert head_of("Less: Non-Tariff Income") == "nti"
    assert head_of("Interest on Working Capital") == "interest_wc"
    assert head_of("Interest on consumer security deposit") == "interest_sd"
    assert head_of("Tax on ROE") == "tax"
    assert head_of("Power Purchase Cost including RPO, Water Tax & Arrears") == "power_purchase"
    assert head_of("Net Revenue Requirement") == "net_arr"
    assert head_of("True up impact Gap/(Surplus)") == "regulatory_asset"
    assert head_of("Revenue Gap/(Surplus)") == "gap"
    assert head_of("Smart Meter OPEX Expenses") == "other"


def test_voices_and_years() -> None:
    assert voice_of("Claimed") == "claimed"
    assert voice_of("Admitted") == "approved"
    assert voice_of("Approved in MYT Order dated 15.03.24") == "approved_earlier"
    assert voice_of("Provisionally Trued up") == "approved_earlier"
    assert voice_of("Claimed in Final True up") == "claimed"
    assert voice_of("Particulars") is None
    assert years_in("FY24") == ["FY2023-24"]
    assert years_in("for FY 2026-27 to FY 2030-31") == ["FY2026-27", "FY2030-31"]


def test_arr_year_and_stage() -> None:
    assert (
        arr_year_of(
            {
                "title": "Case of MSEDCL for Truing-up of FY 2022-23 and MYT for the 5th Control Period "
                "from FY 2025-26 to FY 2029-30"
            }
        )
        == "FY2025-26"
    )
    assert arr_year_of({"title": "Tariff Order of UPCL for FY 2026-27"}) == "FY2026-27"
    assert stage_of("FY2026-27", "FY2026-27") == "ARR"
    assert stage_of("FY2025-26", "FY2026-27") == "APR"
    assert stage_of("FY2024-25", "FY2026-27") == "True-up"
    assert stage_of("FY2028-29", "FY2026-27") == "MYT projection"
