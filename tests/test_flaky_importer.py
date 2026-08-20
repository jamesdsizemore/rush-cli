"""Phase 04 contained JUnit flaky-report importer contracts."""

from __future__ import annotations

from pathlib import Path

from rush.tools.flaky import FlakyTool


def test_flaky_imports_duplicate_junit_cases_without_running_tests(
    tmp_path: Path,
) -> None:
    report = tmp_path / "junit.xml"
    report.write_text(
        "<testsuite><testcase classname='pkg.test' name='example'/>"
        "<testcase classname='pkg.test' name='example'><failure/></testcase></testsuite>"
    )

    result = FlakyTool().run(tmp_path, report_path=report)

    assert result["status"] == "warn"
    assert result["engine"] == "junit-report"
    assert result["findings"][0]["rule"] == "flaky-duplicate-case"
    assert result["metadata"]["evidence_source"] == "imported-local-report"


def test_flaky_rejects_missing_malformed_and_outside_reports(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-junit.xml"
    outside.write_text("<testsuite/>")
    malformed = tmp_path / "bad-junit.xml"
    malformed.write_text("not-xml")

    missing = FlakyTool().run(tmp_path, report_path=tmp_path / "absent.xml")
    bad = FlakyTool().run(tmp_path, report_path=malformed)
    escaped = FlakyTool().run(tmp_path, report_path=outside)

    assert [item["status"] for item in (missing, bad, escaped)] == [
        "skipped",
        "error",
        "error",
    ]
