"""``petition_fill`` (increment 151): fill a case's uploaded formats workbook with the rule engine
(``tariff_api.arr.petition``).  About a minute and a half for NPCL's 74 formats; not retried — a
failure is recorded on the workbook and a person requests the fill again."""

from __future__ import annotations

import uuid

from tariff_api.arr import petition
from tariff_api.db import session_scope
from tariff_api.errors import AppError

from ..runner import JobContext, JobFailure


def petition_fill(ctx: JobContext) -> dict:
    workbook_id = uuid.UUID(ctx.payload["workbook_id"])
    try:
        return petition.run_fill(session_scope, ctx.adapters.storage, workbook_id)
    except AppError as exc:
        raise JobFailure(exc.error_type, str(exc), retry=False) from exc
    except Exception as exc:  # noqa: BLE001 - recorded on the workbook by run_fill
        raise JobFailure("internal_error", f"the fill failed: {type(exc).__name__}: {exc}", retry=False) from exc
