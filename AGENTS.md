# Copilot agents for VPC-SC MCP Server

This file complements `.github/copilot-instructions.md`. Use it to choose the right specialist workflow for a change instead of treating every task as a generic coding session.

## Default operating model

1. Read `.github/copilot-instructions.md` first for architecture, commands, and repo conventions.
2. Route the task by changed area.
3. Run the matching specialist review before finishing, especially for security-sensitive code.

## Recommended specialist agents

| Agent | Use when | Primary files | Expected checks |
|---|---|---|---|
| `code-reviewer` | Any Python change under `src/vpcsc_mcp/` | `src/vpcsc_mcp/**/*.py` | readability, FastMCP patterns, annotations, validation, Ruff-level hygiene |
| `test-runner` | After code changes or when a test is failing | `tests/`, touched source files | `uv run pytest tests/ -v`, failure triage, targeted source lookup |
| `security-scanner` | After edits to command execution, user-input handling, Terraform/YAML generation, or security docs | `src/vpcsc_mcp/tools/safety.py`, `src/vpcsc_mcp/tools/gcloud_ops.py`, `src/vpcsc_mcp/tools/terraform_gen.py`, `src/vpcsc_mcp/tools/rule_gen.py`, `terraform/` | injection review, allowlist enforcement, annotation correctness, secret exposure scan |
| `terraform-reviewer` | Any infrastructure change | `terraform/**/*.tf`, `cloudbuild.yaml`, `Dockerfile` when deployment behavior changes | least privilege, Cloud Run ingress/auth, variable hygiene, provider/version sanity |
| `vpcsc-debugger` | VPC-SC denials, gcloud failures, MCP runtime bugs, transport/startup problems | `src/vpcsc_mcp/server.py`, `src/vpcsc_mcp/tools/gcloud_ops.py`, `src/vpcsc_mcp/tools/analysis.py`, `src/vpcsc_mcp/tools/diagnostic.py`, `src/vpcsc_mcp/data/patterns.py` | trace failing path, isolate root cause, propose minimal fix |
| `gcloud-analyst` | Investigating perimeter layouts, access levels, service support, or method selector behavior | `src/vpcsc_mcp/data/services.py`, `src/vpcsc_mcp/data/patterns.py`, VPC-SC docs-related code | service/method-selector reasoning, VPC-SC rule semantics |
| `doc-maintainer` | Tool/resource/prompt counts or examples may have drifted | `README.md`, `docs/`, `.github/copilot-instructions.md`, `CLAUDE.md`, `examples/` | count reconciliation, example validity, stale docs detection |
| `dependency-manager` | Dependency upkeep, CVE response, lockfile questions | `pyproject.toml`, `uv.lock` | version constraints, outdated packages, vulnerability review |
| `ci-monitor` | GitHub Actions, Docker builds, or Cloud Build are failing | `.github/workflows/`, `Dockerfile`, `cloudbuild.yaml` | failing step analysis, build-system fixes |
| `infra-auditor` | Periodic Terraform/security review or pre-deployment audit | `terraform/`, deployment docs | compliance, drift risk, IAM/network posture |
| `release-coordinator` | Preparing a versioned release | `CHANGELOG.md`, `pyproject.toml`, release-related docs | changelog, version bump, release notes, validation checklist |

## Path-based routing

| Changed area | Primary agent | Also involve |
|---|---|---|
| `src/vpcsc_mcp/tools/safety.py` or `src/vpcsc_mcp/tools/gcloud_ops.py` | `security-scanner` | `code-reviewer`, `test-runner` |
| Other `src/vpcsc_mcp/**/*.py` | `code-reviewer` | `test-runner` |
| `src/vpcsc_mcp/tools/diagnostic.py` or `analysis.py` | `vpcsc-debugger` | `gcloud-analyst`, `test-runner` |
| `src/vpcsc_mcp/tools/terraform_gen.py` or `rule_gen.py` | `security-scanner` | `code-reviewer`, `test-runner` |
| `terraform/**` | `terraform-reviewer` | `infra-auditor`, `ci-monitor` if deployment changed |
| `README.md`, `docs/**`, `.github/copilot-instructions.md`, `CLAUDE.md` | `doc-maintainer` | `code-reviewer` if code examples changed |
| `pyproject.toml`, `uv.lock` | `dependency-manager` | `test-runner` |
| `.github/workflows/**`, `cloudbuild.yaml`, `Dockerfile` | `ci-monitor` | `terraform-reviewer` if infra behavior changed |

## Repo-specific handoff rules

- Changes to `tools/safety.py` or `tools/gcloud_ops.py` should be treated as security-sensitive. Preserve the gcloud allowlist model, subprocess list-arg execution, output sanitisation, and preview-first write behavior.
- Changes that alter tool, resource, prompt, or supported-service counts usually require a doc pass across `README.md`, `docs/`, and `CLAUDE.md`, not just code changes.
- `diagnostic.py` and `analysis.py` often look similar but serve different data sources: diagnostics pull live GCP state; most analysis helpers use static catalogs in `data/`.
- `terraform_gen.py` is not just templating; it also enforces input validation and supports optional file writes through `_maybe_write_hcl()`. Avoid adding parallel file-output patterns elsewhere.
- When a task touches transport or deployment startup behavior, re-check `server.py` assumptions around `VPCSC_MCP_TRANSPORT`, `K_SERVICE`, localhost binding, and `/health`.

## Validation expectations by agent type

| Agent | Minimum validation it should expect |
|---|---|
| `code-reviewer` | read diff, inspect touched Python files, confirm annotations/validation patterns remain consistent |
| `test-runner` | `uv run pytest tests/ -v` or a narrower failing target |
| `security-scanner` | grep or read for `shell=True`, allowlist drift, unsafe interpolation, secret leakage patterns |
| `terraform-reviewer` | `terraform validate` / `terraform fmt -check` when safe, plus IAM and ingress review |
| `doc-maintainer` | compare actual `@mcp.tool`, `@mcp.resource`, `@mcp.prompt`, and service counts against docs |
| `release-coordinator` | inspect git history since last tag, update version/changelog, then lint/test/build steps |

## Good combinations

- **Normal Python feature/fix:** `code-reviewer` + `test-runner`
- **Security-sensitive tooling change:** `security-scanner` + `code-reviewer` + `test-runner`
- **Terraform/deployment change:** `terraform-reviewer` + `infra-auditor` + `ci-monitor`
- **Docs drift after feature work:** `doc-maintainer` + `test-runner` if examples changed
- **Release prep:** `release-coordinator` + `dependency-manager` + `doc-maintainer`
