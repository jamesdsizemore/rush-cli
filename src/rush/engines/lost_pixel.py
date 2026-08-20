"""Lost Pixel adapter for Storybook, Next.js, and Ladle visual regression testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class LostPixelEngine(Engine):
    name = "lost-pixel"
    binary = "lost-pixel"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["update", "--json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=240)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "differences" in parsed:
                    findings_raw = parsed["differences"]
                elif isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"lost-pixel exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("storyId", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": "lost-pixel/visual-diff",
                    "severity": "fail",
                    "message": f"Visual regression difference detected in story '{item.get('name', 'component')}'",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = "fail" if (findings or exit_code != 0) else "ok"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"lost-pixel: {len(findings)} visual difference(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
