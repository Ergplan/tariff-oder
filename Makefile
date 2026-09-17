# Tariff Order Intelligence - developer and deployment entrypoints.
# Two profiles: `local` (this file's dev/test targets) and `gcp` (deploy-* targets).

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE := docker compose -f infra/local/docker-compose.yml
TEST_DB ?= postgresql+psycopg://postgres@127.0.0.1:5433/tariff_test
ENV ?= dev
TF_DIR := infra/gcp
REGION ?= asia-south1

help: ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# ---------------------------------------------------------------- local profile
install: ## Install Python (uv) and Node (pnpm) dependencies
	uv sync --all-packages
	pnpm install --frozen-lockfile

dev: ## Start postgres, api, worker, web in containers (local profile)
	$(COMPOSE) up --build

dev-down: ## Stop the local stack (keeps volumes)
	$(COMPOSE) down

dev-reset: ## Stop the local stack and delete volumes
	$(COMPOSE) down -v

migrate: ## Apply migrations to $$DATABASE_URL
	uv run tariff-api migrate

seed: ## Seed jurisdictions/commissions/utilities (identities only)
	uv run tariff-api seed

api: ## Run the API without containers (needs DATABASE_URL, LOCAL_USER_ALLOWLIST)
	uv run uvicorn tariff_api.asgi:app --host 127.0.0.1 --port 8000 --reload

worker: ## Run the worker without containers
	uv run tariff-worker

web: ## Run the web app in dev mode (needs API_BASE_URL, LOCAL_WEB_USER)
	pnpm --filter @tariff/web dev

ephemeral-postgres: ## Start a throwaway PostgreSQL 16 + pgvector on :5433 (no Docker needed)
	scripts/ephemeral-postgres.sh start

test: ## Run unit + integration tests against TEST_DB
	TARIFF_TEST_DATABASE_URL=$(TEST_DB) uv run pytest -q

lint: ## Ruff + TypeScript checks
	uv run ruff check services tests
	uv run ruff format --check services tests
	pnpm --filter @tariff/web typecheck

contracts: ## Regenerate OpenAPI document and TypeScript types from the API
	DEPLOYMENT_PROFILE=local LOCAL_USER_ALLOWLIST=contracts@example.com:analyst uv run tariff-api openapi -o packages/contracts/openapi.json
	pnpm --filter @tariff/contracts generate

contracts-check: ## Fail if committed contracts drift from the API
	pnpm --filter @tariff/contracts check

build-web: ## Production build of the web app
	pnpm --filter @tariff/web build

fixtures: ## Write synthetic PDFs to tests/fixtures/generated (labelled, git-ignored)
	uv run python tests/fixtures/synthetic_pdfs.py tests/fixtures/generated

# ---------------------------------------------------------------- gcp profile
# Before the first apply there is no Terraform output yet; fall back to the tfvars value.
GCP_PROJECT ?= $(shell cd $(TF_DIR) && terraform output -raw project_id 2>/dev/null || sed -n 's/^project_id *= *"\(.*\)"/\1/p' envs/$(ENV).tfvars)
AR_REPO = $(REGION)-docker.pkg.dev/$(GCP_PROJECT)/tariff
GIT_SHA := $(shell git rev-parse --short HEAD 2>/dev/null || echo dev)

tf-init: ## terraform init for infra/gcp (remote state bucket from envs/$(ENV).backend.hcl); idempotent, also installs providers added since the last init
	cd $(TF_DIR) && terraform init -input=false -backend-config=envs/$(ENV).backend.hcl

tf-plan: tf-init ## terraform plan for ENV (default dev); writes $(ENV).tfplan
	cd $(TF_DIR) && terraform plan -var-file=envs/$(ENV).tfvars -out=$(ENV).tfplan

tf-apply: ## terraform apply the saved plan. Only `dev` without explicit authorisation.
	@if [ "$(ENV)" != "dev" ] && [ "$(AUTHORISED)" != "yes" ]; then echo "Refusing to apply to $(ENV) without AUTHORISED=yes"; exit 2; fi
	cd $(TF_DIR) && terraform apply $(ENV).tfplan

build-images: ## Build amd64 images for api/worker and web
	docker build --platform linux/amd64 -f infra/local/Dockerfile.python -t $(AR_REPO)/python:$(GIT_SHA) .
	docker build --platform linux/amd64 -f infra/local/Dockerfile.web -t $(AR_REPO)/web:$(GIT_SHA) .

push-images: ## Push images to Artifact Registry (release tag = git sha, plus the moving `$(ENV)` tag Terraform bootstraps from)
	gcloud auth configure-docker $(REGION)-docker.pkg.dev --quiet
	docker tag $(AR_REPO)/python:$(GIT_SHA) $(AR_REPO)/python:$(ENV)
	docker tag $(AR_REPO)/web:$(GIT_SHA) $(AR_REPO)/web:$(ENV)
	docker push $(AR_REPO)/python:$(GIT_SHA)
	docker push $(AR_REPO)/web:$(GIT_SHA)
	docker push $(AR_REPO)/python:$(ENV)
	docker push $(AR_REPO)/web:$(ENV)

bootstrap-dev: ## First-time only: create the APIs + Artifact Registry, then build and push images so the full apply can create Cloud Run
	@command -v gcloud >/dev/null || { echo "gcloud is not installed; see docs/deployment.md"; exit 2; }
	@command -v docker >/dev/null || { echo "docker is not installed; see docs/deployment.md"; exit 2; }
	$(MAKE) tf-init ENV=dev
	cd $(TF_DIR) && terraform apply -var-file=envs/dev.tfvars -target=google_project_service.apis -target=google_artifact_registry_repository.docker
	$(MAKE) build-images push-images ENV=dev
	@echo "Images pushed as python:dev and web:dev. Now run: make tf-plan tf-apply ENV=dev"

deploy-dev: ## Build, push, migrate and deploy to the dev project (same images as local)
	@command -v gcloud >/dev/null || { echo "gcloud is not installed; see docs/deployment.md"; exit 2; }
	@test -n "$(GCP_PROJECT)" || { echo "No dev project: run make tf-init tf-plan tf-apply ENV=dev first"; exit 2; }
	@gcloud run jobs describe tariff-migrate --project $(GCP_PROJECT) --region $(REGION) --format='value(name)' >/dev/null 2>&1 || { \
	  echo "Cloud Run job tariff-migrate does not exist in $(GCP_PROJECT): the Terraform apply has not completed."; \
	  echo "Run: make tf-plan ENV=dev   (the plan lists what is still to be created)   then: make tf-apply ENV=dev"; exit 2; }
	$(MAKE) build-images push-images
	gcloud run jobs update tariff-migrate --project $(GCP_PROJECT) --region $(REGION) --image $(AR_REPO)/python:$(GIT_SHA) --quiet
	gcloud run jobs execute tariff-migrate --project $(GCP_PROJECT) --region $(REGION) --wait
	gcloud run services update tariff-api --project $(GCP_PROJECT) --region $(REGION) --image $(AR_REPO)/python:$(GIT_SHA) --quiet
	gcloud run jobs update tariff-worker --project $(GCP_PROJECT) --region $(REGION) --image $(AR_REPO)/python:$(GIT_SHA) --quiet
	gcloud run jobs update tariff-admin --project $(GCP_PROJECT) --region $(REGION) --image $(AR_REPO)/python:$(GIT_SHA) --quiet
	gcloud run services update tariff-web --project $(GCP_PROJECT) --region $(REGION) --image $(AR_REPO)/web:$(GIT_SHA) --quiet
	@if grep -Eq '^web_iap *= *true' $(TF_DIR)/envs/$(ENV).tfvars; then \
	  gcloud beta run services update tariff-web --project $(GCP_PROJECT) --region $(REGION) --iap --quiet; fi
	@echo "Deployed $(GIT_SHA) to $(GCP_PROJECT). Run: make smoke-dev"

smoke-dev: ## Post-deploy checks against the dev project (readiness + authenticated status)
	scripts/smoke-gcp.sh $(GCP_PROJECT) $(REGION)

proxy-dev: ## Proxy the VPC-internal web service to localhost:3000 with the active gcloud identity (run on the VM, tunnel over SSH)
	python3 scripts/run-proxy.py --service tariff-web --project $(GCP_PROJECT) --region $(REGION) --port 3000

admin-dev: ## Run the tariff-api CLI inside the VPC: make admin-dev ARGS=inbox  (comma-separated, e.g. ARGS=users,add,--email,x@y,--role,administrator,--actor,x@y)
	@test -n "$(ARGS)" || { echo "usage: make admin-dev ARGS=<comma-separated tariff-api arguments>"; exit 2; }
	gcloud run jobs update tariff-admin --project $(GCP_PROJECT) --region $(REGION) --args=$(ARGS) --quiet
	@gcloud run jobs execute tariff-admin --project $(GCP_PROJECT) --region $(REGION) --wait; rc=$$?; \
	  echo "--- job output (Cloud Logging, last 3 minutes; waiting 20s for ingestion) ---"; sleep 20; \
	  gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="tariff-admin"' \
	    --project $(GCP_PROJECT) --freshness=3m --order=asc --limit 80 --format='value(textPayload,jsonPayload.message)' | grep -v '^$$'; \
	  exit $$rc

drain-dev: ## Run the worker job until the queue is empty (each run drains what is queued; stages enqueue the next)
	@for i in 1 2 3 4 5 6; do \
	  gcloud run jobs execute tariff-worker --project $(GCP_PROJECT) --region $(REGION) --wait --quiet || { \
	    echo "--- worker output (Cloud Logging, last 5 minutes; waiting 20s for ingestion) ---"; sleep 20; \
	    gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="tariff-worker"' \
	      --project $(GCP_PROJECT) --freshness=5m --order=asc --limit 120 --format='value(textPayload,jsonPayload.message)' | grep -v '^$$'; \
	    exit 1; }; \
	done
	@echo "Worker ran 6 times. Check: make admin-dev ARGS=sources"

backup-dev: ## On-demand Cloud SQL backup + bucket copy (see docs/deployment.md)
	scripts/backup-gcp.sh $(GCP_PROJECT) $(REGION)

.PHONY: help install dev dev-down dev-reset migrate seed api worker web ephemeral-postgres test lint contracts contracts-check build-web fixtures tf-init tf-plan tf-apply build-images push-images bootstrap-dev deploy-dev smoke-dev proxy-dev admin-dev drain-dev backup-dev
