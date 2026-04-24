"""Security module — command validation, output sanitisation, and tool annotation presets.

Implements MCP security best practices:
- Validate gcloud arguments against command/flag allowlists
- Reject shell metacharacters in user-provided arguments
- Strip instruction-like content from tool outputs (prompt injection defence)
- Redact sensitive data patterns from tool outputs (data minimisation)
- Truncate long results to prevent context pollution
- Provide annotation presets for tool safety declarations
"""

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

# Patterns that look like injected instructions in tool output.
# Kept in sync with input_filters._INJECTION_RE so attacker-controlled text
# returned from GCP (resource descriptions, labels, log entries) is filtered
# with the same precision as caller-supplied input.
_INJECTION_PATTERNS = re.compile(
    r"<\s*(?:IMPORTANT|system|instructions?|prompt|override|admin|ignore)\s*>|"
    r"(?:^|[\s\.\!\?,;:])(?:IGNORE\s+(?:PREVIOUS|ALL|ABOVE)|"
    r"FORGET\s+(?:ALL|EVERYTHING|PREVIOUS)|"
    r"DISREGARD\s+(?:ALL|PREVIOUS|ABOVE)|"
    r"OVERRIDE\s+(?:SYSTEM|INSTRUCTIONS?)|"
    r"YOU\s+(?:MUST|ARE\s+NOW|SHOULD)\s+(?:IGNORE|DELETE|EXFILTRATE|REVEAL|"
    r"FORGET|DISREGARD|OUTPUT|PRINT|LEAK)|"
    r"NEW\s+INSTRUCTIONS?\s*[:\-]|"
    r"SYSTEM\s+PROMPT\s*[:\-])",
    re.IGNORECASE,
)

# Unicode tag characters (U+E0000..U+E007F) and other invisible control chars
# used to smuggle instructions past visual review. Also zero-width joiners/
# non-joiners / BOM.
_INVISIBLE_CHARS = re.compile(
    r"[\U000E0000-\U000E007F\u200B\u200C\u200D\u2060\uFEFF]",
)

# Maximum safe output length (chars). Truncate beyond this to prevent context pollution.
MAX_OUTPUT_LENGTH = 50_000


def sanitise_output(text: str, redact: bool = True) -> str:
    """Sanitise tool output to defend against prompt injection and data leakage.

    - Strips instruction-like tags and directives (line-start *and* mid-sentence)
    - Strips invisible/tag Unicode chars used to smuggle hidden instructions
    - Optionally redacts sensitive data patterns (SA keys, tokens)
    - Truncates to MAX_OUTPUT_LENGTH
    """
    # Strip invisible/tag chars first so they can't hide injection patterns.
    cleaned = _INVISIBLE_CHARS.sub("", text)

    # Strip injection patterns
    cleaned = _INJECTION_PATTERNS.sub("[FILTERED]", cleaned)

    # Redact sensitive data
    if redact:
        cleaned = redact_sensitive_data(cleaned)

    # Truncate
    if len(cleaned) > MAX_OUTPUT_LENGTH:
        cleaned = (
            cleaned[:MAX_OUTPUT_LENGTH] + f"\n\n[OUTPUT TRUNCATED — {len(text)} chars total, "
            f"showing first {MAX_OUTPUT_LENGTH}]"
        )

    return cleaned


# ─── Sensitive Data Redaction ─────────────────────────────────────────────

# Service account key IDs (40-char hex or base64 strings following "private_key_id" or similar)
_SA_KEY_PATTERN = re.compile(
    r'"private_key":\s*"[^"]{50,}"',
)

# Full private key blocks (PEM format)
_PEM_KEY_PATTERN = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
)

# OAuth tokens and bearer tokens
_TOKEN_PATTERN = re.compile(
    r"(ya29\.[A-Za-z0-9_-]{20,}|Bearer\s+[A-Za-z0-9_-]{20,})",
)


def redact_sensitive_data(text: str) -> str:
    """Redact sensitive patterns from tool output for data minimisation.

    Redacts:
    - Service account private keys (PEM blocks and JSON key fields)
    - OAuth access tokens and bearer tokens
    """
    cleaned = _SA_KEY_PATTERN.sub('"private_key": "[REDACTED]"', text)
    cleaned = _PEM_KEY_PATTERN.sub("[REDACTED PRIVATE KEY]", cleaned)
    cleaned = _TOKEN_PATTERN.sub("[REDACTED TOKEN]", cleaned)
    return cleaned


# ─── Command Validation ───────────────────────────────────────────────────
# Consolidated from gcloud_ops.py — single source of truth for what's allowed.

# Allowed gcloud subcommands — prevents arbitrary command execution.
ALLOWED_SUBCOMMANDS = frozenset(
    {
        "access-context-manager",
        "config",
        "compute",
        "iam",
        "logging",
        "org-policies",
        "organizations",
        "projects",
        "services",
    }
)

# Only these gcloud flags are allowed. Prevents --impersonate-service-account,
# --access-token-file, --configuration, and other privilege-escalation flags.
ALLOWED_FLAGS = frozenset(
    {
        "--add-resources",
        "--add-restricted-services",
        "--enabled",
        "--etag",
        "--format",
        "--freshness",
        "--limit",
        "--organization",
        "--policy",
        "--project",
        "--remove-resources",
        "--remove-restricted-services",
    }
)

# Pattern for safe argument values — alphanumeric, hyphens, underscores,
# dots, slashes, colons, equals, at-signs, commas, spaces, and tabs.
# Explicitly excludes newlines, carriage returns, and single quotes so that
# argument values cannot smuggle control characters into gcloud (no OS-level
# injection due to create_subprocess_exec, but gcloud parsing can diverge
# across versions on newline-embedded values).
_SAFE_ARG = re.compile(r'^[\w\-\./:=@, \t*"]+$')


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
