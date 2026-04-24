"""VPC-SC Helper ADK Agent — single agent connected to the VPC-SC MCP server.

Supports two connection modes:
  - LOCAL (default): Starts the MCP server as a subprocess via stdio.
  - REMOTE: Connects to a deployed Cloud Run MCP server via streamable-http
            (requires gcloud proxy running on localhost).

Set connection mode via VPCSC_MCP_MODE env var: "local" or "remote".
Set remote URL via VPCSC_MCP_URL env var (default: http://localhost:3000/mcp).

Context caching: set ENABLE_CONTEXT_CACHE=1 to cache the system instruction
and tool schemas across turns. On Gemini 2.5 this reduces input-token cost
for the static prompt prefix by ~75%.
"""

import os
import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters


def _build_toolset() -> McpToolset:
    """Build the MCP toolset based on connection mode."""
    mode = os.environ.get("VPCSC_MCP_MODE", "local").lower()

    if mode == "remote":
        # Connect to a deployed Cloud Run MCP server via proxy
        url = os.environ.get("VPCSC_MCP_URL", "http://localhost:3000/mcp")
        return McpToolset(
            connection_params=StreamableHTTPConnectionParams(url=url),
        )

    # Default: start the MCP server locally as a subprocess
    # Pass only the environment variables the MCP server needs — not the full env.
    subprocess_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/usr/local/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "VPCSC_MCP_TRANSPORT": "stdio",
    }
    # Forward GCP credentials if present
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
    )


def _context_cache_config():
    """Build ADK ContextCacheConfig when ENABLE_CONTEXT_CACHE=1.

    Returns None when disabled, or when the running ADK version does not
    expose ContextCacheConfig (keeps the agent importable on older ADKs).
    """
    if os.environ.get("ENABLE_CONTEXT_CACHE", "").lower() not in ("1", "true", "yes"):
        return None

    try:
        from google.adk.agents.context_cache_config import ContextCacheConfig
    except ImportError:
        return None

    return ContextCacheConfig(
        cache_intervals=int(os.environ.get("CONTEXT_CACHE_INTERVALS", "10")),
        ttl_seconds=int(os.environ.get("CONTEXT_CACHE_TTL_SECONDS", "1800")),
        min_tokens=int(os.environ.get("CONTEXT_CACHE_MIN_TOKENS", "0")),
    )


_extra_kwargs: dict = {}
_cache_config = _context_cache_config()
if _cache_config is not None:
    _extra_kwargs["context_cache_config"] = _cache_config


root_agent = LlmAgent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="vpcsc_helper",
    description=(
        "An AI agent that helps set up, manage, and troubleshoot "
        "Google Cloud VPC Service Controls using the VPC-SC MCP server."
    ),
    **_extra_kwargs,
    instruction="""\
You are a VPC Service Controls specialist. You help developers and platform engineers:

1. **Design perimeters** — recommend which services to restrict, how to structure
   projects, and whether to use dry-run mode first.
2. **Generate configurations** — produce Terraform HCL and gcloud YAML for
   perimeters, access levels, bridges, and ingress/egress rules.
3. **Troubleshoot denials** — diagnose VPC-SC violations from audit logs,
   identify the root cause, and generate the fix.
4. **Query live infrastructure** — list perimeters, access levels, and policies
   from the user's GCP environment.

When helping users:
- Always start by understanding their workload type to recommend the right services.
- Validate identity formats before generating rules.
- Prefer dry-run mode for new perimeters.
- Explain the difference between method selectors and permission selectors.
- For cross-project BigQuery access, remind users they need BOTH ingress AND egress rules.
- Use the pre-built patterns when they match the user's scenario.

You have access to 40 tools from the VPC-SC MCP server. Use them proactively.\
""",
    tools=[_build_toolset()],
)
