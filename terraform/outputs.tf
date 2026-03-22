output "service_url" {
  description = "Cloud Run service URL"
  value       = module.mcp_server.service_url
}

output "mcp_endpoint" {
  description = "MCP endpoint URL"
  value       = module.mcp_server.mcp_endpoint
}

output "service_account_email" {
  description = "MCP server service account"
  value       = module.mcp_server.service_account_email
}

output "proxy_command" {
  description = "Command to start a local authenticated proxy"
  value       = module.mcp_server.proxy_command
}

output "gemini_config" {
  description = "Gemini CLI MCP config (use after starting proxy)"
  value       = module.mcp_server.gemini_config
}
