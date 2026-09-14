"""Publication transaction (Section 7.2, publication; Section 5.2, published facts).

A release is a snapshot over a declared scope with an explicit completeness declaration.
It is preceded by a preview that shows the consequences (what will be published, what is
unresolved, what awaits a second reviewer, which required items are missing) and returns a
token over that state; publishing must present the token, so a release never rests on a
view of the order that has since changed.  `complete` fails on any missing required item;
`partial` must list every gap by key and is labelled partial wherever it is read.  Facts
are copied from the effective records of finally approved candidates, evidence rows are
copied with the printed page label, and nothing is ever read back from `candidates` by the
explorer.  Releases are cumulative per source: a later release supersedes the earlier one.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import AppError
from ..models import (
    AuditEvent,
    CandidateRecord,
    DataRelease,
    FamilyDisposition,
    PublishedEvidence,
    PublishedFact,
    ReviewDecision,
    SourceDocument,
    SourcePage,
    SourceState,
    ValidatorFindingRecord,
)
from ..schemas import PublishRequest
from ..tariff_schema import NETWORK_FAMILIES
from ..telemetry import request_id_var
from . import review as rv
from .sources import transition

PUBLISHABLE = ("approved", "corrected")


def _final(c: CandidateRecord) -> bool:
    return c.review_status in PUBLISHABLE and c.second_review in ("not_required", "done")


def _in_scope(c: CandidateRecord, scope: str, categories: set[str], families: set[str]) -> bool:
    if scope == "whole_schedule":
        return True
    if c.family == "retail_tariff":
        return (c.category_code or "") in categories
    return c.family in families


def _item_key(c: CandidateRecord) -> str:
    return c.category_code or "(no category)" if c.family == "retail_tariff" else c.family


def preview(
    session: Session,
    source: SourceDocument,
    *,
    scope: str,
    categories: list[str] | None,
    families: list[str] | None,
) -> dict[str, Any]:
    """What a release over this scope would contain and what stands in its way."""
    if scope == "subset" and not categories and not families:
        raise AppError("validation_failed", "a subset scope needs categories and/or families")
    cats = set(categories or [])
    fams = set(families or [])
    unknown_f = sorted(fams - set(NETWORK_FAMILIES))
    if unknown_f:
        raise AppError("validation_failed", f"unknown charge families: {', '.join(unknown_f)}")
    rows = session.execute(select(CandidateRecord).where(CandidateRecord.source_id == source.id)).scalars().all()
    known_categories = {c.category_code for c in rows if c.category_code}
    checklist = rv.checklist(session, source)
    inventory = set(checklist["inventory_categories"])
    unknown_c = sorted(cats - known_categories - inventory)
    if unknown_c:
        raise AppError("validation_failed", f"categories not in this order: {', '.join(unknown_c)}")
    in_scope = [c for c in rows if _in_scope(c, scope, cats, fams)]
    publishable = [c for c in in_scope if _final(c)]
    pending = [c for c in in_scope if c.review_status == "pending"]
    second = [c for c in in_scope if c.review_status == "awaiting_second_review"]
    unresolved = [c for c in in_scope if c.review_status == "unresolved"]
    blocked = [c for c in publishable if c.blocking_finding_count > 0]
    dispositions = {
        d.family: d.disposition
        for d in session.execute(select(FamilyDisposition).where(FamilyDisposition.source_id == source.id)).scalars()
    }
    source_level = [
        f
        for f in session.execute(
            select(ValidatorFindingRecord).where(
                ValidatorFindingRecord.source_id == source.id, ValidatorFindingRecord.severity == "blocking"
            )
        ).scalars()
        if not f.candidate_ids
    ]
    # required items for a `complete` declaration
    missing: list[dict[str, str]] = []
    scope_categories = sorted(inventory | known_categories) if scope == "whole_schedule" else sorted(cats)
    approved_categories = {c.category_code for c in publishable if c.family == "retail_tariff" and c.category_code}
    for code in scope_categories:
        if code not in approved_categories:
            missing.append({"key": code, "reason": "no approved fact for this category"})
    scope_families = list(NETWORK_FAMILIES) if scope == "whole_schedule" else sorted(fams)
    approved_families = {c.family for c in publishable if c.family != "retail_tariff"}
    for fam in scope_families:
        if fam not in approved_families and fam not in dispositions:
            missing.append({"key": fam, "reason": "no approved fact and no reviewed disposition"})
    open_keys = sorted({_item_key(c) for c in pending + second + unresolved})
    for k in open_keys:
        missing.append({"key": k, "reason": "candidates still open (pending, awaiting second review or unresolved)"})
    for f in source_level:
        key = f.detail.get("family") or f.validator_id
        missing.append({"key": key, "reason": f"source-level blocking finding {f.validator_id}: {f.message[:120]}"})
    seen: set[tuple[str, str]] = set()
    missing = [m for m in missing if not ((m["key"], m["reason"]) in seen or seen.add((m["key"], m["reason"])))]
    gap_keys_required = sorted({m["key"] for m in missing})
    prior = current_release(session, source.id)
    state = sorted((str(c.id), c.version, c.review_status, c.second_review) for c in in_scope)
    token = hashlib.sha256(
        json.dumps(
            {
                "scope": scope,
                "categories": sorted(cats),
                "families": sorted(fams),
                "source_version": source.version,
                "state": state,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    return {
        "scope": scope,
        "categories": sorted(cats),
        "families": sorted(fams),
        "candidates_in_scope": len(in_scope),
        "facts_to_publish": len(publishable) - len(blocked),
        "pending": [str(c.id) for c in pending],
        "awaiting_second_review": [str(c.id) for c in second],
        "unresolved": [str(c.id) for c in unresolved],
        "blocked_by_findings": [str(c.id) for c in blocked],
        "missing_for_complete": missing,
        "gap_keys_required_for_partial": gap_keys_required,
        "dispositions": dispositions,
        "checklist": checklist,
        "prior_release": _release_dict(prior) if prior else None,
        "source_version": source.version,
        "preview_token": token,
        "_publishable": publishable,
        "_blocked": blocked,
        "_second": second,
        "_pending": pending,
        "_unresolved": unresolved,
    }


def current_release(session: Session, source_id: uuid.UUID) -> DataRelease | None:
    return session.execute(
        select(DataRelease).where(DataRelease.source_id == source_id, DataRelease.is_current.is_(True))
    ).scalar_one_or_none()


def _release_dict(r: DataRelease) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "release_number": r.release_number,
        "scope": r.scope,
        "completeness": r.completeness,
        "gaps": r.gaps,
        "fact_count": r.fact_count,
        "published_by": r.published_by,
        "published_at": r.published_at.isoformat() if r.published_at else None,
        "is_current": r.is_current,
        "is_fixture": r.is_fixture,
    }


def publish(
    session: Session, settings: Settings, source: SourceDocument, body: PublishRequest, *, actor: str
) -> DataRelease:
    if source.state not in (SourceState.awaiting_review, SourceState.published):
        raise AppError("invalid_transition", f"source is {source.state.value}; publication needs awaiting_review")
    if body.expected_source_version != source.version:
        raise AppError(
            "conflict_stale_version",
            f"source is at version {source.version}, you decided on {body.expected_source_version}",
            extra={"current_version": source.version},
        )
    pv = preview(session, source, scope=body.scope, categories=body.categories, families=body.families)
    if body.preview_token != pv["preview_token"]:
        raise AppError(
            "conflict_stale_version",
            "the consequences you were shown are no longer current; review the preview again",
            extra={"current_version": source.version},
        )
    if not body.confirm_consequences:
        raise AppError("validation_failed", "publication must be confirmed after the consequences were shown")
    blocked = pv["_blocked"]
    if blocked:
        raise AppError(
            "validation_failed",
            "approved candidates still carry blocking validator findings; correct or reject them first",
            extra={"blocked": [str(c.id) for c in blocked]},
        )
    if body.completeness == "complete":
        if pv["missing_for_complete"]:
            raise AppError(
                "validation_failed",
                "a complete declaration is refused: required items are missing",
                extra={"missing": pv["missing_for_complete"]},
            )
        if body.gaps:
            raise AppError("validation_failed", "a complete declaration cannot list gaps")
    else:
        declared = {g.key for g in body.gaps}
        undeclared = [k for k in pv["gap_keys_required_for_partial"] if k not in declared]
        if undeclared:
            raise AppError(
                "validation_failed",
                "a partial declaration must list every gap by key",
                extra={"undeclared_gaps": undeclared},
            )
        if not body.gaps and not pv["missing_for_complete"]:
            raise AppError("validation_failed", "nothing is missing: declare the release complete instead")
    publishable: list[CandidateRecord] = pv["_publishable"]
    if not publishable:
        raise AppError("validation_failed", "nothing to publish: no candidate in scope is finally approved")
    prior = current_release(session, source.id)
    number = (
        session.execute(
            select(func.max(DataRelease.release_number)).where(DataRelease.source_id == source.id)
        ).scalar_one()
        or 0
    ) + 1
    labels = {
        p.page_index: p.printed_label
        for p in session.execute(select(SourcePage).where(SourcePage.source_id == source.id)).scalars()
    }
    utilities = {c.utility for c in publishable if c.utility}
    periods = {c.period for c in publishable if c.period}
    checklist = dict(pv["checklist"])
    release = DataRelease(
        source_id=source.id,
        release_number=number,
        scope=body.scope,
        scope_categories=pv["categories"],
        scope_families=pv["families"],
        completeness=body.completeness,
        gaps=[g.model_dump() for g in body.gaps],
        rationale=body.rationale,
        published_by=actor,
        source_version=source.version,
        utility=next(iter(utilities)) if len(utilities) == 1 else None,
        period=next(iter(periods)) if len(periods) == 1 else None,
        candidates_in_scope=pv["candidates_in_scope"],
        unresolved_count=len(pv["_unresolved"]),
        pending_count=len(pv["_pending"]),
        awaiting_second_review_count=len(pv["_second"]),
        checklist_snapshot={
            "summary": checklist["summary"],
            "candidates": checklist["candidates"],
            "dispositions": pv["dispositions"],
        },
        preview_token=pv["preview_token"],
        is_current=True,
        is_fixture=source.dataset.kind.value == "fixture",
        request_id=request_id_var.get(),
    )
    session.add(release)
    session.flush()
    count = 0
    for c in publishable:
        rec = dict(c.effective_record)
        last = session.execute(
            select(ReviewDecision.id)
            .where(ReviewDecision.candidate_id == c.id, ReviewDecision.undone.is_(False))
            .order_by(ReviewDecision.sequence.desc())
        ).first()
        fact = PublishedFact(
            release_id=release.id,
            source_id=source.id,
            candidate_id=c.id,
            decision_id=last[0] if last else None,
            review_status=c.review_status,
            family=c.family,
            category_code=rec.get("category_code"),
            component_type=rec.get("component_type") or c.component_type,
            value=rec.get("value"),
            value_state=rec.get("value_state") or c.value_state,
            currency=rec.get("currency"),
            per_unit=rec.get("per_unit"),
            frequency=rec.get("frequency"),
            decision_status=rec.get("decision_status"),
            period=rec.get("period"),
            utility=rec.get("utility"),
            applicability=rec.get("applicability") or {},
            conditions=rec.get("conditions") or [],
            derivation=rec.get("derivation"),
            record=rec,
            is_fixture=c.is_fixture,
        )
        session.add(fact)
        session.flush()
        for i, ev in enumerate(rec.get("evidence") or []):
            session.add(
                PublishedEvidence(
                    fact_id=fact.id,
                    release_id=release.id,
                    source_id=source.id,
                    ordinal=i,
                    page_index=ev["page_index"],
                    printed_label=labels.get(ev["page_index"]),
                    kind=ev["kind"],
                    grid_ordinal=ev.get("grid_ordinal"),
                    row=ev.get("row"),
                    col=ev.get("col"),
                    line_no=ev.get("line_no"),
                    header_path=ev.get("header_path") or [],
                    row_path=ev.get("row_path") or [],
                    clause_path=ev.get("clause_path") or [],
                    excerpt=(ev.get("excerpt") or "")[:400],
                )
            )
        if c.published_release_id is None:
            c.published_release_id = release.id
        count += 1
    release.fact_count = count
    if prior is not None:
        prior.is_current = False
        prior.superseded_by_id = release.id
    before_state = source.state.value
    if source.state == SourceState.awaiting_review:
        transition(
            session,
            source,
            SourceState.published,
            actor=actor,
            reason=f"release {number} ({body.completeness}, {count} facts)",
        )
    else:
        source.version += 1
    source.publication_summary = {
        **_release_dict(release),
        "unresolved": release.unresolved_count,
        "pending": release.pending_count,
        "awaiting_second_review": release.awaiting_second_review_count,
    }
    session.add(
        AuditEvent(
            actor=actor,
            action="source.publish",
            entity_type="data_release",
            entity_id=str(release.id),
            before={"state": before_state, "prior_release": _release_dict(prior) if prior else None},
            after=_release_dict(release),
            reason=body.rationale,
            request_id=request_id_var.get(),
        )
    )
    session.flush()
    return release


def public_preview(pv: dict[str, Any]) -> dict[str, Any]:
    """The preview without the private candidate lists."""
    return {k: v for k, v in pv.items() if not k.startswith("_")}


def now() -> datetime:
    return datetime.now(UTC)
