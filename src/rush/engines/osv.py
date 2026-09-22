"""Offline-only OSV-Scanner JSON adapter for explicit local lockfiles."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs


class OsvScannerEngine(Engine):
    """Run OSV-Scanner only against a local DB; never refresh or query remotely."""

    name = "osv-scanner"
    binary = "osv-scanner"
    file_extensions: tuple[str, ...] = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        # `path` is either an explicit lockfile (reference-test contract:
        # -L against that exact file) or a project directory -- the real
        # `run_engine` call site (project_run.py) always passes the project
        # root, never a discovered lockfile. `-L <directory>` is an invalid
        # osv-scanner invocation (wrong extractor for a directory); a
        # directory gets osv-scanner's own directory-scan mode instead,
        # with --allow-no-lockfiles so "no lockfile in this project" is its
        # own clean exit 0/empty-results outcome rather than a scan error.
        if path.is_dir():
            argv = [
                binary_path,
                "scan",
                "--offline",
                "--allow-no-lockfiles",
                "--format",
                "json",
                str(path),
                *args,
            ]
        else:
            argv = [
                binary_path,
                "scan",
                "--offline",
                "--format",
                "json",
                "-L",
                str(path),
                *args,
            ]
        proc = run_subprocess(
            argv,
            cwd=cwd,
            timeout=120,
            **ownership_kwargs(owner_instance_id, run_id),
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
        findings: list[Finding] = []
        parsed = raw.get("parsed")
        if isinstance(parsed, dict):
            # `--allow-no-lockfiles` reports "results": null (not []) when a
            # scanned directory has no lockfiles at all.
            for result in parsed.get("results") or []:
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
        stderr_text = raw.get("stderr") or ""
        # osv-scanner exits nonzero (127) when its offline database cache is
        # missing/stale -- a real, expected "can't check vulnerabilities
        # right now" outcome for an offline-only scanner, not a scan crash.
        db_unavailable = (
            "no offline version of the OSV database is available" in stderr_text
        )
        if findings:
            status: ToolStatus = "fail"
            summary = f"osv-scanner: {len(findings)} known vulnerabilit{'y' if len(findings) == 1 else 'ies'}"
        elif db_unavailable:
            status = "skipped"
            summary = "osv-scanner: no offline vulnerability database available"
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
