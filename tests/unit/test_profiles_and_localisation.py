"""Milestone 3a rules as pure functions: reading profiles load, validate and detect; the
localisation rules place every region of the three layout fixtures with a cue, refuse to
resolve ambiguity, and never open a region from a contents page."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from pydantic import ValidationError

from fixtures.synthetic_pdfs import gerc_like_order_pdf, kerc_like_order_pdf, uperc_like_order_pdf
from tariff_api import headings as H
from tariff_api import profiles as P
from tariff_api.localisation import PageInfo, is_contents_page, localise

REPO = Path(__file__).resolve().parents[2]


def _pages(data: bytes) -> list[PageInfo]:
    doc = pymupdf.open(stream=data, filetype="pdf")
    out = []
    for i in range(doc.page_count):
        text = doc[i].get_text("text", sort=True)
        heads = [(h.kind, h.code_canonical) for h in H.dedupe_consecutive(H.scan_headings(i + 1, text))]
        cls = "image_only" if not text.strip() else "narrative"
        out.append(PageInfo(i + 1, None, cls, text, "text_layer" if text.strip() else "none", heads))
    return out


def _by_role(result):
    d: dict[tuple[str, str | None], list[tuple[int, int]]] = {}
    for r in result.regions:
        d.setdefault((r.role, r.sub_role), []).append((r.page_start, r.page_end))
    return d


# ------------------------------------------------------------------ profiles


def test_three_seed_profiles_load_and_differ_where_the_spec_says():
    ids = {p["id"] for p in P.list_profiles()}
    assert ids == {"uperc-npcl", "kerc-escoms", "gerc-discoms"}
    u, k, g = (P.load_profile(i, 1) for i in ("uperc-npcl", "kerc-escoms", "gerc-discoms"))
    assert (u.schedule_representation, k.schedule_representation, g.schedule_representation) == (
        "tables",
        "tables",
        "clause_outline",
    )
    assert (u.unit_placement, k.unit_placement) == ("cell", "header")
    assert (u.tod_adjustment, k.tod_adjustment, g.tod_adjustment) == (
        "percent_of_energy_charge",
        "absolute_paise_per_unit",
        "absolute_paise_per_unit",
    )
    assert (u.effective_rule.type, k.effective_rule.type, g.effective_rule.type) == (
        "publication_plus_days",
        "first_meter_reading_on_or_after",
        "fixed_date",
    )
    assert u.effective_rule.days == 7 and k.schedule_scope == "shared" and len(k.utilities) == 5
    assert u.inventory_expectations.absent_codes == ["LMV-10"] and u.inventory_expectations.schedule_headings == 15
    assert k.secondary_authoritative is True and u.secondary_authoritative is False
    assert k.conversion_factors == {"kw_per_hp": 0.746, "kva_per_hp": 0.878}  # jurisdiction data, not constants


def test_profile_schema_file_matches_the_model():
    committed = (REPO / "packages" / "reading-profiles" / "schema.json").read_text()
    assert committed == P.schema_json(), "run `tariff-api profiles-schema -o packages/reading-profiles/schema.json`"


def test_profile_validation_refuses_bad_data():
    good = json.loads((P.profiles_dir() / "uperc-npcl.v1.json").read_text())
    bad = {**good, "locators": [c for c in good["locators"] if c["role"] != "approved_schedule"]}
    with pytest.raises(ValidationError, match="span locator"):
        P.ReadingProfile.model_validate(bad)
    bad = {**good, "locators": [{**good["locators"][0], "pattern": "(unclosed"}]}
    with pytest.raises(ValidationError):
        P.ReadingProfile.model_validate(bad)
    bad = {
        **good,
        "locators": [*good["locators"], {"role": "network_charges", "pattern": "xyz", "sub_role": "wheeling"}],
    }
    with pytest.raises(ValidationError, match="sub-role"):
        P.ReadingProfile.model_validate(bad)
    with pytest.raises(FileNotFoundError):
        P.load_profile("uperc-npcl", 99)


def test_profile_detection_is_deterministic_and_explained():
    assert P.detect_profile({"rate_schedule": 15, "chapter": 9}) == (
        "uperc-npcl",
        "15 `rate_schedule` headings in the inventory",
    )
    assert P.detect_profile({"tariff_schedule": 22})[0] == "kerc-escoms"
    assert P.detect_profile({"rate_clause": 17})[0] == "gerc-discoms"
    pid, why = P.detect_profile({"rate_schedule": 2, "rate_clause": 2})
    assert pid is None and "tie" in why
    pid, why = P.detect_profile({"chapter": 4})
    assert pid is None and "no schedule headings" in why


# ------------------------------------------------------------------ localisation rules


def test_contents_pages_never_open_a_region():
    assert is_contents_page(
        "CONTENTS\n12.1 ANNEXURE-I: RATE SCHEDULE ......... 352\nANNEXURE-II ....... 401\nCHAPTER 9 ..... 310\n"
    )
    assert not is_contents_page(
        "12.1 ANNEXURE-I: RATE SCHEDULE FOR FY 2026-27\n(APPLICABLE FOR NPCL)\nA. GENERAL PROVISIONS\n"
    )
    pages = _pages(uperc_like_order_pdf())
    assert is_contents_page(pages[1].text)
    result = localise(P.load_profile("uperc-npcl", 1), pages)
    assert all(r.cue_page != 2 for r in result.regions)


def test_uperc_layout_localises_annexure_derived_table_proposals_and_scans():
    result = localise(P.load_profile("uperc-npcl", 1), _pages(uperc_like_order_pdf()))
    assert result.status == "proposed"  # unambiguous, still needs a reviewer
    by = _by_role(result)
    assert by[("approved_schedule", None)] == [(8, 11)]  # stops before Annexure-II, never swallows the scans
    assert by[("derived_not_tariff", None)] == [(12, 12)]
    assert by[("other", None)] == [(13, 14)]
    assert by[("proposed_tariff", None)] == [(4, 5)]
    assert by[("loss_trajectory", None)] == [(3, 3)]
    assert by[("network_charges", "wheeling_charge")] == [(6, 6)]
    assert by[("network_charges", "cross_subsidy_surcharge")] == [(7, 7)]
    assert by[("network_charges", "additional_surcharge")] == [(7, 7)]
    assert by[("network_charges", "oa_loss")] == [(7, 7)]
    assert by[("green_tariff", None)] == [(8, 8)]  # provision 20 sits inside the annexure: a sub-region
    approved = next(r for r in result.regions if r.role == "approved_schedule")
    assert approved.cue_text.startswith("12.1 ANNEXURE-I: RATE SCHEDULE") and approved.cue_page == 8
    derived = next(r for r in result.regions if r.role == "derived_not_tariff")
    assert "fuel surcharge" in (derived.note or "").lower() or "Annexure-II" in (derived.note or "")
    codes = {f.code for f in result.findings}
    assert "inventory_expectation_mismatch" in codes  # 3 schedules in the fixture, the profile expects 15
    assert not any(f.severity == "blocking" for f in result.findings)


def test_kerc_layout_localises_per_escom_tables_summary_and_annexure_9():
    result = localise(P.load_profile("kerc-escoms", 1), _pages(kerc_like_order_pdf()))
    assert result.status == "proposed"
    by = _by_role(result)
    assert by[("approved_schedule", None)] == [(7, 11)]  # cover + general terms + three schedules, not the scan
    assert by[("approved_summary", None)] == [(5, 5)]
    assert by[("existing_tariff", None)] == [(3, 3), (4, 4)]  # one region per ESCOM, not merged
    assert by[("proposed_tariff", None)] == [(3, 3), (4, 4)]
    utilities = [r.utility for r in result.regions if r.role == "existing_tariff"]
    assert utilities == ["BESCOM", "MESCOM"]
    assert by[("other", None)] == [(12, 12)]
    assert by[("network_charges", "additional_surcharge")] == [(6, 6)]
    assert not any(f.code == "secondary_representation_not_found" for f in result.findings)


def test_gerc_layout_localises_clause_schedule_amendment_diff_and_formula():
    result = localise(P.load_profile("gerc-discoms", 1), _pages(gerc_like_order_pdf()))
    assert result.status == "proposed"
    by = _by_role(result)
    assert by[("approved_schedule", None)] == [(6, 11)]  # runs to the heading-less last page
    assert by[("amendment_diff", None)] == [(5, 5)]
    assert by[("formula_parameters", None)] == [(3, 3)]
    assert ("proposed_tariff", None) not in by
    assert any(f.code == "proposed_tariff_absent" and f.severity == "info" for f in result.findings)


def test_two_approved_candidates_halt_with_a_blocking_finding():
    result = localise(P.load_profile("uperc-npcl", 1), _pages(uperc_like_order_pdf(second_annexure=True)))
    assert result.status == "ambiguous"
    by = _by_role(result)
    assert by[("approved_schedule", None)] == [(8, 11), (13, 16)]  # both kept, neither chosen
    f = next(f for f in result.findings if f.code == "multiple_approved_schedule_candidates")
    assert f.severity == "blocking" and f.pages == [8, 13]


def test_no_locator_hit_halts_and_wrong_profile_is_visible():
    # the GERC document read with the UPERC profile: no ANNEXURE-I, no RATE SCHEDULE headings
    result = localise(P.load_profile("uperc-npcl", 1), _pages(gerc_like_order_pdf()))
    assert result.status == "ambiguous"
    assert {f.code for f in result.findings if f.severity == "blocking"} == {"approved_schedule_not_found"}


def test_absent_code_declared_by_profile_is_a_blocking_finding():
    pages = _pages(uperc_like_order_pdf())
    pages[9].headings.append(("rate_schedule", "LMV-10"))  # a reader "found" the schedule Part D says does not exist
    result = localise(P.load_profile("uperc-npcl", 1), pages)
    assert result.status == "ambiguous"
    assert any(f.code == "unexpected_code_found" and "LMV-10" in f.message for f in result.findings)
