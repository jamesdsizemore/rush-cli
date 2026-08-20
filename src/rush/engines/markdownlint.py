"""markdownlint-cli v0.49.1 adapter for non-mutating Markdown checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..tools.base import Finding, ToolResult
from ..tools.common import error_result, resolve_binary, run_subprocess
from .base import Engine, EngineResult

DEFAULT_CONFIG = Path(__file__).with_name("_markdownlint-empty.json")
DEFAULT_IGNORE = Path(__file__).with_name("_markdownlint-empty.ignore")


class MarkdownlintEngine(Engine):
    """Run markdownlint-cli JSON mode without project config or ignore discovery."""

    name = "markdownlint-cli"
    binary = "markdownlint"
    file_extensions = ("md", "mdx")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        del cwd
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "--config",
                str(DEFAULT_CONFIG),
                "--ignore-path",
                str(DEFAULT_IGNORE),
                "--json",
                *args,
            ],
            cwd=path,
            timeout=120,
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        try:
            findings = _parse_report(json.loads(raw.get("stdout", "")), path)
        except (json.JSONDecodeError, TypeError, ValueError):
            return error_result(
                tool_name,
                self.name,
                "markdownlint returned malformed JSON",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="malformed_output",
            )
        expected_exit = 1 if findings else 0
        if raw.get("exit_code", 0) != expected_exit:
            return error_result(
                tool_name,
                self.name,
                "markdownlint exit code did not match its JSON findings",
                duration_ms=raw.get("duration_ms", 0),
                terminal_reason="nonzero_exit",
            )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=raw.get("duration_ms", 0),
            summary=f"markdownlint: {len(findings)} issue(s)",
            findings=findings,
            raw=None,
        )


def _parse_report(report: Any, path: Path) -> list[Finding]:
    if not isinstance(report, list):
        raise TypeError("markdownlint JSON report must be a list")
    findings: list[Finding] = []
    for item in report:
        if not isinstance(item, dict):
            raise TypeError("markdownlint finding must be an object")
        rules = item.get("ruleNames")
        line = item.get("lineNumber")
        description = item.get("ruleDescription")
        if not isinstance(rules, list) or not rules or not isinstance(rules[0], str):
            raise TypeError("markdownlint finding lacks rule name")
        if not isinstance(line, int) or not isinstance(description, str):
            raise TypeError("markdownlint finding lacks location")
        detail = item.get("errorDetail")
        message = f"{description}: {detail}" if isinstance(detail, str) else description
        findings.append(
            {
                "rule": rules[0],
                "severity": "warn",
                "message": message,
                "path": str(path),
                "line": line,
            }
        )
    return findings
