"""Input filters — defend against caller-supplied PII, secrets, and prompt injection.

Mirrors safety.sanitise_output but applied to *inbound* tool arguments
(free-text fields like description, query, error_message). Implements
AGENT_GOVERNANCE_FRAMEWORK §11.2 (input filters) and §12.1 (adversarial
inputs at every step, not only the user boundary).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

# ─── PII patterns ──────────────────────────────────────────────────────────

# Conservative — high precision, low recall. Goal is to flag the obvious,
# not to be a full DLP engine (use §11.8 Cloud DLP for that surface).

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",
)
_PHONE_RE = re.compile(
    r"\b(?:\+?\d{1,3}[\s\-]?)?\(?\d{3,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b",
)
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ \-]*?){13,16}\b")  # 13–16 digits with optional separators
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("email", _EMAIL_RE),
    ("phone", _PHONE_RE),
    ("ssn", _SSN_RE),
    ("credit_card", _CC_RE),
    ("iban", _IBAN_RE),
]

# ─── Secret patterns ──────────────────────────────────────────────────────

_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "gcp_sa_key_block",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----",
        ),
    ),
    ("gcp_sa_json", re.compile(r'"private_key"\s*:\s*"[^"]{50,}"')),
    ("oauth_token", re.compile(r"\bya29\.[A-Za-z0-9_\-]{20,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws_secret_key", re.compile(r"\b[A-Za-z0-9/+=]{40}\b(?=.*aws)", re.IGNORECASE)),
    ("github_token", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("github_oauth", re.compile(r"\bgho_[A-Za-z0-9]{36}\b")),
    ("slack_token", re.compile(r"\bxox[abps]-[A-Za-z0-9\-]{10,}\b")),
    (
        "generic_api_key",
        re.compile(
            r"\b(?:api[_\-]?key|apikey|secret)['\"\s:=]{1,5}['\"]?[A-Za-z0-9_\-]{20,}",
            re.IGNORECASE,
        ),
    ),
]

# ─── Prompt-injection heuristics ──────────────────────────────────────────
# Narrow, high-precision phrases — overlaps with safety._INJECTION_PATTERNS
# but applied to *inputs* so callers can't smuggle directives through args.

_INJECTION_RE = re.compile(
    r"<\s*(?:IMPORTANT|system|instructions?|prompt|override|admin|ignore)\s*>|"
    r"(?:^|[\s\.\!\?])(?:IGNORE\s+(?:PREVIOUS|ALL|ABOVE)|"
    r"FORGET\s+(?:ALL|EVERYTHING|PREVIOUS)|"
    r"DISREGARD\s+(?:ALL|PREVIOUS|ABOVE)|"
    r"OVERRIDE\s+(?:SYSTEM|INSTRUCTIONS?)|"
    r"YOU\s+(?:MUST|ARE\s+NOW|SHOULD)\s+(?:IGNORE|DELETE|EXFILTRATE|REVEAL)|"
    r"NEW\s+INSTRUCTIONS?\s*[:\-]|"
    r"SYSTEM\s+PROMPT\s*[:\-])",
    re.IGNORECASE,
)

# ─── Result dataclass ─────────────────────────────────────────────────────


@dataclass
class FilterResult:
    """Outcome of running a value through the input filter stack."""

    cleaned: Any
    findings: list[str] = field(default_factory=list)
    blocked: bool = False
    reason: str | None = None

    @property
    def has_findings(self) -> bool:
        return bool(self.findings)


# ─── Core filter ──────────────────────────────────────────────────────────

# Default behaviour: redact PII (cleaned), redact secrets (cleaned), BLOCK on
# prompt-injection (we don't trust the rest of the input). Callers can opt
# into permissive modes for free-text fields where redaction-only is enough.


def filter_text(
    value: str,
    *,
    field_name: str = "input",
    block_secrets: bool = True,
    block_injection: bool = True,
    redact_pii: bool = True,
    max_length: int = 4096,
) -> FilterResult:
    """Run a single string through the filter stack.

    - Truncate to ``max_length`` before scanning.
    - Detect & optionally redact PII patterns (default: redact).
    - Detect secrets — by default block (refuse the call rather than redact,
      since a redacted secret in a tool arg is still a sign of misuse).
    - Detect prompt-injection directives — by default block.

    Returns a FilterResult.
    """
    findings: list[str] = []
    if not isinstance(value, str):
        return FilterResult(cleaned=value)

    cleaned = value if len(value) <= max_length else value[:max_length] + "[TRUNCATED]"

    # Secrets first — strongest signal of misuse.
    for label, pattern in _SECRET_PATTERNS:
        if pattern.search(cleaned):
            findings.append(f"secret:{label}")
            if block_secrets:
                return FilterResult(
                    cleaned=cleaned,
                    findings=findings,
                    blocked=True,
                    reason=f"caller-supplied secret detected in {field_name} ({label})",
                )
            cleaned = pattern.sub(f"[REDACTED:{label}]", cleaned)

    # Prompt injection
    if _INJECTION_RE.search(cleaned):
        findings.append("prompt_injection")
        if block_injection:
            return FilterResult(
                cleaned=cleaned,
                findings=findings,
                blocked=True,
                reason=f"prompt-injection pattern detected in {field_name}",
            )
        cleaned = _INJECTION_RE.sub("[FILTERED]", cleaned)

    # PII — redact by default (less severe than blocking)
    if redact_pii:
        for label, pattern in _PII_PATTERNS:
            if pattern.search(cleaned):
                findings.append(f"pii:{label}")
                cleaned = pattern.sub(f"[REDACTED:{label}]", cleaned)

    return FilterResult(cleaned=cleaned, findings=findings)


def filter_args(
    args: Mapping[str, Any],
    *,
    block_secrets: bool = True,
    block_injection: bool = True,
    redact_pii: bool = True,
) -> FilterResult:
    """Run every string-valued field in a tool-args mapping through the filter.

    Non-string values pass through untouched. Returns a single FilterResult
    where ``cleaned`` is a new dict; ``blocked`` is True if any field was blocked.
    """
    cleaned: dict[str, Any] = {}
    all_findings: list[str] = []
    for name, value in args.items():
        if isinstance(value, str):
            res = filter_text(
                value,
                field_name=name,
                block_secrets=block_secrets,
                block_injection=block_injection,
                redact_pii=redact_pii,
            )
            if res.blocked:
                return FilterResult(
                    cleaned={**cleaned, name: value},
                    findings=all_findings + res.findings,
                    blocked=True,
                    reason=res.reason,
                )
            cleaned[name] = res.cleaned
            all_findings.extend(res.findings)
        elif isinstance(value, list):
            cleaned_list = []
            for item in value:
                if isinstance(item, str):
                    res = filter_text(
                        item,
                        field_name=f"{name}[]",
                        block_secrets=block_secrets,
                        block_injection=block_injection,
                        redact_pii=redact_pii,
                    )
                    if res.blocked:
                        return FilterResult(
                            cleaned={**cleaned, name: value},
                            findings=all_findings + res.findings,
                            blocked=True,
                            reason=res.reason,
                        )
                    cleaned_list.append(res.cleaned)
                    all_findings.extend(res.findings)
                else:
                    cleaned_list.append(item)
            cleaned[name] = cleaned_list
        else:
            cleaned[name] = value
    return FilterResult(cleaned=cleaned, findings=all_findings)
