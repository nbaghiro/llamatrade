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
