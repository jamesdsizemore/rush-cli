"""Ts-prune adapter for finding unused TypeScript exports."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class TsPruneEngine(Engine):
    name = "ts-prune"
    binary = "ts-prune"
    file_extensions = ("ts", "tsx")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                # Text format fallback: file:line - exportName (used in module)
                for line in proc.stdout.splitlines():
                    if line.strip():
                        findings_raw.append({"raw": line.strip()})

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"ts-prune exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            if "raw" in item:
                findings.append(
                    {
                        "path": str(path),
                        "line": 0,
                        "column": 0,
                        "rule": "ts-prune/unused-export",
                        "severity": "warn",
                        "message": item["raw"],
                    }
                )
            else:
                findings.append(
                    {
                        "path": item.get("file", str(path)),
                        "line": item.get("line", 0),
                        "column": 0,
                        "rule": "ts-prune/unused-export",
                        "severity": "warn",
                        "message": f"Unused TypeScript export '{item.get('symbol', 'unknown')}'",
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
            summary=f"ts-prune: {len(findings)} unused export(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
