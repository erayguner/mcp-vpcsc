# VPC-SC MCP Server

[![CI](https://github.com/erayguner/mcp-vpcsc/actions/workflows/ci.yml/badge.svg)](https://github.com/erayguner/mcp-vpcsc/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![MCP SDK](https://img.shields.io/badge/MCP_SDK-1.26.0-green.svg)](https://pypi.org/project/mcp/)
[![Tools](https://img.shields.io/badge/tools-43-brightgreen.svg)](docs/mcp-server-guide.md)
[![GCP Services](https://img.shields.io/badge/GCP_services-219-informational.svg)](src/vpcsc_mcp/data/services.py)
[![Ruff](https://img.shields.io/badge/linting-ruff-orange.svg)](https://docs.astral.sh/ruff/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](Dockerfile)
[![uv](https://img.shields.io/badge/uv-package_manager-blueviolet.svg)](https://docs.astral.sh/uv/)

An MCP server that helps AI agents and developers set up, manage, and troubleshoot Google Cloud VPC Service Controls and Organisation Policies.

Built with Python MCP SDK v1.26.0 (FastMCP). Deployable locally via stdio or remotely on Cloud Run via streamable-http.

## The problem

Google Cloud IAM controls *who* can access resources. But it doesn't control *where data can go*. A stolen service account key, a misconfigured permission, or a malicious insider can copy data from your BigQuery datasets, Cloud Storage buckets, or Vertex AI models to any project on the internet — even with IAM correctly configured.

[VPC Service Controls](https://cloud.google.com/vpc-service-controls/docs/overview) solve this by creating security perimeters around your GCP projects and services. But setting them up is hard:

- **Complex configuration** — perimeters, access levels, ingress/egress rules, method selectors, bridge perimeters, dry-run mode
- **Cryptic errors** — `RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER` doesn't tell you *which* rule to add
- **Silent failures** — use the wrong method selector type (`method` vs `permission`) and your rule does nothing
- **High blast radius** — enforce a perimeter without testing and you can break production workloads instantly
- **219 services** — each with different method selector formats and VPC-SC support details

## How this MCP helps

This server gives you (or your AI agent) 43 tools that automate the hard parts:

| Instead of... | The MCP does... |
|---|---|
| Manually checking which APIs are unprotected | `diagnose_project` scans all enabled APIs and flags `[GAP]` for unprotected ones |
| Reading docs to figure out which services to restrict | `recommend_restricted_services` gives a tailored list per workload type |
| Writing Terraform from scratch | `generate_perimeter_terraform` produces validated HCL with the right structure |
| Guessing whether to use `method` or `permission` selectors | `get_method_selectors` returns the correct format for each service |
| Decoding violation error messages | `troubleshoot_violation` explains the root cause and resolution steps |
| Checking 31 org policies one by one | `diagnose_org_policies` scans all of them and classifies compliance status |

**New to VPC-SC?** Start with [VPC-SC Concepts](docs/concepts.md) to understand the building blocks, then follow the [Getting Started](docs/getting-started.md) guide.

**Already know VPC-SC?** Jump to [Use Cases](docs/use-cases.md) for practical scenarios, or the [MCP Server Guide](docs/mcp-server-guide.md) for the full tool reference.

## What it does

| Category | Tools | Examples |
|---|---|---|
| **gcloud operations** | 14 | List perimeters, query audit logs, list/enforce dry-run configs, update resources/services |
| **Terraform generation** | 10 | Generate HCL for perimeters, access levels, bridges, ingress/egress rules, validate output |
| **Analysis** | 9 | Troubleshoot violations, recommend services by workload, validate identities, explain method selectors, check data freshness |
| **Rule generation** | 6 | Produce YAML for gcloud (roles / externalResources / sourceRestriction), apply pre-built patterns for BigQuery/Storage/Vertex AI |
| **VPC-SC diagnostics** | 2 | Project readiness scan with protection gap analysis, implementation guide with Terraform |
| **Org policy diagnostics** | 2 | Org policy compliance scan (COMPLIANT/NON-COMPLIANT/NOT SET), Terraform generator |
| **Operator halt / resume / status** | 3 | Kill-switch — halt all tool calls or a specific principal/tool in under a minute |
| **Resources** | 6 | Supported services list, workload guides, common patterns, server metrics (cache / breaker / audit / halts) |
| **Prompts** | 3 | Perimeter design, troubleshoot denial, migration planning |

**43 tools, 6 resources, 3 prompts.** All 43 tools carry MCP `ToolAnnotations` (36 read-only, 4 destructive write, 1 destructive halt, 2 idempotent override).

## Security and governance

- **Command allowlist** — only 9 gcloud subcommands and 12 gcloud flags permitted; `allowlist-drift` CI job fails PRs that widen the set without updating the baseline
- **Argument validation** — shell metacharacters and privilege-escalation flags rejected
- **Caller-input filter** — secrets (GCP SA, OAuth, GitHub/Slack tokens, AWS keys) and prompt-injection directives are **blocked** in free-text tool args; PII is redacted
- **Write operations require confirmation** — all 4 write tools preview by default, `confirm=True` to execute
- **Tool annotations** — every tool declares `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`
- **Output sanitisation** — strips prompt-injection patterns and redacts private keys/tokens from tool results
- **Per-principal rate limiting** — each caller capped at 3 concurrent gcloud calls + shared global cap of 5
- **Circuit breaker** — opens after 5 consecutive gcloud failures; `/health` reports breaker state and returns 503 when open
- **Kill-switch** — `halt_session` tool halts in-flight calls in <1 min without restart; scoped `global` / `principal:<id>` / `tool:<name>`
- **Chained audit log** — every tool call / halt / override carries SHA-256 chain + HMAC daily manifest; strict chain verification on load; `export_signed` for forensic bundles
- **Dead-letter queue** — audit writes that fail transiently land in a replayable DLQ, not lost
- **Result caching** — read-only gcloud queries cached for 5 minutes to prevent redundant calls
- **Non-root container** — runs as UID 1001
- **Read-only SA** — no write roles for Access Context Manager
- **Binary Authorization + cosign signing** — Cloud Run module provisions attestor + scoped policy; CI signs images keyless and pushes SLSA provenance attestations; unsigned images rejected on admission
- **Immutable AR tags, Trivy container scan, tflint + tfsec** — supply-chain gates in CI
- **Optional OTel Cloud Monitoring exporter** — per-tool / per-principal call metrics
- **Lifespan checks** — validates gcloud CLI at startup; graceful shutdown on SIGTERM
- **Health endpoint** — `/health` returns 503 when breaker is open or any halt is active
- **Localhost binding** — HTTP transport binds to 127.0.0.1 locally; 0.0.0.0 only on Cloud Run
- **120s command timeout** — hung gcloud processes killed automatically

See [Security and Governance](docs/security.md) for the full threat model and controls.

## Project layout

```
src/vpcsc_mcp/
  server.py                 FastMCP server, lifespan, health check, resources, prompts
  tools/
    gcloud_ops.py           gcloud CLI tools with allowlist, validation, caching, rate limiting
    terraform_gen.py        Terraform HCL generators, input validation, terraform validate
    analysis.py             Troubleshooting, recommendations, validation, data freshness
    rule_gen.py             Ingress/egress YAML and pattern library
    diagnostic.py           VPC-SC project diagnostics + implementation guide
    org_policy.py           Org policy compliance scan + Terraform generator
    safety.py               Tool annotations, output sanitisation, data redaction
    observability.py        Audit logging, result caching, rate limiting, tool metrics
  data/
    services.py             219 supported services, 7 workload recommendations, method selectors
    patterns.py             Pre-built ingress/egress patterns, troubleshooting guide

terraform/                  Cloud Run deployment (Terraform >= 1.14, Google provider ~> 7.0)
  modules/mcp-server/       Reusable module: Cloud Run + SA + Artifact Registry + IAM + monitoring

examples/
  adk-agent/                Google ADK single agent (all 43 tools)
  adk-multi-agent/          Google ADK multi-agent (4 specialists + coordinator)

scripts/
  cloudshell-setup.sh       One-command Cloud Shell setup
  run-diagnostic.py         Direct diagnostic CLI (no LLM needed)

tests/                      65 tests
docs/                       9 documents (concepts, use-cases, getting-started, 3 runbooks, guide, security, architecture)
Dockerfile                  Python 3.14 + gcloud, non-root
cloudbuild.yaml             CI/CD: build, push, deploy
```

## Key versions

| Component | Version |
|---|---|
| Python | >= 3.13 |
| MCP SDK (`mcp`) | 1.26.0 |
| Terraform | >= 1.14 |
| Google provider | ~> 7.0 (7.24.0) |
| Google ADK (`google-adk`) | >= 1.27.0 (optional) |

## Getting started

**First time?** Start here: **[Getting Started](docs/getting-started.md)** — 3 paths (local, Cloud Shell, Cloud Run), all under 5 minutes.

| Environment | Guide | Time |
|---|---|---|
| Local + Gemini CLI | [Getting Started](docs/getting-started.md#local-setup) | 2 min |
| Cloud Shell + Gemini | [Getting Started](docs/getting-started.md#cloud-shell-setup) | 3 min |
| Cloud Run (production) | [Getting Started](docs/getting-started.md#cloud-run-setup) | 10 min |

## Runbooks (detailed)

| Runbook | For |
|---|---|
| [Local Setup](docs/runbook-local.md) | Full local reference, HTTP transport, ADK agents, troubleshooting |
| [Cloud Shell](docs/runbook-cloudshell.md) | Direct CLI, ADK web/terminal, E2E test, auth details |
| [Cloud Run](docs/runbook-cloud-run.md) | Terraform, build, deploy, security controls, teardown |

## Reference

| Document | Content |
|---|---|
| [VPC-SC Concepts](docs/concepts.md) | What VPC-SC solves, core concepts (perimeters, access levels, ingress/egress, dry-run), how the MCP maps to each |
| [Use Cases](docs/use-cases.md) | 8 practical scenarios: project assessment, new perimeters, troubleshooting, CI/CD, partner access, compliance, migration, cross-perimeter sharing |
| [MCP Server Guide](docs/mcp-server-guide.md) | All 43 tools, validation rules, Terraform module patterns, end-to-end examples |
| [Agent Governance Framework](AGENT_GOVERNANCE_FRAMEWORK.md) | The standard this server implements: tool governor, chained audit, approvals, kill-switch, supply chain |
| [Security](docs/security.md) | Threat model, command allowlists, tool annotations, governance controls |
| [Architecture](docs/architecture.md) | Component diagrams, data flows, deployment patterns, design decisions |

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) before getting started. Look for issues labelled [`good first issue`](https://github.com/erayguner/mcp-vpcsc/labels/good%20first%20issue) if you're new to the project.

## Community

- [Code of Conduct](CODE_OF_CONDUCT.md) — we follow the Contributor Covenant
- [Governance](GOVERNANCE.md) — how decisions are made
- [GitHub Discussions](https://github.com/erayguner/mcp-vpcsc/discussions) — questions, ideas, conversation
- [Support](SUPPORT.md) — where to get help

## Security

Found a vulnerability? **Do not** open a public issue. See [SECURITY.md](SECURITY.md) for responsible disclosure.

## License

[MIT](LICENSE)
