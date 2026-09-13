# Deployment

Two profiles, one codebase: `DEPLOYMENT_PROFILE=local` (developer machines, CI) and
`DEPLOYMENT_PROFILE=gcp` (dev → staging → prod projects).  Behaviour differs only in the
adapters listed in `docs/architecture.md`.

## The dev environment as it actually exists

| Item | Value |
| --- | --- |
| Project | `tariff-order-parsing` ("tariff order studio"), billing linked |
| Region for Cloud Run, Cloud SQL, Artifact Registry | `asia-south1` (pinned by Terraform, independent of where the VM sits) |
| Source PDFs | `gs://tarifforderstudio_sources` — adopted by Terraform, **multi-region `asia`** (accepted deviation, ADR-0008) |
| Terraform state | `gs://tarifforderstudio_tfstate`, prefix `tariff/dev` |
| Build identity | `agent-builder@tariff-order-parsing.iam.gserviceaccount.com` (Editor + admin roles, this project only) |
| Build VM | `tariff-order`, e2-standard-4, 100 GB, Ubuntu 25.10, Docker, Terraform, Node 22, Claude Code |
| Public ingress | **none** — no domain, so no load balancer and no IAP (ADR-0008) |
| Budget | set `billing_account_id` in `envs/dev.tfvars` to have Terraform create 50/80/100% alerts |
| Code | GitHub `Ergplan/tariff-oder` (repo name is spelled "tariff-oder"); GitLab mirror `icac1/tariff-order-readings` |

**Run this first, on the VM.** It is read-only and reports every outstanding item with the
exact command to fix it — enabled APIs, bucket location/versioning/uniform access, whether the
PDFs are present, whether a budget exists, and the service account's roles:

```bash
scripts/verify-gcp-setup.sh                     # defaults to tariff-order-parsing / asia-south1
```

It prints `OK`, `MISSING` (blocks the deploy) or `DEVIATION` (an accepted choice, recorded
here), and exits non-zero if anything required is missing.

## Google Cloud service choices (Section 3.1)

Decisions recorded at Milestone 0, refined by ADR-0008.  Google's product documentation was
not reachable from the build environment that wrote them (the agent proxy returns 403 for
cloud.google.com), so the limits below are the provider-documented values for the pinned
Terraform provider (`google ~> 6.30`) and **must be re-verified against current documentation
before the first apply**.

| Component | Choice | Notes |
| --- | --- | --- |
| Region | `asia-south1` for every data-bearing service | Data residency and latency; `asia-south2` is the fallback (ADR-0006) |
| Web + API | Cloud Run v2 services, 60 s request timeout | Ingress is internal-only without a domain, load-balancer-only with one |
| Worker | Cloud Run **Job** (`tariff-worker --drain`), 2 vCPU / 4 GiB, 60 min timeout, Cloud Scheduler every 5 min | Milestone 8 re-decides after measuring the 570-page KERC and 423-page NPCL runs |
| Queue | PostgreSQL table in Cloud SQL (`SELECT … FOR UPDATE SKIP LOCKED`) | ADR-0003 |
| Database | Cloud SQL PostgreSQL 16, private IP, automated backups + PITR (7-day logs, 14 backups) | `vector` extension created by migration 0001; verify pgvector availability for the chosen minor version |
| Object storage | `sources` adopted; `artefacts`, `exports`, `backups` created in `asia-south1`, uniform access, public access prevention enforced | Keys are content hashes; CMEK not enabled |
| Secrets | Secret Manager, ids equal env-var names; `DATABASE_URL` managed, provider keys created empty | No secret in images, git or logs |
| Identity | IAP when a domain exists; otherwise no public entry point at all | Roles always enforced in the API from the `users` table |
| Images | Artifact Registry `asia-south1-docker.pkg.dev/tariff-order-parsing/tariff/{python,web}`, amd64 | Pin digests per release in tfvars |
| Observability | Cloud Logging (JSON stdout with `severity`), 5xx alert, failed-job log metric + alert | Dashboards in Milestone 8 |
| Cost | Budget alerts (when `billing_account_id` is set), job concurrency 1, application page/size limits | Provider-token budgets arrive in Milestone 4 |

## Local profile

`make dev` (Docker): `infra/local/docker-compose.yml` starts `postgres` (pgvector/pgvector:pg16),
`migrate`, `api`, `worker`, `web`.  MinIO is available under the `minio` compose profile; the
default local object store is the filesystem (ADR-0004).

Without Docker: `make ephemeral-postgres` (needs `postgresql-16` + `postgresql-16-pgvector`),
then `make migrate seed api worker web` with the variables in `README.md`.

Environment variables (identical names in both profiles):

| Variable | local | gcp |
| --- | --- | --- |
| DEPLOYMENT_PROFILE | local | gcp |
| DATABASE_URL | postgres container / :5433 | Secret Manager |
| OBJECT_STORE_BACKEND / OBJECT_STORE_ROOT | filesystem / path | gcs (+ SOURCE_BUCKET, ARTEFACT_BUCKET, EXPORT_BUCKET) |
| SECRETS_BACKEND | env | secret_manager (+ GCP_PROJECT_ID) |
| IDENTITY_BACKEND | local (+ LOCAL_USER_ALLOWLIST `email:role,…`) | iap (+ IAP_AUDIENCE, comma-separated) |
| LOG_FORMAT | json or text | json |
| MAX_UPLOAD_BYTES, MAX_PAGES_PER_JOB, JOB_LEASE_SECONDS, JOB_HEARTBEAT_SECONDS, JOB_MAX_ATTEMPTS, INVENTORY_CHECKPOINT_EVERY_PAGES | defaults in `config.py` | same |
| GOLDEN_MANIFEST_PATH | tests/golden/manifest.json | /app/tests/golden/manifest.json |

## Standing up the dev project

Status: **not yet applied.**  Terraform is written and `terraform validate`s with providers
`google 6.30.0`, `google-beta 6.30.0`, `random 3.6.3`; no plan or apply has been run against
the project, because the session that wrote it has no Google credentials.

On the VM, as a user (or the `agent-builder` SA) with the roles listed above:

```bash
git clone https://github.com/Ergplan/tariff-oder && cd tariff-oder
git checkout claude/keen-tesla-r9mvv5
scripts/verify-gcp-setup.sh                      # fix every MISSING item first

# 1. Terraform state bucket versioning (confirm; the script reports it)
gcloud storage buckets update gs://tarifforderstudio_tfstate --versioning

# 2. Optional but recommended: put the billing account id in envs/dev.tfvars so the budget
#    is created (the verify script prints the id in the right format).

# 3. Plan and apply
make tf-init ENV=dev
make tf-plan ENV=dev                             # review every resource before applying
make tf-apply ENV=dev
```

The first apply creates: VPC + private services access, Cloud SQL PostgreSQL 16 (private IP),
the artefacts/exports/backups buckets, Secret Manager entries, Artifact Registry, four service
accounts with least-privilege bindings, the Cloud Run API and web services, the worker and
migrate jobs, Cloud Scheduler, logging metrics and alerts.  It creates **no** load balancer,
**no** IAP and **no** public endpoint while `domain = ""`.

Then deploy and migrate:

```bash
make deploy-dev            # builds amd64 images, pushes, runs tariff-migrate, updates services
gcloud run jobs execute tariff-migrate --project tariff-order-parsing --region asia-south1 --wait
```

### Loading the three tariff orders

The PDFs live in the bucket, not in a browser upload, so registration is a two-step operation:

```bash
gcloud storage cp NPCL_TariffOrder1-pdf72202631759PM.pdf \
                  96731743148968.pdf \
                  Gujaratdocument.pdf \
                  gs://tarifforderstudio_sources/inbox/
```

Then, as an administrator against the API:

```
GET  /sources/inbox                 # what is in the bucket and what is already registered
POST /sources/ingest {"object_key": "inbox/NPCL_TariffOrder1-pdf72202631759PM.pdf"}
```

The API re-reads and hashes the bytes — the object's name and metadata are never trusted as
identity — deduplicates on SHA-256, reconciles against `tests/golden/manifest.json` (recording
expected vs observed page count, size and text-layer counts as `manifest_check`, never
overwriting either), and queues the inventory job.  Until a domain exists the API is
VPC-internal, so drive it from inside the VPC (the build VM with a proxy, or a short-lived
Cloud Run Job) rather than from your laptop.

### Registering the first user

An IAP-authenticated user with no row in `users` receives `permission_denied` by design.  Seed
the registry and the first administrator with the migrate image:

```bash
gcloud run jobs execute tariff-migrate --project tariff-order-parsing --region asia-south1 --wait
# then, from a shell with database access:
tariff-api seed          # jurisdictions, commissions, utilities — identities only, no coverage
```

and insert the administrator row (`PUT /users` once the API is reachable, or via `psql`).

### When a domain becomes available

1. Set `domain = "<host>"` in `envs/dev.tfvars`; `make tf-plan tf-apply ENV=dev`.
2. Point the DNS A record at `terraform output load_balancer_ip`; wait for the managed
   certificate to become ACTIVE.
3. `terraform output iap_audiences` → paste into `iap_audiences` → plan and apply again (the
   audiences only exist after the backend services do).
4. Re-check that the web service can call the API: `apps/web/lib/api.ts` forwards the IAP
   assertion but does not yet attach a Cloud Run identity token.  With the API restricted to
   the load balancer, either route web → API through the load balancer's `/api/*` path or add
   an `Authorization: Bearer <id token>` header minted from the web service account.  **Untested
   — verify before relying on it.**

If the front end goes to Firebase Hosting instead, note that Firebase Hosting does not front
IAP; the authentication path would have to be decided first (ADR-0008).

## Backups and restore

- Automated: daily Cloud SQL backups (20:00 UTC) + point-in-time recovery; object versioning on
  the created `backups` bucket (and on `sources`, once confirmed — the verify script checks it).
- On demand: `make backup-dev` (`scripts/backup-gcp.sh`) — Cloud SQL backup plus an rsync of the
  sources bucket into the backups bucket under a UTC timestamp prefix.
- Restore drill (documented now, automated in Milestone 8): restore into a scratch instance
  (`gcloud sql backups restore <id> --restore-instance=<scratch>`), copy the bucket prefix into
  a scratch bucket, point a scratch API at both, and compare `source_documents.sha256`, the page
  rows and `audit_events` byte-for-byte with the source.

## Promotion checklist (Section 3.3)

1. Full evaluation corpus run in `dev` on the release digests with per-stage metrics.
2. Migrations replay from empty (`tests/integration/test_migrations.py`) and apply cleanly to a
   copy of the production backup.
3. Backup restores into scratch Cloud SQL + bucket; published facts, evidence spans and audit
   history round-trip byte-identical for decimals and text.
4. Integration and browser tests pass against the target project before traffic shifts.
5. Provider cost and latency budgets re-measured; alerts and budgets exist in the target project.
6. Rollback = redeploy previous image digests + a tested data rollback plan for any irreversible
   migration.

Production follows ADR-0006 as written (regional source bucket, IAP, REGIONAL Cloud SQL), not
the dev deviations in ADR-0008.  Nothing is applied to `prod` without explicit authorisation
(`make tf-apply ENV=prod AUTHORISED=yes`).
