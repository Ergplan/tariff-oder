output "project_id" {
  value = var.project_id
}

output "region" {
  value = var.region
}

output "load_balancer_ip" {
  description = "Point the DNS A record for var.domain at this address."
  value       = google_compute_global_address.lb.address
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
  value = { for k, b in google_storage_bucket.b : k => b.name }
}

output "cloud_sql_instance" {
  value = google_sql_database_instance.pg.name
}

output "iap_audiences" {
  description = "Copy into var.iap_audiences after the first apply."
  value = [
    "/projects/${data.google_project.this.number}/global/backendServices/${google_compute_backend_service.api.generated_id}",
    "/projects/${data.google_project.this.number}/global/backendServices/${google_compute_backend_service.web.generated_id}",
  ]
}
