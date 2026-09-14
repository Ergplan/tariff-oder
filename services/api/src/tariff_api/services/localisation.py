"""Localisation checkpoint services (Section 6.5): profile assignment, reading the record,
and the reviewer's decision.  The decision is the human boundary: the rules only ever
*propose*; nothing here can set ``extraction_allowed`` without a named reviewer, a rationale
and an audit event."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import AppError
from ..localisation import LOCALISATION_VERSION
from ..models import AuditEvent, LocalisationRecord, LocalisationRegion, SourceDocument, SourceState
from ..profiles import ReadingProfile, latest_version, load_profile
from ..schemas import LocalisationDecision, RegionEdit
from ..telemetry import request_id_var
from .sources import enqueue_stage, request_stage_rerun

ROLES = {
    "approved_schedule",
    "approved_summary",
    "existing_tariff",
    "proposed_tariff",
    "amendment_diff",
    "formula_parameters",
    "network_charges",
    "loss_trajectory",
    "green_tariff",
    "illustrative",
    "derived_not_tariff",
    "other",
}


def assign_profile(
    session: Session,
    settings: Settings,
    source: SourceDocument,
    profile_id: str,
    version: int | None,
    *,
    actor: str,
    reason: str,
) -> tuple[ReadingProfile, bool]:
    """Bind a reading profile by hand (administrator).  Invalidates any localisation and, if
    the source is already parsed, queues a re-run of the localisation stage.  Returns the
    profile and whether a re-run was queued."""
    v = version if version is not None else latest_version(profile_id)
    if v is None:
        raise AppError("not_found", f"no reading profile {profile_id!r}")
    try:
        profile = load_profile(profile_id, v)
    except (FileNotFoundError, ValueError) as e:
        raise AppError("not_found", str(e)) from e
    before = {
        "reading_profile_id": source.reading_profile_id,
        "reading_profile_version": source.reading_profile_version,
        "reading_profile_source": source.reading_profile_source,
    }
    source.reading_profile_id = profile.id
    source.reading_profile_version = profile.version
    source.reading_profile_source = "assigned"
    source.reading_profile_rationale = f"assigned by {actor}: {reason}"
    source.version += 1
    session.add(
        AuditEvent(
            actor=actor,
            action="source.profile_assigned",
            entity_type="source_document",
            entity_id=str(source.id),
            before=before,
            after={"reading_profile_id": profile.id, "reading_profile_version": profile.version},
            reason=reason,
            request_id=request_id_var.get(),
        )
    )
    rerun = False
    order = list(SourceState)
    if source.state in (SourceState.parsed, SourceState.localised) or (
        source.state in order
        and order.index(source.state) > order.index(SourceState.localised)
        and source.state
        not in (SourceState.failed, SourceState.cancelled, SourceState.rejected, SourceState.superseded)
    ):
        # a different profile means the localisation is stale: drop the record and re-run
        session.execute(delete(LocalisationRegion).where(LocalisationRegion.source_id == source.id))
        session.execute(delete(LocalisationRecord).where(LocalisationRecord.source_id == source.id))
        if source.state == SourceState.parsed:
            enqueue_stage(session, settings, source, "localise_source", actor=actor)
        else:
            request_stage_rerun(session, settings, source, "localise_source", actor=actor)
        rerun = True
    return profile, rerun


def get_record(session: Session, source_id: uuid.UUID) -> tuple[LocalisationRecord, list[LocalisationRegion]]:
    rec = session.get(LocalisationRecord, source_id)
    if rec is None:
        raise AppError("not_found", "the source has not been localised yet")
    regions = (
        session.execute(
            select(LocalisationRegion)
            .where(LocalisationRegion.source_id == source_id)
            .order_by(LocalisationRegion.ordinal)
        )
        .scalars()
        .all()
    )
    return rec, regions


def _validate_regions(regions: list[RegionEdit], page_count: int | None) -> None:
    if not regions:
        raise AppError("validation_failed", "a correction must supply at least one region")
    for r in regions:
        if r.role not in ROLES:
            raise AppError("validation_failed", f"unknown region role {r.role!r}")
        if r.page_end < r.page_start:
            raise AppError("validation_failed", f"region {r.role}: page_end before page_start")
        if page_count and r.page_end > page_count:
            raise AppError(
                "validation_failed", f"region {r.role}: page {r.page_end} beyond the document ({page_count} pages)"
            )
    approved = [r for r in regions if r.role == "approved_schedule"]
    if not approved:
        raise AppError("validation_failed", "a correction must place exactly one approved_schedule region per period")


def decide(
    session: Session, source: SourceDocument, body: LocalisationDecision, *, actor: str
) -> tuple[LocalisationRecord, list[LocalisationRegion]]:
    """Reviewer decision.  ``confirm`` is refused while the record is ambiguous: the reviewer
    resolves ambiguity by correcting, never by waving it through.  Every decision is audited
    with the full before/after region sets."""
    rec, regions = get_record(session, source.id)
    if body.expected_version is not None and body.expected_version != rec.version:
        raise AppError(
            "conflict_stale_version", f"record is at version {rec.version}, you decided on {body.expected_version}"
        )
    if not body.pages_viewed:
        raise AppError("validation_failed", "confirm only after looking at the pages (pages_viewed must be true)")
    if rec.rules_version != LOCALISATION_VERSION:
        raise AppError("validation_failed", "the localisation was produced by older rules; re-run the stage first")
    before = {"status": rec.status, "regions": [_region_dict(r) for r in regions]}
    if body.decision == "confirm":
        if rec.status == "ambiguous":
            raise AppError(
                "validation_failed",
                "the rules could not localise the approved schedule unambiguously; "
                "correct the regions instead of confirming",
            )
        new_status = "confirmed"
    else:
        _validate_regions(body.regions or [], source.page_count)
        session.execute(delete(LocalisationRegion).where(LocalisationRegion.source_id == source.id))
        session.flush()
        regions = []
        for i, r in enumerate(body.regions or [], start=1):
            row = LocalisationRegion(
                source_id=source.id,
                ordinal=i,
                role=r.role,
                sub_role=r.sub_role,
                page_start=r.page_start,
                page_end=r.page_end,
                cue_text=f"reviewer {actor}: {r.note or body.rationale}"[:300],
                cue_page=r.page_start,
                cue_kind="reviewer",
                utility=r.utility,
                period=r.period,
                note=r.note,
                origin="reviewer",
            )
            session.add(row)
            regions.append(row)
        new_status = "corrected"
    rec.status = new_status
    rec.extraction_allowed = True
    rec.decided_by = actor
    rec.decided_at = datetime.now(UTC)
    rec.decision_rationale = body.rationale
    rec.decision_count += 1
    rec.version += 1
    session.flush()
    session.add(
        AuditEvent(
            actor=actor,
            action=f"localisation.{body.decision}",
            entity_type="localisation_record",
            entity_id=str(source.id),
            before=before,
            after={"status": new_status, "regions": [_region_dict(r) for r in regions]},
            reason=body.rationale,
            request_id=request_id_var.get(),
        )
    )
    return rec, regions


def _region_dict(r: LocalisationRegion) -> dict:
    return {
        "role": r.role,
        "sub_role": r.sub_role,
        "page_start": r.page_start,
        "page_end": r.page_end,
        "cue_text": r.cue_text,
        "origin": r.origin,
        "utility": r.utility,
        "period": r.period,
    }
