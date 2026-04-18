"""Kill-switch / halt module — operator override for in-flight tool calls.

Implements AGENT_GOVERNANCE_FRAMEWORK §14.1 (kill-switch) and §14.2 (override
API). Halts are persistent for the process lifetime; the audit log records
every halt / resume / override as a HumanOverrideStep equivalent.

Halt scope:
- "global"        — every gcloud call denies; preview-mode tools are unaffected
- "principal:<x>" — every call from principal x denies
- "tool:<x>"      — every call to tool x denies (e.g. "gcloud.access-context-manager")
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from vpcsc_mcp.tools.observability import audit_log, current_principal


@dataclass
class HaltEntry:
    scope: str
    reason: str
    actor: str
    halted_at: float = field(default_factory=time.time)


class HaltRegistry:
    """Thread-safe registry of active halts.

    Checked synchronously by run_gcloud before every subprocess exec.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._halts: dict[str, HaltEntry] = {}

    def halt(self, scope: str, reason: str, actor: str) -> HaltEntry:
        scope = scope.strip()
        if not scope:
            raise ValueError("halt scope must be non-empty")
        if not reason:
            raise ValueError("halt reason must be non-empty")
        entry = HaltEntry(scope=scope, reason=reason, actor=actor)
        with self._lock:
            self._halts[scope] = entry
        audit_log(
            tool="halt.engage",
            args={"scope": scope, "actor": actor, "reason": reason},
            success=True,
        )
        return entry

    def resume(self, scope: str, actor: str) -> bool:
        with self._lock:
            removed = self._halts.pop(scope, None)
        audit_log(
            tool="halt.resume",
            args={"scope": scope, "actor": actor, "had_halt": removed is not None},
            success=removed is not None,
        )
        return removed is not None

    def is_halted(
        self, *, principal: str | None = None, tool: str | None = None,
    ) -> HaltEntry | None:
        principal = principal or current_principal()
        with self._lock:
            for scope_key in (
                "global",
                f"principal:{principal}",
                *([f"tool:{tool}"] if tool else []),
            ):
                entry = self._halts.get(scope_key)
                if entry is not None:
                    return entry
        return None

    def list_halts(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "scope": e.scope,
                    "reason": e.reason,
                    "actor": e.actor,
                    "halted_at": e.halted_at,
                }
                for e in self._halts.values()
            ]

    def clear_for_tests(self) -> None:
        with self._lock:
            self._halts.clear()


registry = HaltRegistry()


def check_halt(tool: str | None = None) -> HaltEntry | None:
    """Convenience wrapper used by run_gcloud and other governed entry points."""
    return registry.is_halted(tool=tool)


# ─── MCP tool registration ────────────────────────────────────────────────


def register_halt_tools(mcp) -> None:
    """Expose halt / resume / status as MCP tools."""
    from mcp.types import ToolAnnotations

    HALT_ANNOTATIONS = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=True,
        openWorldHint=False,
    )
    READ_ANNOTATIONS = ToolAnnotations(
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    )

    @mcp.tool(annotations=HALT_ANNOTATIONS)
    async def halt_session(scope: str, reason: str, actor: str) -> str:
        """Engage the kill-switch — denies subsequent gcloud calls in scope.

        WRITE / OVERRIDE operation. Recorded in the chained audit log.

        Args:
            scope: One of 'global', 'principal:<id>', or 'tool:<tool-name>'.
            reason: Plain-English reason (required, surfaces in /health and audit).
            actor: Identifier of the human operator engaging the halt.
        """
        entry = registry.halt(scope=scope, reason=reason, actor=actor)
        return (
            f"HALT engaged scope={entry.scope} actor={entry.actor}\n"
            f"Reason: {entry.reason}\n"
            "All matching gcloud calls will deny until resume_session is called."
        )

    @mcp.tool(annotations=HALT_ANNOTATIONS)
    async def resume_session(scope: str, actor: str) -> str:
        """Lift a previously engaged halt for the given scope."""
        ok = registry.resume(scope=scope, actor=actor)
        if not ok:
            return f"No active halt for scope={scope!r}."
        return f"Resumed scope={scope} actor={actor}."

    @mcp.tool(annotations=READ_ANNOTATIONS)
    async def list_active_halts() -> str:
        """Return all active halts (scope, reason, actor, when)."""
        halts = registry.list_halts()
        if not halts:
            return "No active halts."
        lines = [f"{len(halts)} active halt(s):"]
        for h in halts:
            ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(h["halted_at"]))
            lines.append(
                f"  - scope={h['scope']} actor={h['actor']} since={ts}\n"
                f"    reason: {h['reason']}",
            )
        return "\n".join(lines)
