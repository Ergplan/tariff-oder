# BUILD_STATE

Last updated: 2026-09-13 (first run: Milestone 0 + Milestone 1). Branch `claude/keen-tesla-r9mvv5`.

## Current milestone and status

- **Milestone 0 — complete.** Repository was empty (no commits); audit, ADR-0001…0007,
  architecture, data dictionary, reliability ledger skeleton, error taxonomy, evaluation
  plan with the D/E/F question set, deployment doc, milestone checklist all written.
- **Milestone 1 — implemented and tested under the `local` profile; cloud gate blocked.**
  Everything the gate requires runs locally against real PostgreSQL 16 + pgvector.  The
  Google Cloud `dev` project was not created or deployed: no credentials, no `gcloud`, and
  the `CLOUDSDK_AUTH_ACCESS_TOKEN` present in the environment is rejected by Google APIs
  (`ACCESS_TOKEN_TYPE_UNSUPPORTED`).  Terraform for `dev` is written and validated, not applied.
- **No parser, no provider connection, no extracted number, no reviewer decision exists.**

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
Handled+tested: P4 (partial run/retry duplicates), P6 (dedup), P7 (idempotent upload),
P8 (unreadable upload), P9 (fixture isolation), P10 (authorization), P11 (local adapter in
cloud), P12 (golden manifest verified not copied).  Detected only: D1, D3, D5 (declared
labels), D7, D9.  Everything else `n/a-yet` pending Milestones 2–4.

## Tests and evaluations executed, with results and denominators

Run in this session against PostgreSQL 16.15 on :5433 (`uv run pytest -q`):

- **25 passed, 0 failed, 0 skipped** (8.7 s): 8 unit (`tests/unit`), 17 integration
  (`tests/integration`: 7 sources, 6 queue, 1 worker-kill recovery, 2 migrations, 1 registry).
- Worker-kill recovery: 1 hard kill (`os._exit(137)` after checkpoint `next_page=3`), lease
  2 s, resumed by a second worker; 6/6 page rows, 0 duplicates, attempts=2, events include
  `lease_expired_reclaimed`.
- Migrations: downgrade to base and upgrade to head on a scratch DB: pass.
- `ruff check` + `ruff format --check`: clean.  `tsc --noEmit`: clean.  `next build`: success
  (8 routes).  `terraform fmt` + `terraform validate` (google 6.30.0 via filesystem mirror):
  valid, 2 provider warnings about `secret_data_wo`.
- Contract drift script (`pnpm --filter @tariff/contracts check`): committed files are the
  ones generated in this session; the script itself was not executed end-to-end here
  because it shells out through `uv` and `npx` — CI runs it.
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

## Known defects and blocked acceptance gates

- **Blocked (M1 gate):** deployment to the `dev` project, migrations against Cloud SQL,
  IAP-protected access, Cloud Logging visibility, backup/restore on Cloud SQL, post-deploy
  integration run.  Needs: a GCP project + billing account, `gcloud` auth for
  `venture@aayuda.energy`, a domain for the managed certificate.
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

1. Operator: supply the three PDFs (or a path/bucket) and, if cloud work is wanted, a dev
   project + `gcloud` auth; then run `make tf-init tf-plan ENV=dev` and review.
2. Engineering (Milestone 2, next run): add the `triage` stage — page class (`narrative`,
   `table`, `mixed`, `image_only`, `vector_graphics_text_sparse`, …), text-quality score,
   footer-derived printed-label map (roman + offset), Docling + pdfplumber grids with
   agreement scoring, document heading/table inventory, inventory UI, resumable stage
   checkpoints — starting with the page-label map and `vector_graphics_text_sparse`
   detection, both testable on synthetic fixtures before the real files arrive.
