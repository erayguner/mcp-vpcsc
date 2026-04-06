# Copilot skills for VPC-SC MCP Server

These are the most useful reusable skill workflows already reflected in the project's `.claude/skills/` library and `CLAUDE.md`. Use them as task recipes for Copilot sessions in this repository.

## Core maintenance skills

| Skill | Use when | Main commands / checks | Main files involved |
|---|---|---|---|
| `pre-commit-check` | Before committing code changes | `uv run ruff check src/ tests/`, `uv run pytest tests/ -x --tb=short -q`, import smoke check, quick secret/dangerous-pattern scan | `src/`, `tests/`, `pyproject.toml` |
| `health-check` | Periodic maintenance or before larger merges/releases | Ruff, full pytest, Docker build, `uv lock --check`, tool/resource/prompt/service count reconciliation, quick security scan | whole repo |
| `doc-sync` | After adding/removing tools, resources, prompts, services, or examples | count `@mcp.tool`, `@mcp.resource`, `@mcp.prompt`, compare docs claims, inspect examples and Terraform docs | `README.md`, `docs/`, `src/vpcsc_mcp/`, `examples/`, `terraform/` |
| `security-audit` | After changes that touch command execution, validation, or generated infra config | grep subprocess usage, review allowlists, sanitisation, Terraform/YAML escaping, infra exposure checks | `tools/safety.py`, `tools/gcloud_ops.py`, `tools/terraform_gen.py`, `tools/rule_gen.py`, `terraform/` |
| `dep-audit` | Dependency upkeep or pre-release review | `uv lock --check`, `uv run pip list`, `uv run pip-audit`, outdated package review | `pyproject.toml`, `uv.lock` |
| `release-prep` | Before cutting a release | git history since last tag, bump `pyproject.toml`, update `CHANGELOG.md`, run lint/tests/build | `CHANGELOG.md`, `pyproject.toml`, repo root |

## Recommended cadence

| Situation | Skills to run |
|---|---|
| Before a commit to main | `pre-commit-check` |
| After changing tool counts, services, or docs | `doc-sync` |
| After modifying `gcloud` execution, safety, Terraform, or rule generators | `security-audit` |
| Before a release | `release-prep`, `doc-sync`, `security-audit`, `dep-audit` |
| Periodic project maintenance | `health-check`, `dep-audit` |

## Skill playbooks

### `pre-commit-check`

Use for fast confidence on code changes.

```bash
uv run ruff check src/ tests/
uv run pytest tests/ -x --tb=short -q
uv run python -c "from vpcsc_mcp.server import mcp; print(f'Server OK: {mcp.name}')"
```

Repo-specific additions:

- If Python files changed under `src/vpcsc_mcp/`, also review tool annotations and validation boundaries.
- If `tools/safety.py` or `tools/gcloud_ops.py` changed, pair this with `security-audit`.

### `health-check`

Use for broad repo health rather than a narrow feature check.

```bash
uv run ruff check src/ tests/
uv run pytest tests/ -v --tb=short
docker build -t vpcsc-mcp:health-check .
uv lock --check
```

Also reconcile documented counts against code reality:

```bash
grep -c "@mcp.tool" src/vpcsc_mcp/tools/*.py
grep -c "@mcp.resource" src/vpcsc_mcp/server.py
grep -c "@mcp.prompt" src/vpcsc_mcp/server.py
grep -c "googleapis.com" src/vpcsc_mcp/data/services.py
```

Focus on the project's repeated public claims: tool/resource/prompt totals, supported-service count, and security guarantees.

### `doc-sync`

Use after any change that can drift docs from code.

Checklist:

- Compare actual `@mcp.tool`, `@mcp.resource`, and `@mcp.prompt` counts with `README.md`, `CLAUDE.md`, and docs.
- Compare supported-service totals in `src/vpcsc_mcp/data/services.py` with docs.
- Check `examples/adk-agent/` and `examples/adk-multi-agent/` imports and referenced tool names.
- Verify security docs still match `tools/safety.py` and `tools/gcloud_ops.py`.
- Re-read `.github/copilot-instructions.md` if architecture, commands, or conventions changed.

### `security-audit`

Use whenever user input, subprocess execution, or generated configuration changes.

Baseline checks:

```bash
grep -n "subprocess\|shell=True\|os.system\|os.popen" src/vpcsc_mcp/tools/*.py
grep -n "ALLOWED\|allowlist\|BLOCKED\|metachar\|inject" src/vpcsc_mcp/tools/safety.py src/vpcsc_mcp/tools/gcloud_ops.py
grep -n "sanitize\|sanitise\|filter" src/vpcsc_mcp/tools/safety.py
grep -n "allUsers\|allAuthenticatedUsers\|allow-unauthenticated\|0\.0\.0\.0" terraform/*.tf cloudbuild.yaml Dockerfile src/vpcsc_mcp/server.py
```

Repo-specific things to preserve:

- exactly centralized `gcloud` execution through `run_gcloud()`
- allowlisted subcommands and flags in `tools/safety.py`
- `asyncio.create_subprocess_exec` with list arguments, never shell execution
- `confirm=True` preview gate on destructive perimeter update tools
- output sanitisation as a first-class defense, not a best-effort extra

### `dep-audit`

Use for lockfile health and Python package hygiene.

```bash
uv lock --check
uv run pip list --format=columns
uv run pip-audit
uv run pip list --outdated --format=columns
```

Review:

- Python compatibility remains `>=3.13`
- MCP SDK stays within the intended major range
- dev dependencies still support the repo's Ruff/pytest workflow

### `release-prep`

Use before creating a versioned release.

Core steps:

```bash
git describe --tags --abbrev=0
git log --oneline --no-merges
uv run ruff check src/ tests/
uv run pytest tests/ -v
docker build -t vpcsc-mcp:pre-release .
```

Update:

- `pyproject.toml` version
- `CHANGELOG.md`
- docs if tool/resource/prompt/service counts or security claims changed

Do not treat release prep as version bump only; this project's release surface also includes docs accuracy and deployment safety.

## Best combinations

| Task | Skills to combine |
|---|---|
| Finish a normal code change | `pre-commit-check` |
| Finish a change to tool counts or public docs | `pre-commit-check` + `doc-sync` |
| Finish a change to `gcloud`/safety/Terraform/YAML logic | `pre-commit-check` + `security-audit` |
| Prepare a release | `release-prep` + `doc-sync` + `security-audit` + `dep-audit` |
| Periodic repo review | `health-check` + `dep-audit` |
