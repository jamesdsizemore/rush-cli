"""Comby adapter for structural code pattern matching and syntax refactoring."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CombyEngine(Engine):
    name = "comby"
    binary = "comby"
    file_extensions = ("py", "js", "jsx", "ts", "tsx", "go", "rs", "c", "cpp", "java")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["-match-only", "-json-lines"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            try:
                item = json.loads(line_str)
                findings_raw.append(item)
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"matches": findings_raw},
            findings=findings_raw,
            summary=f"comby exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("uri", str(path)),
                    "line": item.get("range", {}).get("start", {}).get("line", 0),
                    "column": item.get("range", {}).get("start", {}).get("column", 0),
                    "rule": "comby/pattern-match",
                    "severity": "warn",
                    "message": f"Structural match: '{item.get('matched', 'pattern')}'",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "warn" if findings else ("ok" if exit_code == 0 else "error")

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"comby: {len(findings)} structural pattern match(es)",
            findings=findings,
            raw=raw.get("parsed"),
        )
