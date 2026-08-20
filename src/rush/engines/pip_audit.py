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
from pathlib import Path
from typing import Any

from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class PipAuditEngine(Engine):
    name = "pip-audit"
    binary = "pip-audit"
    file_extensions = ("py", "toml")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary

        # Never inspect the interpreter's installed environment: that would
        # make a target-path request report unrelated local dependencies.
        # The bounded Phase 03 route accepts only an explicit requirements
        # file within the requested project.
        requirements = path if path.is_file() else path / "requirements.txt"
        argv = [
            binary_path,
            "--format=json",
            "--strict",  # treat non-zero exit from underlying pip as failure
            "--requirement",
            str(requirements),
            *args,
        ]
        proc = run_subprocess(argv, cwd=cwd, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                findings_raw = _parse_dependencies(parsed)
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
        from ..tools.base import ToolResult
        from ..tools.common import elapsed_ms, normalize_findings

        all_vulns: list[dict] = []
        for pkg in raw.get("findings", []):
            pkg_name = pkg.get("package") or pkg.get("name", "?")
            pkg_version = pkg.get("version", "?")
            for v in pkg.get("vulns", []):
                fix = v.get("fix_versions", [])
                fix_str = (
                    f" (fix: upgrade to {', '.join(fix)})" if fix else " (no fix yet)"
                )
                all_vulns.append(
                    {
                        "path": str(path),
                        "line": 0,
                        "rule": v.get("id", ""),
                        "severity": "error",  # all vulns are error severity for v0.1
                        "message": f"{pkg_name}=={pkg_version}: {v.get('description', 'vulnerability')[:200]}{fix_str}",
                    }
                )

        findings = normalize_findings(all_vulns)

        exit_code = raw.get("exit_code", 0)
        # pip-audit exit semantics:
        #   0 = no vulns
        #   1 = vulns found (findings is non-empty)
        #   >= 2 = actual error (config, network, etc.)
        if raw.get("stdout", "").strip() and raw.get("parsed") is None:
            status = "error"
            summary = "pip-audit returned malformed JSON"
        elif exit_code == 0:
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


def _parse_dependencies(payload: Any) -> list[dict]:
    """Extract dependency rows from pip-audit's supported JSON envelopes."""
    if isinstance(payload, list):  # pip-audit < 2.10
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):  # pip-audit >= 2.10
        dependencies = payload.get("dependencies", [])
        if isinstance(dependencies, list):
            return [item for item in dependencies if isinstance(item, dict)]
    return []
