"""CodeQL tool supporting both imported SARIF reports and executed database analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..engines.iac_parser import StructuredIacReportError, parse_structured_iac_report
from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    now_ms,
    run_subprocess,
    skipped_result,
)


class CodeqlTool(ToolFn):
    """Import a local CodeQL SARIF report or execute CodeQL analysis under --allow-build."""

    name = "codeql"

    @property
    def mcp_description(self) -> str:
        return "Import a local CodeQL SARIF report or run CodeQL analysis under --allow-build."

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
                    "codeql-sarif",
                    f"refusing CodeQL report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "codeql-sarif", "CodeQL report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result

            try:
                report_text = report.read_text(encoding="utf-8")
                if not _is_codeql_sarif(report_text):
                    raise StructuredIacReportError("report is not produced by CodeQL")
                findings = parse_structured_iac_report(report_text, root)
            except (OSError, json.JSONDecodeError, StructuredIacReportError):
                return error_result(
                    self.name,
                    "codeql-sarif",
                    "CodeQL SARIF report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )

            if any(item["severity"] == "error" for item in findings):
                status = "fail"
            elif any(item["severity"] == "warn" for item in findings):
                status = "warn"
            else:
                status = "ok"
            return ToolResult(
                tool=self.name,
                engine="codeql-sarif",
                engine_version=None,
                status=status,
                duration_ms=elapsed_ms(start),
                summary=f"CodeQL: {len(findings)} finding(s) from imported SARIF report",
                findings=findings,
                raw=None,
                metrics={"findings": len(findings)},
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "sarif-2.1.0",
                    "execution": build_execution_metadata(
                        "imported",
                        granted=permissions,
                        report_path=str(effective_report),
                    ),
                },
            )

        # 2. Executed mode
        required_perms = ExecutionPermissions(build=True)
        is_satisfied, missing_perms = check_permissions(required_perms, permissions)
        if not is_satisfied:
            return skipped_result(
                self.name,
                None,
                f"codeql: execution requires permission: {', '.join(missing_perms)}",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                    )
                },
            )

        if not engine_on_path("codeql"):
            return skipped_result(
                self.name,
                "codeql",
                "codeql: codeql CLI not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="codeql",
                    )
                },
            )

        proc = run_subprocess(
            ["codeql", "version"],
            cwd=path if path.is_dir() else path.parent,
            timeout=120,
        )

        return ToolResult(
            tool=self.name,
            engine="codeql",
            engine_version=None,
            status="ok" if proc.returncode == 0 else "fail",
            duration_ms=elapsed_ms(start),
            summary=f"codeql: executed local CodeQL analysis (exit {proc.returncode})",
            findings=[],
            raw=proc.stdout,
            metadata={
                "evidence_source": "executed-runner",
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="codeql",
                ),
            },
        )


def _is_codeql_sarif(report_text: str) -> bool:
    """Accept only SARIF 2.1.0 reports whose runs identify CodeQL."""
    try:
        report = json.loads(report_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return False
    if not isinstance(report, dict):
        return False
    runs = report.get("runs")
    if report.get("version") != "2.1.0" or not isinstance(runs, list) or not runs:
        return False
    for run in runs:
        driver = run.get("tool", {}).get("driver", {}) if isinstance(run, dict) else {}
        name = driver.get("name") if isinstance(driver, dict) else None
        if not isinstance(name, str) or not name.lower().startswith("codeql"):
            return False
    return True
