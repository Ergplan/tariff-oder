# Architecture (as implemented through Milestone 4b)

The governing design is Section 4 of the specification.  This document records what exists.

## Services

```
browser ──► apps/web (Next.js, server components) ──► services/api (FastAPI) ──► PostgreSQL 16 + pgvector
                                                                │                    ▲
                                                                └──► object store    │ FOR UPDATE SKIP LOCKED
                                                                     (sources/*.pdf) │
                                                    services/worker (job runner) ────┘
```

| Component | Implementation | Notes |
| --- | --- | --- |
| Web | `apps/web` — App Router, server-side fetch to the API, same-origin proxy routes for upload and file bytes | Never touches the database; forwards identity (local header or IAP assertion) |
| API | `services/api/src/tariff_api` — FastAPI app factory (`main.create_app`), routers `health`, `sources`, `jobs`, `registry` | Single schema owner; Alembic migrations under `services/api/migrations` |
| Worker | `services/worker/src/tariff_worker` — `Runner` polls the queue, runs handlers with a heartbeat thread | Handlers: `inventory_source` (M1) → `triage_source` (M2a) → `parse_source` (M2b), each chained automatically — only publication needs a human |
| Triage rules | `tariff_api.triage` (pure functions, `TRIAGE_VERSION`), `tariff_api.page_signals` (PyMuPDF extraction) | Classification, text-quality components, printed-label rule inference; thresholds are data, overridable per reading profile |
| Readers + OCR + headings | `tariff_api.readers` (PyMuPDF primary, pdfplumber secondary, agreement classes), `tariff_api.ocr` (tesseract subprocess, TSV), `tariff_api.headings` (inventory) | ADR-0009; Docling slots in behind the same `TableGrid` interface once measured |
| Queue | `jobs` + `job_events` tables; `tariff_api.queue` | Claim with `SELECT … FOR UPDATE SKIP LOCKED`; expired leases reclaimable; writes fenced by `(job_id, run_id)`; bounded attempts; checkpoints; cancellation flag |
| Adapters | `tariff_api.adapters` — `ObjectStore` (filesystem / GCS), `SecretProvider` (env / Secret Manager), `IdentityProvider` (local allow-list / IAP JWT) | Selected by `DEPLOYMENT_PROFILE`; invalid combinations refused at startup |
| Telemetry | `tariff_api.telemetry` — JSON lines on stdout with `request_id`, `job_id`, `run_id`, `actor`, `severity` | Same schema in both profiles; Cloud Logging parses `severity` |
| Contracts | `packages/contracts/openapi.json` → `src/api.d.ts` via openapi-typescript | Drift check script fails CI |

## Data model (Milestone 1 subset of Section 5.2)

`datasets` (exactly one `real`, one `fixture`) · `users` (roles) · `jurisdictions` →
`commissions` → `utilities` (identities + active reading profile) · `source_documents`
(content hash, immutable object key, inventory, state machine, golden-manifest check,
optimistic `version`) · `source_pages` (per-page inventory; `page_class`/`page_role` default
`unknown` until Milestones 2/3) · `jobs`, `job_events` · `audit_events` (append-only via
trigger) · `idempotency_records`.

The full Section 6.2 state machine is encoded in `models.SOURCE_TRANSITIONS`; Milestones 1–2a
exercise `uploaded → inventoried → triaged → parsed` and `→ failed`; a stage re-run moves the source
back through `needs_reprocessing` to the stage's input state, audited.  Candidates, facts, evidence spans,
review decisions and reading profiles are later migrations — nothing pre-empts their shape.

## Request and job lifecycle

1. `POST /sources` (administrator): size and PDF-header checks → SHA-256 → dedup lookup →
   `storage.put(sources/<sha>.pdf)` (immutable) → `source_documents` row → audit event →
   `enqueue(inventory_source, idempotency_key=inventory_source:<sha>:1)`.  An
   `Idempotency-Key` header replays the stored response for an identical request and
   returns `idempotency_conflict` for a different one.
2. Worker claims the job, opens the bytes, verifies the hash, records document-level facts,
   then inventories pages in batches (`INVENTORY_CHECKPOINT_EVERY_PAGES`), upserting rows
   with `ON CONFLICT DO NOTHING` and checkpointing `next_page`.  A killed worker leaves a
   dangling lease; the next claim after expiry resumes from the checkpoint (tested).
3. `GET /sources/{id}` shows the inventory summary and the latest job; `GET /sources/{id}/file`
   streams the bytes through authorization (no signed/public URLs).

## Localisation (Milestone 3a)

`parsed -> localised`: the worker binds a reading profile (detected from the heading
inventory or assigned by an administrator), builds per-page inputs (text layer in reading
order or the OCR artefact text, triage class, parse headings, grid counts) and runs
`tariff_api.localisation.localise`.  The result — regions with cues, findings, a status of
`proposed` or `ambiguous` — is stored as an immutable artefact and as rows the reviewer can
edit.  `POST /sources/{id}/localisation/decision` (reviewer+) confirms or corrects; only that
sets `extraction_allowed`.  `PUT /sources/{id}/profile` (admin) re-binds and re-runs.  Profiles
are data in `packages/reading-profiles/` (ADR-0010).

## Structure (Milestone 3b)

`localised -> gridded`, queued by the reviewer's localisation decision and refused while
`extraction_allowed` is false: for `tables` profiles the parse stage's primary grids inside
the approved regions go through `tariff_api.grid_integrity` (header/row paths, continuation,
merged cells, unit binding with source, footnotes); for `clause_outline` profiles the page
text goes through `tariff_api.clause_outline`.  Both use `tariff_api.normalise` for values.
Rows land in `structure_cells` / `clause_values`; artefacts under `<sha>/grid/<tool>/`.
`GET /sources/{id}/structure/cells` (filters: page, unresolved, flag) and
`/structure/clauses` (category, kind) expose them; the detail page shows the integrity
summary, the unresolved cells and the clause outline (ADR-0011).

## Extraction and validation (Milestone 4a)

`gridded -> extracted`: for each approved region the structure channel receives the serialised
cells/clauses and the image channel the page images, both through the provider adapter
(`fixture` by default; `anthropic` with a key); prose decisions come from the network-charge
regions; network-charge and loss-trajectory grids and the green-tariff provisions become single-channel typed facts with derivation inputs; condition records are stored verbatim; channels are compared field by field and every candidate gets confidence, risk tags
and a routing.  `extracted -> validated -> awaiting_review`: the deterministic validators run,
findings attach, affected candidates go to individual review.  Endpoints:
`/sources/{id}/candidates`, `/candidates/{id}`, `/sources/{id}/findings`,
`/sources/{id}/extraction-runs`, `/sources/{id}/conditions`, `/review/queue`, `/sources/{id}/dispositions` (ADR-0012).

## Profiles

| Concern | `local` | `gcp` |
| --- | --- | --- |
| Storage | `FilesystemObjectStore(OBJECT_STORE_ROOT)` | `GcsObjectStore` (sources/artefacts/exports buckets) |
| Secrets | process env | Secret Manager (`<NAME>/versions/latest`) |
| Identity | `X-Local-User` on an explicit allow-list; refuses to construct under `gcp` | IAP JWT assertion verified against configured audiences; role from `users` |
| Database | any PostgreSQL 16 + pgvector | Cloud SQL private IP via Direct VPC egress |
| Worker | `tariff-worker` long poller (compose) | Cloud Run Job `--drain` on a Cloud Scheduler cadence |

Prohibited and enforced by review: branching on hostname/platform, cloud SDK use outside
`adapters/`, a second schema definition.
