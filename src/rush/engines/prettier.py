"""prettier engine — format verification via --check.

prettier has two modes:
  - --write: modify files in place (rush's `format` subcommand with no --check)
  - --check: exit non-zero + write filenames to stdout of files that need formatting

We default to --check so format() never silently mutates a user's repo.
The format() tool calls prettier without --check only when the user passes
--write explicitly. But for v0.1, --check is the safe default — we treat
"would be reformatted" as a finding.

Output (--check):
    src/foo.ts
    src/bar.ts

Exit codes:
  0 = all formatted
  1 = some files would be reformatted
  2 = error
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from ..tools.common import resolve_binary
from .base import Engine, EngineResult


class PrettierEngine(Engine):
    name = "prettier"
    binary = "prettier"
    file_extensions = (
        "js", "jsx", "ts", "tsx", "mjs", "cjs",
        "json", "md", "yaml", "yml", "css", "html",
    )

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        argv = [
            binary_path,
            "--check",
            "--log-level=warn",  # suppress info noise
            str(path),
            *args,
        ]
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            timeout=120,
            capture_output=True,
            text=True,
            check=False,
        )

        # prettier --check writes filenames (one per line) to stdout for files
        # that would be reformatted.
        would_reformat = [
            ln.strip() for ln in proc.stdout.splitlines()
            if ln.strip() and not ln.startswith("[warn]")
        ]

        findings_raw = [
            {"path": p, "rule": "formatting", "severity": "warn",
             "message": "file would be reformatted by prettier"}
            for p in would_reformat
        ]

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=None,
            findings=findings_raw,
            summary=(
                f"prettier: {len(would_reformat)} file(s) would be reformatted"
                if would_reformat else "prettier: all formatted"
            ),
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.common import elapsed_ms, normalize_findings
        from ..tools.base import ToolResult

        findings = normalize_findings(raw.get("findings", []))
        exit_code = raw.get("exit_code", 0)
        if exit_code >= 2:
            status = "error"
            summary = f"prettier error (exit {exit_code})"
        elif findings:
            status = "warn"
            summary = raw.get("summary", f"prettier: {len(findings)} file(s) would be reformatted")
        else:
            status = "ok"
            summary = raw.get("summary", "prettier: all formatted")

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", elapsed_ms(0)),
            summary=summary,
            findings=findings,
            raw=None,
        )
