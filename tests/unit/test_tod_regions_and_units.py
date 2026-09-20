"""Rules 4 pairing and de-duplication: a time-of-day row is named by its band however the
hours are printed; a season heading above a table is not a block; a unit missing on one
side does not keep two readings of one fact apart; the same fact read in two overlapping
regions survives once; the model's outer block pairs with the rules' inner sub-block when
the row is unambiguous; different seasons and different values never collapse."""

from __future__ import annotations

from tariff_api.extraction import (
    Compared,
    _blocks_compatible,
    compare_channels,
    dedupe_compared,
    merge_duplicates,
    norm_time_band,
)
from tariff_api.tariff_schema import Applicability, Candidate, EvidenceRef, ExtractionOutput


def _c(
    value,
    *,
    kind="cell",
    page=374,
    block=None,
    desc=None,
    tb=None,
    season=None,
    unit="percent",
    sign=None,
    comp="tod_adjustment",
    cat="LMV-6",
    line=None,
    grid=0,
    voltage=None,
):
    return Candidate(
        family="retail_tariff",
        category_code=cat,
        component_type=comp,
        value=value,
        value_state="value",
        original_text=value,
        per_unit=unit,
        sign=sign,
        applicability=Applicability(rate_block=block, description=desc, time_band=tb, season=season, voltage=voltage),
        evidence=[
            EvidenceRef(
                page_index=page,
                kind=kind,
                grid_ordinal=grid if kind == "cell" else None,
                row=1,
                col=1,
                line_no=line,
                excerpt=value,
            )
        ],
    )


def test_time_bands_normalise_however_the_hours_are_printed():
    assert norm_time_band("19:00 hrs – 02:00 hrs") == "19:00-02:00"
    assert norm_time_band("19:00-02:00") == "19:00-02:00"
    assert norm_time_band("7.00 to 15.00 hrs") == "07:00-15:00"
    assert norm_time_band("Summer months") == ""


def test_season_heading_is_not_a_block_but_two_seasons_are_two_rows():
    assert _blocks_compatible("(A) Time of day", "Summer Months (April to September)")
    assert _blocks_compatible("Summer Months (April to September)", None)
    assert not _blocks_compatible("Summer Months (April to September)", "Winter Months (October to March)")


def test_tod_row_from_table_and_clause_under_a_season_heading_is_one_candidate():
    table = _c("15", block="(A) ToD rates", tb="19:00 hrs – 02:00 hrs", sign=1)
    clause = _c("15", kind="clause", block="Summer Months (April to September)", tb="19:00-02:00", sign=1, line=12)
    out = merge_duplicates([table, clause])
    assert len(out) == 1
    assert out[0].evidence[0].kind == "cell"
    assert len(out[0].evidence) == 2
    assert "Also printed at page 374 line 12" in (out[0].notes or "")


def test_different_seasons_with_the_same_number_stay_apart():
    summer = _c("15", tb="19:00-02:00", season="Summer", sign=1)
    winter = _c("15", tb="19:00-02:00", season="Winter", sign=1)
    assert len(merge_duplicates([summer, winter])) == 2


def test_unit_missing_on_one_side_is_a_wildcard_and_the_survivor_keeps_the_unit():
    a = _c("10", comp="fixed", cat="LMV-9", desc="per connection per day", unit="connection", block="(a) Temporary")
    b = _c("10", comp="fixed", cat="LMV-9", desc="per day", unit=None, kind="clause", line=3)
    out = merge_duplicates([a, b])
    assert len(out) == 1
    assert out[0].per_unit == "connection"
    kw = _c("100", comp="fixed", cat="HV-1", desc="Metered", unit="kW")
    kva = _c("100", comp="fixed", cat="HV-1", desc="Metered", unit="kVA")
    assert len(merge_duplicates([kw, kva])) == 2


def test_same_fact_read_in_two_regions_survives_once_preferring_the_agreeing_cell():
    rail_a = _c("6.50", comp="energy", cat="HV-3", desc="Traction", unit="kVAh", page=380)
    rail_b = _c("6.50", comp="energy", cat="HV-3", desc="Traction", unit="kVAh", page=380, kind="clause", line=8)
    lone = Compared(rail_b.key(), rail_b, None, "one_missing")
    agreed = Compared(rail_a.key(), rail_a, rail_a.model_copy(deep=True), "agree")
    out = dedupe_compared([lone, agreed])
    assert len(out) == 1
    assert out[0].agreement == "agree"
    assert len(out[0].primary.evidence) == 2
    assert "Also read at page 380 line 8" in (out[0].primary.notes or "")
    other = _c("7.00", comp="energy", cat="HV-3", desc="Traction", unit="kVAh", page=380)
    assert len(dedupe_compared([lone, Compared(other.key(), other, None, "one_missing")])) == 2


def test_model_outer_block_pairs_with_rules_inner_block_when_the_row_is_unambiguous():
    rules = ExtractionOutput(
        candidates=[
            _c("110", comp="fixed", cat="LMV-5", block="(ii) Rural Schedule", desc="Metered", unit="kW"),
            _c("6.50", comp="energy", cat="LMV-5", block="(ii) Rural Schedule", desc="Metered", unit="kWh"),
        ]
    )
    model = ExtractionOutput(
        candidates=[
            _c("110", comp="fixed", cat="LMV-5", block="(A) Private Tube Wells", desc="Metered", unit="kW"),
            _c("6.50", comp="energy", cat="LMV-5", block="(A) Private Tube Wells", desc="Metered", unit="kWh"),
        ]
    )
    out = compare_channels(rules, model)
    assert [x.agreement for x in out] == ["agree", "agree"]


def test_ambiguous_rows_across_blocks_are_not_paired():
    rules = ExtractionOutput(
        candidates=[
            _c("110", comp="fixed", cat="LMV-5", block="(ii) Rural", desc="Metered", unit="kW"),
            _c("120", comp="fixed", cat="LMV-5", block="(iii) Urban", desc="Metered", unit="kW"),
        ]
    )
    model = ExtractionOutput(
        candidates=[_c("110", comp="fixed", cat="LMV-5", block="(A) Tube wells", desc="Metered", unit="kW")]
    )
    out = compare_channels(rules, model)
    assert sorted(x.agreement for x in out) == ["one_missing", "one_missing", "one_missing"]


def test_tod_rows_pair_across_channels_on_the_band():
    rules = ExtractionOutput(candidates=[_c("15", block="(A) ToD", tb="19:00 hrs – 02:00 hrs", sign=1)])
    model = ExtractionOutput(candidates=[_c("15", block="(a)", tb="19:00-02:00", desc="Peak hours", sign=1)])
    out = compare_channels(rules, model)
    assert [x.agreement for x in out] == ["agree"]
