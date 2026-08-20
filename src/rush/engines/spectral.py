"""Spectral v6.16.3 adapter for contained local YAML/OpenAPI checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..tools.base import Finding, ToolResult
from ..tools.common import error_result, resolve_binary, run_subprocess
from .base import Engine, EngineResult

DEFAULT_RULESET = Path(__file__).with_name("_spectral-ruleset.yaml")
_REMOTE_REF = re.compile(r"\$ref\s*:\s*['\"]?(?:https?|file)://")


class SpectralEngine(Engine):
    """Run Spectral JSON mode with a Rush-owned local ruleset only."""

    name = "spectral"
    binary = "spectral"
    file_extensions = ("yml", "yaml")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        sources = [Path(arg) for arg in args] or [path]
        for source in sources:
            if source.is_file() and _REMOTE_REF.search(
                source.read_text(encoding="utf-8")
            ):
                return EngineResult(
                    exit_code=2,
                    stdout="",
                    stderr=f"remote reference blocked: {source}",
                )
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "lint",
                "--ruleset",
                str(DEFAULT_RULESET),
                "--format",
                "json",
                "--fail-severity",
                "warn",
                "--ignore-unknown-format",
                *(str(source) for source in sources),
            ],
            cwd=cwd or (path.parent if path.is_file() else path),
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        try:
            report = json.loads(raw.get("stdout", ""))
            findings = _parse_spectral_report(report, path)
        except (json.JSONDecodeError, TypeError, ValueError):
            return error_result(
                tool_name,
                self.name,
                "spectral returned malformed JSON",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="malformed_output",
            )
        exit_code = raw.get("exit_code", 0)
        expected_exit_code = 1 if findings else 0
        if exit_code != expected_exit_code:
            return error_result(
                tool_name,
                self.name,
                "spectral exit code did not match its JSON findings",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="nonzero_exit",
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="fail"
            if any(item["severity"] == "error" for item in findings)
            else "warn"
            if findings
            else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"spectral: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )


def _parse_spectral_report(report: Any, path: Path) -> list[Finding]:
    if not isinstance(report, list):
        raise TypeError("spectral JSON report must be a list")
    root = path if path.is_dir() else path.parent
    findings: list[Finding] = []
    for item in report:
        if not isinstance(item, dict):
            raise TypeError("spectral finding must be an object")
        code = item.get("code")
        message = item.get("message")
        severity = item.get("severity")
        range_ = item.get("range")
        if (
            not isinstance(code, str)
            or not isinstance(message, str)
            or not isinstance(severity, int)
        ):
            raise TypeError("spectral finding lacks required fields")
        if not isinstance(range_, dict) or not isinstance(range_.get("start"), dict):
            raise TypeError("spectral finding lacks a source range")
        start = range_["start"]
        line = start.get("line")
        column = start.get("character")
        if not isinstance(line, int) or not isinstance(column, int):
            raise TypeError("spectral source range is invalid")
        source = item.get("source")
        target = root
        if isinstance(source, str):
            candidate = Path(source)
            target = candidate if candidate.is_absolute() else root / candidate
            try:
                target.resolve().relative_to(root.resolve())
            except ValueError as error:
                raise ValueError(
                    "spectral reported a path outside the target"
                ) from error
        finding: Finding = {
            "rule": code,
            "severity": "error" if severity == 0 else "warn",
            "message": message,
            "path": str(target),
            "line": line + 1,
            "column": column + 1,
        }
        findings.append(finding)
    return findings
