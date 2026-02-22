# Cloud Monitoring and Alerting

# Notification channel for alerts
resource "google_monitoring_notification_channel" "email" {
  display_name = "LlamaTrade Alerts Email"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  enabled = true
}

# Uptime check for API Gateway
resource "google_monitoring_uptime_check_config" "api_gateway" {
  display_name = "API Gateway Health Check"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path         = "/health"
    port         = 8000
    use_ssl      = true
    validate_ssl = true
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.environment == "production" ? "api.llamatrade.com" : "api.staging.llamatrade.com"
    }
  }

  content_matchers {
    content = "ok"
    matcher = "CONTAINS_STRING"
  }
}

# Alert policy for API Gateway downtime
resource "google_monitoring_alert_policy" "api_gateway_down" {
  display_name = "API Gateway Down"
  combiner     = "OR"

  conditions {
    display_name = "API Gateway Uptime Check Failed"

    condition_threshold {
      filter          = "resource.type = \"uptime_url\" AND metric.type = \"monitoring.googleapis.com/uptime_check/check_passed\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "The API Gateway has been unreachable for more than 5 minutes. Check GKE cluster and gateway pods."
    mime_type = "text/markdown"
  }
}

# Alert policy for high CPU usage
resource "google_monitoring_alert_policy" "high_cpu" {
  display_name = "High CPU Usage"
  combiner     = "OR"

  conditions {
    display_name = "GKE Container CPU > 80%"

    condition_threshold {
      filter          = "resource.type = \"k8s_container\" AND metric.type = \"kubernetes.io/container/cpu/limit_utilization\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.8
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "A container is using more than 80% of its CPU limit for 5+ minutes. Consider scaling or optimizing."
    mime_type = "text/markdown"
  }
}

# Alert policy for high memory usage
resource "google_monitoring_alert_policy" "high_memory" {
  display_name = "High Memory Usage"
  combiner     = "OR"

  conditions {
    display_name = "GKE Container Memory > 85%"

    condition_threshold {
      filter          = "resource.type = \"k8s_container\" AND metric.type = \"kubernetes.io/container/memory/limit_utilization\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.85
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "A container is using more than 85% of its memory limit for 5+ minutes. Risk of OOM kills."
    mime_type = "text/markdown"
  }
}

# Alert policy for database connection issues
resource "google_monitoring_alert_policy" "db_connections" {
  display_name = "Database Connection Pool Exhausted"
  combiner     = "OR"

  conditions {
    display_name = "Cloud SQL Connections > 90%"

    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/network/connections\""
      comparison      = "COMPARISON_GT"
      threshold_value = 90
      duration        = "60s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Database connection pool is near exhaustion. Check for connection leaks or scale the database."
    mime_type = "text/markdown"
  }
}

# Alert policy for error rate
resource "google_monitoring_alert_policy" "error_rate" {
  display_name = "High Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "HTTP 5xx Error Rate > 5%"

    condition_threshold {
      filter          = "resource.type = \"k8s_container\" AND metric.type = \"logging.googleapis.com/user/http_error_rate\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      duration        = "300s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.name]

  alert_strategy {
    auto_close = "1800s"
  }

  documentation {
    content   = "Server error rate exceeds 5%. Check application logs for errors."
    mime_type = "text/markdown"
  }
}

# Log sink for long-term storage
resource "google_logging_project_sink" "logs_to_storage" {
  name        = "llamatrade-logs-to-storage"
  destination = "storage.googleapis.com/${google_storage_bucket.logs.name}"
  filter      = "resource.type = \"k8s_container\" AND resource.labels.namespace_name = \"llamatrade\""

  unique_writer_identity = true
}

# Grant write access to the log sink
resource "google_storage_bucket_iam_member" "logs_writer" {
  bucket = google_storage_bucket.logs.name
  role   = "roles/storage.objectCreator"
  member = google_logging_project_sink.logs_to_storage.writer_identity
}

# Custom dashboard
resource "google_monitoring_dashboard" "main" {
  dashboard_json = jsonencode({
    displayName = "LlamaTrade Overview"
    gridLayout = {
      columns = 2
      widgets = [
        {
          title = "API Request Rate"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type = \"k8s_container\" AND metric.type = \"kubernetes.io/container/restart_count\""
                }
              }
            }]
          }
        },
        {
          title = "Container CPU Usage"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type = \"k8s_container\" AND metric.type = \"kubernetes.io/container/cpu/limit_utilization\""
                }
              }
            }]
          }
        },
        {
          title = "Container Memory Usage"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type = \"k8s_container\" AND metric.type = \"kubernetes.io/container/memory/limit_utilization\""
                }
              }
            }]
          }
        },
        {
          title = "Database Connections"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/network/connections\""
                }
              }
            }]
          }
        }
      ]
    }
  })
}
