"""Clause-outline reconstruction against the Part F gate items (F.3, M3): RGP, AG and HTP-1
over the fixture text in tests/fixtures/text/gerc_clauses.txt."""

from __future__ import annotations

from pathlib import Path

import pytest

from tariff_api.clause_outline import CLAUSE_VERSION, reconstruct, summarise

TEXT = (Path(__file__).resolve().parents[1] / "fixtures" / "text" / "gerc_clauses.txt").read_text()


@pytest.fixture(scope="module")
def outline():
    return reconstruct([(7, TEXT)])


def _vals(outline, code, role=None, kind="value"):
    return [
        v for v in outline.values if v.category_code == code and (role is None or v.role == role) and v.kind == kind
    ]


def test_rgp_fixed_charges_are_per_connection_keyed_to_load_ranges(outline):
    fixed = _vals(outline, "RGP", "fixed")
    assert [v.normalised["value"] for v in fixed] == ["15", "25", "45", "70"]
    assert all(v.normalised["per_unit"] == "connection" and v.normalised["frequency"] == "per_month" for v in fixed)
    assert [(v.slab["lower"], v.slab["upper"]) for v in fixed] == [(None, "2"), ("2", "4"), ("4", "6"), ("6", None)]
    assert fixed[0].slab["inclusivity"] == "explicit"  # "up to and including 2 kW"
    assert fixed[0].clause_path == ["1. RATE: RGP", "1.1. FIXED CHARGES / MONTH", fixed[0].line_text]


def test_rgp_energy_charges_are_telescopic_with_two_metering_columns(outline):
    energy = _vals(outline, "RGP", "energy")
    assert len(energy) == 8  # four slabs x post-paid / pre-paid
    assert [v.dimension["metering_type"] for v in energy] == ["post_paid", "pre_paid"] * 4
    assert [v.normalised["value"] for v in energy] == ["305", "296", "350", "340", "415", "403", "520", "504"]
    assert all(v.normalised["currency"] == "paise" and v.normalised["per_unit"] == "unit" for v in energy)
    assert [v.slab["kind"] for v in energy[::2]] == ["telescopic_first", "telescopic_next", "telescopic_next", "open"]
    assert energy[0].connector == "PLUS"  # the energy block is joined to the fixed block, not an alternative


def test_rgp_bpl_subclass_has_one_value_and_one_cross_reference(outline):
    bpl = [v for v in outline.values if v.category_code == "RGP" and "1.3. BPL CONSUMERS" in v.clause_path]
    assert [(v.kind, v.normalised.get("value"), v.normalised.get("reference")) for v in bpl] == [
        ("value", "150", None),
        ("cross_reference", None, "RGP"),
    ]


def test_rgp_tou_discount_is_a_negative_absolute_adjustment_with_a_window(outline):
    (tou,) = _vals(outline, "RGP", "rebate")
    assert tou.normalised["value"] == "60" and tou.normalised["currency"] == "paise"
    assert tou.sign == -1 and tou.time_window == "11:00-17:00"
    assert "smart meters" in tou.line_text


def test_ag_is_one_option_group_with_three_alternatives(outline):
    ag = next(c for c in outline.categories if c.code == "AG")
    assert ag.alternatives == 3
    opts = _vals(outline, "AG", "option")
    assert [(v.alternative, v.connector, v.normalised["value"]) for v in opts] == [
        (0, None, "200"),
        (1, "ALTERNATIVELY", "20"),
        (1, "PLUS", "60"),
        (2, "ALTERNATIVELY", "20"),
        (2, "PLUS", "80"),
    ]
    assert opts[0].normalised["per_unit"] == "HP" and opts[2].normalised["currency"] == "paise"
    brick = [v for v in outline.values if v.category_code == "AG" and v.role == "other"]
    assert brick[0].alternative == 0  # 8.2 closes the 8.1.x option group
    assert (brick[0].normalised["frequency"], brick[0].normalised["per_unit"]) == ("per_annum", "kW")


def test_htp1_demand_charges_are_tiered_within_contract_plus_an_excess_rate(outline):
    demand = _vals(outline, "HTP-1", "demand")
    assert [v.normalised["value"] for v in demand] == ["150", "250", "400", "555"]
    assert all(v.normalised["per_unit"] == "kVA" and v.normalised["frequency"] == "per_month" for v in demand)
    assert "11.1.1. For billing demand up to contract demand" in demand[0].clause_path
    assert demand[3].clause_path[-1].startswith("11.1.2. For billing demand in excess of the contract demand")
    assert demand[0].slab["kind"] == "telescopic_first" and demand[0].slab["upper"] == "500"


def test_htp1_energy_and_tou_are_keyed_to_billing_demand_bands(outline):
    energy = _vals(outline, "HTP-1", "energy")
    assert [(v.normalised["value"], v.slab["lower"], v.slab["upper"]) for v in energy] == [
        ("400", None, "500"),
        ("420", "500", "2500"),
        ("430", "2500", None),
    ]
    tou = _vals(outline, "HTP-1", "tou_surcharge")
    assert [(v.normalised["value"], v.sign) for v in tou] == [("45", 1), ("85", 1)]
    assert tou[0].time_window == "07:00-11:00"  # first window recorded; the line keeps both
    assert "18:00 to 22:00" in tou[0].line_text


def test_htp1_billing_demand_is_a_condition_and_power_factor_is_percent_of_bill(outline):
    (cond,) = _vals(outline, "HTP-1", kind="condition")
    assert cond.role == "condition" and cond.normalised == {} and cond.parameters == ["85% of the contract demand"]
    pf = _vals(outline, "HTP-1", "power_factor")
    assert [(v.normalised["value"], v.normalised["percent_of"], v.parameters) for v in pf] == [
        ("1", "energy charge bill", ["1%", "90%", "85%"]),
        ("0.5", "energy charge bill", ["1%", "95%"]),
    ]
    assert all(v.normalised["percent"] and v.normalised["currency"] is None for v in pf)


def test_summary_and_no_unresolved_lines(outline):
    s = summarise(outline)
    assert s["version"] == CLAUSE_VERSION
    assert s["categories"] == 3 and s["option_groups"] == 1 and s["cross_references"] == 1 and s["conditions"] == 1
    assert s["unresolved_lines"] == 0 and s["currency_unresolved"] == 0


def test_amount_before_any_category_is_unresolved_not_guessed():
    o = reconstruct([(1, "GENERAL\n3. Minimum charges of Rs. 50/- per month apply.\n")])
    assert o.values == [] and o.unresolved_lines and o.unresolved_lines[0]["page_index"] == 1
