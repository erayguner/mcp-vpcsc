variable "project_id" {
  type        = string
  description = "GCP project ID to deploy into"
}

variable "region" {
  type        = string
  description = "GCP region"
  default     = "europe-west2"
}

variable "name" {
  type        = string
  description = "Base name for all resources"
  default     = "vpcsc-mcp"
}

variable "ingress" {
  type        = string
  description = "Cloud Run ingress: INGRESS_TRAFFIC_ALL, INGRESS_TRAFFIC_INTERNAL_ONLY, INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"
  default     = "INGRESS_TRAFFIC_INTERNAL_ONLY"
}

variable "invoker_members" {
  type        = list(string)
  description = "IAM members who can invoke the MCP server"
  default     = []
}

variable "vpc_connector_id" {
  type        = string
  description = "VPC Access connector resource ID (leave empty to skip)"
  default     = ""
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 5
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "enable_binary_authorization" {
  type    = bool
  default = false
}

variable "immutable_tags" {
  type    = bool
  default = false
}
