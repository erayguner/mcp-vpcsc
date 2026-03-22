output "service_url" {
  description = "The URL of the deployed Cloud Run MCP server"
  value       = google_cloud_run_v2_service.mcp_server.uri
}

output "mcp_endpoint" {
  description = "The MCP endpoint URL (append /mcp to the service URL)"
  value       = "${google_cloud_run_v2_service.mcp_server.uri}/mcp"
}

output "service_account_email" {
  description = "Email of the dedicated service account"
  value       = google_service_account.mcp_server.email
}

output "artifact_registry_repo" {
  description = "Full name of the Artifact Registry repository"
  value       = google_artifact_registry_repository.repo.id
}

output "image_uri" {
  description = "Full container image URI"
  value       = local.image
}

output "service_name" {
  description = "Cloud Run service name"
  value       = google_cloud_run_v2_service.mcp_server.name
}

output "proxy_command" {
  description = "gcloud command to create a local proxy for the MCP server"
  value       = "gcloud run services proxy ${google_cloud_run_v2_service.mcp_server.name} --region=${var.region} --port=3000"
}

output "gemini_config" {
  description = "Gemini CLI MCP config (use after starting proxy)"
  value = jsonencode({
    mcpServers = {
      "vpcsc-mcp" = {
        url = "http://localhost:3000/mcp"
      }
    }
  })
}
