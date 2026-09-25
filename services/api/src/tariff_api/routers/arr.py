"""ARR foundation, read-only: the taxonomy and the commission mappings as the app sees them
(ARR spec sections 2 and 3).  Data files served through the models; nothing here writes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..auth import require_analyst
from ..errors import AppError
from ..schemas import ArrMappingOut, ArrTaxonomyOut

router = APIRouter(prefix="/arr", tags=["arr"], dependencies=[Depends(require_analyst)])


@router.get("/taxonomy", response_model=ArrTaxonomyOut)
def get_taxonomy() -> ArrTaxonomyOut:
    from ..arr.taxonomy import load_taxonomy, mapping_files

    t = load_taxonomy()
    return ArrTaxonomyOut(
        id=t.id,
        version=t.version,
        status=t.status,
        canonical_units=t.canonical_units,
        value_types=[c.model_dump() for c in t.value_types],
        reason_categories=[c.model_dump() for c in t.reason_categories],
        line_items=[i.model_dump() for i in t.line_items],
        identities=[i.model_dump() for i in t.identities],
        mappings={k: [v for v, _ in sorted(paths)] for k, paths in mapping_files().items()},
    )


@router.get("/mappings/{commission}", response_model=ArrMappingOut)
def get_mapping(commission: str, version: int | None = None) -> ArrMappingOut:
    from ..arr.taxonomy import load_mapping

    try:
        m = load_mapping(commission, version)
    except (FileNotFoundError, StopIteration) as e:
        raise AppError("not_found", f"no ARR mapping for {commission}") from e
    d: dict[str, Any] = m.model_dump()
    return ArrMappingOut(**d)
