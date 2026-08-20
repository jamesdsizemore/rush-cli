"""CSpell adapter for code-aware spelling and identifier linting."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CspellEngine(Engine):
    name = "cspell"
    binary = "cspell"
    file_extensions = (
        "py",
        "js",
        "jsx",
        "ts",
        "tsx",
        "md",
        "json",
        "yaml",
        "yml",
        "html",
        "css",
    )

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["lint", "--reporter", "@cspell/cspell-json-reporter"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "issues" in parsed:
                    findings_raw = parsed["issues"]
                elif isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"cspell exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("uri", str(path)),
                    "line": item.get("row", 0),
                    "column": item.get("col", 0),
                    "rule": "cspell/unknown-word",
                    "severity": "warn",
                    "message": f"Spelling warning: Unknown word '{item.get('text', 'word')}'",
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
            summary=f"cspell: {len(findings)} spelling issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
