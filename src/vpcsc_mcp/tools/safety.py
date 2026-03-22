"""Output sanitisation, result truncation, and tool annotation presets.

Implements MCP security best practices:
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
        cleaned = cleaned[:MAX_OUTPUT_LENGTH] + f"\n\n[OUTPUT TRUNCATED — {len(text)} chars total, showing first {MAX_OUTPUT_LENGTH}]"

    return cleaned
