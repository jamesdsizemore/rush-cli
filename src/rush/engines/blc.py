"""Broken-Link-Checker (blc) adapter for recursive link validation."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class BlcEngine(Engine):
    name = "blc"
    binary = "blc"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        target = str(path) if str(path).startswith("http") else "http://localhost:3000"
        default_args = [target, "-ro", "--json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            try:
                item = json.loads(line_str)
                if item.get("broken", False):
                    findings_raw.append(item)
            except json.JSONDecodeError:
                if "BROKEN" in line_str:
                    findings_raw.append({"url": line_str, "broken": True})

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"broken_links": findings_raw},
            findings=findings_raw,
            summary=f"blc exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            url = (
                item.get("url", {}).get("resolved")
                if isinstance(item.get("url"), dict)
                else item.get("url", str(path))
            )
            reason = item.get("brokenReason", "BROKEN_LINK")
            findings.append(
                {
                    "path": str(url),
                    "line": 0,
                    "column": 0,
                    "rule": f"blc/{reason.lower()}",
                    "severity": "warn",
                    "message": f"Broken hyperlink encountered: {url} ({reason})",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "warn" if findings else ("ok" if exit_code == 0 else "error")

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"blc: {len(findings)} broken hyperlink(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
