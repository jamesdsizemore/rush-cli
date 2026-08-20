"""Cargo-mutants adapter for Rust mutation testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CargoMutantsEngine(Engine):
    name = "cargo-mutants"
    binary = "cargo-mutants"
    file_extensions = ("rs",)

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["mutants", "--json", "--no-shuffle"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            try:
                item = json.loads(line_str)
                if item.get("summary") == "MISSED" or item.get("status") == "Unviable":
                    findings_raw.append(item)
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"missed_mutants": findings_raw},
            findings=findings_raw,
            summary=f"cargo-mutants exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("filename", str(path)),
                    "line": item.get("line", 0),
                    "column": 0,
                    "rule": f"cargo-mutants/{item.get('genre', 'missed-mutation')}",
                    "severity": "warn",
                    "message": f"Rust mutant survived in {item.get('function', 'function')}: {item.get('replacement', 'mutation')}",
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
            summary=f"cargo-mutants: {len(findings)} missed mutant(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
