# VPC Service Controls Concepts

This document explains the core VPC Service Controls concepts and how the MCP server maps to each one. If you're new to VPC-SC, read this before the [Getting Started](getting-started.md) guide.

---

## Table of contents

- [What VPC Service Controls solve](#what-vpc-service-controls-solve)
- [Core concepts](#core-concepts)
  - [Access policy](#access-policy)
  - [Service perimeter](#service-perimeter)
  - [Restricted services](#restricted-services)
  - [Access levels](#access-levels)
  - [Ingress rules](#ingress-rules)
  - [Egress rules](#egress-rules)
  - [Bridge perimeters](#bridge-perimeters)
  - [Dry-run mode](#dry-run-mode)
  - [Method selectors](#method-selectors)
  - [Method exceptions](#method-exceptions)
- [How the concepts connect](#how-the-concepts-connect)
- [How the MCP maps to each concept](#how-the-mcp-maps-to-each-concept)
- [Common terminology quick reference](#common-terminology-quick-reference)

---

## What VPC Service Controls solve

Google Cloud IAM answers the question *"who can do what?"* — it controls identity and permissions. VPC Service Controls answer a different question: *"where can data go?"*

Even with perfect IAM configuration, data can still be exfiltrated through:

- **Stolen credentials** — an attacker with a valid service account key can read data from anywhere on the internet
- **Misconfigured permissions** — an overly permissive IAM binding lets a user copy data to a personal project
- **Malicious insiders** — a legitimate user exports data to a project outside the organisation
- **Compromised workloads** — a running VM or Cloud Function sends data to an external endpoint

VPC Service Controls create a **security boundary** (called a *perimeter*) around your Google Cloud projects and services. Requests that try to cross this boundary — reading data out or accessing resources from outside — are blocked unless you explicitly allow them.

Think of it as a firewall for Google Cloud APIs. IAM controls *who* can access resources; VPC-SC controls *from where* and *to where* data can flow.

**Where the MCP fits:** Setting up VPC-SC correctly requires understanding multiple interrelated concepts, navigating complex gcloud commands, writing Terraform configurations, and troubleshooting cryptic violation codes. The MCP server provides 40 tools that automate these tasks — scanning your project, generating configurations, explaining violations, and recommending the right services to protect.

---

## Core concepts

### Access policy

An access policy is the top-level container for all VPC-SC resources in an organisation. It holds perimeters, access levels, and authorised orgs lists.

- **One per organisation** (usually) — all perimeters live under the same policy
- **Identified by a numeric ID** (e.g., `123456789`)
- **Required before anything else** — you cannot create perimeters without a policy

**MCP tool:** `list_access_policies(organization_id)` lists all policies for your org.

### Service perimeter

A service perimeter is the core building block. It defines:

1. **Which projects** are inside the boundary (the *resources*)
2. **Which Google Cloud APIs** are restricted at the boundary (the *restricted services*)
3. **What exceptions exist** for traffic crossing the boundary (ingress/egress rules and access levels)

When a perimeter is enforced, any API call to a restricted service that violates the boundary is denied with a VPC-SC violation error.

**Key behaviours:**
- Projects inside the same perimeter can communicate freely with each other's restricted services
- Requests from outside the perimeter to restricted services inside are denied by default
- Requests from inside the perimeter to restricted services outside are denied by default
- Unrestricted services (those not in the `restricted_services` list) are unaffected

**MCP tools:**
- `list_perimeters(policy_id)` — list all perimeters
- `describe_perimeter(policy_id, perimeter_name)` — full details of one perimeter
- `generate_perimeter_terraform(...)` — generate Terraform HCL for a new perimeter
- `diagnose_project()` — scan your project and show which perimeter it belongs to

### Restricted services

The list of Google Cloud APIs that a perimeter protects. Only services in this list are subject to boundary enforcement. Services not in the list are unaffected.

**Example:** If your perimeter restricts `bigquery.googleapis.com` and `storage.googleapis.com`, then BigQuery and Cloud Storage API calls are checked against the perimeter boundary. Pub/Sub calls (if not in the list) pass through freely.

**Common mistake:** Enabling an API on a project inside a perimeter but forgetting to add it to `restricted_services`. The API works but is unprotected — data can flow in and out without VPC-SC checks.

**MCP tools:**
- `recommend_restricted_services(workload_type)` — suggests which services to restrict based on your workload (AI/ML, data analytics, web app, etc.)
- `list_supported_services()` — lists all 147 services the MCP knows support VPC-SC
- `list_supported_services_live()` — queries the live canonical list from the Access Context Manager API
- `describe_supported_service(service_name)` — gets method-level restrictions for a service from the live API
- `check_service_support(service_name)` — checks if a specific service supports VPC-SC
- `diagnose_project()` — cross-references your enabled APIs against the perimeter's restricted services, flagging `[GAP]` for unprotected APIs

### Access levels

Access levels define conditions under which requests from **outside** a perimeter are allowed in. They act as exceptions to the perimeter boundary.

**Types of conditions:**
- **IP-based** — allow requests from specific IP ranges (e.g., corporate VPN CIDR blocks)
- **Identity-based** — allow requests from specific service accounts or user groups
- **Device-based** — allow requests from devices meeting a security posture (requires Chrome Enterprise Premium)
- **Combined** — multiple conditions ANDed together (e.g., from corporate IP AND managed device)

**Important limitations:**
- Access levels only control **inbound** traffic (outside → inside). They do not control egress.
- When multiple access levels are attached to a perimeter, a request is allowed if it satisfies **any one** of them (OR logic).
- Public IP ranges only — you cannot use private RFC 1918 ranges.
- When using Cloud NAT with Private Google Access, the caller IP is redacted as `gce-internal-ip`. Use project- or identity-based conditions instead.

**MCP tools:**
- `list_access_levels(policy_id)` — list all access levels
- `describe_access_level(policy_id, level_name)` — full details of one access level
- `generate_access_level_terraform(...)` — generate Terraform HCL for an access level

### Ingress rules

Ingress rules are the fine-grained way to allow specific external requests **into** a perimeter. They are more flexible than access levels because they can specify exactly which services, methods, and resources the request can target.

**Structure:**
```
ingressFrom:
  identities: [who is making the request]
  sources: [where the request comes from — project, VPC network, or access level]

ingressTo:
  resources: [which projects/resources inside the perimeter]
  operations:
    - serviceName: [which API]
      methodSelectors: [which specific methods/permissions]
```

**When to use ingress rules:**
- A CI/CD pipeline (Cloud Build) needs to deploy into perimeter projects
- A partner's service account needs read access to specific datasets
- A monitoring service from another project needs to query logs
- Console users from the corporate network need to browse resources

**MCP tools:**
- `generate_ingress_yaml(...)` — produce YAML for `gcloud --set-ingress-policies`
- `generate_ingress_policy_terraform(...)` — produce Terraform HCL for an ingress block
- `get_ingress_pattern(pattern_name)` — retrieve a pre-built pattern (BigQuery cross-project read, Cloud Build deploy, etc.)
- `list_ingress_patterns()` — list all available patterns

### Egress rules

Egress rules allow requests from **inside** a perimeter to reach restricted services **outside** it.

**Structure:**
```
egressFrom:
  identities: [who inside the perimeter is making the request]

egressTo:
  resources: [which external projects/resources]
  operations:
    - serviceName: [which API]
      methodSelectors: [which specific methods/permissions]
```

**When to use egress rules:**
- A Composer/Airflow pipeline inside the perimeter needs to query BigQuery datasets in another project
- A Cloud Function needs to write output to a GCS bucket outside the perimeter
- Logging needs to export to a centralised BigQuery dataset in a shared project
- Vertex AI needs to write model artifacts to an external storage bucket

**MCP tools:**
- `generate_egress_yaml(...)` — produce YAML for `gcloud --set-egress-policies`
- `generate_egress_policy_terraform(...)` — produce Terraform HCL for an egress block
- `get_egress_pattern(pattern_name)` — retrieve a pre-built pattern (BigQuery cross-project query, Storage write external, etc.)
- `list_egress_patterns()` — list all available patterns

### Bridge perimeters

A bridge perimeter connects two regular perimeters so that projects in each can access each other's restricted services. It contains no restricted services or rules of its own — it simply lists projects from both sides.

**When to use bridges:**
- Two teams each have their own perimeter but need to share data
- A shared-services project needs to be accessible from multiple perimeters
- Migrating projects between perimeters incrementally

**MCP tool:** `generate_bridge_terraform(...)` — generate Terraform HCL for a bridge perimeter.

### Dry-run mode

Dry-run mode lets you test a perimeter configuration without blocking any requests. Violations are logged but not enforced.

**Why this matters:**
- VPC-SC violations can break production workloads instantly
- Dry-run lets you discover all cross-boundary traffic before enforcement
- You can iterate on ingress/egress rules until the violation log is clean
- Only then do you switch to enforced mode

**Recommended workflow:**
1. Create the perimeter in dry-run mode
2. Monitor Cloud Audit Logs for `RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER` and other violations
3. Add ingress/egress rules to address each violation
4. Once the log is clean for 7+ days, enforce the perimeter
5. Continue monitoring after enforcement

**MCP tools:**
- `generate_perimeter_terraform(dry_run=True)` — generates HCL with a `spec` block (dry-run)
- `generate_perimeter_terraform(dry_run=False)` — generates HCL with a `status` block (enforced)
- `dry_run_status(policy_id)` — shows perimeters that have pending dry-run configurations
- `check_vpc_sc_violations(project_id)` — queries audit logs for recent violations (works in both modes)
- `diagnose_project()` — includes violation scanning as part of the full diagnostic

### Method selectors

Method selectors let you restrict ingress/egress rules to specific API operations instead of allowing all operations on a service. This follows the principle of least privilege.

**Two types — and this is the most common source of confusion:**

| Type | Format | Example | Used by |
|---|---|---|---|
| `method` | RPC-style | `google.storage.objects.get` | Cloud Storage, Vertex AI, Pub/Sub, Cloud Run |
| `permission` | IAM-style | `bigquery.tables.getData` | BigQuery, Data Catalog |

**Critical rule:** If a service uses `permission` selectors and you specify `method` selectors (or vice versa), the rule will silently fail to match. The request will be denied and the violation log won't clearly explain why.

**MCP tools:**
- `get_method_selectors(service_name, access_type)` returns the correct selector type and format for each service
- `explain_method_selector_types()` provides a full reference of which services use which type, with examples of common mistakes

### Method exceptions

Some API methods are **not controllable** by VPC Service Controls. These methods can cross perimeter boundaries regardless of your rules. This means:

- You cannot use VPC-SC to block these specific operations
- You need alternative security controls (IAM, API restrictions) for these methods
- They exist across services like Cloud Build, GKE, IAM, and others

**Why this matters for planning:** When designing your perimeter, review the [method exceptions list](https://docs.cloud.google.com/vpc-service-controls/docs/method-exceptions) for your services. If a critical data path uses an excepted method, you need IAM and network controls instead of (or in addition to) VPC-SC.

---

## How the concepts connect

```
Organisation
  └── Access Policy (1 per org)
        ├── Access Level: "corporate_network" (IP range condition)
        ├── Access Level: "trusted_devices" (device policy condition)
        │
        ├── Service Perimeter: "team_a_prod" (enforced)
        │     ├── Resources: [projects/111, projects/222]
        │     ├── Restricted services: [bigquery, storage, compute, ...]
        │     ├── Access levels: [corporate_network]
        │     ├── Ingress rules:
        │     │     └── Cloud Build SA → all services (CI/CD deploy)
        │     └── Egress rules:
        │           └── Composer SA → BigQuery in shared project (analytics)
        │
        ├── Service Perimeter: "team_b_prod" (dry-run)
        │     ├── Resources: [projects/333, projects/444]
        │     ├── Restricted services: [bigquery, storage, aiplatform, ...]
        │     └── ... (testing rules before enforcement)
        │
        └── Bridge Perimeter: "team_a_to_team_b"
              └── Resources: [projects/222, projects/333]
```

---

## How the MCP maps to each concept

| VPC-SC concept | What you need to do | MCP tools that help |
|---|---|---|
| **Discover your current state** | Find your access policy, perimeters, access levels, violations | `list_access_policies`, `list_perimeters`, `describe_perimeter`, `list_access_levels`, `check_vpc_sc_violations`, `diagnose_project` |
| **Choose services to restrict** | Decide which APIs to protect based on your workload | `recommend_restricted_services`, `list_supported_services`, `check_service_support` |
| **Find protection gaps** | Identify enabled APIs not covered by the perimeter | `diagnose_project` (protection gap analysis) |
| **Create a perimeter** | Generate Terraform or gcloud configs for a new perimeter | `generate_perimeter_terraform`, `generate_full_perimeter_terraform` |
| **Create access levels** | Generate Terraform for IP/identity/device-based access levels | `generate_access_level_terraform` |
| **Add ingress rules** | Allow specific external access into the perimeter | `generate_ingress_yaml`, `generate_ingress_policy_terraform`, `get_ingress_pattern` |
| **Add egress rules** | Allow specific internal access out of the perimeter | `generate_egress_yaml`, `generate_egress_policy_terraform`, `get_egress_pattern` |
| **Create bridges** | Connect two perimeters for cross-team data sharing | `generate_bridge_terraform` |
| **Test with dry-run** | Deploy perimeter without enforcement | `generate_perimeter_terraform(dry_run=True)`, `dry_run_status`, `check_vpc_sc_violations` |
| **Troubleshoot violations** | Understand why a request was denied | `troubleshoot_violation`, `check_vpc_sc_violations` |
| **Get method selectors right** | Use the correct method/permission format per service | `get_method_selectors`, `explain_method_selector_types` |
| **Validate before applying** | Check generated Terraform is syntactically valid | `validate_terraform` |
| **Check org policies** | Ensure org-wide security policies are compliant | `diagnose_org_policies`, `generate_org_policy_terraform` |
| **Plan an implementation** | Get a phased Terraform guide for your project | `generate_implementation_guide` |

---

## Common terminology quick reference

| Term | Meaning |
|---|---|
| **Perimeter** | A security boundary around GCP projects and services |
| **Restricted service** | A GCP API protected by a perimeter |
| **Access level** | A condition (IP, identity, device) that allows external access into a perimeter |
| **Ingress rule** | Fine-grained rule allowing specific external requests into a perimeter |
| **Egress rule** | Fine-grained rule allowing specific internal requests out of a perimeter |
| **Bridge perimeter** | A connector between two regular perimeters |
| **Dry-run mode** | A testing mode that logs violations without blocking requests |
| **Enforced mode** | Production mode where violations are blocked |
| **Access policy** | The org-level container for all VPC-SC resources |
| **Method selector** | A filter specifying which API methods are allowed in a rule |
| **Permission selector** | A filter specifying which IAM permissions are allowed in a rule (used by BigQuery, Data Catalog) |
| **VPC-SC violation** | An API call that was denied (enforced) or would be denied (dry-run) by a perimeter |
| **Protection gap** | An enabled API that is not in the perimeter's restricted services list |
| **`spec` block** | The Terraform block for dry-run configuration |
| **`status` block** | The Terraform block for enforced configuration |
| **`projects/NUMBER`** | How projects are referenced in perimeters — always use project **numbers**, not IDs |
| **`*.googleapis.com`** | Service name format — e.g., `bigquery.googleapis.com` |

---

## Next steps

- [Getting Started](getting-started.md) — install and run your first diagnostic
- [Use Cases](use-cases.md) — practical scenarios showing the MCP in action
- [MCP Server Guide](mcp-server-guide.md) — full reference for all 40 tools
- [Security](security.md) — how the MCP server protects your environment
