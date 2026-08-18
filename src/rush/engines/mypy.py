"""mypy adapter for Rush type checking."""

from __future__ import annotations

import re
from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class MypyEngine(Engine):
    name = "mypy"
    binary = "mypy"
    file_extensions = ("py", "pyi")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, "--hide-error-context", *args],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.base import ToolResult

        pattern = re.compile(
            r"^(?P<path>.+?):(?P<line>\d+): error: (?P<message>.*?)(?:  \[(?P<rule>[^]]+)\])?$"
        )
        findings = []
        for line in raw.get("stdout", "").splitlines():
            match = pattern.match(line)
            if match:
                findings.append(
                    {
                        "path": match["path"],
                        "line": int(match["line"]),
                        "rule": match["rule"] or "mypy",
                        "severity": "error",
                        "message": match["message"],
                    }
                )
        code = raw.get("exit_code", 0)
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="fail" if findings else ("ok" if code == 0 else "error"),
            duration_ms=0,
            summary=f"mypy: {len(findings)} error(s)",
            findings=findings,
            raw=None,
        )
