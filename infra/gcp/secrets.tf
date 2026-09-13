# Secret Manager: secret ids equal the environment-variable names so application code is
# identical across profiles (SecretManagerProvider reads `<NAME>/versions/latest`).
# Provider API keys (ANTHROPIC_API_KEY, OPENAI_API_KEY) are created empty here and populated
# out of band by an administrator; the app treats a missing key as fixture mode, never as an
# error at startup.

locals {
  managed_secrets = {
    DATABASE_URL = local.database_url
  }
  placeholder_secrets = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]
}

resource "google_secret_manager_secret" "managed" {
  for_each  = local.managed_secrets
  secret_id = each.key
  labels    = local.labels
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_version" "managed" {
  for_each    = local.managed_secrets
  secret      = google_secret_manager_secret.managed[each.key].id
  secret_data = each.value
}

resource "google_secret_manager_secret" "placeholder" {
  for_each  = toset(local.placeholder_secrets)
  secret_id = each.value
  labels    = local.labels
  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
  depends_on = [google_project_service.apis]
}
