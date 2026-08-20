"""Playwright browser automation and E2E testing adapter."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class PlaywrightEngine(Engine):
    name = "playwright"
    binary = "playwright"
    file_extensions = ("js", "ts", "mjs", "cjs")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["test", "--reporter=json"]
        argv = [binary_path, *default_args, *args, str(path)]
        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, dict) and "suites" in parsed:
                    # Extract errors from test suites
                    def extract_failures(suite_list: list[dict]) -> None:
                        for s in suite_list:
                            for spec in s.get("specs", []):
                                for test in spec.get("tests", []):
                                    for res in test.get("results", []):
                                        if res.get("status") in {
                                            "unexpected",
                                            "failure",
                                            "timedOut",
                                        }:
                                            err_msg = ""
                                            for err in res.get("errors", []):
                                                err_msg += err.get("message", "") + "\n"
                                            findings_raw.append(
                                                {
                                                    "title": spec.get("title", ""),
                                                    "file": spec.get("file", str(path)),
                                                    "line": spec.get("line", 0),
                                                    "message": err_msg.strip()
                                                    or "Playwright test failed",
                                                }
                                            )
                            if "suites" in s and isinstance(s["suites"], list):
                                extract_failures(s["suites"])

                    extract_failures(parsed["suites"])
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"playwright exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            findings.append(
                {
                    "path": item.get("file", str(path)),
                    "line": item.get("line", 0),
                    "rule": "playwright-test-failed",
                    "severity": "error",
                    "message": f"{item.get('title')}: {item.get('message')}",
                }
            )

        exit_code = raw.get("exit_code", 0)
        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status="fail" if findings else ("ok" if exit_code == 0 else "error"),
            duration_ms=raw.get("duration_ms", 0),
            summary=f"playwright: {len(findings)} failure(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
