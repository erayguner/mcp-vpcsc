# Runbook: Cloud Shell + Gemini

Run the VPC-SC MCP server entirely within Google Cloud Shell using Vertex AI Gemini. No API keys, no local installation needed.

For a quick-start version, see [Getting Started — Cloud Shell setup](getting-started.md#cloud-shell-setup). For VPC-SC background, see [Concepts](concepts.md).

## Prerequisites

- A GCP project with billing enabled
- Access to [Cloud Shell](https://shell.cloud.google.com)
- IAM: `roles/viewer` on the project (for diagnostics), `roles/orgpolicy.policyViewer` (for org policy checks)

## Quick start (1 minute)

Open Cloud Shell and run:

```bash
git clone <your-repo-url> vpcsc-mcp && cd vpcsc-mcp
bash scripts/cloudshell-setup.sh
```

The script installs the MCP server, verifies gcloud auth, and configures the connection.

## Run diagnostics (no LLM needed)

The fastest way — calls the MCP tools directly, no Gemini required:

```bash
# VPC-SC readiness scan
python3 scripts/run-diagnostic.py

# Org policy compliance
python3 scripts/run-diagnostic.py --org-policies

# Both + implementation guide
python3 scripts/run-diagnostic.py --all

# Specific project
python3 scripts/run-diagnostic.py --project=my-project-id

# Validate a Terraform file
python3 scripts/run-diagnostic.py --validate-tf path/to/main.tf
```

Output shows:
- `[ENABLED]` / `[NOT ENABLED]` for APIs
- `[PROTECTED]` / `[GAP]` for VPC-SC coverage
- `[COMPLIANT]` / `[NON-COMPLIANT]` / `[NOT SET]` for org policies
- `STATUS:` summary line
- `ACTION:` recommended gcloud commands

## Run with Gemini (interactive)

### Option A: ADK Web UI

```bash
cd examples/adk-agent
adk web --port 8080
```

Click **Web Preview** (top-right of Cloud Shell) to open the UI. Ask:

> Run diagnostics on my project

The agent runs both `diagnose_project` and `diagnose_org_policies`, summarises findings, and offers to generate Terraform.

### Option B: ADK Terminal

```bash
cd examples/adk-agent
adk run vpcsc_agent
```

Interactive terminal chat. Same capabilities as the web UI.

### Option C: Programmatic

```bash
python3 examples/adk-agent/run_agent.py "Check org policy compliance and generate Terraform fixes"
```

### Option D: Gemini CLI (if installed)

```bash
gemini
> Run a diagnostic on my project
```

The MCP server is configured as a tool provider in `~/.gemini/settings.json`.

## Authentication

Cloud Shell provides Application Default Credentials automatically. No API keys needed.

| Component | Auth method |
|---|---|
| gcloud CLI tools | Active Cloud Shell session |
| Vertex AI (Gemini) | Application Default Credentials |
| MCP server | Runs as subprocess (inherits auth) |

The `.env` file uses Vertex AI mode:

```
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=europe-west2
```

## What each diagnostic checks

### VPC-SC diagnostic (`diagnose_project`)

10 steps:
1. Resolve project and metadata
2. Scan 219 VPC-SC supported APIs
3. Check organisation and access policy
4. List perimeters (flag which contain this project)
5. List access levels
6. List service accounts
7. List VPC networks
8. Query VPC-SC violations (last 7 days)
9. Protection gap analysis (cross-reference APIs vs perimeter)
10. Summary with STATUS

### Org policy diagnostic (`diagnose_org_policies`)

5 steps checking 31 policies across 11 categories:
- Compute (5): serial ports, default network, external IPs, shielded VMs, storage restrictions
- IAM (7): audit logging, default SA grants, SA key creation, WIF providers, allowed members
- Storage (2): public access, uniform bucket access
- GCP (4): resource locations, audit logging, contact domains, service usage
- Cloud Run (2): ingress, VPC egress
- GKE (1+3 custom): public clusters, maintenance windows, release channels, auto-upgrade
- Cloud SQL (1+1 custom): public IP, password policy
- Firestore (1): P4SA import/export
- SCC (4 custom): container/event/VM threat detection, security health analytics

## Generate Terraform for findings

After running diagnostics:

```bash
# VPC-SC implementation guide (raw HCL + The module call)
python3 scripts/run-diagnostic.py --implementation-guide

# Org policy Terraform (all 31 policies)
python3 -c "
import asyncio
from vpcsc_mcp.server import mcp
async def run():
    r = await mcp.call_tool('generate_org_policy_terraform', {'scope': 'project'})
    content, _ = r
    for c in content:
        if hasattr(c, 'text'): print(c.text)
asyncio.run(run())
" > org-policies.tf

# Validate the generated Terraform
python3 scripts/run-diagnostic.py --validate-tf org-policies.tf
```

## End-to-end test

Run this to verify everything works in your Cloud Shell:

```bash
# 1. Setup
bash scripts/cloudshell-setup.sh

# 2. Quick smoke test
python3 -c "from vpcsc_mcp.server import mcp; print('MCP server: OK')"

# 3. Run VPC-SC diagnostic
python3 scripts/run-diagnostic.py 2>/dev/null | tail -15

# 4. Run org policy diagnostic
python3 scripts/run-diagnostic.py --org-policies 2>/dev/null | tail -15

# 5. Generate and validate Terraform
python3 scripts/run-diagnostic.py --implementation-guide 2>/dev/null | head -30

# 6. Run tests
python3 -m pytest tests/ -q

# 7. (Optional) Start ADK web UI
cd examples/adk-agent && adk web --port 8080
```

Expected output for steps 3-4:

```
DIAGNOSTIC SUMMARY
  Project:         your-project-id
  APIs enabled:    N VPC-SC supported
  STATUS: ...

ORG POLICY COMPLIANCE SUMMARY
  Policies checked: 31
  STATUS: ...
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `pip3 install` fails | Run `pip3 install --user -e ".[dev]"` |
| `gcloud` auth errors | Run `gcloud auth login` in Cloud Shell |
| ADK web UI not accessible | Use Cloud Shell's "Web Preview" button, not direct URL |
| `ModuleNotFoundError: vpcsc_mcp` | Run setup script from the project root directory |
| Org policy API not enabled | `gcloud services enable orgpolicy.googleapis.com` |
| Vertex AI API not enabled | `gcloud services enable aiplatform.googleapis.com` |
| `No organisation found` | VPC-SC requires a GCP org — personal projects can't use it |
| Gemini model errors | Ensure `GOOGLE_CLOUD_LOCATION` is set to a region with Gemini access |
