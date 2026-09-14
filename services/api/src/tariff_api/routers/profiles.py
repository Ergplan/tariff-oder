"""Reading profiles as read-only data (Section 6.11).  Profiles live in the repository; the
API lists them so the UI can show what a source was read with and an administrator can
assign one by hand."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import require_analyst
from ..profiles import list_profiles
from ..schemas import ReadingProfileList, ReadingProfileOut

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("", response_model=ReadingProfileList, dependencies=[Depends(require_analyst)])
def get_profiles() -> ReadingProfileList:
    return ReadingProfileList(profiles=[ReadingProfileOut(**p) for p in list_profiles()])
