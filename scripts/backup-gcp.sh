#!/usr/bin/env bash
# Basic backup path (Milestone 1): on-demand Cloud SQL backup + copy of the sources bucket to
# the backup bucket.  Restore drill (into a scratch instance and bucket) is documented in
# docs/deployment.md and automated in Milestone 8.
set -euo pipefail
PROJECT=${1:?project id}
REGION=${2:-asia-south1}
INSTANCE=$(gcloud sql instances list --project "$PROJECT" --format='value(name)' --filter='name~tariff')
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
echo "creating on-demand backup of $INSTANCE"
gcloud sql backups create --instance "$INSTANCE" --project "$PROJECT" --description "manual-$STAMP"
SRC=$(gcloud storage buckets list --project "$PROJECT" --format='value(name)' --filter='name~sources')
DST=$(gcloud storage buckets list --project "$PROJECT" --format='value(name)' --filter='name~backups')
echo "copying gs://$SRC -> gs://$DST/$STAMP/"
gcloud storage rsync -r "gs://$SRC" "gs://$DST/$STAMP/"
echo "backup complete: cloud sql backup manual-$STAMP; bucket copy gs://$DST/$STAMP/"
