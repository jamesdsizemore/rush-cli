"""Contained normalization for local structured IaC scanner reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..tools.base import Finding, Severity


class StructuredIacReportError(ValueError):
    """Raised when a report cannot safely map to contained local findings."""


def parse_structured_iac_report(payload: str, project_root: Path) -> list[Finding]:
    """Parse Checkov-like JSON or SARIF-like findings under ``project_root``.

    This parser intentionally has no scanner-specific invocation behavior. Callers
    must translate this exception to the canonical malformed-output result.
    """
    try:
        report = json.loads(payload)
    except json.JSONDecodeError as error:
        raise StructuredIacReportError("report is not valid JSON") from error

    root = project_root.resolve()
    if not isinstance(report, dict):
        raise StructuredIacReportError("report root must be an object")
    if "runs" in report:
        return _parse_sarif_runs(report["runs"], root)
    if "results" in report:
        return _parse_json_results(report["results"], root)
    raise StructuredIacReportError("report has no supported results collection")


def _parse_json_results(results: Any, root: Path) -> list[Finding]:
    if not isinstance(results, list):
        raise StructuredIacReportError("report results must be a list")
    findings: list[Finding] = []
    for item in results:
        if not isinstance(item, dict):
            raise StructuredIacReportError("report result must be an object")
        findings.append(
            {
                "path": str(_contained_path(item.get("file_path"), root)),
                "line": _line_number(item.get("file_line_range")),
                "rule": _text(item.get("check_id"), "unknown-iac-rule"),
                "severity": _severity(item.get("severity")),
                "message": _text(item.get("check_name"), "IaC policy finding"),
            }
        )
    return findings


def _parse_sarif_runs(runs: Any, root: Path) -> list[Finding]:
    if not isinstance(runs, list):
        raise StructuredIacReportError("SARIF runs must be a list")
    findings: list[Finding] = []
    for run in runs:
        if not isinstance(run, dict) or not isinstance(run.get("results"), list):
            raise StructuredIacReportError("SARIF run results must be a list")
        for item in run["results"]:
            if not isinstance(item, dict):
                raise StructuredIacReportError("SARIF result must be an object")
            location = _sarif_location(item)
            findings.append(
                {
                    "path": str(_contained_path(location.get("uri"), root)),
                    "line": _line_number(location.get("line")),
                    "rule": _text(item.get("ruleId"), "unknown-iac-rule"),
                    "severity": _severity(item.get("level")),
                    "message": _message_text(item.get("message")),
                }
            )
    return findings


def _sarif_location(item: dict[str, Any]) -> dict[str, Any]:
    locations = item.get("locations")
    if (
        not isinstance(locations, list)
        or not locations
        or not isinstance(locations[0], dict)
    ):
        raise StructuredIacReportError("SARIF finding has no location")
    physical = locations[0].get("physicalLocation")
    if not isinstance(physical, dict):
        raise StructuredIacReportError("SARIF finding has no physical location")
    artifact = physical.get("artifactLocation")
    region = physical.get("region", {})
    if not isinstance(artifact, dict) or not isinstance(region, dict):
        raise StructuredIacReportError("SARIF finding location is malformed")
    return {"uri": artifact.get("uri"), "line": region.get("startLine")}


def _contained_path(value: Any, root: Path) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise StructuredIacReportError("finding has no file path")
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise StructuredIacReportError("finding path escapes the project root")
    return resolved


def _line_number(value: Any) -> int:
    if isinstance(value, list):
        value = value[0] if value else None
    if not isinstance(value, int) or value < 1:
        raise StructuredIacReportError("finding has no valid line number")
    return value


def _text(value: Any, default: str) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else default


def _message_text(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("text")
    return _text(value, "IaC policy finding")


def _severity(value: Any) -> Severity:
    normalized = str(value).lower()
    if normalized in {"critical", "error", "high"}:
        return "error"
    if normalized in {"warning", "warn", "medium"}:
        return "warn"
    return "info"
