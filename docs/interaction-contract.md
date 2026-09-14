# Interaction contract (Section 7 as implemented — Milestones 1–5)

## Principles implemented so far

| # | Principle | Implementation | Evidence |
| --- | --- | --- | --- |
| 1 | Every action has an explicit result state | Upload returns `SourceRegistration{deduplicated, job, idempotent_replay}`; jobs carry `status/stage/progress/error_type`; sources carry `state/state_reason` | `schemas.py`; `test_sources.py` |
| 2 | Long operations are jobs with visible progress | Inventory is a queued job; progress `{pages_done, pages_total}` at every checkpoint; source page polls every 3 s while queued/leased and shows stage, attempt, worker | `apps/web/app/sources/[id]` |
| 3 | No optimistic UI for facts | Upload form renders the result only from the backend response; the review workspace shows a decision as recorded only from the API's `DecisionResult` | `upload-form.tsx`, `review-workspace.tsx` |
| 4 | Typed, explained, recoverable failures | `errors.py` taxonomy; every error payload has `error_type`, `message`, `next_step`, `severity`, `request_id`; unhandled exceptions → `internal_error` with request id, stack trace only in logs | `test_unauthenticated_and_role_enforcement`, `test_unreadable_and_non_pdf_are_typed_failures` |
| 5 | Irreversible actions confirm with consequences | Publication is preview-then-confirm: the preview shows facts to publish, open items and missing required items and returns a token; the publish call must carry the token and `confirm_consequences`; a change in between fails with `conflict_stale_version`. Review decisions are reversible by undo until published | `test_publication_and_explorer.py`, `publish-form.tsx` |
| 6 | Screens survive refresh/reconnect | Server-rendered pages; job progress polling via refresh (a dropped connection never marks a job failed) | `auto-refresh.tsx` |
| 7 | Every number carries provenance | Every candidate carries cell/clause evidence; the review workspace renders the cited page with the cited table outlined through `/candidates/{id}/evidence/{n}/image`; every published value in the explorer links to its citation and cited page through `/explorer/facts/{id}/evidence/{n}/image` | `review-workspace.tsx`, `explorer/[id]/shared.tsx` |
| 8 | Idempotent actions | `Idempotency-Key` on upload and on review decisions (client generates one per attempt; reused on retry); job enqueue idempotent on key; fenced worker writes | `test_idempotent_upload`, `test_queue.py`, `test_review_workflow.py` |
| 9 | Stale-version protection | `expected_version` mandatory on localisation and review decisions, `expected_source_version` + preview token on publication; mismatch → `conflict_stale_version` with the current version in `extra`, nothing written | `test_localise_stage.py`, `test_review_workflow.py`, `test_publication_and_explorer.py` |
| 10 | Unknown is never "fine" | `page_class`/`page_role` render as `unknown` badges; missing inventory shows `unknown`, never a default; status page states coverage is empty; the explorer answers `coverage_insufficient` for a source without a release and labels partial releases with their gaps | components `UnknownBadge`, `CompletenessBannerView` |

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
localisation checkpoint (Milestone 3a), the review workflow (Milestone 5a) and the
publication transaction (Milestone 5b) below.  Analyst: the published explorer and the
open-access view (5b).  Comparison (6), Q&A and report-a-problem (7) follow.

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

### Publication (Section 7.2, Milestone 5b; ADR-0014)

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Transaction over a declared scope | `POST /sources/{id}/publish` with `whole_schedule` or `subset` (categories and/or families) | `test_publication_and_explorer.py` |
| Shows the coverage checklist, unresolved items and second-review status first | `POST /sources/{id}/publish/preview` returns facts to publish, pending / awaiting-second-review / unresolved / blocked candidates, missing required items, gap keys, the checklist and the prior release, plus a token | same; `publish-form.tsx` |
| Explicit completeness declaration; fails on missing required items | `complete` refused with `extra.missing`; `partial` must declare every gap key (`extra.undeclared_gaps`); blocked candidates refuse (`extra.blocked`) | same |
| Fails on stale versions | `expected_source_version` and the preview token both checked → `conflict_stale_version` | same |
| Partial labelled everywhere | `completeness` + `gaps` on the release, the explorer banner, the network view, the release list, the source page | same; `CompletenessBannerView` |
| Correction history intact; published decisions frozen | `published_release_id` on the candidate; decide/undo refused with `invalid_transition`; decision rows never deleted | same |
| Cache invalidation | Explorer reads the current release per request and carries its id; no cache exists yet (ADR-0014) | — |

### Analyst workflow (Section 7.3, Milestone 5b)

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Coverage always visible | Completeness banner (release, complete/partial, gaps, open counts, fixture flag) on every explorer view; `coverage_insufficient` when no release exists | `explorer/[id]/shared.tsx` |
| Every number carries its provenance affordance | Each fact row lists its citations (pdf page, printed page, table id, cell or line) linking to the rendered cited page | `Citations` |
| Open-access and network charges view (screen 6a) | `/explorer/{id}/network`: per family, published facts with derivation inputs, decision status and citations, or `coverage_insufficient` with the reviewed disposition | `explorer/[id]/network/page.tsx` |
| Context first, comparisons, report-a-problem, persistent chips | Not built (Milestones 6–7) | — |
