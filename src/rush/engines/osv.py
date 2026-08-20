"""Offline-only OSV-Scanner JSON adapter for explicit local lockfiles."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class OsvScannerEngine(Engine):
    """Run OSV-Scanner only against a local DB; never refresh or query remotely."""

    name = "osv-scanner"
    binary = "osv-scanner"
    file_extensions: tuple[str, ...] = ()

    def run(self, path: Path, args: list[str], cwd: Path | None = None) -> EngineResult:
        proc = run_subprocess(
            [
                resolve_binary(self.binary) or self.binary,
                "scan",
                "--offline",
                "--format",
                "json",
                "-L",
                str(path),
                *args,
            ],
            cwd=cwd,
            timeout=120,
        )
        parsed = None
        if proc.stdout.strip():
            try:
                candidate = json.loads(proc.stdout)
                if isinstance(candidate, dict):
                    parsed = candidate
            except json.JSONDecodeError:
                pass
        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=[],
            summary=f"osv-scanner exit {proc.returncode}",
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[dict[str, object]] = []
        parsed = raw.get("parsed")
        if isinstance(parsed, dict):
            for result in parsed.get("results", []):
                if not isinstance(result, dict):
                    continue
                source = result.get("source", {})
                source_path = (
                    source.get("path", str(path))
                    if isinstance(source, dict)
                    else str(path)
                )
                for package_entry in result.get("packages", []):
                    if not isinstance(package_entry, dict):
                        continue
                    package = package_entry.get("package", {})
                    if not isinstance(package, dict):
                        continue
                    name = package.get("name", "unknown")
                    version = package.get("version", "unknown")
                    ecosystem = package.get("ecosystem", "unknown")
                    for vulnerability in package_entry.get("vulnerabilities", []):
                        if not isinstance(vulnerability, dict):
                            continue
                        rule = vulnerability.get("id", "osv-scanner")
                        fixed = vulnerability.get("fixed_version")
                        remediation = (
                            f"fixed in {fixed}" if fixed else "no fix recorded"
                        )
                        findings.append(
                            {
                                "path": str(source_path),
                                "line": 0,
                                "rule": str(rule),
                                "severity": "error",
                                "message": f"{ecosystem} {name}=={version}: {remediation}",
                            }
                        )
        exit_code = raw.get("exit_code", 0)
        if findings:
            status = "fail"
            summary = f"osv-scanner: {len(findings)} known vulnerabilit{'y' if len(findings) == 1 else 'ies'}"
        elif exit_code == 0 and parsed is not None:
            status = "ok"
            summary = "osv-scanner: no known vulnerabilities"
        else:
            status = "error"
            summary = f"osv-scanner error (exit {exit_code})"
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=summary,
            findings=findings,
            raw=parsed,
            metadata={
                "database_freshness": "unknown-offline",
                "evidence_source": "local-offline-database",
            },
        )
