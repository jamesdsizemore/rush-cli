"""TypeScript compiler adapter for Rush type checking."""

from __future__ import annotations

import re
from pathlib import Path

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class TscEngine(Engine):
    name = "tsc"
    binary = "tsc"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, "--noEmit", *args],
            cwd=cwd,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.base import ToolResult

        text = "\n".join((raw.get("stdout", ""), raw.get("stderr", "")))
        pattern = re.compile(
            r"^(?P<path>.+?)\((?P<line>\d+),(?P<column>\d+)\): error (?P<rule>TS\d+): (?P<message>.*)$"
        )
        findings = []
        for line in text.splitlines():
            match = pattern.match(line)
            if match:
                findings.append(
                    {
                        "path": match["path"],
                        "line": int(match["line"]),
                        "column": int(match["column"]),
                        "rule": match["rule"],
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
            summary=f"tsc: {len(findings)} error(s)",
            findings=findings,
            raw=None,
        )
