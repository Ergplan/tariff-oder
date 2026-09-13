# Deployment

Two profiles, one codebase: `DEPLOYMENT_PROFILE=local` (developer machines, CI) and
`DEPLOYMENT_PROFILE=gcp` (dev → staging → prod projects).  Behaviour differs only in the
adapters listed in `docs/architecture.md`.

## Google Cloud service choices (Section 3.1)

Decisions recorded at Milestone 0.  Product documentation was **not** reachable from the build
environment (the agent proxy returns 403 for cloud.google.com), so limits below are the
provider-documented values as of the Terraform provider release pinned (`google ~> 6.30`),
and must be re-verified against current documentation before `make tf-apply` (see the
checklist at the end).

| Component | Choice | Rationale / verification needed |
| --- | --- | --- |
| Region | `asia-south1` (Mumbai) for every data-bearing service | Data residency in India, lowest latency to Indian users; `asia-south2` (Delhi) is the documented alternative — ADR-0006 |
| Web + API | Cloud Run v2 services, ingress restricted to the load balancer, request timeout 60 s | Document processing never runs in a request |
| Worker | Cloud Run **Job** (`tariff-worker --drain`) triggered every 5 min by Cloud Scheduler, 1 task, 2 vCPU / 4 GiB, 60 min timeout | Simplest durable option; Milestone 8 measures a full 570-page run and decides between Job, worker-pool service and GKE (ADR to follow) |
| Queue | PostgreSQL table in Cloud SQL (`SELECT … FOR UPDATE SKIP LOCKED`) | ADR-0003; Pub/Sub or Cloud Tasks only via an ADR with equivalence tests |
| Database | Cloud SQL for PostgreSQL 16, private IP, automated backups + PITR (7-day logs, 14 backups), `cloudsql.iam_authentication=on`; `vector` extension created by migration 0001 | Verify pgvector availability for the chosen Cloud SQL minor version at apply time |
| Object storage | Four buckets (`sources` versioned, `artefacts`, `exports`, `backups` versioned), uniform bucket-level access, public access prevention enforced | Keys are content hashes; CMEK not enabled (add if required) |
| Secrets | Secret Manager, ids equal env-var names; `DATABASE_URL` managed by Terraform, provider keys created empty | No secret in images, git, or logs |
| Identity | Global external HTTPS LB + IAP on both backend services; roles enforced in the API from the `users` table | IAP audiences are known only after the first apply (two-phase, below) |
| Images | Artifact Registry `asia-south1-docker.pkg.dev/<project>/tariff/{python,web}`; amd64; digests pinned per release in tfvars | Multi-arch only if Apple-silicon developers need it |
| Observability | Cloud Logging (JSON stdout with `severity`), 5xx alert policy, failed-job log metric + alert, email notification channel | Dashboards are Milestone 8 |
| Cost | Billing budget (INR, 50/80/100% thresholds), job concurrency 1, application-level page/size limits | Provider-token budgets arrive in Milestone 4 |
| Environments | One project per environment from the same Terraform (`envs/dev.tfvars`, `envs/prod.tfvars`); remote state in a versioned GCS bucket per environment | Promotion = same digests + migrations, never a rebuild |

## Local profile

`make dev` (Docker): `infra/local/docker-compose.yml` starts `postgres` (pgvector/pgvector:pg16),
`migrate`, `api`, `worker`, `web`; MinIO is available under the `minio` compose profile but
the default local object store is the filesystem (ADR-0004).

Without Docker: `make ephemeral-postgres` (needs `postgresql-16` + `postgresql-16-pgvector`),
then `make migrate seed api worker web` with the env vars in `README.md`.

Environment variables (both profiles use the same names):

| Variable | local | gcp |
| --- | --- | --- |
| DEPLOYMENT_PROFILE | local | gcp |
| DATABASE_URL | postgres container / :5433 | Secret Manager |
| OBJECT_STORE_BACKEND / OBJECT_STORE_ROOT | filesystem / path | gcs (+ SOURCE_BUCKET, ARTEFACT_BUCKET, EXPORT_BUCKET) |
| SECRETS_BACKEND | env | secret_manager (+ GCP_PROJECT_ID) |
| IDENTITY_BACKEND | local (+ LOCAL_USER_ALLOWLIST `email:role,…`) | iap (+ IAP_AUDIENCE comma-separated) |
| LOG_FORMAT | json or text | json |
| MAX_UPLOAD_BYTES, MAX_PAGES_PER_JOB, JOB_LEASE_SECONDS, JOB_HEARTBEAT_SECONDS, JOB_MAX_ATTEMPTS, INVENTORY_CHECKPOINT_EVERY_PAGES | defaults in `config.py` | same |
| GOLDEN_MANIFEST_PATH | tests/golden/manifest.json | /app/tests/golden/manifest.json |

## Cloud path (`make deploy-dev`) — prepared, NOT executed

Status: **blocked**.  The build environment has no `gcloud`, no usable Google credentials
(`CLOUDSDK_AUTH_ACCESS_TOKEN` is a proxy placeholder rejected by Google APIs), and no
project.  Terraform was formatted and `terraform validate`d with providers `google 6.30.0`,
`google-beta 6.30.0`, `random 3.6.3`; no plan or apply was run.

Steps for the operator (`venture@aayuda.energy`):

1. Create the dev project, enable billing, note the billing account id.
2. Create the state bucket: `gcloud storage buckets create gs://<project>-tariff-tfstate --location=asia-south1 --uniform-bucket-level-access && gcloud storage buckets update gs://<project>-tariff-tfstate --versioning`; copy `infra/gcp/envs/dev.backend.hcl.example` to `dev.backend.hcl`.
3. Fill `infra/gcp/envs/dev.tfvars` (`project_id`, `billing_account_id`, `domain`, `iap_members`, image tags).
4. `make tf-init tf-plan ENV=dev` → review the plan → `make tf-apply ENV=dev`.
   First apply creates everything except working IAP audiences; the API refuses IAP
   verification until `IAP_AUDIENCE` is set.
5. `terraform output iap_audiences` → paste into `iap_audiences` in `dev.tfvars` → plan/apply again.
6. Point DNS for `domain` at `terraform output load_balancer_ip`; wait for the managed certificate.
7. Populate provider secrets when available: `gcloud secrets versions add ANTHROPIC_API_KEY --data-file=-`.
8. `make deploy-dev` builds amd64 images, pushes them, runs the `tariff-migrate` job, updates
   `tariff-api`, `tariff-worker`, `tariff-web`.  Then `make smoke-dev` and the browser check
   through IAP.
9. Register the first user with the administrator role: `PUT /users` through the API (an IAP
   authenticated but unregistered user gets `permission_denied`), or insert via `psql` on the
   private IP from a bastion / Cloud SQL Studio.

Known items to verify on the first real deployment (cannot be tested without a project):
- Web → API service-to-service call: `apps/web/lib/api.ts` forwards the IAP assertion but does
  not yet attach a Cloud Run identity token; with API ingress set to the load balancer only,
  the web service needs Direct VPC egress plus an `Authorization: Bearer <id token>` header
  (audience = API URL) minted from the web service account.  Add both before the first deploy
  or route web → API through the load balancer's `/api/*` path.
- Cloud SQL `POSTGRES_16` + pgvector extension availability in `asia-south1`.
- Cloud Run Job scheduler quota (`*/5 * * * *`) and the 60-minute job timeout for large orders.

## Backups and restore (Milestone 1 basic path)

- Automated: daily Cloud SQL backups (20:00 UTC) + point-in-time recovery; object versioning
  on `sources` and `backups`.
- On demand: `make backup-dev` (`scripts/backup-gcp.sh`) creates a Cloud SQL backup and
  rsyncs the sources bucket into the backups bucket under a UTC timestamp prefix.
- Restore drill (documented, automated in Milestone 8): restore the backup into a scratch
  instance (`gcloud sql backups restore <id> --restore-instance=<scratch>`), copy the bucket
  prefix into a scratch bucket, point a scratch API at both, and compare
  `source_documents.sha256`, page rows and `audit_events` byte-for-byte with the source.

## Promotion checklist (Section 3.3)

1. Full evaluation corpus run in `dev` on the release digests with per-stage metrics.
2. Migrations replay from empty (`tests/integration/test_migrations.py`) and apply cleanly to a copy of the production backup.
3. Backup from the source environment restores into scratch Cloud SQL + bucket; published facts, evidence spans and audit history round-trip byte-identical.
4. Integration and browser tests pass against the target project before traffic shift.
5. Provider cost/latency budgets re-measured; alerts and budgets exist in the target project.
6. Rollback = redeploy previous digests + tested data rollback plan for irreversible migrations.

Nothing is applied to `prod` without explicit authorisation (`make tf-apply ENV=prod AUTHORISED=yes`).
