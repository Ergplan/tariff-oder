"""Section 6.7 normalisation rules, one test per rule family, plus the slab parser and the
adjacent-slab ambiguity check.  Every value-level failure mode of 6.1 has a case here."""

from __future__ import annotations

import pytest

from tariff_api.normalise import NORMALISE_VERSION, check_slab_sequence, normalise_value, parse_slab


@pytest.mark.parametrize(
    ("text", "state", "value", "currency", "unit", "freq"),
    [
        ("Rs. 8.32 / kVAh", "value", "8.32", "rupees", "kVAh", None),
        ("Rs. 7.50/ kVAh", "value", "7.50", "rupees", "kVAh", None),  # D.2 hazard 7: inconsistent spacing
        ("Rs. 7.70 / kVAh", "value", "7.70", "rupees", "kVAh", None),
        ("Rs. 90.00/ kW / month", "value", "90.00", "rupees", "kW", "per_month"),
        ("Rs. 430.00 / kVA / month", "value", "430.00", "rupees", "kVA", "per_month"),
        ("Rs. 160.00 per BHP per month", "value", "160.00", "rupees", "BHP", "per_month"),
        ("Rs. 3.00/ kWh", "value", "3.00", "rupees", "kWh", None),
        ("580 paise", "value", "580", "paise", None, None),  # E.1: paise energy charge
        ("Rs.145/-", "value", "145", "rupees", None, None),  # E.1: rupee fixed charge with /-
        ("305 Paise per Unit", "value", "305", "paise", "unit", None),  # F.1
        ("Rs. 90/-per kW per month", "value", "90", "rupees", "kW", "per_month"),
        ("Rs. 150/- per kVA per month", "value", "150", "rupees", "kVA", "per_month"),
        ("Rs. 200 per HP per month", "value", "200", "rupees", "HP", "per_month"),
        ("Rs. 1800 per annum per kW", "value", "1800", "rupees", "kW", "per_annum"),  # F.2 hazard 13
        ("6.50", "value", "6.50", None, None, None),
        ("650", "value", "650", None, None, None),  # not the same as 6.50: no unit means no currency guess
        ("6.50/-", "value", "6.50", None, None, None),
        ("1,00,000", "value", "100000", None, None, None),  # Indian grouping
        ("1,000.50", "value", "1000.50", None, None, None),
    ],
)
def test_currency_unit_and_number_forms(text, state, value, currency, unit, freq):
    n = normalise_value(text)
    assert (n.value_state, n.value, n.currency, n.per_unit, n.frequency) == (state, value, currency, unit, freq)
    assert n.original_text == text and n.version == NORMALISE_VERSION and n.rules


def test_per_connection_charge_is_not_per_kw():
    n = normalise_value("Rs. 15/- per month")  # F.2 hazard 4: per connection with a load-range applicability
    assert (n.value, n.per_unit, n.frequency) == ("15", "connection", "per_month")
    assert "per_connection_inferred" in n.flags
    assert normalise_value("Rs. 90/-per kW per month").per_unit == "kW"


@pytest.mark.parametrize(
    ("text", "state", "flags", "markers"),
    [
        ("Nil", "zero", ["nil_word"], []),
        ("-", "not_applicable", [], []),
        ("–", "not_applicable", [], []),
        ("NA", "not_applicable", [], []),
        ("N.A.", "not_applicable", [], []),
        ("Not applicable", "not_applicable", [], []),
        ("", "unknown", [], []),
        ("   ", "unknown", [], []),
        ("*", "footnote_only", [], ["*"]),
        ("**", "footnote_only", [], ["**"]),
        ("#", "footnote_only", [], ["#"]),
    ],
)
def test_nil_dash_na_blank_and_markers_are_never_zero_numbers(text, state, flags, markers):
    n = normalise_value(text)
    assert n.value_state == state and n.value is None
    assert n.flags == flags and n.footnote_markers == markers


def test_zero_forms_are_state_zero_with_the_number_kept():
    for t in ("0", "0.00", "0%", "0 %"):
        n = normalise_value(t)
        assert n.value_state == "zero" and n.value == "0" or n.value == "0.00", t
    assert normalise_value("0.00").value == "0.00"  # D.2 hazard 3: Annexure-II 0.00 rows stay distinguishable


def test_footnote_markers_are_stripped_and_kept():
    n = normalise_value("Rs. 2.50/kWh *")
    assert n.value == "2.50" and n.footnote_markers == ["*"] and n.per_unit == "kWh"
    n = normalise_value("#1.33")
    assert n.value == "1.33" and n.footnote_markers == ["#"]


@pytest.mark.parametrize(
    ("text", "value", "sign", "base"),
    [
        ("(+) 15%", "15", 1, None),
        ("(-) 15%", "15", -1, None),
        ("+20%", "20", 1, None),
        ("-15 %", "15", -1, None),
        ("15%", "15", None, None),
        ("1% of energy charge bill", "1", None, "energy charge bill"),
        ("0.5% of the energy charges", "0.5", None, "energy charges"),
    ],
)
def test_percentages_keep_sign_and_named_base(text, value, sign, base):
    n = normalise_value(text)
    assert n.percent and n.value == value and n.sign == sign and n.percent_of == base
    assert n.currency is None and n.per_unit is None  # a percentage is never a rupee rate (D.2 hazard 6)


def test_parenthesised_negative_and_bracketed_secondary_value():
    assert normalise_value("(12.5)").value == "-12.5"
    n = normalise_value("122 (12.84)")  # injection/drawal matrix: charge with the loss beside it
    assert n.value == "122" and n.flags == ["bracketed_secondary_value:12.84"]


def test_stray_space_in_decimal_is_read_and_flagged():
    n = normalise_value("6 .50")
    assert n.value == "6.50" and "stray_space_in_number" in n.flags


def test_cross_references_and_formulae_are_states_not_numbers():
    for text, target in (
        ("as applicable to LMV-1", "LMV-1"),
        ("same as HV-2", "HV-2"),
        ("Rate as per RGP", "RGP"),
        ("as per Regulation 12 of the Supply Code", "Regulation 12 of the Supply Code"),
    ):
        n = normalise_value(text)
        assert n.value_state == "cross_reference" and n.reference == target and n.value is None
    n = normalise_value("FPPAS = (A + B) / C x 100")
    assert n.value_state == "formula" and n.value is None


def test_unparsed_text_is_unknown_and_flagged_never_guessed():
    n = normalise_value("see note below")
    assert n.value_state == "unknown" and n.value is None and "unparsed_text" in n.flags


def test_currency_conflict_is_flagged():
    n = normalise_value("Rs. 50 paise")
    assert "currency_conflict" in n.flags


# ------------------------------------------------------------------ slabs


@pytest.mark.parametrize(
    ("text", "lower", "upper", "li", "ui", "incl", "kind", "unit"),
    [
        ("Up to 100 kWh / month", None, "100", None, True, "inferred", "absolute", "kWh"),
        ("101 - 150 kWh / month", "101", "150", True, True, "inferred", "absolute", "kWh"),
        ("151 – 300 kWh / month", "151", "300", True, True, "inferred", "absolute", "kWh"),
        ("Above 300 kWh / month", "300", None, False, None, "inferred", "open", "kWh"),
        ("up to and including 2 kW", None, "2", None, True, "explicit", "absolute", "kW"),
        ("Above 2 to 4 kW", "2", "4", False, True, "inferred", "absolute", "kW"),
        ("First 50 units", "0", "50", True, True, "inferred", "telescopic_first", "unit"),
        ("Next 150 Units", None, "150", False, True, "inferred", "telescopic_next", "unit"),
        (">300", "300", None, False, None, "explicit", "open", None),
        (">= 300", "300", None, True, None, "explicit", "open", None),
        ("100 HP and above", "100", None, True, None, "explicit", "open", "HP"),
        ("Below 100 HP", None, "100", None, False, "explicit", "absolute", "HP"),
        ("Upto 50 KW", None, "50", None, True, "inferred", "absolute", "kW"),
    ],
)
def test_slab_parser(text, lower, upper, li, ui, incl, kind, unit):
    b = parse_slab(text)
    assert b is not None, text
    assert (b.lower, b.upper, b.lower_inclusive, b.upper_inclusive, b.inclusivity, b.kind, b.unit) == (
        lower,
        upper,
        li,
        ui,
        incl,
        kind,
        unit,
    )


def test_slab_bound_by_reference_and_non_slab_text():
    b = parse_slab("For billing demand in excess of the contract demand")
    assert b is not None and b.reference == "contract_demand" and b.lower is None and b.kind == "open"
    assert parse_slab("Fixed Charge") is None and parse_slab("") is None


def test_adjacent_slabs_claiming_one_boundary_become_ambiguous():
    seq = check_slab_sequence([parse_slab("up to 100"), parse_slab("100 - 300"), parse_slab("above 300")])
    assert [b.inclusivity for b in seq] == ["ambiguous", "ambiguous", "inferred"]
    assert "S10.boundary_claimed_twice" in seq[0].rules
    clean = check_slab_sequence([parse_slab("up to 100"), parse_slab("101 - 300"), parse_slab("above 300")])
    assert [b.inclusivity for b in clean] == ["inferred", "inferred", "inferred"]
    gap = check_slab_sequence([parse_slab("up to 100"), parse_slab("above 101")])  # 101 itself is uncovered
    assert gap[0].inclusivity == "ambiguous" and "S11.gap_between_slabs" in gap[1].rules
    explicit = check_slab_sequence([parse_slab("up to and including 100"), parse_slab("above 100")])
    assert [b.inclusivity for b in explicit] == ["explicit", "inferred"]  # explicit wording is never downgraded
