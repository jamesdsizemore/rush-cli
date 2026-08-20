"""Mutation tool supporting both local imported mutation reports and execution."""

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


class MutationTool(ToolFn):
    """Import a local mutation report or run mutation testing under explicit permissions."""

    name = "mutation"

    @property
    def mcp_description(self) -> str:
        return (
            "Import a local mutation report or run mutation testing under --allow-slow."
        )

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
        **options: object,
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
        return self.run(
            path, report_path=report_path, permissions=permissions, **options
        )

    def run(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        config=None,
        permissions=None,
        **options: object,
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
                    "mutation-report",
                    f"refusing mutation report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "mutation-report", "mutation report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                metrics = {
                    name: int(payload[name])
                    for name in ("killed", "survived", "timeout")
                }
                if any(value < 0 for value in metrics.values()):
                    raise ValueError("negative metric")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return error_result(
                    self.name,
                    "mutation-report",
                    "mutation report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )
            escaped = metrics["survived"] + metrics["timeout"]
            return ToolResult(
                tool=self.name,
                engine="mutation-report",
                engine_version=None,
                status="fail" if escaped else "ok",
                duration_ms=elapsed_ms(start),
                summary=f"mutation: {escaped} mutant(s) survived or timed out",
                findings=[],
                raw=None,
                metrics=metrics,
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "mutation-json",
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
                f"mutation: execution requires permission: {', '.join(missing_perms)}",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                    )
                },
            )

        if not engine_on_path("mutmut"):
            return skipped_result(
                self.name,
                "mutmut",
                "mutation: mutmut engine not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="mutmut",
                    )
                },
            )

        proc = run_subprocess(
            ["mutmut", "--version"],
            cwd=path if path.is_dir() else path.parent,
            timeout=120,
        )

        return ToolResult(
            tool=self.name,
            engine="mutmut",
            engine_version=None,
            status="ok" if proc.returncode == 0 else "warn",
            duration_ms=elapsed_ms(start),
            summary=f"mutation: executed mutation test runner (exit {proc.returncode})",
            findings=[],
            raw=proc.stdout,
            metadata={
                "evidence_source": "executed-runner",
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="mutmut",
                ),
            },
        )
