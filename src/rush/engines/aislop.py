"""aislop adapter for AI-generated code anti-pattern detection."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from ..permissions import ExecutionPermissions, build_execution_metadata
from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess, skipped_result
from .base import Engine, EngineResult, env_kwargs, ownership_kwargs

# aislop runs its npm package through `npx`, which downloads it on a cold npm
# cache. The calling tool's grants are ambient here (context-local, like
# `cancel_scope`); without `download`, npm runs offline.
_GRANTS: ContextVar[ExecutionPermissions | None] = ContextVar(
    "rush_aislop_grants", default=None
)
_REQUIRED = ExecutionPermissions(download=True)


def _granted() -> ExecutionPermissions:
    return _GRANTS.get() or ExecutionPermissions()


@contextmanager
def aislop_grants(permissions: ExecutionPermissions) -> Iterator[None]:
    """Make the calling tool's grants decide whether aislop may download."""
    token = _GRANTS.set(permissions)
    try:
        yield
    finally:
        _GRANTS.reset(token)


class AislopEngine(Engine):
    name = "aislop"
    binary = "aislop"
    file_extensions = ("py", "js", "ts", "jsx", "tsx", "go", "rs", "java", "c", "cpp")

    def child_env(self) -> dict[str, str] | None:
        if _granted().download:
            return None
        return {**os.environ, "npm_config_offline": "true"}

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
        # aislop 0.16.1: `scan [options] [directory]` takes one positional, so a
        # file target scans its parent restricted to that file via --include.
        target = path.absolute()
        include: list[str] = []
        if target.is_file():
            include = ["--include", target.name]
            target = target.parent
        argv = [binary_path, "scan", "--format=json", *args, *include, str(target)]

        env = self.child_env()
        proc = run_subprocess(
            argv,
            cwd=target,
            timeout=120,
            **env_kwargs(env),
            **ownership_kwargs(owner_instance_id, run_id),
        )

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "diagnostics" in parsed:
                    findings_raw = parsed["diagnostics"]
                elif isinstance(parsed, dict) and "issues" in parsed:
                    findings_raw = parsed["issues"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"aislop exit {proc.returncode}",
            duration_ms=0,
            cwd=str(target),
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        base = Path(raw.get("cwd") or path)
        for item in raw.get("findings", []):
            sev = item.get("severity", "warning").lower()
            if "filePath" in item:
                # aislop 0.16.1 `diagnostics`: filePath is relative to the
                # scanned directory; rule is namespaced by its aislop engine.
                file = str(base / item["filePath"])
                rule = f"aislop/{item.get('engine', 'aislop')}/{item.get('rule', 'slop-pattern')}"
            else:
                file = item.get("file", str(path))
                rule = f"aislop/{item.get('rule_id', item.get('rule', 'slop-pattern'))}"
            findings.append(
                {
                    "path": file,
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": rule,
                    "severity": "error"
                    if sev in ("error", "fatal", "critical")
                    else "warn",
                    "message": item.get(
                        "message", "AI-generated anti-pattern detected"
                    ),
                    "fix": item.get("fix") or item.get("suggested_fix"),
                    "remediation": item.get("help")
                    or item.get("remediation")
                    or item.get("explanation"),
                }
            )

        parsed = raw.get("parsed")
        reported = isinstance(parsed, list) or (
            isinstance(parsed, dict) and ("diagnostics" in parsed or "issues" in parsed)
        )
        status: ToolStatus
        if (
            not reported
            and not _granted().download
            and "ENOTCACHED" in (raw.get("stderr") or "")
        ):
            # Offline npm and the package is not cached: fetching it needs
            # the download grant. Not run, never an engine error.
            return skipped_result(
                tool_name,
                self.name,
                "requires permission: --allow-download (aislop's npm package "
                "is not in the local npm cache)",
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=_REQUIRED,
                        granted=_granted(),
                        producer=self.name,
                        extra={"disposition": "not_run", "cause": "permission_denied"},
                    )
                },
            )
        if not reported:
            # aislop exits 1 whenever it reports diagnostics, so only a
            # missing/unrecognized JSON report is an engine error.
            status = "error"
            stderr = (raw.get("stderr") or "").strip()[:500]
            summary = f"aislop produced no JSON report (exit {raw.get('exit_code', 0)})"
            if stderr:
                summary += f": {stderr}"
        else:
            status = (
                "fail"
                if any(f["severity"] == "error" for f in findings)
                else ("warn" if findings else "ok")
            )
            summary = f"aislop: {len(findings)} anti-pattern finding(s)"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=summary,
            findings=findings,
            raw=raw.get("parsed"),
        )
