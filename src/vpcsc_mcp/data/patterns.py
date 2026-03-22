"""Common VPC-SC ingress/egress patterns and best practices."""

COMMON_INGRESS_PATTERNS: dict[str, dict] = {
    "bigquery-cross-project-read": {
        "title": "Allow external project to read BigQuery datasets",
        "description": "Enables a service account from an outside project to run read queries against datasets inside the perimeter.",
        "template": {
            "ingressFrom": {
                "identities": ["serviceAccount:{sa_email}"],
                "sources": [{"resource": "projects/{source_project_number}"}],
            },
            "ingressTo": {
                "resources": ["*"],
                "operations": [
                    {
                        "serviceName": "bigquery.googleapis.com",
                        "methodSelectors": [
                            {"permission": "bigquery.datasets.get"},
                            {"permission": "bigquery.tables.getData"},
                            {"permission": "bigquery.tables.list"},
                            {"permission": "bigquery.jobs.create"},
                        ],
                    }
                ],
            },
        },
    },
    "storage-read-from-access-level": {
        "title": "Allow corporate network to read Cloud Storage",
        "description": "Enables users on the corporate network (via access level) to read GCS objects inside the perimeter.",
        "template": {
            "ingressFrom": {
                "identityType": "ANY_IDENTITY",
                "sources": [{"accessLevel": "accessPolicies/{policy_id}/accessLevels/{level_name}"}],
            },
            "ingressTo": {
                "resources": ["*"],
                "operations": [
                    {
                        "serviceName": "storage.googleapis.com",
                        "methodSelectors": [
                            {"method": "google.storage.objects.get"},
                            {"method": "google.storage.objects.list"},
                            {"method": "google.storage.buckets.get"},
                        ],
                    }
                ],
            },
        },
    },
    "vertex-ai-prediction": {
        "title": "Allow external service to call Vertex AI predictions",
        "description": "Enables a service account from outside the perimeter to invoke Vertex AI prediction endpoints.",
        "template": {
            "ingressFrom": {
                "identities": ["serviceAccount:{sa_email}"],
                "sources": [{"resource": "projects/{source_project_number}"}],
            },
            "ingressTo": {
                "resources": ["*"],
                "operations": [
                    {
                        "serviceName": "aiplatform.googleapis.com",
                        "methodSelectors": [
                            {"method": "google.cloud.aiplatform.v1.PredictionService.Predict"},
                            {"method": "google.cloud.aiplatform.v1.PredictionService.RawPredict"},
                        ],
                    }
                ],
            },
        },
    },
    "cloud-build-deploy": {
        "title": "Allow Cloud Build to deploy into perimeter",
        "description": "Enables Cloud Build service agent from an external project to deploy resources inside the perimeter.",
        "template": {
            "ingressFrom": {
                "identities": [
                    "serviceAccount:{project_number}@cloudbuild.gserviceaccount.com",
                    "serviceAccount:service-{project_number}@gcp-sa-cloudbuild.iam.gserviceaccount.com",
                ],
                "sources": [{"resource": "projects/{source_project_number}"}],
            },
            "ingressTo": {
                "resources": ["*"],
                "operations": [
                    {"serviceName": "storage.googleapis.com", "methodSelectors": [{"method": "*"}]},
                    {"serviceName": "cloudbuild.googleapis.com", "methodSelectors": [{"method": "*"}]},
                ],
            },
        },
    },
    "devops-console-access": {
        "title": "Allow DevOps team console access via access level",
        "description": "Enables DevOps team members on the corporate network to access resources in the perimeter via console/API.",
        "template": {
            "ingressFrom": {
                "identities": ["group:{devops_group_email}"],
                "sources": [{"accessLevel": "accessPolicies/{policy_id}/accessLevels/{level_name}"}],
            },
            "ingressTo": {
                "resources": ["*"],
                "operations": [
                    {"serviceName": "bigquery.googleapis.com", "methodSelectors": [{"method": "*"}]},
                    {"serviceName": "storage.googleapis.com", "methodSelectors": [{"method": "*"}]},
                    {"serviceName": "logging.googleapis.com", "methodSelectors": [{"method": "*"}]},
                ],
            },
        },
    },
}

COMMON_EGRESS_PATTERNS: dict[str, dict] = {
    "bigquery-cross-project-query": {
        "title": "Allow BigQuery jobs to query external datasets",
        "description": "Enables service accounts inside the perimeter to run BigQuery jobs that read from external projects.",
        "template": {
            "egressFrom": {
                "identities": ["serviceAccount:{sa_email}"],
            },
            "egressTo": {
                "resources": ["projects/{target_project_number}"],
                "operations": [
                    {
                        "serviceName": "bigquery.googleapis.com",
                        "methodSelectors": [
                            {"permission": "bigquery.datasets.get"},
                            {"permission": "bigquery.tables.getData"},
                            {"permission": "bigquery.jobs.create"},
                        ],
                    }
                ],
            },
        },
    },
    "storage-write-external": {
        "title": "Allow writing to external Cloud Storage bucket",
        "description": "Enables a service account inside the perimeter to write objects to a GCS bucket in an external project.",
        "template": {
            "egressFrom": {
                "identities": ["serviceAccount:{sa_email}"],
            },
            "egressTo": {
                "resources": ["projects/{target_project_number}"],
                "operations": [
                    {
                        "serviceName": "storage.googleapis.com",
                        "methodSelectors": [
                            {"method": "google.storage.objects.create"},
                            {"method": "google.storage.objects.delete"},
                            {"method": "google.storage.buckets.testIamPermissions"},
                        ],
                    }
                ],
            },
        },
    },
    "cloud-functions-deploy": {
        "title": "Allow Cloud Functions deployment to external storage",
        "description": "Enables Cloud Functions service agent to store function source in external GCS during deployment.",
        "template": {
            "egressFrom": {
                "identities": [
                    "serviceAccount:service-{project_number}@gcf-admin-robot.iam.gserviceaccount.com",
                ],
            },
            "egressTo": {
                "resources": ["projects/{target_project_number}"],
                "operations": [
                    {"serviceName": "storage.googleapis.com", "methodSelectors": [{"method": "*"}]},
                    {"serviceName": "cloudfunctions.googleapis.com", "methodSelectors": [{"method": "*"}]},
                ],
            },
        },
    },
    "vertex-ai-training-output": {
        "title": "Allow Vertex AI to write model artifacts externally",
        "description": "Enables Vertex AI to write trained model artifacts to a GCS bucket outside the perimeter.",
        "template": {
            "egressFrom": {
                "identities": [
                    "serviceAccount:service-{project_number}@gcp-sa-aiplatform.iam.gserviceaccount.com",
                ],
            },
            "egressTo": {
                "resources": ["projects/{target_project_number}"],
                "operations": [
                    {
                        "serviceName": "storage.googleapis.com",
                        "methodSelectors": [
                            {"method": "google.storage.objects.create"},
                            {"method": "google.storage.objects.get"},
                        ],
                    },
                    {
                        "serviceName": "aiplatform.googleapis.com",
                        "methodSelectors": [{"method": "*"}],
                    },
                ],
            },
        },
    },
    "logging-export": {
        "title": "Allow log sink to export to external project",
        "description": "Enables the logging service agent to export logs to a BigQuery dataset or GCS bucket in an external project.",
        "template": {
            "egressFrom": {
                "identities": [
                    "serviceAccount:service-{project_number}@gcp-sa-logging.iam.gserviceaccount.com",
                ],
            },
            "egressTo": {
                "resources": ["projects/{target_project_number}"],
                "operations": [
                    {
                        "serviceName": "bigquery.googleapis.com",
                        "methodSelectors": [
                            {"permission": "bigquery.datasets.get"},
                            {"permission": "bigquery.tables.updateData"},
                        ],
                    },
                    {
                        "serviceName": "storage.googleapis.com",
                        "methodSelectors": [
                            {"method": "google.storage.objects.create"},
                        ],
                    },
                ],
            },
        },
    },
}

TROUBLESHOOTING_GUIDE: dict[str, dict] = {
    "RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER": {
        "meaning": "The API client and target resource are in different perimeters with no bridge or ingress/egress rules",
        "common_causes": [
            "Cross-project BigQuery query where projects are in different perimeters",
            "Cloud Function accessing GCS bucket in another perimeter",
            "Service agent from one project accessing resources in another",
        ],
        "resolution_steps": [
            "1. Identify the source and target projects from the audit log",
            "2. Check if both projects should be in the same perimeter",
            "3. If they should stay in different perimeters, create ingress rules on the target perimeter "
            "and egress rules on the source perimeter",
            "4. Alternatively, create a bridge perimeter between the two",
            "5. Test with dry-run mode before enforcing",
        ],
    },
    "NO_MATCHING_ACCESS_LEVEL": {
        "meaning": "The request does not meet any configured access level condition",
        "common_causes": [
            "User connecting from outside the corporate VPN/network",
            "IP address not in the access level CIDR ranges",
            "Device does not meet BeyondCorp trust requirements",
            "Access level references a group the user is not a member of",
        ],
        "resolution_steps": [
            "1. Check the user's source IP against configured access level CIDR ranges",
            "2. Verify VPN/connectivity — user may not be connected to corporate network",
            "3. If using device trust, check BeyondCorp device compliance",
            "4. Consider adding an identity-based ingress rule as an alternative to access levels",
        ],
    },
    "SERVICE_NOT_ALLOWED_FROM_VPC": {
        "meaning": "The VPC accessible services restriction blocks the requested service",
        "common_causes": [
            "vpc_accessible_services does not include the service being called",
            "A new API was added to the project but not to the allowed services list",
        ],
        "resolution_steps": [
            "1. Check the perimeter's vpc_accessible_services configuration",
            "2. Add the missing service to allowed_services",
            "3. Or set allowed_services to ['*'] if you want to allow all services from VPC",
            "4. Note: vpc_accessible_services only restricts VPC-originating traffic, "
            "not internet-originating traffic",
        ],
    },
    "ACCESS_DENIED_GENERIC": {
        "meaning": "General VPC-SC denial — the request matched no allow rules",
        "common_causes": [
            "Missing ingress rule for the identity/source combination",
            "Identity prefix is wrong (e.g., user: vs serviceAccount:)",
            "Method/permission selector mismatch (method vs permission format)",
            "Resource selector too narrow (specific project vs '*')",
        ],
        "resolution_steps": [
            "1. Get the violation unique ID from the error response",
            "2. Look up the audit log entry for full details",
            "3. Check identity format — must be serviceAccount:, user:, or group:",
            "4. Verify method selectors — BigQuery uses 'permission:' while Storage uses 'method:'",
            "5. Test with a broader rule first, then narrow down",
        ],
    },
}
