"""Buf adapter for Protocol Buffers and gRPC schema linting."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class BufEngine(Engine):
    name = "buf"
    binary = "buf"
    file_extensions = ("proto",)

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["lint", "--error-format=json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str:
                continue
            try:
                item = json.loads(line_str)
                findings_raw.append(item)
            except json.JSONDecodeError:
                pass

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"issues": findings_raw},
            findings=findings_raw,
            summary=f"buf exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": item.get("start_line", 0),
                    "column": item.get("start_column", 0),
                    "rule": f"buf/{item.get('type', 'protobuf-lint')}",
                    "severity": "fail",
                    "message": item.get(
                        "message", "Protocol Buffer schema lint violation"
                    ),
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
            summary=f"buf: {len(findings)} protobuf lint violation(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
