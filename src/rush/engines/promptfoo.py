"""Promptfoo adapter for LLM security, redteaming, and agent workflow testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class PromptfooEngine(Engine):
    name = "promptfoo"
    binary = "promptfoo"
    file_extensions = ("yaml", "yml", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "eval",
            "--output",
            "promptfoo-report.json",
            "--no-table",
            "--no-progress-bars",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        parsed = None
        report_file = (cwd or path) / "promptfoo-report.json"
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
        if isinstance(parsed, dict) and "results" in parsed:
            for table in parsed.get("results", {}).get("table", {}).get("body", []):
                # Check for failing test assertions
                pass_status = (
                    table.get("pass", True) if isinstance(table, dict) else True
                )
                if not pass_status:
                    findings_raw.append(
                        {
                            "description": table.get(
                                "description", "Promptfoo test failure"
                            ),
                            "provider": table.get("provider", "llm"),
                            "prompt": table.get("prompt", {}).get("raw", ""),
                            "gradingResult": table.get("gradingResult", {}),
                        }
                    )

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"promptfoo exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            grading = item.get("gradingResult", {})
            message = grading.get("reason") or item.get(
                "description", "Promptfoo assertion failed"
            )
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": "promptfoo-assertion",
                    "severity": "fail",
                    "message": message,
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "fail"
            if (findings or exit_code == 100)
            else ("ok" if exit_code == 0 else "error")
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"promptfoo: {len(findings)} assertion failure(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
