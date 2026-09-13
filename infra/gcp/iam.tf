# One service account per workload; least privilege; no shared credentials across environments.

resource "google_service_account" "api" {
  account_id   = "${local.name}-api"
  display_name = "Tariff API (Cloud Run service)"
}

resource "google_service_account" "worker" {
  account_id   = "${local.name}-worker"
  display_name = "Tariff worker (Cloud Run job)"
}

resource "google_service_account" "web" {
  account_id   = "${local.name}-web"
  display_name = "Tariff web (Cloud Run service)"
}

resource "google_service_account" "scheduler" {
  account_id   = "${local.name}-scheduler"
  display_name = "Cloud Scheduler invoker for the worker job"
}

locals {
  data_services = {
    api    = google_service_account.api.email
    worker = google_service_account.worker.email
  }
}

# Cloud SQL client + logging for data services
resource "google_project_iam_member" "sql_client" {
  for_each = local.data_services
  project  = var.project_id
  role     = "roles/cloudsql.client"
  member   = "serviceAccount:${each.value}"
}

resource "google_project_iam_member" "log_writer" {
  for_each = merge(local.data_services, { web = google_service_account.web.email })
  project  = var.project_id
  role     = "roles/logging.logWriter"
  member   = "serviceAccount:${each.value}"
}

# Bucket-scoped object access (objectUser: read/write objects, no bucket admin)
resource "google_storage_bucket_iam_member" "data_services" {
  for_each = { for pair in setproduct(keys(local.data_services), keys(local.buckets)) : "${pair[0]}-${pair[1]}" => pair }
  bucket   = google_storage_bucket.b[each.value[1]].name
  role     = "roles/storage.objectUser"
  member   = "serviceAccount:${local.data_services[each.value[0]]}"
}

# Secret-scoped access
resource "google_secret_manager_secret_iam_member" "database_url" {
  for_each  = local.data_services
  secret_id = google_secret_manager_secret.managed["DATABASE_URL"].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value}"
}

resource "google_secret_manager_secret_iam_member" "provider_keys_worker" {
  for_each  = toset(local.placeholder_secrets)
  secret_id = google_secret_manager_secret.placeholder[each.value].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "provider_keys_api" {
  for_each  = toset(local.placeholder_secrets)
  secret_id = google_secret_manager_secret.placeholder[each.value].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# Web -> API service-to-service invocation; scheduler -> worker job
resource "google_cloud_run_v2_service_iam_member" "web_invokes_api" {
  location = var.region
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.web.email}"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_runs_worker" {
  location = var.region
  name     = google_cloud_run_v2_job.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# IAP: who may reach the web app / API through the load balancer.  Application roles
# (analyst/reviewer/administrator) are assigned separately in the users table.
resource "google_iap_web_backend_service_iam_member" "web_users" {
  for_each            = toset(var.iap_members)
  project             = var.project_id
  web_backend_service = google_compute_backend_service.web.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}

resource "google_iap_web_backend_service_iam_member" "api_users" {
  for_each            = toset(var.iap_members)
  project             = var.project_id
  web_backend_service = google_compute_backend_service.api.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = each.value
}
