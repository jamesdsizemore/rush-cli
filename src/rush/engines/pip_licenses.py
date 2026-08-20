"""Pip-licenses adapter for Python package license risk auditing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class PipLicensesEngine(Engine):
    name = "pip-licenses"
    binary = "pip-licenses"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--format=json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    for pkg in parsed:
                        lic = pkg.get("License", "").lower()
                        if "gpl" in lic or "agpl" in lic or "unknown" in lic:
                            findings_raw.append(pkg)
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"pip-licenses exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            pkg_name = item.get("Name", "unknown-package")
            version = item.get("Version", "")
            license_name = item.get("License", "Unknown")
            is_copyleft = (
                "gpl" in license_name.lower() or "agpl" in license_name.lower()
            )
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"license/{license_name.lower().replace(' ', '-')}",
                    "severity": "warn" if is_copyleft else "info",
                    "message": f"Package '{pkg_name}' ({version}) has license '{license_name}'",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "warn"
            if any(f["severity"] == "warn" for f in findings)
            else ("ok" if exit_code == 0 else "error")
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"pip-licenses: {len(findings)} flagged dependency license(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
