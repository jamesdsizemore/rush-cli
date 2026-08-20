"""Polaris adapter for Kubernetes workload configuration auditing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class PolarisEngine(Engine):
    name = "polaris"
    binary = "polaris"
    file_extensions = ("yaml", "yml", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["audit", "--audit-path", str(path), "--format", "json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "Results" in parsed:
                    for res in parsed["Results"]:
                        for check in (
                            res.get("PodResult", {}).get("Results", {}).values()
                        ):
                            if not check.get("Success", True):
                                findings_raw.append(
                                    {"target": res.get("Name"), **check}
                                )
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"polaris exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            severity = item.get("Severity", "warning").lower()
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"polaris/{item.get('ID', 'check')}",
                    "severity": "fail" if severity in ("danger", "error") else "warn",
                    "message": f"[{item.get('target', 'resource')}] {item.get('Message', 'Polaris configuration check failed')}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "fail"
            if any(f["severity"] == "fail" for f in findings)
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"polaris: {len(findings)} configuration finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
