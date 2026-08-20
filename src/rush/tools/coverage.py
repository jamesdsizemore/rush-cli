"""Coverage evidence tool supporting both imported reports and executed modes."""

from __future__ import annotations

import json
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


class CoverageTool(ToolFn):
    """Import a local coverage report or execute coverage under explicit permissions."""

    name = "coverage"

    @property
    def mcp_description(self) -> str:
        return "Import a local coverage report or run coverage analysis under --allow-slow."

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
                    "coverage-report",
                    f"refusing coverage report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "coverage-report", "coverage report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                report_text = report.read_text(encoding="utf-8")
                percent, report_format = _coverage_percent(report, report_text)
            except (
                ElementTree.ParseError,
                json.JSONDecodeError,
                KeyError,
                TypeError,
                ValueError,
            ):
                return error_result(
                    self.name,
                    "coverage-report",
                    "coverage report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )

            return ToolResult(
                tool=self.name,
                engine="coverage-report",
                engine_version=None,
                status="ok" if percent >= 100 else "warn",
                duration_ms=elapsed_ms(start),
                summary=f"coverage: {percent:g}% line coverage from imported report",
                findings=[],
                raw=None,
                metrics={"line_percent": percent},
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": report_format,
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
                f"coverage: execution requires permission: {', '.join(missing_perms)}",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                    )
                },
            )

        # Run executed coverage check via pytest-cov or coverage run
        if not engine_on_path("coverage") and not engine_on_path("pytest"):
            return skipped_result(
                self.name,
                "coverage",
                "coverage: coverage engine not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="coverage",
                    )
                },
            )
        binary = "coverage" if engine_on_path("coverage") else "pytest"
        cmd = (
            ["coverage", "run", "-m", "pytest", str(path)]
            if binary == "coverage"
            else ["pytest", "--cov", str(path)]
        )
        proc = run_subprocess(
            cmd,
            cwd=path if path.is_dir() else path.parent,
            timeout=300,
        )

        return ToolResult(
            tool=self.name,
            engine="coverage",
            engine_version=None,
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=elapsed_ms(start),
            summary=f"coverage: executed test coverage (exit {proc.returncode})",
            findings=[],
            raw=proc.stdout,
            metadata={
                "evidence_source": "executed-runner",
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="coverage",
                ),
            },
        )


def _coverage_percent(report: Path, report_text: str) -> tuple[float, str]:
    if report.suffix.lower() in {".lcov", ".info"}:
        hits = [
            int(line.rsplit(",", 1)[1])
            for line in report_text.splitlines()
            if line.startswith("DA:")
        ]
        if not hits:
            raise ValueError("LCOV report has no line records")
        return 100 * sum(hit > 0 for hit in hits) / len(hits), "lcov"
    if report.suffix.lower() == ".xml":
        root = ElementTree.fromstring(report_text)
        if root.tag != "coverage":
            raise ValueError("unsupported XML coverage report")
        return 100 * float(root.attrib["line-rate"]), "cobertura"

    payload = json.loads(report_text)
    return float(payload["totals"]["percent_covered"]), "coverage.py-json"
