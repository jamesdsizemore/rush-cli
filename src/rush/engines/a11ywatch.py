"""A11yWatch adapter for multi-page web accessibility crawling."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class A11ywatchEngine(Engine):
    name = "a11ywatch"
    binary = "a11ywatch"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        target = str(path) if str(path).startswith("http") else "http://localhost:3000"
        default_args = ["scan", "--url", target, "--json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "data" in parsed:
                    for page in parsed["data"]:
                        for issue in page.get("issues", []):
                            findings_raw.append(
                                {"pageUrl": page.get("pageUrl"), **issue}
                            )
                elif isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"a11ywatch exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            issue_type = item.get("type", "error").lower()
            findings.append(
                {
                    "path": item.get("pageUrl", str(path)),
                    "line": 0,
                    "column": 0,
                    "rule": f"a11ywatch/{item.get('code', 'issue')}",
                    "severity": "fail" if issue_type == "error" else "warn",
                    "message": item.get("message", "Web accessibility crawler finding"),
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
            summary=f"a11ywatch: {len(findings)} accessibility crawl issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
