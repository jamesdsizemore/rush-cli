"""SARIF 2.1.0 export utilities for Rush findings.

Converts canonical ToolResult and Finding objects into standard SARIF 2.1.0
JSON format compatible with GitHub Code Scanning, IDEs, and security dashboards.
"""

from __future__ import annotations

from typing import Any

from .tools.base import Finding, ToolResult


def finding_to_sarif_result(
    finding: Finding | dict[str, Any],
    default_tool: str = "rush",
) -> dict[str, Any]:
    """Convert a single Finding into a SARIF 2.1.0 result object."""
    rule_id = finding.get("rule", "general")
    message = finding.get("message", "")
    path = finding.get("path", "")
    line = finding.get("line") or 1
    severity = finding.get("severity", "warn")

    # Map Rush severity to SARIF level (error, warning, note, none)
    level_map = {
        "fail": "error",
        "error": "error",
        "warn": "warning",
        "warning": "warning",
        "info": "note",
    }
    level = level_map.get(severity, "warning")

    sarif_result: dict[str, Any] = {
        "ruleId": rule_id,
        "level": level,
        "message": {"text": message},
        "locations": [
            {
                "physicalLocation": {
                    "artifactLocation": {
                        "uri": path.replace("\\", "/") if path else "workspace",
                    },
                    "region": {
                        "startLine": max(1, line),
                    },
                }
            }
        ],
    }

    if finding.get("fix"):
        sarif_result["fixes"] = [
            {
                "description": {"text": f"Suggested fix for {rule_id}"},
                "changes": [
                    {
                        "replacement": {
                            "text": finding["fix"],
                        }
                    }
                ],
            }
        ]

    return sarif_result


def export_to_sarif(
    results: ToolResult | list[ToolResult],
    *,
    tool_name: str = "rush",
    version: str = "0.2.0",
) -> dict[str, Any]:
    """Export one or more ToolResults to a complete SARIF 2.1.0 document."""
    if isinstance(results, dict):
        results_list = [results]
    else:
        results_list = list(results)

    runs: list[dict[str, Any]] = []

    for res in results_list:
        driver_name = res.get("engine") or res.get("tool") or tool_name
        driver_version = res.get("engine_version") or version
        findings = res.get("findings", [])

        rules_dict: dict[str, dict[str, Any]] = {}
        sarif_findings: list[dict[str, Any]] = []

        for f in findings:
            sarif_f = finding_to_sarif_result(f, default_tool=driver_name)
            sarif_findings.append(sarif_f)
            rule_id = sarif_f["ruleId"]
            if rule_id not in rules_dict:
                rules_dict[rule_id] = {
                    "id": rule_id,
                    "shortDescription": {"text": f"Rule {rule_id}"},
                }

        runs.append(
            {
                "tool": {
                    "driver": {
                        "name": driver_name,
                        "version": driver_version,
                        "rules": list(rules_dict.values()),
                    }
                },
                "results": sarif_findings,
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": runs,
    }
