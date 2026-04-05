"""VPC-SC supported services and workload recommendations.

Service list sourced from official Google Cloud documentation:
https://cloud.google.com/vpc-service-controls/docs/supported-products

Use ``gcloud access-context-manager supported-services list`` for the
live canonical list.  This file is a curated snapshot for offline use.
"""

# Services confirmed as supporting VPC Service Controls.
# Sourced from https://cloud.google.com/vpc-service-controls/docs/supported-products
SUPPORTED_SERVICES: dict[str, str] = {
    # ── AI / ML ──────────────────────────────────────────────────────
    "aiplatform.googleapis.com": "Vertex AI",
    "automl.googleapis.com": "AutoML",
    "cloudaicompanion.googleapis.com": "Gemini for Google Cloud",
    "discoveryengine.googleapis.com": "Vertex AI Search",
    "documentai.googleapis.com": "Document AI",
    "language.googleapis.com": "Cloud Natural Language",
    "ml.googleapis.com": "AI Platform Training (legacy)",
    "notebooks.googleapis.com": "Vertex AI Workbench",
    "retail.googleapis.com": "Vertex AI Search for Retail",
    "speech.googleapis.com": "Cloud Speech-to-Text",
    "texttospeech.googleapis.com": "Cloud Text-to-Speech",
    "translate.googleapis.com": "Cloud Translation",
    "videointelligence.googleapis.com": "Video Intelligence",
    "vision.googleapis.com": "Cloud Vision",
    "visionai.googleapis.com": "Vision AI",
    # ── Analytics / BigQuery ─────────────────────────────────────────
    "analyticshub.googleapis.com": "Analytics Hub",
    "bigquery.googleapis.com": "BigQuery",
    "bigqueryconnection.googleapis.com": "BigQuery Connection",
    "bigquerydatapolicy.googleapis.com": "BigQuery Data Policy",
    "bigquerydatatransfer.googleapis.com": "BigQuery Data Transfer",
    "bigquerymigration.googleapis.com": "BigQuery Migration",
    "bigqueryreservation.googleapis.com": "BigQuery Reservation",
    "bigquerystorage.googleapis.com": "BigQuery Storage",
    "biglake.googleapis.com": "BigLake",
    # ── Compute ──────────────────────────────────────────────────────
    "batch.googleapis.com": "Batch",
    "compute.googleapis.com": "Compute Engine",
    "osconfig.googleapis.com": "OS Config",
    "oslogin.googleapis.com": "OS Login",
    "tpu.googleapis.com": "Cloud TPU",
    "workstations.googleapis.com": "Cloud Workstations",
    # ── Containers / Kubernetes ──────────────────────────────────────
    "container.googleapis.com": "Google Kubernetes Engine",
    "containeranalysis.googleapis.com": "Artifact Analysis",
    "containerregistry.googleapis.com": "Container Registry",
    "gkebackup.googleapis.com": "Backup for GKE",
    "gkeconnect.googleapis.com": "Connect (GKE)",
    "gkehub.googleapis.com": "GKE Hub (Fleet)",
    "gkemulticloud.googleapis.com": "GKE Multi-cloud",
    "gkeonprem.googleapis.com": "GKE On-Prem (Anthos)",
    # ── Serverless ───────────────────────────────────────────────────
    "cloudfunctions.googleapis.com": "Cloud Functions",
    "run.googleapis.com": "Cloud Run",
    "vpcaccess.googleapis.com": "Serverless VPC Access",
    "workflows.googleapis.com": "Workflows",
    # ── Storage ──────────────────────────────────────────────────────
    "storage.googleapis.com": "Cloud Storage",
    "storagebatchoperations.googleapis.com": "Storage Batch Operations",
    "storageinsights.googleapis.com": "Storage Insights",
    "storagetransfer.googleapis.com": "Storage Transfer Service",
    # ── Databases ────────────────────────────────────────────────────
    "alloydb.googleapis.com": "AlloyDB for PostgreSQL",
    "bigtable.googleapis.com": "Cloud Bigtable",
    "datastore.googleapis.com": "Datastore",
    "file.googleapis.com": "Filestore",
    "firestore.googleapis.com": "Firestore",
    "memcache.googleapis.com": "Memorystore for Memcached",
    "redis.googleapis.com": "Memorystore for Redis",
    "spanner.googleapis.com": "Cloud Spanner",
    "sqladmin.googleapis.com": "Cloud SQL Admin",
    # ── Data Engineering ─────────────────────────────────────────────
    "composer.googleapis.com": "Cloud Composer",
    "datacatalog.googleapis.com": "Data Catalog",
    "dataflow.googleapis.com": "Dataflow",
    "dataform.googleapis.com": "Dataform",
    "datafusion.googleapis.com": "Cloud Data Fusion",
    "datalineage.googleapis.com": "Data Lineage",
    "datamigration.googleapis.com": "Database Migration Service",
    "dataplex.googleapis.com": "Dataplex",
    "dataproc.googleapis.com": "Dataproc",
    "datastream.googleapis.com": "Datastream",
    "metastore.googleapis.com": "Dataproc Metastore",
    "pubsub.googleapis.com": "Pub/Sub",
    "pubsublite.googleapis.com": "Pub/Sub Lite",
    # ── Networking ───────────────────────────────────────────────────
    "dns.googleapis.com": "Cloud DNS",
    "networkconnectivity.googleapis.com": "Network Connectivity Center",
    "networkmanagement.googleapis.com": "Network Management",
    "networksecurity.googleapis.com": "Network Security",
    "networkservices.googleapis.com": "Network Services",
    "servicedirectory.googleapis.com": "Service Directory",
    "servicenetworking.googleapis.com": "Service Networking",
    "trafficdirector.googleapis.com": "Traffic Director",
    # ── Security & Identity ──────────────────────────────────────────
    "accesscontextmanager.googleapis.com": "Access Context Manager",
    "beyondcorp.googleapis.com": "BeyondCorp Enterprise",
    "binaryauthorization.googleapis.com": "Binary Authorization",
    "cloudkms.googleapis.com": "Cloud KMS",
    "confidentialcomputing.googleapis.com": "Confidential Computing",
    "dlp.googleapis.com": "Cloud DLP (Sensitive Data Protection)",
    "iam.googleapis.com": "IAM",
    "iamcredentials.googleapis.com": "IAM Service Account Credentials",
    "iap.googleapis.com": "Identity-Aware Proxy",
    "ids.googleapis.com": "Cloud IDS",
    "kmsinventory.googleapis.com": "KMS Inventory",
    "modelarmor.googleapis.com": "Model Armor",
    "policysimulator.googleapis.com": "Policy Simulator",
    "policytroubleshooter.googleapis.com": "Policy Troubleshooter",
    "privateca.googleapis.com": "Certificate Authority Service",
    "privilegedaccessmanager.googleapis.com": "Privileged Access Manager",
    "publicca.googleapis.com": "Public Certificate Authority",
    "recaptchaenterprise.googleapis.com": "reCAPTCHA Enterprise",
    "secretmanager.googleapis.com": "Secret Manager",
    "securitycenter.googleapis.com": "Security Command Center",
    "securitycentermanagement.googleapis.com": "Security Center Management",
    "webrisk.googleapis.com": "Web Risk",
    "websecurityscanner.googleapis.com": "Web Security Scanner",
    # ── CI/CD & DevOps ───────────────────────────────────────────────
    "artifactregistry.googleapis.com": "Artifact Registry",
    "cloudbuild.googleapis.com": "Cloud Build",
    "clouddeploy.googleapis.com": "Cloud Deploy",
    "ondemandscanning.googleapis.com": "On-Demand Scanning",
    "securesourcemanager.googleapis.com": "Secure Source Manager",
    # ── Operations ───────────────────────────────────────────────────
    "clouderrorreporting.googleapis.com": "Error Reporting",
    "cloudprofiler.googleapis.com": "Cloud Profiler",
    "cloudtrace.googleapis.com": "Cloud Trace",
    "logging.googleapis.com": "Cloud Logging",
    "monitoring.googleapis.com": "Cloud Monitoring",
    # ── Management ───────────────────────────────────────────────────
    "accessapproval.googleapis.com": "Access Approval",
    "apikeys.googleapis.com": "API Keys",
    "assuredworkloads.googleapis.com": "Assured Workloads",
    "certificatemanager.googleapis.com": "Certificate Manager",
    "cloudasset.googleapis.com": "Cloud Asset Inventory",
    "cloudresourcemanager.googleapis.com": "Cloud Resource Manager",
    "cloudscheduler.googleapis.com": "Cloud Scheduler",
    "cloudtasks.googleapis.com": "Cloud Tasks",
    "essentialcontacts.googleapis.com": "Essential Contacts",
    "orgpolicy.googleapis.com": "Organization Policy Service",
    "servicecontrol.googleapis.com": "Service Control",
    "servicehealth.googleapis.com": "Personalized Service Health",
    # ── Integration / Middleware ──────────────────────────────────────
    "apigee.googleapis.com": "Apigee API Management",
    "apigeeconnect.googleapis.com": "Apigee Connect",
    "connectors.googleapis.com": "Integration Connectors",
    "eventarc.googleapis.com": "Eventarc",
    "integrations.googleapis.com": "Application Integration",
    "managedkafka.googleapis.com": "Managed Service for Apache Kafka",
    # ── Conversational AI ────────────────────────────────────────────
    "contactcenterinsights.googleapis.com": "Contact Center AI Insights",
    "dialogflow.googleapis.com": "Dialogflow",
    # ── Healthcare ───────────────────────────────────────────────────
    "healthcare.googleapis.com": "Cloud Healthcare API",
    # ── Media ────────────────────────────────────────────────────────
    "livestream.googleapis.com": "Live Stream API",
    "transcoder.googleapis.com": "Transcoder API",
    "videostitcher.googleapis.com": "Video Stitcher API",
    # ── Migration ────────────────────────────────────────────────────
    "migrationcenter.googleapis.com": "Migration Center",
    "rapidmigrationassessment.googleapis.com": "Rapid Migration Assessment",
    "vmmigration.googleapis.com": "VM Migration",
    # ── Hybrid & Multi-cloud ─────────────────────────────────────────
    "edgecontainer.googleapis.com": "Distributed Cloud Edge",
    "vmwareengine.googleapis.com": "VMware Engine",
    # ── High-performance storage ─────────────────────────────────────
    "lustre.googleapis.com": "Google Cloud Managed Lustre",
    "netapp.googleapis.com": "NetApp Volumes",
    "parallelstore.googleapis.com": "Parallelstore",
    # ── Managed databases / identity ─────────────────────────────────
    "managedidentities.googleapis.com": "Managed Service for Microsoft AD",
    # ── Other ────────────────────────────────────────────────────────
    "backupdr.googleapis.com": "Backup and DR Service",
    "config.googleapis.com": "Infrastructure Manager",
    "cloudsupport.googleapis.com": "Cloud Support API",
    "financialservices.googleapis.com": "Financial Services API",
    "looker.googleapis.com": "Looker (Google Cloud core)",
}

# Recommended restricted services grouped by workload type
WORKLOAD_RECOMMENDATIONS: dict[str, dict] = {
    "ai-ml": {
        "description": "AI/ML workloads (Vertex AI, BigQuery ML, AutoML)",
        "required": [
            "aiplatform.googleapis.com",
            "bigquery.googleapis.com",
            "storage.googleapis.com",
            "compute.googleapis.com",
        ],
        "recommended": [
            "notebooks.googleapis.com",
            "artifactregistry.googleapis.com",
            "containerregistry.googleapis.com",
            "dataflow.googleapis.com",
            "logging.googleapis.com",
            "monitoring.googleapis.com",
            "secretmanager.googleapis.com",
            "cloudkms.googleapis.com",
            "pubsub.googleapis.com",
        ],
        "notes": [
            "Vertex AI training jobs need compute and storage in the same perimeter",
            "Use Private Google Access for Workbench notebooks",
            "BigQuery cross-project queries require egress rules on both sides",
            "Model artifacts in GCS need storage rules for training pipelines",
        ],
    },
    "data-analytics": {
        "description": "Data analytics (BigQuery, Dataflow, Dataproc, Dataplex)",
        "required": [
            "bigquery.googleapis.com",
            "storage.googleapis.com",
            "bigquerystorage.googleapis.com",
        ],
        "recommended": [
            "bigquerydatatransfer.googleapis.com",
            "dataflow.googleapis.com",
            "dataproc.googleapis.com",
            "dataplex.googleapis.com",
            "datacatalog.googleapis.com",
            "composer.googleapis.com",
            "logging.googleapis.com",
            "monitoring.googleapis.com",
            "pubsub.googleapis.com",
            "cloudkms.googleapis.com",
        ],
        "notes": [
            "BigQuery Data Transfer Service needs its own egress rules",
            "Dataflow workers must be in projects within the perimeter",
            "Composer environments need Cloud SQL and GCS within scope",
            "Cross-project dataset access is the #1 source of VPC-SC denials",
        ],
    },
    "web-application": {
        "description": "Web applications (Cloud Run, GKE, Cloud Functions)",
        "required": [
            "run.googleapis.com",
            "storage.googleapis.com",
            "compute.googleapis.com",
        ],
        "recommended": [
            "container.googleapis.com",
            "cloudfunctions.googleapis.com",
            "cloudbuild.googleapis.com",
            "artifactregistry.googleapis.com",
            "secretmanager.googleapis.com",
            "cloudkms.googleapis.com",
            "redis.googleapis.com",
            "sqladmin.googleapis.com",
            "logging.googleapis.com",
            "monitoring.googleapis.com",
            "vpcaccess.googleapis.com",
            "pubsub.googleapis.com",
        ],
        "notes": [
            "Cloud Run/Functions need Serverless VPC Access for private networking",
            "Cloud Build needs egress to pull base images from outside perimeter",
            "GKE clusters must use VPC-native (alias IP) mode",
            "Deploying Cloud Functions touches both cloudfunctions and storage APIs",
        ],
    },
    "data-warehouse": {
        "description": "Data warehouse (BigQuery-centric with ETL pipelines)",
        "required": [
            "bigquery.googleapis.com",
            "bigquerystorage.googleapis.com",
            "storage.googleapis.com",
        ],
        "recommended": [
            "bigquerydatatransfer.googleapis.com",
            "bigqueryreservation.googleapis.com",
            "datacatalog.googleapis.com",
            "dataplex.googleapis.com",
            "dataflow.googleapis.com",
            "dlp.googleapis.com",
            "cloudkms.googleapis.com",
            "logging.googleapis.com",
            "monitoring.googleapis.com",
        ],
        "notes": [
            "Reservation API manages slot capacity — restrict to prevent external reservation sharing",
            "DLP scanning jobs need both DLP and target service in perimeter",
            "Data Catalog provides metadata security — restrict alongside BigQuery",
        ],
    },
    "microservices": {
        "description": "Microservices (GKE, Cloud Run, Cloud Functions with service mesh)",
        "required": [
            "container.googleapis.com",
            "run.googleapis.com",
            "compute.googleapis.com",
            "storage.googleapis.com",
        ],
        "recommended": [
            "cloudfunctions.googleapis.com",
            "cloudbuild.googleapis.com",
            "artifactregistry.googleapis.com",
            "binaryauthorization.googleapis.com",
            "secretmanager.googleapis.com",
            "cloudkms.googleapis.com",
            "pubsub.googleapis.com",
            "redis.googleapis.com",
            "sqladmin.googleapis.com",
            "cloudtasks.googleapis.com",
            "cloudscheduler.googleapis.com",
            "logging.googleapis.com",
            "monitoring.googleapis.com",
            "vpcaccess.googleapis.com",
            "dns.googleapis.com",
        ],
        "notes": [
            "GKE clusters must use VPC-native (alias IP) mode for VPC-SC compatibility",
            "Cloud Run and Cloud Functions need Serverless VPC Access connectors for private networking",
            "Binary Authorization verifies container images before deployment — restrict alongside GKE",
            "Cloud Build needs ingress rules to deploy into perimeter projects",
            "Service-to-service calls within the perimeter are unrestricted for restricted services",
            "Use Cloud Tasks and Cloud Scheduler for async communication instead of direct HTTP where possible",
        ],
    },
    "gen-ai": {
        "description": "Generative AI workloads (Gemini, Vertex AI Search, RAG pipelines)",
        "required": [
            "aiplatform.googleapis.com",
            "storage.googleapis.com",
            "compute.googleapis.com",
        ],
        "recommended": [
            "discoveryengine.googleapis.com",
            "cloudaicompanion.googleapis.com",
            "bigquery.googleapis.com",
            "biglake.googleapis.com",
            "notebooks.googleapis.com",
            "artifactregistry.googleapis.com",
            "cloudkms.googleapis.com",
            "secretmanager.googleapis.com",
            "logging.googleapis.com",
            "monitoring.googleapis.com",
            "run.googleapis.com",
            "cloudfunctions.googleapis.com",
            "pubsub.googleapis.com",
            "dataflow.googleapis.com",
            "cloudbuild.googleapis.com",
        ],
        "notes": [
            "Vertex AI endpoints (prediction, tuning, RAG) require aiplatform, compute, "
            "and storage in the same perimeter",
            "Gemini for Google Cloud (cloudaicompanion) needs its own perimeter entry when used in VPC-SC projects",
            "Vertex AI Search (discoveryengine) must be in the same perimeter as its data source (BigQuery/GCS)",
            "BigLake tables used as grounding sources need biglake.googleapis.com restricted alongside BigQuery",
            "Model artifacts and training data in GCS require storage rules for all pipeline stages",
            "Embeddings and vector search workloads use aiplatform — ensure egress rules cover model serving projects",
        ],
    },
    "healthcare": {
        "description": "Healthcare workloads (HIPAA, FHIR, DICOM)",
        "required": [
            "healthcare.googleapis.com",
            "storage.googleapis.com",
            "bigquery.googleapis.com",
            "cloudkms.googleapis.com",
        ],
        "recommended": [
            "dlp.googleapis.com",
            "pubsub.googleapis.com",
            "logging.googleapis.com",
            "monitoring.googleapis.com",
            "secretmanager.googleapis.com",
            "compute.googleapis.com",
            "cloudfunctions.googleapis.com",
        ],
        "notes": [
            "Healthcare API stores PHI — must be in perimeter for HIPAA",
            "CMEK (Cloud KMS) is required for healthcare data at rest",
            "DLP can de-identify PHI before exfiltrating to analytics perimeter",
            "Audit logging must be enabled for all healthcare API access",
        ],
    },
}

# Common method selectors for ingress/egress rules by service
SERVICE_METHOD_SELECTORS: dict[str, dict[str, list[dict[str, str]]]] = {
    "bigquery.googleapis.com": {
        "read": [
            {"permission": "bigquery.datasets.get"},
            {"permission": "bigquery.tables.list"},
            {"permission": "bigquery.tables.get"},
            {"permission": "bigquery.tables.getData"},
            {"permission": "bigquery.jobs.create"},
        ],
        "write": [
            {"permission": "bigquery.datasets.get"},
            {"permission": "bigquery.tables.create"},
            {"permission": "bigquery.tables.update"},
            {"permission": "bigquery.tables.updateData"},
            {"permission": "bigquery.jobs.create"},
        ],
        "stream_insert": [
            {"method": "google.cloud.bigquery.v2.TableDataService.InsertAll"},
        ],
        "transfer": [
            {"permission": "bigquery.transfers.get"},
            {"permission": "bigquery.transfers.update"},
        ],
        "all": [{"method": "*"}],
    },
    "storage.googleapis.com": {
        "read": [
            {"method": "google.storage.objects.get"},
            {"method": "google.storage.objects.list"},
            {"method": "google.storage.buckets.get"},
            {"method": "google.storage.buckets.list"},
            {"method": "google.storage.buckets.testIamPermissions"},
        ],
        "write": [
            {"method": "google.storage.objects.create"},
            {"method": "google.storage.objects.delete"},
            {"method": "google.storage.multipartUploads.create"},
        ],
        "admin": [
            {"method": "google.storage.buckets.create"},
            {"method": "google.storage.buckets.delete"},
            {"method": "google.storage.buckets.update"},
            {"method": "google.storage.buckets.setIamPolicy"},
            {"method": "google.storage.buckets.getIamPolicy"},
        ],
        "all": [{"method": "*"}],
    },
    "aiplatform.googleapis.com": {
        "predict": [
            {"method": "google.cloud.aiplatform.v1.PredictionService.Predict"},
            {"method": "google.cloud.aiplatform.v1.PredictionService.RawPredict"},
        ],
        "training": [
            {"method": "google.cloud.aiplatform.v1.PipelineService.CreateTrainingPipeline"},
            {"method": "google.cloud.aiplatform.v1.PipelineService.GetTrainingPipeline"},
            {"method": "google.cloud.aiplatform.v1.JobService.CreateCustomJob"},
        ],
        "datasets": [
            {"method": "google.cloud.aiplatform.v1.DatasetService.ListDatasets"},
            {"method": "google.cloud.aiplatform.v1.DatasetService.GetDataset"},
            {"method": "google.cloud.aiplatform.v1.DatasetService.CreateDataset"},
        ],
        "all": [{"method": "*"}],
    },
    "logging.googleapis.com": {
        "read": [
            {"method": "google.logging.v2.LoggingServiceV2.ListLogEntries"},
            {"method": "google.logging.v2.LoggingServiceV2.ReadLogEntries"},
        ],
        "write": [
            {"method": "google.logging.v2.LoggingServiceV2.WriteLogEntries"},
        ],
        "all": [{"method": "*"}],
    },
    "secretmanager.googleapis.com": {
        "read": [
            {"method": "google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion"},
            {"method": "google.cloud.secretmanager.v1.SecretManagerService.GetSecret"},
            {"method": "google.cloud.secretmanager.v1.SecretManagerService.ListSecrets"},
        ],
        "write": [
            {"method": "google.cloud.secretmanager.v1.SecretManagerService.CreateSecret"},
            {"method": "google.cloud.secretmanager.v1.SecretManagerService.AddSecretVersion"},
        ],
        "all": [{"method": "*"}],
    },
    "pubsub.googleapis.com": {
        "publish": [
            {"method": "google.pubsub.v1.Publisher.Publish"},
        ],
        "subscribe": [
            {"method": "google.pubsub.v1.Subscriber.Pull"},
            {"method": "google.pubsub.v1.Subscriber.StreamingPull"},
        ],
        "all": [{"method": "*"}],
    },
    "compute.googleapis.com": {
        "read": [
            {"method": "compute.instances.get"},
            {"method": "compute.instances.list"},
            {"method": "compute.networks.get"},
            {"method": "compute.subnetworks.get"},
        ],
        "write": [
            {"method": "compute.instances.insert"},
            {"method": "compute.instances.delete"},
            {"method": "compute.instances.start"},
            {"method": "compute.instances.stop"},
        ],
        "all": [{"method": "*"}],
    },
    "container.googleapis.com": {
        "read": [
            {"method": "google.container.v1.ClusterManager.GetCluster"},
            {"method": "google.container.v1.ClusterManager.ListClusters"},
            {"method": "google.container.v1.ClusterManager.GetNodePool"},
        ],
        "write": [
            {"method": "google.container.v1.ClusterManager.CreateCluster"},
            {"method": "google.container.v1.ClusterManager.UpdateCluster"},
            {"method": "google.container.v1.ClusterManager.DeleteCluster"},
        ],
        "all": [{"method": "*"}],
    },
    "run.googleapis.com": {
        "invoke": [
            {"method": "google.cloud.run.v2.Services.InvokeService"},
        ],
        "manage": [
            {"method": "google.cloud.run.v2.Services.CreateService"},
            {"method": "google.cloud.run.v2.Services.UpdateService"},
            {"method": "google.cloud.run.v2.Services.DeleteService"},
            {"method": "google.cloud.run.v2.Revisions.GetRevision"},
        ],
        "all": [{"method": "*"}],
    },
    "sqladmin.googleapis.com": {
        "read": [
            {"method": "sql.instances.get"},
            {"method": "sql.instances.list"},
            {"method": "sql.databases.list"},
        ],
        "write": [
            {"method": "sql.instances.create"},
            {"method": "sql.instances.update"},
            {"method": "sql.instances.delete"},
        ],
        "all": [{"method": "*"}],
    },
}
