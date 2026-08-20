"""Newman adapter for Postman collection API testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class NewmanEngine(Engine):
    name = "newman"
    binary = "newman"
    file_extensions = ("json",)

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
            "--reporters",
            "json",
            "--reporter-json-export",
            "newman-run.json",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        report_file = (cwd or path) / "newman-run.json"
        if report_file.exists():
            try:
                parsed = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                parsed = None
        elif proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                parsed = None

        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "run" in parsed:
            failures = parsed.get("run", {}).get("failures", [])
            findings_raw = failures

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"newman exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            error_meta = item.get("error", {})
            test_name = error_meta.get("test", "Postman Test")
            message = error_meta.get("message", "API assertion failed")
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"newman/{test_name.lower().replace(' ', '-')}",
                    "severity": "fail",
                    "message": message,
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
            summary=f"newman: {len(findings)} collection assertion failure(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
