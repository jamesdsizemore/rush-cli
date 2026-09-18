"""Git-Guard adapter for working tree hygiene and untracked file auditing."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs


class GitGuardEngine(Engine):
    name = "git-guard"
    binary = "git"
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
        default_args = ["status", "--porcelain=v2", "--branch"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(
            argv,
            cwd=cwd or path,
            timeout=60,
            **ownership_kwargs(owner_instance_id, run_id),
        )

        findings_raw: list[dict] = []
        for line in proc.stdout.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if line_str.startswith("?"):
                findings_raw.append({"type": "untracked", "path": line_str[2:]})
            elif line_str.startswith(("1", "2")):
                findings_raw.append({"type": "modified", "path": line_str})

        result = EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed={"status_entries": findings_raw},
            findings=findings_raw,
            summary=f"git-guard exit {proc.returncode}",
            duration_ms=0,
        )
        # P69-03h: hash the exact stdout bytes already produced and consumed
        # to build `findings_raw` above -- no separate capture-then-compare
        # step, no race between what was hashed and what was parsed.
        result["provenance"] = {
            "kind": "git-status-stdout",
            "digest": sha256(proc.stdout.encode("utf-8")).hexdigest(),
        }
        return result

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        for item in raw.get("findings", []):
            item_type = item.get("type", "change")
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": f"git-guard/{item_type}-files",
                    "severity": "warn",
                    "message": f"Git workspace hygiene: {item_type} entry detected '{item.get('path')}'",
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
            summary=f"git-guard: {len(findings)} workspace hygiene item(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
