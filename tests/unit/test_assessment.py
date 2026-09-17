"""The model feedback loop: Haystack retrieval picks the category's own passages, the
fixture template scores from what the rules know, quotes are grounded verbatim, an ungrounded
quote cannot fill a sub-category, and low confidence or a contradiction raises a risk tag."""

from __future__ import annotations

from tariff_api import assessment
from tariff_api.tariff_schema import Applicability, Candidate, EvidenceRef

PAGE = (
    "RATE SCHEDULE HV-1 NON-INDUSTRIAL BULK LOADS\n3. RATE:\n"
    "(a) Commercial Loads / Private Institutions with contracted load 75 kW & above:\n"
    "Contracted Load Fixed Charge Energy Charge\nFor supply at 11kV Rs. 430.00 / kVA / month Rs. 8.32 / kVAh\n\n"
    "(b) Public Institutions, Registered Societies, Residential Colonies / Townships:\n"
    "Contracted Load Fixed Charge Energy Charge\nFor supply at 11kV Rs. 380.00 / kVA / month Rs. 7.70 / kVAh\n"
    "The body seeking the supply at Single point for bulk loads shall be considered as a deemed franchisee.\n"
)


def _cand(value, comp, per_unit, block=None, row=1):
    return Candidate(
        family="retail_tariff",
        category_code="HV-1",
        component_type=comp,
        value=value,
        value_state="value",
        original_text=f"Rs. {value} / {per_unit}",
        currency="rupees",
        per_unit=per_unit,
        frequency="per_month" if comp == "fixed" else None,
        applicability=Applicability(description="For supply at 11kV", rate_block=block),
        evidence=[
            EvidenceRef(
                page_index=384,
                kind="cell",
                grid_ordinal=1,
                row=row,
                col=1,
                header_path=["Fixed Charge" if comp == "fixed" else "Energy Charge"],
                row_path=["For supply at 11kV"],
                excerpt=f"Rs. {value} / {per_unit}",
            )
        ],
    )


def test_retrieval_brings_the_candidates_own_passages():
    inp = assessment.retrieve(assessment.AssessmentInput("sha", "HV-1", [_cand("380.00", "fixed", "kVA")], {384: PAGE}))
    assert inp.passages[0] and any("380.00" in p["text"] for p in inp.passages[0]) and inp.passages[0][0]["page"] == 384
    text = assessment.serialise(inp)
    assert "[0] fixed: 380.00 rupees per kVA per_month" in text and "passage p384" in text


def test_fixture_assessment_is_grounded_and_fills_a_missing_rate_block_only_from_a_grounded_quote():
    c1 = _cand(
        "380.00",
        "fixed",
        "kVA",
        block="(b) Public Institutions, Registered Societies, Residential Colonies / Townships:",
    )
    c2 = _cand("7.70", "energy", "kVAh")
    inp = assessment.AssessmentInput("sha", "HV-1", [c1, c2], {384: PAGE})
    out = assessment.template_assessment(inp)
    tags = assessment.apply(inp, out, provider="fixture", model="fixture-rules", is_fixture=True)
    assert tags == []
    assert c1.assessment["grounded"] and c1.assessment["confidence"] == 0.9 and c1.assessment["verdict"] == "supported"
    assert c1.assessment["meaning"].startswith("The fixed for (b) Public Institutions")
    assert c1.assessment["sub_categories_seen"] == [
        "(b) Public Institutions, Registered Societies, Residential Colonies / Townships:"
    ]
    # c2 had no rate block: the template never offers the row description as a sub-category,
    # so the block stays empty (one fact, one identity); its quote is still grounded
    assert c2.assessment["grounded"] and c2.applicability.rate_block is None


def test_ungrounded_quotes_low_confidence_and_contradictions_raise_tags_but_never_change_values():
    c = _cand("7.70", "energy", "kVAh")
    inp = assessment.AssessmentInput("sha", "HV-1", [c], {384: PAGE})
    model_out = {
        "items": [
            {
                "index": 0,
                "verdict": "contradicted",
                "confidence": 0.3,
                "sub_category": "(c) Hospitals",
                "quote": "(c) Hospitals and clinics",
                "meaning": "x",
                "issue": "no such block",
            }
        ],
        "sub_categories": [
            {"label": "(b) Public Institutions", "quote": "(b) Public Institutions, Registered Societies"},
            {"label": "made up", "quote": "not on the page"},
        ],
    }
    tags = assessment.apply(inp, model_out, provider="anthropic", model="m", is_fixture=False)
    assert set(tags) == {"0:model_low_confidence", "0:model_contradicted", "0:assessment_ungrounded"}
    assert c.value == "7.70" and c.applicability.rate_block is None  # the ungrounded sub-category was not applied
    assert c.assessment["grounded"] is False and c.assessment["sub_categories_seen"] == ["(b) Public Institutions"]


def test_repeated_passages_on_a_page_do_not_break_the_store():
    page = (
        "NPCL Tariff Order FY 2026-27\n\nFor supply at 11kV Rs. 380.00 / kVA / month\n\nNPCL Tariff Order FY 2026-27\n"
    )
    inp = assessment.retrieve(assessment.AssessmentInput("sha", "HV-1", [_cand("380.00", "fixed", "kVA")], {384: page}))
    assert inp.passages[0] and any("380.00" in p["text"] for p in inp.passages[0])
