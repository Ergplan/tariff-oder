"""The atlas (increment 52): states, their commissions and licensees, and each commission's
ARR norms as the application holds them.  Read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from .. import atlas as atlas_
from .. import order_reproductions as orep
from .. import reference_filings as rf
from ..adapters.identity import Principal
from ..auth import require_analyst, require_reviewer
from ..db import session_scope

router = APIRouter(tags=["atlas"])


@router.get("/atlas", response_model=dict, dependencies=[Depends(require_analyst)])
def atlas() -> dict:
    """Every state and union territory with its commissions, licensees and what is on record."""
    with session_scope() as s:
        return atlas_.atlas(s)


@router.get("/atlas/states/{code}", response_model=dict, dependencies=[Depends(require_analyst)])
def atlas_state(code: str) -> dict:
    """One state: its commissions and each licensee with its documents, readings and facts."""
    with session_scope() as s:
        return atlas_.state(s, code)


@router.get("/atlas/licensees/{code}", response_model=dict, dependencies=[Depends(require_analyst)])
def atlas_licensee(code: str) -> dict:
    """Where a licensee sits (its commission and state) with what is on record for it."""
    with session_scope() as s:
        return atlas_.licensee(s, code)


@router.get("/arr/norms/{commission}", response_model=dict, dependencies=[Depends(require_analyst)])
def arr_norms(commission: str) -> dict:
    """A commission's ARR norms as the application holds them: the regulations its mapping names,
    its conventions (stated and decided by a reviewer) and the method of every ARR line.  The
    values of a regulation's norms are never invented here; a plan that is not confirmed says so."""
    with session_scope() as s:
        return atlas_.norms(s, commission)


@router.get("/arr/rules/{commission}", response_model=dict, dependencies=[Depends(require_analyst)])
def arr_rules(commission: str) -> dict:
    """A commission's executable calculation rules with their status: draft or approved, the
    clause and whether a person verified it, the years each applies to (ADR-0021)."""
    return rf.rules(commission)


@router.get("/arr/reference-filings", response_model=list[dict], dependencies=[Depends(require_analyst)])
def reference_filings() -> list[dict]:
    """Filed petitions kept as reference targets for reproduction (milestone 13)."""
    return rf.filings()


@router.get("/arr/reference-filings/{filing_id}", response_model=dict, dependencies=[Depends(require_analyst)])
def reference_filing(filing_id: str) -> dict:
    """One reference filing: its documents, the reproduction of each format through the rules,
    the chain from base records, and the findings — for the reviewer."""
    return rf.filing(filing_id)


@router.get("/arr/order-reproductions", response_model=list[dict], dependencies=[Depends(require_analyst)])
def order_reproductions() -> list[dict]:
    """Commission orders of other states reproduced from their own printed figures with each
    commission's draft rules: what matched, what differed, the findings."""
    return orep.reproductions()


@router.get("/arr/order-reproductions/{reproduction_id}", response_model=dict, dependencies=[Depends(require_analyst)])
def order_reproduction(reproduction_id: str) -> dict:
    """One reproduced order: its manifest (URL, SHA-256), records, every binding's checks and the
    findings — evaluated on request; nothing verified or approved."""
    return orep.reproduction(reproduction_id)


class AcceptanceIn(BaseModel):
    scope: str = Field(max_length=120)
    decision: str
    note: str | None = Field(default=None, max_length=4000)
    independent: bool = Field(description="the checker attests they did not build the reproduction")
    reproduction_sha256: str = Field(min_length=64, max_length=64, description="the reproduction the checker was shown")


@router.get(
    "/arr/reference-filings/{filing_id}/acceptance", response_model=dict, dependencies=[Depends(require_analyst)]
)
def reference_acceptance(filing_id: str) -> dict:
    """The independent sign-offs of a reference filing (R-ACC-2): every record, current or stale
    against the reproduction as it stands, the latest per scope and the scopes still open."""
    with session_scope() as s:
        return rf.acceptance(s, filing_id)


@router.post("/arr/reference-filings/{filing_id}/acceptance", response_model=dict, status_code=201)
def reference_sign(filing_id: str, body: AcceptanceIn, principal: Principal = Depends(require_reviewer)) -> dict:
    """A named checker's sign-off of one scope — refused without the attestation of
    independence, a reason for anything short of acceptance, or the hash of the reproduction
    the checker was shown.  Append-only; the build never signs."""
    with session_scope() as s:
        return rf.sign(
            s,
            filing_id,
            scope=body.scope,
            decision=body.decision,
            note=body.note,
            independent=body.independent,
            reproduction_sha256_seen=body.reproduction_sha256,
            actor=principal.email,
        )


@router.get(
    "/arr/reference-filings/{filing_id}/queries",
    dependencies=[Depends(require_analyst)],
    responses={200: {"content": {"text/markdown": {}}, "description": "draft queries to the petitioner"}},
)
def reference_queries(filing_id: str) -> Response:
    """A draft of the queries to the petitioner from the findings addressed to it (Markdown), for
    a reviewer to edit and issue.  It is labelled a draft; the build issues nothing."""
    text = rf.queries_draft(filing_id)
    return Response(
        text,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{filing_id}-draft-queries.md"'},
    )
