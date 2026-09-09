"""Phase 04 contained coverage-report importer contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rush.tools.coverage import CoverageTool


def test_coverage_imports_local_coverage_json_without_engine_execution(
    tmp_path: Path,
) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": 82.5}}))

    result = CoverageTool().run(tmp_path, report_path=report)

    assert result["status"] == "warn"
    assert result["engine"] == "coverage-report"
    assert result["metrics"] == {"line_percent": 82.5}
    assert result["metadata"]["evidence_source"] == "imported-local-report"
    assert result["artifacts"] == [str(report)]


def test_coverage_treats_a_file_target_as_the_explicit_report(tmp_path: Path) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": 100}}))

    result = CoverageTool().run(report)

    assert result["status"] == "ok"


def test_coverage_imports_local_lcov_without_engine_execution(tmp_path: Path) -> None:
    report = tmp_path / "coverage.lcov"
    report.write_text("TN:\nSF:src/example.py\nDA:1,1\nDA:2,0\nend_of_record\n")

    result = CoverageTool().run(tmp_path, report_path=report)

    assert result["status"] == "warn"
    assert result["metrics"] == {"line_percent": 50.0}
    assert result["metadata"]["report_format"] == "lcov"


def test_coverage_imports_local_cobertura_without_engine_execution(
    tmp_path: Path,
) -> None:
    report = tmp_path / "cobertura.xml"
    report.write_text('<coverage line-rate="0.875"/>')

    result = CoverageTool().run(tmp_path, report_path=report)

    assert result["status"] == "warn"
    assert result["metrics"] == {"line_percent": 87.5}
    assert result["metadata"]["report_format"] == "cobertura"


def test_coverage_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-coverage.json"
    outside.write_text("{}")
    malformed = tmp_path / "bad.json"
    malformed.write_text("not-json")

    missing = CoverageTool().run(tmp_path, report_path=tmp_path / "absent.json")
    bad = CoverageTool().run(tmp_path, report_path=malformed)
    escaped = CoverageTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]


@pytest.mark.parametrize("value", [-1, 101, float("inf"), float("nan")])
def test_coverage_rejects_nonfinite_or_out_of_range_percentages(
    tmp_path: Path, value: float
) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": value}}))
    assert CoverageTool().run(tmp_path, report_path=report)["status"] == "error"


@pytest.mark.parametrize("value", [0, 100])
def test_coverage_accepts_finite_boundary_percentages(
    tmp_path: Path, value: int
) -> None:
    report = tmp_path / "coverage.json"
    report.write_text(json.dumps({"totals": {"percent_covered": value}}))
    expected = "ok" if value == 100 else "warn"
    assert CoverageTool().run(tmp_path, report_path=report)["status"] == expected


def test_coverage_rejects_inconsistent_cobertura_counts(tmp_path: Path) -> None:
    report = tmp_path / "cobertura.xml"
    report.write_text('<coverage line-rate="0.5" lines-valid="10" lines-covered="4"/>')
    assert CoverageTool().run(tmp_path, report_path=report)["status"] == "error"


def test_coverage_rejects_nonzero_rate_with_zero_cobertura_counts(
    tmp_path: Path,
) -> None:
    report = tmp_path / "cobertura.xml"
    report.write_text('<coverage line-rate="0.5" lines-valid="0" lines-covered="0"/>')
    assert CoverageTool().run(tmp_path, report_path=report)["status"] == "error"


def test_coverage_accepts_rounded_cobertura_rate(tmp_path: Path) -> None:
    report = tmp_path / "cobertura.xml"
    report.write_text(
        '<coverage line-rate="0.6667" lines-valid="3" lines-covered="2"/>'
    )
    assert CoverageTool().run(tmp_path, report_path=report)["status"] == "warn"


@pytest.mark.parametrize("rate", ["-0.1", "1.1", "NaN", "Infinity"])
def test_coverage_rejects_invalid_cobertura_rate(tmp_path: Path, rate: str) -> None:
    report = tmp_path / "cobertura.xml"
    report.write_text(f'<coverage line-rate="{rate}"/>')
    assert CoverageTool().run(tmp_path, report_path=report)["status"] == "error"
