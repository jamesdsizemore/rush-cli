"""Kube-score adapter for Kubernetes manifest security and reliability auditing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class KubeScoreEngine(Engine):
    name = "kube-score"
    binary = "kube-score"
    file_extensions = ("yaml", "yml", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["score", "--output-format", "json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    for manifest in parsed:
                        checks = manifest.get("checks", [])
                        for check in checks:
                            if check.get("grade", 0) < 10 or check.get(
                                "critical", False
                            ):
                                findings_raw.append(
                                    {
                                        "manifest": manifest.get("object_meta", {}),
                                        "check": check,
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
            summary=f"kube-score exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            check = item.get("check", {})
            meta = item.get("manifest", {})
            name = meta.get("name", "kubernetes-resource")
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"kube-score/{check.get('check', {}).get('id', 'check')}",
                    "severity": "fail" if check.get("critical") else "warn",
                    "message": f"[{name}] {check.get('check', {}).get('name')}: {check.get('comments', [{}])[0].get('summary', 'check warning') if check.get('comments') else 'issue'}",
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
            summary=f"kube-score: {len(findings)} recommendation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
