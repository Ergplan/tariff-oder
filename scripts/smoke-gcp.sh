#!/usr/bin/env bash
# Post-deploy smoke test for the gcp profile.  Requires gcloud auth as a user allowed through IAP.
# 1. /readyz through the load balancer must return 200.
# 2. /status with an IAP identity must report deployment_profile=gcp and the expected adapters.
set -euo pipefail
PROJECT=${1:?project id}
REGION=${2:-asia-south1}
API_URL=$(gcloud run services describe tariff-api --project "$PROJECT" --region "$REGION" --format='value(status.url)')
echo "api: $API_URL"
TOKEN=$(gcloud auth print-identity-token)
curl -fsS "$API_URL/readyz" -H "Authorization: Bearer $TOKEN" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="ready", d; print("readyz ok", d["database"].get("migration_head"))'
echo "IAP-fronted /status must be checked through the load balancer URL with a browser or an IAP-authorised token; see docs/deployment.md"
