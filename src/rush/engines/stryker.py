"""Stryker Mutator adapter for JavaScript/TypeScript and C# mutation testing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class StrykerEngine(Engine):
    name = "stryker"
    binary = "stryker"
    file_extensions = ("js", "jsx", "ts", "tsx", "cs")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["run", "--reporters", "json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        parsed = None
        report_file = (cwd or path) / "reports" / "mutation" / "mutation.json"
        if report_file.exists():
            try:
                parsed = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                parsed = None
        elif proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                parsed = None

        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "files" in parsed:
            for file_path, file_data in parsed["files"].items():
                for mutant in file_data.get("mutants", []):
                    if mutant.get("status") == "Survived":
                        findings_raw.append({"file": file_path, **mutant})

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"stryker exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("location", {}).get("start", {}).get("line", 0),
                    "column": item.get("location", {})
                    .get("start", {})
                    .get("column", 0),
                    "rule": f"stryker/{item.get('mutatorName', 'mutation')}",
                    "severity": "warn",
                    "message": f"Mutant survived: {item.get('replacement', 'code change')} was not caught by test suite",
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
            summary=f"stryker: {len(findings)} survived mutant(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
