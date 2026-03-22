# Runbook: Local Setup

## Prerequisites

- Python 3.10+
- `gcloud` CLI authenticated (`gcloud auth login`)
- IAM: `roles/accesscontextmanager.policyReader` + `roles/logging.viewer` on relevant projects

## Install

```bash
cd vpcsc-mcp
pip install -e ".[dev]"
```

## Verify

```bash
python -m pytest tests/ -v
```

Expect: 18 passed.

## Connect to Gemini CLI

Create or edit `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "vpcsc-mcp": {
      "command": "python3",
      "args": ["-m", "vpcsc_mcp.server"],
      "env": {
        "VPCSC_MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

Then start Gemini CLI:

```bash
gemini
```

The server runs via stdio. No port, no Docker, no Terraform needed.

## Test manually

```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' \
  | python -m vpcsc_mcp.server 2>/dev/null
```

Expect: JSON with `"serverInfo":{"name":"VPC-SC Helper"}`.

## Run diagnostics on your project

Once connected, ask:

> Run a diagnostic on my project

The agent calls `diagnose_project` (10 steps), which scans enabled APIs, org, access policy, existing perimeters, service accounts, VPC networks, recent violations, and performs a **protection gap analysis**. Every gcloud command logs to your terminal:

```
[vpcsc-mcp] [1/10] Resolving active GCP project...
[vpcsc-mcp] EXEC: gcloud config get-value project
[vpcsc-mcp]   OK: gcloud config get-value project (1.9s) — 1 result(s)
...
[vpcsc-mcp] [9/10] Analysing protection gaps...
```

The output classifies each enabled API:

```
  PROTECTED (20 APIs — already in perimeter's restricted_services):
    [PROTECTED] bigquery.googleapis.com (BigQuery)

  UNPROTECTED (3 APIs — enabled but NOT in perimeter):
    [GAP] dataplex.googleapis.com (Dataplex)

  ACTION: Add these 3 service(s) to the perimeter's restricted_services list.

  STATUS: PARTIALLY PROTECTED — 3 gap(s) to close
```

Then ask:

> Generate an implementation guide for this project

The agent calls `generate_implementation_guide`, which produces Terraform code (both raw HCL and ONS module calls) tailored to your project's detected services and service accounts.

## Check org policy compliance

> Check org policy compliance on my project

The agent calls `diagnose_org_policies`, which checks 31 baseline policies across compute, IAM, storage, GCP-wide, Cloud Run, GKE, Cloud SQL, Firestore, and SCC. Output:

```
  [COMPLIANT] compute.disableSerialPortAccess
  [NON-COMPLIANT] storage.publicAccessPrevention  (risk: HIGH)
  [NOT SET] compute.requireShieldedVm  (risk: MEDIUM)

  STATUS: NON-COMPLIANT — 4 HIGH risk issue(s)
```

Then:

> Generate Terraform to fix the org policy issues

The agent calls `generate_org_policy_terraform`, which produces HCL for all 31 policies.

## Run HTTP transport locally

```bash
VPCSC_MCP_TRANSPORT=streamable-http python -m vpcsc_mcp.server
```

Binds to `127.0.0.1:8080` by default. Override with `VPCSC_MCP_HOST` and `PORT`.

Test the health endpoint:

```bash
curl http://127.0.0.1:8080/health
```

## Use with Google ADK (optional)

```bash
pip install ".[adk]"
cd examples/adk-agent
cp .env.example .env       # set GOOGLE_API_KEY
adk web                    # browser UI at localhost:8000
```

Multi-agent version (4 specialists + coordinator):

```bash
cd examples/adk-multi-agent
cp .env.example .env
adk web
```

Programmatic use:

```bash
python examples/adk-agent/run_agent.py "Recommend services for an AI/ML perimeter"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: vpcsc_mcp` | Run `pip install -e .` from the project root |
| gcloud tools return errors | Run `gcloud auth login` and verify `gcloud access-context-manager policies list --organization=ORG_ID` works |
| `gcloud CLI not found` warning at startup | Install gcloud: https://cloud.google.com/sdk/docs/install |
| ADK agent fails to connect | Check `.env` has a valid `GOOGLE_API_KEY` or Vertex AI config |
| `mcp` version conflict | Pin with `pip install "mcp>=1.26.0,<2"` |
| `BLOCKED: Flag 'X' is not in the allowed list` | The server rejects unknown gcloud flags for security. Only 11 flags are permitted. |
