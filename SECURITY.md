# Security Policy

## Supported versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a vulnerability

If you discover a security vulnerability in this project, please report it responsibly:

1. **Do not** open a public GitHub issue for security vulnerabilities.
2. Use [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository (preferred).
3. Alternatively, email **erayguner@users.noreply.github.com** with the subject line `[SECURITY] vpcsc-mcp`.
4. Include:
   - A description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)

We will acknowledge receipt within **48 hours** and aim to provide a fix or mitigation within **7 days** for critical issues.

## Security model

This server executes `gcloud` CLI commands on behalf of users — security is a first-class concern. The full threat model is documented in [docs/security.md](docs/security.md). Key controls:

- **Command allowlist** — only 9 `gcloud` subcommands and 11 flags are permitted (`tools/safety.py`)
- **Argument validation** — shell metacharacters and privilege-escalation flags are rejected via regex
- **No `shell=True`** — all subprocess calls use `create_subprocess_exec`
- **Output sanitisation** — prompt-injection patterns are stripped from tool results
- **Write confirmation** — destructive tools require `confirm=True` (preview by default)
- **Tool annotations** — all 40 tools declare `readOnlyHint` / `destructiveHint` (38 read-only, 2 write)
- **120s command timeout** — hung `gcloud` processes are killed automatically
- **Non-root container** — Docker image runs as UID 1001
- **Localhost binding** — HTTP transport binds to `127.0.0.1` locally; `0.0.0.0` only on Cloud Run

## Security practices

- Dependencies are monitored via [GitHub Dependabot](.github/dependabot.yml) (pip, Docker, Terraform, GitHub Actions).
- CI runs linting and tests on all pull requests.
- CodeQL analysis runs on pushes and pull requests for automated vulnerability detection.
- Container images run as non-root users with minimal installed packages.
- Pull requests that touch security-sensitive code (`safety.py`, `gcloud_ops.py`, `terraform_gen.py`) include a security checklist.

## Disclosure policy

- Vulnerabilities are disclosed after a fix is available.
- Credit is given to reporters in the changelog and release notes (unless they prefer anonymity).
