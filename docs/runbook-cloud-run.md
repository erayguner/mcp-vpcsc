# Runbook: Cloud Run Deployment

For a quick-start version, see [Getting Started — Cloud Run setup](getting-started.md#cloud-run-setup). For security details, see [Security](security.md#cloud-run-deployment-security).

## Prerequisites

- `gcloud` CLI authenticated with a project that has billing enabled
- `terraform` >= 1.14
- Docker (for local builds) or Cloud Build (for remote builds)
- IAM: `roles/run.admin`, `roles/iam.serviceAccountCreator`, `roles/artifactregistry.admin` on the target project

## Step 1: Configure Terraform

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:

```hcl
project_id = "your-project-id"

invoker_members = [
  "user:you@your-org.com",
  "group:platform-team@your-org.com",
]
```

Secure defaults applied automatically:
- `ingress = "INGRESS_TRAFFIC_INTERNAL_ONLY"` (no public access)
- `deletion_protection = true`
- Dedicated SA with `policyReader` + `logging.viewer` only
- Health probes on `/health`
- Non-root container

## Step 2: Create infrastructure

```bash
terraform init
terraform plan
terraform apply
```

Creates: service account, Artifact Registry repo, Cloud Run service, IAM bindings, 5xx error metric.

## Step 3: Build and push the container

Option A — Cloud Build (recommended):

```bash
cd ..
gcloud builds submit --region=europe-west2 --config=cloudbuild.yaml
```

Option B — Local Docker build:

```bash
REGION=europe-west2
PROJECT=your-project-id
TAG=latest

docker build -t ${REGION}-docker.pkg.dev/${PROJECT}/vpcsc-mcp/vpcsc-mcp:${TAG} .
docker push ${REGION}-docker.pkg.dev/${PROJECT}/vpcsc-mcp/vpcsc-mcp:${TAG}
```

## Step 4: Verify the deployment

```bash
# Check service is running
gcloud run services describe vpcsc-mcp --region=europe-west2

# Check health (via proxy)
gcloud run services proxy vpcsc-mcp --region=europe-west2 --port=3000 &
curl http://localhost:3000/health
```

Expected: `{"status":"ok","server":"vpcsc-mcp","version":"0.1.0","tools":40}`

## Step 5: Connect via proxy

```bash
gcloud run services proxy vpcsc-mcp --region=europe-west2 --port=3000
```

Leave running. This creates an authenticated tunnel.

## Step 6: Connect Gemini CLI

Add the MCP server to Gemini CLI config (`~/.gemini/settings.json`):

```json
{
  "mcpServers": {
    "vpcsc-mcp": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

Then start Gemini CLI:

```bash
gemini
```

## Step 7: Test

In Gemini CLI, ask:

> Run a diagnostic on my project

The diagnostic scans 10 areas and produces a protection gap analysis showing which APIs are `[PROTECTED]`, which are `[GAP]`, and a clear `STATUS:` line. Then:

> Generate an implementation guide for data-analytics workload

This produces Terraform code (raw HCL + The module call) tailored to your project.

## Deploy ADK agent to Cloud Run (optional)

```bash
cd examples/adk-agent
adk deploy cloud_run \
  --project=your-project-id \
  --region=europe-west2 \
  --service_name=vpcsc-adk-agent \
  --with_ui \
  ./vpcsc_agent \
  -- --no-allow-unauthenticated
```

## Security controls active on Cloud Run

| Control | Default |
|---|---|
| Public access | Blocked (`INGRESS_TRAFFIC_INTERNAL_ONLY`) |
| Authentication | IAM required (`roles/run.invoker`) |
| Service account | Dedicated, read-only (`policyReader` + `logging.viewer`) |
| Transport | Streamable HTTP (stateless, scale-to-zero) |
| Health probes | `/health` (startup + liveness) |
| Network binding | `0.0.0.0` (detected via `K_SERVICE` env var) |
| Tool annotations | 40 tools annotated (38 readOnly, 2 destructive) |
| Output sanitisation | Strips prompt-injection patterns |
| Command allowlist | 9 subcommands, 11 flags |
| Subprocess timeout | 120s |
| Container user | Non-root (UID 1001) |
| Container registry | Artifact Registry with cleanup policies |
| Deletion protection | Enabled |
| Binary authorization | Available (`enable_binary_authorization = true`) |
| Immutable tags | Available (`immutable_tags = true`) |

## Updating

Push a new container image:

```bash
gcloud builds submit --region=europe-west2 --config=cloudbuild.yaml
```

Update infrastructure:

```bash
cd terraform && terraform plan && terraform apply
```

## Teardown

```bash
cd terraform
# Set deletion_protection = false first
terraform apply
terraform destroy
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `terraform apply` fails on APIs | Wait 60s and retry — API enablement is eventually consistent |
| Container fails to start | `gcloud run services logs read vpcsc-mcp --region=europe-west2` |
| Proxy returns 403 | Verify your user has `roles/run.invoker` on the service |
| gcloud tools return errors | The SA needs `policyReader` at the **org** level for cross-project policies — uncomment the org-level IAM block in `terraform/main.tf` |
| Slow cold starts | Set `min_instances = 1` in tfvars |
| Health check fails | Verify the container starts and `/health` responds — check `gcloud run services logs` |
| `BLOCKED: Flag 'X' not in allowed list` | The server only allows 11 gcloud flags. This is by design to prevent privilege escalation. |
