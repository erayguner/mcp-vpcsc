# Contributing to VPC-SC MCP Server

Thanks for your interest in contributing! This guide covers everything you need to get started.

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager
- A Google Cloud project (for integration testing)

## Development setup

```bash
# Clone the repository
git clone https://github.com/erayguner/mcp-vpcsc.git
cd mcp-vpcsc

# Install dependencies
uv sync --dev

# Run linting
uv run ruff check src/ tests/

# Run tests
uv run pytest
```

## Making changes

1. Fork the repository and create a feature branch from `main`.
2. Make your changes in small, focused commits.
3. Ensure linting and tests pass before pushing.
4. Open a pull request against `main`.

## Adding a new tool

1. Add the tool function in the appropriate module under `src/vpcsc_mcp/`.
2. Include `ToolAnnotations` — every tool must declare `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint`.
3. Destructive tools must require `confirm=True` to execute.
4. If the tool invokes `gcloud`, only use allowed subcommands and flags (see `ALLOWED_SUBCOMMANDS` and `ALLOWED_FLAGS` in the source).
5. Add tests in `tests/`.

## Code style

- **Linter:** [Ruff](https://docs.astral.sh/ruff/) — rules E, F, I, W
- **Line length:** 120 characters
- **Target:** Python 3.10

Run `uv run ruff check src/ tests/` to check and `uv run ruff check --fix src/ tests/` to auto-fix.

## Commit messages

Write clear, imperative-mood commit messages:

```
Add perimeter validation tool
Fix audit log query date range handling
Update Terraform output format for bridge rules
```

## Reporting issues

Use the [issue templates](https://github.com/erayguner/mcp-vpcsc/issues/new/choose) to report bugs or request features.

## Security

If you discover a security vulnerability, please follow the [security policy](SECURITY.md) for responsible disclosure. Do **not** open a public issue.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
