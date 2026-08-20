"""Kubeconform adapter for Kubernetes manifest validation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class KubeconformEngine(Engine):
    name = "kubeconform"
    binary = "kubeconform"
    file_extensions = ("yaml", "yml", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["-output", "json", "-summary"]
        argv = [binary_path, *default_args, *args, str(path)]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line:
                    try:
                        item = json.loads(line)
                        if isinstance(item, dict) and item.get("status") in {
                            "invalid",
                            "error",
                        }:
                            findings_raw.append(item)
                    except json.JSONDecodeError:
                        continue

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"kubeconform exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("filename", str(path)),
                    "line": 0,
                    "rule": item.get("kind", "kubeconform-schema"),
                    "severity": "error",
                    "message": item.get("msg", "Invalid Kubernetes manifest"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="fail" if findings else ("ok" if exit_code == 0 else "error"),
            duration_ms=raw.get("duration_ms", 0),
            summary=f"kubeconform: {len(findings)} schema issue(s)",
            findings=findings,
            raw=raw.get("stdout"),
        )
