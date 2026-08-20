"""HTML-Validate adapter for strict W3C HTML validation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class HtmlValidateEngine(Engine):
    name = "html-validate"
    binary = "html-validate"
    file_extensions = ("html", "htm", "vue", "svelte")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--formatter", "json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    for file_res in parsed:
                        for msg in file_res.get("messages", []):
                            findings_raw.append(
                                {"filePath": file_res.get("filePath"), **msg}
                            )
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"html-validate exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            severity = item.get("severity", 1)  # 2 is error, 1 is warning
            findings.append(
                {
                    "path": item.get("filePath", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": f"html-validate/{item.get('ruleId', 'html-error')}",
                    "severity": "fail" if severity == 2 else "warn",
                    "message": item.get("message", "HTML validation error"),
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
            summary=f"html-validate: {len(findings)} HTML validation issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
