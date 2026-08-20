"""PageSpeed-CLI adapter for real-world web performance auditing."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class PagespeedEngine(Engine):
    name = "pagespeed"
    binary = "pagespeed-insights"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        target = str(path) if str(path).startswith("http") else "http://localhost:3000"
        default_args = [target, "--format", "json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "lighthouseResult" in parsed:
                    audits = parsed["lighthouseResult"].get("audits", {})
                    for audit_id, audit in audits.items():
                        score = audit.get("score")
                        if score is not None and score < 0.9:
                            findings_raw.append({"id": audit_id, **audit})
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"pagespeed exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            score = item.get("score", 1.0)
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"pagespeed/{item.get('id', 'metric')}",
                    "severity": "fail" if score < 0.5 else "warn",
                    "message": item.get("title", "PageSpeed metric recommendation"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "fail"
            if any(f["severity"] == "fail" for f in findings)
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"pagespeed: {len(findings)} performance metric finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
