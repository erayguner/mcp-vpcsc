"""Tests for the YAML rule generators — roles, externalResources, sourceRestriction."""

from __future__ import annotations

from urllib.parse import urlparse

import yaml

from vpcsc_mcp.server import mcp  # noqa: F401 — triggers register_rule_tools
from vpcsc_mcp.tools import register_rule_tools


class _MockMCP:
    """Lightweight MCP shim for invoking the tool factories directly."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, *, annotations=None):  # noqa: ARG002
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _load_rule(text: str) -> dict:
    """Strip header comments and parse the YAML rule list."""
    yaml_part = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    rules = yaml.safe_load(yaml_part)
    assert isinstance(rules, list) and len(rules) == 1
    return rules[0]


def _register() -> _MockMCP:
    mock = _MockMCP()
    register_rule_tools(mock)
    return mock


# ─── Ingress ─────────────────────────────────────────────────────────────


class TestIngressYAML:
    def test_roles_mode_omits_operations(self):
        m = _register()
        out = m.tools["generate_ingress_yaml"](
            service_name="bigquery.googleapis.com",
            roles=["roles/bigquery.dataViewer"],
            identity_type="ANY_SERVICE_ACCOUNT",
            title="bq-read",
        )
        rule = _load_rule(out)
        assert rule["ingressTo"]["roles"] == ["roles/bigquery.dataViewer"]
        assert "operations" not in rule["ingressTo"]

    def test_operations_mode_default(self):
        m = _register()
        out = m.tools["generate_ingress_yaml"](
            service_name="bigquery.googleapis.com",
            access_type="read",
            identity_type="ANY_SERVICE_ACCOUNT",
        )
        rule = _load_rule(out)
        assert "operations" in rule["ingressTo"]
        assert rule["ingressTo"]["operations"][0]["serviceName"] == ("bigquery.googleapis.com")
        assert "roles" not in rule["ingressTo"]

    def test_vpc_network_source(self):
        m = _register()
        out = m.tools["generate_ingress_yaml"](
            service_name="storage.googleapis.com",
            source_vpc_networks=[
                "//compute.googleapis.com/projects/p1/global/networks/vpc1",
            ],
        )
        rule = _load_rule(out)
        sources = rule["ingressFrom"]["sources"]
        assert any(
            (
                (parsed := urlparse(f"https:{resource}")).hostname == "compute.googleapis.com"
                and parsed.path.startswith("/projects/")
            )
            for s in sources
            for resource in [s.get("resource", "")]
            if resource.startswith("//")
        )

    def test_target_resources_override(self):
        m = _register()
        out = m.tools["generate_ingress_yaml"](
            service_name="bigquery.googleapis.com",
            target_resources=["projects/111111", "projects/222222"],
        )
        rule = _load_rule(out)
        assert rule["ingressTo"]["resources"] == [
            "projects/111111",
            "projects/222222",
        ]

    def test_title_length_limit(self):
        m = _register()
        out = m.tools["generate_ingress_yaml"](
            service_name="bigquery.googleapis.com",
            title="x" * 150,
        )
        assert "Error" in out and "≤ 100" in out


# ─── Egress ──────────────────────────────────────────────────────────────


class TestEgressYAML:
    def test_roles_mode_omits_operations(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="storage.googleapis.com",
            roles=["roles/storage.objectViewer"],
        )
        rule = _load_rule(out)
        assert rule["egressTo"]["roles"] == ["roles/storage.objectViewer"]
        assert "operations" not in rule["egressTo"]

    def test_external_resources_s3(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="bigquery.googleapis.com",
            external_resources=["s3://my-omni-bucket"],
            title="omni-s3-egress",
        )
        rule = _load_rule(out)
        assert rule["egressTo"]["externalResources"] == ["s3://my-omni-bucket"]
        # externalResources and resources are mutually exclusive
        assert "resources" not in rule["egressTo"]

    def test_external_resources_azure(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="bigquery.googleapis.com",
            external_resources=[
                "azure://myacct.blob.core.windows.net/container",
            ],
        )
        rule = _load_rule(out)
        assert rule["egressTo"]["externalResources"][0].startswith(
            "azure://",
        )

    def test_external_resources_wildcard_rejected(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="bigquery.googleapis.com",
            external_resources=["*"],
        )
        assert "Error" in out and "'*' wildcard" in out

    def test_source_restriction_enabled_for_source_projects(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="storage.googleapis.com",
            source_project_numbers=["111111"],
        )
        rule = _load_rule(out)
        assert rule["egressFrom"]["sourceRestriction"] == ("SOURCE_RESTRICTION_ENABLED")
        assert rule["egressFrom"]["sources"] == [{"resource": "projects/111111"}]

    def test_source_restriction_enabled_for_access_level(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="storage.googleapis.com",
            source_access_level=("accessPolicies/123/accessLevels/corp_network"),
        )
        rule = _load_rule(out)
        assert rule["egressFrom"]["sourceRestriction"] == ("SOURCE_RESTRICTION_ENABLED")

    def test_no_source_restriction_when_sources_unset(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="storage.googleapis.com",
        )
        rule = _load_rule(out)
        assert "sourceRestriction" not in rule["egressFrom"]
        assert "sources" not in rule["egressFrom"]

    def test_target_projects_default_wildcard(self):
        m = _register()
        out = m.tools["generate_egress_yaml"](
            service_name="bigquery.googleapis.com",
        )
        rule = _load_rule(out)
        assert rule["egressTo"]["resources"] == ["*"]
