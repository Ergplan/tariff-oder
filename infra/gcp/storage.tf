# Buckets: private, uniform access, no public objects.  Sources are versioned (immutable
# content-addressed keys plus object versioning as a second safety net).  Names are globally
# unique, so they carry the project id.

locals {
  buckets = {
    sources   = { versioning = true }
    artefacts = { versioning = false }
    exports   = { versioning = false }
    backups   = { versioning = true }
  }
}

resource "google_storage_bucket" "b" {
  for_each                    = local.buckets
  name                        = "${var.project_id}-${local.name}-${each.key}"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = !var.deletion_protection
  labels                      = local.labels

  versioning {
    enabled = each.value.versioning
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 5
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.apis]
}
