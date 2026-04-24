# Contributing to VPC-SC MCP Server

Thanks for your interest in contributing! This project welcomes bug reports, feature requests, documentation improvements, and code contributions.

## Getting started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- [gcloud CLI](https://cloud.google.com/sdk/docs/install) (for integration testing)
- A Google Cloud project with VPC Service Controls API enabled (for integration testing)

### Development setup

```bash
# Clone your fork
git clone https://github.com/<your-username>/mcp-vpcsc.git
cd mcp-vpcsc

# Install all dependencies (including dev extras)
uv sync --frozen --extra dev

# Install git hooks — runs ruff, gitleaks, actionlint, hadolint, terraform fmt,
# shellcheck, the gcloud allowlist drift check, and more on every commit.
uv run pre-commit install --install-hooks

# Verify everything works
uv run pre-commit run --all-files
uv run pytest tests/ -v
```

Slow hooks (full pytest, allowlist drift) run in the `manual` stage so they do
not slow down every commit. Exercise them before opening a PR:

```bash
uv run pre-commit run --hook-stage manual --all-files
```

### Running the server locally

```bash
# stdio transport (for MCP clients like Claude Desktop, Gemini CLI)
uv run vpcsc-mcp

# Verify the import works
uv run python -c "from vpcsc_mcp.server import mcp; print(mcp.name)"
```

## Finding something to work on

- Look for issues labelled [`good first issue`](https://github.com/erayguner/mcp-vpcsc/labels/good%20first%20issue) — these are scoped, well-described tasks suitable for newcomers.
- Issues labelled [`help wanted`](https://github.com/erayguner/mcp-vpcsc/labels/help%20wanted) are open for external contribution.
- If you have an idea that isn't tracked yet, [open a feature request](https://github.com/erayguner/mcp-vpcsc/issues/new?template=feature_request.yml) first so we can discuss scope before you invest time coding.

## Making changes

1. **Fork** the repository and create a feature branch from `main`:
   ```bash
   git checkout -b feat/my-change
   ```
2. Make your changes in **small, focused commits**.
3. **Run the checks** before pushing:
   ```bash
   uv run ruff check src/ tests/        # lint
   uv run ruff check --fix src/ tests/   # auto-fix lint issues
   uv run pytest tests/ -v               # tests
   ```
4. **Open a pull request** against `main`. Fill in the PR template — it includes a security checklist.

## Adding a new tool

1. Add the tool function in the appropriate module under `src/vpcsc_mcp/tools/`.
2. Include `ToolAnnotations` — every tool **must** declare `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint`.
3. Destructive tools must require `confirm=True` to execute (preview by default).
4. If the tool invokes `gcloud`, only use allowed subcommands and flags defined in `tools/safety.py` (`ALLOWED_SUBCOMMANDS`, `ALLOWED_FLAGS`). Do **not** widen the allowlist without discussion.
5. Add tests in `tests/`.
6. Update `CHANGELOG.md` under an `[Unreleased]` section.

## Code style

- **Linter:** [Ruff](https://docs.astral.sh/ruff/) — rules `E`, `F`, `I`, `W`
- **Line length:** 120 characters
- **Target:** Python 3.13
- **Formatting:** Follow existing patterns in the codebase

Run `uv run ruff check src/ tests/` to check and `uv run ruff check --fix src/ tests/` to auto-fix.

## Commit messages

Write clear, imperative-mood commit messages:

```
Add perimeter validation tool
Fix audit log query date range handling
Update Terraform output format for bridge rules
```

Prefix with the area when helpful: `tools:`, `terraform:`, `docs:`, `ci:`.

## Pull request process

1. PRs require **passing CI** (lint + tests on Python 3.13 and 3.14, Docker build).
2. PRs are reviewed by a [code owner](https://github.com/erayguner/mcp-vpcsc/blob/main/.github/CODEOWNERS).
3. Expect a first response within **a few days**. Complex PRs may take longer.
4. Maintainers may request changes — this is normal and collaborative.
5. Once approved, a maintainer will merge your PR.

## Security considerations

This server executes `gcloud` CLI commands — security is critical:

- **Never** bypass the command allowlist or argument validation in `tools/safety.py`.
- **Never** use `shell=True` in subprocess calls.
- **Always** sanitise tool output (see `safety.sanitise_output`).
- If your change touches `gcloud_ops.py`, `safety.py`, or `terraform_gen.py`, the security checklist in the PR template is mandatory.

See [Security and Governance](docs/security.md) for the full threat model.

## Reporting issues

Use the [issue templates](https://github.com/erayguner/mcp-vpcsc/issues/new/choose) to report bugs or request features.

## Security vulnerabilities

If you discover a security vulnerability, **do not** open a public issue. Follow the [security policy](SECURITY.md) for responsible disclosure.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
