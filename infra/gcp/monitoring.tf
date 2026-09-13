# Budgets and alerts.  A stopped job is preferable to an unbounded bill.

resource "google_monitoring_notification_channel" "email" {
  display_name = "tariff-${var.environment}-alerts"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
  depends_on = [google_project_service.apis]
}

locals {
  # A budget needs the billing account id, which is not required to stand the project up.
  # `scripts/verify-gcp-setup.sh` reports a missing budget as an outstanding item.
  enable_budget = var.billing_account_id != "" ? 1 : 0
}

resource "google_billing_budget" "project" {
  count           = local.enable_budget
  billing_account = var.billing_account_id
  display_name    = "tariff-${var.environment}-monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }
  amount {
    specified_amount {
      currency_code = "INR"
      units         = tostring(var.budget_amount_inr)
    }
  }
  threshold_rules {
    threshold_percent = 0.5
  }
  threshold_rules {
    threshold_percent = 0.8
  }
  threshold_rules {
    threshold_percent = 1.0
  }
  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
    disable_default_iam_recipients   = false
  }
  depends_on = [google_project_service.apis]
}

# API 5xx rate
resource "google_monitoring_alert_policy" "api_5xx" {
  display_name = "tariff-${var.environment} API 5xx"
  combiner     = "OR"
  conditions {
    display_name = "Cloud Run api 5xx > 5 in 5m"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${google_cloud_run_v2_service.api.name}\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "300s"
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
  depends_on            = [google_project_service.apis]
}

# Worker job failures (typed failures are logged at ERROR with error_type)
resource "google_logging_metric" "job_failed" {
  name   = "tariff_job_failed"
  filter = "resource.type=\"cloud_run_job\" AND jsonPayload.message=\"job failed\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    labels {
      key         = "error_type"
      value_type  = "STRING"
      description = "typed error"
    }
  }
  label_extractors = {
    error_type = "EXTRACT(jsonPayload.error_type)"
  }
  depends_on = [google_project_service.apis]
}

resource "google_monitoring_alert_policy" "job_failed" {
  display_name = "tariff-${var.environment} worker job failed"
  combiner     = "OR"
  conditions {
    display_name = "any failed job in 10m"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.job_failed.name}\" AND resource.type=\"cloud_run_job\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period   = "600s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }
  notification_channels = [google_monitoring_notification_channel.email.id]
}
