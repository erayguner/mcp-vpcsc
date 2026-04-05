"""Cloud Shell-optimised agent — uses Vertex AI (Gemini) with no external API keys needed.

Cloud Shell automatically provides Application Default Credentials via the
active gcloud session. Set GOOGLE_GENAI_USE_VERTEXAI=TRUE in .env.
"""

import os
import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters


def _build_toolset() -> McpToolset:
    """Build MCP toolset — always local subprocess in Cloud Shell."""
    subprocess_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "VPCSC_MCP_TRANSPORT": "stdio",
    }
    for key in ("GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT", "CLOUDSDK_CONFIG", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE"):
        if key in os.environ:
            subprocess_env[key] = os.environ[key]

    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "vpcsc_mcp.server"],
                env=subprocess_env,
            ),
            timeout=15,
        ),
    )


root_agent = LlmAgent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="vpcsc_cloudshell",
    description=(
        "VPC-SC and Org Policy diagnostic agent for Cloud Shell. "
        "Uses Vertex AI Gemini. No API keys needed — authenticates via gcloud."
    ),
    instruction="""\
You are a VPC Service Controls and Organisation Policy specialist running in Google Cloud Shell.

You have 40 tools from the VPC-SC MCP server. Use them to:
1. Run `diagnose_project` to scan the current project for VPC-SC readiness and protection gaps.
2. Run `diagnose_org_policies` to check organisation policy compliance.
3. Run `generate_implementation_guide` to produce Terraform code.
4. Run `generate_org_policy_terraform` to produce org policy Terraform.
5. Run `validate_terraform` to validate any generated Terraform.
6. Use the troubleshooting and analysis tools as needed.

When the user asks to "run diagnostics" or "check my project":
- Run BOTH diagnose_project AND diagnose_org_policies.
- Summarise the results clearly: what's protected, what's missing, what to fix first.
- Offer to generate Terraform for any gaps found.

Always explain findings in plain English before showing technical details.\
""",
    tools=[_build_toolset()],
)
