# Cloud Run: api + web services (behind the IAP load balancer), worker + migrate jobs.
# Request timeouts are sized for API calls; document processing never runs in a request.

locals {
  # With a load balancer the services accept traffic only from it; without one they accept
  # nothing from the internet at all (ADR-0008).
  run_ingress = local.enable_lb == 1 ? "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER" : "INGRESS_TRAFFIC_INTERNAL_ONLY"

  gcp_env = {
    DEPLOYMENT_PROFILE   = "gcp"
    ENVIRONMENT_NAME     = var.environment
    GCP_PROJECT_ID       = var.project_id
    OBJECT_STORE_BACKEND = "gcs"
    SOURCE_BUCKET        = local.bucket_names["sources"]
    ARTEFACT_BUCKET      = local.bucket_names["artefacts"]
    EXPORT_BUCKET        = local.bucket_names["exports"]
    SECRETS_BACKEND      = "secret_manager"
    # With a domain: IAP assertions through the load balancer.  Without one (ADR-0015):
    # Google-signed ID tokens, as minted by `gcloud run services proxy` for the operator and
    # by the web service for itself; audiences are our own Cloud Run URLs in both forms.
    IDENTITY_BACKEND = (local.enable_lb == 1 || var.web_iap) ? "iap" : "google_id_token"
    # Load balancer: backend-service ids exist only after the first apply (copy the
    # `iap_audiences` output into envs/<env>.tfvars and apply again).  IAP directly on the
    # Cloud Run web service (operator-authorised 2026-09-14): the audience is the web
    # service's own resource path.
    IAP_AUDIENCE              = join(",", concat(var.iap_audiences, var.web_iap ? local.web_iap_audiences : []))
    ID_TOKEN_AUDIENCES        = join(",", local.id_token_audiences)
    LOG_FORMAT                = "json"
    JOB_LEASE_SECONDS         = tostring(var.job_lease_seconds)
    PROVIDER_BACKEND          = var.provider_backend
    ANTHROPIC_MODEL           = var.anthropic_model
    SECOND_REVIEW_FIRST_ORDER = var.second_review_first_order ? "true" : "false"
    GOLDEN_MANIFEST_PATH      = "/app/tests/golden/manifest.json"
  }
}

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  # Cloud Run gives every service two URLs: the deterministic
  # https://<name>-<project number>.<region>.run.app and a per-project hashed
  # https://<name>-<hash>-<rc>.a.run.app.  gcloud and the web service may mint tokens for
  # either.  The API cannot reference its own resource, so its hashed form is derived from the
  # web service's (the hash is per project).
  run_base = "${data.google_project.this.number}.${var.region}.run.app"
  # A token minted by `gcloud auth print-identity-token` for a *user* account names gcloud's
  # own OAuth client as its audience (service accounts can name a URL; users cannot).  Cloud
  # Run accepts it at the front door; the API accepts it too, and still takes the role only
  # from the users table.
  gcloud_user_audience = "32555940559.apps.googleusercontent.com"
  # IAP on a Cloud Run service signs assertions for the service's resource path.  The web
  # service becomes reachable from the internet behind Google's sign-in; the API stays internal.
  # Two candidate forms, both exact: the service resource path and the IAP web resource path
  # that IAM reports for the service (`iap_web/cloud_run-<region>/services/<name>`).  The
  # adapter logs the observed audience if neither matches.
  web_iap_audiences = [
    "/projects/${data.google_project.this.number}/locations/${var.region}/services/${local.name}-web",
    "/projects/${data.google_project.this.number}/iap_web/cloud_run-${var.region}/services/${local.name}-web",
  ]
  web_ingress = var.web_iap ? "INGRESS_TRAFFIC_ALL" : local.run_ingress
  id_token_audiences = [
    "https://${local.name}-api-${local.run_base}",
    "https://${local.name}-web-${local.run_base}",
    local.gcloud_user_audience,
  ]
}

resource "google_cloud_run_v2_service" "api" {
  name                = "${local.name}-api"
  location            = var.region
  ingress             = local.run_ingress
  deletion_protection = false
  labels              = local.labels

  template {
    service_account = google_service_account.api.email
    timeout         = "60s"
    scaling {
      min_instance_count = var.api_min_instances
      max_instance_count = 4
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
      egress = "PRIVATE_RANGES_ONLY"
    }
    containers {
      image = var.python_image
      ports {
        container_port = 8000
      }
      resources {
        limits = { cpu = "1", memory = "1Gi" }
      }
      dynamic "env" {
        for_each = local.gcp_env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.managed["DATABASE_URL"].secret_id
            version = "latest"
          }
        }
      }
      startup_probe {
        http_get {
          path = "/healthz"
        }
        initial_delay_seconds = 2
        period_seconds        = 5
        failure_threshold     = 6
      }
      liveness_probe {
        http_get {
          path = "/healthz"
        }
        period_seconds = 30
      }
    }
  }
  lifecycle {
    # Terraform sets the bootstrap image; `make deploy-dev` moves services to release tags.
    ignore_changes = [template[0].containers[0].image]
  }
  depends_on = [google_project_service.apis, google_secret_manager_secret_version.managed]
}

resource "google_cloud_run_v2_service" "web" {
  name                = "${local.name}-web"
  location            = var.region
  ingress             = local.web_ingress
  deletion_protection = false
  labels              = local.labels

  template {
    service_account = google_service_account.web.email
    timeout         = "60s"
    scaling {
      min_instance_count = 0
      max_instance_count = 4
    }
    vpc_access {
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
      # ALL_TRAFFIC: the API's run.app address is public, and the API admits only traffic that
      # arrives through the VPC (internal ingress via Private Google Access).  With
      # PRIVATE_RANGES_ONLY the web service's calls took the public path and got 404.  The VPC
      # has no NAT, so the web service can reach nothing else on the internet — intended.
      egress = "ALL_TRAFFIC"
    }
    containers {
      image = var.web_image
      ports {
        container_port = 3000
      }
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      env {
        name  = "DEPLOYMENT_PROFILE"
        value = "gcp"
      }
      env {
        name  = "API_BASE_URL"
        value = google_cloud_run_v2_service.api.uri
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
  depends_on = [google_project_service.apis]
}

# Worker: Cloud Run Job draining the queue on a schedule (Milestone 1 default).  Milestone 8
# measures a full 570-page run and may replace this with a worker-pool service or GKE (ADR).
resource "google_cloud_run_v2_job" "worker" {
  name                = "${local.name}-worker"
  location            = var.region
  deletion_protection = false
  labels              = local.labels

  template {
    task_count = 1
    template {
      service_account = google_service_account.worker.email
      timeout         = "3600s"
      max_retries     = 0 # retries are the queue's job (bounded attempts, checkpoints)
      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }
      containers {
        image   = var.python_image
        command = ["tariff-worker", "--drain"]
        resources {
          limits = { cpu = "2", memory = "4Gi" }
        }
        dynamic "env" {
          for_each = local.gcp_env
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.managed["DATABASE_URL"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }
  depends_on = [google_project_service.apis, google_secret_manager_secret_version.managed]
}

resource "google_cloud_run_v2_job" "migrate" {
  name                = "${local.name}-migrate"
  location            = var.region
  deletion_protection = false
  labels              = local.labels

  template {
    task_count = 1
    template {
      service_account = google_service_account.api.email
      timeout         = "900s"
      max_retries     = 0
      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }
      containers {
        image   = var.python_image
        command = ["tariff-api", "migrate"]
        dynamic "env" {
          for_each = local.gcp_env
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.managed["DATABASE_URL"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image]
  }
  depends_on = [google_project_service.apis, google_secret_manager_secret_version.managed]
}

# Operator console.  The API is VPC-internal (and, without a domain, has no public ingress at
# all), and the build VM sits in a different network and region — so administrative work runs
# here, inside the VPC, rather than from a laptop or the VM:
#
#   gcloud run jobs update tariff-admin --region <region> --args=inbox
#   gcloud run jobs execute tariff-admin --region <region> --wait
#
# Useful argument sets: `seed`; `inbox`; `ingest,inbox/<file>.pdf,--actor,<email>`;
# `users,add,--email,<email>,--role,administrator,--actor,<email>`.
resource "google_cloud_run_v2_job" "admin" {
  name                = "${local.name}-admin"
  location            = var.region
  deletion_protection = false
  labels              = local.labels

  template {
    task_count = 1
    template {
      service_account = google_service_account.api.email
      timeout         = "900s"
      max_retries     = 0
      vpc_access {
        network_interfaces {
          network    = google_compute_network.vpc.id
          subnetwork = google_compute_subnetwork.run.id
        }
        egress = "PRIVATE_RANGES_ONLY"
      }
      containers {
        image   = var.python_image
        command = ["tariff-api"]
        args    = ["check-config"]
        resources {
          limits = { cpu = "1", memory = "2Gi" }
        }
        dynamic "env" {
          for_each = local.gcp_env
          content {
            name  = env.key
            value = env.value
          }
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.managed["DATABASE_URL"].secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }
  lifecycle {
    # The operator changes `args` per invocation and `make deploy-dev` changes the image;
    # Terraform must not revert either.
    ignore_changes = [template[0].template[0].containers[0].args, template[0].template[0].containers[0].image]
  }
  depends_on = [google_project_service.apis, google_secret_manager_secret_version.managed]
}

resource "google_cloud_scheduler_job" "worker" {
  name        = "${local.name}-worker-drain"
  description = "Run the worker job to drain the PostgreSQL queue"
  schedule    = var.worker_schedule
  time_zone   = "Asia/Kolkata"
  region      = var.region

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.worker.name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
  depends_on = [google_project_service.apis]
}
