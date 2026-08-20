"""Flaky testing evidence tool supporting both imported JUnit reports and execution."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from xml.etree import ElementTree

from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    now_ms,
    run_subprocess,
    skipped_result,
)


class FlakyTool(ToolFn):
    """Import a local JUnit report or execute duplicate test analysis under --allow-slow."""

    name = "flaky"

    @property
    def mcp_description(self) -> str:
        return "Import a local JUnit report or run duplicate test analysis under --allow-slow."

    def __call__(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, report_path=report_path, permissions=permissions)

    def run(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        config=None,
        permissions=None,
    ) -> ToolResult:
        from ..permissions import (
            ExecutionPermissions,
            build_execution_metadata,
            check_permissions,
        )

        start = now_ms()

        # 1. Imported mode
        if report_path is not None or path.is_file():
            effective_report = report_path or path
            root = path.resolve() if path.is_dir() else path.parent.resolve()
            report = effective_report.resolve()
            try:
                report.relative_to(root)
            except ValueError:
                return error_result(
                    self.name,
                    "junit-report",
                    f"refusing flaky report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "junit-report", "flaky report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                testcases = list(ElementTree.parse(report).iter("testcase"))
            except ElementTree.ParseError:
                return error_result(
                    self.name,
                    "junit-report",
                    "flaky report is malformed XML",
                    duration_ms=elapsed_ms(start),
                )

            identities = [
                f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}"
                for case in testcases
            ]
            duplicates = sorted(
                name for name, count in Counter(identities).items() if count > 1
            )
            findings = [
                {
                    "path": str(effective_report),
                    "line": 0,
                    "rule": "flaky-duplicate-case",
                    "severity": "warning",
                    "message": f"JUnit report repeats test case {identity}",
                }
                for identity in duplicates
            ]
            return ToolResult(
                tool=self.name,
                engine="junit-report",
                engine_version=None,
                status="warn" if findings else "ok",
                duration_ms=elapsed_ms(start),
                summary=(
                    f"flaky: {len(findings)} repeated test case(s) in imported report"
                    if findings
                    else "flaky: no repeated test cases in imported report"
                ),
                findings=findings,
                raw=None,
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "junit",
                    "execution": build_execution_metadata(
                        "imported",
                        granted=permissions,
                        report_path=str(effective_report),
                    ),
                },
            )

        # 2. Executed mode
        required_perms = ExecutionPermissions(slow=True)
        is_satisfied, missing_perms = check_permissions(required_perms, permissions)
        if not is_satisfied:
            return skipped_result(
                self.name,
                None,
                f"flaky: execution requires permission: {', '.join(missing_perms)}",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                    )
                },
            )

        if not engine_on_path("pytest"):
            return skipped_result(
                self.name,
                "pytest-rerun",
                "flaky: rerun engine not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="pytest-rerun",
                    )
                },
            )

        proc = run_subprocess(
            ["pytest", "--reruns", "3", str(path)],
            cwd=path if path.is_dir() else path.parent,
            timeout=180,
        )

        return ToolResult(
            tool=self.name,
            engine="pytest-rerun",
            engine_version=None,
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=elapsed_ms(start),
            summary=f"flaky: executed rerun analysis (exit {proc.returncode})",
            findings=[],
            raw=proc.stdout,
            metadata={
                "evidence_source": "executed-runner",
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="pytest-rerun",
                ),
            },
        )
