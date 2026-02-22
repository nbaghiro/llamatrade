# Cloud SQL PostgreSQL Instance
resource "google_sql_database_instance" "main" {
  name             = "llamatrade-${var.environment}"
  database_version = "POSTGRES_16"
  region           = var.region

  settings {
    tier = var.db_tier

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "04:00"
    }

    maintenance_window {
      day  = 7  # Sunday
      hour = 4
    }

    insights_config {
      query_insights_enabled = true
    }
  }

  deletion_protection = var.environment == "production"

  depends_on = [google_service_networking_connection.private_vpc]
}

# Database
resource "google_sql_database" "main" {
  name     = "llamatrade"
  instance = google_sql_database_instance.main.name
}

# Database user
resource "google_sql_user" "main" {
  name     = "llamatrade"
  instance = google_sql_database_instance.main.name
  password = random_password.db_password.result
}

resource "random_password" "db_password" {
  length  = 32
  special = false
}

# Store password in Secret Manager
resource "google_secret_manager_secret" "db_password" {
  secret_id = "db-password"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}
