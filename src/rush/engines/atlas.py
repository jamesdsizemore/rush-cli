"""Atlas adapter for declarative database schema and migration safety linting."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class AtlasEngine(Engine):
    name = "atlas"
    binary = "atlas"
    file_extensions = ("sql", "hcl")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "migrate",
            "lint",
            "--dir",
            f"file://{path}",
            "--format",
            "{{ json . }}",
        ]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "Files" in parsed:
                    for file_item in parsed["Files"]:
                        for report in file_item.get("Reports", []):
                            findings_raw.append(
                                {"file": file_item.get("Name"), **report}
                            )
                elif isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"atlas exit {proc.returncode}",
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
                    "rule": f"atlas/{item.get('Text', 'migration-risk').lower().replace(' ', '-')}",
                    "severity": "fail" if item.get("Level") == "ERROR" else "warn",
                    "message": item.get("Text", "Database migration safety check"),
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
            summary=f"atlas: {len(findings)} schema migration issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
