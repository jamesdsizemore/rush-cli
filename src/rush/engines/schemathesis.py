"""Schemathesis adapter for property-based API contract fuzzing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class SchemathesisEngine(Engine):
    name = "schemathesis"
    binary = "schemathesis"
    file_extensions = ("json", "yaml", "yml")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "run",
            str(path),
            "--report=junit",
            "--output-path=schemathesis-report.xml",
            "--dry-run",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "errors" in parsed:
                    findings_raw = parsed["errors"]
            except json.JSONDecodeError:
                parsed = {"output": proc.stdout}
        else:
            parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"schemathesis exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": item.get("code", "schemathesis-contract-error"),
                    "severity": "fail",
                    "message": item.get(
                        "message", "API schema property contract violation"
                    ),
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "fail" if (findings or exit_code != 0) else "ok"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"schemathesis: {len(findings)} contract failure(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
