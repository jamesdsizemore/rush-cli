"""pip-audit engine — Python dependency vulnerability scanner.

JSON output schema (pip-audit >=2):
    [
        {
            "package": "requests",
            "version": "2.25.0",
            "vulns": [
                {
                    "id": "PYSEC-2021-...",
                    "fix_versions": ["2.26.0"],
                    "description": "...",
                    "cvss_v3": {"base_score": 7.5, ...} | None
                }
            ]
        }
    ]
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from ..tools.common import resolve_binary
from .base import Engine, EngineResult


class PipAuditEngine(Engine):
    name = "pip-audit"
    binary = "pip-audit"
    file_extensions = ("py", "toml")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary

        # pip-audit scans the env's installed packages by default. To scan a
        # project's requirements, we'd need to point it at requirements.txt
        # or pyproject.toml. For v0.1, scan the active venv (or the user can
        # `pip-audit -r requirements.txt` via custom args).
        argv = [
            binary_path,
            "--format=json",
            "--strict",  # treat non-zero exit from underlying pip as failure
            *args,
        ]
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            timeout=180,
            capture_output=True,
            text=True,
            check=False,
        )

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"pip-audit exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.common import elapsed_ms, normalize_findings
        from ..tools.base import ToolResult

        all_vulns: list[dict] = []
        for pkg in raw.get("findings", []):
            pkg_name = pkg.get("package", "?")
            pkg_version = pkg.get("version", "?")
            for v in pkg.get("vulns", []):
                fix = v.get("fix_versions", [])
                fix_str = f" (fix: upgrade to {', '.join(fix)})" if fix else " (no fix yet)"
                all_vulns.append({
                    "path": str(path),
                    "line": 0,
                    "rule": v.get("id", ""),
                    "severity": "error",  # all vulns are error severity for v0.1
                    "message": f"{pkg_name}=={pkg_version}: {v.get('description', 'vulnerability')[:200]}{fix_str}",
                })

        findings = normalize_findings(all_vulns)

        exit_code = raw.get("exit_code", 0)
        # pip-audit exit semantics:
        #   0 = no vulns
        #   1 = vulns found (findings is non-empty)
        #   >= 2 = actual error (config, network, etc.)
        if exit_code == 0:
            status = "ok"
            summary = "pip-audit: no known vulnerabilities"
        elif exit_code == 1 and findings:
            status = "fail"
            summary = f"pip-audit: {len(findings)} vulnerabilit{'y' if len(findings) == 1 else 'ies'}"
        elif exit_code == 1 and raw.get("parsed") is None:
            # exit 1 but couldn't parse JSON → real error
            status = "error"
            summary = f"pip-audit error (exit 1, no JSON): {(raw.get('stderr') or '').strip().splitlines()[0] if raw.get('stderr') else 'unknown'}"
        elif exit_code >= 2:
            status = "error"
            summary = f"pip-audit error (exit {exit_code}): {(raw.get('stderr') or '').strip().splitlines()[0] if raw.get('stderr') else 'unknown'}"
        else:
            status = "ok"
            summary = "pip-audit: clean"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", elapsed_ms(0)),
            summary=summary,
            findings=findings,
            raw=raw.get("parsed"),
        )
