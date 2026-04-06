# Copilot instructions for VPC-SC MCP Server

## Build, test, and lint commands

```bash
# Install dev dependencies
uv sync --frozen --extra dev

# Run the server locally (stdio transport)
uv run vpcsc-mcp

# Run the full test suite
uv run pytest tests/ -v

# Run one focused test file
uv run pytest tests/test_safety.py -v

# Run one test
uv run pytest tests/test_safety.py::TestValidateGcloudArgs::test_blocked_flag -v

# Lint
uv run ruff check src/ tests/

# Auto-fix lint issues
uv run ruff check --fix src/ tests/

# Smoke check the package import / entrypoint wiring
uv run python -c "from vpcsc_mcp.server import mcp; print(mcp.name)"

# Build the container image
docker build -t vpcsc-mcp:test .
```

## High-level architecture

- `src/vpcsc_mcp/server.py` is the composition root. It creates the `FastMCP` server, registers every tool module, exposes the 6 resources and 3 prompts, adds the `/health` route, and selects transport/bind host from `VPCSC_MCP_TRANSPORT`, `PORT`, and `K_SERVICE`. The sixth resource, `vpcsc://server/metrics`, exposes runtime observability state.
- The server is organized by domain-specific registration modules under `src/vpcsc_mcp/tools/`. Each module exports a `register_*_tools(mcp)` function and owns one slice of behavior: live `gcloud` operations, Terraform generation/validation, analysis helpers, ingress/egress YAML generation, project diagnostics, and org-policy diagnostics.
- `src/vpcsc_mcp/tools/safety.py` is the shared security layer. Tool annotations, prompt-injection sanitisation, sensitive-data redaction, the `gcloud` subcommand/flag allowlists, and argument validation all live there and are reused across tool modules.
- `src/vpcsc_mcp/tools/observability.py` is the shared runtime layer. It provides structured audit logging, a 5-minute TTL cache for read-only `gcloud` queries, semaphore-based rate limiting, and per-tool metrics. `gcloud_ops.py` applies all of that inside `run_gcloud()`.
- `src/vpcsc_mcp/tools/gcloud_ops.py` is the only place live `gcloud` subprocess execution should be centralized. It powers both perimeter/policy operations and the live service-introspection tools (`list_supported_services_live`, `describe_supported_service`) instead of letting each tool spawn its own subprocess path.
- `src/vpcsc_mcp/tools/terraform_gen.py` is generation plus validation. The generators validate identifiers and service formats before producing HCL, `validate_terraform` writes temp files with a provider stub and runs `terraform init` / `validate` / `fmt -check`, and `_maybe_write_hcl()` centralizes optional `.tf` file output.
- `src/vpcsc_mcp/tools/diagnostic.py` is the most orchestration-heavy module. `diagnose_project()` chains many `gcloud` reads, correlates enabled APIs against the built-in service catalog, and reports progress through MCP context when available. `analysis.py` and `rule_gen.py` are mostly the curated knowledge layer on top of static catalogs.
- `src/vpcsc_mcp/data/services.py`, `patterns.py`, and `policies.py` are static catalogs that feed tools, resources, prompts, docs, and tests. The test suite is split by concern: `tests/test_server.py` for data/server contracts, `tests/test_safety.py` for validation/redaction, and `tests/test_observability.py` for cache/rate-limit/audit behavior.
- `terraform/` is the deployable Cloud Run infrastructure, while `examples/` contains optional Google ADK clients that exercise the MCP server rather than core server behavior.

## Important runtime flows

- **Live GCP reads/writes:** tool -> `run_gcloud()` -> allowlist/arg validation -> cache lookup -> rate limiter -> `gcloud ... --format=json` -> sanitise/redact output -> parsed response -> audit log + metrics -> formatted MCP output. If a new tool needs `gcloud`, it should reuse this path instead of spawning its own subprocess logic.
- **Destructive updates:** only `update_perimeter_resources` and `update_perimeter_services` modify live infrastructure. Both follow a preview-first flow and require `confirm=True` before execution.
- **Terraform generation:** generators return HCL text by default, but some can also write `.tf` files when `project_name` is provided. That file-writing behavior lives in `_maybe_write_hcl()`, so changes to output naming conventions should stay centralized there.
- **Static guidance vs live service discovery:** built-in catalogs in `data/` power fast curated guidance and method-selector presets, while `list_supported_services_live` and `describe_supported_service` query Access Context Manager for canonical current service metadata. Choose the source intentionally.
- **Resource responses:** built-in resources include `_meta` blocks with version/source/quality hints, while `vpcsc://server/metrics` reports runtime cache, rate-limiter, uptime, and per-tool metrics from the observability singletons.
- **Diagnostics and analysis:** diagnostics use live `gcloud` data; most analysis tools use static catalogs, with `check_data_freshness()` acting as the bridge that compares built-in knowledge against live project state.

## Key conventions

- Treat security constraints as product behavior, not implementation detail. If you change `tools/safety.py` or `tools/gcloud_ops.py`, preserve the allowlist model and do not widen allowed commands or flags casually.
- New `gcloud`-backed behavior should go through `run_gcloud()` so validation, sanitisation/redaction, caching, rate limiting, audit logging, and metrics stay consistent. Do not add parallel subprocess helpers for live GCP calls.
- New MCP tools should follow the existing registration pattern: define them inside the appropriate `register_*_tools(mcp)` function and annotate them with the preset `ToolAnnotations` from `tools/safety.py` (`READONLY_GCP`, `WRITE_GCP`, `GENERATE`, `DIAGNOSTIC`).
- Destructive `gcloud` tools are preview-first. Follow the existing pattern where the tool explains the pending change and only executes against GCP when `confirm=True`.
- Keep tool outputs client-friendly. Existing tools generally return formatted strings or JSON-formatted text for MCP consumers rather than exposing raw internal objects or raw subprocess payloads.
- Built-in resources carry `_meta` metadata, and server/runtime observability lives behind `vpcsc://server/metrics`. If you add a new resource, match that split instead of mixing runtime state into the static knowledge resources.
- The codebase prefers explicit validation over permissive defaults. Examples: Terraform generators reject invalid identifiers and non-numeric policy/project IDs, access-level generation refuses to emit an open rule with no conditions, and write tools validate project/service formats before execution.
- Preserve the split between static knowledge and live queries. Service support, method selectors, troubleshooting guidance, common patterns, and org-policy baselines are intended to live in `data/`; operational state should come from `gcloud`.
- Public counts and versioned claims are repeated across docs and code surfaces. If you add/remove tools, resources, or prompts, update `README.md`, `CLAUDE.md`, `.github/copilot-instructions.md`, `docs/architecture.md`, the startup log in `server.py`, and the `/health` response.
- Tests are split by layer now: `tests/test_server.py` for data/resources/import wiring, `tests/test_safety.py` for allowlists/redaction/sanitisation, and `tests/test_observability.py` for cache/rate-limiter/audit behavior. Update the focused suite that matches the layer you change.
- `ToolAnnotations` are mandatory for every MCP tool in this repo. CONTRIBUTING.md explicitly calls out `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint`, and the repo already centralizes those combinations in `tools/safety.py`.
- Be careful with file-writing behavior in generator tools. Most MCP tools are text-returning helpers, but Terraform generators can write files into the current working directory or a caller-provided `output_dir`; avoid introducing new implicit writes outside `_maybe_write_hcl()`.
- When adding a tool or changing a public capability, follow the project’s contributor workflow from `CONTRIBUTING.md`: update tests, keep the security model intact, and add an `[Unreleased]` entry in `CHANGELOG.md`.
- `AGENTS.md` captures the repo’s path-based specialist routing. For example, changes under `tools/safety.py` / `tools/gcloud_ops.py` are treated as security-scanner territory, while general Python changes under `src/vpcsc_mcp/` should still satisfy the code-reviewer/test-runner expectations.
- Transport behavior matters for deployment changes. `server.py` is written to support local `stdio`, local/remote HTTP, and Cloud Run without code branching elsewhere; if you touch startup or binding behavior, preserve the `VPCSC_MCP_TRANSPORT` / `K_SERVICE` conventions.

## Source-of-truth files

- `README.md`: product-level overview, public counts, security/observability claims, layout summary, and setup commands.
- `CONTRIBUTING.md`: contributor-facing requirements such as mandatory tool annotations and security expectations for new `gcloud` tools.
- `CLAUDE.md`: the strongest repo-specific AI assistant guidance checked in; it captures security-sensitive modules, expected validation steps, and project-specific subagents/maintenance skills.
- `AGENTS.md`: path-based specialist routing for security, infrastructure, docs, dependency, CI, and release changes.
- `docs/security.md`: detailed explanation of the security model, including redaction, caching, rate limiting, and why `gcloud` execution is centralized and restricted.
- `docs/architecture.md`: the clearest cross-file explanation of transport, server composition, validation flow, observability, and Cloud Run deployment shape.
