"""wasm-tools adapter for WebAssembly binary validation and component inspection."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class WasmToolsEngine(Engine):
    name = "wasm-tools"
    binary = "wasm-tools"
    file_extensions = ("wasm", "wat")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["validate"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        findings_raw: list[dict] = []
        if proc.returncode != 0:
            findings_raw.append(
                {
                    "file": str(path),
                    "error": proc.stderr.strip() or "WebAssembly validation failed",
                }
            )

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"valid": proc.returncode == 0},
            findings=findings_raw,
            summary=f"wasm-tools exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": "wasm-tools/validate",
                    "severity": "fail",
                    "message": item.get(
                        "error", "WebAssembly bytecode validation error"
                    ),
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
            summary=f"wasm-tools: {len(findings)} validation failure(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
