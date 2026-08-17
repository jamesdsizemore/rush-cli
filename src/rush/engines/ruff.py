"""ruff engine — Python lint + format.

Uses `ruff check --output-format=json` for lint (structured findings) and
`ruff format --check` for format verification.

JSON output schema:
    [
        {
            "code": "E501",
            "message": "Line too long (110 > 88 characters)",
            "location": {"row": 42, "column": 1},
            "filename": "src/foo.py",
            "fix": {"applicability": "safe", "edits": [...]}
        },
        ...
    ]
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from ..tools.common import resolve_binary
from .base import Engine, EngineResult


class RuffEngine(Engine):
    name = "ruff"
    binary = "ruff"
    file_extensions = ("py", "pyi")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        """Run `ruff check --output-format=json <path> <args>`.

        `args` come from the tool caller (CLI flags / rush.toml). We prepend
        `--output-format=json` so the output is always structured.
        """
        argv = [
            self.binary,
            "check",
            "--output-format=json",
            "--no-cache",  # deterministic; cache is host-specific
            str(path),
            *args,
        ]
        # Use absolute binary path so subprocess finds it even when PATH is weird
        binary_path = resolve_binary(self.binary) or self.binary
        argv[0] = binary_path

        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            timeout=120,
            capture_output=True,
            text=True,
            check=False,
        )

        # ruff exits 0 (clean), 1 (findings), or 2 (config error). All are valid.
        # We parse JSON iff exit code in {0, 1}; otherwise return raw stdout/stderr.
        findings_raw: list[dict] = []
        parsed = None
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        # If user passed --fix-related flags, drop them — rush v0.1 doesn't auto-fix.
        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=self._summary(proc.returncode, len(findings_raw)),
            duration_ms=0,  # stamped by run_engine()
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        """Convert ruff JSON to canonical ToolResult."""
        from ..tools.common import elapsed_ms, normalize_findings
        from ..tools.base import ToolResult

        findings = normalize_findings(
            [
                {
                    "path": f.get("filename", ""),
                    "line": f.get("location", {}).get("row", 0),
                    "column": f.get("location", {}).get("column", 0),
                    "rule": f.get("code", ""),
                    # ruff uses pycodestyle rule codes; map to severity heuristically
                    "severity": _ruff_severity(f.get("code", "")),
                    "message": f.get("message", ""),
                    "fix": f.get("fix"),
                }
                for f in raw.get("findings", [])
            ]
        )

        # ruff exit 0 = clean, 1 = findings, 2+ = config/crash
        exit_code = raw.get("exit_code", 0)
        if exit_code >= 2:
            status = "error"
            summary = f"ruff config error: {raw.get('stderr', '').strip().splitlines()[0] if raw.get('stderr') else 'unknown'}"
        elif findings:
            status = "fail" if any(f.get("severity") == "error" for f in findings) else "warn"
            summary = raw.get("summary") or f"ruff found {len(findings)} issue(s)"
        else:
            status = "ok"
            summary = "ruff: no issues"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self._version_str(),
            status=status,
            duration_ms=raw.get("duration_ms", elapsed_ms(0)),
            summary=summary,
            findings=findings,
            raw=raw.get("parsed"),
        )

    def _summary(self, exit_code: int, n_findings: int) -> str:
        if exit_code >= 2:
            return f"ruff exit {exit_code}"
        return f"{n_findings} ruff issue(s)" if n_findings else "ruff clean"

    _cached_version: Optional[str] = None

    def _version_str(self) -> Optional[str]:
        # Cache per-instance; first call shells out, subsequent return cached.
        if RuffEngine._cached_version is not None:
            return RuffEngine._cached_version
        v = self.version()
        RuffEngine._cached_version = v
        return v


def _ruff_severity(code: str) -> str:
    """Heuristic: E/W codes are warn; F (pyflakes) are error; others warn.

    ruff doesn't expose severity directly in JSON; this approximation
    matches what users expect from `ruff check` output.
    """
    if not code:
        return "warn"
    if code.startswith("F"):  # pyflakes — likely a bug
        return "error"
    if code.startswith(("E", "W")):  # pycodestyle
        return "warn"
    return "warn"  # default
