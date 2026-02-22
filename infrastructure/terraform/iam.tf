# Service Accounts for workload identity

# GKE Workload Identity Service Account
resource "google_service_account" "gke_workload" {
  account_id   = "llamatrade-gke-workload"
  display_name = "LlamaTrade GKE Workload Identity"
  description  = "Service account for GKE workloads to access GCP services"
}

# Cloud SQL Client role for database access
resource "google_project_iam_member" "gke_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# Secret Manager access for secrets
resource "google_project_iam_member" "gke_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# Cloud Storage access for backtest results
resource "google_project_iam_member" "gke_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# Pub/Sub access for event-driven architecture
resource "google_project_iam_member" "gke_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.editor"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# Monitoring metrics writer
resource "google_project_iam_member" "gke_monitoring" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# Logging writer
resource "google_project_iam_member" "gke_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# Trace agent
resource "google_project_iam_member" "gke_trace" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.gke_workload.email}"
}

# Workload Identity binding
resource "google_service_account_iam_member" "gke_workload_identity" {
  service_account_id = google_service_account.gke_workload.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[llamatrade/llamatrade-workload]"
}

# Cloud Build Service Account
resource "google_service_account" "cloudbuild" {
  account_id   = "llamatrade-cloudbuild"
  display_name = "LlamaTrade Cloud Build"
  description  = "Service account for Cloud Build CI/CD"
}

# Cloud Build permissions
resource "google_project_iam_member" "cloudbuild_gke" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_artifact" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

resource "google_project_iam_member" "cloudbuild_logs" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.cloudbuild.email}"
}

# Output service account emails
output "gke_workload_sa_email" {
  description = "GKE workload service account email"
  value       = google_service_account.gke_workload.email
}

output "cloudbuild_sa_email" {
  description = "Cloud Build service account email"
  value       = google_service_account.cloudbuild.email
}
