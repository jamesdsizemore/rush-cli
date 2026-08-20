"""Critical adapter for above-the-fold CSS extraction."""

from __future__ import annotations

from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class CriticalEngine(Engine):
    name = "critical"
    binary = "critical"
    file_extensions = ("html", "htm")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--base", str(cwd or path), "--inline", "--dry-run"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        findings_raw: list[dict] = []
        if proc.returncode != 0 and proc.stderr:
            findings_raw.append({"error": proc.stderr.strip()})

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"critical_css": proc.stdout},
            findings=findings_raw,
            summary=f"critical exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": "critical/extraction-error",
                    "severity": "warn",
                    "message": f"Critical CSS generation issue: {item.get('error', 'unknown')}",
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
            summary=f"critical: critical CSS generation completed ({len(findings)} issue(s))",
            findings=findings,
            raw=raw.get("parsed"),
        )
