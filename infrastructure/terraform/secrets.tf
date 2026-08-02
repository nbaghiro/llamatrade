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

# RS256 user-token PEM pair. Terraform declares the containers only: generating
# the key here would persist the private half in state, so an operator uploads
# both versions out of band (placeholder, same as the Alpaca/Stripe entries).
resource "google_secret_manager_secret" "auth_jwt_private_key" {
  secret_id = "auth-jwt-private-key"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "auth"
  }
}

resource "google_secret_manager_secret" "auth_jwt_public_key" {
  secret_id = "auth-jwt-public-key"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "auth"
  }
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
resource "google_secret_manager_secret" "smtp_host" {
  secret_id = "smtp-host"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "notification"
  }
}

resource "google_secret_manager_secret" "smtp_user" {
  secret_id = "smtp-user"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "notification"
  }
}

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

# AI copilot LLM provider keys (placeholder)
resource "google_secret_manager_secret" "agent_google_api_key" {
  secret_id = "agent-google-api-key"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "agent"
  }
}

resource "google_secret_manager_secret" "agent_anthropic_api_key" {
  secret_id = "agent-anthropic-api-key"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "agent"
  }
}

# Timescale (market-data bars) credentials. The hypertable runs as an in-cluster
# StatefulSet, so both values are set out of band (placeholder).
resource "google_secret_manager_secret" "timescale_password" {
  secret_id = "timescale-password"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "market-data"
  }
}

resource "google_secret_manager_secret" "timescale_url" {
  secret_id = "timescale-url"

  replication {
    auto {}
  }

  labels = {
    environment = var.environment
    service     = "market-data"
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

# External Secrets Operator reads Secret Manager on behalf of the cluster and
# projects each entry into the Kubernetes Secrets the workloads reference
# (infrastructure/k8s/base/external-secrets). The operator authenticates by
# impersonating the KSA named in the SecretStore, so the bindings follow the
# Managed Kafka pattern in kafka.tf: one GCP SA, the accessor role, and one
# Workload Identity binding per namespace/KSA pair.
resource "google_service_account" "external_secrets" {
  account_id   = "llamatrade-external-secrets"
  display_name = "LlamaTrade External Secrets Operator"
  description  = "Workload Identity SA for External Secrets Operator to read Secret Manager"
}

# Project-level accessor: the operator syncs every secret above, so per-secret
# grants would enumerate the same set. Matches the style in iam.tf.
resource "google_project_iam_member" "external_secrets_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.external_secrets.email}"
}

# The base and production overlays use namespace llamatrade with unprefixed SA names.
resource "google_service_account_iam_member" "external_secrets_workload_identity" {
  service_account_id = google_service_account.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[llamatrade/external-secrets]"
}

# The staging overlay runs in namespace llamatrade-staging with a staging- prefix
# on every resource name.
resource "google_service_account_iam_member" "external_secrets_workload_identity_staging" {
  service_account_id = google_service_account.external_secrets.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[llamatrade-staging/staging-external-secrets]"
}

# Outputs
output "external_secrets_service_account_email" {
  description = "External Secrets Operator SA email (for the KSA iam.gke.io annotation)"
  value       = google_service_account.external_secrets.email
}

output "jwt_secret_name" {
  description = "JWT secret name in Secret Manager"
  value       = google_secret_manager_secret.jwt_secret.secret_id
}

output "database_url_secret_name" {
  description = "Database URL secret name in Secret Manager"
  value       = google_secret_manager_secret.database_url.secret_id
}
