"""Tools for managing VPC-SC via gcloud CLI commands."""

import asyncio
import json
import logging
import sys
import time

from vpcsc_mcp.tools.circuit_breaker import CircuitOpen, gcloud_breaker
from vpcsc_mcp.tools.halt import check_halt
from vpcsc_mcp.tools.observability import audit_log, cache, metrics, rate_limiter
from vpcsc_mcp.tools.safety import sanitise_output, validate_gcloud_args

logger = logging.getLogger(__name__)

# Max time (seconds) a single gcloud call may take before being killed.
_GCLOUD_TIMEOUT = 120


def _log(message: str) -> None:
    """Write a progress message to stderr (safe for stdio transport)."""
    print(f"[vpcsc-mcp] {message}", file=sys.stderr, flush=True)


async def run_gcloud(args: list[str], project: str | None = None) -> dict:
    """Execute a gcloud command and return parsed JSON output.

    Security:
      - Only allowed subcommands are executed (see safety.ALLOWED_SUBCOMMANDS).
      - Arguments are validated against a safe character pattern.
      - Uses create_subprocess_exec (not shell=True) — no shell injection.
      - Enforces a timeout to prevent hung processes.
      - Rate-limited to prevent API abuse.
      - Output is sanitised (prompt injection + sensitive data redaction).

    Performance:
      - Read-only results are cached with a 5-minute TTL.
      - Audit logged for security review.
    """
    tool_name = f"gcloud.{args[0]}" if args else "gcloud"
    t0 = time.monotonic()

    # Validate arguments before execution
    error = validate_gcloud_args(args)
    if error:
        _log(f"BLOCKED: {error}")
        audit_log(tool=tool_name, args=args, success=False, error=error)
        return {
            "error": f"Validation failed: {error}",
            "error_code": "VALIDATION_FAILED",
            "command": f"gcloud {' '.join(args)}",
        }

    # Kill-switch — operator may have halted this principal / tool / globally
    halt = check_halt(tool=tool_name)
    if halt is not None:
        _log(f"HALTED scope={halt.scope} reason={halt.reason}")
        audit_log(
            tool=tool_name, args=args, success=False, halted=True,
            error=f"halted:{halt.scope}:{halt.reason}",
        )
        return {
            "error": f"Operation halted by operator (scope={halt.scope}): {halt.reason}",
            "error_code": "HALTED",
            "command": f"gcloud {' '.join(args)}",
        }

    # Circuit breaker — bail fast if gcloud is currently unhealthy
    try:
        gcloud_breaker.before_call()
    except CircuitOpen as exc:
        _log(f"CIRCUIT OPEN: {exc}")
        audit_log(
            tool=tool_name, args=args, success=False,
            error=f"circuit_open:retry_after={exc.retry_after:.1f}s",
        )
        return {
            "error": f"gcloud circuit breaker open; retry after {exc.retry_after:.1f}s",
            "error_code": "CIRCUIT_OPEN",
            "retry_after_seconds": exc.retry_after,
            "command": f"gcloud {' '.join(args)}",
        }

    # Check cache for read-only operations
    cached_result = cache.get(args, project)
    if cached_result is not None:
        elapsed_ms = (time.monotonic() - t0) * 1000
        _log(f"CACHE HIT: gcloud {' '.join(args)}")
        audit_log(tool=tool_name, args=args, duration_ms=elapsed_ms, cached=True)
        metrics.record(tool_name, elapsed_ms, cached=True)
        return cached_result

    # Rate limiting — wait for a slot (per-principal + global)
    acquired = await rate_limiter.acquire(timeout=30.0)
    if not acquired:
        _log(f"RATE LIMITED: gcloud {' '.join(args)}")
        audit_log(tool=tool_name, args=args, success=False, error="Rate limited")
        return {
            "error": "Too many concurrent gcloud operations. Please retry shortly.",
            "error_code": "RATE_LIMITED",
            "command": f"gcloud {' '.join(args)}",
        }

    cmd = ["gcloud"] + args + ["--format=json"]
    if project:
        cmd += [f"--project={project}"]

    # Log the command (redact --format=json for readability)
    display_cmd = " ".join(a for a in cmd if a != "--format=json")
    _log(f"EXEC: {display_cmd}")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_GCLOUD_TIMEOUT,
        )
    except asyncio.TimeoutError:
        elapsed_ms = (time.monotonic() - t0) * 1000
        _log(f"TIMEOUT: {display_cmd} (>{_GCLOUD_TIMEOUT}s)")
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        gcloud_breaker.record_failure()
        audit_log(tool=tool_name, args=args, duration_ms=elapsed_ms, success=False, error="timeout")
        metrics.record(tool_name, elapsed_ms, success=False)
        return {
            "error": f"Command timed out after {_GCLOUD_TIMEOUT}s",
            "error_code": "TIMEOUT",
            "command": " ".join(cmd),
        }
    finally:
        rate_limiter.release()

    elapsed = time.monotonic() - t0
    elapsed_ms = elapsed * 1000

    if proc.returncode != 0:
        error_msg = stderr.decode().strip()
        _log(f"FAIL: {display_cmd} ({elapsed:.1f}s) — {error_msg[:120]}")
        gcloud_breaker.record_failure()
        audit_log(tool=tool_name, args=args, duration_ms=elapsed_ms, success=False, error=error_msg[:200])
        metrics.record(tool_name, elapsed_ms, success=False)
        return {
            "error": error_msg,
            "error_code": "GCLOUD_ERROR",
            "command": " ".join(cmd),
            "returncode": proc.returncode,
        }

    raw = stdout.decode().strip()
    gcloud_breaker.record_success()

    # Sanitise output (prompt injection defence + sensitive data redaction)
    raw = sanitise_output(raw)

    if not raw:
        _log(f"  OK: {display_cmd} ({elapsed:.1f}s) — empty result")
        result = {"result": [], "command": " ".join(cmd)}
        cache.set(args, project, result)
        audit_log(tool=tool_name, args=args, duration_ms=elapsed_ms)
        metrics.record(tool_name, elapsed_ms)
        return result

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _log(f"  OK: {display_cmd} ({elapsed:.1f}s) — text response")
        result = {"result_text": raw, "command": " ".join(cmd)}
        cache.set(args, project, result)
        audit_log(tool=tool_name, args=args, duration_ms=elapsed_ms)
        metrics.record(tool_name, elapsed_ms)
        return result

    count = len(parsed) if isinstance(parsed, list) else 1
    _log(f"  OK: {display_cmd} ({elapsed:.1f}s) — {count} result(s)")
    result = {"result": parsed, "command": " ".join(cmd)}
    cache.set(args, project, result)
    audit_log(tool=tool_name, args=args, duration_ms=elapsed_ms)
    metrics.record(tool_name, elapsed_ms)
    return result


def register_gcloud_tools(mcp) -> None:
    """Register all gcloud-based VPC-SC tools on the FastMCP server."""

    from vpcsc_mcp.tools.safety import READONLY_GCP, WRITE_GCP

    @mcp.tool(annotations=READONLY_GCP)
    async def list_access_policies(organization_id: str) -> str:
        """List all access policies for an organisation.

        Args:
            organization_id: The GCP organisation ID (numeric).
        """
        result = await run_gcloud([
            "access-context-manager", "policies", "list",
            f"--organization={organization_id}",
        ])
        if "error" in result:
            return f"Error listing policies: {result['error']}"
        policies = result.get("result", [])
        if not policies:
            return f"No access policies found for organisation {organization_id}."
        lines = [f"Found {len(policies)} access policy(ies):\n"]
        for p in policies:
            name = p.get("name", "unknown")
            title = p.get("title", "untitled")
            policy_id = name.split("/")[-1] if "/" in name else name
            lines.append(f"  - Policy ID: {policy_id}")
            lines.append(f"    Title: {title}")
            lines.append(f"    Name: {name}\n")
        return "\n".join(lines)

    @mcp.tool(annotations=READONLY_GCP)
    async def list_perimeters(policy_id: str) -> str:
        """List all VPC Service Control perimeters for an access policy.

        Args:
            policy_id: The access policy ID (numeric).
        """
        result = await run_gcloud([
            "access-context-manager", "perimeters", "list",
            f"--policy={policy_id}",
        ])
        if "error" in result:
            return f"Error listing perimeters: {result['error']}"
        perimeters = result.get("result", [])
        if not perimeters:
            return f"No perimeters found for policy {policy_id}."
        lines = [f"Found {len(perimeters)} perimeter(s):\n"]
        for p in perimeters:
            name = p.get("name", "").split("/")[-1]
            title = p.get("title", "untitled")
            ptype = p.get("perimeterType", "REGULAR")
            status = p.get("status", {})
            resources = status.get("resources", [])
            restricted = status.get("restrictedServices", [])
            lines.append(f"  - {title} ({name})")
            lines.append(f"    Type: {ptype}")
            lines.append(f"    Projects: {len(resources)}")
            lines.append(f"    Restricted services: {len(restricted)}\n")
        return "\n".join(lines)

    @mcp.tool(annotations=READONLY_GCP)
    async def describe_perimeter(policy_id: str, perimeter_name: str) -> str:
        """Get detailed information about a specific VPC-SC perimeter.

        Args:
            policy_id: The access policy ID (numeric).
            perimeter_name: The perimeter name (not the full resource path).
        """
        result = await run_gcloud([
            "access-context-manager", "perimeters", "describe", perimeter_name,
            f"--policy={policy_id}",
        ])
        if "error" in result:
            return f"Error describing perimeter: {result['error']}"
        p = result.get("result", result.get("result_text", {}))
        return json.dumps(p, indent=2) if isinstance(p, (dict, list)) else str(p)

    @mcp.tool(annotations=READONLY_GCP)
    async def list_access_levels(policy_id: str) -> str:
        """List all access levels for an access policy.

        Args:
            policy_id: The access policy ID (numeric).
        """
        result = await run_gcloud([
            "access-context-manager", "levels", "list",
            f"--policy={policy_id}",
        ])
        if "error" in result:
            return f"Error listing access levels: {result['error']}"
        levels = result.get("result", [])
        if not levels:
            return f"No access levels found for policy {policy_id}."
        lines = [f"Found {len(levels)} access level(s):\n"]
        for lev in levels:
            name = lev.get("name", "").split("/")[-1]
            title = lev.get("title", "untitled")
            lines.append(f"  - {title} ({name})")
            basic = lev.get("basic", {})
            conditions = basic.get("conditions", [])
            for cond in conditions:
                if "ipSubnetworks" in cond:
                    lines.append(f"    IP ranges: {', '.join(cond['ipSubnetworks'])}")
                if "members" in cond:
                    lines.append(f"    Members: {', '.join(cond['members'])}")
                if "regions" in cond:
                    lines.append(f"    Regions: {', '.join(cond['regions'])}")
            lines.append("")
        return "\n".join(lines)

    @mcp.tool(annotations=READONLY_GCP)
    async def describe_access_level(policy_id: str, level_name: str) -> str:
        """Get detailed information about a specific access level.

        Args:
            policy_id: The access policy ID (numeric).
            level_name: The access level name (not the full resource path).
        """
        result = await run_gcloud([
            "access-context-manager", "levels", "describe", level_name,
            f"--policy={policy_id}",
        ])
        if "error" in result:
            return f"Error describing access level: {result['error']}"
        lev = result.get("result", result.get("result_text", {}))
        return json.dumps(lev, indent=2) if isinstance(lev, (dict, list)) else str(lev)

    @mcp.tool(annotations=READONLY_GCP)
    async def check_vpc_sc_violations(
        project_id: str,
        freshness: str = "7d",
        limit: int = 25,
    ) -> str:
        """Query Cloud Audit Logs for VPC Service Controls violations.

        Args:
            project_id: The GCP project ID to query logs in.
            freshness: How far back to search (e.g. '1d', '7d', '30d'). Default '7d'.
            limit: Maximum number of log entries to return. Default 25.
        """
        log_filter = (
            'protoPayload.metadata.@type='
            '"type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata"'
        )
        result = await run_gcloud([
            "logging", "read", log_filter,
            f"--project={project_id}",
            f"--freshness={freshness}",
            f"--limit={limit}",
        ])
        if "error" in result:
            return f"Error querying violations: {result['error']}"
        entries = result.get("result", [])
        if not entries:
            return f"No VPC-SC violations found in project {project_id} (last {freshness})."

        lines = [f"Found {len(entries)} VPC-SC violation(s) in last {freshness}:\n"]
        for entry in entries:
            proto = entry.get("protoPayload", {})
            metadata = proto.get("metadata", {})
            timestamp = entry.get("timestamp", "unknown")
            service = proto.get("serviceName", "unknown")
            method = proto.get("methodName", "unknown")
            violation = metadata.get("violationReason", "unknown")
            dry_run = metadata.get("dryRun", False)
            resource = proto.get("resourceName", "unknown")
            caller = proto.get("authenticationInfo", {}).get("principalEmail", "unknown")

            mode = " [DRY-RUN]" if dry_run else " [ENFORCED]"
            lines.append(f"  {timestamp}{mode}")
            lines.append(f"    Violation: {violation}")
            lines.append(f"    Service: {service}")
            lines.append(f"    Method: {method}")
            lines.append(f"    Resource: {resource}")
            lines.append(f"    Caller: {caller}\n")
        return "\n".join(lines)

    @mcp.tool(annotations=READONLY_GCP)
    async def dry_run_status(policy_id: str) -> str:
        """List all perimeters that have a dry-run configuration pending enforcement.

        Args:
            policy_id: The access policy ID (numeric).
        """
        result = await run_gcloud([
            "access-context-manager", "perimeters", "list",
            f"--policy={policy_id}",
        ])
        if "error" in result:
            return f"Error listing perimeters: {result['error']}"
        perimeters = result.get("result", [])
        dry_run_perimeters = [
            p for p in perimeters
            if p.get("useExplicitDryRunSpec") or p.get("spec")
        ]
        if not dry_run_perimeters:
            return f"No perimeters with dry-run configurations found in policy {policy_id}."

        lines = [f"Found {len(dry_run_perimeters)} perimeter(s) with dry-run config:\n"]
        for p in dry_run_perimeters:
            name = p.get("name", "").split("/")[-1]
            title = p.get("title", "untitled")
            spec = p.get("spec", {})
            status = p.get("status", {})
            spec_resources = set(spec.get("resources", []))
            status_resources = set(status.get("resources", []))
            new_resources = spec_resources - status_resources
            spec_services = set(spec.get("restrictedServices", []))
            status_services = set(status.get("restrictedServices", []))
            new_services = spec_services - status_services

            lines.append(f"  - {title} ({name})")
            if new_resources:
                lines.append(f"    New projects in dry-run: {len(new_resources)}")
            if new_services:
                lines.append(f"    New restricted services in dry-run: {', '.join(new_services)}")
            lines.append(
                "    To enforce: gcloud access-context-manager perimeters "
                f"dry-run enforce {name} --policy={policy_id}\n"
            )
        return "\n".join(lines)

    @mcp.tool(annotations=READONLY_GCP)
    async def list_supported_services_live() -> str:
        """Query the live list of VPC-SC supported services from the Access Context Manager API.

        This returns the canonical, up-to-date list of all services that
        support VPC Service Controls, including their support stage (GA,
        Preview) and whether they are available on the restricted VIP.
        """
        result = await run_gcloud([
            "access-context-manager", "supported-services", "list",
        ])
        if "error" in result:
            return f"Error listing supported services: {result['error']}"
        services = result.get("result", [])
        if not services:
            return "No supported services returned. Ensure you have an active access policy."

        ga_services = []
        preview_services = []
        for svc in services:
            name = svc.get("serviceName", svc.get("name", "unknown"))
            title = svc.get("title", "")
            stage = svc.get("serviceSupportStage", svc.get("serviceStatus", "UNKNOWN"))
            restricted_vip = svc.get("availableOnRestrictedVip", svc.get("restrictedVipStatus", ""))
            entry = f"  {name}"
            if title:
                entry += f" ({title})"
            if restricted_vip in ("TRUE", True):
                entry += " [restricted-VIP]"
            if "GA" in str(stage).upper():
                ga_services.append(entry)
            else:
                preview_services.append(entry)

        lines = [f"VPC-SC Supported Services (live, {len(services)} total)\n"]
        if ga_services:
            lines.append(f"GA ({len(ga_services)}):")
            lines.extend(sorted(ga_services))
            lines.append("")
        if preview_services:
            lines.append(f"Preview / Other ({len(preview_services)}):")
            lines.extend(sorted(preview_services))

        return "\n".join(lines)

    @mcp.tool(annotations=READONLY_GCP)
    async def describe_supported_service(service_name: str) -> str:
        """Get detailed VPC-SC support information for a specific service, including supported methods.

        Returns the service's VPC-SC support stage, restricted VIP availability,
        known limitations, and the full list of methods/permissions that can be
        used in ingress/egress rule method selectors.

        Args:
            service_name: The service API name (e.g. 'bigquery.googleapis.com').
        """
        svc = service_name.strip()
        if not svc.endswith(".googleapis.com"):
            svc = f"{svc}.googleapis.com"

        result = await run_gcloud([
            "access-context-manager", "supported-services", "describe", svc,
        ])
        if "error" in result:
            return f"Error describing service {svc}: {result['error']}"

        data = result.get("result", result.get("result_text", {}))
        if isinstance(data, str):
            return data

        if not isinstance(data, dict):
            return json.dumps(data, indent=2) if data else f"No data returned for {svc}."

        title = data.get("title", svc)
        stage = data.get("serviceSupportStage", "UNKNOWN")
        restricted_vip = data.get("availableOnRestrictedVip", "UNKNOWN")
        limitations = data.get("knownLimitations", False)
        methods = data.get("supportedMethods", [])

        lines = [
            f"Service: {svc} ({title})",
            f"VPC-SC Support: {stage}",
            f"Available on restricted VIP: {restricted_vip}",
            f"Known limitations: {'Yes' if limitations else 'No'}",
        ]

        if methods:
            lines.append(f"\nSupported methods/permissions ({len(methods)}):")
            for m in methods:
                method = m.get("method", "")
                permission = m.get("permission", "")
                if method:
                    lines.append(f"  method: {method}")
                elif permission:
                    lines.append(f"  permission: {permission}")
            lines.append(
                "\nThese are the exact selectors you can use in ingress/egress rules."
            )
        else:
            lines.append("\nNo method-level restrictions listed (use {'method': '*'} for all).")

        return "\n".join(lines)

    @mcp.tool(annotations=WRITE_GCP)
    async def update_perimeter_resources(
        policy_id: str,
        perimeter_name: str,
        add_projects: list[str] | None = None,
        remove_projects: list[str] | None = None,
        confirm: bool = False,
    ) -> str:
        """Add or remove projects from a VPC-SC perimeter.

        WRITE OPERATION: modifies live infrastructure. Set confirm=True to execute.

        Args:
            policy_id: The access policy ID (numeric).
            perimeter_name: The perimeter name.
            add_projects: Project numbers to add (format: 'projects/123456').
            remove_projects: Project numbers to remove (format: 'projects/123456').
            confirm: Must be True to execute. Returns a preview if False.
        """
        if not add_projects and not remove_projects:
            return "Error: specify at least one of add_projects or remove_projects."

        # Validate project format
        for p in (add_projects or []) + (remove_projects or []):
            if not p.startswith("projects/"):
                return f"Error: '{p}' must start with 'projects/'. Example: 'projects/123456'."

        args = ["access-context-manager", "perimeters", "update", perimeter_name, f"--policy={policy_id}"]
        changes = []
        if add_projects:
            args.append(f"--add-resources={','.join(add_projects)}")
            changes.append(f"  ADD: {', '.join(add_projects)}")
        if remove_projects:
            args.append(f"--remove-resources={','.join(remove_projects)}")
            changes.append(f"  REMOVE: {', '.join(remove_projects)}")

        if not confirm:
            _log(f"PREVIEW: update_perimeter_resources({perimeter_name}) — confirm=False, showing preview only")
            return (
                f"PREVIEW — This will modify perimeter '{perimeter_name}' (policy {policy_id}):\n"
                + "\n".join(changes)
                + "\n\nSet confirm=True to execute this change."
            )

        _log(f"WRITE: update_perimeter_resources({perimeter_name}) — confirm=True, executing")
        result = await run_gcloud(args)
        if "error" in result:
            return f"Error updating perimeter: {result['error']}"
        return f"Successfully updated perimeter {perimeter_name}.\n" + "\n".join(changes)

    @mcp.tool(annotations=READONLY_GCP)
    async def list_dry_run_perimeters(policy_id: str) -> str:
        """List the effective dry-run configuration across all service perimeters.

        Shows each perimeter's dry-run config status (Inherited / Modified /
        New / Deleted). Use this before enforce_dry_run_perimeter to confirm
        a perimeter has an explicit dry-run spec ready to promote.

        Args:
            policy_id: The access policy ID (numeric).
        """
        result = await run_gcloud([
            "access-context-manager", "perimeters", "dry-run", "list",
            f"--policy={policy_id}",
        ])
        if "error" in result:
            return f"Error listing dry-run configs: {result['error']}"
        entries = result.get("result", result.get("result_text", []))
        if not entries:
            return f"No dry-run perimeter configurations in policy {policy_id}."
        if isinstance(entries, str):
            return entries
        lines = [f"Dry-run perimeter configurations in policy {policy_id}:\n"]
        for e in entries:
            name = e.get("name", "unknown").split("/")[-1] if isinstance(e, dict) else str(e)
            lines.append(f"  - {name}")
        lines.append(
            "\nUse enforce_dry_run_perimeter(perimeter_name=...) to promote a\n"
            "single perimeter's dry-run spec, or enforce_all_dry_run_perimeters\n"
            "to commit all modified perimeters atomically.",
        )
        return "\n".join(lines)

    @mcp.tool(annotations=WRITE_GCP)
    async def enforce_dry_run_perimeter(
        policy_id: str,
        perimeter_name: str,
        confirm: bool = False,
    ) -> str:
        """Promote a perimeter's dry-run spec to its enforced status.

        WRITE OPERATION — changes the live enforcement posture of a perimeter.
        Copies spec → status and clears useExplicitDryRunSpec. Fails if the
        perimeter has no explicit dry-run configuration or if the dry-run
        config is incompatible with the rest of the policy.

        Args:
            policy_id: The access policy ID (numeric).
            perimeter_name: The perimeter name (short form, not full resource path).
            confirm: Must be True to execute. Preview-only when False.
        """
        if not confirm:
            _log(f"PREVIEW: enforce_dry_run_perimeter({perimeter_name}) — confirm=False")
            return (
                f"PREVIEW — This will PROMOTE dry-run spec → enforced status for\n"
                f"perimeter '{perimeter_name}' in policy {policy_id}.\n\n"
                f"Before confirming:\n"
                f"  1. Review dry-run audit logs via check_vpc_sc_violations (dryRun=true)\n"
                f"  2. Ensure no unexpected violations remain\n"
                f"  3. Coordinate with perimeter owners — this is irreversible\n\n"
                f"Set confirm=True to execute."
            )

        _log(f"WRITE: enforce_dry_run_perimeter({perimeter_name}) — confirm=True, executing")
        result = await run_gcloud([
            "access-context-manager", "perimeters", "dry-run", "enforce",
            perimeter_name,
            f"--policy={policy_id}",
        ])
        if "error" in result:
            return f"Error enforcing dry-run config: {result['error']}"
        return (
            f"Successfully enforced dry-run configuration for perimeter {perimeter_name}.\n"
            f"Note: changes may take up to 30 minutes to propagate."
        )

    @mcp.tool(annotations=WRITE_GCP)
    async def enforce_all_dry_run_perimeters(
        policy_id: str,
        etag: str | None = None,
        confirm: bool = False,
    ) -> str:
        """Promote dry-run spec → enforced status for ALL modified perimeters in a policy.

        WRITE OPERATION — atomic commit across every perimeter in the policy
        that has a modified dry-run spec. Fails the whole operation if any
        perimeter's dry-run config is incompatible. Optionally gate the
        operation on an etag to detect concurrent policy modifications.

        Args:
            policy_id: The access policy ID (numeric).
            etag: Optional access-policy etag — fails if the policy has changed
                since this etag was read (list_access_policies returns etags).
            confirm: Must be True to execute. Preview-only when False.
        """
        if not confirm:
            _log("PREVIEW: enforce_all_dry_run_perimeters — confirm=False")
            return (
                f"PREVIEW — This will promote dry-run → enforced for every modified\n"
                f"perimeter in policy {policy_id}.\n\n"
                f"CAUTION: this is an ORG-WIDE change. Coordinate with every team\n"
                f"that owns perimeters in this policy before proceeding. Any single\n"
                f"perimeter failing will abort the whole operation.\n\n"
                f"Set confirm=True to execute."
            )

        _log("WRITE: enforce_all_dry_run_perimeters — confirm=True, executing")
        args = [
            "access-context-manager", "perimeters", "dry-run", "enforce-all",
            f"--policy={policy_id}",
        ]
        if etag:
            args.append(f"--etag={etag}")
        result = await run_gcloud(args)
        if "error" in result:
            return f"Error enforcing dry-run configs: {result['error']}"
        return (
            f"Successfully enforced dry-run configurations for all modified\n"
            f"perimeters in policy {policy_id}. Changes may take up to 30 minutes\n"
            f"to propagate."
        )

    @mcp.tool(annotations=WRITE_GCP)
    async def update_perimeter_services(
        policy_id: str,
        perimeter_name: str,
        add_services: list[str] | None = None,
        remove_services: list[str] | None = None,
        confirm: bool = False,
    ) -> str:
        """Add or remove restricted services from a VPC-SC perimeter.

        WRITE OPERATION: modifies live infrastructure. Set confirm=True to execute.

        Args:
            policy_id: The access policy ID (numeric).
            perimeter_name: The perimeter name.
            add_services: Services to add (e.g. 'storage.googleapis.com').
            remove_services: Services to remove.
            confirm: Must be True to execute. Returns a preview if False.
        """
        if not add_services and not remove_services:
            return "Error: specify at least one of add_services or remove_services."

        # Validate service format
        for s in (add_services or []) + (remove_services or []):
            if not s.endswith(".googleapis.com"):
                return f"Error: '{s}' must end with '.googleapis.com'."

        args = ["access-context-manager", "perimeters", "update", perimeter_name, f"--policy={policy_id}"]
        changes = []
        if add_services:
            args.append(f"--add-restricted-services={','.join(add_services)}")
            changes.append(f"  ADD: {', '.join(add_services)}")
        if remove_services:
            args.append(f"--remove-restricted-services={','.join(remove_services)}")
            changes.append(f"  REMOVE: {', '.join(remove_services)}")

        if not confirm:
            _log(f"PREVIEW: update_perimeter_services({perimeter_name}) — confirm=False, showing preview only")
            return (
                f"PREVIEW — This will modify perimeter '{perimeter_name}' (policy {policy_id}):\n"
                + "\n".join(changes)
                + "\n\nSet confirm=True to execute this change."
            )

        _log(f"WRITE: update_perimeter_services({perimeter_name}) — confirm=True, executing")
        result = await run_gcloud(args)
        if "error" in result:
            return f"Error updating perimeter services: {result['error']}"
        return f"Successfully updated restricted services for perimeter {perimeter_name}.\n" + "\n".join(changes)
