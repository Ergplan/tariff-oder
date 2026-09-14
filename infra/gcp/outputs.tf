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

output "admin_job_usage" {
  description = "How to run operator commands inside the VPC (the API has no public ingress)."
  value = join(" && ", [
    "gcloud run jobs update ${google_cloud_run_v2_job.admin.name} --project ${var.project_id} --region ${var.region} --args=<command>",
    "gcloud run jobs execute ${google_cloud_run_v2_job.admin.name} --project ${var.project_id} --region ${var.region} --wait",
  ])
}

output "web_iap_commands" {
  description = "With var.web_iap: the gcloud steps that switch IAP on for the web service (the pinned provider has no field for it) and admit var.iap_members. Idempotent; re-run after any apply that changes the web service."
  value = var.web_iap ? join("\n", concat(
    [
      "gcloud beta services identity create --service=iap.googleapis.com --project ${var.project_id}",
      "gcloud run services add-iam-policy-binding ${local.name}-web --project ${var.project_id} --region ${var.region} --member=serviceAccount:service-${data.google_project.this.number}@gcp-sa-iap.iam.gserviceaccount.com --role=roles/run.invoker",
      "gcloud beta run services update ${local.name}-web --project ${var.project_id} --region ${var.region} --iap",
    ],
    [for m in var.iap_members :
      "gcloud beta iap web add-iam-policy-binding --project ${var.project_id} --resource-type=cloud-run --service=${local.name}-web --region=${var.region} --member=${m} --role=roles/iap.httpsResourceAccessor"
    ],
    ["echo open: ${google_cloud_run_v2_service.web.uri}"],
  )) : "web_iap is false: no IAP on the web service"
}
