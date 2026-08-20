"""Hadolint v2.15.1 adapter for safe local Containerfile checks."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..tools.base import Finding, ToolResult
from ..tools.common import error_result, resolve_binary, run_subprocess
from .base import Engine, EngineResult

DEFAULT_CONFIG = Path(__file__).with_name("_hadolint-empty.yaml")


class HadolintEngine(Engine):
    """Run Hadolint JSON mode with Rush's empty config, never project defaults."""

    name = "hadolint"
    binary = "hadolint"
    file_extensions = ("dockerfile", "containerfile")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        del args, cwd
        source = path
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "--config",
                str(DEFAULT_CONFIG),
                "--format",
                "json",
                "--no-color",
                str(source),
            ],
            cwd=source.parent if source.is_file() else source,
            timeout=120,
            env=_hadolint_environment(),
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        try:
            report = json.loads(raw.get("stdout", ""))
            findings = _parse_hadolint_report(report, path)
        except (json.JSONDecodeError, TypeError, ValueError):
            return error_result(
                tool_name,
                self.name,
                "hadolint returned malformed JSON",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="malformed_output",
            )
        exit_code = raw.get("exit_code", 0)
        expected_exit_code = 1 if findings else 0
        if exit_code != expected_exit_code:
            return error_result(
                tool_name,
                self.name,
                "hadolint exit code did not match its JSON findings",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="nonzero_exit",
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"hadolint: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )


def _hadolint_environment() -> dict[str, str]:
    """Pass only process essentials, excluding all Hadolint environment config."""
    keys = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
    )
    return {key: os.environ[key] for key in keys if key in os.environ}


def _parse_hadolint_report(report: Any, path: Path) -> list[Finding]:
    if not isinstance(report, list):
        raise TypeError("Hadolint JSON report must be a list")
    root = path if path.is_dir() else path.parent
    findings: list[Finding] = []
    for item in report:
        if not isinstance(item, dict):
            raise TypeError("Hadolint finding must be an object")
        code = item.get("code")
        message = item.get("message")
        line = item.get("line")
        column = item.get("column")
        if (
            not isinstance(code, str)
            or not isinstance(message, str)
            or not isinstance(line, int)
        ):
            raise TypeError("Hadolint finding lacks required fields")
        reported = item.get("file")
        filename = Path(reported) if isinstance(reported, str) else Path("Dockerfile")
        target = filename if filename.is_absolute() else root / filename
        try:
            target.resolve().relative_to(root.resolve())
        except ValueError as error:
            raise ValueError("Hadolint reported a path outside the target") from error
        finding: Finding = {
            "rule": code,
            "severity": _severity(item.get("level")),
            "message": message,
            "path": str(target),
            "line": line,
        }
        if isinstance(column, int):
            finding["column"] = column
        findings.append(finding)
    return findings


def _severity(value: object) -> str:
    return {"error": "error", "warning": "warn", "info": "info", "style": "info"}.get(
        str(value).lower(), "warn"
    )
