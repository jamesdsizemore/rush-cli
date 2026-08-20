"""Cejel adapter for offline codebase trust certificate verification."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CejelEngine(Engine):
    name = "cejel"
    binary = "cejel"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["verify", "--format=json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "violations" in parsed:
                    findings_raw = parsed["violations"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"cejel exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": f"cejel/{item.get('rule', 'trust-violation')}",
                    "severity": "fail",
                    "message": item.get(
                        "description", "Codebase trust attestation mismatch"
                    ),
                    "fix": None,
                    "remediation": "Re-sign or verify trust certificate against current repository state.",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "fail" if findings else ("ok" if exit_code == 0 else "error")

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"cejel: {len(findings)} trust violation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
