"""Tools for generating Terraform HCL configurations for VPC-SC resources."""

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import textwrap

_TF_IDENTIFIER = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
_NUMERIC = re.compile(r"^[0-9]+$")
_SERVICE_API = re.compile(r"^[a-z0-9.-]+\.googleapis\.com$")
_SAFE_FILENAME = re.compile(r"[^a-zA-Z0-9_-]")


def _resolve_output_dir(output_dir: str | None) -> str:
    """Resolve and validate the output directory.

    Returns an absolute path under an allowed root. Rejects paths that would
    escape the allowed root (traversal), absolute paths outside it, and
    symlinks that resolve outside it.

    Allowed roots (in order of precedence):
      1. ``VPCSC_MCP_OUTPUT_ROOT`` env var, if set (must be an absolute path).
      2. The current working directory.
    """
    allowed_root = os.environ.get("VPCSC_MCP_OUTPUT_ROOT") or os.getcwd()
    allowed_root = os.path.realpath(os.path.abspath(allowed_root))

    if output_dir is None:
        return allowed_root

    # Treat relative paths as relative to the allowed root.
    candidate = output_dir if os.path.isabs(output_dir) else os.path.join(allowed_root, output_dir)
    resolved = os.path.realpath(os.path.abspath(candidate))

    # Containment check — resolved path must equal or be nested under allowed_root.
    root_with_sep = allowed_root + os.sep
    if resolved != allowed_root and not resolved.startswith(root_with_sep):
        raise ValueError(
            f"output_dir {output_dir!r} resolves to {resolved!r} which is outside "
            f"the allowed root {allowed_root!r}. Set VPCSC_MCP_OUTPUT_ROOT to widen "
            f"the allowed root, or use a path inside the current working directory."
        )
    return resolved


def _maybe_write_hcl(
    hcl: str,
    project_name: str | None,
    resource_type: str,
    resource_name: str,
    output_dir: str | None = None,
) -> str:
    """Optionally write HCL to a project-prefixed file in the working directory.

    When *project_name* is provided the HCL is written to
    ``{output_dir}/{project_name}_{resource_type}_{resource_name}.tf``
    and the return value includes both the file path and the HCL content.
    When *project_name* is ``None`` the HCL is returned unchanged.

    ``output_dir`` is validated to be under an allowed root (current working
    directory, or ``VPCSC_MCP_OUTPUT_ROOT`` if set). Paths outside the root
    — including absolute paths and traversal attempts — raise ``ValueError``.
    """
    if not project_name:
        return hcl

    safe_project = _SAFE_FILENAME.sub("_", project_name.lower()).strip("_")
    safe_name = _SAFE_FILENAME.sub("_", resource_name.lower()).strip("_")
    filename = f"{safe_project}_{resource_type}_{safe_name}.tf"
    directory = _resolve_output_dir(output_dir)
    filepath = os.path.join(directory, filename)

    # Ensure directory exists (under the validated root).
    os.makedirs(directory, exist_ok=True)

    with open(filepath, "w") as f:
        f.write(hcl)

    _tf_log(f"Wrote {len(hcl)} chars to {filepath}")
    return f"File written: {filepath}\n\n{hcl}"


def _tf_log(message: str) -> None:
    print(f"[vpcsc-mcp] TOOL: {message}", file=sys.stderr, flush=True)


def _sanitise_hcl_string(value: str) -> str:
    """Escape characters that break HCL quoted strings.

    Also:
      - escapes ``${`` and ``%{`` so that attacker-controlled strings cannot
        inject Terraform interpolation or template directives (e.g.
        ``${file("/etc/passwd")}``). HCL escapes literal braces by doubling
        the leading sigil: ``$$`` and ``%%``.
      - runs the value through the input-filter stack with secret blocking
        enabled, so callers cannot smuggle OAuth tokens, PEM keys, or
        service-account-key JSON into generated HCL via ``title`` /
        ``description`` / ``resource`` / method fields. If the filter blocks
        the value, a safe placeholder is substituted so the generator does
        not fail closed on noisy input.
    """
    # Lazy import: input_filters depends on pyyaml which we only need at
    # generation time, and avoiding the import at module load keeps
    # terraform_gen importable in environments that skip yaml.
    from vpcsc_mcp.tools.input_filters import filter_text

    res = filter_text(value, field_name="hcl_value", block_secrets=True, redact_pii=True)
    if res.blocked:
        cleaned = f"[REJECTED:{res.reason or 'blocked'}]"
    else:
        cleaned = res.cleaned if isinstance(res.cleaned, str) else str(res.cleaned)

    return (
        cleaned.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("${", "$${")
        .replace("%{", "%%{")
    )


def _hcl_list(items: list[str], indent: int = 4) -> str:
    """Format a list of strings as HCL list. Each item is HCL-sanitised."""
    pad = " " * indent
    safe = [_sanitise_hcl_string(i) for i in items]
    if len(safe) <= 3:
        return "[" + ", ".join(f'"{i}"' for i in safe) + "]"
    inner = ",\n".join(f'{pad}  "{i}"' for i in safe)
    return f"[\n{inner},\n{pad}]"


_PROVIDER_BLOCK = textwrap.dedent("""\
    terraform {
      required_version = ">= 1.5"
      required_providers {
        google = {
          source  = "hashicorp/google"
          version = "~> 7.0"
        }
      }
    }

    provider "google" {
      project = "validation-only"
      region  = "europe-west2"
    }
    """)

_TF_TIMEOUT = 60  # seconds per terraform command


async def _run_tf(args: list[str], cwd: str) -> tuple[int, str, str]:
    """Run a terraform command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        "terraform", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TF_TIMEOUT)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return 1, "", f"terraform {args[0]} timed out after {_TF_TIMEOUT}s"
    return proc.returncode, stdout.decode(), stderr.decode()


def register_terraform_tools(mcp) -> None:
    """Register all Terraform generation tools on the FastMCP server."""

    from vpcsc_mcp.tools.safety import DIAGNOSTIC, GENERATE

    @mcp.tool(annotations=GENERATE)
    def generate_perimeter_terraform(
        name: str,
        policy_id: str,
        project_numbers: list[str],
        restricted_services: list[str],
        title: str | None = None,
        description: str | None = None,
        dry_run: bool = True,
        access_level_names: list[str] | None = None,
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate Terraform HCL for a VPC-SC regular service perimeter.

        Args:
            name: The perimeter name (alphanumeric and underscores).
            policy_id: The access policy ID (numeric).
            project_numbers: List of project numbers to include (just numbers, no 'projects/' prefix).
            restricted_services: List of GCP API services to restrict (e.g. 'storage.googleapis.com').
            title: Human-readable title. Defaults to name.
            description: Optional description of the perimeter and its purpose.
            dry_run: Whether to use dry-run mode (spec block). Default True.
            access_level_names: Optional list of access level names to allow.
            project_name: If set, writes HCL to {project_name}_perimeter_{name}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        # Validate inputs
        if not _TF_IDENTIFIER.match(name):
            return (
                f"Error: name '{name}' is not a valid Terraform identifier "
                "(use alphanumeric + underscores, start with letter)."
            )
        if not _NUMERIC.match(policy_id):
            return f"Error: policy_id '{policy_id}' must be numeric."
        for pn in project_numbers:
            if not _NUMERIC.match(pn):
                return f"Error: project number '{pn}' must be numeric (no 'projects/' prefix)."
        for svc in restricted_services:
            if not _SERVICE_API.match(svc):
                return f"Error: service '{svc}' must match format 'name.googleapis.com'."

        title = _sanitise_hcl_string(title or name)
        mode = "dry-run" if dry_run else "enforced"
        _tf_log(
            f"generate_perimeter_terraform({name}, {len(project_numbers)} projects, "
            f"{len(restricted_services)} services, {mode})"
        )
        resources_hcl = _hcl_list([f"projects/{p}" for p in project_numbers], indent=4)
        services_hcl = _hcl_list(restricted_services, indent=4)

        access_levels_block = ""
        if access_level_names:
            al_refs = [f"accessPolicies/{policy_id}/accessLevels/{al}" for al in access_level_names]
            access_levels_block = f"\n    access_levels       = {_hcl_list(al_refs, indent=4)}"

        block_type = "spec" if dry_run else "status"
        dry_run_line = '\n  use_explicit_dry_run_spec = true' if dry_run else ""

        desc_line = ""
        if description:
            desc_line = f'\n  description    = "{_sanitise_hcl_string(description)}"'

        hcl = textwrap.dedent(f"""\
        resource "google_access_context_manager_service_perimeter" "{name}" {{
          parent         = "accessPolicies/{policy_id}"
          name           = "accessPolicies/{policy_id}/servicePerimeters/{name}"
          title          = "{title}"{desc_line}
          perimeter_type = "PERIMETER_TYPE_REGULAR"{dry_run_line}

          {block_type} {{
            restricted_services = {services_hcl}
            resources           = {resources_hcl}{access_levels_block}
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "perimeter", name, output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_access_level_terraform(
        name: str,
        policy_id: str,
        title: str | None = None,
        ip_ranges: list[str] | None = None,
        members: list[str] | None = None,
        regions: list[str] | None = None,
        require_all: bool = True,
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate Terraform HCL for a VPC-SC access level.

        Args:
            name: The access level name (alphanumeric and underscores).
            policy_id: The access policy ID (numeric).
            title: Human-readable title. Defaults to name.
            ip_ranges: List of CIDR ranges to allow (e.g. '203.0.113.0/24').
            members: List of identity members (e.g. 'user:admin@example.com').
            regions: List of region codes (e.g. 'GB', 'US').
            require_all: If True, all conditions must be met (AND). If False, any (OR).
            project_name: If set, writes HCL to {project_name}_access_level_{name}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        title = title or name
        combining = "AND" if require_all else "OR"

        conditions_parts = []
        if ip_ranges:
            conditions_parts.append(f"      ip_subnetworks = {_hcl_list(ip_ranges, indent=6)}")
        if members:
            conditions_parts.append(f"      members = {_hcl_list(members, indent=6)}")
        if regions:
            conditions_parts.append(f"      regions = {_hcl_list(regions, indent=6)}")

        if not conditions_parts:
            return (
                "Error: at least one condition is required (ip_ranges, members, "
                "or regions). No default is generated to prevent accidental open access."
            )

        conditions_block = "\n".join(conditions_parts)

        hcl = textwrap.dedent(f"""\
        resource "google_access_context_manager_access_level" "{name}" {{
          parent = "accessPolicies/{policy_id}"
          name   = "accessPolicies/{policy_id}/accessLevels/{name}"
          title  = "{title}"

          basic {{
            combining_function = "{combining}"

            conditions {{
        {conditions_block}
            }}
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "access_level", name, output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_bridge_terraform(
        name: str,
        policy_id: str,
        project_numbers_a: list[str],
        project_numbers_b: list[str],
        title: str | None = None,
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate Terraform HCL for a VPC-SC bridge perimeter connecting two perimeters.

        Args:
            name: The bridge perimeter name.
            policy_id: The access policy ID (numeric).
            project_numbers_a: Project numbers from perimeter A.
            project_numbers_b: Project numbers from perimeter B.
            title: Human-readable title. Defaults to name.
            project_name: If set, writes HCL to {project_name}_bridge_{name}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        title = title or name
        all_projects = [f"projects/{p}" for p in project_numbers_a + project_numbers_b]
        resources_hcl = _hcl_list(all_projects, indent=4)

        hcl = textwrap.dedent(f"""\
        resource "google_access_context_manager_service_perimeter" "{name}" {{
          parent         = "accessPolicies/{policy_id}"
          name           = "accessPolicies/{policy_id}/servicePerimeters/{name}"
          title          = "{title}"
          perimeter_type = "PERIMETER_TYPE_BRIDGE"

          status {{
            resources = {resources_hcl}
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "bridge", name, output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_ingress_policy_terraform(
        service_name: str,
        method_selectors: list[dict[str, str]] | None = None,
        identity_type: str | None = None,
        identities: list[str] | None = None,
        source_project_numbers: list[str] | None = None,
        source_vpc_networks: list[str] | None = None,
        source_access_level: str | None = None,
        target_resources: list[str] | None = None,
        roles: list[str] | None = None,
        title: str = "Ingress Rule",
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate Terraform HCL for a VPC-SC ingress policy block.

        Args:
            service_name: The GCP service (e.g. 'bigquery.googleapis.com').
            method_selectors: List of {'method': '...'} or {'permission': '...'} dicts.
                Mutually exclusive with roles.
            identity_type: One of 'ANY_IDENTITY', 'ANY_USER_ACCOUNT',
                'ANY_SERVICE_ACCOUNT'. Mutually exclusive with identities.
            identities: Explicit identity list (e.g. 'serviceAccount:sa@project.iam.gserviceaccount.com').
            source_project_numbers: Source project numbers (without 'projects/' prefix).
            source_vpc_networks: Source VPC network resource names. Format:
                '//compute.googleapis.com/projects/{PROJECT_ID}/global/networks/{NAME}'.
            source_access_level: Full access level resource name.
            target_resources: Target resources (default ['*']).
            roles: IAM roles to allow (e.g. 'roles/bigquery.admin'). Alternative to
                method_selectors — simpler when granting broad access.
            title: Title for the ingress policy.
            project_name: If set, writes HCL to {project_name}_ingress_{title}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        target_resources = target_resources or ["*"]

        # Build ingress_from
        from_parts = []
        if identity_type:
            from_parts.append(f'      identity_type = "{identity_type}"')
        elif identities:
            from_parts.append(
                f"      identities = {_hcl_list(identities, indent=6)}"
            )
        else:
            from_parts.append('      identity_type = "ANY_IDENTITY"')

        sources = []
        if source_project_numbers:
            for pn in source_project_numbers:
                sources.append(f'        resource = "projects/{pn}"')
        if source_vpc_networks:
            for vpc in source_vpc_networks:
                sources.append(f'        resource = "{vpc}"')
        if source_access_level:
            sources.append(f'        access_level = "{source_access_level}"')

        sources_block = ""
        if sources:
            source_entries = "\n      }\n      sources {\n".join(sources)
            sources_block = (
                f"\n      sources {{\n{source_entries}\n      }}"
            )

        from_block = "\n".join(from_parts)

        # Build ingress_to
        targets_hcl = _hcl_list(target_resources, indent=6)
        to_parts = [f"        resources = {targets_hcl}"]

        # roles-based access (alternative to method_selectors)
        if roles:
            roles_hcl = _hcl_list(roles, indent=8)
            to_parts.append(f"        roles = {roles_hcl}")
        else:
            # method_selectors-based access
            selectors = method_selectors or [{"method": "*"}]
            method_lines = []
            for ms in selectors:
                if "method" in ms:
                    method_lines.append(
                        f'          method_selectors {{\n'
                        f'            method = "{ms["method"]}"\n'
                        f'          }}'
                    )
                elif "permission" in ms:
                    method_lines.append(
                        f'          method_selectors {{\n'
                        f'            permission = "{ms["permission"]}"\n'
                        f'          }}'
                    )
            methods_hcl = "\n".join(method_lines)
            to_parts.append(
                f'        operations {{\n'
                f'          service_name = "{service_name}"\n'
                f'{methods_hcl}\n'
                f'        }}'
            )

        to_block = "\n".join(to_parts)

        hcl = textwrap.dedent(f"""\
        # {title}
        ingress_policies {{
          title = "{title}"
          ingress_from {{
        {from_block}{sources_block}
          }}
          ingress_to {{
        {to_block}
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "ingress", title, output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_egress_policy_terraform(
        service_name: str,
        method_selectors: list[dict[str, str]] | None = None,
        identity_type: str | None = None,
        identities: list[str] | None = None,
        target_project_numbers: list[str] | None = None,
        target_resources: list[str] | None = None,
        external_resources: list[str] | None = None,
        source_project_numbers: list[str] | None = None,
        source_access_level: str | None = None,
        roles: list[str] | None = None,
        title: str = "Egress Rule",
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate Terraform HCL for a VPC-SC egress policy block.

        Args:
            service_name: The GCP service (e.g. 'storage.googleapis.com').
            method_selectors: List of {'method': '...'} or {'permission': '...'} dicts.
                Mutually exclusive with roles.
            identity_type: One of 'ANY_IDENTITY', 'ANY_USER_ACCOUNT',
                'ANY_SERVICE_ACCOUNT'. Mutually exclusive with identities.
            identities: Explicit identity list.
            target_project_numbers: Target project numbers (without 'projects/' prefix).
            target_resources: Target resources (overrides target_project_numbers if set).
            external_resources: Non-GCP target resources (e.g. 's3://bucket/path').
            source_project_numbers: Source project numbers inside the perimeter to
                restrict which projects can use this egress rule. Requires
                source_restriction to be set automatically.
            source_access_level: Access level restricting which sources inside the
                perimeter can use this egress rule.
            roles: IAM roles to allow (e.g. 'roles/bigquery.admin'). Alternative to
                method_selectors — simpler when granting broad access.
            title: Title for the egress policy.
            project_name: If set, writes HCL to {project_name}_egress_{title}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        if target_resources:
            targets = target_resources
        elif target_project_numbers:
            targets = [f"projects/{p}" for p in target_project_numbers]
        else:
            targets = ["*"]

        # Build egress_from
        from_parts = []
        if identity_type:
            from_parts.append(f'      identity_type = "{identity_type}"')
        elif identities:
            from_parts.append(
                f"      identities = {_hcl_list(identities, indent=6)}"
            )
        else:
            from_parts.append('      identity_type = "ANY_IDENTITY"')

        # egress_from.sources + source_restriction (provider >= 5.x)
        if source_project_numbers or source_access_level:
            from_parts.append(
                '      source_restriction = "SOURCE_RESTRICTION_ENABLED"'
            )
            if source_project_numbers:
                for pn in source_project_numbers:
                    from_parts.append(
                        f"      sources {{\n"
                        f'        resource = "projects/{pn}"\n'
                        f"      }}"
                    )
            if source_access_level:
                from_parts.append(
                    f"      sources {{\n"
                    f'        access_level = "{source_access_level}"\n'
                    f"      }}"
                )

        from_block = "\n".join(from_parts)

        # Build egress_to
        targets_hcl = _hcl_list(targets, indent=6)
        to_parts = [f"        resources = {targets_hcl}"]

        # external_resources (cross-cloud, e.g. s3://)
        if external_resources:
            ext_hcl = _hcl_list(external_resources, indent=8)
            to_parts.append(f"        external_resources = {ext_hcl}")

        # roles-based access (alternative to method_selectors)
        if roles:
            roles_hcl = _hcl_list(roles, indent=8)
            to_parts.append(f"        roles = {roles_hcl}")
        else:
            # method_selectors-based access
            selectors = method_selectors or [{"method": "*"}]
            method_lines = []
            for ms in selectors:
                if "method" in ms:
                    method_lines.append(
                        f'          method_selectors {{\n'
                        f'            method = "{ms["method"]}"\n'
                        f'          }}'
                    )
                elif "permission" in ms:
                    method_lines.append(
                        f'          method_selectors {{\n'
                        f'            permission = "{ms["permission"]}"\n'
                        f'          }}'
                    )
            methods_hcl = "\n".join(method_lines)
            to_parts.append(
                f'        operations {{\n'
                f'          service_name = "{service_name}"\n'
                f'{methods_hcl}\n'
                f'        }}'
            )

        to_block = "\n".join(to_parts)

        hcl = textwrap.dedent(f"""\
        # {title}
        egress_policies {{
          title = "{title}"
          egress_from {{
        {from_block}
          }}
          egress_to {{
        {to_block}
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "egress", title, output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_vpc_accessible_services_terraform(
        allowed_services: list[str],
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate Terraform HCL for the vpc_accessible_services block.

        Args:
            allowed_services: Services accessible from VPCs inside the perimeter. Use ['*'] for all.
            project_name: If set, writes HCL to {project_name}_vpc_accessible_services.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        if allowed_services == ["*"]:
            hcl = textwrap.dedent("""\
            # VPC Accessible Services: all services allowed
            # vpc_accessible_services block is omitted when allowing all services.
            # To restrict, specify an explicit list of services.
            """)
        else:
            services_hcl = _hcl_list(allowed_services, indent=6)
            hcl = textwrap.dedent(f"""\
            vpc_accessible_services {{
              enable_restriction = true
              allowed_services   = {services_hcl}
            }}
            """)
        return _maybe_write_hcl(hcl, project_name, "vpc_accessible_services", "config", output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_standalone_ingress_policy_terraform(
        perimeter_resource_name: str,
        service_name: str,
        method_selectors: list[dict[str, str]] | None = None,
        identity_type: str | None = None,
        identities: list[str] | None = None,
        source_access_level: str | None = None,
        source_project_numbers: list[str] | None = None,
        roles: list[str] | None = None,
        title: str = "Ingress Rule",
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate a standalone ingress policy Terraform resource.

        Uses google_access_context_manager_service_perimeter_ingress_policy,
        which manages a single ingress rule independently of the perimeter
        resource. This is preferred over inline ingress_policies blocks for
        easier lifecycle management.

        Note: When using standalone policies, add a lifecycle ignore_changes
        block to the perimeter resource for status[0].ingress_policies.

        Args:
            perimeter_resource_name: Full perimeter resource name
                (e.g. 'accessPolicies/123/servicePerimeters/my_perimeter').
            service_name: The GCP service (e.g. 'bigquery.googleapis.com').
            method_selectors: List of {'method': '...'} or {'permission': '...'}
                dicts. Mutually exclusive with roles.
            identity_type: One of 'ANY_IDENTITY', 'ANY_USER_ACCOUNT',
                'ANY_SERVICE_ACCOUNT'. Mutually exclusive with identities.
            identities: Explicit identity list.
            source_access_level: Full access level resource name.
            source_project_numbers: Source project numbers.
            roles: IAM roles to allow. Alternative to method_selectors.
            title: Title for the ingress policy.
            project_name: If set, writes HCL to {project_name}_ingress_policy_{title}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        safe_title = title.lower().replace(" ", "_").replace("-", "_")
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", safe_title)

        from_lines = []
        if identity_type:
            from_lines.append(f'    identity_type = "{identity_type}"')
        elif identities:
            from_lines.append(
                f"    identities = {_hcl_list(identities, indent=4)}"
            )
        if source_access_level:
            from_lines.append(
                f"    sources {{\n"
                f'      access_level = "{source_access_level}"\n'
                f"    }}"
            )
        if source_project_numbers:
            for pn in source_project_numbers:
                from_lines.append(
                    f"    sources {{\n"
                    f'      resource = "projects/{pn}"\n'
                    f"    }}"
                )
        from_block = "\n".join(from_lines)

        # Build ingress_to
        to_lines = ['    resources = ["*"]']
        if roles:
            roles_hcl = _hcl_list(roles, indent=4)
            to_lines.append(f"    roles = {roles_hcl}")
        else:
            selectors = method_selectors or [{"method": "*"}]
            ms_lines = []
            for ms in selectors:
                if "method" in ms:
                    ms_lines.append(
                        f'      method_selectors {{\n'
                        f'        method = "{ms["method"]}"\n'
                        f'      }}'
                    )
                elif "permission" in ms:
                    ms_lines.append(
                        f'      method_selectors {{\n'
                        f'        permission = "{ms["permission"]}"\n'
                        f'      }}'
                    )
            ms_block = "\n".join(ms_lines)
            to_lines.append(
                f'    operations {{\n'
                f'      service_name = "{service_name}"\n'
                f'{ms_block}\n'
                f'    }}'
            )
        to_block = "\n".join(to_lines)

        hcl = textwrap.dedent(f"""\
        resource "google_access_context_manager_service_perimeter_ingress_policy" "{safe_name}" {{
          perimeter = "{perimeter_resource_name}"
          title     = "{_sanitise_hcl_string(title)}"

          ingress_from {{
        {from_block}
          }}

          ingress_to {{
        {to_block}
          }}

          lifecycle {{
            create_before_destroy = true
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "ingress_policy", title, output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_standalone_egress_policy_terraform(
        perimeter_resource_name: str,
        service_name: str,
        method_selectors: list[dict[str, str]] | None = None,
        identity_type: str | None = None,
        identities: list[str] | None = None,
        target_project_numbers: list[str] | None = None,
        external_resources: list[str] | None = None,
        roles: list[str] | None = None,
        title: str = "Egress Rule",
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate a standalone egress policy Terraform resource.

        Uses google_access_context_manager_service_perimeter_egress_policy,
        which manages a single egress rule independently of the perimeter
        resource. This is preferred over inline egress_policies blocks for
        easier lifecycle management.

        Note: When using standalone policies, add a lifecycle ignore_changes
        block to the perimeter resource for status[0].egress_policies.

        Args:
            perimeter_resource_name: Full perimeter resource name
                (e.g. 'accessPolicies/123/servicePerimeters/my_perimeter').
            service_name: The GCP service (e.g. 'storage.googleapis.com').
            method_selectors: List of {'method': '...'} or {'permission': '...'}
                dicts. Mutually exclusive with roles.
            identity_type: One of 'ANY_IDENTITY', 'ANY_USER_ACCOUNT',
                'ANY_SERVICE_ACCOUNT'. Mutually exclusive with identities.
            identities: Explicit identity list.
            target_project_numbers: Target project numbers.
            external_resources: Non-GCP target resources (e.g. 's3://bucket/path').
            roles: IAM roles to allow. Alternative to method_selectors.
            title: Title for the egress policy.
            project_name: If set, writes HCL to {project_name}_egress_policy_{title}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        safe_title = title.lower().replace(" ", "_").replace("-", "_")
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", safe_title)

        from_lines = []
        if identity_type:
            from_lines.append(f'    identity_type = "{identity_type}"')
        elif identities:
            from_lines.append(
                f"    identities = {_hcl_list(identities, indent=4)}"
            )
        else:
            from_lines.append('    identity_type = "ANY_IDENTITY"')
        from_block = "\n".join(from_lines)

        # Build egress_to
        if target_project_numbers:
            targets = [f"projects/{p}" for p in target_project_numbers]
        else:
            targets = ["*"]
        targets_hcl = _hcl_list(targets, indent=4)

        to_lines = [f"    resources = {targets_hcl}"]
        if external_resources:
            ext_hcl = _hcl_list(external_resources, indent=4)
            to_lines.append(f"    external_resources = {ext_hcl}")
        if roles:
            roles_hcl = _hcl_list(roles, indent=4)
            to_lines.append(f"    roles = {roles_hcl}")
        else:
            selectors = method_selectors or [{"method": "*"}]
            ms_lines = []
            for ms in selectors:
                if "method" in ms:
                    ms_lines.append(
                        f'      method_selectors {{\n'
                        f'        method = "{ms["method"]}"\n'
                        f'      }}'
                    )
                elif "permission" in ms:
                    ms_lines.append(
                        f'      method_selectors {{\n'
                        f'        permission = "{ms["permission"]}"\n'
                        f'      }}'
                    )
            ms_block = "\n".join(ms_lines)
            to_lines.append(
                f'    operations {{\n'
                f'      service_name = "{service_name}"\n'
                f'{ms_block}\n'
                f'    }}'
            )
        to_block = "\n".join(to_lines)

        hcl = textwrap.dedent(f"""\
        resource "google_access_context_manager_service_perimeter_egress_policy" "{safe_name}" {{
          perimeter = "{perimeter_resource_name}"
          title     = "{_sanitise_hcl_string(title)}"

          egress_from {{
        {from_block}
          }}

          egress_to {{
        {to_block}
          }}

          lifecycle {{
            create_before_destroy = true
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "egress_policy", title, output_dir)

    @mcp.tool(annotations=GENERATE)
    def generate_full_perimeter_terraform(
        name: str,
        policy_id: str,
        project_numbers: list[str],
        restricted_services: list[str],
        title: str | None = None,
        dry_run: bool = True,
        access_level_names: list[str] | None = None,
        ingress_rules_json: str | None = None,
        egress_rules_json: str | None = None,
        project_name: str | None = None,
        output_dir: str | None = None,
    ) -> str:
        """Generate a complete Terraform perimeter with inline ingress/egress policies.

        Args:
            name: The perimeter name.
            policy_id: The access policy ID (numeric).
            project_numbers: Project numbers to include.
            restricted_services: Services to restrict.
            title: Human-readable title. Defaults to name.
            dry_run: Use dry-run mode. Default True.
            access_level_names: Access level names to allow.
            ingress_rules_json: JSON array of ingress rules, each with: title,
                identity_type or identities, sources, service_name,
                method_selectors.
            egress_rules_json: JSON array of egress rules, each with: title,
                identity_type or identities, targets, service_name,
                method_selectors.
            project_name: If set, writes HCL to {project_name}_perimeter_full_{name}.tf in output_dir.
            output_dir: Directory for output file. Defaults to current working directory.
        """
        title = title or name
        resources_hcl = _hcl_list([f"projects/{p}" for p in project_numbers], indent=4)
        services_hcl = _hcl_list(restricted_services, indent=4)

        access_levels_block = ""
        if access_level_names:
            al_refs = [f"accessPolicies/{policy_id}/accessLevels/{al}" for al in access_level_names]
            access_levels_block = f"\n    access_levels       = {_hcl_list(al_refs, indent=4)}"

        block_type = "spec" if dry_run else "status"
        dry_run_line = '\n  use_explicit_dry_run_spec = true' if dry_run else ""

        # Parse and build ingress policies
        ingress_blocks = ""
        if ingress_rules_json:
            try:
                ingress_rules = json.loads(ingress_rules_json)
                parts = []
                for rule in ingress_rules:
                    parts.append(_build_ingress_hcl(rule))
                ingress_blocks = "\n" + "\n".join(parts)
            except (json.JSONDecodeError, KeyError) as e:
                ingress_blocks = f"\n    # Error parsing ingress rules: {e}"

        # Parse and build egress policies
        egress_blocks = ""
        if egress_rules_json:
            try:
                egress_rules = json.loads(egress_rules_json)
                parts = []
                for rule in egress_rules:
                    parts.append(_build_egress_hcl(rule))
                egress_blocks = "\n" + "\n".join(parts)
            except (json.JSONDecodeError, KeyError) as e:
                egress_blocks = f"\n    # Error parsing egress rules: {e}"

        hcl = textwrap.dedent(f"""\
        resource "google_access_context_manager_service_perimeter" "{name}" {{
          parent         = "accessPolicies/{policy_id}"
          name           = "accessPolicies/{policy_id}/servicePerimeters/{name}"
          title          = "{title}"
          perimeter_type = "PERIMETER_TYPE_REGULAR"{dry_run_line}

          {block_type} {{
            restricted_services = {services_hcl}
            resources           = {resources_hcl}{access_levels_block}
        {ingress_blocks}{egress_blocks}
          }}
        }}
        """)
        return _maybe_write_hcl(hcl, project_name, "perimeter_full", name, output_dir)


    @mcp.tool(annotations=DIAGNOSTIC)
    async def validate_terraform(hcl_code: str) -> str:
        """Validate Terraform HCL code by running terraform init and terraform validate.

        Writes the code to a temporary directory, adds a Google provider block,
        runs terraform init + validate, and returns the result. The temp directory
        is deleted after validation.

        Args:
            hcl_code: The Terraform HCL code to validate. Can be a full resource block or multiple blocks.
        """
        tf_path = shutil.which("terraform")
        if not tf_path:
            return (
                "Error: terraform CLI not found on PATH.\n"
                "Install Terraform: https://developer.hashicorp.com/terraform/install"
            )

        _tf_log(f"validate_terraform({len(hcl_code)} chars)")

        tmpdir = tempfile.mkdtemp(prefix="vpcsc_mcp_validate_")
        try:
            # Write provider config
            with open(os.path.join(tmpdir, "provider.tf"), "w") as f:
                f.write(_PROVIDER_BLOCK)

            # Write the user's HCL
            with open(os.path.join(tmpdir, "main.tf"), "w") as f:
                f.write(hcl_code)

            lines = []

            # terraform init
            _tf_log("Running terraform init...")
            rc, stdout, stderr = await _run_tf(["init", "-backend=false", "-no-color"], tmpdir)
            if rc != 0:
                init_err = stderr.strip() or stdout.strip()
                lines.append("INIT FAILED:")
                lines.append(init_err[:2000])
                return "\n".join(lines)

            lines.append("INIT: OK")

            # terraform validate
            _tf_log("Running terraform validate...")
            rc, stdout, stderr = await _run_tf(["validate", "-no-color"], tmpdir)

            if rc == 0:
                lines.append("VALIDATE: OK")
                # Parse the JSON output if available
                try:
                    rc_json, stdout_json, _ = await _run_tf(["validate", "-json", "-no-color"], tmpdir)
                    result = json.loads(stdout_json)
                    if result.get("valid"):
                        lines.append("\nTerraform validated successfully.")
                        lines.append(f"  Format version: {result.get('format_version', 'N/A')}")
                except (json.JSONDecodeError, Exception):
                    pass
            else:
                lines.append("VALIDATE: FAILED")
                # Parse structured errors if possible
                try:
                    rc_json, stdout_json, _ = await _run_tf(["validate", "-json", "-no-color"], tmpdir)
                    result = json.loads(stdout_json)
                    for diag in result.get("diagnostics", []):
                        severity = diag.get("severity", "error").upper()
                        summary = diag.get("summary", "Unknown error")
                        detail = diag.get("detail", "")
                        snippet = diag.get("snippet", {})
                        context = snippet.get("context", "")
                        code = snippet.get("code", "")

                        lines.append(f"\n  {severity}: {summary}")
                        if detail:
                            lines.append(f"  Detail: {detail[:500]}")
                        if context:
                            lines.append(f"  Context: {context}")
                        if code:
                            lines.append(f"  Code: {code[:200]}")
                except (json.JSONDecodeError, Exception):
                    # Fall back to raw stderr
                    lines.append(stderr.strip()[:2000])

            # terraform fmt -check (style check, non-blocking)
            _tf_log("Running terraform fmt -check...")
            rc_fmt, stdout_fmt, _ = await _run_tf(["fmt", "-check", "-no-color", "-diff"], tmpdir)
            if rc_fmt == 0:
                lines.append("\nFORMAT: OK (correctly formatted)")
            else:
                lines.append("\nFORMAT: Needs formatting (non-blocking)")
                if stdout_fmt.strip():
                    lines.append("  Suggested diff:")
                    for diff_line in stdout_fmt.strip().splitlines()[:20]:
                        lines.append(f"    {diff_line}")

            return "\n".join(lines)

        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
            _tf_log("Cleaned up temp directory")


def _build_ingress_hcl(rule: dict) -> str:
    """Build an ingress_policies HCL block from a rule dict.

    All values interpolated into HCL strings are passed through
    ``_sanitise_hcl_string`` to prevent quote breakout and Terraform
    interpolation injection (``${}`` / ``%{}``).
    """
    s = _sanitise_hcl_string
    title = s(str(rule.get("title", "Ingress Rule")))
    lines = ['    ingress_policies {', f'      title = "{title}"', "      ingress_from {"]

    if "identity_type" in rule:
        lines.append(f'        identity_type = "{s(str(rule["identity_type"]))}"')
    elif "identities" in rule:
        lines.append(f"        identities = {_hcl_list(rule['identities'], indent=8)}")

    for src in rule.get("sources", []):
        lines.append("        sources {")
        if "resource" in src:
            lines.append(f'          resource = "{s(str(src["resource"]))}"')
        if "access_level" in src:
            lines.append(f'          access_level = "{s(str(src["access_level"]))}"')
        lines.append("        }")

    lines.append("      }")
    lines.append("      ingress_to {")
    targets = rule.get("target_resources", ["*"])
    lines.append(f"        resources = {_hcl_list(targets, indent=8)}")

    for op in rule.get("operations", []):
        lines.append("        operations {")
        lines.append(f'          service_name = "{s(str(op["service_name"]))}"')
        for ms in op.get("method_selectors", []):
            lines.append("          method_selectors {")
            if "method" in ms:
                lines.append(f'            method = "{s(str(ms["method"]))}"')
            elif "permission" in ms:
                lines.append(f'            permission = "{s(str(ms["permission"]))}"')
            lines.append("          }")
        lines.append("        }")

    lines.append("      }")
    lines.append("    }")
    return "\n".join(lines)


def _build_egress_hcl(rule: dict) -> str:
    """Build an egress_policies HCL block from a rule dict.

    All values interpolated into HCL strings are HCL-sanitised.
    """
    s = _sanitise_hcl_string
    title = s(str(rule.get("title", "Egress Rule")))
    lines = ['    egress_policies {', f'      title = "{title}"', "      egress_from {"]

    if "identity_type" in rule:
        lines.append(f'        identity_type = "{s(str(rule["identity_type"]))}"')
    elif "identities" in rule:
        lines.append(f"        identities = {_hcl_list(rule['identities'], indent=8)}")

    lines.append("      }")
    lines.append("      egress_to {")
    targets = rule.get("target_resources", ["*"])
    lines.append(f"        resources = {_hcl_list(targets, indent=8)}")

    for op in rule.get("operations", []):
        lines.append("        operations {")
        lines.append(f'          service_name = "{s(str(op["service_name"]))}"')
        for ms in op.get("method_selectors", []):
            lines.append("          method_selectors {")
            if "method" in ms:
                lines.append(f'            method = "{s(str(ms["method"]))}"')
            elif "permission" in ms:
                lines.append(f'            permission = "{s(str(ms["permission"]))}"')
            lines.append("          }")
        lines.append("        }")

    lines.append("      }")
    lines.append("    }")
    return "\n".join(lines)
