"""DeepEval adapter for RAG and LLM unit metric evaluations."""

from __future__ import annotations

import json
from pathlib import Path

from ..io.atomic_file import AtomicFile
from ..io.physical_paths import PhysicalRoot
from ..safety.redactor import sanitize_value
from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class DeepevalEngine(Engine):
    name = "deepeval"
    binary = "deepeval"
    file_extensions = ("py", "yaml", "yml")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        physical = PhysicalRoot(cwd or path)
        report_file = physical.open_contained("deepeval-results.json", purpose="write")
        if report_file.exists():
            raise ValueError("Evaluation report must not preexist invocation")
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["test", "run", str(path), f"--json-report={report_file}"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        report_file = physical.open_contained(report_file.name, purpose="read")
        if not report_file.is_file():
            raise ValueError("DeepEval did not create its invocation report")
        sanitized = sanitize_value(json.loads(report_file.read_text(encoding="utf-8")))
        parsed = sanitized.value
        AtomicFile(physical).write_json(report_file.name, sanitized)

        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "test_results" in parsed:
            for test in parsed.get("test_results", []):
                if not test.get("success", True):
                    findings_raw.append(test)
        elif isinstance(parsed, list):
            for test in parsed:
                if isinstance(test, dict) and not test.get("success", True):
                    findings_raw.append(test)

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"deepeval exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            name = item.get("name") or item.get("metric", "DeepEvalMetric")
            score = item.get("score", 0.0)
            reason = item.get("reason", "Metric threshold not satisfied")
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"deepeval/{name}",
                    "severity": "fail",
                    "message": f"{name} failed with score {score}: {reason}",
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
            summary=f"deepeval: {len(findings)} metric failure(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
