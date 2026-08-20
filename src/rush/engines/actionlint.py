"""actionlint v1.7.12 adapter for local GitHub Actions workflow checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..tools.base import Finding, ToolResult
from ..tools.common import error_result, resolve_binary, run_subprocess
from .base import Engine, EngineResult

DEFAULT_CONFIG = Path(__file__).with_name("_actionlint-empty.yaml")


class ActionlintEngine(Engine):
    """Run actionlint JSON mode without project config or child integrations."""

    name = "actionlint"
    binary = "actionlint"
    file_extensions = ("yml", "yaml")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        del args, cwd
        source = path
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "-config-file",
                str(DEFAULT_CONFIG),
                "-shellcheck=",
                "-pyflakes=",
                "-no-color",
                "-format",
                "{{json .}}",
                str(source),
            ],
            cwd=source.parent if source.is_file() else source,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        try:
            report = json.loads(raw.get("stdout", ""))
            findings = _parse_actionlint_report(report, path)
        except (json.JSONDecodeError, TypeError, ValueError):
            return error_result(
                tool_name,
                self.name,
                "actionlint returned malformed JSON",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="malformed_output",
            )
        exit_code = raw.get("exit_code", 0)
        expected_exit_code = 1 if findings else 0
        if exit_code != expected_exit_code:
            return error_result(
                tool_name,
                self.name,
                "actionlint exit code did not match its JSON findings",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="nonzero_exit",
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"actionlint: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )


def _parse_actionlint_report(report: Any, path: Path) -> list[Finding]:
    if not isinstance(report, list):
        raise TypeError("actionlint JSON report must be a list")
    root = path if path.is_dir() else path.parent
    findings: list[Finding] = []
    for item in report:
        if not isinstance(item, dict):
            raise TypeError("actionlint finding must be an object")
        kind = item.get("kind")
        message = item.get("message")
        line = item.get("line")
        column = item.get("column")
        filepath = item.get("filepath")
        if (
            not isinstance(kind, str)
            or not isinstance(message, str)
            or not isinstance(line, int)
            or not isinstance(filepath, str)
        ):
            raise TypeError("actionlint finding lacks required fields")
        filename = Path(filepath)
        target = filename if filename.is_absolute() else root / filename
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise ValueError("actionlint reported a path outside the target") from error
        finding: Finding = {
            "rule": kind,
            "severity": "warn",
            "message": message,
            "path": str(target),
            "line": line,
        }
        if isinstance(column, int):
            finding["column"] = column
        findings.append(finding)
    return findings
