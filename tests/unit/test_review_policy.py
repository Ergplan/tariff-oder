"""Milestone 5a policy as pure functions: when a second reviewer is required, how a
checklist item's status is derived from its candidates, and what batch approval refuses."""

from __future__ import annotations

from types import SimpleNamespace

from tariff_api.config import Settings
from tariff_api.services.review import (
    CAUSE_TAGS,
    OPEN_STATUSES,
    _item_status,
    batch_eligible,
    second_review_reasons,
)
from tariff_api.tariff_schema import Candidate, EvidenceRef


def _settings(**kw) -> Settings:
    base = dict(
        deployment_profile="local",
        database_url="postgresql+psycopg://x@localhost/x",
        local_user_allowlist="a@example.com:analyst",
    )
    return Settings(**{**base, **kw})


def _candidate(**kw) -> Candidate:
    fields = dict(
        family="retail_tariff",
        category_code="LMV-1",
        component_type="energy",
        value="3.00",
        value_state="value",
        original_text="3.00",
        currency="rupees",
        per_unit="kWh",
        evidence=[EvidenceRef(page_index=1, kind="cell", grid_ordinal=0, row=1, col=1, excerpt="3.00")],
    )
    return Candidate(**{**fields, **kw})


def _row(**kw):
    base = dict(
        review_status="pending",
        routing="batch",
        risk_tags=[],
        confidence="high",
        finding_count=0,
        channel_agreement="agree",
    )
    return SimpleNamespace(**{**base, **kw})


def test_second_review_policy_material_items_first_orders_and_corrected_disagreements():
    s = _settings()
    assert second_review_reasons(_row(), _candidate(), outcome="approve", settings=s) == []
    assert second_review_reasons(
        _row(),
        _candidate(component_type="condition", value=None, value_state="absent_in_source"),
        outcome="approve",
        settings=s,
    ) == ["material_condition"]
    assert second_review_reasons(
        _row(), _candidate(value=None, value_state="formula"), outcome="approve", settings=s
    ) == ["formula_component"]
    assert second_review_reasons(_row(channel_agreement="disagree"), _candidate(), outcome="approve", settings=s) == []
    assert second_review_reasons(_row(channel_agreement="disagree"), _candidate(), outcome="correct", settings=s) == [
        "corrected_channel_disagreement"
    ]
    assert second_review_reasons(_row(risk_tags=["new_profile"]), _candidate(), outcome="approve", settings=s) == [
        "first_order_from_utility"
    ]
    off = _settings(second_review_material=False, second_review_first_order=False)
    assert (
        second_review_reasons(
            _row(risk_tags=["new_profile"], channel_agreement="disagree"),
            _candidate(component_type="condition", value=None, value_state="absent_in_source"),
            outcome="correct",
            settings=off,
        )
        == []
    )


def test_checklist_status_never_reports_green_for_open_or_unresolved_items():
    assert _item_status([]) == "not_started"
    assert _item_status(["pending", "pending"]) == "not_started"
    assert _item_status(["pending", "approved"]) == "in_progress"
    assert _item_status(["awaiting_second_review", "approved"]) == "in_progress"
    assert _item_status(["approved", "approved"]) == "approved"
    assert _item_status(["approved", "corrected"]) == "corrected"
    assert _item_status(["approved", "unresolved"]) == "unresolved"
    assert _item_status(["rejected", "rejected"]) == "rejected"
    assert _item_status(["rejected", "approved"]) == "approved"
    assert set(OPEN_STATUSES) == {"pending", "awaiting_second_review"}


def test_batch_eligibility_refuses_anything_but_clean_high_confidence_pending_candidates():
    assert batch_eligible(_row()) is None
    assert batch_eligible(_row(routing="individual")) == "routed to individual review"
    assert batch_eligible(_row(risk_tags=["ocr_page"])).startswith("carries risk tags")
    assert batch_eligible(_row(confidence="medium")) == "confidence is medium"
    assert batch_eligible(_row(finding_count=1)) == "has validator findings"
    assert batch_eligible(_row(review_status="approved")) == "candidate is approved"
    assert len(CAUSE_TAGS) == 7 and "other" in CAUSE_TAGS
