"""Provision a Vertex AI Memory Bank for the VPC-SC agent.

Memory Bank is a managed long-term memory service from the Gemini Enterprise
Agent Platform. It persists user-scoped facts across sessions (e.g. the
project, perimeter name, or workload type a user is iterating on) so the
agent does not re-ask on every turn.

Create once, then set MEMORY_BANK_AGENT_ENGINE to the printed resource name.

Usage:
    export GOOGLE_CLOUD_PROJECT=your-project
    export GOOGLE_CLOUD_LOCATION=us-central1
    export AGENT_ENGINE_STAGING_BUCKET=gs://your-bucket

    uv run python examples/adk-agent/memory_bank.py create
    uv run python examples/adk-agent/memory_bank.py list
    uv run python examples/adk-agent/memory_bank.py delete <resource-name>
"""

from __future__ import annotations

import os
import sys

REQUIRED_ENV = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "AGENT_ENGINE_STAGING_BUCKET")


def _init_vertex() -> None:
    import vertexai

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        sys.exit(f"missing required env vars: {', '.join(missing)}")

    vertexai.init(
        project=os.environ[REQUIRED_ENV[0]],
        location=os.environ[REQUIRED_ENV[1]],
        staging_bucket=os.environ[REQUIRED_ENV[2]],
    )


def create() -> None:
    _init_vertex()
    from vertexai import agent_engines

    engine = agent_engines.create(display_name="vpcsc-memory-bank")
    print(engine.resource_name)
    print(
        "\nexport MEMORY_BANK_AGENT_ENGINE='" + engine.resource_name + "'  # add to your environment",
    )


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
        sys.exit("usage: memory_bank.py {create|list|delete <resource-name>}")

    cmd = sys.argv[1]
    if cmd == "create":
        create()
    elif cmd == "list":
        list_engines()
    elif cmd == "delete":
        if len(sys.argv) != 3:
            sys.exit("usage: memory_bank.py delete <resource-name>")
        delete(sys.argv[2])
    else:
        sys.exit(f"unknown command: {cmd}")


if __name__ == "__main__":
    main()
