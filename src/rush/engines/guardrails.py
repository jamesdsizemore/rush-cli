"""Guardrails adapter for deterministic LLM safety and policy flow validation."""

from __future__ import annotations

import json
from pathlib import Path

from ..io.atomic_file import AtomicFile
from ..io.physical_paths import PhysicalRoot
from ..safety.redactor import sanitize_value
from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class GuardrailsEngine(Engine):
    name = "guardrails"
    binary = "guardrails"
    file_extensions = ("co", "yml", "yaml", "py")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        physical = PhysicalRoot(cwd or path)
        report_file = physical.open_contained(
            "guardrails-results.json", purpose="write"
        )
        if report_file.exists():
            raise ValueError("Evaluation report must not preexist invocation")
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["validate", "--format", "json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        sanitized = sanitize_value(json.loads(proc.stdout))
        parsed = sanitized.value
        AtomicFile(physical).write_json(report_file.name, sanitized)
        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "violations" in parsed:
            findings_raw = parsed["violations"]
        elif isinstance(parsed, list):
            findings_raw = parsed

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"guardrails exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": item.get("rule", "guardrails-policy"),
                    "severity": "fail" if item.get("severity") == "error" else "warn",
                    "message": item.get("message", "Guardrail policy violation"),
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
            summary=f"guardrails: {len(findings)} violation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
