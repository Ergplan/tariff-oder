"""The atlas (increment 52): states, their commissions and licensees, and each commission's
ARR norms as the application holds them.  Read-only."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .. import atlas as atlas_
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
