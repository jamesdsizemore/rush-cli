"""Secretlint adapter for fast pre-commit secret and credential linting."""

from __future__ import annotations

import json
from pathlib import Path

from ..logging import redact_secrets
from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class SecretlintEngine(Engine):
    name = "secretlint"
    binary = "secretlint"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--format", "json"]
        argv = [binary_path, *default_args, *args, "**/*"]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"secretlint exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for file_item in raw.get("findings", []):
            file_path = file_item.get("filePath", str(path))
            for msg in file_item.get("messages", []):
                redacted_msg = redact_secrets(msg.get("message", "Secret detected"))
                findings.append(
                    {
                        "path": file_path,
                        "line": msg.get("line", 0),
                        "column": msg.get("column", 0),
                        "rule": msg.get("ruleId", "secretlint-rule"),
                        "severity": "fail"
                        if msg.get("severity") == "error"
                        else "warn",
                        "message": redacted_msg,
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
            summary=f"secretlint: {len(findings)} secret message(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
