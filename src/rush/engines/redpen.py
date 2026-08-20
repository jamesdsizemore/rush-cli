"""RedPen adapter for technical documentation vocabulary and style guide validation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class RedpenEngine(Engine):
    name = "redpen"
    binary = "redpen"
    file_extensions = ("md", "txt", "adoc")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["-f", "json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    for doc in parsed:
                        for err in doc.get("errors", []):
                            findings_raw.append(
                                {"document": doc.get("document"), **err}
                            )
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"redpen exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("document", str(path)),
                    "line": item.get("lineNumber", 0),
                    "column": 0,
                    "rule": f"redpen/{item.get('validator', 'style')}",
                    "severity": "warn",
                    "message": item.get("message", "Technical prose validation error"),
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
            summary=f"redpen: {len(findings)} documentation style issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
