# Use Cases

Practical scenarios showing how the VPC-SC MCP server helps with common VPC Service Controls tasks. Each scenario walks through the problem, the MCP tools involved, and the expected output.

For background on the concepts referenced here, see [VPC-SC Concepts](concepts.md).

---

## Table of contents

- [Scenario 1: Assess a project's VPC-SC readiness](#scenario-1-assess-a-projects-vpc-sc-readiness)
- [Scenario 2: Set up a new perimeter for a data analytics team](#scenario-2-set-up-a-new-perimeter-for-a-data-analytics-team)
- [Scenario 3: Troubleshoot a denied BigQuery query](#scenario-3-troubleshoot-a-denied-bigquery-query)
- [Scenario 4: Allow a CI/CD pipeline into the perimeter](#scenario-4-allow-a-cicd-pipeline-into-the-perimeter)
- [Scenario 5: Grant a partner read access to Cloud Storage](#scenario-5-grant-a-partner-read-access-to-cloud-storage)
- [Scenario 6: Audit org policy compliance before a security review](#scenario-6-audit-org-policy-compliance-before-a-security-review)
- [Scenario 7: Migrate a project into an existing perimeter](#scenario-7-migrate-a-project-into-an-existing-perimeter)
- [Scenario 8: Enable cross-perimeter data sharing with a bridge](#scenario-8-enable-cross-perimeter-data-sharing-with-a-bridge)

---

## Scenario 1: Assess a project's VPC-SC readiness

**Situation:** You've inherited a GCP project and need to understand its current VPC-SC posture — which APIs are enabled, whether a perimeter exists, and what's protected.

**Ask the MCP:**

> Run a diagnostic on my project

**What happens:**

The `diagnose_project` tool runs 10 automated steps:

1. Resolves your active project and organisation
2. Scans all enabled APIs against 217 known VPC-SC supported services
3. Checks whether the project belongs to any perimeter
4. Lists existing access levels, service accounts, and VPC networks
5. Queries Cloud Audit Logs for recent VPC-SC violations
6. Cross-references enabled APIs against the perimeter's restricted services

**Example output:**

```
DIAGNOSTIC SUMMARY
  Project:          analytics-prod-42
  Organisation:     123456789 (example.com)
  Access policy:    987654321
  Perimeter:        data_team_prod (contains this project)

  APIs enabled:     23 VPC-SC supported
  APIs protected:   20 (in perimeter's restricted_services)
  APIs unprotected: 3  <-- ACTION NEEDED

  PROTECTED (20 APIs):
    [PROTECTED] bigquery.googleapis.com (BigQuery)
    [PROTECTED] storage.googleapis.com (Cloud Storage)
    ...

  UNPROTECTED (3 APIs — enabled but NOT in perimeter):
    [GAP] dataplex.googleapis.com (Dataplex)
    [GAP] notebooks.googleapis.com (Vertex AI Workbench)
    [GAP] documentai.googleapis.com (Document AI)

  ACTION: Add these 3 service(s) to the perimeter's restricted_services.
  Use dry-run mode first:
    gcloud access-context-manager perimeters dry-run update data_team_prod \
      --policy=987654321 \
      --add-restricted-services=dataplex.googleapis.com,notebooks.googleapis.com,documentai.googleapis.com

  Recent violations: 2 in last 7 days
  STATUS: PARTIALLY PROTECTED — 3 gap(s) to close
```

**What to do next:**
- Close the protection gaps by adding the missing services to the perimeter
- Investigate the 2 recent violations
- Ask for an implementation guide: *"Generate an implementation guide for this project"*

---

## Scenario 2: Set up a new perimeter for a data analytics team

**Situation:** Your team has 4 GCP projects running BigQuery, Dataflow, and Cloud Storage workloads. You need to create a VPC-SC perimeter to protect them.

**Step 1 — Get service recommendations:**

> What services should I restrict for a data analytics workload?

The `recommend_restricted_services` tool returns a tailored list:

```
Required: bigquery.googleapis.com, storage.googleapis.com, bigquerystorage.googleapis.com
Recommended: dataflow.googleapis.com, dataproc.googleapis.com, composer.googleapis.com,
             datacatalog.googleapis.com, dataplex.googleapis.com, dlp.googleapis.com,
             cloudkms.googleapis.com, pubsub.googleapis.com, logging.googleapis.com
```

**Step 2 — Generate the Terraform:**

> Generate Terraform for a VPC-SC perimeter called "analytics_prod" with policy ID 987654321,
> projects 111111, 222222, 333333, 444444, and the recommended services in dry-run mode

The `generate_perimeter_terraform` tool produces ready-to-use HCL with a `spec` block (dry-run).

**Step 3 — Validate the Terraform:**

> Validate that Terraform code

The `validate_terraform` tool writes the HCL to a temp directory, runs `terraform init`, `validate`, and `fmt`, and reports any syntax or formatting issues.

**Step 4 — Review the implementation guide:**

> Generate a full implementation guide for a data-analytics workload

The `generate_implementation_guide` tool produces a 7-phase plan:
1. Prerequisites and gcloud commands
2. Access level Terraform
3. Perimeter in dry-run mode
4. Monitoring commands
5. Ingress/egress rules (both raw HCL and module variable format)
6. Enforcement commands
7. Ongoing monitoring

**What to do next:**
- Apply the Terraform in dry-run mode
- Monitor violations for 7+ days using `check_vpc_sc_violations`
- Add ingress/egress rules to address any denied requests
- Enforce once the violation log is clean

---

## Scenario 3: Troubleshoot a denied BigQuery query

**Situation:** A Composer (Airflow) pipeline in project A is querying a BigQuery dataset in project B. The query started failing with a VPC-SC denial after the perimeter was enforced.

**Step 1 — Check the violation logs:**

> Check VPC-SC violations for project analytics-pipeline-prod in the last 24 hours

The `check_vpc_sc_violations` tool queries Cloud Audit Logs and returns:

```
Violation #1:
  Time: 2025-01-15T10:23:45Z
  Service: bigquery.googleapis.com
  Method: google.cloud.bigquery.v2.JobService.InsertJob
  Reason: RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER
  Caller: serviceAccount:composer-sa@analytics-pipeline-prod.iam.gserviceaccount.com
  Resource: projects/shared-data-prod
```

**Step 2 — Understand the violation:**

> Troubleshoot RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER

The `troubleshoot_violation` tool explains:

```
Root cause: The request targets a resource in a different project that is either:
  (a) in a different perimeter, or
  (b) not in any perimeter

Resolution:
  1. If both projects should be in the same perimeter — add the target project
  2. If they must be in separate perimeters — create egress and/or ingress rules
  3. If they must be in separate perimeters — consider a bridge perimeter

Common pitfall: BigQuery uses PERMISSION selectors (not METHOD selectors).
  Correct: "permission": "bigquery.tables.getData"
  Wrong:   "method": "bigquery.tables.getData"  ← will silently fail
```

**Step 3 — Get the correct method selectors:**

> Get method selectors for BigQuery read access

The `get_method_selectors` tool returns the exact permissions needed:

```
Service: bigquery.googleapis.com
Selector type: permission (not method!)
Selectors:
  - bigquery.datasets.get
  - bigquery.tables.getData
  - bigquery.tables.list
  - bigquery.jobs.create
```

**Step 4 — Get a ready-made egress rule:**

> Get the bigquery-cross-project-query egress pattern for composer-sa@analytics-pipeline-prod.iam.gserviceaccount.com targeting project 555666777

The `get_egress_pattern` tool returns a complete egress rule with the substituted values, ready to apply.

**Step 5 — Or generate YAML for gcloud:**

> Generate an egress YAML for BigQuery read access from the Composer SA to project 555666777

The `generate_egress_yaml` tool produces a YAML file with a comment showing the exact `gcloud` command to apply it.

---

## Scenario 4: Allow a CI/CD pipeline into the perimeter

**Situation:** Cloud Build needs to deploy container images and update Cloud Run services inside the perimeter. Currently, deployments are failing with VPC-SC denials.

**Step 1 — Get the Cloud Build deploy pattern:**

> Get the cloud-build-deploy ingress pattern

The `get_ingress_pattern` tool returns a pre-built ingress rule that allows Cloud Build to deploy into the perimeter:

```yaml
ingressFrom:
  identities:
    - serviceAccount:{cloudbuild_sa_email}
  sources:
    - resource: projects/{source_project_number}
ingressTo:
  resources: ["*"]
  operations:
    - serviceName: "*"
      methodSelectors:
        - method: "*"
```

**Step 2 — Substitute your values:**

> Get the cloud-build-deploy ingress pattern with SA 123456@cloudbuild.gserviceaccount.com from project 789012

Returns the same pattern with your actual values filled in.

**Step 3 — Generate Terraform:**

> Generate ingress policy Terraform for Cloud Build deploying into the perimeter

The `generate_ingress_policy_terraform` tool produces an HCL block you can add to your perimeter configuration, or translate to the module variable `ingress_terraform_cloud_build`.

**Module variable translation:**

```hcl
ingress_terraform_cloud_build = [
  {
    title      = "CI/CD Cloud Build deploy"
    identities = ["serviceAccount:123456@cloudbuild.gserviceaccount.com"]
    resources  = ["*"]
  },
]
```

---

## Scenario 5: Grant a partner read access to Cloud Storage

**Situation:** A partner organisation's service account needs to read objects from a GCS bucket inside your perimeter. You need to allow this access without opening the perimeter too broadly.

**Step 1 — Validate the identity format:**

> Validate identity format for serviceAccount:partner-reader@external-org.iam.gserviceaccount.com

The `validate_identity_format` tool confirms the format is valid (`serviceAccount:` prefix).

**Step 2 — Get the Storage read pattern:**

> Get the storage-read-from-access-level ingress pattern

This returns a template that uses an access level for source filtering. If you don't have an access level for the partner, you can use a project-based source instead.

**Step 3 — Generate the ingress YAML:**

> Generate an ingress YAML for storage read access from serviceAccount:partner-reader@external-org.iam.gserviceaccount.com with source project 999888777

The `generate_ingress_yaml` tool produces:

```yaml
# Apply with:
# gcloud access-context-manager perimeters update my_perimeter \
#   --policy=123456 \
#   --set-ingress-policies=ingress-partner-storage-read.yaml

- ingressFrom:
    identities:
      - serviceAccount:partner-reader@external-org.iam.gserviceaccount.com
    sources:
      - resource: projects/999888777
  ingressTo:
    resources:
      - "*"
    operations:
      - serviceName: storage.googleapis.com
        methodSelectors:
          - method: google.storage.objects.get
          - method: google.storage.objects.list
          - method: google.storage.buckets.get
```

**Key detail:** Cloud Storage uses `method` selectors (RPC-style), not `permission` selectors. The MCP generates the correct format automatically.

---

## Scenario 6: Audit org policy compliance before a security review

**Situation:** Your security team has an upcoming compliance review. You need to check all org policies against a baseline and fix any gaps.

**Step 1 — Run the org policy diagnostic:**

> Check org policy compliance on my project

The `diagnose_org_policies` tool checks 31 policies across 11 categories:

```
--- COMPLIANT (18) ---
  [COMPLIANT] compute.disableSerialPortAccess
  [COMPLIANT] iam.disableAuditLoggingExemption
  ...

--- NON-COMPLIANT (4) ---  <-- ACTION NEEDED
  [NON-COMPLIANT] storage.publicAccessPrevention  (risk: HIGH)
    Why: Public buckets are the #1 cause of data leaks in GCP.
  [NON-COMPLIANT] iam.automaticIamGrantsForDefaultServiceAccounts  (risk: HIGH)
    Why: Default SAs get Editor role automatically — far too permissive.
  ...

--- NOT SET (9) ---  <-- ACTION NEEDED
  [NOT SET] compute.requireShieldedVm  (risk: MEDIUM)
  [NOT SET] run.allowedIngress  (risk: HIGH)
  ...

ORG POLICY COMPLIANCE SUMMARY
  Policies checked: 31
  Compliant:      18
  Non-compliant:  4   <-- ACTION NEEDED
  Not set:        9   <-- ACTION NEEDED
  STATUS: NON-COMPLIANT — 8 HIGH risk issue(s)
```

**Step 2 — Generate fix Terraform:**

> Generate Terraform to enforce all recommended org policies at the project level

The `generate_org_policy_terraform` tool produces HCL for all 31 policies, grouped by category, with risk labels and rationale as comments. Each policy includes the constraint, enforcement setting, and a description of what it does.

**Step 3 — Validate and plan:**

> Validate that Terraform code

Apply the validated Terraform to bring the project into compliance.

---

## Scenario 7: Migrate a project into an existing perimeter

**Situation:** A new project needs to be added to an existing perimeter. You need to understand what will break and how to prepare.

**Step 1 — Run diagnostics on the new project:**

> Run a diagnostic on project new-team-project-prod

The diagnostic reveals which APIs are enabled on the project and whether there are any VPC-SC violations.

**Step 2 — Understand current cross-project traffic:**

> Check VPC-SC violations for project new-team-project-prod in the last 30 days

This shows what traffic patterns exist, which helps you anticipate which ingress/egress rules you'll need after adding the project to the perimeter.

**Step 3 — Use the migration prompt:**

> Plan a migration to VPC-SC for projects new-team-project-prod, existing-team-project-prod

The `migrate_to_vpcsc` prompt guides a phased migration conversation, helping you identify:
- Which services the new project uses
- What cross-project dependencies exist
- Which rules to create
- The recommended migration sequence

**Step 4 — Add the project in dry-run mode first:**

> Preview adding projects/NEW_PROJECT_NUMBER to perimeter data_team_prod

The `update_perimeter_resources` tool (without `confirm=True`) returns a preview showing what would change.

**Step 5 — Monitor and then enforce:**

Use `check_vpc_sc_violations` daily to identify any traffic that would be blocked. Create ingress/egress rules for legitimate traffic, then switch from dry-run to enforced.

---

## Scenario 8: Enable cross-perimeter data sharing with a bridge

**Situation:** Team A and Team B each have their own perimeters. A project in Team A needs to share BigQuery datasets with a project in Team B.

**Option A — Bridge perimeter (bidirectional access):**

> Generate a bridge perimeter between projects/111111 and projects/333333

The `generate_bridge_terraform` tool produces:

```hcl
resource "google_access_context_manager_service_perimeter" "bridge_team_a_team_b" {
  parent         = "accessPolicies/987654321"
  name           = "accessPolicies/987654321/servicePerimeters/bridge_team_a_team_b"
  title          = "bridge_team_a_team_b"
  perimeter_type = "PERIMETER_TYPE_BRIDGE"

  status {
    resources = [
      "projects/111111",
      "projects/333333",
    ]
  }
}
```

**Option B — Egress + ingress rules (unidirectional, more granular):**

If you only need one-way access (e.g., Team A reads Team B's data), use egress rules on Team A's perimeter and ingress rules on Team B's perimeter. This gives you control over exactly which services, methods, and identities are allowed.

> Generate an egress rule for Team A's SA to read BigQuery in Team B's project

> Generate an ingress rule allowing Team A's SA to read BigQuery in Team B's perimeter

---

## Choosing the right approach

| Situation | Best approach | MCP tools |
|---|---|---|
| Assess current state | Full project diagnostic | `diagnose_project` |
| New perimeter from scratch | Service recommendations + Terraform generation + implementation guide | `recommend_restricted_services`, `generate_perimeter_terraform`, `generate_implementation_guide` |
| Something broke after enforcement | Violation logs + troubleshooting + rule generation | `check_vpc_sc_violations`, `troubleshoot_violation`, `get_method_selectors`, `get_*_pattern` |
| CI/CD access | Pre-built Cloud Build ingress pattern | `get_ingress_pattern("cloud-build-deploy")` |
| External partner access | Identity validation + ingress YAML/Terraform | `validate_identity_format`, `generate_ingress_yaml` |
| Security compliance audit | Org policy diagnostic + Terraform remediation | `diagnose_org_policies`, `generate_org_policy_terraform` |
| Add project to perimeter | Dry-run preview + violation monitoring | `update_perimeter_resources`, `check_vpc_sc_violations` |
| Cross-perimeter sharing | Bridge perimeter or targeted egress/ingress rules | `generate_bridge_terraform`, `generate_egress_yaml`, `generate_ingress_yaml` |

---

## Next steps

- [Getting Started](getting-started.md) — install and connect the MCP server
- [Concepts](concepts.md) — understand VPC-SC terminology and how the MCP maps to it
- [MCP Server Guide](mcp-server-guide.md) — full reference for all 40 tools, 5 resources, and 3 prompts
