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
unverified=0
ok()        { printf '  \033[32mOK\033[0m        %s\n' "$*"; }
unknown()   { printf '  \033[35mUNKNOWN\033[0m   %s\n' "$*"; unverified=1; }
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
BILLING_OUT=$(gcloud beta billing projects describe "$PROJECT" --format='value(billingAccountName)' 2>&1)
BILLING_RC=$?
if [ $BILLING_RC -eq 0 ] && [ -n "$BILLING_OUT" ]; then
  ok "billing enabled (${BILLING_OUT})"
  BA=${BILLING_OUT#billingAccounts/}
  info "billing_account_id for dev.tfvars: $BA"
  BUDGETS=$(gcloud billing budgets list --billing-account="$BA" --format='value(displayName)' 2>&1)
  if [ $? -eq 0 ] && [ -n "$BUDGETS" ]; then
    ok "budget(s) on the billing account: $(echo "$BUDGETS" | tr '\n' ' ')"
  elif [ $? -eq 0 ]; then
    missing "no budget on billing account $BA"
    fixcmd "set billing_account_id = \"$BA\" in infra/gcp/envs/dev.tfvars and apply Terraform"
  else
    unknown "cannot list budgets: $(echo "$BUDGETS" | tail -1)"
  fi
elif grep -qiE "permission|denied|forbidden|not have" <<<"$BILLING_OUT"; then
  # Editor on the project does not grant any billing permission: billing lives on the billing
  # account, not the project.  This says nothing about whether billing is actually linked.
  unknown "cannot read billing from this identity — this does NOT mean billing is unlinked"
  fixcmd "grant the caller roles/billing.viewer on the billing account, or read the id from"
  fixcmd "  console.cloud.google.com/billing → Account management, and paste it into envs/dev.tfvars"
  info "gcloud said: $(echo "$BILLING_OUT" | tail -1)"
else
  unknown "billing state could not be determined: $(echo "$BILLING_OUT" | tail -1)"
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
# gcloud's `value(...)` projection drops empty fields, and `read` collapses consecutive tabs,
# which silently shifts every column.  Parse JSON instead, and accept either the `gcloud
# storage` (snake_case) or the JSON-API (nested) spelling of each field.
bucket_facts() {
  gcloud storage buckets describe "gs://$1" --project "$PROJECT" --format=json 2>/dev/null | python3 -c '
import json, sys

raw = sys.stdin.read().strip()
if not raw:
    print("ERROR"); sys.exit(0)
b = json.loads(raw)
if isinstance(b, list):
    b = b[0] if b else {}
iam = b.get("iam_configuration") or b.get("iamConfiguration") or {}

def pick(*paths, default=None):
    for path in paths:
        cur, ok = b, True
        for key in path.split("."):
            src = iam if cur is b and key in iam and key not in b else cur
            if isinstance(src, dict) and key in src:
                cur = src[key]
            else:
                ok = False
                break
        if ok and cur is not None:
            return cur
    return default

ubla = pick("uniform_bucket_level_access", "uniformBucketLevelAccess.enabled",
            "uniform_bucket_level_access.enabled", default=None)
if isinstance(ubla, dict):
    ubla = ubla.get("enabled")
ver = pick("versioning_enabled", "versioning.enabled", "versioningEnabled", default=None)
pap = pick("public_access_prevention", "publicAccessPrevention", default=None)

print("\t".join([
    str(b.get("location", "?")),
    str(b.get("location_type") or b.get("locationType") or "?"),
    {True: "true", False: "false", None: "unknown"}.get(ubla, str(ubla)),
    {True: "true", False: "false", None: "off"}.get(ver, str(ver)),
    str(pap if pap is not None else "unknown"),
]))
'
}

check_bucket() {
  local b=$1 want_versioning=$2 role=$3 strict_public=${4:-no}
  local facts loc loctype ubla ver pap
  facts=$(bucket_facts "$b")
  if [ -z "$facts" ] || [ "$facts" = "ERROR" ]; then
    missing "gs://$b ($role) not found or not readable"
    return
  fi
  IFS=$'\t' read -r loc loctype ubla ver pap <<<"$facts"
  ok "gs://$b exists — $role"
  info "location=$loc ($loctype) uniform_access=$ubla versioning=$ver public_access_prevention=$pap"

  if [ "${loctype,,}" != "region" ] || [ "${loc,,}" != "${REGION,,}" ]; then
    deviation "gs://$b is $loc/$loctype, not regional $REGION — accepted for sources (ADR-0008); cross-region reads cost egress"
  fi
  case "${ubla,,}" in
    true)    ok "gs://$b enforces uniform bucket-level access" ;;
    unknown) unknown "gs://$b uniform bucket-level access could not be read" ;;
    *)       missing "gs://$b does not enforce uniform bucket-level access"
             fixcmd "gcloud storage buckets update gs://$b --uniform-bucket-level-access" ;;
  esac
  if [ "$want_versioning" = "yes" ]; then
    case "${ver,,}" in
      true)    ok "gs://$b has object versioning on" ;;
      unknown) unknown "gs://$b versioning could not be read" ;;
      *)       missing "gs://$b has versioning OFF"
               fixcmd "gcloud storage buckets update gs://$b --versioning" ;;
    esac
  fi
  if [ "$strict_public" = "yes" ]; then
    # Terraform state holds the Cloud SQL password in plaintext, so "inherited" is not enough:
    # it leaves the bucket one org-policy change away from being publicly readable.
    case "${pap,,}" in
      enforced) ok "gs://$b enforces public access prevention" ;;
      unknown)  unknown "gs://$b public access prevention could not be read — check it by hand; this bucket holds secrets" ;;
      *)        missing "gs://$b does not ENFORCE public access prevention, and it holds secrets"
                fixcmd "gcloud storage buckets update gs://$b --public-access-prevention" ;;
    esac
  elif [ "${pap,,}" = "unknown" ]; then
    unknown "gs://$b public access prevention could not be read"
  elif [ "${pap,,}" != "enforced" ] && [ "${pap,,}" != "inherited" ]; then
    deviation "gs://$b public access prevention: $pap"
  fi
}
check_bucket "$SOURCES_BUCKET" yes "tariff PDFs (adopted by Terraform as the source store)"
check_bucket "$TFSTATE_BUCKET" yes "Terraform remote state (contains the Cloud SQL password)" yes

section "Who can read the Terraform state"
gcloud storage buckets get-iam-policy "gs://$TFSTATE_BUCKET" --format=json 2>/dev/null | python3 -c '
import json, sys
raw = sys.stdin.read().strip()
if not raw:
    print("UNREADABLE"); sys.exit(0)
pol = json.loads(raw)
for binding in pol.get("bindings", []):
    for member in binding.get("members", []):
        print(f"{member}\t{binding.get(\"role\", \"?\")}")
' | sort -u | while IFS=$'\t' read -r member role; do
  case "$member" in
    UNREADABLE) info "bucket IAM policy not readable (needs storage.buckets.getIamPolicy)" ;;
    allUsers|allAuthenticatedUsers)
      printf '  \033[31mMISSING\033[0m   %s holds %s on the state bucket — remove now\n' "$member" "$role" ;;
    projectEditor:*|projectOwner:*)
      deviation "$member holds $role — anyone with project Editor/Owner can read the Cloud SQL password in state" ;;
    *) info "$member — $role" ;;
  esac
done

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
if [ "$fail" -ne 0 ]; then
  echo "  Fix the MISSING items above, then re-run."
fi
if [ "$unverified" -ne 0 ]; then
  echo "  UNKNOWN items could not be checked from this identity — verify them by hand rather than"
  echo "  assuming they are fine. An unverified budget is an unbounded bill."
fi
if [ "$fail" -eq 0 ] && [ "$unverified" -eq 0 ]; then
  echo "  All required items present. Next: make tf-init tf-plan ENV=dev"
fi
echo "  DEVIATION lines are accepted choices, recorded in docs/deployment.md and ADR-0008."
exit $fail
