# Interaction contract (Section 7 as implemented — Milestones 1–5a)

## Principles implemented so far

| # | Principle | Implementation | Evidence |
| --- | --- | --- | --- |
| 1 | Every action has an explicit result state | Upload returns `SourceRegistration{deduplicated, job, idempotent_replay}`; jobs carry `status/stage/progress/error_type`; sources carry `state/state_reason` | `schemas.py`; `test_sources.py` |
| 2 | Long operations are jobs with visible progress | Inventory is a queued job; progress `{pages_done, pages_total}` at every checkpoint; source page polls every 3 s while queued/leased and shows stage, attempt, worker | `apps/web/app/sources/[id]` |
| 3 | No optimistic UI for facts | Upload form renders the result only from the backend response; the review workspace shows a decision as recorded only from the API's `DecisionResult` | `upload-form.tsx`, `review-workspace.tsx` |
| 4 | Typed, explained, recoverable failures | `errors.py` taxonomy; every error payload has `error_type`, `message`, `next_step`, `severity`, `request_id`; unhandled exceptions → `internal_error` with request id, stack trace only in logs | `test_unauthenticated_and_role_enforcement`, `test_unreadable_and_non_pdf_are_typed_failures` |
| 5 | Irreversible actions confirm with consequences | Review decisions are reversible by undo until publication; publication/supersede confirmation arrives with Milestone 5b | `test_review_workflow.py` (undo) |
| 6 | Screens survive refresh/reconnect | Server-rendered pages; job progress polling via refresh (a dropped connection never marks a job failed) | `auto-refresh.tsx` |
| 7 | Every number carries provenance | Every candidate carries cell/clause evidence; the review workspace renders the cited page with the cited table outlined through `/candidates/{id}/evidence/{n}/image` | `review-workspace.tsx` |
| 8 | Idempotent actions | `Idempotency-Key` on upload and on review decisions (client generates one per attempt; reused on retry); job enqueue idempotent on key; fenced worker writes | `test_idempotent_upload`, `test_queue.py`, `test_review_workflow.py` |
| 9 | Stale-version protection | `expected_version` mandatory on localisation and review decisions; mismatch → `conflict_stale_version` with the current version in `extra`, nothing written | `test_localise_stage.py`, `test_review_workflow.py` |
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
| conflict_stale_version | 409 | warning | Record changed since load (localisation record, candidate) |
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

Administrator: source inbox (upload, dedup result, per-stage state, typed failures,
reprocess/cancel), registry/users/audit endpoints, bucket ingest CLI.  Reviewer:
localisation checkpoint (Milestone 3a) and the review workflow below (Milestone 5a).
Publication, the explorer (5b), comparison (6) and Q&A (7) follow.

### Review workflow (Section 7.2, Milestone 5a; ADR-0013)

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Queue ordered by risk, then coverage impact, then confidence; filters by category, component, page range, risk tag, channel | `GET /sources/{id}/review/queue` (position + reason per item) | `test_review_workflow.py` |
| Completeness checklist from the inventory | `GET /sources/{id}/review/checklist`: inventory headings without candidates are `not_started` gaps; statuses `not_started`, `in_progress`, `approved`, `corrected`, `rejected`, `unresolved`, `disposition:<x>` | `test_review_policy.py`, `test_review_workflow.py` |
| Side by side: page image with the cited cell/header path, both channels when they disagree, findings | Workspace `/sources/{id}/review`; image via `/candidates/{id}/evidence/{n}/image` (cited table outlined) | `review-workspace.tsx` |
| Approve disabled until evidence rendered; decision records evidence viewed and time spent | View rows written by the image endpoint; decision must cite the reviewer's own view of evidence 0; `view_to_decision_ms` server-measured, `time_spent_ms` client-reported | `test_review_workflow.py` |
| Four outcomes; correct = structured edit + rationale + evidence selection; reject/unresolved need a reason | `POST /candidates/{id}/decision` | same |
| Cause tags on corrections | `cause_tag` mandatory: `wrong_table`, `header_misbound`, `unit`, `ocr`, `footnote_missed`, `cross_reference`, `other` | same |
| Second review for material items, formula components, corrected channel disagreements, first order from any utility | `second_review_*` settings; `awaiting_second_review`; different reviewer enforced | `test_review_policy.py`, `test_review_workflow.py` |
| Keyboard-first; batch approval only for high-confidence no-risk candidates, still one by one | keys n/p/a/c/r/u/Enter/z; `POST /review/batch` refuses everything else per item | same |
| Undo within the session before publication | `POST /review/decisions/{id}/undo`, same reviewer, latest decision only, history kept | same |
| Corrections feed the system | cause tags aggregated in `GET /review/telemetry`; the correction re-runs the validators | same |
| Telemetry without document text | `GET /review/telemetry`: review ms by risk tag, correction rate by cause and utility, outcomes, undo, second reviews | same |
