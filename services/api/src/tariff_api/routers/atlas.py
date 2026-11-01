"""The atlas (increment 52): states, their commissions and licensees, and each commission's
ARR norms as the application holds them.  Read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import atlas as atlas_
from .. import reference_filings as rf
from ..auth import require_analyst
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
