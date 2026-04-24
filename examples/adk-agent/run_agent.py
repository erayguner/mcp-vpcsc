"""Run the VPC-SC ADK agent programmatically (without adk web).

Usage:
    python run_agent.py "List all perimeters in policy 123456"
    python run_agent.py "Recommend services for an AI/ML workload"
    echo "Troubleshoot RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER" | python run_agent.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.genai import types
from mcp import StdioServerParameters

load_dotenv()


async def main(query: str) -> None:
    """Run a single query through the VPC-SC agent."""

    # Connect to the MCP server as a subprocess
    mcp_toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "vpcsc_mcp.server"],
                env={**os.environ, "VPCSC_MCP_TRANSPORT": "stdio"},
            ),
            timeout=10,
        ),
    )

    agent = LlmAgent(
        model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
        name="vpcsc_helper",
        instruction=("You are a VPC Service Controls specialist. " "Use the available tools to help the user."),
        tools=[mcp_toolset],
    )

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        state={},
        app_name="vpcsc-mcp",
        user_id="cli-user",
    )

    runner = Runner(
        app_name="vpcsc-mcp",
        agent=agent,
        session_service=session_service,
    )

    content = types.Content(role="user", parts=[types.Part(text=query)])

    print(f"User: {query}\n")

    async for event in runner.run_async(
        session_id=session.id,
        user_id=session.user_id,
        new_message=content,
    ):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    print(f"Agent: {part.text}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_query = " ".join(sys.argv[1:])
    elif not sys.stdin.isatty():
        user_query = sys.stdin.read().strip()
    else:
        user_query = "What workload types can you help me with?"

    asyncio.run(main(user_query))
