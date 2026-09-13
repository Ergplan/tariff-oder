# Global external HTTPS load balancer with Identity-Aware Proxy in front of the web app and
# the API.  Cloud Run ingress is restricted to the load balancer, so IAP is the only public
# entry point.  Path routing: /api/* -> api service, everything else -> web.

resource "google_compute_global_address" "lb" {
  name = "${local.name}-lb-ip"
}

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "${local.name}-api-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_region_network_endpoint_group" "web" {
  name                  = "${local.name}-web-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region
  cloud_run {
    service = google_cloud_run_v2_service.web.name
  }
}

resource "google_compute_backend_service" "api" {
  name                  = "${local.name}-api-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }
  iap {
    enabled = true
  }
  log_config {
    enable = true
  }
}

resource "google_compute_backend_service" "web" {
  name                  = "${local.name}-web-backend"
  protocol              = "HTTPS"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  backend {
    group = google_compute_region_network_endpoint_group.web.id
  }
  iap {
    enabled = true
  }
  log_config {
    enable = true
  }
}

resource "google_compute_url_map" "lb" {
  name            = "${local.name}-urlmap"
  default_service = google_compute_backend_service.web.id

  host_rule {
    hosts        = [var.domain]
    path_matcher = "main"
  }
  path_matcher {
    name            = "main"
    default_service = google_compute_backend_service.web.id
    path_rule {
      paths   = ["/api", "/api/*"]
      service = google_compute_backend_service.api.id
    }
  }
}

resource "google_compute_managed_ssl_certificate" "lb" {
  name = "${local.name}-cert"
  managed {
    domains = [var.domain]
  }
}

resource "google_compute_target_https_proxy" "lb" {
  name             = "${local.name}-https-proxy"
  url_map          = google_compute_url_map.lb.id
  ssl_certificates = [google_compute_managed_ssl_certificate.lb.id]
}

resource "google_compute_global_forwarding_rule" "lb" {
  name                  = "${local.name}-https"
  target                = google_compute_target_https_proxy.lb.id
  port_range            = "443"
  ip_address            = google_compute_global_address.lb.address
  load_balancing_scheme = "EXTERNAL_MANAGED"
}
