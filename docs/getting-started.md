# Getting Started

Set up the VPC-SC MCP server in under 5 minutes. Pick your environment and follow the steps.

## Choose your path

| I want to... | Go to |
|---|---|
| Run locally with Gemini CLI | [Local setup](#local-setup) |
| Run in Google Cloud Shell | [Cloud Shell setup](#cloud-shell-setup) |
| Deploy to Cloud Run | [Cloud Run setup](#cloud-run-setup) |

---

## Local setup

**Time:** 2 minutes. **Needs:** Python 3.10+, gcloud CLI.

### Step 1: Install

```bash
git clone <your-repo-url> vpcsc-mcp
cd vpcsc-mcp
pip install -e .
```

### Step 2: Verify

```bash
python -m pytest tests/ -q
```

You should see `18 passed`.

### Step 3: Connect to Gemini CLI

Create `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "vpcsc-mcp": {
      "command": "python3",
      "args": ["-m", "vpcsc_mcp.server"],
      "env": { "VPCSC_MCP_TRANSPORT": "stdio" }
    }
  }
}
```

### Step 4: Use it

Start `gemini` and type:

> Run a diagnostic on my project

The server scans your authenticated GCP project and reports:
- Which VPC-SC APIs are enabled and whether they're protected by a perimeter
- Which org policies are compliant, non-compliant, or missing
- Recommended actions with ready-to-run gcloud commands

---

## Cloud Shell setup

**Time:** 3 minutes. **Needs:** A GCP project. **No API keys needed.**

### Step 1: Open Cloud Shell

Go to [shell.cloud.google.com](https://shell.cloud.google.com).

### Step 2: Clone and set up

```bash
git clone <your-repo-url> vpcsc-mcp
cd vpcsc-mcp
bash scripts/cloudshell-setup.sh
```

The script installs dependencies, verifies gcloud auth, and configures Gemini.

### Step 3: Run diagnostics (no LLM needed)

```bash
python3 scripts/run-diagnostic.py --all
```

This runs both VPC-SC and org policy diagnostics directly — no Gemini, no API keys, no waiting for LLM responses.

### Step 4: Use with Gemini (interactive)

```bash
cd examples/adk-agent
adk web --port 8080
```

Click **Web Preview** in Cloud Shell to open the UI. Ask:

> Check my project for VPC-SC gaps and org policy compliance

### What you'll see

```
DIAGNOSTIC SUMMARY
  Project:         your-project-id
  APIs enabled:    23 VPC-SC supported
  APIs protected:  20
  APIs unprotected:3 <-- ACTION NEEDED
  STATUS: PARTIALLY PROTECTED — 3 gap(s) to close

ORG POLICY COMPLIANCE SUMMARY
  Policies checked: 31
  Compliant:      18
  Non-compliant:  4 <-- ACTION NEEDED
  Not set:        9 <-- ACTION NEEDED
  STATUS: NON-COMPLIANT — 8 HIGH risk issue(s)
```

---

## Cloud Run setup

**Time:** 10 minutes. **Needs:** Terraform 1.14+, gcloud CLI, a GCP project with billing.

### Step 1: Configure

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` — set `project_id` and `invoker_members`.

### Step 2: Deploy infrastructure

```bash
terraform init && terraform apply
```

### Step 3: Build and push container

```bash
cd ..
gcloud builds submit --region=europe-west2 --config=cloudbuild.yaml
```

### Step 4: Connect

```bash
gcloud run services proxy vpcsc-mcp --region=europe-west2 --port=3000
```

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "vpcsc-mcp": { "url": "http://localhost:3000/mcp" }
  }
}
```

---

## What the server does

Once connected, you have 35 tools that:

| Action | Example command |
|---|---|
| **Scan your project** | "Run a diagnostic on my project" |
| **Check org policies** | "Check org policy compliance" |
| **Find gaps** | "Which APIs are unprotected?" |
| **Generate Terraform** | "Generate Terraform for a VPC-SC perimeter" |
| **Generate YAML** | "Create an ingress rule for BigQuery cross-project read" |
| **Troubleshoot denials** | "Troubleshoot RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER" |
| **Validate Terraform** | "Validate this Terraform code" |
| **Recommend services** | "What services should I restrict for an AI/ML workload?" |

## What happens next

1. Run the diagnostic to understand your current state
2. Review the protection gaps and org policy findings
3. Generate Terraform for the recommended changes
4. Apply in dry-run mode first, monitor for violations
5. Enforce once violations are resolved

## Need help?

| Topic | Document |
|---|---|
| All 34 tools explained | [MCP Server Guide](mcp-server-guide.md) |
| Security controls | [Security](security.md) |
| Architecture | [Architecture](architecture.md) |
| Cloud Run deployment details | [Runbook: Cloud Run](runbook-cloud-run.md) |
| Cloud Shell details | [Runbook: Cloud Shell](runbook-cloudshell.md) |
