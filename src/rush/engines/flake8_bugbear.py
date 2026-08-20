"""Flake8-Bugbear adapter for Python AST subtle bug and design flaw detection."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class Flake8BugbearEngine(Engine):
    name = "flake8-bugbear"
    binary = "flake8"
    file_extensions = ("py", "pyi")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "--select=B,B9",
            "--format=%(path)s:%(row)d:%(col)d:%(code)s:%(text)s",
        ]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str or ":" not in line_str:
                continue
            parts = line_str.split(":", 4)
            if len(parts) == 5:
                findings_raw.append(
                    {
                        "path": parts[0],
                        "row": int(parts[1]) if parts[1].isdigit() else 0,
                        "col": int(parts[2]) if parts[2].isdigit() else 0,
                        "code": parts[3],
                        "text": parts[4],
                    }
                )

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"violations": findings_raw},
            findings=findings_raw,
            summary=f"flake8-bugbear exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": item.get("row", 0),
                    "column": item.get("col", 0),
                    "rule": f"bugbear/{item.get('code', 'B000')}",
                    "severity": "warn",
                    "message": item.get("text", "Python design risk / subtle bug"),
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
            summary=f"flake8-bugbear: {len(findings)} design risk(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
