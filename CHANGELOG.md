# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-23

### Added

- Initial release of VPC-SC MCP Server
- 35 tools with MCP ToolAnnotations (33 read-only, 2 destructive)
- 5 resources (supported services, workload guides, common patterns)
- 3 prompts (perimeter design, troubleshoot denial, migration planning)
- gcloud operations: list perimeters, query audit logs, check dry-run status, update resources/services
- Terraform generation: perimeters, access levels, bridges, ingress/egress rules
- Analysis tools: troubleshoot violations, recommend services, validate identities
- Rule generation: YAML for gcloud, pre-built patterns for BigQuery/Storage/Vertex AI
- VPC-SC diagnostics: project readiness scan, implementation guide
- Org policy diagnostics: compliance scan, Terraform generator
- Command allowlist security model (9 gcloud subcommands, 11 flags)
- Argument validation with shell metacharacter rejection
- Write operations require confirmation
- Output sanitisation against prompt injection
- Docker support with non-root container (UID 1001)
- Cloud Run deployment via streamable-http transport
- CI pipeline with Ruff linting and pytest across Python 3.10/3.12/3.14
