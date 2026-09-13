# BUILD_STATE

Last updated: 2026-09-13. Branch `claude/keen-tesla-r9mvv5`.
Increments so far: (1) Milestone 0 + Milestone 1; (2) dev-project wiring and bucket ingest;
(3) first verification against the real project; (4) Milestone 2a — page triage.

## Current milestone and status

- **Milestone 0 — complete.** Repository was empty (no commits); audit, ADR-0001…0007,
  architecture, data dictionary, reliability ledger skeleton, error taxonomy, evaluation
  plan with the D/E/F question set, deployment doc, milestone checklist all written.
- **Milestone 1 — implemented and tested under the `local` profile; cloud gate still blocked.**
  Everything the gate requires runs locally against real PostgreSQL 16 + pgvector.  Terraform
  now targets the real project (`tariff-order-parsing`) and validates, but **nothing has been
  planned or applied**: this build environment has no `gcloud` and its Google token is rejected
  (`ACCESS_TOKEN_TYPE_UNSUPPORTED`, re-checked after the project details arrived).  The apply
  has to run on the `tariff-order` VM.
- **Milestone 2 — part (a) implemented and tested: page triage.**  Classification, text-layer
  quality, printed-label maps, immutable stage artefacts, resumable and re-runnable.  Part (b)
  — OCR execution, the second reader, table grids and agreement scoring — is the next task.
- **No parser beyond PyMuPDF, no provider connection, no extracted number, no reviewer
  decision exists.**

### Increment 4 (Milestone 2a: page triage)

- Stage `inventoried → triaged` (`tariff_worker.stages.triage`), chained automatically after
  inventory; page-batched checkpoints; pages already triaged at the current rules version are
  skipped on resume; one immutable JSON artefact per page plus one per document under
  `<sha>/triage/pymupdf@<v>+rules@<v>/`, indexed in the new `stage_artefacts` table.
- `tariff_api.triage` — pure, versioned rules (`TRIAGE_VERSION = "1"`): eight page classes
  with a recorded rationale each (`unknown` when nothing matches); three independent
  text-quality components (glyph coverage, dictionary hit rate gated on token count,
  reading-order sanity) with separate flags; footer label extraction anchored to line ends;
  document-wide label rule inferred as segments of (style, offset) — singleton disagreements
  excluded, agreeing neighbours merged — and every page resolved with a recorded source.
- API: pages carry `label_declared/observed/source`, `text_quality`, `ocr_recommended`,
  `triage_rationale`; `?page_class=` and `?ocr_recommended=` filters; source detail carries a
  `triage` summary (class histogram, label rule, OCR/low-quality/unknown/label-flagged page
  lists) and its artefact index; `POST /sources/{id}/stages/rerun` (admin) re-runs a stage
  through the transition table, audited.  Web: triage section and per-page badges.
- Fixtures: `labelled_order_pdf` (12 pages: roman i–iii, then index − 3 with footer-less
  pages, a ruled table, a vector-drawn table with no text, an image-only page, a blank page,
  an annexure cover, one wrong footer) and `garbled_text_pdf`.
- Three rule defects were found by running the rules over the fixtures before locking
  thresholds, and fixed with tests: a weighted quality score let consonant soup pass; running
  prose ("see page 12 of the petition") was read as a footer label; a numeric table was
  classed `mixed` because prose was measured in characters rather than words.  A fourth in
  label inference: one wrong footer split a continuous rule in two.

### Increment 2 (dev-project wiring and bucket ingest)

- `infra/gcp/envs/dev.tfvars` and `dev.backend.hcl` carry the real values: project
  `tariff-order-parsing`, region `asia-south1`, state in `gs://tarifforderstudio_tfstate`.
- Terraform **adopts** `gs://tarifforderstudio_sources` instead of creating a source bucket
  (`var.existing_source_bucket`); artefacts/exports/backups are still created in `asia-south1`.
- The load balancer, managed certificate and IAP are created only when `var.domain` is set.
  With no domain (the current dev state) Cloud Run is `INGRESS_TRAFFIC_INTERNAL_ONLY` — no
  public endpoint exists at all.  The budget resource is likewise gated on `billing_account_id`.
- New `scripts/verify-gcp-setup.sh`: read-only check of project, billing and budget, the 15
  required APIs, both buckets (location, uniform access, versioning, public-access prevention),
  the presence of the three PDFs with their expected hashes, the `agent-builder` roles, and the
  VM's zone.  Prints OK / MISSING / DEVIATION with the fix command and exits non-zero on MISSING.
- **Bucket ingest**: `GET /sources/inbox` lists objects with registration state;
  `POST /sources/ingest` registers one by key.  The bytes are re-read and hashed, so an
  object's name is never identity; dedup, golden-manifest reconciliation and the inventory job
  are the same code path as a browser upload.  `ObjectStore.list` added to both adapters.
- Two test-quality defects found and fixed while writing those tests: the synthetic PDF
  generators were not byte-reproducible (PyMuPDF stamps timestamps and randomises the trailer
  `/ID`), which made every hash-based assertion vacuous; and the object store was shared across
  tests, so an immutable key served an earlier test's bytes.  Both now have tests
  (`test_synthetic_fixtures_are_byte_reproducible`, per-test `object_store_root` fixture).
- ADR-0008 records the dev topology and the two accepted deviations (multi-region source
  bucket; `roles/editor` on the build SA).  `CLAUDE.md` and `docs/build-spec.md` added.

## Deployment profile(s) exercised

- `local`: PostgreSQL 16.15 + pgvector 0.6.0 (apt packages, ephemeral cluster on :5433),
  filesystem object store, env secrets, local identity allow-list.  API + worker + Next.js
  web ran together end-to-end in this session (upload through the web proxy → inventory →
  detail page → authorized file reopen).
- `gcp`: adapters implemented (`GcsObjectStore`, `SecretManagerProvider`,
  `IapIdentityProvider`) but **not exercised** against real services.  Docker daemon was
  unavailable, so images were not built here; Dockerfiles are validated only by reading.

## Implemented user-visible behaviour

- Status page: readiness (DB, migration head, pgvector, storage), profile/adapters, tool
  versions, limits, queue depth, dataset counts; states plainly that coverage is empty.
- Source inbox: upload with dataset choice (real/fixture) and idempotency key; dedup result
  banner; list with state, page count, text-layer counts (unknown badges until inventoried).
- Source detail: pipeline stage track, latest job with live progress (`pages_done/total`),
  document metadata (PDF version, producer, encryption, tagging, fonts not embedded),
  golden-manifest reconciliation, page inventory table (index, declared label, size,
  rotation, text chars, text layer, images, drawings, class=unknown, role=unknown),
  authorized "open the PDF" link.
- Jobs page and Registry page (seeded jurisdictions/commissions/utilities, no coverage claim).
- API: `/healthz`, `/readyz`, `/status`, `/me`, `/sources` (POST/GET), `/sources/{id}`,
  `/sources/{id}/pages`, `/sources/{id}/file`, `/sources/{id}/reprocess`, `/jobs`,
  `/jobs/{id}`, `/jobs/{id}/cancel`, `/registry`, `/utilities`, `/users`, `/audit`.
  OpenAPI at `/docs`.

## Exact commands to run and test

```bash
make install                      # uv sync --all-packages && pnpm install --frozen-lockfile
make ephemeral-postgres           # or: docker compose stack via `make dev`
export DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5433/tariff_dev
export LOCAL_USER_ALLOWLIST="admin@example.com:administrator,reviewer@example.com:reviewer,analyst@example.com:analyst"
make migrate seed
make api                          # :8000
make worker                       # long poller; `uv run tariff-worker --drain` for one pass
API_BASE_URL=http://127.0.0.1:8000 LOCAL_WEB_USER=admin@example.com make web   # :3000
make test                         # TEST_DB defaults to :5433/tariff_test
make lint && make contracts-check && make build-web
make tf-plan ENV=dev              # requires gcloud auth + filled envs/dev.tfvars (blocked here)
```

## Schema, API, adapter, and reading-profile changes

- Migration `0001_foundation`: datasets, users, jurisdictions, commissions, utilities,
  source_documents, source_pages, jobs, job_events, audit_events (append-only trigger),
  idempotency_records; enums dataset_kind, user_role, jurisdiction_kind, source_state (full
  Section 6.2 set), job_status; extensions vector, pgcrypto.
- API contract v0.1.0 exported to `packages/contracts/openapi.json`; types generated.
- Adapters: storage (filesystem, gcs), secrets (env, secret_manager), identity (local, iap).
- Reading profiles: none yet (`packages/reading-profiles/` holds a README; Milestone 3).

## Source files and dataset coverage actually used (hashes)

- **None of the three real orders was available** in this environment (only the
  specification markdown was uploaded).  Their expected hashes are in
  `tests/golden/manifest.json` (`ff36813e…174b1a` NPCL, `d84997a4…95fcf50` KERC,
  `1c4697f8…95925e1a` GERC) with `bytes_present: false`.
- Synthetic fixtures only (dataset `fixture`): `mixed_text_and_image_pdf` (6 pages), `text_only_pdf` variants, `not_a_pdf`.

## Reading reliability ledger changes

`docs/reading-reliability.md` created with every Section 6.1 failure mode as a row.
Handled+tested: D5 (printed-label maps), P4, P6, P7, P8, P9, P10, P11, P12, P13–P15
(ingest, reproducible fixtures), P16 (immutable versioned artefacts), P17 (unknown is visible).
Detected+tested, handling pending OCR (M2b): D1 (image-only), D2 (corrupted text layer),
D3 (rotation), D8 (vector-drawn tables).  Detected: D7, D9.  Everything structure-, value-
and network-level `n/a-yet` pending Milestones 3–4.

## Tests and evaluations executed, with results and denominators

Run in this session against PostgreSQL 16.15 on :5433 (`uv run pytest -q`):

- **70 passed, 0 failed, 0 skipped** (~20 s): 43 unit (12 adapters/profile, 31 triage rules), 27
  integration (7 sources, 5 ingest/CLI, 6 queue, 1 worker-kill recovery, 5 triage stage incl.
  a second worker-kill resume and a stage rerun, 2 migrations, 1 registry).  Three consecutive
  clean runs after one earlier intermittent failure in a lease-expiry test (2 s lease, 2.5 s
  wait); the wait margin was widened to 3.5 s.  Not a product defect.
  (`tests/integration`: 7 sources, 4 ingest, 6 queue, 1 worker-kill recovery, 2 migrations,
  1 registry).  Run twice in different orders to confirm no inter-test dependence.
- Worker-kill recovery: 1 hard kill (`os._exit(137)` after checkpoint `next_page=3`), lease
  2 s, resumed by a second worker; 6/6 page rows, 0 duplicates, attempts=2, events include
  `lease_expired_reclaimed`.
- Migrations: downgrade to base and upgrade to head on a scratch DB: pass.
- `ruff check` + `ruff format --check`: clean.  `tsc --noEmit`: clean.  `next build`: success
  (8 routes).  `terraform fmt` + `terraform validate` (google 6.30.0 via filesystem mirror):
  valid, 2 provider warnings about `secret_data_wo`.
- Contract drift script (`pnpm --filter @tariff/contracts check`): executed, reports
  `contracts: no drift` against the committed `openapi.json` and `api.d.ts` (now including
  the inbox/ingest endpoints).
- End-to-end smoke (manual, this session): web upload → HTTP 201 → worker drained 1 job in
  0.04 s → detail page shows `inventoried` → file reopened via web proxy (6,714 bytes, same
  hash).
- Not run: container image builds (no Docker daemon), anything against Google Cloud.

## Real provider calls versus fixtures

No provider (Claude, OpenAI, OCR) is integrated in Milestone 1.  Zero real provider calls.

## Reviewer decisions obtained versus pending

None required and none obtained.  No candidates exist.

## Review/publication status and completeness declarations

Nothing reviewed, nothing published, no coverage declared for any utility.

### Increment 3 (first real verification against the project)

`scripts/verify-gcp-setup.sh` was run on the VM by the operator.  Findings and what changed:

- **Two bugs in the verify script itself**, both fixed: `read` with the default IFS collapses
  consecutive tabs, so gcloud's empty fields shifted every bucket column left (it reported the
  public-access-prevention value as "uniform access"); and the billing check reported
  "billing account not linked" when the real cause was that the caller has no billing
  permission.  Bucket facts are now parsed from JSON (accepting both the `gcloud storage` and
  JSON-API field spellings), and the script distinguishes MISSING from a new **UNKNOWN**
  state — "could not verify" is never reported as "fine".
- **Two deployment bugs found by reasoning about the verify output**, both fixed with tests:
  with no domain `IAP_AUDIENCE` is empty, and `IapIdentityProvider` refused to construct — the
  API container would have crash-looped on first deploy.  It now starts and fails closed
  (refuses every request, logs a warning, shows `UNCONFIGURED` in `/status`).  And the worker
  and CLI were building an identity provider they must never have; `build_adapters` now takes
  `include_identity=False` for processes that serve no requests.
- **The build VM cannot reach the deployed system**: it is in the default VPC in `asia-south2`,
  while Terraform builds its VPC in `asia-south1` with private-IP Cloud SQL and VPC-internal
  Cloud Run.  Rather than widen the network, administration runs as a new `tariff-admin` Cloud
  Run Job inside the VPC, driving the same `tariff-api` CLI.  New CLI commands: `inbox`,
  `ingest`, `users add|list` (`--actor` must be an email, so the audit trail names a person).
- **A latent test-harness trap**, fixed: adapters were built in the FastAPI lifespan handler, so
  fixtures that touched `app.state.adapters` worked or failed depending on the order fixtures
  appeared in a test signature.  They are built eagerly in `create_app` now.

Outstanding on the project itself, for the operator: four APIs to enable
(`secretmanager`, `iap`, `cloudscheduler`, `cloudbuild`), object versioning on both buckets,
the three PDFs to upload, and the budget to confirm and its account id to paste into
`envs/dev.tfvars`.  Re-run the verify script after fixing them.

## Known defects and blocked acceptance gates

- **Blocked (M1 gate):** deployment to the `dev` project, migrations against Cloud SQL, Cloud
  Logging visibility, backup/restore on Cloud SQL, post-deploy integration run.  The project,
  billing, buckets, service account and VM now exist; what is missing is a run of
  `scripts/verify-gcp-setup.sh` + `make tf-plan/tf-apply ENV=dev` **on the VM**, since this
  environment cannot authenticate to Google.
- **Deferred by decision (ADR-0008):** IAP-protected browser access, pending a domain.  Until
  then Cloud Run has no public ingress and the API is driven from inside the VPC.  The
  web → API service-to-service identity token is written but untested.
- **Blocked (M1 gate):** "upload the real NPCL file" — bytes not supplied.  When supplied,
  registration will verify hash/size/page count/text-layer ranges against the manifest.
- Web → API service-to-service auth under the gcp profile needs a Cloud Run identity token
  (documented in `docs/deployment.md`); untested.
- Cloud documentation was not reachable (proxy 403); service limits/pricing in
  `docs/deployment.md` are to be re-verified before apply.
- Declared PDF page labels only; footer-derived printed labels and the offset map are
  Milestone 2.
- `apps/web` has no automated browser tests yet (Section 7.5 browser tests start when the
  review flow exists).
- Docker Compose stack and Dockerfiles untested in this environment (no daemon).

## Architecture decisions and rationale

ADR-0001 service boundaries · ADR-0002 migration owner + OpenAPI contract · ADR-0003
PostgreSQL queue with fenced leases · ADR-0004 platform adapters, filesystem local store ·
ADR-0005 PyMuPDF inventory tooling · ADR-0006 asia-south1, per-env projects, Cloud Run Job
worker (revisit in M8) · ADR-0007 fixture/real isolation via datasets.

## Next smallest actionable task

1. **Operator, on the `tariff-order` VM:** clone the branch and run
   `scripts/verify-gcp-setup.sh`.  It will confirm or flag the four open items (budget,
   tfstate versioning, enabled APIs, PDFs present) and print the `billing_account_id` to paste
   into `envs/dev.tfvars`.  Then `make tf-init tf-plan ENV=dev` and review the plan before any
   apply.  Copy the three PDFs to `gs://tarifforderstudio_sources/inbox/` if not already there.
2. Engineering (Milestone 2b, next run): execute OCR (tesseract, via apt in the image) on
   `ocr_recommended` pages and reconcile with any existing text; add the reader interface with
   PyMuPDF and pdfplumber producing table grids for `table`/`mixed` pages, agreement scoring
   (cell count, header row, normalised cell text) recorded per grid; document-wide heading
   and table inventory (`RATE SCHEDULE …`, `TARIFF SCHEDULE …`, `<n>. RATE: …` headings de-
   duplicated); inventory UI.  Docling stays behind the reader interface until it can be
   measured on real pages — it pulls a large ML stack that this environment cannot verify.
   Then, as soon as the three PDFs are in the bucket: ingest, inventory, triage, and compare
   the triage output with Parts D–F (NPCL 402–423 `image_only`; KERC 226–240
   `vector_graphics_text_sparse` and the printed 209 → PDF 225 rule; GERC all-text with roman
   front matter and the −16 rule).
