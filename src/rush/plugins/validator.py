"""Strict Schema Validator for Plugin JSON Output.

Architecture §8, Phase 28.
Ensures external plugins conform to the canonical ToolResult schema.
"""

from __future__ import annotations

import json
from typing import Any

from rush.logging import get_logger, log_subsystem
from rush.tools.base import Finding, ToolResult

logger = get_logger("plugins.validator")

REQUIRED_KEYS = {"tool", "status", "summary"}
VALID_STATUSES = {"ok", "warn", "fail", "skipped", "error"}


def validate_plugin_output(raw_output: str, plugin_name: str) -> ToolResult:
    """Parse and validate plugin stdout against canonical ToolResult schema."""
    try:
        data: dict[str, Any] = json.loads(raw_output.strip())
    except json.JSONDecodeError as exc:
        log_subsystem(
            "plugin",
            "ERROR",
            f"Plugin '{plugin_name}' emitted invalid JSON: {exc}",
        )
        return ToolResult(
            tool=plugin_name,
            status="error",
            duration_ms=0,
            summary=f"plugin: Invalid JSON output from {plugin_name} - {exc}",
            findings=[],
        )

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        log_subsystem(
            "plugin",
            "ERROR",
            f"Plugin '{plugin_name}' missing required keys: {sorted(missing)}",
        )
        return ToolResult(
            tool=plugin_name,
            status="error",
            duration_ms=0,
            summary=f"plugin: Missing required keys {sorted(missing)} in {plugin_name}",
            findings=[],
        )

    status = data.get("status")
    if status not in VALID_STATUSES:
        status = "error"

    raw_findings = data.get("findings", [])
    findings: list[Finding] = []
    if isinstance(raw_findings, list):
        for f in raw_findings:
            if isinstance(f, dict):
                findings.append(
                    Finding(
                        file=str(f.get("file", "")),
                        line=int(f.get("line", 0)) if f.get("line") else None,
                        column=int(f.get("column", 0)) if f.get("column") else None,
                        rule=str(f.get("rule", "")),
                        message=str(f.get("message", "")),
                        severity=str(f.get("severity", "info")),  # type: ignore[arg-type]
                    )
                )

    return ToolResult(
        tool=str(data.get("tool", plugin_name)),
        engine=data.get("engine", "custom-plugin"),
        engine_version=data.get("engine_version", "1.0.0"),
        status=status,  # type: ignore[arg-type]
        duration_ms=int(data.get("duration_ms", 0)),
        summary=str(data.get("summary", "")),
        findings=findings,
    )
