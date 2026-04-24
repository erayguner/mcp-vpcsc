"""Tools for running project diagnostics and generating VPC-SC implementation guides."""

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from vpcsc_mcp.data.services import SUPPORTED_SERVICES, WORKLOAD_RECOMMENDATIONS
from vpcsc_mcp.tools.gcloud_ops import _log, run_gcloud


def register_diagnostic_tools(mcp) -> None:
    """Register diagnostic and implementation guide tools."""

    from vpcsc_mcp.tools.safety import DIAGNOSTIC

    @mcp.tool(annotations=DIAGNOSTIC)
    async def diagnose_project(
        project_id: str | None = None,
        ctx: Context[ServerSession, None] | None = None,
    ) -> str:
        """Run a full VPC-SC readiness diagnostic on the currently authenticated GCP project.

        Discovers: active project, enabled APIs, existing perimeters, access policies,
        service accounts, recent VPC-SC violations, and VPC networks.

        Args:
            project_id: GCP project ID. Leave empty to use the currently configured gcloud project.
        """
        total_steps = 10
        step = 0

        async def progress(message: str) -> None:
            nonlocal step
            step += 1
            _log(f"[{step}/{total_steps}] {message}")
            if ctx:
                try:
                    await ctx.report_progress(progress=step, total=total_steps, message=message)
                    await ctx.info(message)
                except Exception:
                    pass  # Context may not support progress in all transports

        sections = []

        # ── Resolve project ──────────────────────────────────────────
        await progress("Resolving active GCP project...")
        if not project_id:
            result = await run_gcloud(["config", "get-value", "project"])
            if "error" in result:
                return "Cannot determine active project. Run 'gcloud config set project PROJECT_ID' or pass project_id."
            raw = result.get("result_text", result.get("result", ""))
            project_id = raw.strip().strip('"') if isinstance(raw, str) else str(raw)
            if not project_id or project_id == "None":
                return "No active gcloud project set. Run 'gcloud config set project PROJECT_ID' or pass project_id."

        sections.append(f"PROJECT: {project_id}")
        sections.append("=" * 60)

        # ── Account ──────────────────────────────────────────────────
        await progress(f"Fetching project metadata for {project_id}...")
        acct = await run_gcloud(["config", "get-value", "account"])
        acct_str = acct.get("result_text", acct.get("result", "unknown"))
        if isinstance(acct_str, str):
            acct_str = acct_str.strip().strip('"')
        sections.append(f"\nAuthenticated as: {acct_str}")

        # ── Project metadata ─────────────────────────────────────────
        proj_info = await run_gcloud(["projects", "describe", project_id])
        if "error" not in proj_info:
            proj = proj_info.get("result", {})
            if isinstance(proj, dict):
                sections.append(f"Project name: {proj.get('name', 'N/A')}")
                sections.append(f"Project number: {proj.get('projectNumber', 'N/A')}")
                parent = proj.get("parent", {})
                if parent:
                    sections.append(f"Parent: {parent.get('type', '')}/{parent.get('id', '')}")

        # ── Enabled APIs ─────────────────────────────────────────────
        await progress("Scanning enabled APIs for VPC-SC support...")
        sections.append("\n--- ENABLED APIS (VPC-SC relevant) ---")
        api_result = await run_gcloud(["services", "list", "--enabled"], project=project_id)
        enabled_apis: list[str] = []
        if "error" not in api_result:
            services = api_result.get("result", [])
            for svc in services:
                name = svc.get("config", {}).get("name", "")
                if name in SUPPORTED_SERVICES:
                    enabled_apis.append(name)
            enabled_apis.sort()
            if enabled_apis:
                for api in enabled_apis:
                    display = SUPPORTED_SERVICES.get(api, "")
                    sections.append(f"  [ENABLED] {api} ({display})")
                sections.append(
                    f"\n  {len(enabled_apis)} VPC-SC supported APIs enabled " f"out of {len(SUPPORTED_SERVICES)} known."
                )
            else:
                sections.append("  No VPC-SC supported APIs found enabled.")
        else:
            sections.append(f"  Could not list APIs: {api_result['error']}")

        # ── Not-enabled but common ───────────────────────────────────
        common_missing = set(SUPPORTED_SERVICES.keys()) - set(enabled_apis)
        important_missing = {
            s
            for s in common_missing
            if s
            in {
                "accesscontextmanager.googleapis.com",
                "cloudkms.googleapis.com",
                "secretmanager.googleapis.com",
            }
        }
        if important_missing:
            sections.append("\n  Potentially needed APIs not yet enabled:")
            for api in sorted(important_missing):
                sections.append(f"    [NOT ENABLED] {api} ({SUPPORTED_SERVICES[api]})")

        # ── Organization & access policy ─────────────────────────────
        await progress("Checking organisation and access policy...")
        sections.append("\n--- ORGANISATION & ACCESS POLICY ---")
        org_result = await run_gcloud(["organizations", "list"])
        org_id = None
        if "error" not in org_result:
            orgs = org_result.get("result", [])
            if orgs:
                org = orgs[0]
                org_id = org.get("name", "").replace("organizations/", "")
                sections.append(f"  Organization: {org.get('displayName', 'N/A')} (ID: {org_id})")
            else:
                sections.append("  No organisation found (project may not be in an org).")
                sections.append("  VPC-SC requires an organisation. Cannot proceed without one.")
        else:
            sections.append(f"  Could not list organisations: {org_result['error']}")

        policy_id = None
        if org_id:
            pol_result = await run_gcloud(
                [
                    "access-context-manager",
                    "policies",
                    "list",
                    f"--organization={org_id}",
                ]
            )
            if "error" not in pol_result:
                policies = pol_result.get("result", [])
                if policies:
                    pol = policies[0]
                    policy_name = pol.get("name", "")
                    policy_id = policy_name.split("/")[-1] if "/" in policy_name else policy_name
                    sections.append(f"  Access policy: {pol.get('title', 'N/A')} (ID: {policy_id})")
                else:
                    sections.append("  No access policy found. One must be created before VPC-SC perimeters.")
            else:
                sections.append(f"  Could not query access policies: {pol_result['error']}")

        # ── Existing perimeters ──────────────────────────────────────
        await progress("Listing existing perimeters and access levels...")
        if policy_id:
            sections.append("\n--- EXISTING PERIMETERS ---")
            peri_result = await run_gcloud(
                [
                    "access-context-manager",
                    "perimeters",
                    "list",
                    f"--policy={policy_id}",
                ]
            )
            if "error" not in peri_result:
                perimeters = peri_result.get("result", [])
                project_in_perimeter = False
                if perimeters:
                    for p in perimeters:
                        name = p.get("name", "").split("/")[-1]
                        title = p.get("title", name)
                        ptype = p.get("perimeterType", "REGULAR")
                        status = p.get("status", {})
                        resources = status.get("resources", [])
                        restricted = status.get("restrictedServices", [])
                        has_dry_run = bool(p.get("spec") or p.get("useExplicitDryRunSpec"))

                        proj_ref = (
                            f"projects/{proj.get('projectNumber', '')}"
                            if isinstance(proj_info.get("result"), dict)
                            else ""
                        )
                        in_this = proj_ref in resources if proj_ref else False
                        if in_this:
                            project_in_perimeter = True

                        marker = " <-- THIS PROJECT" if in_this else ""
                        dr = " [has dry-run config]" if has_dry_run else ""
                        sections.append(f"  {title} ({name}) [{ptype}]{dr}{marker}")
                        sections.append(f"    Projects: {len(resources)}, Services: {len(restricted)}")
                    sections.append(f"\n  Total: {len(perimeters)} perimeter(s)")
                    if not project_in_perimeter:
                        sections.append(f"  NOTE: Project {project_id} is NOT in any perimeter.")
                else:
                    sections.append("  No perimeters exist. This project is not protected by VPC-SC.")
            else:
                sections.append(f"  Could not list perimeters: {peri_result['error']}")

            # ── Access levels ────────────────────────────────────────
            sections.append("\n--- ACCESS LEVELS ---")
            level_result = await run_gcloud(
                [
                    "access-context-manager",
                    "levels",
                    "list",
                    f"--policy={policy_id}",
                ]
            )
            if "error" not in level_result:
                levels = level_result.get("result", [])
                if levels:
                    for lev in levels:
                        lname = lev.get("name", "").split("/")[-1]
                        ltitle = lev.get("title", lname)
                        sections.append(f"  {ltitle} ({lname})")
                    sections.append(f"\n  Total: {len(levels)} access level(s)")
                else:
                    sections.append("  No access levels defined.")
            else:
                sections.append(f"  Could not list access levels: {level_result['error']}")

        # ── Service accounts ─────────────────────────────────────────
        await progress("Listing service accounts...")
        sections.append("\n--- SERVICE ACCOUNTS ---")
        sa_result = await run_gcloud(["iam", "service-accounts", "list"], project=project_id)
        if "error" not in sa_result:
            accounts = sa_result.get("result", [])
            if accounts:
                for sa in accounts:
                    email = sa.get("email", "unknown")
                    display = sa.get("displayName", "")
                    disabled = sa.get("disabled", False)
                    status = " [DISABLED]" if disabled else ""
                    sections.append(f"  {email}{status}")
                    if display:
                        sections.append(f"    Display name: {display}")
                sections.append(f"\n  Total: {len(accounts)} service account(s)")
            else:
                sections.append("  No service accounts found.")
        else:
            sections.append(f"  Could not list service accounts: {sa_result['error']}")

        # ── VPC networks ─────────────────────────────────────────────
        await progress("Listing VPC networks...")
        sections.append("\n--- VPC NETWORKS ---")
        vpc_result = await run_gcloud(["compute", "networks", "list"], project=project_id)
        if "error" not in vpc_result:
            networks = vpc_result.get("result", [])
            if networks:
                for net in networks:
                    name = net.get("name", "unknown")
                    mode = net.get("x_gcloud_subnet_mode", net.get("autoCreateSubnetworks", ""))
                    peerings = net.get("peerings", [])
                    peer_info = f", {len(peerings)} peering(s)" if peerings else ""
                    sections.append(f"  {name} (mode: {mode}{peer_info})")
            else:
                sections.append("  No VPC networks found.")
        else:
            sections.append(f"  Could not list networks: {vpc_result['error']}")

        # ── Recent VPC-SC violations ─────────────────────────────────
        await progress("Querying Cloud Audit Logs for VPC-SC violations...")
        sections.append("\n--- RECENT VPC-SC VIOLATIONS (last 7d) ---")
        log_filter = (
            "protoPayload.metadata.@type=" '"type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata"'
        )
        log_result = await run_gcloud(
            [
                "logging",
                "read",
                log_filter,
                f"--project={project_id}",
                "--freshness=7d",
                "--limit=10",
            ]
        )
        if "error" not in log_result:
            entries = log_result.get("result", [])
            if entries:
                violations_by_reason: dict[str, int] = {}
                for entry in entries:
                    reason = entry.get("protoPayload", {}).get("metadata", {}).get("violationReason", "UNKNOWN")
                    violations_by_reason[reason] = violations_by_reason.get(reason, 0) + 1
                sections.append(f"  {len(entries)} violation(s) found:")
                for reason, count in sorted(violations_by_reason.items(), key=lambda x: -x[1]):
                    sections.append(f"    {reason}: {count}")
            else:
                sections.append("  No VPC-SC violations in the last 7 days.")
        else:
            sections.append(f"  Could not query logs: {log_result['error']}")

        # ── Protection gap analysis ─────────────────────────────────
        await progress("Analysing protection gaps...")
        sections.append("\n--- PROTECTION GAP ANALYSIS ---")

        # Find restricted services in the perimeter this project belongs to
        protected_services: set[str] = set()
        perimeter_name_for_project = None
        if policy_id and "error" not in peri_result:
            proj_ref = ""
            if isinstance(proj_info.get("result"), dict):
                proj_ref = f"projects/{proj_info['result'].get('projectNumber', '')}"

            for p in peri_result.get("result", []):
                status = p.get("status", {})
                resources = status.get("resources", [])
                if proj_ref and proj_ref in resources:
                    protected_services = set(status.get("restrictedServices", []))
                    perimeter_name_for_project = p.get("title", p.get("name", "").split("/")[-1])
                    break

        if perimeter_name_for_project:
            sections.append(f"\n  Project is in perimeter: {perimeter_name_for_project}")
            sections.append(f"  Perimeter restricts {len(protected_services)} service(s)")

            # Already protected
            already_protected = sorted(set(enabled_apis) & protected_services)
            if already_protected:
                sections.append(
                    f"\n  PROTECTED ({len(already_protected)} APIs " "— already in perimeter's restricted_services):"
                )
                for api in already_protected:
                    sections.append(f"    [PROTECTED] {api} ({SUPPORTED_SERVICES.get(api, '')})")

            # Enabled but NOT protected
            unprotected = sorted(set(enabled_apis) - protected_services)
            if unprotected:
                sections.append(
                    f"\n  UNPROTECTED ({len(unprotected)} APIs "
                    "— enabled but NOT in perimeter's restricted_services):"
                )
                for api in unprotected:
                    sections.append(f"    [GAP] {api} ({SUPPORTED_SERVICES.get(api, '')})")
                sections.append(
                    f"\n  ACTION: Add these {len(unprotected)} service(s) to the perimeter's restricted_services list."
                )
                sections.append("  Use dry-run mode first to identify any violations:")
                sections.append(
                    "    gcloud access-context-manager perimeters dry-run update " f"{perimeter_name_for_project} \\"
                )
                sections.append(f"      --policy={policy_id} \\")
                add_svc = ",".join(unprotected[:5])
                sections.append(f"      --add-restricted-services={add_svc}")
                if len(unprotected) > 5:
                    sections.append(f"      # ... plus {len(unprotected) - 5} more services")
            else:
                sections.append("\n  All enabled VPC-SC APIs are already protected. No gaps found.")

            # In perimeter but not enabled (over-restricted)
            restricted_but_unused = sorted(protected_services - set(enabled_apis))
            if restricted_but_unused:
                sections.append(
                    f"\n  INFO: {len(restricted_but_unused)} service(s) in "
                    "restricted_services but not currently enabled in this project."
                )
                sections.append("  This is normal — they may be enabled in other projects in the same perimeter.")

        elif enabled_apis:
            sections.append("\n  Project is NOT in any perimeter. All enabled APIs are unprotected.")
            sections.append(f"\n  UNPROTECTED ({len(enabled_apis)} APIs — no perimeter protection):")
            for api in enabled_apis:
                sections.append(f"    [GAP] {api} ({SUPPORTED_SERVICES.get(api, '')})")
            sections.append("\n  ACTION: Create a new perimeter with these services.")
            sections.append(f'  Use: generate_implementation_guide(project_id="{project_id}") for full Terraform.')
        else:
            sections.append("  No VPC-SC supported APIs enabled. Nothing to protect.")

        # ── Summary ──────────────────────────────────────────────────
        sections.append("\n" + "=" * 60)
        sections.append("DIAGNOSTIC SUMMARY")
        sections.append("=" * 60)
        sections.append(f"  Project:         {project_id}")
        sections.append(f"  Organization:    {'found' if org_id else 'NOT FOUND — required for VPC-SC'}")
        policy_status = f"found (ID: {policy_id})" if policy_id else "NOT FOUND — create one first"
        sections.append(f"  Access policy:   {policy_status}")
        sections.append(f"  In perimeter:    {perimeter_name_for_project or 'NO — not protected'}")
        sections.append(f"  APIs enabled:    {len(enabled_apis)} VPC-SC supported")

        if perimeter_name_for_project:
            sections.append(f"  APIs protected:  {len(already_protected)}")
            sections.append(f"  APIs unprotected:{len(unprotected)} {'<-- ACTION NEEDED' if unprotected else ''}")
        else:
            sections.append("  APIs protected:  0")
            sections.append(f"  APIs unprotected:{len(enabled_apis)} <-- ACTION NEEDED")

        if perimeter_name_for_project and not unprotected:
            sections.append("\n  STATUS: FULLY PROTECTED")
        elif perimeter_name_for_project and unprotected:
            sections.append(f"\n  STATUS: PARTIALLY PROTECTED — {len(unprotected)} gap(s) to close")
        else:
            sections.append("\n  STATUS: NOT PROTECTED — create a perimeter")

        return "\n".join(sections)

    @mcp.tool(annotations=DIAGNOSTIC)
    async def generate_implementation_guide(
        project_id: str | None = None,
        workload_type: str = "data-analytics",
        ctx: Context[ServerSession, None] | None = None,
    ) -> str:
        """Generate a step-by-step VPC-SC implementation guide with Terraform for the authenticated project.

        Runs a diagnostic, detects enabled services, and produces a complete
        Terraform configuration tailored to the project.

        Args:
            project_id: GCP project ID. Leave empty to use the active gcloud project.
            workload_type: Workload type for service recommendations: 'ai-ml',
                'data-analytics', 'web-application', 'data-warehouse',
                'healthcare'. Default 'data-analytics'.
        """
        guide_steps = 5
        guide_step = 0

        async def guide_progress(message: str) -> None:
            nonlocal guide_step
            guide_step += 1
            _log(f"[guide {guide_step}/{guide_steps}] {message}")
            if ctx:
                try:
                    await ctx.report_progress(progress=guide_step, total=guide_steps, message=message)
                    await ctx.info(message)
                except Exception:
                    pass

        # ── Resolve project ──────────────────────────────────────────
        await guide_progress("Resolving project and fetching metadata...")
        if not project_id:
            result = await run_gcloud(["config", "get-value", "project"])
            raw = result.get("result_text", result.get("result", ""))
            project_id = raw.strip().strip('"') if isinstance(raw, str) else str(raw)
            if not project_id or project_id == "None":
                return "No active gcloud project. Run 'gcloud config set project PROJECT_ID' or pass project_id."

        # ── Get project number ───────────────────────────────────────
        proj_info = await run_gcloud(["projects", "describe", project_id])
        project_number = "REPLACE_WITH_PROJECT_NUMBER"
        org_id = None
        if "error" not in proj_info:
            proj = proj_info.get("result", {})
            if isinstance(proj, dict):
                project_number = proj.get("projectNumber", project_number)
                parent = proj.get("parent", {})
                if parent.get("type") == "organization":
                    org_id = parent.get("id", "")

        # ── Get organisation ─────────────────────────────────────────
        if not org_id:
            org_result = await run_gcloud(["organizations", "list"])
            if "error" not in org_result:
                orgs = org_result.get("result", [])
                if orgs:
                    org_id = orgs[0].get("name", "").replace("organizations/", "")

        if not org_id:
            org_id = "REPLACE_WITH_ORG_ID"

        # ── Get access policy ────────────────────────────────────────
        await guide_progress("Looking up access policy...")
        policy_id = "REPLACE_WITH_POLICY_ID"
        if org_id and org_id != "REPLACE_WITH_ORG_ID":
            pol_result = await run_gcloud(
                [
                    "access-context-manager",
                    "policies",
                    "list",
                    f"--organization={org_id}",
                ]
            )
            if "error" not in pol_result:
                policies = pol_result.get("result", [])
                if policies:
                    policy_name = policies[0].get("name", "")
                    policy_id = policy_name.split("/")[-1] if "/" in policy_name else policy_name

        # ── Detect enabled services ──────────────────────────────────
        await guide_progress("Scanning enabled APIs and matching to workload recommendations...")
        api_result = await run_gcloud(["services", "list", "--enabled"], project=project_id)
        enabled_vpcsc: list[str] = []
        if "error" not in api_result:
            for svc in api_result.get("result", []):
                name = svc.get("config", {}).get("name", "")
                if name in SUPPORTED_SERVICES:
                    enabled_vpcsc.append(name)
            enabled_vpcsc.sort()

        # ── Get workload recommendations ─────────────────────────────
        rec = WORKLOAD_RECOMMENDATIONS.get(workload_type.lower().replace(" ", "-"), {})
        required = rec.get("required", [])
        recommended = rec.get("recommended", [])
        notes = rec.get("notes", [])

        # Merge: enabled APIs + workload required + workload recommended
        restricted_services = sorted(set(enabled_vpcsc) | set(required) | set(recommended))

        # ── Detect service accounts ──────────────────────────────────
        await guide_progress("Detecting service accounts and generating Terraform...")
        sa_result = await run_gcloud(["iam", "service-accounts", "list"], project=project_id)
        service_accounts: list[str] = []
        if "error" not in sa_result:
            for sa in sa_result.get("result", []):
                email = sa.get("email", "")
                if email and not sa.get("disabled", False):
                    service_accounts.append(email)

        # ── Generate the perimeter name ──────────────────────────────
        safe_name = project_id.replace("-", "_").replace(".", "_")
        perimeter_name = f"{safe_name}_prod"

        # ── Build the guide ──────────────────────────────────────────
        services_hcl = "\n".join(f'    "{s}",' for s in restricted_services)
        "\n".join(f'    "serviceAccount:{sa}",' for sa in service_accounts[:10])

        acm_policy_ref = "${{data.google_access_context_manager_access_policy.org_policy.name}}"

        guide = f"""\
VPC-SC IMPLEMENTATION GUIDE
Project: {project_id} (number: {project_number})
Organization: {org_id}
Access Policy: {policy_id}
Workload type: {workload_type}
{'=' * 60}

PHASE 1: PREREQUISITES
-----------------------
1. Verify the access policy exists:
   gcloud access-context-manager policies list --organization={org_id}

2. Enable the Access Context Manager API (if not already):
   gcloud services enable accesscontextmanager.googleapis.com --project={project_id}

3. Grant yourself the required role:
   gcloud organizations add-iam-policy-binding {org_id} \\
     --member="user:YOUR_EMAIL" \\
     --role="roles/accesscontextmanager.policyAdmin"

PHASE 2: CREATE ACCESS LEVEL (Terraform)
-----------------------------------------
# access_level.tf

data "google_access_context_manager_access_policy" "org_policy" {{
  parent = "organizations/{org_id}"
}}

resource "google_access_context_manager_access_level" "corporate_network" {{
  parent = "accessPolicies/{acm_policy_ref}"
  name   = "accessPolicies/{acm_policy_ref}/accessLevels/corporate_network"
  title  = "Corporate Network"

  basic {{
    conditions {{
      ip_subnetworks = [
        "REPLACE_WITH_YOUR_CORPORATE_CIDR/24",  # e.g. "203.0.113.0/24"
      ]
    }}
  }}
}}

PHASE 3: CREATE PERIMETER IN DRY-RUN MODE (Terraform)
------------------------------------------------------
# perimeter.tf

resource "google_access_context_manager_service_perimeter" "{perimeter_name}" {{
  parent                    = "accessPolicies/{policy_id}"
  name                      = "accessPolicies/{policy_id}/servicePerimeters/{perimeter_name}"
  title                     = "{perimeter_name}"
  perimeter_type            = "PERIMETER_TYPE_REGULAR"
  use_explicit_dry_run_spec = true  # Start in dry-run mode

  spec {{
    restricted_services = [
{services_hcl}
    ]

    resources = [
      "projects/{project_number}",
    ]

    access_levels = [
      google_access_context_manager_access_level.corporate_network.name,
    ]

    # Admin ingress: allow your team from corporate network
    ingress_policies {{
      title = "Admin access from corporate network"
      ingress_from {{
        identity_type = "ANY_IDENTITY"
        sources {{
          access_level = google_access_context_manager_access_level.corporate_network.name
        }}
      }}
      ingress_to {{
        resources = ["*"]
        operations {{
          service_name = "*"
          method_selectors {{
            method = "*"
          }}
        }}
      }}
    }}

    # CI/CD ingress: allow Cloud Build service accounts
    ingress_policies {{
      title = "Cloud Build CI/CD"
      ingress_from {{
        identities = [
          "serviceAccount:{project_number}@cloudbuild.gserviceaccount.com",
        ]
        sources {{
          resource = "projects/{project_number}"
        }}
      }}
      ingress_to {{
        resources = ["*"]
        operations {{
          service_name = "*"
          method_selectors {{
            method = "*"
          }}
        }}
      }}
    }}
  }}
}}

PHASE 4: MONITOR DRY-RUN VIOLATIONS (1-2 weeks)
-------------------------------------------------
Run this daily to check for violations that would be blocked if enforced:

  gcloud logging read \\
    'protoPayload.metadata.@type="type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata"' \\
    --project={project_id} --freshness=1d --format=json

Or use the MCP tool:
  check_vpc_sc_violations(project_id="{project_id}", freshness="1d")

For each violation, use:
  troubleshoot_violation(violation_reason="THE_REASON_CODE")

Then generate the fix:
  generate_ingress_yaml(...) or generate_egress_yaml(...)

PHASE 5: ADD INGRESS/EGRESS RULES FOR VIOLATIONS
--------------------------------------------------
Add rules to the spec block for each violation found.

Common rules you will likely need:
"""

        # Add notes from workload recommendations
        if notes:
            guide += "\nWorkload-specific notes:\n"
            for note in notes:
                guide += f"  - {note}\n"

        # Add detected service accounts
        if service_accounts:
            guide += f"""
Detected service accounts in this project ({len(service_accounts)} total):
"""
            for sa in service_accounts[:10]:
                guide += f"  - serviceAccount:{sa}\n"
            if len(service_accounts) > 10:
                guide += f"  ... and {len(service_accounts) - 10} more\n"
            guide += "\nYou will likely need ingress/egress rules for some of these.\n"

        # ── Build module-based Terraform ────────────────────────────
        sa_ingress_lines = ""
        if service_accounts:
            # Group SAs by common patterns for rule generation
            cloudbuild_sas = [sa for sa in service_accounts if "cloudbuild" in sa]
            gcf_sas = [sa for sa in service_accounts if "gcf-admin-robot" in sa]
            composer_sas = [sa for sa in service_accounts if "composer" in sa]
            other_sas = [sa for sa in service_accounts if sa not in cloudbuild_sas + gcf_sas + composer_sas]

            if cloudbuild_sas:
                sa_ingress_lines += f"""
  # Cloud Build CI/CD — ingress for all methods
  ingress_terraform_cloud_build = [
    {{
      title      = "Cloud Build CI/CD deploy"
      identities = [
{chr(10).join(f'        "serviceAccount:{sa}",' for sa in cloudbuild_sas)}
      ]
      resources = ["*"]
    }},
  ]
"""
            if gcf_sas:
                sa_ingress_lines += f"""
  # Cloud Functions service agents — egress for deploy
  generic_egress_cloudfunctions_deploy = [
    {{
      identities = [
{chr(10).join(f'        "serviceAccount:{sa}",' for sa in gcf_sas)}
      ]
      resources = ["*"]
    }},
  ]
"""
            if other_sas[:5]:
                sa_ingress_lines += f"""
  # Service account ingress — BigQuery read access (adjust per SA needs)
  generic_ingress_bigquery_read = [
    {{
      title      = "Service account BQ read access"
      identities = [
{chr(10).join(f'        "serviceAccount:{sa}",' for sa in other_sas[:5])}
      ]
      resources = ["*"]
    }},
  ]
"""

        guide += f"""
PHASE 5B: MODULE-BASED TERRAFORM (The perimeter module)
---------------------------------------------------------
Use this if deploying via the perimeter module.
The module handles method selectors automatically — you only supply
identities and target resources.

# perimeter-module.tf

module "{perimeter_name}" {{
  source         = "gcs::https://www.googleapis.com/storage/v1/ons-ci-functions/modules/gcp-vpcsc-modules/gcp-vpcsc-modules-v2.16.5/perimeter"
  parent         = data.google_access_context_manager_access_policy.org-access-policy.name
  name           = "{perimeter_name}"
  perimeter_type = "PERIMETER_TYPE_REGULAR"

  restricted_services = [
{services_hcl}
  ]

  access_levels = [
    local.ci_cloudbuild_exemption_access_level,
  ]

  resources = [
    local.{safe_name},  # "projects/{project_number}"
  ]

  vpc_accessible_services = ["RESTRICTED-SERVICES"]

  # ── Admin rules ──────────────────────────────────────────────

  admin_egress_all = [
    {{
      identities = toset(flatten([local.vpc_sc_admin_groups]))
      resources  = ["*"]
    }},
  ]

  admin_ingress_all = [
    {{
      title        = "VPC-SC admins from corporate network"
      access_level = [local.console_access_level_uk_access_level]
      identities   = flatten([local.vpc_sc_admin_groups])
      resources    = ["*"]
    }},
  ]
{sa_ingress_lines}}}

# locals.tf — add your project and service account references

locals {{
  {safe_name} = "projects/{project_number}"

  # Add service account locals here:
  # {safe_name}_cloudbuild_sa = "serviceAccount:{project_number}@cloudbuild.gserviceaccount.com"
}}

PHASE 6: ENFORCE THE PERIMETER
-------------------------------
Once dry-run violations are resolved:

Option A — gcloud:
  gcloud access-context-manager perimeters dry-run enforce {perimeter_name} \\
    --policy={policy_id}

Option B — Terraform:
  Change use_explicit_dry_run_spec to false, move the spec block to status,
  and run terraform apply.

PHASE 7: ONGOING MONITORING
-----------------------------
  # Check for violations regularly
  gcloud logging read \\
    'protoPayload.metadata.@type="type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata"' \\
    --project={project_id} --freshness=1d

  # List perimeter state
  gcloud access-context-manager perimeters describe {perimeter_name} \\
    --policy={policy_id}

{'=' * 60}
SERVICES TO RESTRICT ({len(restricted_services)} total)
{'=' * 60}
"""
        for svc in restricted_services:
            display = SUPPORTED_SERVICES.get(svc, "")
            enabled_marker = " [already enabled]" if svc in enabled_vpcsc else " [not yet enabled]"
            required_marker = " [required for workload]" if svc in required else ""
            guide += f"  {svc} ({display}){enabled_marker}{required_marker}\n"

        guide += f"""
{'=' * 60}
MODULE VARIABLE QUICK REFERENCE
{'=' * 60}
The perimeter module uses pre-defined method selectors.
Pick the right variable name for your use case:

EGRESS (who inside perimeter can access what outside):
  admin_egress_all                    — all services, all methods
  generic_egress_bigquery_read        — BQ datasets.get, tables.getData, jobs.create
  generic_egress_bigquery_stream_writer — BQ TableDataService.InsertAll
  generic_egress_storage_reader       — GCS objects.get, objects.list, buckets.get
  generic_egress_storage_writer       — GCS objects.create, objects.delete
  generic_egress_cloudfunctions_deploy — Storage all (for CF source upload)
  generic_egress_pubsub_publisher     — Pub/Sub Publisher.Publish
  generic_egress_logging_all          — Logging all methods
  generic_egress_monitoring_all       — Monitoring all methods
  data_engineer_egress_output_project — BQ write + GCS read/write

INGRESS (who outside perimeter can access what inside):
  admin_ingress_all                   — all services, all methods
  ingress_terraform_cloud_build       — all services (CI/CD)
  generic_ingress_bigquery_read       — BQ read access
  generic_ingress_bigquery_all        — BQ all methods
  generic_ingress_storage_reader      — GCS read access
  generic_ingress_storage_writer      — GCS write access
  generic_ingress_pubsub_all          — Pub/Sub all methods
  generic_ingress_compute_all         — Compute all methods
  generic_ingress_secretmanager_all   — Secret Manager all methods

Each variable takes a list of objects:
  {{
    title           = "Rule description"       # optional
    access_level    = [local.my_access_level]  # optional, ingress only
    source_resource = [local.source_project]   # optional, ingress only
    identities      = ["serviceAccount:..."]   # required
    resources       = ["projects/..." or "*"]   # required
  }}
"""

        return guide
