"""Lychee link-checker adapter with offline default mode."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class LycheeEngine(Engine):
    name = "lychee"
    binary = "lychee"
    file_extensions = ("md", "mdx", "html", "rst", "txt")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        # Default to offline mode unless explicitly configured
        default_args = ["--output", "json"]
        if not any("--offline" in arg or "--include-verbatim" in arg for arg in args):
            default_args.append("--offline")

        argv = [binary_path, *default_args, *args, str(path)]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "fail_map" in parsed:
                    for src_file, failed_urls in parsed["fail_map"].items():
                        for item in failed_urls:
                            findings_raw.append(
                                {
                                    "file": src_file,
                                    "url": item.get("url", ""),
                                    "status": item.get("status", {}),
                                }
                            )
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"lychee exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": 0,
                    "rule": "broken-link",
                    "severity": "warn",
                    "message": f"Broken link: {item.get('url')} ({item.get('status', 'failed')})",
                }
            )

        exit_code = raw.get("exit_code", 0)
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="warn" if findings else ("ok" if exit_code == 0 else "error"),
            duration_ms=raw.get("duration_ms", 0),
            summary=f"lychee: {len(findings)} broken link(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
