# ─────────────────────────────────────────────────────────────────────────────
# VPC-SC MCP Server — Root Terraform configuration
#
# Deploys the VPC-SC Helper MCP server to Cloud Run with full security:
#   - Internal-only ingress (no public internet access)
#   - IAM-authenticated (no unauthenticated invocations)
#   - Dedicated least-privilege service account
#   - Container images in Artifact Registry
#   - gcloud proxy required for local access
#
# Usage:
#   1. Set variables in terraform.tfvars
#   2. Build and push the container image (see cloudbuild.yaml)
#   3. terraform init && terraform plan && terraform apply
#   4. Connect via: gcloud run services proxy vpcsc-mcp --region=REGION --port=3000
# ─────────────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.14"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }

  # TODO: Configure your remote backend
  # backend "gcs" {
  #   bucket = "your-terraform-state-bucket"
  #   prefix = "vpcsc-mcp"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ─── MCP Server Module ──────────────────────────────────────────────────────

module "mcp_server" {
  source = "./modules/mcp-server"

  project_id = var.project_id
  region     = var.region
  name       = var.name

  # Security: internal-only, no public access
  ingress = var.ingress

  # Who can invoke the MCP server
  invoker_members = var.invoker_members

  # Optional: VPC connector for private networking
  vpc_connector_id = var.vpc_connector_id

  # Scaling
  min_instances = var.min_instances
  max_instances = var.max_instances
  cpu           = var.cpu
  memory        = var.memory

  # Container image
  image_tag = var.image_tag

  # Security hardening
  deletion_protection         = var.deletion_protection
  enable_binary_authorization = var.enable_binary_authorization
  immutable_tags              = var.immutable_tags

  labels = var.labels
}

# ─── Org-level Access Context Manager reader (optional) ─────────────────────
# If the MCP server needs to read access policies at the org level,
# grant the role at the org level instead of the project level.
# Uncomment and set your organization_id.

# resource "google_organization_iam_member" "mcp_acm_reader" {
#   org_id = var.organization_id
#   role   = "roles/accesscontextmanager.policyReader"
#   member = "serviceAccount:${module.mcp_server.service_account_email}"
# }
