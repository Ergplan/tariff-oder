# Buckets: private, uniform access, no public objects.  Sources are versioned (immutable
# content-addressed keys plus object versioning as a second safety net).  Names are globally
# unique, so created buckets carry the project id.
#
# The source bucket may already exist (ADR-0008): set var.existing_source_bucket and Terraform
# adopts it by name instead of creating one.  Terraform does not manage that bucket's location,
# versioning or lifecycle — `scripts/verify-gcp-setup.sh` checks them and reports deviations.

locals {
  created_buckets = merge(
    {
      artefacts = { versioning = false }
      exports   = { versioning = false }
      backups   = { versioning = true }
    },
    var.existing_source_bucket == "" ? { sources = { versioning = true } } : {}
  )

  source_bucket_name = var.existing_source_bucket != "" ? var.existing_source_bucket : google_storage_bucket.b["sources"].name

  # Every logical bucket the services need access to, created or adopted.
  bucket_names = merge(
    { for k, b in google_storage_bucket.b : k => b.name },
    { sources = local.source_bucket_name },
  )
}

resource "google_storage_bucket" "b" {
  for_each                    = local.created_buckets
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
