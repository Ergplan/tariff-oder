# ADR-0008 Dev project topology: adopted source bucket, no public ingress, optional budget

Status: accepted (2026-09-13), supersedes parts of ADR-0006 for the `dev` environment

## Context

The `dev` environment is an existing Google Cloud project rather than one Terraform created:

- Project `tariff-order-parsing` ("tariff order studio"), billing linked.
- `gs://tarifforderstudio_sources` — already holds (or will hold) the tariff PDFs.
  **Multi-region `asia`**, Standard, uniform access, public access prevented.
- `gs://tarifforderstudio_tfstate` — Terraform state.
- Service account `agent-builder@tariff-order-parsing.iam.gserviceaccount.com` with Editor
  plus several admin roles, attached to a build VM (`tariff-order`, e2-standard-4).
- **No domain name** is available, and the intent is to stay on Google Cloud (possibly
  Firebase Hosting) for any public front end.

## Decisions

### 1. Adopt the existing source bucket rather than create one

`var.existing_source_bucket` makes Terraform reference `tarifforderstudio_sources` by name for
IAM and for the services' `SOURCE_BUCKET`; it does not manage the bucket's location, versioning
or lifecycle.  The artefacts, exports and backups buckets are still created in `asia-south1`.

**Accepted deviation from ADR-0006** (single Indian region): the bucket is multi-region `asia`,
which spans locations outside India.  Accepted because tariff orders are public regulatory
documents, so there is no residency obligation, and because re-creating the bucket would mean
moving data for no functional gain.  The costs are real and recorded: cross-region reads from
a worker in `asia-south1` incur egress and added latency on every page fetch, and the storage
price is higher than regional.  `scripts/verify-gcp-setup.sh` prints this as a DEVIATION on
every run so it does not become invisible.  Revisit before production: a production source
bucket should be regional `asia-south1`.

### 2. No public ingress until a domain exists

The load balancer, its managed certificate and IAP are created only when `var.domain` is set.
With `domain = ""` (the dev default):

- Cloud Run ingress is `INGRESS_TRAFFIC_INTERNAL_ONLY` — nothing is reachable from the
  internet, which is the safe default rather than a gap.
- Cloud SQL, buckets, Secret Manager, migrations, the worker job and bucket ingest all work.
  Operations run through `gcloud run jobs execute` and, for the API, from inside the VPC.
- The browser workspace is unavailable until a hostname exists.

Rejected: exposing Cloud Run publicly with Cloud Run IAM instead of IAP.  It would avoid the
domain requirement, but it means a second identity path in the backend — the boundary that
keeps unreviewed candidates out of user-facing tools (Section 8).  That is not a change to
make in passing; it needs its own ADR if the project chooses it.

Routes to a working browser front end, when wanted:
- **Custom domain** → set `domain`, apply, point DNS at `load_balancer_ip`, copy
  `terraform output iap_audiences` into `iap_audiences`, apply again.  Full IAP path, already written.
- **Firebase Hosting** → gives a free managed `*.web.app` hostname that can rewrite to Cloud
  Run, but Firebase Hosting does not front IAP.  Choosing it means deciding the authentication
  path (Firebase Auth or Cloud Run IAM) first; unimplemented, deliberately.

### 3. The budget is optional in Terraform, mandatory in practice

`billing_account_id` defaults to empty and the `google_billing_budget` resource is created only
when it is set, so the project can be stood up before the billing id is looked up.  A missing
budget is reported as MISSING by `scripts/verify-gcp-setup.sh` — "a stopped job is preferable
to an unbounded bill" (Section 3.1) is not satisfied by an unset budget.

### 4. Registration of bucket-resident PDFs is a first-class path

Because the orders arrive by `gcloud storage cp` into the source bucket rather than through a
browser, the API exposes `GET /sources/inbox` (what is in the bucket, and whether it is
registered) and `POST /sources/ingest` (register one object).  The object's name and metadata
are never trusted as identity: the bytes are re-read and hashed, and registration then follows
exactly the same path as an upload — same deduplication, same golden-manifest verification,
same inventory job.  The operator's copy stays where they put it; the registered copy is
written under its content-addressed key.

## Consequences

- `make tf-plan ENV=dev` works today with no billing id and no domain.
- The `agent-builder` service account holds `roles/editor`, which is broader than a build
  identity needs.  It is flagged as a DEVIATION by the verify script; once the first apply has
  created the per-service accounts, Editor should be removed in favour of the specific admin
  roles it already holds.  The guardrail that it is scoped to this project only stands.
- Nothing in this ADR applies to a future production project, which follows ADR-0006 as written.
