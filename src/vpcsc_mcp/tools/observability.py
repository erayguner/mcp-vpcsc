"""Observability module — audit logging, result caching, rate limiting, and metrics.

Implements MCP best practices from the Model Context Protocol book:
- Structured audit logging for every tool invocation (Ch 8)
- TTL-based caching for read-only gcloud results (Ch 6, 9)
- Asyncio semaphore rate limiting for gcloud operations (Ch 8)
- Tool invocation metrics for performance monitoring (Ch 9, 18)
"""

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict

logger = logging.getLogger(__name__)

# ─── Audit Logging ────────────────────────────────────────────────────────

_audit_logger = logging.getLogger("vpcsc_mcp.audit")


def audit_log(
    *,
    tool: str,
    args: dict | list | None = None,
    duration_ms: float | None = None,
    success: bool = True,
    error: str | None = None,
    cached: bool = False,
) -> None:
    """Emit a structured audit log entry for a tool invocation.

    Every gcloud operation and tool call is logged with enough context
    for post-hoc security review and anomaly detection.
    """
    entry = {
        "event": "tool_call",
        "tool": tool,
        "timestamp": time.time(),
        "success": success,
        "cached": cached,
    }
    if args is not None:
        entry["args"] = args if isinstance(args, dict) else {"raw": args}
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    if error:
        entry["error"] = error

    _audit_logger.info(json.dumps(entry, default=str))


# ─── Result Cache ─────────────────────────────────────────────────────────

# Subcommand verbs that are safe to cache (read-only operations).
_CACHEABLE_VERBS = frozenset({
    "list", "describe", "get-value", "read",
    "supported-services",
})


def _is_cacheable(args: list[str]) -> bool:
    """Return True if the gcloud command is read-only and safe to cache."""
    return any(verb in arg for arg in args for verb in _CACHEABLE_VERBS)


def _cache_key(args: list[str], project: str | None) -> str:
    """Produce a deterministic cache key from command arguments."""
    raw = json.dumps({"args": args, "project": project}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class GcloudCache:
    """Simple TTL cache for read-only gcloud results.

    Prevents redundant subprocess calls when the same query is repeated
    within a short window (e.g. list_perimeters called twice in one session).
    """

    def __init__(self, default_ttl: int = 300):
        self._cache: dict[str, tuple[float, dict]] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, args: list[str], project: str | None = None) -> dict | None:
        """Return cached result if available and not expired."""
        if not _is_cacheable(args):
            return None

        key = _cache_key(args, project)
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        expiry, value = entry
        if time.monotonic() >= expiry:
            del self._cache[key]
            self._misses += 1
            return None

        self._hits += 1
        return value

    def set(self, args: list[str], project: str | None, value: dict, ttl: int | None = None) -> None:
        """Store a result if the command is cacheable."""
        if not _is_cacheable(args):
            return
        # Don't cache errors
        if "error" in value:
            return

        key = _cache_key(args, project)
        self._cache[key] = (time.monotonic() + (ttl or self._default_ttl), value)

    def invalidate(self, pattern: str | None = None) -> None:
        """Clear all entries, or entries whose key-args contain *pattern*."""
        if pattern is None:
            self._cache.clear()
        else:
            self._cache = {k: v for k, v in self._cache.items() if pattern not in k}

    @property
    def stats(self) -> dict:
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / max(self._hits + self._misses, 1), 3),
        }


# ─── Rate Limiter ─────────────────────────────────────────────────────────


class RateLimiter:
    """Asyncio semaphore-based rate limiter for gcloud operations.

    Prevents a misbehaving client from overwhelming the GCP API by
    limiting the number of concurrent gcloud subprocess calls.
    """

    def __init__(self, max_concurrent: int = 5):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max_concurrent = max_concurrent
        self._active = 0
        self._total = 0
        self._rejected = 0

    async def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire a slot. Returns False if timed out."""
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=timeout)
            self._active += 1
            self._total += 1
            return True
        except asyncio.TimeoutError:
            self._rejected += 1
            return False

    def release(self) -> None:
        self._semaphore.release()
        self._active = max(0, self._active - 1)

    @property
    def stats(self) -> dict:
        return {
            "max_concurrent": self._max_concurrent,
            "active": self._active,
            "total_acquired": self._total,
            "rejected": self._rejected,
        }


# ─── Tool Metrics ─────────────────────────────────────────────────────────


class ToolMetrics:
    """Lightweight metrics collector for tool invocation performance.

    Tracks call count, total duration, and error count per tool name
    for performance monitoring and bottleneck detection.
    """

    def __init__(self):
        self._calls: dict[str, int] = defaultdict(int)
        self._durations: dict[str, float] = defaultdict(float)
        self._errors: dict[str, int] = defaultdict(int)
        self._cache_hits: dict[str, int] = defaultdict(int)

    def record(self, tool: str, duration_ms: float, success: bool = True, cached: bool = False) -> None:
        self._calls[tool] += 1
        self._durations[tool] += duration_ms
        if not success:
            self._errors[tool] += 1
        if cached:
            self._cache_hits[tool] += 1

    @property
    def summary(self) -> dict:
        """Return a summary of all tool metrics."""
        tools = {}
        for tool in sorted(self._calls):
            count = self._calls[tool]
            tools[tool] = {
                "calls": count,
                "total_ms": round(self._durations[tool], 2),
                "avg_ms": round(self._durations[tool] / count, 2) if count else 0,
                "errors": self._errors.get(tool, 0),
                "cache_hits": self._cache_hits.get(tool, 0),
            }
        return tools


# ─── Module-level singletons ─────────────────────────────────────────────
# Initialised once, shared across all tool modules in the process.

cache = GcloudCache(default_ttl=300)
rate_limiter = RateLimiter(max_concurrent=5)
metrics = ToolMetrics()
