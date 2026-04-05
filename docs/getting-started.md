# Getting Started

Set up the VPC-SC MCP server in under 5 minutes. Pick your environment and follow the steps.

**New to VPC Service Controls?** Read [VPC-SC Concepts](concepts.md) first — it explains what perimeters, access levels, and ingress/egress rules are and how this MCP maps to each concept.

## Before you begin

### What you need (all paths)

| Requirement | Why | How to check |
|---|---|---|
| A GCP organisation | VPC-SC requires an org — personal projects can't use it | `gcloud organizations list` returns at least one org |
| A GCP project with billing | gcloud tools query live GCP APIs | `gcloud config get-value project` returns your project ID |
| `gcloud` CLI authenticated | The MCP server calls gcloud on your behalf | `gcloud auth list` shows an active account |
| Python 3.10+ | The MCP server is a Python package | `python3 --version` shows 3.10 or later |

### IAM permissions needed

The MCP server runs read-only gcloud commands. Your authenticated account (or the Cloud Run service account) needs these roles:

| Role | Grants access to | Required for |
|---|---|---|
| `roles/accesscontextmanager.policyReader` | Read perimeters, access levels, access policies | All gcloud query tools, diagnostics |
| `roles/logging.viewer` | Read Cloud Audit Logs | `check_vpc_sc_violations`, violation scanning in diagnostics |
| `roles/orgpolicy.policyViewer` | Read org policy constraints | `diagnose_org_policies` |
| `roles/viewer` | Read project metadata, APIs, networks, SAs | `diagnose_project` (project-level details) |

**Grant at the org level** for cross-project visibility:

```bash
gcloud organizations add-iam-policy-binding ORG_ID \
  --member="user:you@example.com" \
  --role="roles/accesscontextmanager.policyReader"
```

### APIs that should be enabled

```bash
# Required for VPC-SC operations
gcloud services enable accesscontextmanager.googleapis.com --project=YOUR_PROJECT

# Required for org policy diagnostics
gcloud services enable orgpolicy.googleapis.com --project=YOUR_PROJECT
```

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

Once connected, you have 40 tools, 5 resources, and 3 prompts that cover the full VPC-SC lifecycle:

| Action | Example command | What it does |
|---|---|---|
| **Scan your project** | "Run a diagnostic on my project" | 10-step scan of APIs, perimeters, org, violations, protection gaps |
| **Check org policies** | "Check org policy compliance" | Checks 31 policies across 11 categories, classifies compliance |
| **Find gaps** | "Which APIs are unprotected?" | Cross-references enabled APIs vs perimeter restricted_services |
| **Recommend services** | "What services should I restrict for an AI/ML workload?" | Tailored service list for 5 workload types |
| **Generate Terraform** | "Generate Terraform for a VPC-SC perimeter" | HCL for perimeters, access levels, bridges, ingress/egress rules |
| **Generate YAML** | "Create an ingress rule for BigQuery cross-project read" | YAML ready for `gcloud --set-ingress-policies` |
| **Troubleshoot denials** | "Troubleshoot RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER" | Root cause, resolution steps, common pitfalls |
| **Validate Terraform** | "Validate this Terraform code" | Runs `terraform init + validate + fmt` on generated HCL |
| **Get implementation guide** | "Generate an implementation guide" | 7-phase Terraform plan with both raw HCL and module calls |

## Recommended onboarding flow

Whether you're new to VPC-SC or adding a new project to an existing perimeter, follow this sequence:

```
1. ASSESS          Run a diagnostic to understand your current state
                   → diagnose_project + diagnose_org_policies

2. PLAN            Review findings: protection gaps, non-compliant policies, violations
                   → Decide which services to restrict, which rules you need

3. GENERATE        Produce Terraform for the perimeter, access levels, and rules
                   → generate_implementation_guide or individual generate_* tools

4. VALIDATE        Check the generated Terraform is syntactically correct
                   → validate_terraform

5. DRY-RUN         Deploy the perimeter in dry-run mode (logs violations, doesn't block)
                   → terraform apply with dry_run=True configuration

6. MONITOR         Watch for violations over 7+ days, add rules for legitimate traffic
                   → check_vpc_sc_violations (run daily)

7. ENFORCE         Switch from dry-run to enforced mode
                   → Update Terraform from spec block to status block

8. MAINTAIN        Ongoing monitoring and compliance
                   → diagnose_project + diagnose_org_policies periodically
```

See [Use Cases](use-cases.md) for detailed walkthroughs of each step in common scenarios.

## Need help?

| Topic | Document |
|---|---|
| VPC-SC concepts explained | [Concepts](concepts.md) |
| Practical scenarios | [Use Cases](use-cases.md) |
| All 40 tools explained | [MCP Server Guide](mcp-server-guide.md) |
| Security controls | [Security](security.md) |
| Architecture | [Architecture](architecture.md) |
| Cloud Run deployment details | [Runbook: Cloud Run](runbook-cloud-run.md) |
| Cloud Shell details | [Runbook: Cloud Shell](runbook-cloudshell.md) |
| Local setup details | [Runbook: Local](runbook-local.md) |
