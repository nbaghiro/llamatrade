# Managed Service for Apache Kafka — the event backbone (replaces Redis Streams).
# Requires the hashicorp/google provider >= 5.34 (google_managed_kafka_* GA).

# Cluster lives in the platform VPC (networking.tf), reachable privately from GKE.
resource "google_managed_kafka_cluster" "main" {
  cluster_id = "llamatrade-${var.environment}"
  location   = var.region

  capacity_config {
    vcpu_count   = var.kafka_vcpu_count
    memory_bytes = var.kafka_memory_bytes
  }

  gcp_config {
    access_config {
      network_configs {
        subnet = "projects/${var.project_id}/regions/${var.region}/subnetworks/${google_compute_subnetwork.main.name}"
      }
    }
  }

  rebalance_config {
    mode = "AUTO_REBALANCE_ON_SCALE_UP"
  }

  labels = local.default_labels

  depends_on = [google_project_service.services]
}

locals {
  # Per-topic partition + retention policy. Retention is time-based (delete).
  # NOTE: lt.ledger.fills partition count is a decide-once value — repartitioning a
  # keyed, ordered stream is disruptive, so confirm 24 before the first apply.
  kafka_topics = {
    "lt.ledger.fills"      = { partitions = 24, retention_ms = 90 * 24 * 60 * 60 * 1000 } # 90 days
    "lt.ledger.fills.dlq"  = { partitions = 6, retention_ms = 30 * 24 * 60 * 60 * 1000 }  # 30 days
    "lt.market.bars.1m"    = { partitions = 12, retention_ms = 7 * 24 * 60 * 60 * 1000 }  # 7 days
    "lt.trading.orders"    = { partitions = 12, retention_ms = 24 * 60 * 60 * 1000 }      # 24 hours
    "lt.trading.positions" = { partitions = 12, retention_ms = 24 * 60 * 60 * 1000 }      # 24 hours
    "lt.backtest.progress" = { partitions = 6, retention_ms = 6 * 60 * 60 * 1000 }        # 6 hours
    "lt.notifications"     = { partitions = 6, retention_ms = 30 * 24 * 60 * 60 * 1000 }  # 30 days
    "lt.notifications.dlq" = { partitions = 3, retention_ms = 30 * 24 * 60 * 60 * 1000 }  # 30 days
  }

  # Services that produce/consume events, each gets a dedicated Workload Identity SA.
  kafka_services = toset(["trading", "portfolio", "market-data", "backtest", "notification", "strategy", "billing", "auth", "agent"])
}

resource "google_managed_kafka_topic" "topics" {
  for_each = local.kafka_topics

  topic_id           = each.key
  cluster            = google_managed_kafka_cluster.main.cluster_id
  location           = var.region
  partition_count    = each.value.partitions
  replication_factor = var.kafka_replication_factor

  configs = {
    "retention.ms"   = tostring(each.value.retention_ms)
    "cleanup.policy" = "delete"
  }

  depends_on = [google_project_service.services]
}

# Per-service GCP service accounts (Workload Identity clients of the cluster).
resource "google_service_account" "kafka_service" {
  for_each = local.kafka_services

  account_id   = "llamatrade-${each.key}"
  display_name = "LlamaTrade ${each.key} (Managed Kafka client)"
  description  = "Workload Identity SA for the ${each.key} service to access Managed Service for Apache Kafka"
}

# Cluster-wide client role (connect + produce/consume). Matches the project-level
# IAM style in iam.tf.
resource "google_project_iam_member" "kafka_client" {
  for_each = local.kafka_services

  project = var.project_id
  role    = "roles/managedkafka.client"
  member  = "serviceAccount:${google_service_account.kafka_service[each.key].email}"
}

# Workload Identity: map each K8s SA (namespace/name) to its GCP SA. The base and
# production overlays use namespace llamatrade with unprefixed SA names.
resource "google_service_account_iam_member" "kafka_workload_identity" {
  for_each = local.kafka_services

  service_account_id = google_service_account.kafka_service[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[llamatrade/${each.key}]"
}

# The staging overlay runs in namespace llamatrade-staging with a staging- prefix
# on every resource name, so its K8s SAs need their own bindings.
resource "google_service_account_iam_member" "kafka_workload_identity_staging" {
  for_each = local.kafka_services

  service_account_id = google_service_account.kafka_service[each.key].name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[llamatrade-staging/staging-${each.key}]"
}

# Topic-scoped publish/subscribe (Kafka ACLs) is expressed via
# google_managed_kafka_acl, which requires the google provider >= 6.x
# (google-beta). Under the pinned "~> 5.0" provider we grant cluster-wide
# roles/managedkafka.client above; tighten to per-topic ACLs when the provider is
# bumped. Example (uncomment after the provider upgrade):
#
# resource "google_managed_kafka_acl" "trading_write_ledger_fills" {
#   acl_id   = "topic/lt.ledger.fills"
#   cluster  = google_managed_kafka_cluster.main.cluster_id
#   location = var.region
#   acl_entries {
#     principal       = "User:${google_service_account.kafka_service["trading"].email}"
#     operation       = "WRITE"
#     permission_type = "ALLOW"
#     host            = "*"
#   }
# }

output "kafka_bootstrap_address" {
  description = "Managed Kafka bootstrap server (SASL_SSL) for KAFKA_BOOTSTRAP_SERVERS"
  value       = "bootstrap.${google_managed_kafka_cluster.main.cluster_id}.${var.region}.managedkafka.${var.project_id}.cloud.goog:9092"
}

output "kafka_service_account_emails" {
  description = "Per-service Managed Kafka client SA emails (for KSA annotations)"
  value       = { for k, sa in google_service_account.kafka_service : k => sa.email }
}
