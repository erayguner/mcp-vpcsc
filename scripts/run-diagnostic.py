#!/usr/bin/env python3
"""Run VPC-SC diagnostics directly — no LLM needed.

Usage:
    python3 scripts/run-diagnostic.py                      # VPC-SC diagnostic
    python3 scripts/run-diagnostic.py --org-policies       # Org policy diagnostic
    python3 scripts/run-diagnostic.py --implementation-guide  # Terraform guide
    python3 scripts/run-diagnostic.py --all                # Everything
    python3 scripts/run-diagnostic.py --project=my-project # Specific project
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Add project root to path so imports work from any directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def run_tool(tool_name: str, args: dict) -> str:
    """Call an MCP tool and return the text result."""
    from vpcsc_mcp.server import mcp

    result = await mcp.call_tool(tool_name, args)
    content, _ = result
    for c in content:
        if hasattr(c, "text"):
            return c.text
    return "No output"


async def main() -> None:
    parser = argparse.ArgumentParser(description="VPC-SC MCP Diagnostics")
    parser.add_argument("--project", help="GCP project ID (default: active gcloud project)")
    parser.add_argument("--org-policies", action="store_true", help="Run org policy diagnostic")
    parser.add_argument("--implementation-guide", action="store_true", help="Generate implementation guide")
    parser.add_argument("--workload", default="data-analytics", help="Workload type for implementation guide")
    parser.add_argument("--all", action="store_true", help="Run all diagnostics")
    parser.add_argument("--validate-tf", metavar="FILE", help="Validate a Terraform file")
    args = parser.parse_args()

    tool_args: dict = {}
    if args.project:
        tool_args["project_id"] = args.project

    # Default: run VPC-SC diagnostic
    run_vpcsc = not args.org_policies and not args.implementation_guide and not args.validate_tf
    if args.all:
        run_vpcsc = True
        args.org_policies = True
        args.implementation_guide = True

    if run_vpcsc:
        print(await run_tool("diagnose_project", tool_args))

    if args.org_policies:
        if run_vpcsc:
            print("\n\n")
        print(await run_tool("diagnose_org_policies", tool_args))

    if args.implementation_guide:
        guide_args = {**tool_args, "workload_type": args.workload}
        print("\n\n")
        print(await run_tool("generate_implementation_guide", guide_args))

    if args.validate_tf:
        with open(args.validate_tf) as f:
            hcl = f.read()
        print(await run_tool("validate_terraform", {"hcl_code": hcl}))


if __name__ == "__main__":
    asyncio.run(main())
