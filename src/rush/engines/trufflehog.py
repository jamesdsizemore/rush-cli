"""TruffleHog adapter for deep and high-entropy secret scanning."""

from __future__ import annotations

import json
from pathlib import Path

from ..logging import redact_secrets
from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class TruffleHogEngine(Engine):
    name = "trufflehog"
    binary = "trufflehog"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["filesystem", "--json", "--no-verification", "--no-update"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        findings_raw: list[dict] = []
        if proc.stdout.strip():
            for line in proc.stdout.splitlines():
                if not line.strip():
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        findings_raw.append(obj)
                except json.JSONDecodeError:
                    pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"findings": findings_raw},
            findings=findings_raw,
            summary=f"trufflehog exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            detector = item.get("DetectorName", "Secret")
            source_meta = (
                item.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {})
            )
            file_path = source_meta.get("file", str(path))
            line = source_meta.get("line", 0)
            raw_secret = item.get("Raw", "")
            redacted_message = redact_secrets(f"Found {detector} secret: {raw_secret}")

            findings.append(
                {
                    "path": file_path,
                    "line": line,
                    "column": 0,
                    "rule": f"trufflehog/{detector.lower()}",
                    "severity": "fail" if item.get("Verified") else "warn",
                    "message": redacted_message,
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
            summary=f"trufflehog: {len(findings)} secret(s) found",
            findings=findings,
            raw=raw.get("parsed"),
        )
