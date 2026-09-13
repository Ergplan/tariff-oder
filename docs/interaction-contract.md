# Interaction contract (Section 7 as implemented — Milestone 1)

## Principles implemented so far

| # | Principle | Implementation | Evidence |
| --- | --- | --- | --- |
| 1 | Every action has an explicit result state | Upload returns `SourceRegistration{deduplicated, job, idempotent_replay}`; jobs carry `status/stage/progress/error_type`; sources carry `state/state_reason` | `schemas.py`; `test_sources.py` |
| 2 | Long operations are jobs with visible progress | Inventory is a queued job; progress `{pages_done, pages_total}` at every checkpoint; source page polls every 3 s while queued/leased and shows stage, attempt, worker | `apps/web/app/sources/[id]` |
| 3 | No optimistic UI for facts | Upload form renders the result only from the backend response; registered/deduplicated banners come from the response | `upload-form.tsx` |
| 4 | Typed, explained, recoverable failures | `errors.py` taxonomy; every error payload has `error_type`, `message`, `next_step`, `severity`, `request_id`; unhandled exceptions → `internal_error` with request id, stack trace only in logs | `test_unauthenticated_and_role_enforcement`, `test_unreadable_and_non_pdf_are_typed_failures` |
| 5 | Irreversible actions confirm with consequences | Not yet applicable (no publication/supersede/delete actions exist); `deletion_protection` guards infra | — |
| 6 | Screens survive refresh/reconnect | Server-rendered pages; job progress polling via refresh (a dropped connection never marks a job failed) | `auto-refresh.tsx` |
| 7 | Every number carries provenance | Not yet applicable (no numbers); source bytes reachable from every source row | — |
| 8 | Idempotent actions | `Idempotency-Key` on upload (client generates one per attempt; reused on retry); job enqueue idempotent on key; fenced worker writes | `test_idempotent_upload`, `test_queue.py` |
| 9 | Stale-version protection | `source_documents.version` counter exists; enforced on review/publication in Milestone 5 | — |
| 10 | Unknown is never "fine" | `page_class`/`page_role` render as `unknown` badges; missing inventory shows `unknown`, never a default; status page states coverage is empty | components `UnknownBadge` |

## Error taxonomy

Defined in `services/api/src/tariff_api/errors.py` and exported in the OpenAPI document as
`ErrorResponse`.  Each entry: `error_type`, HTTP status, severity (`info`, `warning`,
`error`, `critical`), user message (what happened), next step (what to do).

| error_type | HTTP | Severity | When |
| --- | --- | --- | --- |
| unauthenticated | 401 | warning | No/unknown identity |
| permission_denied | 403 | warning | Role too low; IAP user not registered |
| not_found | 404 | info | Unknown id |
| validation_failed | 422 | warning | Request validation |
| source_unreadable | 422 | error | Not a PDF / cannot open |
| source_too_large | 413 | warning | `MAX_UPLOAD_BYTES` |
| page_limit_exceeded | 422 | warning | `MAX_PAGES_PER_JOB` |
| idempotency_conflict | 409 | warning | Key reused with different request |
| conflict_stale_version | 409 | warning | Record changed since load (M5) |
| invalid_transition | 409 | error | Disallowed state change |
| job_not_cancellable | 409 | info | Job already finished |
| storage_unavailable | 503 | critical | Object store unreachable / object missing |
| database_unavailable | 503 | critical | DB unreachable |
| provider_unavailable | 503 | error | External provider down (M4+) |
| budget_exceeded | 409 | error | Token/cost/page budget (M4+) |
| retries_exhausted | 500 | error | Job failed `max_attempts` times |
| lease_lost | 500 | error | Worker lost its lease |
| internal_error | 500 | critical | Unhandled |
| fixture_real_isolation | 409 | critical | Fixture ↔ real join attempted |
| page_low_quality, localisation_ambiguous, reader_disagreement, coverage_insufficient | — | — | Reserved for M2–M7 |

Severity levels: `info` (expected outcome), `warning` (user can fix), `error` (system stopped
a unit of work with a recovery path), `critical` (availability or integrity at risk; page an
operator).

## Reviewer, analyst and administrator workflows

Not implemented in Milestone 1 beyond the administrator's source inbox (upload, dedup
result, per-stage state, typed failures, reprocess/cancel via API) and registry/users/audit
endpoints.  Localisation checkpoint (M3), review workspace and publication (M5), explorer and
comparison (M5–M6), Q&A (M7) follow the spec's Sections 7.2–7.4 when built.
