variable "project_id" {
  type        = string
  description = "GCP project ID to deploy the MCP server into"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid GCP project ID"
  }
}

variable "region" {
  type        = string
  description = "GCP region for Cloud Run and Artifact Registry"
  default     = "europe-west2"
}

variable "name" {
  type        = string
  description = "Base name for all resources (Cloud Run service, SA, repo)"
  default     = "vpcsc-mcp"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,61}[a-z0-9]$", var.name))
    error_message = "name must be lowercase alphanumeric with hyphens, 3-63 characters"
  }
}

variable "image_tag" {
  type        = string
  description = "Container image tag to deploy"
  default     = "latest"
}

variable "invoker_members" {
  type        = list(string)
  description = "IAM members allowed to invoke the MCP server (e.g. 'serviceAccount:agent@project.iam.gserviceaccount.com', 'group:team@example.com')"
  default     = []

  validation {
    condition = alltrue([
      for m in var.invoker_members :
      can(regex("^(serviceAccount|user|group|domain):", m))
    ])
    error_message = "Each member must start with serviceAccount:, user:, group:, or domain:"
  }
}

variable "ingress" {
  type        = string
  description = "Cloud Run ingress setting: INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, or INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  default     = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  validation {
    condition     = contains(["INGRESS_TRAFFIC_ALL", "INGRESS_TRAFFIC_INTERNAL_ONLY", "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"], var.ingress)
    error_message = "ingress must be one of: INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  }
}

variable "vpc_connector_id" {
  type        = string
  description = "Full resource ID of a VPC Access connector for private networking. Leave empty to skip."
  default     = ""
}

variable "min_instances" {
  type        = number
  description = "Minimum number of Cloud Run instances (0 for scale-to-zero)"
  default     = 0
}

variable "max_instances" {
  type        = number
  description = "Maximum number of Cloud Run instances"
  default     = 5
}

variable "cpu" {
  type        = string
  description = "CPU allocation per container (e.g. '1', '2')"
  default     = "1"
}

variable "memory" {
  type        = string
  description = "Memory allocation per container (e.g. '512Mi', '1Gi')"
  default     = "512Mi"
}

variable "timeout" {
  type        = string
  description = "Request timeout in seconds"
  default     = "300s"
}

variable "environment_variables" {
  type        = map(string)
  description = "Additional environment variables to set on the Cloud Run service"
  default     = {}
}

variable "labels" {
  type        = map(string)
  description = "Labels to apply to all resources"
  default     = {}
}

variable "deletion_protection" {
  type        = bool
  description = "Prevent accidental deletion of the Cloud Run service via Terraform"
  default     = true
}

variable "enable_binary_authorization" {
  type        = bool
  description = "Enable Binary Authorization to verify container images before deployment (framework §12.3)"
  default     = true
}

variable "immutable_tags" {
  type        = bool
  description = "Prevent overwriting container image tags in Artifact Registry (supply chain security)"
  default     = true
}

variable "binauthz_attestor_note_id" {
  type        = string
  description = "Container Analysis note ID for the signing attestor. Created if enable_binary_authorization=true."
  default     = "vpcsc-mcp-attestor-note"
}

variable "binauthz_cosign_public_key_pem" {
  type        = string
  description = "Cosign keyless / key-backed public key PEM that signed the image. Required when enable_binary_authorization=true and use_default_binauthz_policy=false."
  default     = ""
  sensitive   = false
}

variable "use_default_binauthz_policy" {
  type        = bool
  description = "If true, use Google's default binauthz policy (permissive). If false, enforce the cosign attestor policy."
  default     = false
}

variable "max_concurrency" {
  type        = number
  description = "Maximum concurrent requests per Cloud Run instance"
  default     = 80
}
