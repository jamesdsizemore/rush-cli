"""Undercover adapter for git-diff structural code coverage analysis."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs


class UndercoverEngine(Engine):
    name = "undercover"
    binary = "undercover"
    file_extensions = ("rb", "py", "js", "ts")

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
        default_args = ["--format", "json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(
            argv,
            cwd=cwd or path,
            timeout=120,
            **ownership_kwargs(owner_instance_id, run_id),
        )

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "uncovered_blocks" in parsed:
                    findings_raw = parsed["uncovered_blocks"]
            except json.JSONDecodeError:
                parsed = None

        result = EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"undercover exit {proc.returncode}",
            duration_ms=0,
        )
        # P69-03h: undercover's own adapter exposes no comparison-ref
        # argument at all (only `--format json` plus caller args) -- there is
        # no symbolic ref to pin. Its real evidence is the exact stdout bytes
        # already produced and consumed to build `findings_raw` above, the
        # same principle git-guard uses.
        result["provenance"] = {
            "kind": "undercover-stdout",
            "digest": sha256(proc.stdout.encode("utf-8")).hexdigest(),
        }
        return result

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("line", 0),
                    "column": 0,
                    "rule": "undercover/untested-change",
                    "severity": "warn",
                    "message": item.get(
                        "message",
                        f"Uncovered {item.get('kind', 'block')} in diff: {item.get('name', 'untested')}",
                    ),
                    "fix": None,
                    "remediation": "Add automated tests covering this modified block before merging.",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status: ToolStatus = (
            "warn" if findings else ("ok" if exit_code == 0 else "error")
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"undercover: {len(findings)} untested diff block(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
