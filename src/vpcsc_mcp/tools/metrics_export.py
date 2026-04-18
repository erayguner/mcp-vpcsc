"""Optional OpenTelemetry / Cloud Monitoring metrics exporter.

Wires ToolMetrics.record to an OTel MeterProvider when available. Enabled
per AGENT_GOVERNANCE_FRAMEWORK §9.1 (named sinks — Cloud Monitoring) and
§9.2 (call-rate / tool-distribution signals).

Enable by setting:
  VPCSC_MCP_METRICS_EXPORT=otel-cloudmon   # Cloud Monitoring via OTel
  VPCSC_MCP_METRICS_EXPORT=otel-stdout     # stdout exporter (debug)

Silent no-op if the env var is unset or OTel packages are absent — the
project does not add these to the required-dep set.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_EXPORT_ENV = "VPCSC_MCP_METRICS_EXPORT"


def install_metrics_exporter(metrics_registry: Any) -> bool:
    """Attach an OTel exporter to the ToolMetrics instance, if configured.

    Returns True if an exporter was installed, False otherwise.
    """
    mode = os.environ.get(_EXPORT_ENV, "").strip().lower()
    if not mode:
        return False
    try:
        from opentelemetry import metrics as ot_metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    except ImportError:
        logger.warning(
            "VPCSC_MCP_METRICS_EXPORT=%s but opentelemetry-sdk is not installed; "
            "install opentelemetry-sdk (and exporter-gcp-monitoring for Cloud Monitoring)",
            mode,
        )
        return False

    exporter = _build_exporter(mode)
    if exporter is None:
        return False

    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=60_000)
    provider = MeterProvider(metric_readers=[reader])
    ot_metrics.set_meter_provider(provider)
    meter = ot_metrics.get_meter("vpcsc_mcp")

    call_counter = meter.create_counter(
        "vpcsc_mcp.tool_calls",
        description="Total tool calls by tool, principal, outcome",
    )
    duration_histogram = meter.create_histogram(
        "vpcsc_mcp.tool_duration_ms",
        description="Tool call duration in milliseconds",
        unit="ms",
    )

    def export(
        tool: str, duration_ms: float, success: bool, cached: bool, principal: str,
    ) -> None:
        attrs = {
            "tool": tool,
            "principal": principal,
            "success": str(success).lower(),
            "cached": str(cached).lower(),
        }
        call_counter.add(1, attrs)
        duration_histogram.record(duration_ms, attrs)

    metrics_registry.attach_exporter(export)
    logger.info("OTel metrics exporter installed (mode=%s)", mode)
    return True


def _build_exporter(mode: str):
    if mode == "otel-stdout":
        try:
            from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
            return ConsoleMetricExporter()
        except ImportError:
            return None
    if mode == "otel-cloudmon":
        try:
            from opentelemetry.exporter.cloud_monitoring import (
                CloudMonitoringMetricsExporter,
            )
            project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
            return CloudMonitoringMetricsExporter(project_id=project_id)
        except ImportError:
            logger.warning(
                "otel-cloudmon requested but opentelemetry-exporter-gcp-monitoring "
                "is not installed",
            )
            return None
    logger.warning("Unknown %s value: %r", _EXPORT_ENV, mode)
    return None
