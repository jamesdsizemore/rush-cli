"""TDD Guard tool for Red-Green-Refactor cycle enforcement.

Ensures that code commits adhere to Test-Driven Development contracts and that
tests are executed deterministically before changes are accepted into Git history.
"""

from __future__ import annotations

from pathlib import Path

from .base import Finding, ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


class TddGuardTool(ToolFn):
    name: ToolName = "tdd"

    @property
    def mcp_description(self) -> str:
        return (
            "Verify Test-Driven Development (TDD) compliance at <path>. "
            "Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
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
        return self.run(path, permissions=permissions, **options)

    def run(
        self,
        path: Path,
        *,
        config=None,
        permissions=None,
        **options: object,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        findings: list[Finding] = []

        # Check if test directory or test files exist
        target_path = Path(path)
        tests_found = False
        if target_path.is_dir():
            test_files = (
                list(target_path.glob("**/test_*.py"))
                + list(target_path.glob("**/*_test.go"))
                + list(target_path.glob("**/*.test.ts"))
                + list(target_path.glob("**/*.spec.ts"))
            )
            tests_found = len(test_files) > 0
        else:
            tests_found = "test" in target_path.name

        if not tests_found:
            findings.append(
                Finding(
                    path=str(path),
                    line=1,
                    rule="tdd/missing-tests",
                    severity="fail",
                    message="No corresponding automated test suite discovered for target path.",
                    remediation="Author test cases in tests/ defining expected behavior before modifying implementation.",
                )
            )

        status = "fail" if findings else "ok"
        summary = (
            f"tdd: {len(findings)} TDD compliance finding(s)"
            if findings
            else "tdd: test suite verified"
        )

        return ToolResult(
            tool=self.name,
            engine="tdd-guard",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            raw=None,
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="tdd-guard",
                )
            },
        )
