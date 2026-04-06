# Copilot instructions for VPC-SC MCP Server

## Build, test, and lint commands

```bash
# Install dev dependencies
uv sync --frozen --extra dev

# Run the full test suite
uv run pytest tests/ -v

# Run one test file
uv run pytest tests/test_server.py -v

# Run one test
uv run pytest tests/test_server.py::TestSupportedServices::test_services_not_empty -v

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

- `src/vpcsc_mcp/server.py` is the composition root. It creates the `FastMCP` server, registers every tool module, exposes the 5 resources and 3 prompts, performs startup checks in the lifespan hook, and selects transport from `VPCSC_MCP_TRANSPORT`. Local HTTP binds to `127.0.0.1`; Cloud Run uses `K_SERVICE` and exposes `/health`.
- The server is organized by domain-specific registration modules under `src/vpcsc_mcp/tools/`. Each module exports a `register_*_tools(mcp)` function and owns one slice of behavior: live `gcloud` operations, Terraform generation/validation, analysis helpers, ingress/egress YAML generation, project diagnostics, and org-policy diagnostics.
- `src/vpcsc_mcp/tools/safety.py` is the shared security layer. Tool annotations, output sanitisation, the `gcloud` subcommand/flag allowlists, and argument validation all live there and are reused across tool modules.
- `src/vpcsc_mcp/tools/gcloud_ops.py` is the only place live `gcloud` subprocess execution should be centralized. Those calls go through `run_gcloud()`, which validates args, uses `asyncio.create_subprocess_exec` (never `shell=True`), appends `--format=json`, and enforces the 120-second timeout.
- `src/vpcsc_mcp/tools/terraform_gen.py` is pure generation plus validation. The generators validate identifiers and service formats before producing HCL, and `validate_terraform` writes temp files with a provider stub, then runs `terraform init`, `terraform validate`, and `terraform fmt -check` in a scratch directory.
- `src/vpcsc_mcp/tools/diagnostic.py` is the most orchestration-heavy module. `diagnose_project()` is effectively a guided readiness scan that chains many `gcloud` reads, correlates enabled APIs against the supported-services catalog, reports progress through MCP context when available, and returns a structured text report with status markers and action hints.
- `src/vpcsc_mcp/tools/analysis.py` and `rule_gen.py` sit on top of the static data catalogs rather than querying GCP directly for most operations. They are the "knowledge layer": violation explanations, workload-based service recommendations, method-selector guidance, and reusable ingress/egress templates.
- `src/vpcsc_mcp/data/services.py`, `patterns.py`, and `policies.py` are static catalogs that feed tools, resources, prompts, docs, and tests. A lot of the current test coverage validates those datasets and the formatting helpers around them.
- `terraform/` is the deployable Cloud Run infrastructure, while `examples/` contains optional Google ADK clients that exercise the MCP server rather than core server behavior.

## Important runtime flows

- **Live GCP reads/writes:** tool -> `run_gcloud()` -> allowlist/arg validation -> `gcloud ... --format=json` -> parsed response -> formatted MCP output. If a new tool needs `gcloud`, it should reuse this path instead of spawning its own subprocess logic.
- **Destructive updates:** only `update_perimeter_resources` and `update_perimeter_services` modify live infrastructure. Both follow a preview-first flow and require `confirm=True` before execution.
- **Terraform generation:** generators return HCL text by default, but some can also write `.tf` files when `project_name` is provided. That file-writing behavior lives in `_maybe_write_hcl()`, so changes to output naming conventions should stay centralized there.
- **Rule generation:** ingress/egress YAML generators normalize service names to `*.googleapis.com`, pull selector presets from `SERVICE_METHOD_SELECTORS`, and default to `{"method": "*"}` when no per-service preset exists.
- **Diagnostics and analysis:** diagnostics use live `gcloud` data; most analysis tools use static catalogs. When a result seems stale, check whether the source of truth is a data module or a live command before changing behavior.

## Key conventions

- Treat security constraints as product behavior, not implementation detail. If you change `tools/safety.py` or `tools/gcloud_ops.py`, preserve the allowlist model and do not widen allowed commands or flags casually.
- New MCP tools should follow the existing registration pattern: define them inside the appropriate `register_*_tools(mcp)` function and annotate them with the preset `ToolAnnotations` from `tools/safety.py` (`READONLY_GCP`, `WRITE_GCP`, `GENERATE`, `DIAGNOSTIC`).
- Destructive `gcloud` tools are preview-first. Follow the existing pattern where the tool explains the pending change and only executes against GCP when `confirm=True`.
- Keep tool outputs client-friendly. Existing tools generally return formatted strings or JSON-formatted text for MCP consumers rather than exposing raw internal objects or raw subprocess payloads.
- The codebase prefers explicit validation over permissive defaults. Examples: Terraform generators reject invalid identifiers and non-numeric policy/project IDs, access-level generation refuses to emit an open rule with no conditions, and write tools validate project/service formats before execution.
- Preserve the split between static knowledge and live queries. Service support, method selectors, troubleshooting guidance, common patterns, and org-policy baselines are intended to live in `data/`; operational state should come from `gcloud`.
- The server-level counts in docs are intentional and repeated in several places. If you add/remove tools, resources, or prompts, update the counts and descriptions in `README.md`, `CLAUDE.md`, and docs that reference them.
- The current tests are concentrated in `tests/test_server.py` and mostly verify static catalogs plus small formatting helpers such as `_hcl_list`. When changing services, patterns, troubleshooting entries, or workload presets, update the existing expectations there.
- `ToolAnnotations` are mandatory for every MCP tool in this repo. CONTRIBUTING.md explicitly calls out `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint`, and the repo already centralizes those combinations in `tools/safety.py`.
- Be careful with file-writing behavior in generator tools. Most MCP tools are text-returning helpers, but Terraform generators can write files into the current working directory or a caller-provided `output_dir`; avoid introducing new implicit writes outside that pattern.
- Transport behavior matters for deployment changes. `server.py` is written to support local `stdio`, local/remote HTTP, and Cloud Run without code branching elsewhere; if you touch startup or binding behavior, preserve the `VPCSC_MCP_TRANSPORT` / `K_SERVICE` conventions.

## Source-of-truth files

- `README.md`: product-level overview, public counts, layout summary, setup commands.
- `CONTRIBUTING.md`: contributor-facing requirements such as mandatory tool annotations and security expectations for new `gcloud` tools.
- `CLAUDE.md`: the most repository-specific AI assistant guidance currently checked in; it contains strong guardrails around security-sensitive modules, expected validation steps, and when to use project-specific subagents.
- `docs/security.md`: detailed explanation of the security model, including why `gcloud` execution is centralized and restricted.
- `docs/architecture.md`: the clearest cross-file explanation of transport, server composition, validation flow, and Cloud Run deployment shape.
