"""FawltyDeps adapter for undeclared and unused Python dependencies."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class FawltydepsEngine(Engine):
    name = "fawltydeps"
    binary = "fawltydeps"
    file_extensions = ("py", "toml", "txt")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--json", "--detailed"]
        argv = [binary_path, *default_args, *args, "--code", str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict):
                    for undeclared in parsed.get("undeclared_deps", []):
                        findings_raw.append({"type": "undeclared", "dep": undeclared})
                    for unused in parsed.get("unused_deps", []):
                        findings_raw.append({"type": "unused", "dep": unused})
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"fawltydeps exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            dep_type = item.get("type", "dep")
            dep_name = (
                item.get("dep", {}).get("name", "dependency")
                if isinstance(item.get("dep"), dict)
                else str(item.get("dep"))
            )
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"fawltydeps/{dep_type}-dependency",
                    "severity": "fail" if dep_type == "undeclared" else "warn",
                    "message": f"Python {dep_type} dependency found: '{dep_name}'",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "fail"
            if any(f["severity"] == "fail" for f in findings)
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"fawltydeps: {len(findings)} dependency issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
