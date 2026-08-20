"""Contract tool supporting both local imported Pact reports and local execution."""

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


class ContractTool(ToolFn):
    """Import a local Pact report or run local contract tests without network."""

    name = "contract"

    @property
    def mcp_description(self) -> str:
        return "Import a local Pact report or run local contract verifications under --allow-slow."

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
                    "pact-report",
                    f"refusing contract report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "pact-report", "contract report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                summary = payload["summary"]
                errors = int(summary["errors"])
                warnings = int(summary.get("warnings", 0))
                if errors < 0 or warnings < 0:
                    raise ValueError("negative counts")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return error_result(
                    self.name,
                    "pact-report",
                    "contract report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )

            status = "fail" if errors else "warn" if warnings else "ok"
            return ToolResult(
                tool=self.name,
                engine="pact-report",
                engine_version=None,
                status=status,
                duration_ms=elapsed_ms(start),
                summary=f"contract: {errors} error(s), {warnings} warning(s) in imported report",
                findings=[],
                raw=None,
                metrics={"errors": errors, "warnings": warnings},
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "pact",
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
                f"contract: execution requires permission: {', '.join(missing_perms)}",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                    )
                },
            )

        if not engine_on_path("pact-verifier"):
            return skipped_result(
                self.name,
                "pact",
                "contract: pact verifier not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="pact",
                    )
                },
            )

        proc = run_subprocess(
            ["pact-verifier", "--version"],
            cwd=path if path.is_dir() else path.parent,
            timeout=120,
        )

        return ToolResult(
            tool=self.name,
            engine="pact",
            engine_version=None,
            status="ok" if proc.returncode == 0 else "fail",
            duration_ms=elapsed_ms(start),
            summary=f"contract: executed local contract verifier (exit {proc.returncode})",
            findings=[],
            raw=proc.stdout,
            metadata={
                "evidence_source": "executed-runner",
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="pact",
                ),
            },
        )
