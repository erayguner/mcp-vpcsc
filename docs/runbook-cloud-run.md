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
- `enable_binary_authorization = true` — Cloud Run will reject unsigned images
- `immutable_tags = true` — Artifact Registry refuses tag overwrites
- Dedicated SA with `policyReader` + `logging.viewer` only
- Health probes on `/health`
- Non-root container

### Binary Authorization (required when enabled)

When `enable_binary_authorization = true` and `use_default_binauthz_policy = false` (both defaults), you must provide the cosign public key that CI uses to sign the image:

```hcl
# If you use keyless cosign in CI (the default workflow), extract the public key
# that was used to sign the latest image and paste the PEM here. See:
#   cosign verify --certificate-identity-regexp ... <image>@<digest>
binauthz_cosign_public_key_pem = <<-EOT
-----BEGIN PUBLIC KEY-----
MFkw...
-----END PUBLIC KEY-----
EOT
```

Alternative: set `use_default_binauthz_policy = true` to fall back to Google's permissive default policy (not recommended for production). Set `enable_binary_authorization = false` entirely only in dev clusters.

### Audit log env vars (recommended for production)

Set these on the Cloud Run service via `var.environment_variables` to activate on-disk audit, chained manifest, and HMAC signing:

```hcl
environment_variables = {
  VPCSC_MCP_AUDIT_DIR = "/var/audit"           # writable volume or ephemeral
  VPCSC_MCP_AUDIT_DLQ = "/var/audit/dlq.jsonl" # replay via AuditLogger.replay_dlq()
  # Prefer the Secret Manager route below; never bake the key into plain env.
}

# Mount the HMAC key from Secret Manager (hex-encoded 32 bytes recommended):
#   VPCSC_MCP_AUDIT_KEY (secret): hex-encoded HMAC key
```

Without `VPCSC_MCP_AUDIT_KEY`, the logger falls back to a process-ephemeral key — fine for dev, never for prod. Without `VPCSC_MCP_AUDIT_DIR`, entries still reach Cloud Logging but there is no on-disk chain file and no signed manifest.

**Independent blast radius (framework §8.5).** Sink the `vpcsc_mcp.audit` Python logger to a Cloud Logging **log bucket in a separate project** so the agent's own identity cannot delete entries. Configure via a logging sink in Terraform that filters on `logName=/logs/vpcsc_mcp.audit` and routes to the forensic project.

### Metrics exporter (optional)

To export per-tool / per-principal call metrics to Cloud Monitoring, install the optional OTel dependency and set the env var:

```hcl
environment_variables = {
  VPCSC_MCP_METRICS_EXPORT = "otel-cloudmon"   # or "otel-stdout" for debug
}
```

Requires `opentelemetry-sdk` + `opentelemetry-exporter-gcp-monitoring` to be installed in the image. The SA already has `roles/monitoring.metricWriter`.

### Principal extraction (recommended for production)

The per-principal rate limiter, audit log, and metrics key off the caller principal that the `PrincipalMiddleware` extracts from request headers. When the Cloud Run service is invoked behind IAP or with Google-authenticated IAM bindings, `X-Goog-Authenticated-User-Email` is populated automatically — no env var needed. For MCP clients that authenticate by other means, route a stable identifier through `X-MCP-Client-ID` (or `X-MCP-Principal`).

Set a fallback for unmatched requests:

```hcl
environment_variables = {
  VPCSC_MCP_DEFAULT_PRINCIPAL = "cloud-run-anonymous"
}
```

Header precedence (first non-empty wins): `X-MCP-Client-ID` → `X-MCP-Principal` → `X-Goog-Authenticated-User-Email` → `X-Serverless-Authorization`. Without any of these and without the fallback env var, the principal is `"anonymous"` and the per-principal bucket collapses to a single shared bucket for all callers.

### Generated Terraform file output (if enabled)

When an MCP client invokes a Terraform-generating tool with `project_name` set, the server writes the generated `.tf` to disk. To confine writes, set:

```hcl
environment_variables = {
  VPCSC_MCP_OUTPUT_ROOT = "/var/terraform-out"
}
```

Paths outside the allowed root (absolute paths, `..` traversal, symlinks that resolve elsewhere) raise `ValueError`. If unset, the server uses its current working directory as the root. Mount a writable volume at this path if `project_name` will be used in production.

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

Expected (healthy): `{"status":"ok","server":"vpcsc-mcp","version":"0.1.0","tools":43,"resources":6,"prompts":3,"breaker":"closed","active_halts":0}`

If the service returns `503` with `"status":"degraded"`, either the gcloud circuit breaker is OPEN or an operator halt is active. Run `list_active_halts` via the MCP or inspect Cloud Monitoring for the `breaker` state before treating the 503 as an infrastructure failure.

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
| Tool annotations | 43 tools annotated (36 readOnly, 4 destructive write, 2 halt, 1 resume) |
| Output sanitisation | Strips prompt-injection patterns |
| Caller-input filter | Blocks secrets + prompt-injection in free-text args; redacts PII |
| Command allowlist | 9 subcommands, 12 flags (`allowlist-drift` CI enforces) |
| Subprocess timeout | 120s |
| Circuit breaker | OPEN after 5 consecutive gcloud failures; cool-off backoff |
| Rate limiter | Per-principal (3) + global (5) concurrent gcloud calls |
| Audit log | SHA-256 chained, daily HMAC manifest, DLQ-backed, signed export |
| Kill-switch | `halt_session` tool + `/health` returns 503 while active |
| Container user | Non-root (UID 1001) |
| Container registry | Artifact Registry with cleanup policies |
| Deletion protection | Enabled |
| Binary authorization | **Enabled by default** (`enable_binary_authorization = true`) |
| Immutable tags | **Enabled by default** (`immutable_tags = true`) |
| CI supply-chain gates | cosign keyless sign, Trivy scan, SLSA provenance attest, tflint, tfsec |

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

## Incident response — halt a misbehaving agent

If a caller (human or agent) is issuing unsafe / unexpected gcloud calls through the MCP, halt in under a minute without a deploy or IAM change.

From an MCP client with access to the server:

```
halt_session(scope="global", reason="incident #42 — unexpected perimeter churn", actor="oncall-alice")
```

To target a specific caller (identify them via the `principal` field in the audit log):

```
halt_session(scope="principal:agent-bob", reason="rogue agent loop", actor="oncall-alice")
```

To target a specific tool surface (e.g. write operations only):

```
halt_session(scope="tool:gcloud.access-context-manager", reason="pending policy review", actor="oncall-alice")
```

While any halt is active, `/health` returns 503 — if your traffic manager treats 503 as a degraded instance, requests are automatically failed over. To confirm halt state without hitting the MCP:

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://<service-url>/health
```

Lift the halt when the incident is resolved:

```
resume_session(scope="global", actor="oncall-alice")
```

Every halt / resume is written to the chained audit log. Pull the forensic bundle afterwards via `AuditLogger.export_signed(since=<incident start>, until=<now>)`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `terraform apply` fails on APIs | Wait 60s and retry — API enablement is eventually consistent |
| Container fails to start | `gcloud run services logs read vpcsc-mcp --region=europe-west2` |
| Proxy returns 403 | Verify your user has `roles/run.invoker` on the service |
| `/health` returns 503 with `breaker=open` | gcloud circuit breaker tripped (5 consecutive failures). Check upstream gcloud health; breaker will transition to HALF_OPEN after cool-off and recover automatically on the first successful call |
| `/health` returns 503 with `active_halts>0` | An operator halt is active. Call `list_active_halts` to inspect; `resume_session` to lift |
| Deployment fails with `denied: image not attested` | Binary Authorization rejected the image. Either the cosign signature is missing (CI job `sign-and-push` didn't run or failed) or `binauthz_cosign_public_key_pem` is wrong. Temporary workaround: set `enable_binary_authorization = false` and apply — then investigate the CI signature |
| `AuditChainError` on startup | The on-disk audit file was edited / corrupted. Don't "fix" it — investigate as a security incident, preserve the file, and start a fresh audit directory only after forensic capture |
| DLQ not draining | Call `AuditLogger.replay_dlq()` once the root cause (disk full, permissions) is fixed |
| gcloud tools return errors | The SA needs `policyReader` at the **org** level for cross-project policies — uncomment the org-level IAM block in `terraform/main.tf` |
| Slow cold starts | Set `min_instances = 1` in tfvars |
| Health check fails | Verify the container starts and `/health` responds — check `gcloud run services logs` |
| `BLOCKED: Flag 'X' not in allowed list` | The server only allows 12 gcloud flags. This is by design to prevent privilege escalation. |
| `CIRCUIT_OPEN` with `retry_after_seconds` | gcloud breaker is open — respect the retry-after; do not loop |
| `HALTED` with `scope=...` | The named scope is in a halt; call `list_active_halts` and coordinate with the operator who engaged it |
