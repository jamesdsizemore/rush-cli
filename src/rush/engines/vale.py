"""Vale adapter for syntax-aware documentation and prose style linting."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ValeEngine(Engine):
    name = "vale"
    binary = "vale"
    file_extensions = ("md", "mdx", "rst", "adoc", "html", "txt")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--output=JSON", "--no-wrap"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict):
                    for file_path, alerts in parsed.items():
                        for alert in alerts:
                            findings_raw.append({"file": file_path, **alert})
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"vale exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            severity = item.get("Severity", "warning").lower()
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("Line", 0),
                    "column": item.get("Span", [0])[0],
                    "rule": f"vale/{item.get('Check', 'style')}",
                    "severity": "fail" if severity == "error" else "warn",
                    "message": item.get("Message", "Prose style recommendation"),
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
            summary=f"vale: {len(findings)} prose style issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
