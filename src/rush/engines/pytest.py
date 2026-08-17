"""pytest engine — Python test runner.

Uses `--json-report` if the `pytest-json-report` plugin is installed, else
falls back to parsing the human-readable summary line.

JSON-report schema:
    {
      "exit_code": 0,
      "summary": {"passed": 5, "failed": 1, "total": 6, "duration": 0.42},
      "tests": [
        {
          "nodeid": "tests/test_x.py::test_y",
          "outcome": "failed",
          "call": {"duration": 0.01, "longrepr": "AssertionError: ..."}
        }
      ]
    }

Plain output we parse:
    ====== 5 passed, 1 failed in 0.42s ======
    ====== 1 failed in 0.42s ======
    ====== 5 passed in 0.42s ======
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from ..tools.common import run_subprocess
from .base import Engine, EngineResult

_SUMMARY_RE = re.compile(
    r"=+\s*(?:(\d+)\s+failed)?[,\s]*(?:(\d+)\s+passed)?[,\s]*"
    r"(?:(\d+)\s+skipped)?[,\s]*(?:(\d+)\s+warning[s]?)?[,\s]*"
    r"in\s+([\d.]+)s\s*=+",
    re.IGNORECASE,
)


class PytestEngine(Engine):
    name = "pytest"
    binary = "pytest"
    file_extensions = ("py", "pyi")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        # Try --json-report first; fall back to plain output if plugin missing.
        # Prefer the active interpreter over pytest.exe. On Windows, a console
        # script launched from an MCP stdio child can inherit a broken entrypoint
        # environment, while ``python -m pytest`` is bound to Rush's venv.
        argv = [sys.executable, "-m", "pytest", str(path), "--tb=line", "-q", *args]
        proc = run_subprocess(argv, cwd=cwd, timeout=300)

        parsed = None
        findings_raw: list[dict] = []
        summary_line = self._parse_summary(proc.stdout + proc.stderr)

        # If user explicitly asked for --json-report and plugin is present,
        # parse it. We don't auto-enable because the plugin isn't a dep.
        if "--json-report" in args:
            try:
                parsed = json.loads(proc.stdout)
                findings_raw = self._json_report_findings(parsed)
            except (json.JSONDecodeError, KeyError):
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed or summary_line,
            findings=findings_raw,
            summary=summary_line or f"pytest exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.base import ToolResult
        from ..tools.common import elapsed_ms

        exit_code = raw.get("exit_code", 0)
        summary = raw.get("summary", "")
        if not summary:
            summary = f"pytest exit {exit_code}"

        if exit_code == 0 or exit_code == 5:
            status = "ok"
        elif exit_code == 2:  # pytest: interrupted / collection error
            status = "error"
        else:
            status = "fail"

        # Build findings from parsed json-report or from exit code alone
        findings = []
        for f in raw.get("findings", []):
            findings.append(
                {
                    "path": f.get("path", ""),
                    "line": f.get("line", 0),
                    "rule": f.get("rule", "test-failure"),
                    "severity": "error",
                    "message": f.get("message", ""),
                }
            )
        if not findings and status == "fail":
            # No json-report — leave a single summary finding so agent sees it
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "rule": "pytest",
                    "severity": "error",
                    "message": summary,
                }
            )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", elapsed_ms(0)),
            summary=summary,
            findings=findings,
            raw=raw.get("parsed"),
        )

    @staticmethod
    def _parse_summary(text: str) -> str | None:
        """Extract pytest's summary line.

        Handles three formats:
            ==== 5 passed, 1 failed in 0.42s ====   (pytest <=7)
            5 passed, 1 failed in 0.42s             (pytest 8+ -q mode)
            no tests ran in 0.01s                  (exit 5 — empty test dir)
        """
        for line in text.splitlines():
            cleaned = " ".join(line.split()).strip("= ").strip()
            if not cleaned or cleaned.startswith("."):
                continue
            # Plain format (pytest 8+ with -q): "X passed, Y failed in N s"
            if (
                "passed" in line or "failed" in line or "error" in line
            ) and " in " in line:
                return cleaned
            # No-tests case
            if "no tests ran" in line.lower():
                return cleaned
        return None

    @staticmethod
    def _json_report_findings(report: dict) -> list[dict]:
        """Convert pytest-json-report 'tests' list into finding dicts."""
        out: list[dict] = []
        for t in report.get("tests", []):
            if t.get("outcome") in ("failed", "error"):
                nodeid = t.get("nodeid", "")
                # nodeid like "tests/test_x.py::test_y" — extract path
                path = nodeid.split("::")[0]
                longrepr = ""
                if t.get("call"):
                    longrepr = (
                        str(t["call"].get("longrepr", "")).strip().splitlines()[0]
                    )
                out.append(
                    {
                        "path": path,
                        "line": t.get("call", {}).get("lineno", 0)
                        if isinstance(t.get("call"), dict)
                        else 0,
                        "rule": "test-" + t.get("outcome", "fail"),
                        "severity": "error",
                        "message": longrepr or nodeid,
                    }
                )
        return out
