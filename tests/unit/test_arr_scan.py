"""The ARR taxonomy loads through its models; printed labels place on it by exact alias,
by the longest contained alias, by the licensee kind and by the table's unit, and never by
a guess; the scanner places table-like rows from page text and lists the rest as unplaced,
with the year and voice words seen in headers."""

from __future__ import annotations

import json
from pathlib import Path

from tariff_api.arr.scan import scan_exchange_folder, scan_texts, unit_context
from tariff_api.arr.taxonomy import Placer, load_mapping, load_taxonomy, mapping_files, norm_label, taxonomy_dir

PAGE = """CHAPTER 5: AGGREGATE REVENUE REQUIREMENT FOR FY 2026-27
5.3 Operation and Maintenance Expenses
Table 5-7: O&M expenses approved by the Commission (Rs. Crore)
Particulars FY 2024-25 (True-up) FY 2025-26 (APR) FY 2026-27 Petition FY 2026-27 Approved
Employee Expenses 412.10 430.55 471.20 452.00
Repairs & Maintenance Expenses 88.40 92.00 101.30 95.60
Administration & General Expenses 61.25 63.00 70.10 66.40
Total O&M Expenses 561.75 585.55 642.60 614.00
Provision for smart meter opex 0.00 4.20 12.00 9.50
Cost of fuel adjustment 10.00 11.00 12.00 12.00
Others 3.00 3.10 3.20 3.20
5.4 Power Purchase
Table 5-9: Energy available from sources (MU)
Solar 1,210.5 1,340.0 1,600.0 1,580.0
Wind 310.0 320.0 330.0 330.0
Table 5-10: Power purchase cost (Rs. Cr.)
Solar 402.3 438.1 520.0 512.4
"""


def test_taxonomy_and_mappings_load_and_no_alias_is_unresolvable():
    tax = load_taxonomy()
    assert tax.version >= 1 and len(tax.line_items) > 100
    for commission in ("UPERC", "KERC", "GERC"):
        m = load_mapping(commission)
        assert m.taxonomy_version == tax.version and m.commission == commission
        for kind in ("distribution", "transmission"):
            assert Placer(tax, m, kind).collisions() == {}
    assert set(mapping_files()) >= {"UPERC", "KERC", "GERC"}


def test_generated_schema_is_on_file():
    from tariff_api.arr.taxonomy import Mapping, Taxonomy

    on_file = json.loads((taxonomy_dir() / "schema.json").read_text())
    assert on_file["oneOf"] == [Taxonomy.model_json_schema(), Mapping.model_json_schema()], (
        "run: tariff-api arr-schema -o packages/arr-taxonomy/schema.json"
    )


def test_labels_normalise_and_place():
    assert norm_label("1. Employee Expenses (Rs. Crore):") == "employee expenses"
    assert norm_label("(a) Repairs & Maintenance") == "repairs and maintenance"
    assert norm_label("Less: Non-Tariff Income") == "less non tariff income"
    p = Placer(load_taxonomy(), load_mapping("UPERC"), "distribution")
    assert p.place("Employee Expenses").code == "C.OM.EMPLOYEE"
    assert p.place("Repairs & Maintenance Expenses").code == "C.OM.RM"
    assert p.place("Less: Non-Tariff Income").code == "L.NTI"
    assert p.place("Return on Equity").code == "C.RETURN.ROE"
    assert p.place("Revenue Gap / (Surplus)").code == "R.GAP"
    assert p.place("Transmission Charges").code == "C.TX"  # a cost in a distribution order
    assert p.place("Cost of fuel adjustment") is None
    assert p.place("Others") is None  # too common to be an alias
    assert p.place("Solar") is None and p.options("Solar") == ["C.PP.RE.SOLAR", "E.PP.QTY.RE.SOLAR"]
    assert p.place("Solar", "MU").code == "E.PP.QTY.RE.SOLAR"
    assert p.place("Solar", "INR_crore").code == "C.PP.RE.SOLAR"
    tx = Placer(load_taxonomy(), load_mapping("KERC"), "transmission")
    assert tx.place("Transmission Charges").code == "T.TARIFF.TOTAL"  # its own tariff in a transmission order


def test_a_commission_alias_outranks_the_generic_one():
    m = load_mapping("UPERC").model_copy(deep=True)
    m.label_aliases.entries.append({"label": "Provision for smart meter opex", "code": "C.OTHER.SMART_METER"})
    p = Placer(load_taxonomy(), m, "distribution")
    assert p.place("Provision for smart meter opex").code == "C.OTHER.SMART_METER"


def test_unit_context_from_headers_and_rows():
    assert unit_context("Table 5-7: O&M expenses approved (Rs. Crore)") == "INR_crore"
    assert unit_context("Energy available from sources (MU)") == "MU"
    assert unit_context("Employee Expenses 412.10") is None


def test_scanner_places_rows_and_lists_unplaced_with_years_and_voices():
    rep = scan_texts({5: PAGE}, commission="UPERC", licensee_kind="distribution").to_dict()
    assert rep["pages_scanned"] == 1
    placed = {r["key"]: r for r in rep["placed"]}
    assert placed["C.OM.EMPLOYEE"]["count"] == 1 and placed["C.OM.EMPLOYEE"]["pages"] == [5]
    assert "C.OM.RM" in placed and "C.OM.AG" in placed and "C.OM" in placed
    # the same "Solar" row is energy under the MU header and cost under the crore header
    assert placed["E.PP.QTY.RE.SOLAR"]["count"] == 1 and placed["C.PP.RE.SOLAR"]["count"] == 1
    assert placed["E.PP.QTY.RE.WIND"]["count"] == 1
    unplaced = {r["key"]: r for r in rep["unplaced"]}
    assert placed["C.OTHER.SMART_METER"]["how"] == "contains"  # "smart meter" inside a longer label
    assert "cost of fuel adjustment" in unplaced and unplaced["cost of fuel adjustment"]["pages"] == [5]
    assert "others" in unplaced
    assert rep["rows_seen"] == rep["placed_rows"] + rep["unplaced_rows"] + sum(r["count"] for r in rep["ambiguous"])
    assert set(rep["year_columns_seen"]) >= {"FY2024-25", "FY2025-26", "FY2026-27"}
    assert {"petition", "approved", "true-up", "apr"} <= set(rep["voice_words_seen"])
    assert any(c["branch"] == "C.OM" for c in rep["chapters"])


def test_scanner_reads_an_exchange_folder(tmp_path: Path):
    folder = tmp_path / "UPERC" / "NPCL-test"
    folder.mkdir(parents=True)
    (folder / "source.json").write_text(json.dumps({"commission": "UPERC", "utility": "NPCL"}))
    (folder / "page_texts.json").write_text(json.dumps({"page_count": 1, "texts": {"5": PAGE}}))
    rep = scan_exchange_folder(folder)
    assert rep.commission == "UPERC" and rep.rows_seen > 5
