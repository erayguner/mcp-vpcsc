## Summary

<!-- Describe what this PR does and why. -->

## Changes

-

## Type of change

- [ ] Bug fix
- [ ] New feature (tool, resource, or prompt)
- [ ] Breaking change
- [ ] Documentation update
- [ ] Refactoring / chore

## Checklist

- [ ] I have read [CONTRIBUTING.md](../CONTRIBUTING.md)
- [ ] Tests pass locally (`uv run pytest`)
- [ ] Linting passes (`uv run ruff check src/ tests/`)
- [ ] New tools include `ToolAnnotations` (readOnlyHint, destructiveHint, etc.)
- [ ] Destructive operations require `confirm=True`
- [ ] Documentation updated if needed
- [ ] `CHANGELOG.md` updated under `[Unreleased]`

## Security checklist

<!-- Required if this PR touches gcloud_ops.py, safety.py, terraform_gen.py, or any subprocess call. -->

- [ ] No new gcloud subcommands or flags added outside `ALLOWED_SUBCOMMANDS` / `ALLOWED_FLAGS`
- [ ] No `shell=True` in subprocess calls
- [ ] User-supplied inputs are validated before use
- [ ] Tool output is sanitised via `safety.sanitise_output`
- [ ] N/A — this PR does not touch security-sensitive code
