output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "load_balancer_ip" {
  description = "Point the DNS A record for var.domain at this address. Null when no domain is configured (no public ingress)."
  value       = local.enable_lb == 1 ? google_compute_global_address.lb[0].address : null
}

output "public_ingress" {
  description = "Whether anything is reachable from the internet."
  value       = local.enable_lb == 1 ? "load balancer + IAP on ${var.domain}" : "none (Cloud Run is VPC-internal; use Cloud Run Jobs or a proxy)"
}

output "api_service_uri" {
  value = google_cloud_run_v2_service.api.uri
}

output "web_service_uri" {
  value = google_cloud_run_v2_service.web.uri
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.docker.repository_id}"
}

output "buckets" {
  description = "Logical bucket name per role; `sources` may be an adopted pre-existing bucket."
  value       = local.bucket_names
}

output "source_bucket_is_adopted" {
  description = "True when the source bucket was created outside Terraform (its location/versioning are not managed here)."
  value       = var.existing_source_bucket != ""
}

output "cloud_sql_instance" {
  value = google_sql_database_instance.pg.name
}

output "budget_created" {
  value = local.enable_budget == 1
}

output "iap_audiences" {
  description = "Copy into var.iap_audiences after the first apply. Empty when no load balancer exists."
  value = local.enable_lb == 1 ? [
    "/projects/${data.google_project.this.number}/global/backendServices/${google_compute_backend_service.api[0].generated_id}",
    "/projects/${data.google_project.this.number}/global/backendServices/${google_compute_backend_service.web[0].generated_id}",
  ] : []
}
