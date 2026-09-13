# Global external HTTPS load balancer with Identity-Aware Proxy in front of the web app and
# the API.  Created only when var.domain is set: a Google-managed certificate requires a
# domain you control.  With no domain the whole block is skipped and Cloud Run has no public
# ingress at all (see run.tf) — the backend is still fully usable through Cloud Run Jobs and
# from inside the VPC.  ADR-0008.

locals {
  enable_lb = var.domain != "" ? 1 : 0
}

resource "google_compute_global_address" "lb" {
  count = local.enable_lb
  name  = "${local.name}-lb-ip"
}

resource "google_compute_region_network_endpoint_group" "api" {
  count                 = local.enable_lb
  name                  = "${local.name}-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_region_network_endpoint_group" "web" {
  count                 = local.enable_lb
  name                  = "${local.name}-web-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.web.name
  }
}

resource "google_compute_backend_service" "api" {
  count                 = local.enable_lb
  name                  = "${local.name}-api-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.api[0].id
  }
  iap {
    enabled = true
  }
  log_config {
    enable = true
  }
}

resource "google_compute_backend_service" "web" {
  count                 = local.enable_lb
  name                  = "${local.name}-web-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.web[0].id
  }
  iap {
    enabled = true
  }
  log_config {
    enable = true
  }
}

resource "google_compute_url_map" "lb" {
  count           = local.enable_lb
  name            = "${local.name}-urlmap"
  default_service = google_compute_backend_service.web[0].id

  host_rule {
    hosts        = [var.domain]
    path_matcher = "main"
  }
  path_matcher {
    name            = "main"
    default_service = google_compute_backend_service.web[0].id
    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.api[0].id
    }
  }
}

resource "google_compute_managed_ssl_certificate" "lb" {
  count = local.enable_lb
  name  = "${local.name}-cert"
  managed {
    domains = [var.domain]
  }
}

resource "google_compute_target_https_proxy" "lb" {
  count            = local.enable_lb
  name             = "${local.name}-https-proxy"
  url_map          = google_compute_url_map.lb[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb[0].id]
}

resource "google_compute_global_forwarding_rule" "lb" {
  count                 = local.enable_lb
  name                  = "${local.name}-https"
  target                = google_compute_target_https_proxy.lb[0].id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb[0].address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
