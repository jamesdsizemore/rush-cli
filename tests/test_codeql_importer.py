"""Phase 05 contained CodeQL SARIF importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

from rush.tools.codeql import CodeqlTool


def _sarif(uri: str, *, level: str = "error", tool_name: str = "CodeQL") -> str:
    return json.dumps(
        {
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {"driver": {"name": tool_name}},
                    "results": [
                        {
                            "ruleId": "py/clear-text-logging-sensitive-data",
                            "level": level,
                            "message": {"text": "Sensitive data reaches logging."},
                            "locations": [
                                {
                                    "physicalLocation": {
                                        "artifactLocation": {"uri": uri},
                                        "region": {"startLine": 7},
                                    }
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_codeql_imports_contained_sarif_without_running_codeql(tmp_path: Path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("print('example')\n")
    report = tmp_path / "codeql.sarif"
    report.write_text(_sarif("src/app.py"))

    result = CodeqlTool().run(tmp_path, report_path=report)

    assert result["status"] == "fail"
    assert result["tool"] == "codeql"
    assert result["engine"] == "codeql-sarif"
    assert result["findings"] == [
        {
            "path": str(source),
            "line": 7,
            "rule": "py/clear-text-logging-sensitive-data",
            "severity": "error",
            "message": "Sensitive data reaches logging.",
        }
    ]
    assert result["artifacts"] == [str(report)]
    assert result["metadata"]["evidence_source"] == "imported-local-report"
    assert result["metadata"]["report_format"] == "sarif-2.1.0"
    assert result["metadata"]["execution"]["mode"] == "imported"


def test_codeql_preserves_nonblocking_sarif_severity(tmp_path: Path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("print('example')\n")
    report = tmp_path / "codeql.sarif"
    report.write_text(_sarif("src/app.py", level="warning"))

    result = CodeqlTool().run(tmp_path, report_path=report)

    assert result["status"] == "warn"
    assert result["findings"][0]["severity"] == "warn"


def test_codeql_rejects_sarif_from_a_different_engine(tmp_path: Path) -> None:
    source = tmp_path / "src" / "app.py"
    source.parent.mkdir()
    source.write_text("print('example')\n")
    report = tmp_path / "foreign.sarif"
    report.write_text(_sarif("src/app.py", tool_name="Semgrep"))

    result = CodeqlTool().run(tmp_path, report_path=report)

    assert result["status"] == "error"
    assert result["findings"] == []


def test_codeql_returns_a_structured_error_for_a_nonobject_report(
    tmp_path: Path,
) -> None:
    report = tmp_path / "bad-root.sarif"
    report.write_text("[]")

    result = CodeqlTool().run(tmp_path, report_path=report)

    assert result["status"] == "error"
    assert result["findings"] == []


def test_codeql_rejects_sarif_without_a_codeql_run(tmp_path: Path) -> None:
    report = tmp_path / "empty.sarif"
    report.write_text('{"version": "2.1.0", "runs": []}')

    result = CodeqlTool().run(tmp_path, report_path=report)

    assert result["status"] == "error"
    assert result["findings"] == []


def test_codeql_rejects_missing_malformed_and_path_escaping_sarif(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / "outside.sarif"
    outside.write_text(_sarif("outside.py"))
    malformed = tmp_path / "bad.sarif"
    malformed.write_text("not-json")

    missing = CodeqlTool().run(tmp_path, report_path=tmp_path / "absent.sarif")
    bad = CodeqlTool().run(tmp_path, report_path=malformed)
    escaped = CodeqlTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
