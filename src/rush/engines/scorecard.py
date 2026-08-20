"""OpenSSF Scorecard adapter for supply chain security posture assessment."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ScorecardEngine(Engine):
    name = "scorecard"
    binary = "scorecard"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--repo=.", "--format=json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=180)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "checks" in parsed:
                    for check in parsed["checks"]:
                        if check.get("score", 10) < 5:
                            findings_raw.append(check)
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"scorecard exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            name = item.get("name", "SupplyChainCheck")
            score = item.get("score", 0)
            reason = item.get("reason", "Low security posture score")
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"scorecard/{name.lower()}",
                    "severity": "warn" if score > 0 else "fail",
                    "message": f"{name} scored {score}/10: {reason}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        overall_score = (
            raw.get("parsed", {}).get("score", 10)
            if isinstance(raw.get("parsed"), dict)
            else 10
        )
        status = (
            "warn"
            if (findings or overall_score < 7)
            else ("ok" if exit_code == 0 else "error")
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"scorecard: overall score {overall_score}/10 with {len(findings)} weak check(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
