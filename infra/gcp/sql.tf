# Cloud SQL for PostgreSQL 16 with pgvector, private IP, automated backups and PITR.
# The `vector` extension is created by the application's first migration (CREATE EXTENSION),
# which Cloud SQL permits for pgvector without flags.

resource "random_password" "db" {
  length  = 32
  special = false
}

resource "google_sql_database_instance" "pg" {
  name                = "${local.name}-pg-${var.environment}"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = var.deletion_protection
  depends_on          = [google_service_networking_connection.psa]

  settings {
    tier              = var.db_tier
    availability_type = var.db_availability_type
    disk_autoresize   = true
    disk_type         = "PD_SSD"
    user_labels       = local.labels

    ip_configuration {
      ipv4_enabled                                  = false
      private_network                               = google_compute_network.vpc.id
      enable_private_path_for_google_cloud_services = true
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "20:00" # UTC = 01:30 IST
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 14
        retention_unit   = "COUNT"
      }
    }

    maintenance_window {
      day          = 7
      hour         = 21
      update_track = "stable"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
  }
}

resource "google_sql_database" "app" {
  name     = local.name
  instance = google_sql_database_instance.pg.name
}

resource "google_sql_user" "app" {
  name     = local.name
  instance = google_sql_database_instance.pg.name
  password = random_password.db.result
}

locals {
  database_url = "postgresql+psycopg://${google_sql_user.app.name}:${random_password.db.result}@${google_sql_database_instance.pg.private_ip_address}:5432/${google_sql_database.app.name}"
}
