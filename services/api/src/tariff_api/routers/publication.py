"""Publication endpoints (Section 7.2): preview the consequences of a release over a declared
scope, publish with an explicit completeness declaration, list a source's releases.
Reviewer or administrator only; the transaction is in `services.publication`."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from ..adapters.identity import Principal
from ..auth import require_analyst, require_reviewer
from ..db import session_scope
from ..models import DataRelease
from ..schemas import (
    ChecklistItem,
    PublicationSummary,
    PublishPreview,
    PublishPreviewRequest,
    PublishRequest,
    ReleaseList,
    ReleaseOut,
    ReviewChecklist,
)
from ..services import publication as pub
from ..services import sources as svc

router = APIRouter(tags=["publication"])


def _release(r: DataRelease) -> ReleaseOut:
    return ReleaseOut.model_validate(r, from_attributes=True)


def _preview_out(source_id: uuid.UUID, pv: dict, settings) -> PublishPreview:
    c = pv["checklist"]
    checklist = ReviewChecklist(
        source_id=source_id,
        items=[ChecklistItem(**i) for i in c["items"]],
        summary=c["summary"],
        inventory_categories=c["inventory_categories"],
        condition_records=c["condition_records"],
        condition_candidates=c["condition_candidates"],
        candidates=c["candidates"],
        awaiting_second_review=c["awaiting_second_review"],
        unresolved=c["unresolved"],
        second_review_policy={
            "material": settings.second_review_material,
            "first_order": settings.second_review_first_order,
        },
    )
    public = pub.public_preview(pv)
    prior = public.pop("prior_release")
    public.pop("checklist")
    return PublishPreview(
        source_id=source_id,
        checklist=checklist,
        prior_release=PublicationSummary(**prior) if prior else None,
        **public,
    )


@router.post("/sources/{source_id}/publish/preview", response_model=PublishPreview)
def publish_preview(
    source_id: uuid.UUID,
    body: PublishPreviewRequest,
    request: Request,
    principal: Principal = Depends(require_reviewer),
) -> PublishPreview:
    """Show what a release over this scope would publish and what stands in its way.  The
    returned token is required by the publish call: the consequences shown must still hold."""
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        pv = pub.preview(s, src, scope=body.scope, categories=body.categories, families=body.families)
        return _preview_out(source_id, pv, request.app.state.settings)


@router.post("/sources/{source_id}/publish", response_model=ReleaseOut, status_code=201)
def publish_source(
    source_id: uuid.UUID, body: PublishRequest, request: Request, principal: Principal = Depends(require_reviewer)
) -> ReleaseOut:
    """The publication transaction.  Fails on a stale source version or preview token, on
    missing required items for a `complete` declaration, on undeclared gaps for a `partial`
    one, and on approved candidates that still carry blocking findings."""
    with session_scope() as s:
        src = svc.get_source(s, source_id)
        release = pub.publish(s, request.app.state.settings, src, body, actor=principal.email)
        return _release(release)


@router.get("/sources/{source_id}/releases", response_model=ReleaseList, dependencies=[Depends(require_analyst)])
def list_releases(source_id: uuid.UUID) -> ReleaseList:
    with session_scope() as s:
        svc.get_source(s, source_id)
        rows = (
            s.execute(
                select(DataRelease).where(DataRelease.source_id == source_id).order_by(DataRelease.release_number)
            )
            .scalars()
            .all()
        )
        return ReleaseList(releases=[_release(r) for r in rows], total=len(rows))
