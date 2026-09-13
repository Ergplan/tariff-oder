# Production project.  Applied only with explicit authorisation (Section 3.3); same code, different values.
project_id           = "REPLACE-tariff-prod"
environment          = "prod"
region               = "asia-south1"
billing_account_id   = "REPLACE-000000-000000-000000"
alert_email          = "venture@aayuda.energy"
domain               = "tariff.example.invalid"
iap_audiences        = [] # fill from `terraform output iap_audiences` after the first apply
iap_members          = []
python_image         = "asia-south1-docker.pkg.dev/REPLACE-tariff-prod/tariff/python@sha256:REPLACE"
web_image            = "asia-south1-docker.pkg.dev/REPLACE-tariff-prod/tariff/web@sha256:REPLACE"
db_availability_type = "REGIONAL"
db_tier              = "db-custom-2-7680"
deletion_protection  = true
api_min_instances    = 1
budget_amount_inr    = 60000
