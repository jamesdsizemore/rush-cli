"""Property-based testing tool supporting both local imported reports and execution."""

from __future__ import annotations

import json
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    now_ms,
    run_subprocess,
    skipped_result,
)


class PbtTool(ToolFn):
    """Import a local property-test report or run property tests under --allow-slow."""

    name = "pbt"

    @property
    def mcp_description(self) -> str:
        return "Import a local property-test report or run property tests under --allow-slow."

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
                    "property-report",
                    f"refusing property report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "property-report", "property-test report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                seed = int(payload["seed"])
                failures = payload.get("failures", [])
                if not isinstance(failures, list):
                    raise TypeError("failures must be a list")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return error_result(
                    self.name,
                    "property-report",
                    "property-test report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )

            findings = [
                {
                    "path": str(effective_report),
                    "line": 0,
                    "rule": "property-failure",
                    "severity": "error",
                    "message": (
                        f"{item.get('property', 'property')}: {item.get('message', 'failed')}"
                        if isinstance(item, dict)
                        else "property test failed"
                    ),
                }
                for item in failures
            ]
            return ToolResult(
                tool=self.name,
                engine="property-report",
                engine_version=None,
                status="fail" if findings else "ok",
                duration_ms=elapsed_ms(start),
                summary=f"pbt: {len(findings)} failure(s) in imported seeded report",
                findings=findings,
                raw=None,
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "property-json",
                    "seed": seed,
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
                f"pbt: execution requires permission: {', '.join(missing_perms)}",
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
                "hypothesis",
                "pbt: hypothesis test runner not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="hypothesis",
                    )
                },
            )

        proc = run_subprocess(
            ["pytest", "-m", "hypothesis", str(path)],
            cwd=path if path.is_dir() else path.parent,
            timeout=180,
        )

        return ToolResult(
            tool=self.name,
            engine="hypothesis",
            engine_version=None,
            status="ok" if proc.returncode == 0 else "fail",
            duration_ms=elapsed_ms(start),
            summary=f"pbt: executed property test runner (exit {proc.returncode})",
            findings=[],
            raw=proc.stdout,
            metadata={
                "evidence_source": "executed-runner",
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="hypothesis",
                ),
            },
        )
