"""Garak adapter for LLM vulnerability and redteaming scanning."""

from __future__ import annotations

import json
from pathlib import Path

from ..io.atomic_file import AtomicFile, SanitizedBytes
from ..io.physical_paths import PhysicalRoot
from ..safety.redactor import sanitize_value
from ..tools.base import Finding, ToolResult, ToolStatus
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
        physical = PhysicalRoot(cwd or path)
        report_file = physical.open_contained(
            "garak_report.report.jsonl", purpose="write"
        )
        if report_file.exists():
            raise ValueError("Evaluation report must not preexist invocation")
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--report_prefix", str(physical.root_path / "garak_report")]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        findings_raw: list[dict] = []
        report_file = physical.open_contained(report_file.name, purpose="read")
        if not report_file.is_file():
            raise ValueError("Garak did not create its invocation report")
        rows = sanitize_value(
            [
                json.loads(line)
                for line in report_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        ).value
        AtomicFile(physical).write_bytes(
            report_file.name,
            SanitizedBytes("".join(json.dumps(row) + "\n" for row in rows).encode()),
        )
        for entry in rows:
            if entry.get("entry_type") == "eval" and entry.get("passed") is False:
                findings_raw.append(entry)

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
        findings: list[Finding] = []
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
                    "severity": "error" if score < 0.5 else "warn",
                    "message": f"Garak probe vulnerability: {probe_name} (detector: {detector}, score: {score})",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status: ToolStatus = (
            "fail" if findings else ("ok" if exit_code == 0 else "error")
        )

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
