# Memorystore Redis Instance
resource "google_redis_instance" "main" {
  name           = "llamatrade-${var.environment}"
  tier           = local.redis_tier
  memory_size_gb = var.redis_memory_size_gb
  region         = var.region

  authorized_network = google_compute_network.main.id

  redis_version = "REDIS_7_0"

  # Replica configuration for HA tier
  replica_count = var.redis_ha_enabled ? 1 : 0
  read_replicas_mode = var.redis_ha_enabled ? "READ_REPLICAS_ENABLED" : "READ_REPLICAS_DISABLED"

  # Transit encryption
  transit_encryption_mode = "SERVER_AUTHENTICATION"

  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 4
        minutes = 0
      }
    }
  }

  labels = local.default_labels

  depends_on = [google_project_service.services]
}

output "redis_host" {
  description = "Redis instance host"
  value       = google_redis_instance.main.host
  sensitive   = true
}

output "redis_port" {
  description = "Redis instance port"
  value       = google_redis_instance.main.port
}
