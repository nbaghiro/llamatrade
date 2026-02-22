# Secret Manager secrets for LlamaTrade

# JWT Secret
resource "google_secret_manager_secret" "jwt_secret" {
  secret_id = "jwt-secret"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "auth"
  }
}

resource "google_secret_manager_secret_version" "jwt_secret" {
  secret      = google_secret_manager_secret.jwt_secret.id
  secret_data = random_password.jwt_secret.result
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = true
}

# Encryption Key
resource "google_secret_manager_secret" "encryption_key" {
  secret_id = "encryption-key"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "auth"
  }
}

resource "google_secret_manager_secret_version" "encryption_key" {
  secret      = google_secret_manager_secret.encryption_key.id
  secret_data = random_password.encryption_key.result
}

resource "random_password" "encryption_key" {
  length  = 32
  special = false
}

# Alpaca API credentials (placeholder - actual values set via console/CLI)
resource "google_secret_manager_secret" "alpaca_api_key" {
  secret_id = "alpaca-api-key"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "trading"
  }
}

resource "google_secret_manager_secret" "alpaca_api_secret" {
  secret_id = "alpaca-api-secret"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "trading"
  }
}

# Stripe API credentials (placeholder)
resource "google_secret_manager_secret" "stripe_secret_key" {
  secret_id = "stripe-secret-key"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "billing"
  }
}

resource "google_secret_manager_secret" "stripe_webhook_secret" {
  secret_id = "stripe-webhook-secret"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "billing"
  }
}

# SMTP credentials (placeholder)
resource "google_secret_manager_secret" "smtp_password" {
  secret_id = "smtp-password"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "notification"
  }
}

# Database connection string (composed from other values)
resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "database"
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql+asyncpg://${google_sql_user.main.name}:${random_password.db_password.result}@${google_sql_database_instance.main.private_ip_address}:5432/${google_sql_database.main.name}"
}

# Redis connection string
resource "google_secret_manager_secret" "redis_url" {
  secret_id = "redis-url"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "cache"
  }
}

resource "google_secret_manager_secret_version" "redis_url" {
  secret      = google_secret_manager_secret.redis_url.id
  secret_data = "redis://${google_redis_instance.main.host}:${google_redis_instance.main.port}"
}

# Outputs
output "jwt_secret_name" {
  description = "JWT secret name in Secret Manager"
  value       = google_secret_manager_secret.jwt_secret.secret_id
}

output "database_url_secret_name" {
  description = "Database URL secret name in Secret Manager"
  value       = google_secret_manager_secret.database_url.secret_id
}
