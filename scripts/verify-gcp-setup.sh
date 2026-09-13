#!/usr/bin/env bash
# Verify the Google Cloud prerequisites for the dev environment and report what is missing.
#
#   scripts/verify-gcp-setup.sh [project_id] [region]
#
# Read-only: it enables nothing, creates nothing and changes nothing.  Every check prints
# OK / MISSING / DEVIATION with the exact command to fix it.  Run it on the VM (or anywhere
# with gcloud authenticated for the project).  Exit code 1 if any required item is missing.
set -uo pipefail

PROJECT=${1:-tariff-order-parsing}
REGION=${2:-asia-south1}
SOURCES_BUCKET=${SOURCES_BUCKET:-tarifforderstudio_sources}
TFSTATE_BUCKET=${TFSTATE_BUCKET:-tarifforderstudio_tfstate}
SA=${SA:-agent-builder@${PROJECT}.iam.gserviceaccount.com}

fail=0
ok()        { printf '  \033[32mOK\033[0m        %s\n' "$*"; }
missing()   { printf '  \033[31mMISSING\033[0m   %s\n' "$*"; fail=1; }
deviation() { printf '  \033[33mDEVIATION\033[0m %s\n' "$*"; }
info()      { printf '  \033[36mINFO\033[0m      %s\n' "$*"; }
fixcmd()    { printf '            fix: %s\n' "$*"; }
section()   { printf '\n\033[1m%s\033[0m\n' "$*"; }

command -v gcloud >/dev/null || { echo "gcloud is not installed; run this on the VM"; exit 2; }

section "Project"
if gcloud projects describe "$PROJECT" --format='value(projectId)' >/dev/null 2>&1; then
  NUM=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
  ok "project $PROJECT exists (number $NUM)"
else
  missing "project $PROJECT not accessible with the current credentials"
  exit 1
fi
ACCOUNT=$(gcloud config get-value account 2>/dev/null)
info "authenticated as ${ACCOUNT:-unknown}"

section "Billing and budget"
BILLING=$(gcloud beta billing projects describe "$PROJECT" --format='value(billingAccountName)' 2>/dev/null)
if [ -n "$BILLING" ]; then
  ok "billing enabled (${BILLING})"
  BA=${BILLING#billingAccounts/}
  BUDGETS=$(gcloud billing budgets list --billing-account="$BA" --format='value(displayName)' 2>/dev/null)
  if [ -n "$BUDGETS" ]; then
    ok "budget(s) on the billing account: $(echo "$BUDGETS" | tr '\n' ' ')"
  else
    missing "no budget found on billing account $BA"
    fixcmd "set billing_account_id = \"$BA\" in infra/gcp/envs/dev.tfvars and re-apply Terraform"
  fi
  info "billing_account_id for dev.tfvars: $BA"
else
  missing "billing account not linked (or the billing API is not enabled for your account)"
fi

section "Enabled APIs"
REQUIRED_APIS="run.googleapis.com sqladmin.googleapis.com storage.googleapis.com \
secretmanager.googleapis.com artifactregistry.googleapis.com compute.googleapis.com \
servicenetworking.googleapis.com iap.googleapis.com cloudscheduler.googleapis.com \
logging.googleapis.com monitoring.googleapis.com billingbudgets.googleapis.com \
cloudresourcemanager.googleapis.com iam.googleapis.com cloudbuild.googleapis.com"
ENABLED=$(gcloud services list --enabled --project "$PROJECT" --format='value(config.name)' 2>/dev/null)
for api in $REQUIRED_APIS; do
  if grep -qx "$api" <<<"$ENABLED"; then ok "$api"; else
    missing "$api not enabled"
    fixcmd "gcloud services enable $api --project $PROJECT"
  fi
done

section "Buckets"
check_bucket() {
  local b=$1 want_versioning=$2 role=$3
  local json
  json=$(gcloud storage buckets describe "gs://$b" --project "$PROJECT" \
          --format='value(location,locationType,uniform_bucket_level_access.enabled,versioning.enabled,public_access_prevention)' 2>/dev/null)
  if [ -z "$json" ]; then
    missing "gs://$b ($role) not found or not readable"
    return
  fi
  read -r loc loctype ubla ver pap <<<"$json"
  ok "gs://$b exists — $role"
  info "location=$loc ($loctype) uniform_access=$ubla versioning=$ver public_access_prevention=$pap"
  if [ "${loctype,,}" != "region" ] || [ "${loc,,}" != "${REGION,,}" ]; then
    deviation "gs://$b is $loc/$loctype, not regional $REGION — accepted for sources (ADR-0008); cross-region reads cost egress"
  fi
  if [ "${ubla,,}" != "true" ]; then
    missing "gs://$b does not enforce uniform bucket-level access"
    fixcmd "gcloud storage buckets update gs://$b --uniform-bucket-level-access"
  fi
  if [ "$want_versioning" = "yes" ] && [ "${ver,,}" != "true" ]; then
    missing "gs://$b has versioning OFF"
    fixcmd "gcloud storage buckets update gs://$b --versioning"
  fi
  if [ "${pap,,}" != "enforced" ] && [ "${pap,,}" != "inherited" ]; then
    deviation "gs://$b public access prevention: $pap"
  fi
}
check_bucket "$SOURCES_BUCKET" yes "tariff PDFs (adopted by Terraform as the source store)"
check_bucket "$TFSTATE_BUCKET" yes "Terraform remote state"

section "Source PDFs in gs://$SOURCES_BUCKET"
OBJECTS=$(gcloud storage ls -r "gs://$SOURCES_BUCKET/**" 2>/dev/null | grep -i '\.pdf$')
if [ -z "$OBJECTS" ]; then
  missing "no PDF objects found — upload the three tariff orders"
  fixcmd "gcloud storage cp NPCL_TariffOrder1-pdf72202631759PM.pdf 96731743148968.pdf Gujaratdocument.pdf gs://$SOURCES_BUCKET/inbox/"
else
  echo "$OBJECTS" | while read -r o; do info "$o"; done
  echo
  info "expected SHA-256 (from tests/golden/manifest.json — verified, never assumed, at registration):"
  info "  NPCL  ff36813e2671e0498b78784afec73f548626d9779af8d1c1bb79585a4e174b1a  6,314,646 B  423 pages"
  info "  KERC  d84997a4f7195b5c4ebb94064bd15428d2e8657c4f53e1671a074200595fcf50 21,755,322 B  570 pages"
  info "  GERC  1c4697f8b315d64a2f161e2a26cafc5ad2ccc5cb62799161fcfb529695925e1a  2,803,465 B  184 pages"
  info "check locally with: gcloud storage hash --hex gs://$SOURCES_BUCKET/<object>"
fi

section "Service account $SA"
if gcloud iam service-accounts describe "$SA" --project "$PROJECT" >/dev/null 2>&1; then
  ok "service account exists"
  ROLES=$(gcloud projects get-iam-policy "$PROJECT" --flatten='bindings[].members' \
           --filter="bindings.members:serviceAccount:$SA" --format='value(bindings.role)' 2>/dev/null | sort)
  echo "$ROLES" | while read -r r; do [ -n "$r" ] && info "$r"; done
  if grep -qx "roles/editor" <<<"$ROLES"; then
    deviation "holds roles/editor — broad for a build identity; after the first apply, drop it in favour of the specific admin roles it already has"
  fi
  if grep -q "resourcemanager.projectIamAdmin\|roles/owner" <<<"$ROLES"; then
    info "can grant IAM — required for Terraform to create the per-service accounts"
  fi
else
  missing "service account $SA not found"
fi

section "Region check"
info "intended region for Cloud Run, Cloud SQL and Artifact Registry: $REGION"
ZONE=$(gcloud compute instances list --project "$PROJECT" --filter='name~tariff' --format='value(name,zone)' 2>/dev/null)
[ -n "$ZONE" ] && echo "$ZONE" | while read -r n z; do info "VM $n is in zone $z"; done
info "the VM's zone does not constrain the app; Terraform pins Cloud Run and Cloud SQL to $REGION"

section "Terraform state"
if [ -f infra/gcp/envs/dev.backend.hcl ]; then ok "infra/gcp/envs/dev.backend.hcl present"; else
  missing "infra/gcp/envs/dev.backend.hcl missing"
  fixcmd "cp infra/gcp/envs/dev.backend.hcl.example infra/gcp/envs/dev.backend.hcl"
fi

section "Summary"
if [ "$fail" -eq 0 ]; then
  echo "  All required items present. Next: make tf-init tf-plan ENV=dev"
else
  echo "  Fix the MISSING items above, then re-run. DEVIATION lines are accepted choices, recorded in docs/deployment.md."
fi
exit $fail
