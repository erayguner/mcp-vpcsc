"""Tools for generating ingress/egress rule YAML and retrieving common patterns."""

import json

import yaml

from vpcsc_mcp.data.patterns import COMMON_EGRESS_PATTERNS, COMMON_INGRESS_PATTERNS
from vpcsc_mcp.data.services import SERVICE_METHOD_SELECTORS


def register_rule_tools(mcp) -> None:
    """Register all rule generation tools on the FastMCP server."""

    from vpcsc_mcp.tools.safety import GENERATE

    @mcp.tool(annotations=GENERATE)
    def generate_ingress_yaml(
        service_name: str,
        access_type: str = "all",
        identity_type: str | None = None,
        identities: list[str] | None = None,
        source_project_numbers: list[str] | None = None,
        source_vpc_networks: list[str] | None = None,
        source_access_level: str | None = None,
        target_resources: list[str] | None = None,
        roles: list[str] | None = None,
        title: str = "Ingress Rule",
    ) -> str:
        """Generate a VPC-SC ingress policy YAML file for use with gcloud commands.

        Args:
            service_name: The GCP service API (e.g. 'bigquery.googleapis.com').
                Ignored when roles is set (roles apply across services).
            access_type: Method selector preset ('read', 'write', 'all', etc.). Default 'all'.
                Ignored when roles is set.
            identity_type: Identity type ('ANY_IDENTITY', 'ANY_USER_ACCOUNT',
                'ANY_SERVICE_ACCOUNT'). Mutually exclusive with identities.
            identities: Explicit list of identities. Mutually exclusive with identity_type.
            source_project_numbers: Source project numbers (without 'projects/' prefix).
            source_vpc_networks: Source VPC networks. Format:
                '//compute.googleapis.com/projects/{PROJECT_ID}/global/networks/{NAME}'.
            source_access_level: Full access level resource name, or '*' to allow any.
            target_resources: Projects inside the perimeter to grant access to.
                Default ['*'] (all resources). Must be full 'projects/NUMBER' form.
            roles: IAM roles to allow (e.g. 'roles/bigquery.dataViewer'). Alternative
                to service+methodSelectors — simpler for broad scope. Requires provider
                support for the `roles` attribute on ingressTo.operations (see docs).
            title: Title for the rule (max 100 chars).
        """
        svc = service_name.strip()
        if not svc.endswith(".googleapis.com"):
            svc = f"{svc}.googleapis.com"

        if len(title) > 100:
            return f"Error: title must be ≤ 100 chars (got {len(title)})."

        rule: dict = {"title": title}

        # Build ingressFrom
        ingress_from: dict = {}
        if identity_type:
            ingress_from["identityType"] = identity_type
        elif identities:
            ingress_from["identities"] = identities
        else:
            ingress_from["identityType"] = "ANY_IDENTITY"

        sources = []
        if source_project_numbers:
            for pn in source_project_numbers:
                sources.append({"resource": f"projects/{pn}"})
        if source_vpc_networks:
            for vpc in source_vpc_networks:
                sources.append({"resource": vpc})
        if source_access_level:
            sources.append({"accessLevel": source_access_level})
        if sources:
            ingress_from["sources"] = sources

        rule["ingressFrom"] = ingress_from

        # Build ingressTo. `operations` (service+method/permission) and `roles`
        # are mutually exclusive within a single ingressTo block per
        # Access Context Manager API rules.
        ingress_to: dict = {"resources": target_resources or ["*"]}
        if roles:
            ingress_to["roles"] = roles
        else:
            methods = SERVICE_METHOD_SELECTORS.get(svc, {})
            selectors = methods.get(access_type.lower(), [{"method": "*"}])
            ingress_to["operations"] = [
                {"serviceName": svc, "methodSelectors": selectors},
            ]
        rule["ingressTo"] = ingress_to

        yaml_output = yaml.dump([rule], default_flow_style=False, sort_keys=False)
        return (
            f"# Ingress Rule: {title}\n"
            f"# Usage: gcloud access-context-manager perimeters update PERIMETER \\\n"
            f"#   --policy=POLICY_ID --set-ingress-policies=ingress.yaml\n\n"
            f"{yaml_output}"
        )

    @mcp.tool(annotations=GENERATE)
    def generate_egress_yaml(
        service_name: str,
        access_type: str = "all",
        identity_type: str | None = None,
        identities: list[str] | None = None,
        target_project_numbers: list[str] | None = None,
        external_resources: list[str] | None = None,
        source_project_numbers: list[str] | None = None,
        source_access_level: str | None = None,
        roles: list[str] | None = None,
        title: str = "Egress Rule",
    ) -> str:
        """Generate a VPC-SC egress policy YAML file for use with gcloud commands.

        Args:
            service_name: The GCP service API (e.g. 'storage.googleapis.com').
                Ignored when roles is set.
            access_type: Method selector preset. Ignored when roles is set.
            identity_type: Identity type ('ANY_IDENTITY', 'ANY_USER_ACCOUNT',
                'ANY_SERVICE_ACCOUNT'). Mutually exclusive with identities.
            identities: Explicit list of identities. Mutually exclusive with identity_type.
            target_project_numbers: Target project numbers (without 'projects/' prefix).
            external_resources: BigQuery Omni destinations — Amazon S3
                ('s3://BUCKET') or Azure Blob Storage
                ('azure://myaccount.blob.core.windows.net/CONTAINER').
                Wildcard '*' is not allowed.
            source_project_numbers: Projects inside the perimeter that this
                egress rule applies to. When set, sourceRestriction is
                automatically enabled so only these projects match.
            source_access_level: Access level that gates which sources inside
                the perimeter may use this rule. Enables sourceRestriction.
            roles: IAM roles the caller may exercise on the egress target.
                Alternative to service+methodSelectors.
            title: Title for the rule (max 100 chars).
        """
        svc = service_name.strip()
        if not svc.endswith(".googleapis.com"):
            svc = f"{svc}.googleapis.com"

        if len(title) > 100:
            return f"Error: title must be ≤ 100 chars (got {len(title)})."

        rule: dict = {"title": title}

        # Build egressFrom (identity + optional source restriction)
        egress_from: dict = {}
        if identity_type:
            egress_from["identityType"] = identity_type
        elif identities:
            egress_from["identities"] = identities
        else:
            egress_from["identityType"] = "ANY_IDENTITY"

        sources = []
        if source_project_numbers:
            for pn in source_project_numbers:
                sources.append({"resource": f"projects/{pn}"})
        if source_access_level:
            sources.append({"accessLevel": source_access_level})
        if sources:
            egress_from["sources"] = sources
            egress_from["sourceRestriction"] = "SOURCE_RESTRICTION_ENABLED"

        rule["egressFrom"] = egress_from

        # Build egressTo — resources XOR externalResources per API rules.
        egress_to: dict = {}
        if external_resources:
            if any(r == "*" for r in external_resources):
                return "Error: external_resources does not support '*' wildcard."
            egress_to["externalResources"] = external_resources
        else:
            targets = ["*"]
            if target_project_numbers:
                targets = [f"projects/{pn}" for pn in target_project_numbers]
            egress_to["resources"] = targets

        if roles:
            egress_to["roles"] = roles
        else:
            methods = SERVICE_METHOD_SELECTORS.get(svc, {})
            selectors = methods.get(access_type.lower(), [{"method": "*"}])
            egress_to["operations"] = [
                {"serviceName": svc, "methodSelectors": selectors},
            ]
        rule["egressTo"] = egress_to

        yaml_output = yaml.dump([rule], default_flow_style=False, sort_keys=False)
        return (
            f"# Egress Rule: {title}\n"
            f"# Usage: gcloud access-context-manager perimeters update PERIMETER \\\n"
            f"#   --policy=POLICY_ID --set-egress-policies=egress.yaml\n\n"
            f"{yaml_output}"
        )

    @mcp.tool(annotations=GENERATE)
    def list_ingress_patterns() -> str:
        """List all pre-built common ingress rule patterns available for quick use."""
        lines = [f"Available ingress patterns ({len(COMMON_INGRESS_PATTERNS)}):\n"]
        for key, pattern in COMMON_INGRESS_PATTERNS.items():
            lines.append(f"  {key}:")
            lines.append(f"    Title: {pattern['title']}")
            lines.append(f"    {pattern['description']}\n")
        lines.append("Use 'get_ingress_pattern' with the pattern name to get the full template.")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def list_egress_patterns() -> str:
        """List all pre-built common egress rule patterns available for quick use."""
        lines = [f"Available egress patterns ({len(COMMON_EGRESS_PATTERNS)}):\n"]
        for key, pattern in COMMON_EGRESS_PATTERNS.items():
            lines.append(f"  {key}:")
            lines.append(f"    Title: {pattern['title']}")
            lines.append(f"    {pattern['description']}\n")
        lines.append("Use 'get_egress_pattern' with the pattern name to get the full template.")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def get_ingress_pattern(
        pattern_name: str,
        substitutions: str | None = None,
    ) -> str:
        """Get a pre-built ingress rule pattern with optional variable substitution.

        Args:
            pattern_name: The pattern name (e.g. 'bigquery-cross-project-read').
            substitutions: Optional JSON object with variable substitutions
                (e.g. '{"sa_email": "my-sa@proj.iam.gserviceaccount.com",
                "source_project_number": "123456"}').
        """
        pattern = COMMON_INGRESS_PATTERNS.get(pattern_name)
        if not pattern:
            available = ", ".join(COMMON_INGRESS_PATTERNS.keys())
            return f"Pattern '{pattern_name}' not found. Available: {available}"

        template = json.dumps(pattern["template"], indent=2)

        if substitutions:
            try:
                subs = json.loads(substitutions)
                for key, value in subs.items():
                    template = template.replace(f"{{{key}}}", str(value))
            except json.JSONDecodeError:
                return f"Error: invalid JSON in substitutions: {substitutions}"

        # Check for remaining placeholders
        remaining = []
        import re

        for match in re.finditer(r"\{(\w+)\}", template):
            remaining.append(match.group(1))

        lines = [
            f"Pattern: {pattern['title']}",
            f"Description: {pattern['description']}",
            f"\nIngress Rule (JSON):\n{template}",
        ]
        if remaining:
            lines.append(f"\nRemaining placeholders to fill: {', '.join(set(remaining))}")
        return "\n".join(lines)

    @mcp.tool(annotations=GENERATE)
    def get_egress_pattern(
        pattern_name: str,
        substitutions: str | None = None,
    ) -> str:
        """Get a pre-built egress rule pattern with optional variable substitution.

        Args:
            pattern_name: The pattern name (e.g. 'bigquery-cross-project-query').
            substitutions: Optional JSON object with variable substitutions.
        """
        pattern = COMMON_EGRESS_PATTERNS.get(pattern_name)
        if not pattern:
            available = ", ".join(COMMON_EGRESS_PATTERNS.keys())
            return f"Pattern '{pattern_name}' not found. Available: {available}"

        template = json.dumps(pattern["template"], indent=2)

        if substitutions:
            try:
                subs = json.loads(substitutions)
                for key, value in subs.items():
                    template = template.replace(f"{{{key}}}", str(value))
            except json.JSONDecodeError:
                return f"Error: invalid JSON in substitutions: {substitutions}"

        remaining = []
        import re

        for match in re.finditer(r"\{(\w+)\}", template):
            remaining.append(match.group(1))

        lines = [
            f"Pattern: {pattern['title']}",
            f"Description: {pattern['description']}",
            f"\nEgress Rule (JSON):\n{template}",
        ]
        if remaining:
            lines.append(f"\nRemaining placeholders to fill: {', '.join(set(remaining))}")
        return "\n".join(lines)
