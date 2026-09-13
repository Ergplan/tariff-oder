variable "project_id" {
  description = "GCP project id for this environment (dev, staging, prod are separate projects)."
  type        = string
}

variable "environment" {
  description = "Environment name: dev | staging | prod."
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod"
  }
}

variable "region" {
  description = "Single Indian region for all data-bearing services (ADR-0006)."
  type        = string
  default     = "asia-south1"
}

variable "billing_account_id" {
  description = "Billing account for the budget resource (format 012345-678901-ABCDEF)."
  type        = string
}

variable "budget_amount_inr" {
  description = "Monthly budget in INR for alerts (50/80/100%)."
  type        = number
  default     = 20000
}

variable "alert_email" {
  description = "Email for budget and monitoring alerts."
  type        = string
}

variable "domain" {
  description = "Hostname for the IAP-protected load balancer (managed certificate)."
  type        = string
}

variable "iap_members" {
  description = "Principals allowed through IAP, e.g. [\"user:venture@aayuda.energy\"]. Roles are still enforced by the API."
  type        = list(string)
  default     = []
}

variable "python_image" {
  description = "Artifact Registry image for api/worker/migrate (pin a digest per release)."
  type        = string
}

variable "web_image" {
  description = "Artifact Registry image for the web app (pin a digest per release)."
  type        = string
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-custom-1-3840"
}

variable "db_availability_type" {
  description = "ZONAL for dev, REGIONAL for prod."
  type        = string
  default     = "ZONAL"
}

variable "deletion_protection" {
  description = "Protect Cloud SQL and buckets from terraform destroy."
  type        = bool
  default     = true
}

variable "api_min_instances" {
  type    = number
  default = 0
}

variable "worker_schedule" {
  description = "Cloud Scheduler cron that triggers the worker job to drain the queue."
  type        = string
  default     = "*/5 * * * *"
}

variable "job_lease_seconds" {
  type    = number
  default = 120
}

variable "iap_audiences" {
  description = "IAP JWT audiences the API accepts (api and web backend services). Empty on the first apply; fill from the `iap_audiences` output and re-apply."
  type        = list(string)
  default     = []
}
