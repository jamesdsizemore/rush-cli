"""Promptfoo adapter for LLM security, redteaming, and agent workflow testing."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ..io.atomic_file import AtomicFile
from ..io.physical_paths import PhysicalRoot
from ..safety.redactor import sanitize_value
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
        physical = PhysicalRoot(cwd or path)
        report_file = physical.open_contained("promptfoo-report.json", purpose="write")
        if report_file.exists():
            raise ValueError("Evaluation report must not preexist invocation")
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "eval",
            "--output",
            str(report_file),
            "--no-table",
            "--no-progress-bar",
            "--no-cache",
            "--no-write",
            "--no-share",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(
            argv,
            cwd=cwd or path,
            timeout=300,
            env={
                **os.environ,
                "PROMPTFOO_CONFIG_DIR": str(cwd or path),
                "PROMPTFOO_DISABLE_TELEMETRY": "1",
            },
        )

        parsed = None
        report_file = physical.open_contained(report_file.name, purpose="read")
        if not report_file.is_file():
            raise ValueError("Promptfoo did not create its invocation report")
        sanitized = sanitize_value(json.loads(report_file.read_text(encoding="utf-8")))
        parsed = sanitized.value
        AtomicFile(physical).write_json(report_file.name, sanitized)

        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "results" in parsed:
            results = parsed["results"]
            rows = results.get("results", []) if isinstance(results, dict) else []
            if not rows and isinstance(results, dict):
                rows = results.get("table", {}).get("body", [])
            for row in rows:
                if not isinstance(row, dict):
                    continue
                grading = row.get("gradingResult", {})
                pass_status = row.get(
                    "success", row.get("pass", grading.get("pass", True))
                )
                if not pass_status:
                    findings_raw.append(
                        {
                            "description": row.get("testCase", {}).get(
                                "description",
                                row.get("description", "Promptfoo test failure"),
                            ),
                            "provider": row.get("provider", "llm"),
                            "prompt": row.get("prompt", {}).get("raw", ""),
                            "gradingResult": grading,
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
