#!/usr/bin/env python3
"""Fail CI if the gcloud subcommand/flag allowlist has widened without review.

The command and flag allowlists in `safety.py` are the single point where the
security posture of this MCP server is enforced. Widening them must be a
deliberate, reviewed change — not a quiet PR diff.

This script:
- Loads the current ALLOWED_SUBCOMMANDS / ALLOWED_FLAGS frozensets
- Compares them against a baseline JSON file stored in the repo
- Exits non-zero if the current set is a strict superset of the baseline
  (i.e. new entries were added) without also updating the baseline

To intentionally widen the allowlist:
  1. Update safety.py
  2. Run this script with --update-baseline
  3. Commit both changes together with justification in the PR body
  4. A security reviewer must approve (per framework §16.2 — 2 peers incl. security)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from vpcsc_mcp.tools.safety import ALLOWED_FLAGS, ALLOWED_SUBCOMMANDS

REPO_ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = REPO_ROOT / ".github" / "allowlist-baseline.json"


def current() -> dict:
    return {
        "subcommands": sorted(ALLOWED_SUBCOMMANDS),
        "flags": sorted(ALLOWED_FLAGS),
    }


def load_baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {"subcommands": [], "flags": []}
    return json.loads(BASELINE_PATH.read_text())


def save_baseline(data: dict) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Rewrite the baseline to match current source (requires security review).",
    )
    args = parser.parse_args()

    cur = current()
    if args.update_baseline:
        save_baseline(cur)
        print(f"baseline updated: {BASELINE_PATH}")
        print(
            f"  subcommands={len(cur['subcommands'])} "
            f"flags={len(cur['flags'])}",
        )
        return 0

    baseline = load_baseline()
    cur_sub = set(cur["subcommands"])
    cur_flg = set(cur["flags"])
    base_sub = set(baseline["subcommands"])
    base_flg = set(baseline["flags"])

    added_sub = cur_sub - base_sub
    added_flg = cur_flg - base_flg
    removed_sub = base_sub - cur_sub
    removed_flg = base_flg - cur_flg

    if not (added_sub or added_flg or removed_sub or removed_flg):
        print(
            f"allowlist in sync with baseline "
            f"(subcommands={len(cur_sub)}, flags={len(cur_flg)})",
        )
        return 0

    print("ALLOWLIST DRIFT DETECTED", file=sys.stderr)
    if added_sub:
        print(f"  + subcommands: {sorted(added_sub)}", file=sys.stderr)
    if added_flg:
        print(f"  + flags: {sorted(added_flg)}", file=sys.stderr)
    if removed_sub:
        print(f"  - subcommands: {sorted(removed_sub)}", file=sys.stderr)
    if removed_flg:
        print(f"  - flags: {sorted(removed_flg)}", file=sys.stderr)
    print(
        "\nTo approve: rerun with --update-baseline, commit the baseline change in\n"
        "the same PR, and ensure a security reviewer is on the PR (framework §16.2).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
