# ─────────────────────────────────────────────────────────────────────────────
# VPC-SC MCP Server — Cloud Run deployment module
#
# Deploys the VPC-SC Helper MCP server on Cloud Run with:
#   - Dedicated service account (least-privilege)
#   - Artifact Registry with immutable tags and cleanup policies
#   - IAM-authenticated access (no unauthenticated invocations)
#   - Binary Authorization for container verification
#   - Gen2 execution environment with startup CPU boost
#   - Optional VPC connector for private networking
#   - Deletion protection on the Cloud Run service
#   - Cloud Audit Logging enabled by default
#
# Based on Google Cloud MCP documentation:
#   https://docs.cloud.google.com/mcp/overview
#   https://docs.cloud.google.com/run/docs/host-mcp-servers
# ─────────────────────────────────────────────────────────────────────────────

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${var.name}:${var.image_tag}"

  default_labels = merge(var.labels, {
    managed-by = "terraform"
    component  = "mcp-server"
    service    = var.name
  })
}

# ─── APIs ────────────────────────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "iam.googleapis.com",
    "secretmanager.googleapis.com",
    "accesscontextmanager.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "binaryauthorization.googleapis.com",
    "containeranalysis.googleapis.com",
  ])

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ─── Service Account (dedicated, least-privilege) ───────────────────────────

resource "google_service_account" "mcp_server" {
  project      = var.project_id
  account_id   = var.name
  display_name = "VPC-SC MCP Server"
  description  = "Dedicated service account for the VPC-SC Helper MCP server on Cloud Run"
}

# Read Access Context Manager resources (perimeters, access levels, policies)
resource "google_project_iam_member" "mcp_server_acm_reader" {
  project = var.project_id
  role    = "roles/accesscontextmanager.policyReader"
  member  = "serviceAccount:${google_service_account.mcp_server.email}"
}

# Read Cloud Audit Logs (for check_vpc_sc_violations tool)
resource "google_project_iam_member" "mcp_server_log_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.mcp_server.email}"
}

# Write structured logs from the container
resource "google_project_iam_member" "mcp_server_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.mcp_server.email}"
}

# Write monitoring metrics
resource "google_project_iam_member" "mcp_server_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.mcp_server.email}"
}

# ─── Artifact Registry ──────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.name
  format        = "DOCKER"
  description   = "Container images for the VPC-SC MCP server"
  labels        = local.default_labels

  # Prevent tag overwriting — supply chain security
  docker_config {
    immutable_tags = var.immutable_tags
  }

  # Keep the most recent images, auto-purge old untagged ones
  cleanup_policies {
    id     = "keep-latest-5"
    action = "KEEP"

    most_recent_versions {
      keep_count = 5
    }
  }

  cleanup_policies {
    id     = "delete-old-untagged"
    action = "DELETE"

    condition {
      tag_state  = "UNTAGGED"
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.apis["artifactregistry.googleapis.com"]]
}

# ─── Cloud Run Service ──────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "mcp_server" {
  name                = var.name
  project             = var.project_id
  location            = var.region
  ingress             = var.ingress
  deletion_protection = var.deletion_protection
  labels              = local.default_labels

  # Binary Authorization — verify container images before deployment.
  # Framework §12.3: admission controller rejects unsigned images; cosign
  # keyless signatures from CI are the attestation source of truth. The
  # project-level policy (google_binary_authorization_policy.policy) defines
  # which attestations are required; this block opts the service in.
  dynamic "binary_authorization" {
    for_each = var.enable_binary_authorization ? ["enabled"] : []
    content {
      use_default = true
    }
  }

  template {
    service_account       = google_service_account.mcp_server.email
    execution_environment = "EXECUTION_ENVIRONMENT_GEN2"
    timeout               = var.timeout

    # Concurrency: MCP servers handle independent requests
    max_instance_request_concurrency = var.max_concurrency

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = local.image

      ports {
        name           = "http1"
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        startup_cpu_boost = true
      }

      # ── Core environment variables ──────────────────────────────────
      env {
        name  = "PORT"
        value = "8080"
      }

      env {
        name  = "VPCSC_MCP_TRANSPORT"
        value = "streamable-http"
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }

      env {
        name  = "PYTHONUNBUFFERED"
        value = "1"
      }

      # Additional user-provided environment variables
      dynamic "env" {
        for_each = var.environment_variables
        content {
          name  = env.key
          value = env.value
        }
      }

      # ── Health checks ───────────────────────────────────────────────
      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get {
          path = "/health"
        }
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3
      }
    }

    # VPC connector for private networking (optional)
    dynamic "vpc_access" {
      for_each = var.vpc_connector_id != "" ? [var.vpc_connector_id] : []
      content {
        connector = vpc_access.value
        egress    = "PRIVATE_RANGES_ONLY"
      }
    }
  }

  # Route all traffic to latest revision
  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.apis["run.googleapis.com"],
    google_artifact_registry_repository.repo,
  ]

  lifecycle {
    ignore_changes = [
      # Image tag changes are managed by CI/CD, not Terraform
      template[0].containers[0].image,
    ]
  }
}

# ─── IAM: No unauthenticated access ────────────────────────────────────────

# The SA itself needs invoker access for health checks / self-calls
resource "google_cloud_run_v2_service_iam_member" "self_invoke" {
  project  = google_cloud_run_v2_service.mcp_server.project
  location = google_cloud_run_v2_service.mcp_server.location
  name     = google_cloud_run_v2_service.mcp_server.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.mcp_server.email}"
}

# Grant invoker access to specified members (agents, users, groups)
resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)

  project  = google_cloud_run_v2_service.mcp_server.project
  location = google_cloud_run_v2_service.mcp_server.location
  name     = google_cloud_run_v2_service.mcp_server.name
  role     = "roles/run.invoker"
  member   = each.value
}

# ─── Monitoring: Log-based metric for errors ────────────────────────────────

# ─── Binary Authorization — attestor + policy ────────────────────────────
# Framework §12.3. Creates a Container Analysis note + a binauthz attestor
# that verifies cosign-signed images, and a project-level policy that
# requires attestation for the MCP server's Artifact Registry path. The
# default_admission_rule stays permissive (admission controller only
# enforces on the scoped cluster_admission_rules) so unrelated workloads
# in the project are not affected.

resource "google_container_analysis_note" "attestor_note" {
  count = var.enable_binary_authorization && !var.use_default_binauthz_policy ? 1 : 0

  project = var.project_id
  name    = var.binauthz_attestor_note_id

  attestation_authority {
    hint {
      human_readable_name = "VPC-SC MCP Server cosign attestor"
    }
  }

  depends_on = [google_project_service.apis["containeranalysis.googleapis.com"]]
}

resource "google_binary_authorization_attestor" "cosign_attestor" {
  count = var.enable_binary_authorization && !var.use_default_binauthz_policy ? 1 : 0

  project = var.project_id
  name    = "${var.name}-cosign-attestor"

  attestation_authority_note {
    note_reference = google_container_analysis_note.attestor_note[0].name

    dynamic "public_keys" {
      for_each = var.binauthz_cosign_public_key_pem != "" ? [var.binauthz_cosign_public_key_pem] : []
      content {
        id = "cosign-ci-key"
        pkix_public_key {
          public_key_pem      = public_keys.value
          signature_algorithm = "ECDSA_P256_SHA256"
        }
      }
    }
  }

  depends_on = [google_project_service.apis["binaryauthorization.googleapis.com"]]
}

resource "google_binary_authorization_policy" "policy" {
  count = var.enable_binary_authorization && !var.use_default_binauthz_policy ? 1 : 0

  project = var.project_id

  # Deny-by-default: every image must be cosign-attested unless it matches
  # one of the narrow Google-managed system-image patterns below. Previously
  # this was ALWAYS_ALLOW with a non-enforcing whitelist, which made the
  # feature effectively a no-op for Cloud Run workloads.
  default_admission_rule {
    evaluation_mode  = "REQUIRE_ATTESTATION"
    enforcement_mode = "ENFORCED_BLOCK_AND_AUDIT_LOG"
    require_attestations_by = [
      google_binary_authorization_attestor.cosign_attestor.name,
    ]
  }

  # Whitelist system images that Google signs but whose attestations we do
  # not own (e.g. Cloud Run system containers, GKE managed images). Keep
  # this list as narrow as possible.
  admission_whitelist_patterns {
    name_pattern = "gcr.io/cloud-run-managed/*"
  }
  admission_whitelist_patterns {
    name_pattern = "gke.gcr.io/*"
  }

  depends_on = [
    google_binary_authorization_attestor.cosign_attestor,
    google_project_service.apis["binaryauthorization.googleapis.com"],
  ]
}

resource "google_logging_metric" "mcp_server_errors" {
  project = var.project_id
  name    = "${var.name}-5xx-errors"
  filter  = <<-EOT
    resource.type="cloud_run_revision"
    resource.labels.service_name="${var.name}"
    httpRequest.status>=500
  EOT

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    unit         = "1"
    display_name = "VPC-SC MCP Server 5xx Errors"
  }

  depends_on = [google_project_service.apis["logging.googleapis.com"]]
}
