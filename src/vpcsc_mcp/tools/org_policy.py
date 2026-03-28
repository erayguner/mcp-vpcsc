"""Tools for diagnosing Organisation Policy compliance and recommending configurations."""

from __future__ import annotations

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from vpcsc_mcp.data.policies import EXPECTED_POLICIES
from vpcsc_mcp.tools.gcloud_ops import _log, run_gcloud


def register_org_policy_tools(mcp) -> None:
    """Register Organisation Policy diagnostic tools."""

    from vpcsc_mcp.tools.safety import DIAGNOSTIC

    @mcp.tool(annotations=DIAGNOSTIC)
    async def diagnose_org_policies(
        project_id: str | None = None,
        ctx: Context[ServerSession, None] | None = None,
    ) -> str:
        """Run an Organisation Policy compliance diagnostic on the current project.

        Checks which org policies are applied, identifies non-compliant or missing
        policies, and recommends fixes. Classifies each policy as COMPLIANT,
        NON-COMPLIANT, or NOT SET.

        Args:
            project_id: GCP project ID. Leave empty to use the active gcloud project.
        """
        total_steps = 5
        step = 0

        async def progress(message: str) -> None:
            nonlocal step
            step += 1
            _log(f"[org-policy {step}/{total_steps}] {message}")
            if ctx:
                try:
                    await ctx.report_progress(progress=step, total=total_steps, message=message)
                    await ctx.info(message)
                except Exception:
                    pass

        sections: list[str] = []

        # ── Resolve project ──────────────────────────────────────────
        await progress("Resolving project...")
        if not project_id:
            result = await run_gcloud(["config", "get-value", "project"])
            if "error" in result:
                return "No active gcloud project. Set one with 'gcloud config set project PROJECT_ID'."
            raw = result.get("result_text", result.get("result", ""))
            project_id = raw.strip().strip('"') if isinstance(raw, str) else str(raw)
            if not project_id or project_id == "None":
                return "No active gcloud project set."

        sections.append(f"ORGANISATION POLICY DIAGNOSTIC: {project_id}")
        sections.append("=" * 60)

        # ── Get effective org policies on the project ────────────────
        await progress("Fetching effective org policies...")
        pol_result = await run_gcloud([
            "org-policies", "list",
            f"--project={project_id}",
        ])

        applied_constraints: dict[str, dict] = {}
        if "error" not in pol_result:
            for pol in pol_result.get("result", []):
                constraint = pol.get("constraint", pol.get("name", ""))
                # Normalise: remove "constraints/" prefix if present
                constraint = constraint.replace("constraints/", "").replace("policies/", "")
                applied_constraints[constraint] = pol
            sections.append(f"\n  Found {len(applied_constraints)} org policy(ies) applied to this project.")
        else:
            sections.append(f"\n  Could not list org policies: {pol_result['error']}")
            sections.append("  Ensure you have roles/orgpolicy.policyViewer on the project or org.")

        # ── Describe each expected policy ────────────────────────────
        await progress("Checking each policy against expected baseline...")
        compliant: list[str] = []
        non_compliant: list[str] = []
        not_set: list[str] = []

        for constraint_id, expected in EXPECTED_POLICIES.items():
            short_id = constraint_id.split("/")[-1] if "/" in constraint_id else constraint_id

            # Check if this constraint is in the applied list
            found = None
            for applied_key in applied_constraints:
                if short_id in applied_key or constraint_id in applied_key:
                    found = applied_constraints[applied_key]
                    break

            if found is None:
                # Try to describe it directly
                desc_result = await run_gcloud([
                    "org-policies", "describe", constraint_id,
                    f"--project={project_id}",
                ])
                if "error" not in desc_result:
                    found = desc_result.get("result", desc_result.get("result_text", {}))

            if found is None or (isinstance(found, dict) and not found):
                not_set.append(constraint_id)
            else:
                # Check if it's actually enforced
                spec = found if isinstance(found, dict) else {}
                rules = spec.get("spec", spec).get("rules", spec.get("rules", []))
                is_enforced = False
                for rule in (rules if isinstance(rules, list) else []):
                    if isinstance(rule, dict):
                        if rule.get("enforce") == "TRUE":
                            is_enforced = True
                        if rule.get("values") or rule.get("allowAll") == "FALSE" or rule.get("denyAll") == "TRUE":
                            is_enforced = True
                if is_enforced or expected["expected"] == "restricted":
                    compliant.append(constraint_id)
                else:
                    non_compliant.append(constraint_id)

        # ── Build report ─────────────────────────────────────────────
        await progress("Building compliance report...")

        # Compliant
        if compliant:
            sections.append(f"\n--- COMPLIANT ({len(compliant)}) ---")
            for c in sorted(compliant):
                p = EXPECTED_POLICIES[c]
                sections.append(f"  [COMPLIANT] {c}")
                sections.append(f"    {p['description']}")

        # Non-compliant
        if non_compliant:
            sections.append(f"\n--- NON-COMPLIANT ({len(non_compliant)}) ---")
            for c in sorted(non_compliant):
                p = EXPECTED_POLICIES[c]
                sections.append(f"  [NON-COMPLIANT] {c}  (risk: {p['risk']})")
                sections.append(f"    {p['description']}")
                sections.append(f"    Why: {p['rationale']}")

        # Not set
        if not_set:
            sections.append(f"\n--- NOT SET ({len(not_set)}) ---")
            for c in sorted(not_set):
                p = EXPECTED_POLICIES[c]
                sections.append(f"  [NOT SET] {c}  (risk: {p['risk']})")
                sections.append(f"    {p['description']}")
                sections.append(f"    Why: {p['rationale']}")

        # ── Recommendations ──────────────────────────────────────────
        await progress("Generating recommendations...")
        sections.append("\n--- RECOMMENDED ACTIONS ---")

        if non_compliant or not_set:
            high_risk = [c for c in non_compliant + not_set if EXPECTED_POLICIES[c]["risk"] == "HIGH"]
            med_risk = [c for c in non_compliant + not_set if EXPECTED_POLICIES[c]["risk"] == "MEDIUM"]

            if high_risk:
                sections.append(f"\n  HIGH RISK — fix immediately ({len(high_risk)}):")
                for c in sorted(high_risk):
                    p = EXPECTED_POLICIES[c]
                    sections.append(f"    {c}: {p['description']}")
                    if p["expected"] == "enforced":
                        sections.append(f"      gcloud org-policies set-policy policy.yaml --project={project_id}")
                        sections.append(f"      # where policy.yaml enforces {c}")

            if med_risk:
                sections.append(f"\n  MEDIUM RISK — fix in next sprint ({len(med_risk)}):")
                for c in sorted(med_risk):
                    p = EXPECTED_POLICIES[c]
                    sections.append(f"    {c}: {p['description']}")

            sections.append("\n  To generate Terraform for these policies, use:")
            sections.append(f"    generate_org_policy_terraform(project_id=\"{project_id}\")")
        else:
            sections.append("  All checked policies are compliant. No action needed.")

        # ── Summary ──────────────────────────────────────────────────
        total = len(EXPECTED_POLICIES)
        sections.append(f"\n{'=' * 60}")
        sections.append("ORG POLICY COMPLIANCE SUMMARY")
        sections.append("=" * 60)
        sections.append(f"  Project:        {project_id}")
        sections.append(f"  Policies checked: {total}")
        sections.append(f"  Compliant:      {len(compliant)}")
        sections.append(f"  Non-compliant:  {len(non_compliant)} {'<-- ACTION NEEDED' if non_compliant else ''}")
        sections.append(f"  Not set:        {len(not_set)} {'<-- ACTION NEEDED' if not_set else ''}")
        high_total = len([c for c in non_compliant + not_set if EXPECTED_POLICIES[c]["risk"] == "HIGH"])
        if not non_compliant and not not_set:
            sections.append("\n  STATUS: FULLY COMPLIANT")
        elif high_total:
            sections.append(f"\n  STATUS: NON-COMPLIANT — {high_total} HIGH risk issue(s)")
        else:
            sections.append(f"\n  STATUS: PARTIALLY COMPLIANT — {len(non_compliant) + len(not_set)} issue(s)")

        return "\n".join(sections)

    @mcp.tool(annotations=DIAGNOSTIC)
    async def generate_org_policy_terraform(
        project_id: str | None = None,
        scope: str = "project",
    ) -> str:
        """Generate Terraform code to enforce recommended Organisation Policies.

        Produces HCL for all expected org policies that match the baseline.
        The output can be applied at project or organisation level.

        Args:
            project_id: GCP project ID for project-scoped policies. Leave empty for active project.
            scope: 'project' or 'organization' (GCP term). Default 'project'.
        """
        _log(f"TOOL: generate_org_policy_terraform(scope={scope})")

        if not project_id:
            result = await run_gcloud(["config", "get-value", "project"])
            raw = result.get("result_text", result.get("result", ""))
            project_id = raw.strip().strip('"') if isinstance(raw, str) else str(raw)

        lines = [
            f"# Organisation Policy Terraform — {scope} scope",
            f"# Generated for: {project_id}",
            f"# Enforces {len(EXPECTED_POLICIES)} baseline policies",
            "",
        ]

        if scope == "organization":
            lines.append('data "google_organization" "org" {')
            lines.append('  domain = "REPLACE_WITH_YOUR_DOMAIN"  # e.g. "ons.gov.uk"')
            lines.append("}")
            lines.append("")
            parent_ref = 'data.google_organization.org.name'
        else:
            parent_ref = f'"projects/{project_id}"'

        # Group by category
        by_category: dict[str, list[tuple[str, dict]]] = {}
        for cid, meta in sorted(EXPECTED_POLICIES.items()):
            by_category.setdefault(meta["category"], []).append((cid, meta))

        for category, policies in sorted(by_category.items()):
            lines.append(f"# ── {category.upper()} policies ──")
            lines.append("")

            for constraint_id, meta in policies:
                safe_name = constraint_id.replace(".", "_").replace("/", "_")
                lines.append(f'# {meta["description"]}')
                lines.append(f'# Risk: {meta["risk"]} — {meta["rationale"]}')
                lines.append(f'resource "google_org_policy_policy" "{safe_name}" {{')
                lines.append(f"  name   = \"{{{parent_ref}}}/policies/{constraint_id}\"")
                lines.append(f"  parent = {parent_ref}")
                lines.append("  spec {")

                if meta["expected"] == "enforced":
                    lines.append("    rules {")
                    lines.append("      enforce = \"TRUE\"")
                    lines.append("    }")
                elif meta["expected"] == "restricted":
                    lines.append("    rules {")
                    lines.append(f"      # TODO: Configure allowed values for {constraint_id}")
                    lines.append("      values {")
                    lines.append('        allowed_values = ["REPLACE_WITH_ALLOWED_VALUES"]')
                    lines.append("      }")
                    lines.append("    }")

                lines.append("  }")
                lines.append("}")
                lines.append("")

        return "\n".join(lines)
