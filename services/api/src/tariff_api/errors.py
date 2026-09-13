"""Typed error taxonomy (Section 7.1, principle 4).

Every failure that can reach a user has a stable ``error_type``, an HTTP status, and a
user-facing message that states what happened, what the system did, and what the user
can do next.  Raw stack traces and provider messages never reach ordinary users; they are
logged with the request id so support can trace them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ErrorSpec:
    error_type: str
    http_status: int
    severity: str  # info | warning | error | critical
    user_message: str
    next_step: str


ERROR_TAXONOMY: dict[str, ErrorSpec] = {
    e.error_type: e
    for e in [
        ErrorSpec(
            "unauthenticated",
            401,
            "warning",
            "You are not signed in.",
            "Sign in through the configured identity provider and retry.",
        ),
        ErrorSpec(
            "permission_denied",
            403,
            "warning",
            "Your role does not allow this action.",
            "Ask an administrator to grant the required role.",
        ),
        ErrorSpec(
            "not_found",
            404,
            "info",
            "The requested record does not exist.",
            "Check the identifier or refresh the list.",
        ),
        ErrorSpec(
            "validation_failed",
            422,
            "warning",
            "The request did not pass validation.",
            "Correct the highlighted fields and retry.",
        ),
        ErrorSpec(
            "source_unreadable",
            422,
            "error",
            "The uploaded file could not be opened as a PDF.",
            "Upload the original PDF; scanned images must be inside a PDF container.",
        ),
        ErrorSpec(
            "source_too_large",
            413,
            "warning",
            "The file exceeds the configured size limit.",
            "Ask an administrator to raise MAX_UPLOAD_BYTES or split the document.",
        ),
        ErrorSpec(
            "page_limit_exceeded",
            422,
            "warning",
            "The document has more pages than a single job may process.",
            "Ask an administrator to raise MAX_PAGES_PER_JOB; the source stays registered.",
        ),
        ErrorSpec(
            "idempotency_conflict",
            409,
            "warning",
            "This idempotency key was already used with a different request.",
            "Use a new idempotency key for a new request.",
        ),
        ErrorSpec(
            "conflict_stale_version",
            409,
            "warning",
            "The record changed since you loaded it.",
            "Reload the record and reapply your change.",
        ),
        ErrorSpec(
            "invalid_transition",
            409,
            "error",
            "The requested state change is not allowed from the current state.",
            "Refresh the record; if the state is unexpected, report it.",
        ),
        ErrorSpec(
            "job_not_cancellable",
            409,
            "info",
            "The job has already finished.",
            "No action needed.",
        ),
        ErrorSpec(
            "storage_unavailable",
            503,
            "critical",
            "Object storage is not reachable.",
            "Retry shortly; if the problem persists, contact an administrator with the request id.",
        ),
        ErrorSpec(
            "database_unavailable",
            503,
            "critical",
            "The database is not reachable.",
            "Retry shortly; if the problem persists, contact an administrator with the request id.",
        ),
        ErrorSpec(
            "provider_unavailable",
            503,
            "error",
            "An external provider is unavailable.",
            "The job was stopped with a resume path; retry when the provider is back.",
        ),
        ErrorSpec(
            "budget_exceeded",
            409,
            "error",
            "A processing budget was reached.",
            "An administrator can raise the budget and resume the job.",
        ),
        ErrorSpec(
            "retries_exhausted",
            500,
            "error",
            "The job failed repeatedly and was stopped.",
            "Inspect the job events and retry after the cause is fixed.",
        ),
        ErrorSpec(
            "lease_lost",
            500,
            "error",
            "The worker lost its lease on the job.",
            "Another worker will resume the job from its last checkpoint.",
        ),
        ErrorSpec(
            "internal_error",
            500,
            "critical",
            "Something went wrong on our side.",
            "Retry; if it persists, report the request id.",
        ),
        ErrorSpec(
            "fixture_real_isolation",
            409,
            "critical",
            "Fixture data may not be joined with real-utility data.",
            "Use a fixture utility for fixture sources.",
        ),
        # Reserved for later milestones; listed so the taxonomy is complete from Milestone 0.
        ErrorSpec(
            "page_low_quality",
            422,
            "warning",
            "A page could not be read reliably.",
            "Review the page in the inventory.",
        ),
        ErrorSpec(
            "localisation_ambiguous",
            409,
            "warning",
            "More than one region claims to be the approved schedule.",
            "A reviewer must confirm the localisation.",
        ),
        ErrorSpec(
            "reader_disagreement",
            409,
            "warning",
            "Readers disagree on a table's structure.",
            "The table is routed to review.",
        ),
        ErrorSpec(
            "coverage_insufficient",
            200,
            "info",
            "Our reviewed coverage does not include this.",
            "See the coverage status for what is missing.",
        ),
    ]
}


class AppError(Exception):
    def __init__(
        self,
        error_type: str,
        detail: str | None = None,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if error_type not in ERROR_TAXONOMY:
            raise ValueError(f"unknown error_type {error_type!r}")
        self.spec = ERROR_TAXONOMY[error_type]
        self.error_type = error_type
        self.detail = detail
        self.extra = extra or {}
        super().__init__(detail or self.spec.user_message)

    def to_payload(self, request_id: str | None) -> dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.spec.user_message,
            "next_step": self.spec.next_step,
            "detail": self.detail,
            "severity": self.spec.severity,
            "request_id": request_id,
            **({"extra": self.extra} if self.extra else {}),
        }


@dataclass
class ErrorEnvelope:
    error_type: str
    message: str
    next_step: str
    severity: str
    request_id: str | None = None
    detail: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
