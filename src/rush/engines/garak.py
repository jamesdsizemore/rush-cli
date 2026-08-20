"""Garak adapter for LLM vulnerability and redteaming scanning."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class GarakEngine(Engine):
    name = "garak"
    binary = "garak"
    file_extensions = ("yaml", "yml", "py")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--report_prefix", "garak_report"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        findings_raw: list[dict] = []
        # Search for generated report.jsonl
        report_files = list((cwd or path).glob("garak_report*.report.jsonl"))
        if report_files:
            try:
                for line in report_files[0].read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if (
                        entry.get("entry_type") == "eval"
                        and entry.get("passed") is False
                    ):
                        findings_raw.append(entry)
            except (json.JSONDecodeError, OSError):
                pass
        elif proc.stdout.strip():
            try:
                for line in proc.stdout.splitlines():
                    if not line.strip():
                        continue
                    entry = json.loads(line)
                    if isinstance(entry, dict) and entry.get("passed") is False:
                        findings_raw.append(entry)
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"failures": findings_raw},
            findings=findings_raw,
            summary=f"garak exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            probe_name = item.get("probe", "garak-probe")
            detector = item.get("detector", "vulnerability")
            score = item.get("score", 0.0)
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"{probe_name}/{detector}",
                    "severity": "fail" if score < 0.5 else "warn",
                    "message": f"Garak probe vulnerability: {probe_name} (detector: {detector}, score: {score})",
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
            summary=f"garak: {len(findings)} vulnerability probe hit(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
