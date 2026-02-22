# GKE Autopilot Cluster
resource "google_container_cluster" "main" {
  name     = "llamatrade-${var.environment}"
  location = var.region

  # Enable Autopilot
  enable_autopilot = true

  # Network configuration
  network    = google_compute_network.main.name
  subnetwork = google_compute_subnetwork.main.name

  # Private cluster
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = false
    master_ipv4_cidr_block  = "172.16.0.0/28"
  }

  # IP allocation policy
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  # Maintenance window
  maintenance_policy {
    daily_maintenance_window {
      start_time = "03:00"
    }
  }

  depends_on = [google_project_service.services]
}

# Artifact Registry for container images
resource "google_artifact_registry_repository" "main" {
  location      = var.region
  repository_id = "llamatrade"
  format        = "DOCKER"
}
