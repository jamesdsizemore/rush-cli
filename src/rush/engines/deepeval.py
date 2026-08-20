"""DeepEval adapter for RAG and LLM unit metric evaluations."""

from __future__ import annotations

import json
from pathlib import Path

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
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["test", "run", "--json-report=deepeval-results.json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        parsed = None
        report_file = (cwd or path) / "deepeval-results.json"
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
