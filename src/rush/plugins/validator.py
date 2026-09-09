"""Strict Schema Validator for Plugin JSON Output.

Architecture §8, Phase 28 & Phase 56.
Ensures external plugins conform to the canonical ToolResultV1 schema.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from rush.contracts.results import (
    FindingSeverity,
    FindingV1,
    ToolResultV1,
    validate_tool_result,
)
from rush.logging import get_logger, log_subsystem
from rush.tools.base import ToolStatus

logger = get_logger("plugins.validator")

REQUIRED_KEYS = {"tool", "status", "summary"}
VALID_STATUSES = {"ok", "warn", "fail", "skipped", "error"}


def validate_plugin_output(raw_output: str, plugin_name: str) -> ToolResultV1:
    """Parse and validate plugin stdout against canonical ToolResultV1 schema."""
    try:
        data: dict[str, Any] = json.loads(raw_output.strip())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log_subsystem(
            "plugin",
            "ERROR",
            f"Plugin '{plugin_name}' emitted invalid JSON: {exc}",
        )
        return ToolResultV1(
            schema_version="1.0.0",
            tool=plugin_name,
            engine=plugin_name,
            engine_version="1.0.0",
            status="error",
            duration_ms=0,
            summary=f"plugin: Invalid JSON output from {plugin_name} - {exc}",
            findings=[],
        )

    if not isinstance(data, dict):
        return ToolResultV1(
            schema_version="1.0.0",
            tool=plugin_name,
            engine=plugin_name,
            engine_version="1.0.0",
            status="error",
            duration_ms=0,
            summary=f"plugin: Output from {plugin_name} must be a JSON object",
            findings=[],
        )

    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        log_subsystem(
            "plugin",
            "ERROR",
            f"Plugin '{plugin_name}' missing required keys: {sorted(missing)}",
        )
        return ToolResultV1(
            schema_version="1.0.0",
            tool=plugin_name,
            engine=plugin_name,
            engine_version="1.0.0",
            status="error",
            duration_ms=0,
            summary=f"plugin: Missing required keys {sorted(missing)} in {plugin_name}",
            findings=[],
        )

    if data.get("schema_version") == "1.0.0":
        try:
            return validate_tool_result(data)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Direct ToolResultV1 validation failed, falling back: %s", exc)

    status: ToolStatus = data["status"]
    if status not in VALID_STATUSES:
        status = "error"

    raw_findings = data.get("findings", [])
    findings: list[FindingV1] = []
    if isinstance(raw_findings, list):
        for f in raw_findings:
            if isinstance(f, dict):
                path_str = str(f.get("path") or f.get("file", ""))
                line_val = int(f.get("line", 1)) if f.get("line") else 1
                col_val = int(f.get("column", 1)) if f.get("column") else 1
                rule_id_str = str(f.get("rule_id") or f.get("rule", "plugin-finding"))
                sev_raw = str(f.get("severity", "info")).lower()
                sev: FindingSeverity = (
                    "warning"
                    if sev_raw in ("warn", "warning")
                    else ("error" if sev_raw == "error" else "info")
                )
                msg = str(f.get("message", ""))
                fp_seed = (
                    f"{plugin_name}:{path_str}:{line_val}:{col_val}:{rule_id_str}:{msg}"
                )
                fp = str(
                    f.get("fingerprint")
                    or hashlib.sha256(fp_seed.encode("utf-8")).hexdigest()
                )
                findings.append(
                    FindingV1(
                        path=path_str,
                        line=line_val,
                        column=col_val,
                        rule_id=rule_id_str,
                        severity=sev,
                        message=msg,
                        fingerprint=fp,
                    )
                )

    return ToolResultV1(
        schema_version="1.0.0",
        tool=str(data.get("tool", plugin_name)),
        engine=str(data.get("engine", plugin_name)),
        engine_version=str(data.get("engine_version", "1.0.0")),
        status=status,
        duration_ms=int(data.get("duration_ms", 0)),
        summary=str(data.get("summary", "")),
        findings=findings,
    )
