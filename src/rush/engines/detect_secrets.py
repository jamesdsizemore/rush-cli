"""Detect-secrets adapter for baseline-managed credential screening."""

from __future__ import annotations

import json
from pathlib import Path

from ..logging import redact_secrets
from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class DetectSecretsEngine(Engine):
    name = "detect-secrets"
    binary = "detect-secrets"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["scan", "--all-files"]
        baseline_file = (cwd or path) / ".secrets.baseline"
        if baseline_file.exists():
            default_args.extend(["--baseline", str(baseline_file)])

        argv = [binary_path, *default_args, *args]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "results" in parsed:
                    for filename, secret_list in parsed["results"].items():
                        for secret in secret_list:
                            findings_raw.append({"file": filename, **secret})
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"detect-secrets exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            secret_type = item.get("type", "Secret")
            file_path = item.get("file", str(path))
            line = item.get("line_number", 0)
            redacted_msg = redact_secrets(f"Potential secret detected ({secret_type})")
            findings.append(
                {
                    "path": file_path,
                    "line": line,
                    "column": 0,
                    "rule": f"detect-secrets/{secret_type.lower()}",
                    "severity": "warn",
                    "message": redacted_msg,
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "warn" if findings else ("ok" if exit_code == 0 else "error")

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"detect-secrets: {len(findings)} secret(s) flagged",
            findings=findings,
            raw=raw.get("parsed"),
        )
