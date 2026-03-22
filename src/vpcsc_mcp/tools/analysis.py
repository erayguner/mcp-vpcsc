"""Tools for analysing VPC-SC configurations, troubleshooting violations, and recommending services."""

from __future__ import annotations

import json

from vpcsc_mcp.data.patterns import TROUBLESHOOTING_GUIDE
from vpcsc_mcp.data.services import (
    SERVICE_METHOD_SELECTORS,
    SUPPORTED_SERVICES,
    WORKLOAD_RECOMMENDATIONS,
)
from vpcsc_mcp.tools.gcloud_ops import _log


def register_analysis_tools(mcp) -> None:
    """Register all analysis and troubleshooting tools on the FastMCP server."""

    from vpcsc_mcp.tools.safety import DIAGNOSTIC, GENERATE

    @mcp.tool(annotations=GENERATE)
    def troubleshoot_violation(violation_reason: str) -> str:
        """Get troubleshooting guidance for a VPC-SC violation reason code.

        Args:
            violation_reason: The violation reason from audit logs
                (e.g. 'RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER',
                'NO_MATCHING_ACCESS_LEVEL').
        """
        reason = violation_reason.upper().strip()
        _log(f"TOOL: troubleshoot_violation({reason})")
        guide = TROUBLESHOOTING_GUIDE.get(reason)
        if not guide:
            known = ", ".join(TROUBLESHOOTING_GUIDE.keys())
            return (
                f"Unknown violation reason: {violation_reason}\n\n"
                f"Known violation types: {known}\n\n"
                "For unrecognised violations, check the Cloud Audit Logs for the full metadata "
                "and use the VPC-SC Violation Analyser in the Google Cloud Console."
            )

        lines = [
            f"Violation: {reason}",
            f"\nMeaning: {guide['meaning']}",
            "\nCommon causes:",
        ]
        for cause in guide["common_causes"]:
            lines.append(f"  - {cause}")
        lines.append("\nResolution steps:")
        for step in guide["resolution_steps"]:
            lines.append(f"  {step}")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def recommend_restricted_services(workload_type: str) -> str:
        """Recommend restricted services for a VPC-SC perimeter based on workload type.

        Args:
            workload_type: The workload type. Options: 'ai-ml', 'data-analytics',
                'web-application', 'data-warehouse', 'healthcare'.
        """
        key = workload_type.lower().strip().replace(" ", "-")
        _log(f"TOOL: recommend_restricted_services({key})")
        rec = WORKLOAD_RECOMMENDATIONS.get(key)
        if not rec:
            available = ", ".join(WORKLOAD_RECOMMENDATIONS.keys())
            return (
                f"Unknown workload type: {workload_type}\n"
                f"Available types: {available}\n\n"
                "You can also use 'list_supported_services' to see all VPC-SC supported services."
            )

        lines = [
            f"Workload: {rec['description']}",
            "\nRequired services (must be in perimeter):",
        ]
        for svc in rec["required"]:
            display = SUPPORTED_SERVICES.get(svc, svc)
            lines.append(f"  - {svc} ({display})")
        lines.append("\nRecommended services:")
        for svc in rec["recommended"]:
            display = SUPPORTED_SERVICES.get(svc, svc)
            lines.append(f"  - {svc} ({display})")
        lines.append("\nNotes:")
        for note in rec["notes"]:
            lines.append(f"  - {note}")
        lines.append(f"\nTotal: {len(rec['required'])} required + {len(rec['recommended'])} recommended")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def list_supported_services(filter_keyword: str | None = None) -> str:
        """List GCP services that support VPC Service Controls.

        Args:
            filter_keyword: Optional keyword to filter services (e.g. 'bigquery', 'storage', 'ai').
        """
        services = SUPPORTED_SERVICES
        if filter_keyword:
            kw = filter_keyword.lower()
            services = {
                k: v for k, v in services.items()
                if kw in k.lower() or kw in v.lower()
            }

        if not services:
            return f"No services matched filter '{filter_keyword}'."

        lines = [f"VPC-SC supported services ({len(services)} total):\n"]
        for api, display in sorted(services.items()):
            lines.append(f"  {api} — {display}")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def check_service_support(service_name: str) -> str:
        """Check if a specific GCP service supports VPC Service Controls.

        Args:
            service_name: The service API name (e.g. 'storage.googleapis.com') or partial name (e.g. 'storage').
        """
        svc = service_name.strip().lower()
        if not svc.endswith(".googleapis.com"):
            svc_full = f"{svc}.googleapis.com"
        else:
            svc_full = svc

        if svc_full in SUPPORTED_SERVICES:
            display = SUPPORTED_SERVICES[svc_full]
            methods = SERVICE_METHOD_SELECTORS.get(svc_full, {})
            lines = [
                f"'{svc_full}' ({display}) supports VPC Service Controls.",
            ]
            if methods:
                lines.append(f"\nAvailable method selector presets: {', '.join(methods.keys())}")
                for preset_name, selectors in methods.items():
                    lines.append(f"\n  {preset_name}:")
                    for sel in selectors:
                        key = "method" if "method" in sel else "permission"
                        lines.append(f"    - {key}: {sel[key]}")
            return "\n".join(lines)

        # Fuzzy match
        partial = svc.replace(".googleapis.com", "")
        matches = {k: v for k, v in SUPPORTED_SERVICES.items() if partial in k.lower() or partial in v.lower()}
        if matches:
            lines = [f"'{service_name}' not found exactly. Did you mean one of these?\n"]
            for api, display in matches.items():
                lines.append(f"  {api} — {display}")
            return "\n".join(lines)

        return (
            f"'{service_name}' is not in the known VPC-SC supported services list.\n\n"
            "This may mean:\n"
            "  1. The service does not support VPC-SC\n"
            "  2. The service was recently added and our list is not yet updated\n"
            "  3. The service name may be different — check https://cloud.google.com/vpc-service-controls/docs/supported-products"
        )

    @mcp.tool(annotations=GENERATE)
    def get_method_selectors(service_name: str, access_type: str = "all") -> str:
        """Get pre-defined method selectors for a service, useful for building ingress/egress rules.

        Args:
            service_name: The GCP service API name (e.g. 'bigquery.googleapis.com').
            access_type: The access pattern. Options depend on service, common ones:
                'read', 'write', 'all', 'admin'. Default 'all'.
        """
        svc = service_name.strip()
        if not svc.endswith(".googleapis.com"):
            svc = f"{svc}.googleapis.com"

        methods = SERVICE_METHOD_SELECTORS.get(svc)
        if not methods:
            return (
                f"No pre-defined method selectors for '{svc}'.\n"
                "Available services with selectors: "
                + ", ".join(SERVICE_METHOD_SELECTORS.keys())
                + "\n\nFor other services, use {'method': '*'} to allow all methods."
            )

        preset = methods.get(access_type.lower())
        if not preset:
            available = ", ".join(methods.keys())
            return f"Access type '{access_type}' not found for {svc}. Available: {available}"

        lines = [f"Method selectors for {svc} ({access_type}):\n"]
        for sel in preset:
            key = "method" if "method" in sel else "permission"
            lines.append(f"  {key}: {sel[key]}")
        lines.append(f"\nJSON (for use in ingress/egress tool args):\n{json.dumps(preset, indent=2)}")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def validate_identity_format(identities: list[str]) -> str:
        """Validate that identity strings are correctly formatted for VPC-SC rules.

        Args:
            identities: List of identity strings to validate.
        """
        valid_prefixes = ("serviceAccount:", "user:", "group:")
        issues = []
        valid = []

        for identity in identities:
            identity = identity.strip()
            if not identity:
                issues.append("  - Empty identity string")
                continue

            has_valid_prefix = any(identity.startswith(p) for p in valid_prefixes)
            if not has_valid_prefix:
                issues.append(
                    f"  - '{identity}': missing prefix. Must start with one of: "
                    + ", ".join(valid_prefixes)
                )
                # Suggest correction
                if "@" in identity and "." in identity:
                    if "gserviceaccount.com" in identity:
                        issues.append(f"    Suggested: serviceAccount:{identity}")
                    elif identity.count("@") == 1:
                        issues.append(f"    Suggested: user:{identity}")
            else:
                # Check the email portion
                parts = identity.split(":", 1)
                email = parts[1] if len(parts) > 1 else ""
                if "@" not in email:
                    issues.append(f"  - '{identity}': missing @ in email portion")
                else:
                    valid.append(identity)

        lines = []
        if valid:
            lines.append(f"Valid identities ({len(valid)}):")
            for v in valid:
                lines.append(f"  - {v}")
        if issues:
            lines.append(f"\nIssues found ({len(issues)}):")
            lines.extend(issues)
        if not issues:
            lines.append("\nAll identities are correctly formatted.")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def analyze_perimeter_design(
        project_count: int,
        services: list[str],
        has_cross_project_queries: bool = False,
        has_external_access: bool = False,
        workload_type: str = "general",
    ) -> str:
        """Analyze a planned perimeter design and provide recommendations.

        Args:
            project_count: Number of projects in the perimeter.
            services: List of restricted services planned.
            has_cross_project_queries: Whether BigQuery cross-project queries are needed.
            has_external_access: Whether external users/services need access.
            workload_type: The primary workload type for additional recommendations.
        """
        findings = []
        warnings = []
        recommendations = []

        # Check project count
        if project_count > 50:
            warnings.append(
                "Large perimeter (>50 projects) — consider splitting into domain-specific perimeters "
                "connected with bridges for easier management."
            )
        elif project_count == 1:
            recommendations.append(
                "Single-project perimeter. Consider whether related projects should be grouped together."
            )

        # Check services
        essential = {"storage.googleapis.com", "logging.googleapis.com"}
        missing_essential = essential - set(services)
        if missing_essential:
            warnings.append(
                f"Missing commonly-needed services: {', '.join(missing_essential)}. "
                "Most workloads need Cloud Storage and Logging."
            )

        # Check BigQuery cross-project
        if has_cross_project_queries:
            if "bigquery.googleapis.com" not in services:
                warnings.append(
                    "Cross-project BigQuery queries planned but "
                    "bigquery.googleapis.com not in restricted services."
                )
            recommendations.append(
                "For cross-project BigQuery: you'll need both ingress rules (on data project perimeter) "
                "and egress rules (on query project perimeter). This is the #1 source of VPC-SC violations."
            )

        # Check external access
        if has_external_access:
            recommendations.append(
                "External access needed — create access levels for corporate network IPs "
                "and/or identity-based ingress rules for specific service accounts."
            )

        # Dry-run recommendation
        recommendations.append(
            "Always start in dry-run mode to identify violations before enforcing. "
            "Review Cloud Audit Logs for at least 1-2 weeks."
        )

        # Workload-specific
        rec = WORKLOAD_RECOMMENDATIONS.get(workload_type.lower().replace(" ", "-"))
        if rec:
            missing_required = set(rec["required"]) - set(services)
            if missing_required:
                warnings.append(
                    f"For {workload_type} workloads, these services are typically required: "
                    + ", ".join(missing_required)
                )

        lines = [f"Perimeter Design Analysis ({project_count} projects, {len(services)} services)\n"]

        if warnings:
            lines.append(f"Warnings ({len(warnings)}):")
            for w in warnings:
                lines.append(f"  - {w}")
            lines.append("")

        if findings:
            lines.append(f"Findings ({len(findings)}):")
            for f in findings:
                lines.append(f"  - {f}")
            lines.append("")

        lines.append(f"Recommendations ({len(recommendations)}):")
        for r in recommendations:
            lines.append(f"  - {r}")

        return "\n".join(lines)

    @mcp.tool(annotations=DIAGNOSTIC)
    async def check_data_freshness(project_id: str | None = None) -> str:
        """Check if the MCP server's built-in data is up to date.

        Compares the built-in VPC-SC supported services list against the APIs
        actually available in your GCP project. Reports any services that support
        VPC-SC but are missing from the server's knowledge base, and any in the
        knowledge base that may have been removed.

        Also reports the current server version and data counts.

        Args:
            project_id: GCP project ID. Leave empty for active gcloud project.
        """
        from vpcsc_mcp.tools.gcloud_ops import _log, run_gcloud
        from vpcsc_mcp.tools.org_policy import EXPECTED_POLICIES

        _log("TOOL: check_data_freshness()")

        lines = [
            "DATA FRESHNESS CHECK",
            "=" * 50,
            "",
            "Server version: 0.1.0",
            f"Built-in VPC-SC services: {len(SUPPORTED_SERVICES)}",
            f"Built-in org policies: {len(EXPECTED_POLICIES)}",
            f"Built-in workload profiles: {len(WORKLOAD_RECOMMENDATIONS)}",
            f"Built-in method selector sets: {len(SERVICE_METHOD_SELECTORS)}",
            "",
        ]

        # Check for services enabled in the project that we don't know about
        if not project_id:
            result = await run_gcloud(["config", "get-value", "project"])
            raw = result.get("result_text", result.get("result", ""))
            project_id = raw.strip().strip('"') if isinstance(raw, str) else str(raw)

        if project_id and project_id != "None":
            api_result = await run_gcloud(["services", "list", "--enabled"], project=project_id)
            if "error" not in api_result:
                enabled = set()
                for svc in api_result.get("result", []):
                    name = svc.get("config", {}).get("name", "")
                    if name.endswith(".googleapis.com"):
                        enabled.add(name)

                # APIs the project has that we don't track
                unknown = sorted(enabled - set(SUPPORTED_SERVICES.keys()))
                # Filter to likely VPC-SC candidates (not all APIs support VPC-SC)
                candidates = [a for a in unknown if not any(
                    skip in a for skip in [
                        "serviceusage", "servicemanagement", "cloudapis",
                        "oslogin", "iamcredentials", "cloudtrace",
                        "stackdriver", "clouddebugger", "source",
                        "testing", "firebase", "fcm", "identitytoolkit",
                        "securetoken", "maps", "places", "geocoding",
                        "translate", "sheets", "drive", "calendar",
                        "chat", "meet", "admin", "groupssettings",
                        "people", "youtube", "playintegrity",
                        "analyticshub", "analyticsadmin", "orgpolicy",
                        "essentialcontacts", "recommender",
                    ]
                )]

                if candidates:
                    lines.append(f"POTENTIALLY MISSING from knowledge base ({len(candidates)}):")
                    lines.append("  These APIs are enabled in your project and might support VPC-SC:")
                    for api in candidates:
                        lines.append(f"    [CHECK] {api}")
                    lines.append("  Verify at: https://cloud.google.com/vpc-service-controls/docs/supported-products")
                    lines.append("")
                else:
                    lines.append("No unknown VPC-SC candidate APIs found in your project.")
                    lines.append("")

        # Update instructions
        lines.append("HOW TO UPDATE")
        lines.append("-" * 50)
        lines.append("")
        lines.append("1. VPC-SC services (most frequent changes):")
        lines.append("   Edit: src/vpcsc_mcp/data/services.py")
        lines.append("   Check: https://cloud.google.com/vpc-service-controls/docs/supported-products")
        lines.append("")
        lines.append("2. Org policies (occasional changes):")
        lines.append("   Edit: src/vpcsc_mcp/tools/org_policy.py (EXPECTED_POLICIES dict)")
        lines.append("   Check: https://cloud.google.com/resource-manager/docs/organization-policy/org-policy-constraints")
        lines.append("")
        lines.append("3. Method selectors (rarely change):")
        lines.append("   Edit: src/vpcsc_mcp/data/services.py (SERVICE_METHOD_SELECTORS dict)")
        lines.append("   Check: API reference docs for each service")
        lines.append("")
        lines.append("4. Ingress/egress patterns (add new ones as needed):")
        lines.append("   Edit: src/vpcsc_mcp/data/patterns.py")
        lines.append("")
        lines.append("After editing, run: python -m pytest tests/ -q")

        return "\n".join(lines)
