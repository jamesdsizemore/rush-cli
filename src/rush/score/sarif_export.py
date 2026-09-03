"""OASIS SARIF 2.1.0 exporter for GitHub Code Scanning."""

from __future__ import annotations

import json

from rush import __version__
from rush.score.consensus import ConsensusFinding


class SarifExporter:
    """Exports consensus code review findings into SARIF 2.1.0 format."""

    @staticmethod
    def export_sarif(findings: list[ConsensusFinding]) -> str:
        results = []
        for f in findings:
            level = "error" if f.severity.upper() in ("HIGH", "CRITICAL") else "warning"
            results.append(
                {
                    "ruleId": f.rule_id,
                    "level": level,
                    "message": {"text": f.description},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": f.file_path},
                                "region": {"startLine": f.line_number},
                            }
                        }
                    ],
                }
            )

        sarif_doc = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Rush Consensus Engine",
                            "semanticVersion": __version__,
                        }
                    },
                    "results": results,
                }
            ],
        }
        from rush.safety.redactor import sanitize_value

        clean_doc = sanitize_value(sarif_doc).value
        return json.dumps(clean_doc, indent=2)
