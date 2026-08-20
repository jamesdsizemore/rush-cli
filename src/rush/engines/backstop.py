"""BackstopJS adapter for responsive DOM visual regression testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class BackstopEngine(Engine):
    name = "backstop"
    binary = "backstop"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["test", "--reporter=json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=240)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "tests" in parsed:
                    for test in parsed["tests"]:
                        if test.get("status") == "fail":
                            findings_raw.append(test)
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"backstop exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            pair = item.get("pair", {})
            findings.append(
                {
                    "path": pair.get("url", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": "backstop/viewport-mismatch",
                    "severity": "fail",
                    "message": f"Visual mismatch in scenario '{pair.get('label', 'view')}' on viewport {pair.get('viewportLabel', 'default')}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "fail" if (findings or exit_code != 0) else "ok"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"backstop: {len(findings)} visual test mismatch(es)",
            findings=findings,
            raw=raw.get("parsed"),
        )
