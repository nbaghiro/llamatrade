# Cloud Storage buckets for LlamaTrade

# Backtest results bucket
resource "google_storage_bucket" "backtest_results" {
  name          = "llamatrade-${var.environment}-backtest-results"
  location      = var.region
  force_destroy = var.environment != "production"

  uniform_bucket_level_access = true

  versioning {
    enabled = var.environment == "production"
  }

  lifecycle_rule {
    condition {
      age = var.environment == "production" ? 365 : 30
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  labels = {
    environment = var.environment
    service     = "backtest"
  }
}

# Static assets bucket (for CDN)
resource "google_storage_bucket" "static_assets" {
  name          = "llamatrade-${var.environment}-static"
  location      = var.region
  force_destroy = var.environment != "production"

  uniform_bucket_level_access = true

  website {
    main_page_suffix = "index.html"
    not_found_page   = "404.html"
  }

  cors {
    origin          = var.environment == "production" ? ["https://llamatrade.com"] : ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["*"]
    max_age_seconds = 3600
  }

  labels = {
    environment = var.environment
    service     = "frontend"
  }
}

# Make static assets public
resource "google_storage_bucket_iam_member" "static_public" {
  bucket = google_storage_bucket.static_assets.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Logs export bucket
resource "google_storage_bucket" "logs" {
  name          = "llamatrade-${var.environment}-logs"
  location      = var.region
  force_destroy = var.environment != "production"

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = var.environment == "production" ? 90 : 14
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  labels = {
    environment = var.environment
    service     = "logs"
  }
}

# Database backups bucket
resource "google_storage_bucket" "db_backups" {
  name          = "llamatrade-${var.environment}-db-backups"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = var.environment == "production" ? 365 : 30
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    environment = var.environment
    service     = "database"
  }
}

# Outputs
output "backtest_results_bucket" {
  description = "Backtest results storage bucket"
  value       = google_storage_bucket.backtest_results.name
}

output "static_assets_bucket" {
  description = "Static assets storage bucket"
  value       = google_storage_bucket.static_assets.name
}

output "static_assets_url" {
  description = "Static assets URL"
  value       = "https://storage.googleapis.com/${google_storage_bucket.static_assets.name}"
}
