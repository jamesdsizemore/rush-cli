"""Stylelint adapter for CSS, SCSS, and CSS-in-JS linting."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class StylelintEngine(Engine):
    name = "stylelint"
    binary = "stylelint"
    file_extensions = ("css", "scss", "sass", "less")

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
                        for warning in file_res.get("warnings", []):
                            findings_raw.append(
                                {"source": file_res.get("source"), **warning}
                            )
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"stylelint exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            severity = item.get("severity", "warning").lower()
            findings.append(
                {
                    "path": item.get("source", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": f"stylelint/{item.get('rule', 'syntax')}",
                    "severity": "fail" if severity == "error" else "warn",
                    "message": item.get("text", "Stylelint CSS rule violation"),
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
            summary=f"stylelint: {len(findings)} stylesheet issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
