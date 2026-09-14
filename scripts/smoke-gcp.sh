#!/usr/bin/env bash
# Post-deploy smoke test for the gcp profile.  Requires gcloud auth as an identity allowed to
# invoke the API (the build service account is).  With no domain the API's ingress is
# VPC-internal, so this must run from inside the VPC (the admin job or a VPC-attached VM);
# from elsewhere the run.app URL is refused before the container is reached.
# 1. /readyz must return 200 with status=ready; on 503 the body says which check failed.
# 2. /status with an IAP identity must report deployment_profile=gcp and the expected adapters.
set -euo pipefail
PROJECT=${1:?project id}
REGION=${2:-asia-south1}
API_URL=$(gcloud run services describe tariff-api --project "$PROJECT" --region "$REGION" --format='value(status.url)')
echo "api: $API_URL"
TOKEN=$(gcloud auth print-identity-token)
BODY=$(mktemp)
CODE=$(curl -sS -o "$BODY" -w '%{http_code}' "$API_URL/readyz" -H "Authorization: Bearer $TOKEN" || true)
echo "readyz: HTTP $CODE"
cat "$BODY"; echo
if [ "$CODE" != "200" ]; then
  echo "not ready. The body above names the failing check (database, migration_head, pgvector, storage)."
  echo "API logs: gcloud run services logs read tariff-api --project $PROJECT --region $REGION --limit 100"
  echo "If the body is empty or HTML, the request never reached the container: the API is VPC-internal and this host is outside the VPC."
  rm -f "$BODY"; exit 1
fi
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["status"]=="ready", d; print("readyz ok, migration head", d["database"].get("migration_head"))' "$BODY"
rm -f "$BODY"
echo "IAP-fronted /status must be checked through the load balancer URL with a browser or an IAP-authorised token; see docs/deployment.md"
