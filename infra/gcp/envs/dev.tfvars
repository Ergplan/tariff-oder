# Development project.  Fill project_id/billing_account_id/domain before `make tf-plan ENV=dev`.
# Nothing here is a secret.
project_id           = "REPLACE-tariff-dev"
environment          = "dev"
region               = "asia-south1"
billing_account_id   = "REPLACE-000000-000000-000000"
alert_email          = "venture@aayuda.energy"
domain               = "tariff-dev.example.invalid"
iap_audiences        = [] # fill from `terraform output iap_audiences` after the first apply
iap_members          = ["user:venture@aayuda.energy"]
python_image         = "asia-south1-docker.pkg.dev/REPLACE-tariff-dev/tariff/python:dev"
web_image            = "asia-south1-docker.pkg.dev/REPLACE-tariff-dev/tariff/web:dev"
db_availability_type = "ZONAL"
deletion_protection  = false
api_min_instances    = 0
budget_amount_inr    = 20000
