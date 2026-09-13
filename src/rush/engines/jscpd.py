"""jscpd adapter for duplicated JavaScript/TypeScript code analysis."""

from __future__ import annotations

import re
from pathlib import Path

from ..tools.base import Finding, ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class JscpdEngine(Engine):
    name = "jscpd"
    binary = "jscpd"
    file_extensions = ("js", "jsx", "mjs", "cjs", "ts", "tsx")

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [resolve_binary(self.binary) or self.binary, *args], cwd=cwd, timeout=120
        )
        return EngineResult(
            exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    # jscpd 5.x (Rust engine) console format, e.g.:
    #   Clone found (typescript):
    #    - a.ts [4:19 - 10:2] (7 lines, 21 tokens)
    #      b.ts [4:20 - 10:2]
    # jscpd wraps parts of this in ANSI escapes even when stdout is piped, so
    # those are stripped before either pattern is applied.
    _ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
    _HEADER_RE = re.compile(r"^Clone found \([^)]*\):?$")
    _FILE_RE = re.compile(
        r"^\s*-?\s*(?P<path>\S+)\s*\[(?P<start_line>\d+):\d+\s*-\s*\d+:\d+\]"
        r"(?:\s*\((?P<lines>\d+) lines, \d+ tokens\))?\s*$"
    )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        text = self._ANSI_RE.sub("", raw.get("stdout", ""))
        lines = text.splitlines()
        findings: list[Finding] = []
        i = 0
        while i < len(lines):
            if not self._HEADER_RE.match(lines[i]):
                i += 1
                continue
            i += 1
            block: list[re.Match[str]] = []
            while i < len(lines):
                match = self._FILE_RE.match(lines[i])
                if not match:
                    break
                block.append(match)
                i += 1
            if len(block) < 2:
                continue
            paths = [m["path"] for m in block]
            clone_lines = next((m["lines"] for m in block if m["lines"]), None)
            detail = f"{clone_lines} lines" if clone_lines else "duplicate block"
            for match in block:
                others = [p for p in paths if p != match["path"]]
                findings.append(
                    {
                        "path": match["path"],
                        "line": int(match["start_line"]),
                        "rule": "jscpd",
                        "severity": "warn",
                        "message": f"duplicates {', '.join(others)} ({detail})",
                    }
                )
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else "ok",
            duration_ms=0,
            summary=f"jscpd: {len(findings)} duplicate(s)",
            findings=findings,
            raw=None,
        )
