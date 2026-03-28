"""Security module — command validation, output sanitisation, and tool annotation presets.

Implements MCP security best practices:
- Validate gcloud arguments against command/flag allowlists
- Reject shell metacharacters in user-provided arguments
- Strip instruction-like content from tool outputs (prompt injection defence)
- Truncate long results to prevent context pollution
- Provide annotation presets for tool safety declarations
"""

from __future__ import annotations

import re

from mcp.types import ToolAnnotations

# ─── Tool Annotation Presets ────────────────────────────────────────────────

# Read-only tools that query GCP (list, describe, check)
READONLY_GCP = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)

# Write tools that modify GCP resources (update perimeters)
WRITE_GCP = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=False,
    openWorldHint=True,
)

# Pure computation tools (generate Terraform, YAML, analysis) — no external calls
GENERATE = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)

# Diagnostic tools that query GCP but never modify
DIAGNOSTIC = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=True,
)

# ─── Output Sanitisation ───────────────────────────────────────────────────

# Patterns that look like injected instructions in tool output
_INJECTION_PATTERNS = re.compile(
    r"<\s*(?:IMPORTANT|system|instructions?|prompt|override|admin|ignore)\s*>|"
    r"(?:^|\n)\s*(?:IGNORE PREVIOUS|FORGET ALL|DISREGARD|OVERRIDE|YOU MUST|YOU ARE NOW)\b",
    re.IGNORECASE,
)

# Maximum safe output length (chars). Truncate beyond this to prevent context pollution.
MAX_OUTPUT_LENGTH = 50_000


def sanitise_output(text: str) -> str:
    """Sanitise tool output to defend against prompt injection via tool results.

    - Strips instruction-like tags and directives
    - Truncates to MAX_OUTPUT_LENGTH
    """
    # Strip injection patterns
    cleaned = _INJECTION_PATTERNS.sub("[FILTERED]", text)

    # Truncate
    if len(cleaned) > MAX_OUTPUT_LENGTH:
        cleaned = (
            cleaned[:MAX_OUTPUT_LENGTH]
            + f"\n\n[OUTPUT TRUNCATED — {len(text)} chars total, "
            f"showing first {MAX_OUTPUT_LENGTH}]"
        )

    return cleaned


# ─── Command Validation ───────────────────────────────────────────────────
# Consolidated from gcloud_ops.py — single source of truth for what's allowed.

# Allowed gcloud subcommands — prevents arbitrary command execution.
ALLOWED_SUBCOMMANDS = frozenset({
    "access-context-manager",
    "config",
    "compute",
    "iam",
    "logging",
    "org-policies",
    "organizations",
    "projects",
    "services",
})

# Only these gcloud flags are allowed. Prevents --impersonate-service-account,
# --access-token-file, --configuration, and other privilege-escalation flags.
ALLOWED_FLAGS = frozenset({
    "--add-resources",
    "--add-restricted-services",
    "--enabled",
    "--format",
    "--freshness",
    "--limit",
    "--organization",
    "--policy",
    "--project",
    "--remove-resources",
    "--remove-restricted-services",
})

# Pattern for safe argument values — alphanumeric, hyphens, underscores,
# dots, slashes, colons, equals, at-signs, commas, and spaces.
_SAFE_ARG = re.compile(r'^[\w\-\./:=@,\s*"\']+$')


def validate_gcloud_args(args: list[str]) -> str | None:
    """Validate gcloud arguments against the command allowlist.

    Returns an error message string if validation fails, or None if the arguments are safe.
    """
    if not args:
        return "No gcloud arguments provided."

    subcommand = args[0]
    if subcommand not in ALLOWED_SUBCOMMANDS:
        return f"Subcommand '{subcommand}' is not in the allowed list: {sorted(ALLOWED_SUBCOMMANDS)}"

    for arg in args:
        if not _SAFE_ARG.match(arg):
            return f"Argument contains disallowed characters: {arg!r}"

        if arg.startswith("--"):
            flag_name = arg.split("=")[0]
            if flag_name not in ALLOWED_FLAGS:
                return f"Flag '{flag_name}' is not in the allowed list. Allowed: {sorted(ALLOWED_FLAGS)}"

    return None
