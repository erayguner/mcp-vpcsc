"""Organisation Policy baseline — expected constraints, enforcement, risk, and rationale."""

EXPECTED_POLICIES: dict[str, dict] = {
    # Compute
    "compute.disableSerialPortAccess": {
        "category": "compute",
        "description": "Disable serial port access on VMs",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Serial port access can bypass OS-level security controls and expose sensitive data.",
    },
    "compute.skipDefaultNetworkCreation": {
        "category": "compute",
        "description": "Skip default network creation in new projects",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Default networks have permissive firewall rules. Projects should use custom VPCs.",
    },
    "compute.vmExternalIpAccess": {
        "category": "compute",
        "description": "Restrict VM external IP access",
        "expected": "restricted",
        "risk": "HIGH",
        "rationale": "VMs with external IPs are directly exposed to the internet.",
    },
    "compute.storageResourceUseRestrictions": {
        "category": "compute",
        "description": "Restrict storage resource usage to the organisation",
        "expected": "restricted",
        "risk": "MEDIUM",
        "rationale": "Prevents using disk images or snapshots from outside the organisation.",
    },
    "compute.requireShieldedVm": {
        "category": "compute",
        "description": "Require Shielded VMs",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Shielded VMs protect against rootkits and bootkits.",
    },
    # IAM
    "iam.disableAuditLoggingExemption": {
        "category": "iam",
        "description": "Disable audit logging exemptions",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "All actions should be audited. Exemptions hide activity.",
    },
    "iam.automaticIamGrantsForDefaultServiceAccounts": {
        "category": "iam",
        "description": "Disable automatic IAM grants for default SAs",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Default SAs get Editor role automatically — far too permissive.",
    },
    "iam.managed.disableServiceAccountKeyCreation": {
        "category": "iam",
        "description": "Disable service account key creation",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "SA keys are long-lived credentials that can leak. Use Workload Identity instead.",
    },
    "iam.managed.disableServiceAccountKeyUpload": {
        "category": "iam",
        "description": "Disable service account key upload",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Uploaded keys bypass Cloud IAM key rotation controls.",
    },
    "iam.managed.allowedPolicyMembers": {
        "category": "iam",
        "description": "Restrict IAM policy members to allowed domains",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Prevents granting roles to external identities.",
    },
    # Storage
    "storage.publicAccessPrevention": {
        "category": "storage",
        "description": "Prevent public access to Cloud Storage buckets",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Public buckets are the #1 cause of data leaks in GCP.",
    },
    "storage.uniformBucketLevelAccess": {
        "category": "storage",
        "description": "Enforce uniform bucket-level access",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Uniform access simplifies IAM and prevents ACL-based misconfigurations.",
    },
    # GCP-wide
    "gcp.resourceLocations": {
        "category": "gcp",
        "description": "Restrict resource locations to allowed regions",
        "expected": "restricted",
        "risk": "HIGH",
        "rationale": "Data sovereignty — resources must stay in approved regions.",
    },
    "gcp.detailedAuditLoggingMode": {
        "category": "gcp",
        "description": "Enable detailed audit logging",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Detailed logs are required for forensic analysis.",
    },
    "essentialcontacts.managed.allowedContactDomains": {
        "category": "gcp",
        "description": "Restrict essential contacts to organisational domains",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Security notifications must go to internal addresses.",
    },
    # IAM — Workload Identity & key response
    "iam.serviceAccountKeyExposureResponse": {
        "category": "iam",
        "description": "Auto-disable exposed SA keys",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Automatically disables SA keys detected in public repos or logs.",
    },
    "iam.workloadIdentityPoolProviders": {
        "category": "iam",
        "description": "Restrict Workload Identity Federation providers",
        "expected": "restricted",
        "risk": "HIGH",
        "rationale": "Only approved IdPs (GitHub Actions, Azure, AWS) should be federated.",
    },
    # Cloud Run
    "run.allowedIngress": {
        "category": "cloud-run",
        "description": "Restrict Cloud Run ingress to internal only",
        "expected": "restricted",
        "risk": "HIGH",
        "rationale": "Public Cloud Run services bypass VPC-SC perimeters.",
    },
    "run.allowedVPCEgress": {
        "category": "cloud-run",
        "description": "Control Cloud Run VPC egress routing",
        "expected": "restricted",
        "risk": "MEDIUM",
        "rationale": "All egress should route through VPC for network controls.",
    },
    # GKE
    "container.restrictPublicClusters": {
        "category": "gke",
        "description": "Restrict public GKE clusters",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Public cluster endpoints expose the Kubernetes API to the internet.",
    },
    # GKE — custom constraints
    "custom.gkeClusterUMaintenanceWindowsEnforced": {
        "category": "gke-custom",
        "description": "Require GKE cluster maintenance windows",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Maintenance windows prevent disruptive upgrades during business hours.",
    },
    "custom.gkeClusterUpdateReleaseChannelEnforced": {
        "category": "gke-custom",
        "description": "Require GKE cluster release channel subscription",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Release channels ensure clusters receive security patches.",
    },
    "custom.nodePoolAutoUpdateEnforce": {
        "category": "gke-custom",
        "description": "Require GKE node pool auto-upgrade",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Node pools without auto-upgrade miss critical security patches.",
    },
    # Cloud SQL
    "sql.restrictPublicIp": {
        "category": "cloudsql",
        "description": "Restrict public IP on Cloud SQL instances",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Databases with public IPs are directly attackable.",
    },
    # Cloud SQL — custom
    "custom.csqlPassPol": {
        "category": "cloudsql-custom",
        "description": "Enforce Cloud SQL password policy (min 16 chars, complexity, no username)",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Weak database passwords are a common attack vector.",
    },
    # Firestore
    "firestore.requireP4SAforImportExport": {
        "category": "firestore",
        "description": "Require P4SA for Firestore import/export",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "P4SA ensures Firestore operations use the project's own service account.",
    },
    # SCC — custom constraints
    "custom.sccContainerThreatDetectionEnablement": {
        "category": "scc",
        "description": "Require SCC Container Threat Detection enabled",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Detects runtime threats in GKE containers.",
    },
    "custom.sccEventThreatDetectionEnablement": {
        "category": "scc",
        "description": "Require SCC Event Threat Detection enabled",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Detects threats from audit log analysis (crypto mining, data exfiltration).",
    },
    "custom.sccSecurityHealthAnalyticsEnablement": {
        "category": "scc",
        "description": "Require SCC Security Health Analytics enabled",
        "expected": "enforced",
        "risk": "HIGH",
        "rationale": "Detects misconfigurations like public buckets, open firewall rules.",
    },
    "custom.sccVirtualMachineThreatDetectionEnablement": {
        "category": "scc",
        "description": "Require SCC VM Threat Detection enabled",
        "expected": "enforced",
        "risk": "MEDIUM",
        "rationale": "Detects crypto mining and other threats on VMs.",
    },
    # Service usage (dry-run)
    "gcp.restrictServiceUsage": {
        "category": "gcp",
        "description": "Restrict which GCP services can be used (dry-run recommended first)",
        "expected": "restricted",
        "risk": "MEDIUM",
        "rationale": "Limits attack surface by whitelisting only approved GCP services.",
    },
}
