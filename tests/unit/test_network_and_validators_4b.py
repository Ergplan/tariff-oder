"""Milestone 4b rules: network-charge grids into typed facts with derivation inputs, green
tariff prose, condition records, and the four validators that need them (amendment
consistency, derivation checks, condition links, cross-representation agreement)."""

from __future__ import annotations

from tariff_api import validators as V
from tariff_api.extraction import StructureInput, extract_conditions, green_tariff_prose, network_extract
from tariff_api.grid_integrity import GridInput, analyse_grids
from tariff_api.tariff_schema import Applicability, Candidate, EvidenceRef


def _cells(records, role):
    out = []
    for r in records:
        for c in r.cells:
            d = c.to_dict()
            d["value_state"] = d["normalised"]["value_state"]
            d["region_role"] = role
            out.append(d)
    return out


def _inp(cells, role, sub_role=None, texts=None, headings=None, clauses=None):
    return StructureInput(
        source_sha="c" * 64,
        profile_id="uperc-npcl",
        schedule_heading_kind="rate_schedule",
        region_role=role,
        region_ordinal=2,
        page_indices=sorted({c["page_index"] for c in cells} or {1}),
        cells=cells,
        clauses=clauses or [],
        headings=headings or [],
        page_texts=texts or {},
        period="FY2026-27",
        utility="NPCL",
        utilities=["NPCL"],
    )


def test_wheeling_working_table_yields_one_charge_with_arr_and_sales_as_derivation():
    g = GridInput(
        4,
        0,
        [
            ["Particulars", "Value"],
            ["Wheeling ARR (Rs Cr)", "451.70"],
            ["Sales (MU)", "4399.84"],
            ["Average Wheeling Charge (Rs/kWh)", "1.03"],
        ],
        1,
    )
    out = network_extract(
        _inp(_cells(analyse_grids([g]), "network_charges"), "network_charges", "wheeling_charge"), "wheeling_charge"
    )
    (w,) = out.candidates
    assert w.family == "wheeling_charge" and w.value == "1.03" and w.decision_status == "approved"
    assert (w.currency, w.per_unit) == ("rupees", "kWh")
    assert w.derivation["rule"] == "arr_over_sales" and w.derivation["inputs"]["arr"]["value"] == "451.70"
    assert w.derivation["inputs"]["sales"]["value"] == "4399.84" and w.evidence[0].excerpt == "1.03"
    (f,) = [
        x for x in V.val_07_derivation_checks(V.ValidationContext([w], {}, {}, {}, [])) if x.validator_id == "VAL-07"
    ]
    assert f.severity == "info" and f.detail["computed"] == "1.0266"  # 451.70 Cr / 4399.84 MU
    w.value = "1.30"
    (f,) = V.val_07_derivation_checks(V.ValidationContext([w], {}, {}, {}, []))
    assert f.severity == "blocking" and "ARR/sales gives 1.0266" in f.message  # flagged, never corrected


def test_losses_are_filed_by_region_role_never_by_number():
    g = GridInput(
        5,
        0,
        [["Level", "Loss (%)"], ["Inter-state transmission", "3.58"], ["11 kV", "2.58"], ["Below 11 kV", "6.97"]],
        1,
    )
    oa = network_extract(
        _inp(_cells(analyse_grids([g]), "network_charges"), "network_charges", "oa_loss"), "oa_loss"
    ).candidates
    assert [(c.family, c.value, c.per_unit, c.applicability.voltage) for c in oa] == [
        ("oa_loss", "3.58", "percent", "Inter-state transmission"),
        ("oa_loss", "2.58", "percent", "11 kV"),
        ("oa_loss", "6.97", "percent", "Below 11 kV"),
    ]
    t = GridInput(3, 0, [["Particulars", "FY2025-26", "FY2026-27"], ["Distribution loss (%)", "8.00", "7.48"]], 1)
    arr = network_extract(_inp(_cells(analyse_grids([t]), "loss_trajectory"), "loss_trajectory"), None).candidates
    assert [(c.family, c.value, c.period) for c in arr] == [
        ("distribution_loss_approved", "8.00", "FY2025-26"),
        ("distribution_loss_approved", "7.48", "FY2026-27"),
    ]
    assert all(c.component_type == "loss" and c.currency is None for c in oa + arr)


def test_css_table_only_the_approved_column_is_a_candidate_and_lower_of_is_checked():
    g = GridInput(
        6,
        0,
        [
            ["Category", "Voltage", "Last year approved (A)", "Computed (C)", "Approved (Lower of A & C)"],
            ["LMV-2", "11 kV", "1.50", "1.33", "1.33"],
            ["HV-2", "33 kV", "1.20", "1.45", "1.45"],
            ["HV-1", "132 kV", "-", "0.90", "-"],
        ],
        1,
    )
    out = network_extract(
        _inp(_cells(analyse_grids([g]), "network_charges"), "network_charges", "cross_subsidy_surcharge"),
        "cross_subsidy_surcharge",
    )
    by = {c.category_code: c for c in out.candidates}
    assert set(by) == {"LMV-2", "HV-2", "HV-1"}
    assert by["LMV-2"].value == "1.33" and by["LMV-2"].derivation["rule"] == "lower_of"
    assert set(by["LMV-2"].derivation["inputs"].values()) == {"1.50", "1.33"}
    assert by["HV-1"].value_state == "not_applicable" and by["HV-1"].value is None  # `-` never zero (N6)
    assert by["HV-2"].applicability.voltage == "33 kV"
    f = {
        x.candidate_keys[0]: x
        for x in V.val_07_derivation_checks(V.ValidationContext(list(by.values()), {}, {}, {}, []))
    }
    assert f[by["LMV-2"].key()].severity == "info"
    assert f[by["HV-2"].key()].severity == "blocking" and "not the lower" in f[by["HV-2"].key()].message
    assert by["HV-1"].key() not in f  # nothing to recompute for a not-applicable row


def test_green_tariff_prose_yields_scoped_premiums_with_the_exclusion_condition():
    text = (
        "20. Green Energy Tariff: Rs 0.34 per unit for HV categories and Rs 0.17 per unit for LMV categories,\n"
        "in addition to the regular tariff. 20(f) The regulatory discount shall not be applicable to the Green Tariff.\n"
    )
    out = green_tariff_prose(_inp([], "approved_schedule", texts={8: text}))
    assert [(c.value, c.applicability.voltage, c.currency, c.per_unit) for c in out] == [
        ("0.34", "HV", "rupees", "unit"),
        ("0.17", "LMV", "rupees", "unit"),
    ]
    assert all(c.family == "green_tariff" and c.decision_status == "approved" for c in out)
    assert all("regulatory discount shall not be applicable" in c.conditions[0] for c in out)
    kerc = green_tariff_prose(
        _inp(
            [],
            "green_tariff",
            texts={9: "Green tariff of 50 paise per unit for HT industrial and commercial consumers.\n"},
        )
    )
    assert (
        kerc
        and kerc[0].value == "50"
        and kerc[0].currency == "paise"
        and kerc[0].applicability.voltage.startswith("HT industrial")
    )


def test_condition_records_are_verbatim_with_scope_codes():
    text = (
        "A. GENERAL PROVISIONS\n"
        "20. Green Energy Tariff: Rs 0.34 per unit for HV categories and Rs 0.17 per unit for LMV categories.\n"
        "21. A regulatory discount of 10% shall apply to fixed / demand and energy charges of all consumers.\n"
        "22. An unmetered consumer under LMV-5 with no tariff here is billed at the FY 2023-24 rate.\n"
    )
    g = GridInput(
        9,
        0,
        [["Description", "Energy Charge"], ["Metered", "Rs. 7.50/ kWh *"]],
        1,
        footnote_lines=["* subject to the regulatory discount of general provision 21"],
    )
    cells = _cells(analyse_grids([g]), "approved_schedule")
    inp = _inp(
        cells,
        "approved_schedule",
        texts={8: text, 9: "RATE SCHEDULE LMV - 2\n"},
        headings=[
            {"page_index": 9, "kind": "rate_schedule", "code_canonical": "LMV-2", "text": "RATE SCHEDULE LMV - 2"}
        ],
    )
    recs = extract_conditions(inp)
    gp = [r for r in recs if r.kind == "general_provision"]
    assert [r.number for r in gp] == ["20", "21", "22"] and gp[2].scope_codes == ["LMV-5"]
    assert all(r.interpretation_status == "verbatim_only" for r in recs)
    fn = [r for r in recs if r.kind == "footnote"]
    assert fn and fn[0].text.startswith("subject to the regulatory discount")
    # VAL-12: a candidate condition must be a recorded condition or footnote
    c = Candidate(
        family="retail_tariff",
        category_code="LMV-2",
        component_type="energy",
        value="7.50",
        value_state="value",
        original_text="Rs. 7.50/ kWh *",
        currency="rupees",
        per_unit="kWh",
        conditions=["subject to the regulatory discount of general provision 21", "some condition nobody recorded"],
        evidence=[EvidenceRef(page_index=9, kind="cell", grid_ordinal=0, row=1, col=1, excerpt="Rs. 7.50/ kWh *")],
    )
    f = V.val_12_condition_links(V.ValidationContext([c], {}, {}, {}, [], condition_texts=[r.text for r in recs]))
    assert len(f) == 1 and "nobody recorded" in f[0].message


def test_val05_amendment_consistency_against_the_consolidated_schedule():
    schedule = {
        5: "1.4. TIME OF USE DISCOUNT\nConsumers with smart meters shall get a concession of 60 Paise per Unit for consumption between 11:00 hrs to 17:00 hrs.\n"
    }
    rows = [
        {
            "page": 2,
            "grid": 0,
            "row": 1,
            "existing": "consumption between 11:00 hrs to 15:00 hrs",
            "modified": "consumption between 11:00 hrs to 17:00 hrs",
        },
        {
            "page": 2,
            "grid": 0,
            "row": 2,
            "existing": "consumption between 11:00 hrs to 16:00 hrs",
            "modified": "consumption between 11:00 hrs to 18:00 hrs",
        },
    ]
    f = V.val_05_amendment_consistency(
        V.ValidationContext([], {}, {}, {}, [], approved_page_texts=schedule, amendment_rows=rows)
    )
    assert [(x.severity, x.detail["row"]) for x in f] == [("info", 1), ("blocking", 2)]
    stale = [
        {
            "page": 2,
            "grid": 0,
            "row": 1,
            "existing": "consumption between 11:00 hrs to 17:00 hrs",
            "modified": "consumption between 11:00 hrs to 19:00 hrs",
        }
    ]
    f = V.val_05_amendment_consistency(
        V.ValidationContext([], {}, {}, {}, [], approved_page_texts=schedule, amendment_rows=stale)
    )
    assert any("superseded" in x.message for x in f)  # the schedule still carries the old text


def _cand(cat, comp, value, page, currency="paise"):
    return Candidate(
        family="retail_tariff",
        category_code=cat,
        component_type=comp,
        value=value,
        value_state="value",
        original_text=value,
        currency=currency,
        per_unit="unit",
        period="FY2025-26",
        evidence=[EvidenceRef(page_index=page, kind="cell", grid_ordinal=0, row=1, col=1, excerpt=value)],
    )


def test_val16_cross_representation_blocks_a_disagreeing_cell_and_records_agreement():
    roles = {2: {"approved_summary"}, 6: {"approved_schedule"}, 7: {"approved_schedule"}}
    cands = [
        _cand("LT-1", "energy", "580", 2),
        _cand("LT-1", "energy", "580", 6),
        _cand("LT-2", "energy", "585", 2),
        _cand("LT-2", "energy", "650", 7),
    ]
    f = V.val_16_cross_representation(V.ValidationContext(cands, roles, {}, {}, [], secondary_authoritative=True))
    by = {x.severity: x for x in f}
    assert "agree (580)" in by["info"].message and "585" in by["blocking"].message and "650" in by["blocking"].message
    assert len(by["blocking"].candidate_keys) == 2  # both records blocked until reviewed
    assert (
        V.val_16_cross_representation(V.ValidationContext(cands, roles, {}, {}, [], secondary_authoritative=False))
        == []
    )
    only_schedule = V.val_16_cross_representation(
        V.ValidationContext(cands[1:2], roles, {}, {}, [], secondary_authoritative=True)
    )
    assert only_schedule and "no summary candidates" in only_schedule[0].message


def test_network_candidates_carry_single_channel_risk_and_pass_field_checks():
    from tariff_api.extraction import Compared, route

    c = Candidate(
        family="oa_loss",
        component_type="loss",
        value="6.97",
        value_state="value",
        original_text="6.97",
        per_unit="percent",
        decision_status="approved",
        applicability=Applicability(voltage="Below 11 kV"),
        evidence=[EvidenceRef(page_index=5, kind="cell", grid_ordinal=0, row=3, col=1, excerpt="6.97")],
    )
    r = route(Compared(c.key(), c, None, "single_channel"), [], ocr_page=False, new_profile=False)
    assert r.confidence == "medium" and r.routing == "individual" and "single_channel" in r.risk_tags
    assert V.val_01_field_types(V.ValidationContext([c], {}, {}, {}, [])) == []
    assert V.val_09_unit_sanity_per_family(V.ValidationContext([c], {}, {}, {}, [])) == []
