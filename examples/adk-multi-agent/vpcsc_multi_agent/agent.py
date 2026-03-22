"""VPC-SC Multi-Agent — hierarchical ADK agent with specialised sub-agents.

Architecture:
  Coordinator (root_agent)
    ├── Perimeter Designer    — designs new perimeters, recommends services
    ├── Terraform Generator   — produces HCL and YAML configurations
    ├── Troubleshooter        — diagnoses violations, generates fixes
    └── Infrastructure Query  — reads live perimeters, levels, and logs

Each sub-agent connects to the same VPC-SC MCP server but is instructed
to use only the tools relevant to its specialisation.
"""

import os
import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters


def _build_toolset(tool_filter: list[str] | None = None) -> McpToolset:
    """Build MCP toolset with optional tool filter."""
    mode = os.environ.get("VPCSC_MCP_MODE", "local").lower()

    kwargs = {}
    if tool_filter:
        kwargs["tool_filter"] = tool_filter

    if mode == "remote":
        url = os.environ.get("VPCSC_MCP_URL", "http://localhost:3000/mcp")
        return McpToolset(
            connection_params=StreamableHTTPConnectionParams(url=url),
            **kwargs,
        )

    # Minimal subprocess environment — only what the MCP server needs.
    subprocess_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "VPCSC_MCP_TRANSPORT": "stdio",
    }
    for key in ("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT", "CLOUDSDK_CONFIG"):
        if key in os.environ:
            subprocess_env[key] = os.environ[key]

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "vpcsc_mcp.server"],
                env=subprocess_env,
            ),
            timeout=10,
        ),
        **kwargs,
    )


# ── Sub-agent: Perimeter Designer ───────────────────────────────────────────

perimeter_designer = LlmAgent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="perimeter_designer",
    description="Designs VPC-SC perimeters — recommends services, analyses designs, validates identities.",
    instruction="""\
You are a VPC-SC perimeter design specialist. Your job is to:
1. Ask the user about their workload type and recommend restricted services.
2. Analyse their perimeter design for potential issues.
3. Validate identity formats and access level names.
4. Recommend dry-run vs enforced mode.
5. Identify cross-project access patterns that need ingress/egress rules.

Use these tools: recommend_restricted_services, list_supported_services,
check_service_support, analyze_perimeter_design, validate_identity_format,
get_method_selectors.\
""",
    tools=[
        _build_toolset(tool_filter=[
            "recommend_restricted_services",
            "list_supported_services",
            "check_service_support",
            "analyze_perimeter_design",
            "validate_identity_format",
            "get_method_selectors",
        ]),
    ],
)

# ── Sub-agent: Terraform Generator ──────────────────────────────────────────

terraform_generator = LlmAgent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="terraform_generator",
    description="Generates Terraform HCL and gcloud YAML for VPC-SC resources.",
    instruction="""\
You are a Terraform and gcloud configuration generator for VPC-SC. Your job is to:
1. Generate Terraform HCL for perimeters, access levels, and bridges.
2. Generate ingress and egress policy blocks.
3. Generate gcloud-compatible YAML for ingress/egress rules.
4. Retrieve and apply pre-built rule patterns.
5. Always explain what each generated block does.

Use these tools: generate_perimeter_terraform, generate_access_level_terraform,
generate_bridge_terraform, generate_ingress_policy_terraform,
generate_egress_policy_terraform, generate_full_perimeter_terraform,
generate_vpc_accessible_services_terraform, generate_ingress_yaml,
generate_egress_yaml, list_ingress_patterns, list_egress_patterns,
get_ingress_pattern, get_egress_pattern.\
""",
    tools=[
        _build_toolset(tool_filter=[
            "generate_perimeter_terraform",
            "generate_access_level_terraform",
            "generate_bridge_terraform",
            "generate_ingress_policy_terraform",
            "generate_egress_policy_terraform",
            "generate_full_perimeter_terraform",
            "generate_vpc_accessible_services_terraform",
            "generate_ingress_yaml",
            "generate_egress_yaml",
            "list_ingress_patterns",
            "list_egress_patterns",
            "get_ingress_pattern",
            "get_egress_pattern",
        ]),
    ],
)

# ── Sub-agent: Troubleshooter ───────────────────────────────────────────────

troubleshooter = LlmAgent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="troubleshooter",
    description="Diagnoses VPC-SC access denials and generates fixes.",
    instruction="""\
You are a VPC-SC troubleshooting specialist. Your job is to:
1. Query audit logs for VPC-SC violations.
2. Explain violation reason codes and their root causes.
3. Determine which ingress or egress rule is needed to fix a denial.
4. Generate the rule configuration as both Terraform and YAML.
5. Recommend testing the fix in dry-run mode first.

Use these tools: check_vpc_sc_violations, troubleshoot_violation,
get_method_selectors, generate_ingress_yaml, generate_egress_yaml,
get_ingress_pattern, get_egress_pattern.\
""",
    tools=[
        _build_toolset(tool_filter=[
            "check_vpc_sc_violations",
            "troubleshoot_violation",
            "get_method_selectors",
            "generate_ingress_yaml",
            "generate_egress_yaml",
            "get_ingress_pattern",
            "get_egress_pattern",
        ]),
    ],
)

# ── Sub-agent: Infrastructure Query ─────────────────────────────────────────

infra_query = LlmAgent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="infrastructure_query",
    description="Queries live GCP infrastructure, runs diagnostics, and generates implementation guides with Terraform.",
    instruction="""\
You are an infrastructure query and diagnostic specialist. Your job is to:
1. List and describe access policies, perimeters, and access levels.
2. Check the dry-run status of perimeters.
3. Show which projects and services are in each perimeter.
4. Run full project diagnostics to assess VPC-SC readiness.
5. Generate implementation guides with Terraform code (both raw HCL and ONS module calls).

Use these tools: list_access_policies, list_perimeters, describe_perimeter,
list_access_levels, describe_access_level, dry_run_status,
update_perimeter_resources, update_perimeter_services,
diagnose_project, generate_implementation_guide.

When users ask to scan or diagnose a project, use diagnose_project first,
then generate_implementation_guide to produce the Terraform code.\
""",
    tools=[
        _build_toolset(tool_filter=[
            "list_access_policies",
            "list_perimeters",
            "describe_perimeter",
            "list_access_levels",
            "describe_access_level",
            "dry_run_status",
            "update_perimeter_resources",
            "update_perimeter_services",
            "diagnose_project",
            "generate_implementation_guide",
        ]),
    ],
)

# ── Root Agent: Coordinator ─────────────────────────────────────────────────

root_agent = LlmAgent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="vpcsc_coordinator",
    description="Coordinates VPC-SC tasks across specialised sub-agents.",
    instruction="""\
You are the VPC-SC Coordinator. You manage a team of specialised agents:

- **perimeter_designer**: Designs perimeters, recommends services, validates configs.
  Delegate to this agent when users ask about which services to restrict,
  how to structure perimeters, or need a design review.

- **terraform_generator**: Produces Terraform HCL and gcloud YAML.
  Delegate to this agent when users need configuration code for perimeters,
  access levels, bridges, or ingress/egress rules.

- **troubleshooter**: Diagnoses VPC-SC violations and generates fixes.
  Delegate to this agent when users report access denials, errors,
  or need help debugging VPC-SC issues.

- **infrastructure_query**: Reads live GCP infrastructure, runs diagnostics,
  and generates implementation guides with Terraform.
  Delegate to this agent when users want to scan a project, see their current
  perimeters, or get a full VPC-SC implementation plan with Terraform code.

Route each user request to the right specialist. For complex tasks that span
multiple areas (e.g., "troubleshoot this denial and generate the fix"),
coordinate across agents in sequence.

Always summarise the results clearly for the user.\
""",
    sub_agents=[perimeter_designer, terraform_generator, troubleshooter, infra_query],
)
