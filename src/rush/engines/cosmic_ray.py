"""Cosmic Ray adapter for Python mutation testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CosmicRayEngine(Engine):
    name = "cosmic-ray"
    binary = "cosmic-ray"
    file_extensions = ("py",)

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["dump", "cosmic-ray.sqlite"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            try:
                item = json.loads(line_str)
                if (
                    item.get("test_outcome") == "SURVIVED"
                    or item.get("worker_outcome") == "NORMAL"
                ):
                    findings_raw.append(item)
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"mutants": findings_raw},
            findings=findings_raw,
            summary=f"cosmic-ray exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("module_path", str(path)),
                    "line": item.get("line_number", 0),
                    "column": 0,
                    "rule": f"cosmic-ray/{item.get('operator_name', 'operator')}",
                    "severity": "warn",
                    "message": f"Python mutant survived: {item.get('description', 'mutation did not fail test suite')}",
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
            summary=f"cosmic-ray: {len(findings)} survived mutant(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
