"""Phase 02 structured IaC report normalization contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rush.engines.iac_parser import (
    StructuredIacReportError,
    parse_structured_iac_report,
)


def test_parses_contained_json_findings_with_stable_mapping(tmp_path: Path) -> None:
    source = tmp_path / "infra" / "main.tf"
    source.parent.mkdir()
    source.write_text('resource "example" "test" {}\n')
    payload = json.dumps(
        {
            "results": [
                {
                    "file_path": "infra/main.tf",
                    "check_id": "CKV_TEST_1",
                    "severity": "HIGH",
                    "file_line_range": [1, 1],
                    "check_name": "Example policy failed",
                }
            ]
        }
    )

    findings = parse_structured_iac_report(payload, tmp_path)

    assert findings == [
        {
            "path": str(source),
            "line": 1,
            "rule": "CKV_TEST_1",
            "severity": "error",
            "message": "Example policy failed",
        }
    ]


def test_parses_sarif_like_locations_with_contained_paths(tmp_path: Path) -> None:
    source = tmp_path / "infra" / "modules" / "network.tf"
    source.parent.mkdir(parents=True)
    source.write_text('resource "example" "network" {}\n')
    payload = json.dumps(
        {
            "runs": [
                {
                    "results": [
                        {
                            "ruleId": "TF001",
                            "level": "warning",
                            "message": {"text": "Network policy warning"},
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {
                                            "uri": "infra/modules/network.tf"
                                        },
                                        "region": {"startLine": 1},
                                    }
                                }
                            ],
                        }
                    ]
                }
            ]
        }
    )

    findings = parse_structured_iac_report(payload, tmp_path)

    assert findings[0]["path"] == str(source)
    assert findings[0]["line"] == 1
    assert findings[0]["rule"] == "TF001"
    assert findings[0]["severity"] == "warn"
    assert findings[0]["message"] == "Network policy warning"


@pytest.mark.parametrize(
    "payload",
    [
        "not json",
        json.dumps({"results": {}}),
        json.dumps({"runs": [{"results": {}}]}),
        json.dumps({"results": [{"file_path": "../outside.tf"}]}),
    ],
)
def test_rejects_malformed_or_path_escaping_reports(
    tmp_path: Path, payload: str
) -> None:
    with pytest.raises(StructuredIacReportError):
        parse_structured_iac_report(payload, tmp_path)
