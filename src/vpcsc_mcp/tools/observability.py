"""Observability — audit logging, caching, rate limiting, metrics, DLQ.

Implements MCP best practices and AGENT_GOVERNANCE_FRAMEWORK §8 / §9 / §13:
- Structured audit logging with SHA-256 chain + daily HMAC-signed manifest
- Append-only on-disk JSONL with chain-break detection on load
- Signed export bundle for forensic / regulator evidence
- Dead-letter queue for audit writes that fail transiently
- TTL-based caching for read-only gcloud results
- Per-principal asyncio rate limiting (falls back to global bucket)
- Per-tool metrics + optional Cloud Monitoring exporter hook
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ─── Caller principal context ──────────────────────────────────────────────
# Set per-request via the MCP middleware / tool wrapper; defaults to "anonymous".
# Used for per-principal rate limiting and per-principal metrics.

_principal_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "vpcsc_mcp_principal", default="anonymous",
)


def set_principal(principal: str | None) -> contextvars.Token:
    """Bind a caller principal for the duration of a request.

    Returns a token that can be passed to reset_principal() on cleanup.
    """
    return _principal_var.set(principal or "anonymous")


def reset_principal(token: contextvars.Token) -> None:
    _principal_var.reset(token)


def current_principal() -> str:
    return _principal_var.get()


# ─── Audit logging — chained, signed, DLQ-backed ──────────────────────────

_audit_logger = logging.getLogger("vpcsc_mcp.audit")

# HMAC key for signing daily manifests + export bundles. In production this
# should be sourced from Secret Manager via VPCSC_MCP_AUDIT_KEY (raw bytes,
# hex-encoded). Falls back to a process-ephemeral key for dev/tests so unit
# tests can exercise the chain without external setup.
_AUDIT_KEY_ENV = "VPCSC_MCP_AUDIT_KEY"
_AUDIT_DIR_ENV = "VPCSC_MCP_AUDIT_DIR"
_AUDIT_DLQ_ENV = "VPCSC_MCP_AUDIT_DLQ"


def _resolve_audit_key() -> bytes:
    raw = os.environ.get(_AUDIT_KEY_ENV)
    if raw:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            return raw.encode("utf-8")
    # Process-ephemeral fallback — sufficient for dev / test, never for prod.
    return hashlib.sha256(f"vpcsc-dev-{os.getpid()}-{time.time()}".encode()).digest()


def _canonical_dumps(obj: Any) -> str:
    """Stable JSON serialisation for hashing — sort keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


class AuditChainError(RuntimeError):
    """Raised when an audit log on disk fails chain verification."""


class AuditLogger:
    """Append-only audit log with SHA-256 chain + daily HMAC manifest.

    Each entry's ``chain_hash`` = sha256(prev_chain_hash || canonical(entry_payload)).
    Tampering with any prior entry invalidates every subsequent entry.

    Daily manifests record the last hash, entry count, and file SHA-256, signed
    with HMAC-SHA256. Forensic exports bundle a window of entries with their
    chain head + signature.
    """

    GENESIS = "0" * 64  # initial previous-hash for the first entry

    def __init__(
        self,
        *,
        directory: str | os.PathLike[str] | None = None,
        dlq_path: str | os.PathLike[str] | None = None,
        key: bytes | None = None,
    ) -> None:
        self._dir = Path(directory or os.environ.get(_AUDIT_DIR_ENV) or "")
        self._dlq_path = Path(
            dlq_path or os.environ.get(_AUDIT_DLQ_ENV) or "",
        )
        self._key = key or _resolve_audit_key()
        self._lock = threading.Lock()
        self._last_hash = self.GENESIS
        self._count = 0
        self._dlq_count = 0
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)
            # Bootstrap chain head from existing files (strict load).
            self._last_hash = self._verify_and_resume()

    # -- public API --------------------------------------------------------

    def append(self, entry: dict) -> dict:
        """Append an audit entry. Always best-effort — never raises to caller.

        Failures land in the DLQ (if configured) for later replay.
        Returns the chained entry (or the DLQ-tagged entry on failure).
        """
        chained = self._build_entry(entry)
        # Always emit to the python logger sink (stdout / Cloud Logging).
        try:
            _audit_logger.info(_canonical_dumps(chained))
        except Exception:  # pragma: no cover - logger should not throw
            pass

        if self._dir:
            try:
                self._write_to_disk(chained)
            except OSError as exc:
                self._send_to_dlq(chained, reason=f"write_failed:{exc}")
                return chained
        return chained

    def stats(self) -> dict:
        return {
            "entries_total": self._count,
            "last_hash": self._last_hash,
            "dlq_entries": self._dlq_count,
            "directory": str(self._dir) if self._dir else None,
            "dlq_path": str(self._dlq_path) if self._dlq_path else None,
        }

    def export_signed(
        self,
        *,
        since: float | None = None,
        until: float | None = None,
    ) -> dict:
        """Produce a signed export bundle for the given timestamp window.

        Returns ``{"payload": <canonical JSON>, "signature": <hex>, "algorithm": ...}``.
        Replayable in audit reviews and submittable to regulators.
        """
        entries = list(self._iter_entries(since=since, until=until))
        chain_head = entries[-1]["chain_hash"] if entries else self.GENESIS
        payload = {
            "exported_at": time.time(),
            "exported_at_iso": datetime.now(UTC).isoformat(),
            "since": since,
            "until": until,
            "count": len(entries),
            "chain_head": chain_head,
            "entries": entries,
        }
        canonical = _canonical_dumps(payload)
        signature = hmac.new(self._key, canonical.encode(), hashlib.sha256).hexdigest()
        return {
            "payload": payload,
            "signature": signature,
            "algorithm": "HMAC-SHA256",
        }

    def write_daily_manifest(self, day: str | None = None) -> dict | None:
        """Write a signed manifest for the given UTC day (YYYY-MM-DD).

        Returns the manifest dict, or None if no entries exist for that day.
        """
        if not self._dir:
            return None
        target_day = day or datetime.now(UTC).strftime("%Y-%m-%d")
        log_path = self._log_path_for(target_day)
        if not log_path.exists():
            return None
        entries = list(self._read_log_file(log_path))
        if not entries:
            return None
        file_hash = hashlib.sha256(log_path.read_bytes()).hexdigest()
        manifest = {
            "day": target_day,
            "file": log_path.name,
            "entry_count": len(entries),
            "file_sha256": file_hash,
            "chain_head": entries[-1]["chain_hash"],
            "generated_at": time.time(),
        }
        canonical = _canonical_dumps(manifest)
        manifest["signature"] = hmac.new(
            self._key, canonical.encode(), hashlib.sha256,
        ).hexdigest()
        manifest["algorithm"] = "HMAC-SHA256"
        manifest_path = self._dir / f"manifest-{target_day}.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        return manifest

    def replay_dlq(self) -> int:
        """Re-attempt DLQ entries; return the number successfully drained."""
        if not (self._dlq_path and self._dlq_path.exists() and self._dir):
            return 0
        drained = 0
        remaining: list[str] = []
        for line in self._dlq_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                self._write_to_disk(entry)
                drained += 1
                self._dlq_count = max(0, self._dlq_count - 1)
            except (OSError, json.JSONDecodeError):
                remaining.append(line)
        if remaining:
            self._dlq_path.write_text("\n".join(remaining) + "\n")
        else:
            self._dlq_path.write_text("")
        return drained

    # -- internals ---------------------------------------------------------

    def _build_entry(self, entry: dict) -> dict:
        with self._lock:
            payload = dict(entry)
            payload.setdefault("timestamp", time.time())
            payload.setdefault("principal", current_principal())
            chain_input = self._last_hash + _canonical_dumps(payload)
            chain_hash = hashlib.sha256(chain_input.encode()).hexdigest()
            payload["prev_hash"] = self._last_hash
            payload["chain_hash"] = chain_hash
            payload["seq"] = self._count
            self._last_hash = chain_hash
            self._count += 1
            return payload

    def _log_path_for(self, day: str) -> Path:
        return self._dir / f"audit-{day}.jsonl"

    def _write_to_disk(self, entry: dict) -> None:
        ts = entry.get("timestamp", time.time())
        day = datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d")
        path = self._log_path_for(day)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, default=str) + "\n")

    def _send_to_dlq(self, entry: dict, *, reason: str) -> None:
        self._dlq_count += 1
        if not self._dlq_path:
            return
        try:
            self._dlq_path.parent.mkdir(parents=True, exist_ok=True)
            with self._dlq_path.open("a", encoding="utf-8") as fh:
                tagged = dict(entry, dlq_reason=reason)
                fh.write(json.dumps(tagged, default=str) + "\n")
        except OSError:
            # Last resort — emit to stderr via python logger
            logger.warning("audit dlq write failed", extra={"reason": reason})

    def _read_log_file(self, path: Path) -> Iterator[dict]:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise AuditChainError(
                        f"corrupt entry in {path}: {exc}",
                    ) from exc

    def _iter_entries(
        self, *, since: float | None, until: float | None,
    ) -> Iterator[dict]:
        if not self._dir:
            return
        for log_path in sorted(self._dir.glob("audit-*.jsonl")):
            for entry in self._read_log_file(log_path):
                ts = entry.get("timestamp")
                if since is not None and ts is not None and ts < since:
                    continue
                if until is not None and ts is not None and ts > until:
                    continue
                yield entry

    def _verify_and_resume(self) -> str:
        """Verify the chain across rotated files; return the last hash.

        Raises AuditChainError on the first inconsistency.
        """
        prev = self.GENESIS
        seq = 0
        if not self._dir.exists():
            return prev
        for log_path in sorted(self._dir.glob("audit-*.jsonl")):
            for entry in self._read_log_file(log_path):
                expected_prev = entry.get("prev_hash")
                if expected_prev != prev:
                    raise AuditChainError(
                        f"chain break in {log_path.name} at seq={entry.get('seq')}"
                        f": expected prev_hash={prev} got {expected_prev}",
                    )
                payload = {
                    k: v for k, v in entry.items()
                    if k not in {"prev_hash", "chain_hash", "seq"}
                }
                recomputed = hashlib.sha256(
                    (prev + _canonical_dumps(payload)).encode(),
                ).hexdigest()
                if recomputed != entry.get("chain_hash"):
                    raise AuditChainError(
                        f"checksum mismatch in {log_path.name} at seq={entry.get('seq')}",
                    )
                prev = entry["chain_hash"]
                seq += 1
        self._count = seq
        return prev


# Module-level singleton — initialised lazily so env vars are read at first use.
_audit_singleton: AuditLogger | None = None
_audit_lock = threading.Lock()


def get_audit_logger() -> AuditLogger:
    global _audit_singleton
    if _audit_singleton is None:
        with _audit_lock:
            if _audit_singleton is None:
                _audit_singleton = AuditLogger()
    return _audit_singleton


def reset_audit_logger_for_tests(logger_: AuditLogger | None = None) -> None:
    """Test-only helper: replace the module singleton."""
    global _audit_singleton
    with _audit_lock:
        _audit_singleton = logger_


def audit_log(
    *,
    tool: str,
    args: dict | list | None = None,
    duration_ms: float | None = None,
    success: bool = True,
    error: str | None = None,
    cached: bool = False,
    halted: bool = False,
) -> dict:
    """Emit a chained audit entry for a tool invocation.

    Returns the chained entry (with prev_hash / chain_hash / seq / principal).
    """
    entry: dict = {
        "event": "tool_call",
        "tool": tool,
        "success": success,
        "cached": cached,
    }
    if halted:
        entry["halted"] = True
    if args is not None:
        entry["args"] = args if isinstance(args, dict) else {"raw": args}
    if duration_ms is not None:
        entry["duration_ms"] = round(duration_ms, 2)
    if error:
        entry["error"] = error
    return get_audit_logger().append(entry)


# ─── Result Cache ─────────────────────────────────────────────────────────

# Subcommand verbs that are safe to cache (read-only operations).
_CACHEABLE_VERBS = frozenset({
    "list", "describe", "get-value", "read",
    "supported-services",
})


def _is_cacheable(args: list[str]) -> bool:
    return any(verb in arg for arg in args for verb in _CACHEABLE_VERBS)


def _cache_key(args: list[str], project: str | None) -> str:
    raw = json.dumps({"args": args, "project": project}, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


class GcloudCache:
    """Simple TTL cache for read-only gcloud results."""

    def __init__(self, default_ttl: int = 300):
        self._cache: dict[str, tuple[float, dict]] = {}
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, args: list[str], project: str | None = None) -> dict | None:
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

    def set(
        self, args: list[str], project: str | None, value: dict, ttl: int | None = None,
    ) -> None:
        if not _is_cacheable(args):
            return
        if "error" in value:
            return
        key = _cache_key(args, project)
        self._cache[key] = (time.monotonic() + (ttl or self._default_ttl), value)

    def invalidate(self, pattern: str | None = None) -> None:
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


# ─── Per-Principal Rate Limiter ───────────────────────────────────────────


class RateLimiter:
    """Per-principal asyncio semaphore rate limiter.

    Each caller principal gets its own semaphore so a single misbehaving
    client cannot starve others. Also tracks a global cap to prevent
    aggregate API abuse.
    """

    def __init__(self, max_concurrent: int = 5, max_per_principal: int | None = None):
        self._max_concurrent = max_concurrent
        self._max_per_principal = max_per_principal or max_concurrent
        self._global = asyncio.Semaphore(max_concurrent)
        self._per_principal: dict[str, asyncio.Semaphore] = {}
        self._stats_lock = threading.Lock()
        self._active = 0
        self._total = 0
        self._rejected = 0
        self._per_principal_stats: dict[str, dict[str, int]] = defaultdict(
            lambda: {"acquired": 0, "rejected": 0, "active": 0},
        )

    def _principal_sem(self, principal: str) -> asyncio.Semaphore:
        sem = self._per_principal.get(principal)
        if sem is None:
            sem = asyncio.Semaphore(self._max_per_principal)
            self._per_principal[principal] = sem
        return sem

    async def acquire(self, timeout: float = 30.0, principal: str | None = None) -> bool:
        principal = principal or current_principal()
        psem = self._principal_sem(principal)
        try:
            await asyncio.wait_for(psem.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            with self._stats_lock:
                self._rejected += 1
                self._per_principal_stats[principal]["rejected"] += 1
            return False
        try:
            await asyncio.wait_for(self._global.acquire(), timeout=timeout)
        except asyncio.TimeoutError:
            psem.release()
            with self._stats_lock:
                self._rejected += 1
                self._per_principal_stats[principal]["rejected"] += 1
            return False
        with self._stats_lock:
            self._active += 1
            self._total += 1
            stats = self._per_principal_stats[principal]
            stats["acquired"] += 1
            stats["active"] += 1
        return True

    def release(self, principal: str | None = None) -> None:
        principal = principal or current_principal()
        psem = self._per_principal.get(principal)
        if psem is not None:
            psem.release()
        self._global.release()
        with self._stats_lock:
            self._active = max(0, self._active - 1)
            stats = self._per_principal_stats.get(principal)
            if stats is not None:
                stats["active"] = max(0, stats["active"] - 1)

    @property
    def stats(self) -> dict:
        with self._stats_lock:
            top_offenders = sorted(
                self._per_principal_stats.items(),
                key=lambda kv: kv[1]["rejected"],
                reverse=True,
            )[:10]
        return {
            "max_concurrent": self._max_concurrent,
            "max_per_principal": self._max_per_principal,
            "active": self._active,
            "total_acquired": self._total,
            "rejected": self._rejected,
            "principals_seen": len(self._per_principal),
            "top_rejected_principals": [
                {"principal": p, **s} for p, s in top_offenders if s["rejected"] > 0
            ],
        }


# ─── Tool Metrics ─────────────────────────────────────────────────────────


class ToolMetrics:
    """Per-tool + per-principal call metrics.

    Optional Cloud Monitoring exporter hook: if set, ``record()`` invokes the
    callback so callers can wire OpenTelemetry / google-cloud-monitoring
    without forcing the dependency on every install.
    """

    def __init__(self):
        self._calls: dict[str, int] = defaultdict(int)
        self._durations: dict[str, float] = defaultdict(float)
        self._errors: dict[str, int] = defaultdict(int)
        self._cache_hits: dict[str, int] = defaultdict(int)
        self._principal_calls: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int),
        )
        self._exporter: Any = None

    def attach_exporter(self, callback: Any) -> None:
        """Wire an optional metrics exporter.

        ``callback(tool, duration_ms, success, cached, principal)`` is called
        synchronously after every record. Exceptions are swallowed.
        """
        self._exporter = callback

    def record(
        self, tool: str, duration_ms: float, success: bool = True, cached: bool = False,
        principal: str | None = None,
    ) -> None:
        principal = principal or current_principal()
        self._calls[tool] += 1
        self._durations[tool] += duration_ms
        if not success:
            self._errors[tool] += 1
        if cached:
            self._cache_hits[tool] += 1
        self._principal_calls[principal][tool] += 1
        if self._exporter is not None:
            try:
                self._exporter(tool, duration_ms, success, cached, principal)
            except Exception:  # pragma: no cover
                logger.debug("metrics exporter raised", exc_info=True)

    @property
    def summary(self) -> dict:
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

    @property
    def per_principal(self) -> dict:
        return {
            p: dict(tools) for p, tools in self._principal_calls.items()
        }


# ─── Module-level singletons ─────────────────────────────────────────────

cache = GcloudCache(default_ttl=300)
rate_limiter = RateLimiter(max_concurrent=5, max_per_principal=3)
metrics = ToolMetrics()
