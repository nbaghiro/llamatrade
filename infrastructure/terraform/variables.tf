variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment (staging, production)"
  type        = string
  default     = "staging"

  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "Environment must be 'staging' or 'production'."
  }
}

variable "db_tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_max_connections" {
  description = <<-EOT
    Postgres max_connections for the Cloud SQL instance. Must cover the sum of
    every pod's (DB_POOL_SIZE + DB_MAX_OVERFLOW) at HPA maxima plus a reserve for
    admin and monitoring sessions; see the budget in
    infrastructure/k8s/base/configmap.yaml (worst case ~400). Leave null to keep
    the tier default. Set to 500 for the production tier (db-custom-2-7680); a
    smaller tier (db-f1-micro) cannot honor a large value.
  EOT
  type        = number
  default     = null
}

variable "db_ha_enabled" {
  description = "Enable high availability for Cloud SQL"
  type        = bool
  default     = false
}

variable "redis_memory_size_gb" {
  description = "Redis memory size in GB"
  type        = number
  default     = 1
}

variable "redis_ha_enabled" {
  description = "Enable high availability for Redis (STANDARD_HA tier)"
  type        = bool
  default     = false
}

variable "alert_email" {
  description = "Email address for monitoring alerts"
  type        = string
  default     = "alerts@llamatrade.com"
}

variable "domain" {
  description = "Primary domain for the application"
  type        = string
  default     = "llamatrade.com"
}

variable "enable_cdn" {
  description = "Enable Cloud CDN for static assets"
  type        = bool
  default     = true
}

variable "gke_release_channel" {
  description = "GKE release channel (RAPID, REGULAR, STABLE)"
  type        = string
  default     = "REGULAR"
}

# Managed Service for Apache Kafka (the event backbone)
variable "kafka_vcpu_count" {
  description = "Managed Kafka cluster vCPU count (minimum 3)"
  type        = number
  default     = 3
}

variable "kafka_memory_bytes" {
  description = "Managed Kafka cluster memory in bytes (1-8 GiB per vCPU)"
  type        = number
  default     = 12884901888 # 12 GiB (4 GiB per vCPU at 3 vCPUs)
}

variable "kafka_replication_factor" {
  description = "Topic replication factor (must be <= broker count)"
  type        = number
  default     = 3
}

# Environment-specific defaults
locals {
  is_production = var.environment == "production"

  db_tier_default = local.is_production ? "db-custom-2-7680" : "db-f1-micro"
  redis_tier      = var.redis_ha_enabled ? "STANDARD_HA" : "BASIC"

  default_labels = {
    environment = var.environment
    managed_by  = "terraform"
    project     = "llamatrade"
  }
}
