"""vitest engine — JS/TS test runner with --reporter=json.

Vitest's JSON reporter outputs an array of test result objects. Exit
non-zero if any tests fail.

Output structure (simplified):
    [
        {
            "name": "tests/foo.test.ts > bar > does X",
            "status": "passed" | "failed" | "skipped",
            "duration": 12,
            "failureMessages": ["AssertionError: ..."]
        },
        ...
    ]
"""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class VitestEngine(Engine):
    name = "vitest"
    binary = "vitest"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        argv = [
            binary_path,
            "run",
            "--reporter=json",
            "--no-color",
            str(path),
            *args,
        ]
        proc = run_subprocess(argv, cwd=cwd, timeout=300)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"vitest exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.base import ToolResult
        from ..tools.common import elapsed_ms

        # Count outcomes
        n_pass = n_fail = n_skip = 0
        failure_messages: list[str] = []
        for t in raw.get("findings", []):
            status = t.get("status", "unknown")
            if status == "passed":
                n_pass += 1
            elif status == "failed":
                n_fail += 1
                msgs = t.get("failureMessages", [])
                if msgs:
                    failure_messages.append(msgs[0] if msgs else t.get("name", ""))
            elif status == "skipped":
                n_skip += 1

        # Build findings from failures
        findings = []
        for t in raw.get("findings", []):
            if t.get("status") == "failed":
                findings.append(
                    {
                        "path": str(
                            path
                        ),  # vitest names don't map cleanly to file paths
                        "line": 0,
                        "rule": "test-failed",
                        "severity": "error",
                        "message": (
                            t.get("failureMessages", [""])[0]
                            if t.get("failureMessages")
                            else t.get("name", "")
                        )[:200],
                    }
                )

        exit_code = raw.get("exit_code", 0)
        if exit_code >= 2:
            status = "error"
            summary = f"vitest error (exit {exit_code})"
        elif n_fail:
            status = "fail"
            summary = f"vitest: {n_pass} passed, {n_fail} failed, {n_skip} skipped"
        elif n_pass == 0 and n_skip == 0:
            status = "ok"
            summary = "vitest: no tests collected"
        else:
            status = "ok"
            summary = f"vitest: {n_pass} passed, {n_fail} failed, {n_skip} skipped"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", elapsed_ms(0)),
            summary=summary,
            findings=findings,
            raw=raw.get("parsed"),
        )
