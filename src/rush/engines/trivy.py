"""Trivy vulnerability scanner adapter with offline scan default."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class TrivyEngine(Engine):
    name = "trivy"
    binary = "trivy"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["fs", "--format", "json", "--offline-scan", "--quiet"]
        argv = [binary_path, *default_args, *args, str(path)]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "Results" in parsed:
                    for target_res in parsed["Results"]:
                        target_file = target_res.get("Target", str(path))
                        for vuln in target_res.get("Vulnerabilities", []):
                            findings_raw.append(
                                {
                                    "target": target_file,
                                    "vuln_id": vuln.get(
                                        "VulnerabilityID", "CVE-UNKNOWN"
                                    ),
                                    "pkg_name": vuln.get("PkgName", ""),
                                    "installed_version": vuln.get(
                                        "InstalledVersion", ""
                                    ),
                                    "fixed_version": vuln.get("FixedVersion", ""),
                                    "severity": vuln.get("Severity", "UNKNOWN"),
                                    "title": vuln.get(
                                        "Title", vuln.get("VulnerabilityID", "")
                                    ),
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
            summary=f"trivy exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            sev = item.get("severity", "").upper()
            findings.append(
                {
                    "path": item.get("target", str(path)),
                    "line": 0,
                    "rule": item.get("vuln_id", "trivy-vuln"),
                    "severity": "error" if sev in {"CRITICAL", "HIGH"} else "warn",
                    "message": f"{item.get('pkg_name')} {item.get('installed_version')}: {item.get('title')}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        has_critical = any(f["severity"] == "error" for f in findings)
        status = (
            "fail"
            if has_critical
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"trivy: {len(findings)} vulnerability finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
