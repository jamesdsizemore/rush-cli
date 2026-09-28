"""Trivy vulnerability scanner adapter with offline scan default."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs


class TrivyEngine(Engine):
    name = "trivy"
    binary = "trivy"
    file_extensions = ()

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
        default_args = ["fs", "--format", "json", "--offline-scan", "--quiet"]
        argv = [binary_path, *default_args, *args, str(path)]
        proc = run_subprocess(
            argv,
            cwd=cwd or path,
            timeout=180,
            **ownership_kwargs(owner_instance_id, run_id),
        )

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "Results" in parsed:
                    # M20: Trivy's own top-level `Target` field is not a
                    # generic `_PATH_KEYS` name (`engines/staging.py`
                    # deliberately never treats every key literally named
                    # `Target`/`source` as a path -- an unrelated engine's
                    # own `Target` field could mean anything else).
                    # Adapter-specific remap, in place, before this decoded
                    # `parsed` object becomes both `findings_raw[].target`
                    # and this result's own `raw` field -- one remap fixes
                    # both, and is a no-op (returns the value unchanged)
                    # once this engine ever runs outside a staged attempt.
                    from .staging import active_staging, map_staged_path

                    staging = active_staging()
                    for target_res in parsed["Results"]:
                        target = target_res.get("Target")
                        if staging is not None and isinstance(target, str):
                            target_res["Target"] = map_staged_path(
                                target, staging.staged_root, staging.original_root
                            )
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
        findings: list[Finding] = []
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
        status: ToolStatus = (
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
