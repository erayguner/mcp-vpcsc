"""Deploy the VPC-SC ADK agent to Vertex AI Agent Engine (managed runtime).

Agent Engine is the serverless runtime from the Gemini Enterprise Agent Platform.
It hosts the agent so you don't run Cloud Run yourself, and integrates with
Memory Bank, Sessions, and the Evaluation Service.

Usage:
    export GOOGLE_CLOUD_PROJECT=your-project
    export GOOGLE_CLOUD_LOCATION=us-central1
    export AGENT_ENGINE_STAGING_BUCKET=gs://your-bucket
    export VPCSC_MCP_URL=https://your-mcp.run.app/mcp

    uv run python examples/adk-agent/deploy_agent_engine.py deploy
    uv run python examples/adk-agent/deploy_agent_engine.py list
    uv run python examples/adk-agent/deploy_agent_engine.py delete <resource-name>

The MCP server must be reachable from Agent Engine — deploy it to Cloud Run
first and set VPCSC_MCP_URL to its /mcp endpoint.
"""

from __future__ import annotations

import os
import sys

REQUIRED_ENV = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "AGENT_ENGINE_STAGING_BUCKET")


def _require_env() -> tuple[str, str, str]:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing required env vars: {', '.join(missing)}")
    return (os.environ[REQUIRED_ENV[0]], os.environ[REQUIRED_ENV[1]], os.environ[REQUIRED_ENV[2]])


def _init_vertex() -> None:
    import vertexai

    project, location, bucket = _require_env()
    vertexai.init(project=project, location=location, staging_bucket=bucket)


def _build_app():
    """Build the ADK agent wrapped for Agent Engine deployment.

    Forces remote MCP mode — Agent Engine cannot run gcloud/MCP as a subprocess.
    """
    os.environ.setdefault("VPCSC_MCP_MODE", "remote")
    if not os.environ.get("VPCSC_MCP_URL"):
        sys.exit("VPCSC_MCP_URL must be set to the deployed MCP server /mcp endpoint")

    from vertexai.preview import reasoning_engines
    from vpcsc_agent.agent import root_agent

    return reasoning_engines.AdkApp(agent=root_agent, enable_tracing=True)


def deploy() -> None:
    _init_vertex()
    from vertexai import agent_engines

    app = _build_app()
    remote = agent_engines.create(
        agent_engine=app,
        requirements=[
            "google-adk>=1.27.0",
            "google-cloud-aiplatform[adk,agent_engines]>=1.95.0",
            "mcp>=1.26.0",
        ],
        extra_packages=[os.path.join(os.path.dirname(__file__), "vpcsc_agent")],
        display_name="vpcsc-helper",
        description="VPC Service Controls specialist agent",
        env_vars={
            "VPCSC_MCP_MODE": "remote",
            "VPCSC_MCP_URL": os.environ["VPCSC_MCP_URL"],
            "GEMINI_MODEL": os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        },
    )
    print(f"deployed: {remote.resource_name}")


def list_engines() -> None:
    _init_vertex()
    from vertexai import agent_engines

    for engine in agent_engines.list():
        print(f"{engine.resource_name}\t{engine.display_name}")


def delete(resource_name: str) -> None:
    _init_vertex()
    from vertexai import agent_engines

    agent_engines.get(resource_name).delete(force=True)
    print(f"deleted: {resource_name}")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: deploy_agent_engine.py {deploy|list|delete <resource-name>}")

    cmd = sys.argv[1]
    if cmd == "deploy":
        deploy()
    elif cmd == "list":
        list_engines()
    elif cmd == "delete":
        if len(sys.argv) != 3:
            sys.exit("usage: deploy_agent_engine.py delete <resource-name>")
        delete(sys.argv[2])
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
