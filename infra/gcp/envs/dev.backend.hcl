# Remote Terraform state for the dev project.
# Bucket already exists: tarifforderstudio_tfstate (confirm versioning with
# `scripts/verify-gcp-setup.sh`, or: gcloud storage buckets update gs://tarifforderstudio_tfstate --versioning).
bucket = "tarifforderstudio_tfstate"
prefix = "tariff/dev"
