# Development project "tariff order studio" (tariff-order-parsing).
# Nothing here is a secret.  Apply with: make tf-init tf-plan ENV=dev && make tf-apply ENV=dev
project_id  = "tariff-order-parsing"
environment = "dev"
region      = "asia-south1"

alert_email = "venture@aayuda.energy"

# Adopt the bucket that already holds the tariff PDFs instead of creating a new one (ADR-0008).
# Note: it is multi-region `asia`, not regional `asia-south1` — accepted deviation from ADR-0006,
# recorded in docs/deployment.md.  Terraform does not manage its location or versioning.
existing_source_bucket = "tarifforderstudio_sources"

# No custom domain yet: the load balancer and IAP are NOT created and Cloud Run has no public
# ingress (ADR-0008).  Set `domain` (and re-apply) when a hostname exists, then fill
# iap_audiences from `terraform output iap_audiences` and apply once more.
domain        = ""
iap_members   = ["user:venture@aayuda.energy"]
iap_audiences = []

# Budget: set billing_account_id (Billing → Account management, format 012345-678901-ABCDEF)
# to have Terraform create the 50/80/100% budget alerts.  Empty skips it.
billing_account_id = ""
budget_amount_inr  = 20000

# Images: replace the tags with digests for anything you intend to keep.
python_image = "asia-south1-docker.pkg.dev/tariff-order-parsing/tariff/python:dev"
web_image    = "asia-south1-docker.pkg.dev/tariff-order-parsing/tariff/web:dev"

db_availability_type = "ZONAL"
db_tier              = "db-custom-1-3840"
deletion_protection  = false
api_min_instances    = 0

# IAP directly on the Cloud Run web service (ADR-0015 addendum, operator-authorised
# 2026-09-14): a public URL with a Google sign-in for iap_members, no domain needed.  After
# apply, run every line of `terraform output -raw web_iap_commands`.
web_iap = true
# Real model calls for extraction and category summaries (key in Secret Manager, never in files).
provider_backend = "anthropic"
