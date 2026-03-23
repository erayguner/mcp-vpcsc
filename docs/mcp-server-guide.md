# VPC-SC MCP Server — User Guide

A Model Context Protocol (MCP) server that helps AI agents and developers set up, manage, and troubleshoot Google Cloud VPC Service Controls. Built with the Python MCP SDK v1.26.0 (FastMCP).

---

## Table of Contents

- [What this server does](#what-this-server-does)
- [What this server does NOT do](#what-this-server-does-not-do)
- [Installation](#installation)
- [Connecting to Gemini CLI](#connecting-to-gemini-cli)
- [Tools reference](#tools-reference)
  - [gcloud operations](#1-gcloud-operations)
  - [Terraform generation](#2-terraform-generation)
  - [Analysis and troubleshooting](#3-analysis-and-troubleshooting)
  - [Rule generation and patterns](#4-rule-generation-and-patterns)
  - [Diagnostics and implementation guides](#5-diagnostics-and-implementation-guides)
- [Resources and prompts](#resources-and-prompts)
- [Validation rules and constraints](#validation-rules-and-constraints)
- [Terraform examples with the perimeter module](#terraform-examples-with-the-ons-perimeter-module)
  - [Complete perimeter example](#complete-perimeter-example)
  - [Egress rule variables](#egress-rule-variables)
  - [Ingress rule variables](#ingress-rule-variables)
  - [Bridge perimeter example](#bridge-perimeter-example)
  - [How rules are assembled inside the module](#how-rules-are-assembled-inside-the-module)
- [End-to-end workflow examples](#end-to-end-workflow-examples)
- [Limitations and known behaviour](#limitations-and-known-behaviour)

---

## What this server does

| Capability | Description |
|---|---|
| **Query live infrastructure** | Lists perimeters, access levels, policies, and audit-log violations by calling `gcloud` on your behalf |
| **Generate Terraform HCL** | Produces ready-to-paste HCL blocks for perimeters, access levels, bridges, and ingress/egress policies |
| **Generate gcloud YAML** | Creates YAML files compatible with `--set-ingress-policies` / `--set-egress-policies` flags |
| **Troubleshoot violations** | Maps VPC-SC violation codes to root causes, common pitfalls, and step-by-step resolution |
| **Recommend services** | Suggests which GCP APIs to restrict based on workload type (AI/ML, data analytics, web app, healthcare, data warehouse) |
| **Validate inputs** | Checks identity format, service support, and perimeter design before you apply anything |
| **Provide patterns** | Supplies pre-built ingress/egress rule templates for common scenarios (BigQuery cross-project reads, Cloud Build deploys, Vertex AI predictions, etc.) |
| **Diagnose projects** | Scans the authenticated project for VPC-SC readiness: enabled APIs, org, perimeters, SAs, violations |
| **Generate implementation guides** | Produces 7-phase Terraform guides with both raw HCL and The module calls |
| **Health check** | `/health` endpoint for Cloud Run probes (HTTP transports only) |

## What this server does NOT do

- **It does not apply changes.** It generates configurations and runs read-only `gcloud` queries. You decide when to `terraform apply` or `gcloud ... update`.
- **It does not manage IAM.** Identity bindings, role grants, and service account creation are out of scope.
- **It does not replace `terraform plan`.** Generated HCL is a starting point. Always run `terraform validate` and `terraform plan` before applying.
- **It does not store credentials.** It calls whichever `gcloud` is on your PATH using your active authentication. No tokens are cached or transmitted.
- **It does not guarantee completeness.** The supported-services list covers ~53 commonly used APIs. Newly added GCP services may not be included yet.

---

## Installation

### Prerequisites

- Python 3.10 or later
- `gcloud` CLI installed and authenticated (`gcloud auth login` + `gcloud auth application-default login`)
- Appropriate IAM permissions to read Access Context Manager resources and Cloud Audit Logs

### Install the package

```bash
cd vpcsc-mcp
pip install -e ".[dev]"
```

### Verify it works

```bash
# Check the server starts and responds
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' \
  | python -m vpcsc_mcp.server
```

You should see a JSON response containing `"serverInfo":{"name":"VPC-SC Helper"}`.

---

## Connecting to Gemini CLI

Create or edit `~/.gemini/settings.json`:

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

Start `gemini`. The 35 tools, 5 resources, and 3 prompts are available automatically.

---

## Tools reference

### 1. gcloud operations

These tools execute `gcloud access-context-manager` commands against your live GCP environment. They require an authenticated `gcloud` session.

| Tool | Purpose | Required arguments |
|---|---|---|
| `list_access_policies` | List all access policies for an org | `organization_id` |
| `list_perimeters` | List all perimeters in a policy | `policy_id` |
| `describe_perimeter` | Full JSON detail of one perimeter | `policy_id`, `perimeter_name` |
| `list_access_levels` | List all access levels in a policy | `policy_id` |
| `describe_access_level` | Full JSON detail of one access level | `policy_id`, `level_name` |
| `check_vpc_sc_violations` | Query audit logs for VPC-SC denials | `project_id` (+ optional `freshness`, `limit`) |
| `dry_run_status` | Show perimeters with pending dry-run configs | `policy_id` |
| `update_perimeter_resources` | Add/remove projects from a perimeter | `policy_id`, `perimeter_name`, `add_projects` or `remove_projects`, `confirm` |
| `update_perimeter_services` | Add/remove restricted services | `policy_id`, `perimeter_name`, `add_services` or `remove_services`, `confirm` |

**Behaviour notes:**

- All commands append `--format=json` and parse the output. If the command fails, the error message from `gcloud` is returned verbatim.
- Only 9 gcloud subcommands are permitted (access-context-manager, config, compute, iam, logging, org-policies, organizations, projects, services). All others are blocked.
- Arguments are validated against a safe character pattern. Shell metacharacters are rejected.
- Each gcloud command has a 120-second timeout. Hung processes are killed.
- `check_vpc_sc_violations` reads from Cloud Audit Logs. The caller needs `roles/logging.viewer` on the project.
- `update_perimeter_resources` and `update_perimeter_services` are **write operations**. They require `confirm=True` to execute. Without it, they return a preview of what would change. Project references must start with `projects/` and service names must end with `.googleapis.com`.

### 2. Terraform generation

These tools produce HCL strings. They do **not** write files or call Terraform. You paste the output into your `.tf` files.

| Tool | Purpose |
|---|---|
| `generate_perimeter_terraform` | Regular perimeter resource block |
| `generate_access_level_terraform` | Access level resource block |
| `generate_bridge_terraform` | Bridge perimeter resource block |
| `generate_ingress_policy_terraform` | Single `ingress_policies` block (for pasting inside a perimeter) |
| `generate_egress_policy_terraform` | Single `egress_policies` block (for pasting inside a perimeter) |
| `generate_vpc_accessible_services_terraform` | `vpc_accessible_services` block |
| `generate_full_perimeter_terraform` | Complete perimeter with inline ingress and egress policies |
| `validate_terraform` | Run `terraform init` + `validate` + `fmt -check` on generated HCL |

**Behaviour notes:**

- All HCL generators produce **raw `google_access_context_manager_*` resources**, not module calls. This is intentional — they serve as a reference for what the final resource should look like, which you then translate to your module's variable format (see [Terraform examples](#terraform-examples-with-the-ons-perimeter-module) below).
- `generate_full_perimeter_terraform` accepts `ingress_rules_json` and `egress_rules_json` as JSON strings because MCP tool arguments cannot be nested objects of arbitrary depth.
- When `dry_run=True` (the default), the generated HCL uses a `spec` block and sets `use_explicit_dry_run_spec = true`. When `False`, it uses a `status` block.
- `validate_terraform` writes HCL to a temp directory, adds a Google provider block, runs `terraform init -backend=false`, `terraform validate`, and `terraform fmt -check`, then cleans up. Returns structured errors with line context on failure. Requires `terraform` on PATH.

### 3. Analysis and troubleshooting

| Tool | Purpose |
|---|---|
| `troubleshoot_violation` | Explain a violation code and provide resolution steps |
| `recommend_restricted_services` | Suggest services for a workload type |
| `list_supported_services` | List all known VPC-SC supported services (with optional keyword filter) |
| `check_service_support` | Check if a specific service supports VPC-SC (includes fuzzy matching) |
| `get_method_selectors` | Get pre-defined method/permission selectors for a service and access type |
| `validate_identity_format` | Check that identity strings have the required prefix |
| `analyze_perimeter_design` | Review a planned perimeter and flag issues |
| `check_data_freshness` | Compare built-in data against live project APIs, report server version and data counts |

**Behaviour notes:**

- `check_data_freshness` compares the server's built-in VPC-SC services list against APIs enabled in your project, flags potentially missing services, and reports server version, data counts, and update instructions.
- `troubleshoot_violation` recognises four violation codes: `RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER`, `NO_MATCHING_ACCESS_LEVEL`, `SERVICE_NOT_ALLOWED_FROM_VPC`, and `ACCESS_DENIED_GENERIC`.
- `recommend_restricted_services` supports five workload types: `ai-ml`, `data-analytics`, `web-application`, `data-warehouse`, `healthcare`.
- `get_method_selectors` returns both the human-readable list and a JSON array you can pass directly into the Terraform or YAML generators.

### 4. Rule generation and patterns

| Tool | Purpose |
|---|---|
| `generate_ingress_yaml` | Produce a YAML ingress rule for `gcloud ... --set-ingress-policies` |
| `generate_egress_yaml` | Produce a YAML egress rule for `gcloud ... --set-egress-policies` |
| `list_ingress_patterns` | List all pre-built ingress patterns |
| `list_egress_patterns` | List all pre-built egress patterns |
| `get_ingress_pattern` | Retrieve a pattern with variable substitution |
| `get_egress_pattern` | Retrieve a pattern with variable substitution |

**Pre-built ingress patterns:**

| Pattern name | Scenario |
|---|---|
| `bigquery-cross-project-read` | External SA reads BigQuery datasets inside the perimeter |
| `storage-read-from-access-level` | Corporate network users read GCS objects |
| `vertex-ai-prediction` | External SA calls Vertex AI prediction endpoints |
| `cloud-build-deploy` | Cloud Build SA deploys into the perimeter |
| `devops-console-access` | DevOps group accesses resources via console from corporate network |

**Pre-built egress patterns:**

| Pattern name | Scenario |
|---|---|
| `bigquery-cross-project-query` | SAs inside perimeter query external BigQuery datasets |
| `storage-write-external` | SA inside perimeter writes to external GCS bucket |
| `cloud-functions-deploy` | Cloud Functions SA stores source in external GCS |
| `vertex-ai-training-output` | Vertex AI writes model artifacts to external GCS |
| `logging-export` | Logging SA exports to external BigQuery/GCS |

**Behaviour notes:**

- Patterns use `{placeholder}` syntax. Pass `substitutions` as a JSON string like `{"sa_email": "my-sa@project.iam.gserviceaccount.com", "source_project_number": "123456"}`.
- Unsubstituted placeholders are listed in the response so you know what still needs filling in.
- YAML output includes a comment header showing the exact `gcloud` command to use.

### 5. Diagnostics and implementation guides

| Tool | Purpose |
|---|---|
| `diagnose_project` | Full VPC-SC readiness scan of the authenticated project |
| `generate_implementation_guide` | 7-phase Terraform guide with both raw HCL and The module calls |

**`diagnose_project` runs 10 steps:**

1. Resolve active project, account, project number, parent org
2. Scan enabled APIs against 53 known VPC-SC supported services
3. Flag missing critical APIs (Access Context Manager, Cloud KMS, Secret Manager)
4. Check organisation and access policy
5. List existing perimeters — flag which perimeter contains this project
6. List access levels
7. List service accounts
8. List VPC networks and peerings
9. Query Cloud Audit Logs for VPC-SC violations (last 7 days)
10. **Protection gap analysis** — cross-references enabled APIs against the perimeter's `restricted_services`

**Protection gap analysis output:**

The diagnostic classifies every enabled API into one of three states:

| Label | Meaning |
|---|---|
| `[PROTECTED]` | API is enabled AND in the perimeter's restricted_services |
| `[GAP]` | API is enabled but NOT in the perimeter — unprotected |
| `[NOT ENABLED]` | API missing but commonly needed |

Then provides a clear status and actionable gcloud command:

```
  PROTECTED (20 APIs):
    [PROTECTED] bigquery.googleapis.com (BigQuery)
    [PROTECTED] storage.googleapis.com (Cloud Storage)

  UNPROTECTED (3 APIs — enabled but NOT in perimeter):
    [GAP] dataplex.googleapis.com (Dataplex)
    [GAP] notebooks.googleapis.com (Vertex AI Workbench)

  ACTION: Add these 3 service(s) to the perimeter's restricted_services list.
  Use dry-run mode first:
    gcloud access-context-manager perimeters dry-run update my_perimeter \
      --policy=123456 \
      --add-restricted-services=dataplex.googleapis.com,notebooks.googleapis.com

  STATUS: PARTIALLY PROTECTED — 3 gap(s) to close
```

Three possible statuses:
- `FULLY PROTECTED` — all enabled VPC-SC APIs are in the perimeter
- `PARTIALLY PROTECTED — N gap(s) to close` — some APIs need adding
- `NOT PROTECTED — create a perimeter` — project is not in any perimeter

**`generate_implementation_guide` produces:**

- Phase 1: Prerequisites (gcloud commands)
- Phase 2: Access level Terraform
- Phase 3: Perimeter in dry-run mode (raw HCL)
- Phase 4: Monitoring commands
- Phase 5A: Raw Terraform ingress/egress rules
- Phase 5B: The perimeter module call with auto-detected service accounts mapped to the correct module variables (`ingress_terraform_cloud_build`, `generic_egress_cloudfunctions_deploy`, `generic_ingress_bigquery_read`, etc.)
- Phase 6: Enforcement commands
- Phase 7: Ongoing monitoring
- Module variable quick reference (all common egress/ingress variable names)

**Behaviour notes:**

- Both tools accept an optional `project_id`. Leave empty to use the active `gcloud` project.
- `generate_implementation_guide` accepts `workload_type` to tailor service recommendations.
- Both tools log progress to stderr: `[1/10] Resolving active GCP project...`
- Both tools report progress via MCP Context when available.
- The module Terraform in Phase 5B is ready to paste into your `vpcsc-*.tf` files with minimal edits.

### 6. Organisation Policy compliance

| Tool | Purpose |
|---|---|
| `diagnose_org_policies` | Scan project against 31 baseline org policies, classify as COMPLIANT / NON-COMPLIANT / NOT SET |
| `generate_org_policy_terraform` | Generate Terraform HCL to enforce all recommended org policies |

**`diagnose_org_policies` checks 31 policies across 11 categories:**

| Category | Count | Policies checked |
|---|---|---|
| Compute | 5 | disableSerialPortAccess, skipDefaultNetworkCreation, vmExternalIpAccess, storageResourceUseRestrictions, requireShieldedVm |
| IAM | 7 | disableAuditLoggingExemption, automaticIamGrantsForDefaultServiceAccounts, disableServiceAccountKeyCreation, disableServiceAccountKeyUpload, allowedPolicyMembers, serviceAccountKeyExposureResponse, workloadIdentityPoolProviders |
| Storage | 2 | publicAccessPrevention, uniformBucketLevelAccess |
| GCP-wide | 4 | resourceLocations, detailedAuditLoggingMode, allowedContactDomains, restrictServiceUsage |
| Cloud Run | 2 | allowedIngress, allowedVPCEgress |
| GKE | 1 | restrictPublicClusters |
| GKE custom | 3 | maintenance windows, release channels, node pool auto-upgrade |
| Cloud SQL | 1 | restrictPublicIp |
| Cloud SQL custom | 1 | password policy (min 16 chars, complexity) |
| Firestore | 1 | requireP4SAforImportExport |
| SCC custom | 4 | container threat detection, event threat detection, security health analytics, VM threat detection |

**Output classifies each policy:**

```
--- COMPLIANT (12) ---
  [COMPLIANT] compute.disableSerialPortAccess
    Disable serial port access on VMs

--- NON-COMPLIANT (3) ---
  [NON-COMPLIANT] storage.publicAccessPrevention  (risk: HIGH)
    Prevent public access to Cloud Storage buckets
    Why: Public buckets are the #1 cause of data leaks in GCP.

--- NOT SET (3) ---
  [NOT SET] compute.requireShieldedVm  (risk: MEDIUM)
    Require Shielded VMs
    Why: Shielded VMs protect against rootkits and bootkits.

ORG POLICY COMPLIANCE SUMMARY
  Policies checked: 18
  Compliant:      12
  Non-compliant:  3 <-- ACTION NEEDED
  Not set:        3 <-- ACTION NEEDED
  STATUS: NON-COMPLIANT — 4 HIGH risk issue(s)
```

**`generate_org_policy_terraform` produces HCL for all 31 policies**, grouped by category, with risk labels and rationale as comments. Supports `scope="project"` or `scope="organization"`.

**Behaviour notes:**

- Requires `roles/orgpolicy.policyViewer` on the project or org.
- Requires the `orgpolicy.googleapis.com` API enabled.
- Recommendations are prioritised by risk: HIGH (fix immediately), MEDIUM (fix in next sprint).
- The org policy baseline matches the `gcp-terraform-org-policy` module.

---

## Resources and prompts

### Resources (read-only data endpoints)

| URI | Content |
|---|---|
| `vpcsc://services/supported` | Full list of 53 VPC-SC supported services |
| `vpcsc://workloads/{workload_type}` | Workload recommendations (ai-ml, data-analytics, etc.) |
| `vpcsc://patterns/ingress` | All ingress patterns as JSON |
| `vpcsc://patterns/egress` | All egress patterns as JSON |
| `vpcsc://troubleshooting/guide` | Full troubleshooting guide as JSON |

### Prompts (conversation starters)

| Prompt | Purpose | Key arguments |
|---|---|---|
| `design_perimeter` | Guide the design of a new perimeter | `workload_description`, `project_count`, `has_external_access` |
| `troubleshoot_denial` | Diagnose a VPC-SC access denial | `error_message`, `service_name`, `caller_identity` |
| `migrate_to_vpcsc` | Plan a phased migration to VPC-SC | `project_ids`, `current_services` |

---

## Validation rules and constraints

The MCP server enforces the same validation rules as the Terraform modules. Understanding these prevents errors at both the MCP and Terraform layers.

### Identity format

All identities **must** start with one of:

```
serviceAccount:
user:
group:
```

The `validate_identity_format` tool checks this. Terraform variables enforce it with:

```hcl
can(regex("^serviceAccount:|^user:|^group:", x))
```

Examples:

```
serviceAccount:my-sa@my-project.iam.gserviceaccount.com
user:admin@example.com
group:team@example.com
```

### Resource format

All resources **must** start with `projects/` or be exactly `*`:

```hcl
can(regex("^projects/|^[*]$", x))
```

Use project **numbers** (not IDs): `projects/123456789`

### Access level format

Access levels **must** start with `accessPolicies`:

```
accessPolicies/123456/accessLevels/my_level
```

### Perimeter name format (convention)

Perimeter names must be lowercase and end with an environment suffix:

```
_prod    _preprod    _nonprod    _dryrun
```

### Method selectors: `method` vs `permission`

This is the single most common source of confusion with VPC-SC rules:

| Type | Format | Used by |
|---|---|---|
| `method` | RPC-style: `google.storage.objects.get` | Cloud Storage, Vertex AI, Pub/Sub |
| `permission` | IAM-style: `bigquery.tables.getData` | BigQuery, Data Catalog |

**Rule:** If a service uses `permission` selectors and you specify `method` selectors (or vice versa), the rule will not match and the request will be denied. The `get_method_selectors` tool returns the correct format for each service.

---

## Terraform examples with the perimeter module

The MCP server generates raw `google_access_context_manager_*` HCL as a reference. In this repository, perimeters are created by calling the perimeter module. This section shows how to translate MCP output into module calls.

### How the module works

The perimeter module (`gcp-vpcsc-modules/perimeter/`) uses a pattern where:

1. **You provide identities and target resources** via typed variables (e.g., `generic_egress_bigquery_read`)
2. **The module provides the operations** (service name + method selectors) as `locals`
3. **They are merged together** with `merge(rule, local.operations)` to form complete policies

This means you never write method selectors yourself — you pick the right variable name and supply who (identities) and where (resources).

### Complete perimeter example

```hcl
module "my_team_prod" {
  source         = "gcs::https://www.googleapis.com/storage/v1/ons-ci-functions/modules/gcp-vpcsc-modules/gcp-vpcsc-modules-v2.16.5/perimeter"
  parent         = data.google_access_context_manager_access_policy.org-access-policy.name
  name           = "my_team_prod"
  perimeter_type = "PERIMETER_TYPE_REGULAR"

  # ── Services to restrict ──────────────────────────────────────────────
  restricted_services = [
    "bigquery.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "compute.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ]

  # ── Access levels that bypass the perimeter ───────────────────────────
  access_levels = [
    local.ci_cloudbuild_exemption_access_level,
  ]

  # ── Projects inside the perimeter ─────────────────────────────────────
  resources = [
    local.my_team_data_prod,       # "projects/111111111"
    local.my_team_analytics_prod,  # "projects/222222222"
    local.my_team_landing_prod,    # "projects/333333333"
  ]

  vpc_accessible_services = ["RESTRICTED-SERVICES"]

  # ── Egress: admin full access ─────────────────────────────────────────
  admin_egress_all = [
    {
      identities = toset(flatten([local.vpc_sc_admin_groups]))
      resources  = ["*"]
    },
  ]

  # ── Egress: BigQuery read to external project ─────────────────────────
  generic_egress_bigquery_read = [
    {
      identities = [local.my_team_data_prod_composer_sa]
      resources  = [local.shared_data_prod]
    },
  ]

  # ── Egress: write objects to external storage ─────────────────────────
  generic_egress_storage_writer = [
    {
      identities = [local.my_team_data_prod_export_sa]
      resources  = [local.external_output_prod]
    },
  ]

  # ── Ingress: Cloud Build deploy ───────────────────────────────────────
  ingress_terraform_cloud_build = [
    {
      title        = "CI/CD Cloud Build deploy"
      identities   = [local.my_team_cicd_cloudbuild_sa]
      resources    = ["*"]
    },
  ]

  # ── Ingress: DevOps console access from corporate network ─────────────
  admin_ingress_all = [
    {
      title        = "VPC-SC admins from UK office"
      access_level = [local.console_access_level_uk_access_level]
      identities   = flatten([local.vpc_sc_admin_groups])
      resources    = ["*"]
    },
  ]

  # ── Ingress: BigQuery read from external project ──────────────────────
  generic_ingress_bigquery_read = [
    {
      title      = "Shared analytics SA reads BQ datasets"
      identities = [local.shared_analytics_sa]
      resources  = [local.my_team_analytics_prod]
      source_resource = [local.shared_analytics_project]
    },
  ]

  # ── Ingress: Storage read from access level ───────────────────────────
  generic_ingress_storage_reader = [
    {
      title        = "Corporate network users read GCS"
      access_level = [local.cisco_umbrella_vpn_access_level]
      identities   = flatten([local.my_team_data_users_group])
      resources    = ["*"]
    },
  ]
}
```

### Egress rule variables

The module provides egress variables with pre-defined operations. Here is how MCP tool output maps to the module:

**When the MCP `recommend_restricted_services` or `get_egress_pattern` tool suggests an egress rule like:**

> Allow `serviceAccount:composer-sa@my-project.iam.gserviceaccount.com` to read BigQuery in `projects/999888777`

**You translate it to the module variable:**

```hcl
# The module already knows the BigQuery read operations:
#   bigquery.datasets.get, bigquery.tables.getData, bigquery.tables.list, etc.
# You only supply WHO and WHERE.

generic_egress_bigquery_read = [
  {
    identities = ["serviceAccount:composer-sa@my-project.iam.gserviceaccount.com"]
    resources  = ["projects/999888777"]
  },
]
```

**Common egress variable names and what they allow:**

| Variable name | Service | Access level |
|---|---|---|
| `admin_egress_all` | `*` (all services) | All methods |
| `generic_egress_bigquery_read` | `bigquery.googleapis.com` | datasets.get, tables.getData, tables.list, jobs.create |
| `generic_egress_bigquery_stream_writer` | `bigquery.googleapis.com` | TableDataService.InsertAll |
| `generic_egress_storage_reader` | `storage.googleapis.com` | objects.get, objects.list, buckets.get |
| `generic_egress_storage_writer` | `storage.googleapis.com` | objects.create, objects.delete |
| `generic_egress_storage_deleter` | `storage.googleapis.com` | objects.delete, buckets.delete |
| `generic_egress_cloudfunctions_all` | `cloudfunctions.googleapis.com` | All methods |
| `generic_egress_cloudfunctions_deploy` | `storage.googleapis.com` | All methods (for function source upload) |
| `generic_egress_pubsub_all` | `pubsub.googleapis.com` | All methods |
| `generic_egress_pubsub_publisher` | `pubsub.googleapis.com` | Publisher.Publish |
| `generic_egress_logging_all` | `logging.googleapis.com` | All methods |
| `generic_egress_monitoring_all` | `monitoring.googleapis.com` | All methods |
| `generic_egress_secretmanager_all` | `secretmanager.googleapis.com` | All methods |
| `generic_egress_iam_all` | `iam.googleapis.com` | All methods |
| `generic_egress_run_http` | `run.googleapis.com` | HttpService.InvokeService |
| `data_engineer_egress_output_project` | `bigquery` + `storage` | BigQuery write + GCS read/write |
| `data_engineer_egress_viewer_output_project` | `bigquery` + `storage` | BigQuery read-only + GCS read-only |

**Egress variable shape:**

```hcl
variable "generic_egress_bigquery_read" {
  type = list(object({
    title      = optional(string, "")
    identities = list(string)    # Must start with serviceAccount:, user:, or group:
    resources  = list(string)    # Must start with projects/ or be *
  }))
  default = null
}
```

### Ingress rule variables

Ingress variables have the same pattern but include additional source fields:

**When the MCP `get_ingress_pattern` tool returns a pattern like:**

> Allow `serviceAccount:external-sa@other-project.iam.gserviceaccount.com` from `projects/555666777` to read BigQuery inside the perimeter

**You translate it to:**

```hcl
generic_ingress_bigquery_read = [
  {
    title           = "External analytics SA reads our BQ datasets"
    identities      = ["serviceAccount:external-sa@other-project.iam.gserviceaccount.com"]
    resources       = ["*"]
    source_resource = ["projects/555666777"]
  },
]
```

**Common ingress variable names and what they allow:**

| Variable name | Service | Access level |
|---|---|---|
| `admin_ingress_all` | `*` (all services) | All methods |
| `ingress_terraform_cloud_build` | `*` (all services) | All methods |
| `generic_ingress_bigquery_all` | `bigquery.googleapis.com` | All methods |
| `generic_ingress_bigquery_read` | `bigquery.googleapis.com` | datasets.get, tables.getData, tables.list, jobs.create |
| `generic_ingress_bigquery_stream_writer` | `bigquery.googleapis.com` | TableDataService.InsertAll |
| `generic_ingress_storage_all` | `storage.googleapis.com` | All methods |
| `generic_ingress_storage_reader` | `storage.googleapis.com` | objects.get, objects.list, buckets.get |
| `generic_ingress_storage_writer` | `storage.googleapis.com` | objects.create, objects.delete |
| `generic_ingress_cloudfunctions_all` | `cloudfunctions.googleapis.com` | All methods |
| `generic_ingress_pubsub_all` | `pubsub.googleapis.com` | All methods |
| `generic_ingress_pubsub_publisher` | `pubsub.googleapis.com` | Publisher.Publish |
| `generic_ingress_pubsub_reader` | `pubsub.googleapis.com` | Subscriber.Pull, StreamingPull |
| `generic_ingress_secretmanager_all` | `secretmanager.googleapis.com` | All methods |
| `generic_ingress_logging_all` | `logging.googleapis.com` | All methods |
| `generic_ingress_compute_all` | `compute.googleapis.com` | All methods |
| `generic_ingress_container_all` | `container.googleapis.com` | All methods |
| `generic_ingress_run_all` | `run.googleapis.com` | All methods |
| `generic_ingress_cloudkms_all` | `cloudkms.googleapis.com` | All methods |
| `generic_ingress_composer_all` | `composer.googleapis.com` | All methods |

**Ingress variable shape:**

```hcl
variable "generic_ingress_bigquery_read" {
  type = list(object({
    title           = optional(string, "")
    access_level    = optional(list(string), [])   # Full access level resource names
    source_resource = optional(list(string), [])   # Source project resource names
    identities      = list(string)                 # Must start with serviceAccount:, user:, or group:
    resources       = list(string)                 # Must start with projects/ or be *
  }))
  default = null
}
```

### Bridge perimeter example

Bridge perimeters connect two regular perimeters by listing projects from both sides. They contain no restricted services or rules.

```hcl
module "bridge_team_a_to_team_b" {
  source         = "gcs::https://www.googleapis.com/storage/v1/ons-ci-functions/modules/gcp-vpcsc-modules/gcp-vpcsc-modules-v2.16.5/bridge"
  parent         = data.google_access_context_manager_access_policy.org-access-policy.name
  name           = "bridge_team_a_to_team_b_prod"
  perimeter_type = "PERIMETER_TYPE_BRIDGE"

  resources = [
    local.team_a_data_prod,   # project from perimeter A
    local.team_b_data_prod,   # project from perimeter B
  ]
}
```

### How rules are assembled inside the module

Understanding this pattern helps you debug unexpected behaviour.

**Step 1: You provide identities and resources**

```hcl
generic_egress_bigquery_read = [
  {
    identities = ["serviceAccount:my-sa@project.iam.gserviceaccount.com"]
    resources  = ["projects/123456"]
  },
]
```

**Step 2: The module defines the operations in a local**

```hcl
# In rules-egress.tf
locals {
  generic_egress_bigquery_read = {
    operations = {
      "bigquery.googleapis.com" = {
        permissions = [
          "bigquery.datasets.get",
          "bigquery.tables.get",
          "bigquery.tables.getData",
          "bigquery.tables.list",
          "bigquery.jobs.create",
        ]
      }
    }
  }
}
```

**Step 3: They are merged**

```hcl
generic_egress_bigquery_read_rule = (
  var.generic_egress_bigquery_read == null ? [] :
  [
    for rule in var.generic_egress_bigquery_read :
      merge(rule, local.generic_egress_bigquery_read)
  ]
)
```

**Step 4: All rules are concatenated into a single list**

```hcl
egress_policies = concat(
  local.admin_egress_all_rule,
  local.generic_egress_bigquery_read_rule,
  local.generic_egress_storage_writer_rule,
  # ... all other rules
)
```

**Step 5: The perimeter resource iterates over them with `dynamic` blocks**

```hcl
dynamic "egress_policies" {
  for_each = local.egress_policies
  content {
    title = egress_policies.value.title
    egress_from {
      identities = egress_policies.value["identities"]
    }
    egress_to {
      resources = egress_policies.value["resources"]
      dynamic "operations" {
        for_each = egress_policies.value["operations"]
        content {
          service_name = operations.key
          dynamic "method_selectors" { ... }
        }
      }
    }
  }
}
```

**Key insight:** If you set a variable to `null` (the default), no rule is generated. This means unused rules add zero overhead. You only need to populate the variables relevant to your perimeter.

---

## End-to-end workflow examples

### Example 1: Set up a new data analytics perimeter

```
You:  "I need a VPC-SC perimeter for our data analytics team with 4 projects"

Step 1 — Ask the MCP server what services to restrict:
  Tool: recommend_restricted_services(workload_type="data-analytics")
  Returns: bigquery, storage, bigquerystorage (required) + 10 recommended

Step 2 — Check if all your services are supported:
  Tool: check_service_support(service_name="bigquerydatatransfer")
  Returns: confirmed, with method selector presets

Step 3 — Generate the base perimeter Terraform:
  Tool: generate_perimeter_terraform(
    name="analytics_prod",
    policy_id="123456",
    project_numbers=["111", "222", "333", "444"],
    restricted_services=[...from step 1...],
    dry_run=True
  )
  Returns: HCL for a dry-run perimeter

Step 4 — Translate to module call using the variable patterns above

Step 5 — Run terraform plan and review
```

### Example 2: Troubleshoot a denied BigQuery query

```
You: "BigQuery query from project A to dataset in project B is being denied"

Step 1 — Check the audit logs:
  Tool: check_vpc_sc_violations(project_id="project-a", freshness="1d")
  Returns: violation entries with reason codes

Step 2 — Get troubleshooting guidance:
  Tool: troubleshoot_violation(violation_reason="RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER")
  Returns: root cause explanation + resolution steps

Step 3 — Get the right method selectors:
  Tool: get_method_selectors(service_name="bigquery", access_type="read")
  Returns: permission selectors for BQ read access

Step 4 — Get a pre-built pattern:
  Tool: get_egress_pattern(
    pattern_name="bigquery-cross-project-query",
    substitutions='{"sa_email":"composer-sa@project-a.iam.gserviceaccount.com","target_project_number":"222222"}'
  )
  Returns: complete egress rule with substituted values

Step 5 — Translate to module variable:
  generic_egress_bigquery_read = [{
    identities = ["serviceAccount:composer-sa@project-a.iam.gserviceaccount.com"]
    resources  = ["projects/222222"]
  }]
```

### Example 3: Add external access for a partner

```
You: "Partner SA needs to read our GCS bucket from outside the perimeter"

Step 1 — Validate the identity format:
  Tool: validate_identity_format(identities=["serviceAccount:partner@external.iam.gserviceaccount.com"])
  Returns: valid

Step 2 — Get the ingress pattern:
  Tool: get_ingress_pattern(
    pattern_name="storage-read-from-access-level",
    substitutions='{"policy_id":"123456","level_name":"partner_vpn"}'
  )
  Returns: ingress rule template

Step 3 — Or generate YAML for gcloud:
  Tool: generate_ingress_yaml(
    service_name="storage",
    access_type="read",
    identities=["serviceAccount:partner@external.iam.gserviceaccount.com"],
    source_project_numbers=["999888"],
    title="Partner GCS read access"
  )
  Returns: YAML file ready for gcloud --set-ingress-policies
```

---

## Limitations and known behaviour

### Dry-run egress gap

The perimeter module has a difference between enforced and dry-run egress policies. In the enforced `status` block, `egress_from` supports `sources` and `source_restriction`. In the dry-run `spec` block, these fields are omitted. This means source-restricted egress rules cannot be tested in dry-run mode.

### Method selector coverage

The MCP server includes pre-defined method selectors for 6 services: BigQuery, Cloud Storage, Vertex AI, Cloud Logging, Secret Manager, and Pub/Sub. For other services, use `{"method": "*"}` to allow all methods, or consult the [GCP documentation](https://cloud.google.com/vpc-service-controls/docs/supported-products) for specific method names.

### Supported services list

The built-in list covers 53 commonly used services. GCP regularly adds VPC-SC support for new services. If a service is not found, the `check_service_support` tool will suggest checking the latest documentation.

### gcloud authentication

The server calls whatever `gcloud` binary is on your PATH. It does not handle authentication — you must run `gcloud auth login` and set the correct project/account before using the gcloud tools. The server checks for gcloud at startup and warns if it is missing.

### Command restrictions

Only 9 gcloud subcommands and 11 gcloud flags are allowed. This is intentional — it prevents the server from executing arbitrary commands or escalating privileges. If you see `BLOCKED: Flag 'X' is not in the allowed list`, the server is working as designed. See [Security and Governance](security.md) for the full allowlist.

### Write operations require confirmation

The `update_perimeter_resources` and `update_perimeter_services` tools return a preview by default. Set `confirm=True` to execute. This prevents AI agents from accidentally modifying live infrastructure.

### Terraform generation is a starting point

Generated HCL uses the raw `google_access_context_manager_*` resource syntax. The `generate_implementation_guide` tool also produces The module calls. In this repository, use the module format rather than raw resources.

### No state awareness

The MCP server does not read your Terraform state or `.tf` files. It generates configurations based on the arguments you provide. It cannot detect conflicts with existing rules or duplicate definitions.

### Rate limiting

The `check_vpc_sc_violations` tool calls `gcloud logging read`, which is subject to Cloud Logging API quotas. For large projects with many violations, use the `limit` parameter (default 25) and narrow the `freshness` window.

### Health check

The `/health` endpoint is available on HTTP transports only (streamable-http, SSE). It is not available on stdio. Cloud Run probes use this endpoint.
