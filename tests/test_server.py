"""Tests for the VPC-SC MCP server tools and data."""



from vpcsc_mcp.data.patterns import (
    COMMON_EGRESS_PATTERNS,
    COMMON_INGRESS_PATTERNS,
    TROUBLESHOOTING_GUIDE,
)
from vpcsc_mcp.data.services import (
    SERVICE_METHOD_SELECTORS,
    SUPPORTED_SERVICES,
    WORKLOAD_RECOMMENDATIONS,
)


class TestSupportedServices:
    def test_services_not_empty(self):
        assert len(SUPPORTED_SERVICES) > 60

    def test_key_services_present(self):
        for svc in [
            "bigquery.googleapis.com",
            "storage.googleapis.com",
            "aiplatform.googleapis.com",
            "compute.googleapis.com",
            "cloudkms.googleapis.com",
        ]:
            assert svc in SUPPORTED_SERVICES, f"{svc} missing"

    def test_service_format(self):
        for api in SUPPORTED_SERVICES:
            assert api.endswith(".googleapis.com"), f"Bad format: {api}"


class TestWorkloadRecommendations:
    def test_all_workload_types_exist(self):
        expected = {
            "ai-ml", "data-analytics", "web-application",
            "data-warehouse", "healthcare", "microservices", "gen-ai",
        }
        assert set(WORKLOAD_RECOMMENDATIONS.keys()) == expected

    def test_workload_has_required_fields(self):
        for name, rec in WORKLOAD_RECOMMENDATIONS.items():
            assert "description" in rec, f"{name} missing description"
            assert "required" in rec, f"{name} missing required"
            assert "recommended" in rec, f"{name} missing recommended"
            assert "notes" in rec, f"{name} missing notes"
            assert len(rec["required"]) > 0, f"{name} has no required services"

    def test_all_recommended_services_are_known(self):
        for name, rec in WORKLOAD_RECOMMENDATIONS.items():
            for svc in rec["required"] + rec["recommended"]:
                assert svc in SUPPORTED_SERVICES, f"{name}: {svc} not in supported services"


class TestMethodSelectors:
    def test_bigquery_selectors(self):
        assert "bigquery.googleapis.com" in SERVICE_METHOD_SELECTORS
        bq = SERVICE_METHOD_SELECTORS["bigquery.googleapis.com"]
        assert "read" in bq
        assert "write" in bq
        assert "all" in bq

    def test_storage_selectors(self):
        assert "storage.googleapis.com" in SERVICE_METHOD_SELECTORS
        gcs = SERVICE_METHOD_SELECTORS["storage.googleapis.com"]
        assert "read" in gcs
        assert "write" in gcs

    def test_selector_format(self):
        for svc, presets in SERVICE_METHOD_SELECTORS.items():
            for preset_name, selectors in presets.items():
                for sel in selectors:
                    assert "method" in sel or "permission" in sel, (
                        f"{svc}/{preset_name}: selector missing method/permission key"
                    )


class TestPatterns:
    def test_ingress_patterns_not_empty(self):
        assert len(COMMON_INGRESS_PATTERNS) >= 3

    def test_egress_patterns_not_empty(self):
        assert len(COMMON_EGRESS_PATTERNS) >= 3

    def test_ingress_pattern_structure(self):
        for name, pattern in COMMON_INGRESS_PATTERNS.items():
            assert "title" in pattern, f"{name} missing title"
            assert "description" in pattern, f"{name} missing description"
            assert "template" in pattern, f"{name} missing template"
            tpl = pattern["template"]
            assert "ingressFrom" in tpl, f"{name} missing ingressFrom"
            assert "ingressTo" in tpl, f"{name} missing ingressTo"

    def test_egress_pattern_structure(self):
        for name, pattern in COMMON_EGRESS_PATTERNS.items():
            assert "title" in pattern, f"{name} missing title"
            assert "description" in pattern, f"{name} missing description"
            assert "template" in pattern, f"{name} missing template"
            tpl = pattern["template"]
            assert "egressFrom" in tpl, f"{name} missing egressFrom"
            assert "egressTo" in tpl, f"{name} missing egressTo"


class TestTroubleshootingGuide:
    def test_violation_types_present(self):
        expected = {
            "RESOURCES_NOT_IN_SAME_SERVICE_PERIMETER",
            "NO_MATCHING_ACCESS_LEVEL",
            "SERVICE_NOT_ALLOWED_FROM_VPC",
            "ACCESS_DENIED_GENERIC",
            "EGRESS_VIOLATION",
            "METHOD_NOT_ALLOWED",
        }
        assert set(TROUBLESHOOTING_GUIDE.keys()) == expected

    def test_guide_structure(self):
        for code, guide in TROUBLESHOOTING_GUIDE.items():
            assert "meaning" in guide, f"{code} missing meaning"
            assert "common_causes" in guide, f"{code} missing common_causes"
            assert "resolution_steps" in guide, f"{code} missing resolution_steps"
            assert len(guide["common_causes"]) > 0
            assert len(guide["resolution_steps"]) > 0


class TestTerraformGeneration:
    def test_generate_perimeter(self):
        from vpcsc_mcp.tools.terraform_gen import _hcl_list

        result = _hcl_list(["a", "b", "c"])
        assert '"a"' in result
        assert '"b"' in result
        assert '"c"' in result

    def test_hcl_list_multiline(self):
        from vpcsc_mcp.tools.terraform_gen import _hcl_list

        result = _hcl_list(["a", "b", "c", "d"], indent=4)
        assert "\n" in result  # Should be multiline for 4+ items


class TestNewServices:
    """Tests for newly added VPC-SC supported services."""

    def test_new_services_present(self):
        new_services = [
            "workstations.googleapis.com",
            "networkmanagement.googleapis.com",
            "accesscontextmanager.googleapis.com",
            "binaryauthorization.googleapis.com",
            "clouddeploy.googleapis.com",
            "cloudscheduler.googleapis.com",
            "cloudtasks.googleapis.com",
            "privateca.googleapis.com",
            "tpu.googleapis.com",
        ]
        for svc in new_services:
            assert svc in SUPPORTED_SERVICES, f"{svc} missing from SUPPORTED_SERVICES"


class TestNewMethodSelectors:
    """Tests for newly added method selectors."""

    def test_compute_selectors(self):
        assert "compute.googleapis.com" in SERVICE_METHOD_SELECTORS
        compute = SERVICE_METHOD_SELECTORS["compute.googleapis.com"]
        assert "read" in compute
        assert "write" in compute
        assert "all" in compute

    def test_container_selectors(self):
        assert "container.googleapis.com" in SERVICE_METHOD_SELECTORS
        gke = SERVICE_METHOD_SELECTORS["container.googleapis.com"]
        assert "read" in gke
        assert "write" in gke

    def test_run_selectors(self):
        assert "run.googleapis.com" in SERVICE_METHOD_SELECTORS
        run = SERVICE_METHOD_SELECTORS["run.googleapis.com"]
        assert "invoke" in run
        assert "manage" in run

    def test_sqladmin_selectors(self):
        assert "sqladmin.googleapis.com" in SERVICE_METHOD_SELECTORS
        sql = SERVICE_METHOD_SELECTORS["sqladmin.googleapis.com"]
        assert "read" in sql
        assert "write" in sql

    def test_total_selector_services(self):
        """At least 10 services should have method selectors."""
        assert len(SERVICE_METHOD_SELECTORS) >= 10


class TestNewPatterns:
    """Tests for newly added ingress/egress patterns."""

    def test_new_ingress_patterns(self):
        new_patterns = ["gke-workload-identity", "pubsub-cross-project-subscribe"]
        for name in new_patterns:
            assert name in COMMON_INGRESS_PATTERNS, f"Ingress pattern '{name}' missing"
            pattern = COMMON_INGRESS_PATTERNS[name]
            assert "template" in pattern
            assert "ingressFrom" in pattern["template"]
            assert "ingressTo" in pattern["template"]

    def test_new_egress_patterns(self):
        new_patterns = ["dataflow-cross-project", "pubsub-cross-project-publish"]
        for name in new_patterns:
            assert name in COMMON_EGRESS_PATTERNS, f"Egress pattern '{name}' missing"
            pattern = COMMON_EGRESS_PATTERNS[name]
            assert "template" in pattern
            assert "egressFrom" in pattern["template"]
            assert "egressTo" in pattern["template"]

    def test_ingress_pattern_count(self):
        assert len(COMMON_INGRESS_PATTERNS) >= 7

    def test_egress_pattern_count(self):
        assert len(COMMON_EGRESS_PATTERNS) >= 7


class TestMicroservicesWorkload:
    """Tests for the microservices workload type."""

    def test_microservices_exists(self):
        assert "microservices" in WORKLOAD_RECOMMENDATIONS

    def test_microservices_structure(self):
        rec = WORKLOAD_RECOMMENDATIONS["microservices"]
        assert "description" in rec
        assert "required" in rec
        assert "recommended" in rec
        assert "notes" in rec
        assert "container.googleapis.com" in rec["required"]
        assert "run.googleapis.com" in rec["required"]

    def test_microservices_services_known(self):
        rec = WORKLOAD_RECOMMENDATIONS["microservices"]
        for svc in rec["required"] + rec["recommended"]:
            assert svc in SUPPORTED_SERVICES, f"microservices: {svc} not in supported services"


class TestNewViolationTypes:
    """Tests for newly added violation troubleshooting entries."""

    def test_egress_violation(self):
        guide = TROUBLESHOOTING_GUIDE["EGRESS_VIOLATION"]
        assert "meaning" in guide
        assert len(guide["common_causes"]) > 0
        assert len(guide["resolution_steps"]) > 0

    def test_method_not_allowed(self):
        guide = TROUBLESHOOTING_GUIDE["METHOD_NOT_ALLOWED"]
        assert "meaning" in guide
        assert len(guide["common_causes"]) > 0
        assert len(guide["resolution_steps"]) > 0
        # Should mention the method/permission distinction
        combined = " ".join(guide["common_causes"] + guide["resolution_steps"])
        assert "permission" in combined.lower()


class TestServerImport:
    def test_server_creates(self):
        from vpcsc_mcp.server import mcp

        assert mcp.name == "VPC-SC Helper"
