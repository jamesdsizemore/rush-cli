"""Conftest adapter for OPA Rego policy testing on structured configuration."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ConftestEngine(Engine):
    name = "conftest"
    binary = "conftest"
    file_extensions = ("yaml", "yml", "json", "tf", "dockerfile", "toml")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["test", "-o", "json", "--no-color"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    for file_res in parsed:
                        for failure in file_res.get("failures", []):
                            findings_raw.append(
                                {
                                    "file": file_res.get("filename"),
                                    "severity": "fail",
                                    **failure,
                                }
                            )
                        for warning in file_res.get("warnings", []):
                            findings_raw.append(
                                {
                                    "file": file_res.get("filename"),
                                    "severity": "warn",
                                    **warning,
                                }
                            )
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"conftest exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": item.get("metadata", {}).get("rule", "conftest-policy"),
                    "severity": item.get("severity", "warn"),
                    "message": item.get("msg", "OPA Rego policy failure"),
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
            summary=f"conftest: {len(findings)} policy finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
