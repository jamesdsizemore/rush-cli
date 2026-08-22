"""Contained SQLFluff v4.3.0 JSON adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..tools.base import Finding, ToolResult
from ..tools.common import error_result, resolve_binary, run_subprocess
from .base import Engine, EngineResult

DEFAULT_CONFIG = Path(__file__).with_name("_sqlfluff.ini")


class SqlfluffEngine(Engine):
    name = "sqlfluff"
    binary = "sqlfluff"
    file_extensions = ("sql",)

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        sources = [Path(arg) for arg in args] or [path]
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "lint",
                "--ignore-local-config",
                "--config",
                str(DEFAULT_CONFIG),
                "--dialect",
                "ansi",
                "--templater",
                "raw",
                "--format",
                "json",
                "--processes",
                "1",
                *(str(source) for source in sources),
            ],
            cwd=cwd or path.parent,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        try:
            findings = _parse(json.loads(raw.get("stdout", "")), path)
        except (TypeError, ValueError, json.JSONDecodeError):
            return error_result(
                tool_name,
                self.name,
                "sqlfluff returned malformed JSON",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="malformed_output",
            )
        if raw.get("exit_code", 0) != (1 if findings else 0):
            return error_result(
                tool_name,
                self.name,
                "sqlfluff exit code did not match its JSON findings",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="nonzero_exit",
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"sqlfluff: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )


def _parse(report: Any, root: Path) -> list[Finding]:
    if not isinstance(report, list):
        raise TypeError("report must be a list")
    findings: list[Finding] = []
    for file_result in report:
        if (
            not isinstance(file_result, dict)
            or not isinstance(file_result.get("filepath"), str)
            or not isinstance(file_result.get("violations"), list)
        ):
            raise TypeError("invalid file result")
        raw_target = Path(file_result["filepath"])
        target = raw_target if raw_target.is_absolute() else (root / raw_target)
        for item in file_result["violations"]:
            if not isinstance(item, dict):
                raise TypeError("invalid violation")
            code = item.get("code")
            desc = item.get("description")
            line = item.get("line_no") or item.get("start_line_no", 1)
            pos = item.get("line_pos") or item.get("start_line_pos", 1)
            if (
                not isinstance(code, str)
                or not isinstance(desc, str)
                or not isinstance(line, int)
                or not isinstance(pos, int)
            ):
                raise TypeError("invalid violation fields")
            findings.append(
                {
                    "rule": code,
                    "severity": "warn",
                    "message": desc,
                    "path": str(target),
                    "line": line,
                    "column": pos,
                }
            )
    return findings
