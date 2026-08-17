"""npm audit engine — JS/TS dependency vulnerability scanner.

Runs `npm audit --json` in the directory containing package.json.
Output schema (npm >=7):
    {
      "auditReportVersion": 2,
      "vulnerabilities": {
        "package-name": {
          "name": "package-name",
          "severity": "high" | "moderate" | "critical" | "low" | "info",
          "isDirect": true,
          "via": [{"title": "...", "url": "...", "severity": "high", ...}],
          "effects": [...],
          "range": "<1.0.0",
          "fixAvailable": true | { "name": "...", "version": "..." }
        }
      },
      "metadata": {
        "vulnerabilities": {"info": 0, "low": 1, "moderate": 2, "high": 0, "critical": 1, "total": 4}
      }
    }
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from ..tools.common import resolve_binary
from .base import Engine, EngineResult


class NpmAuditEngine(Engine):
    name = "npm-audit"
    binary = "npm"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary

        # npm audit needs to run inside a project dir with package.json.
        # If `path` is a file, use its parent dir; if dir, use it directly.
        run_dir = path if path.is_dir() else path.parent

        argv = [
            binary_path,
            "audit",
            "--json",
            *args,
        ]
        proc = subprocess.run(
            argv,
            cwd=str(run_dir),
            timeout=180,
            capture_output=True,
            text=True,
            check=False,
        )

        # npm sometimes writes non-JSON noise to stdout around the JSON
        # payload. Try to parse the first { ... } block.
        parsed = None
        findings_raw: dict = {}
        if proc.stdout.strip():
            # Find the JSON object in stdout
            start = proc.stdout.find("{")
            if start != -1:
                try:
                    parsed = json.loads(proc.stdout[start:])
                    if isinstance(parsed, dict):
                        findings_raw = parsed.get("vulnerabilities", {})
                except json.JSONDecodeError:
                    parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=[{"pkg_data": k, **v} for k, v in findings_raw.items()],
            summary=f"npm audit exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.common import elapsed_ms, normalize_findings
        from ..tools.base import ToolResult

        # Each "finding" is a dict {pkg_data, name, severity, via, ...}
        all_vulns: list[dict] = []
        for entry in raw.get("findings", []):
            pkg_name = entry.get("name") or entry.get("pkg_data", "?")
            severity_str = entry.get("severity", "info")
            fix = entry.get("fixAvailable")
            fix_str = ""
            if isinstance(fix, dict):
                fix_str = f" (fix: upgrade {fix.get('name', '?')} to {fix.get('version', '?')})"
            elif fix is True:
                fix_str = " (fix: npm audit fix)"

            # via can be a list of strings (transitive) or dicts (advisory info)
            via = entry.get("via", [])
            titles: list[str] = []
            for v in via:
                if isinstance(v, dict):
                    titles.append(v.get("title", ""))
                elif isinstance(v, str):
                    pass
            via_summary = "; ".join(t for t in titles if t)[:200] or "no details"

            all_vulns.append({
                "path": str(path),
                "line": 0,
                "rule": (titles[0] if titles else "npm-audit") or "npm-audit",
                "severity": _npm_severity(severity_str),
                "message": f"{pkg_name}: {via_summary}{fix_str}",
            })

        findings = normalize_findings(all_vulns)

        exit_code = raw.get("exit_code", 0)
        # npm exits 0 = clean, 1 = vulns found, >1 = error
        if exit_code == 0:
            status = "ok"
            summary = "npm audit: no known vulnerabilities"
        elif findings:
            status = "fail"
            summary = f"npm audit: {len(findings)} vulnerabilit{'y' if len(findings) == 1 else 'ies'}"
        else:
            status = "error"
            summary = f"npm audit error (exit {exit_code})"

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


def _npm_severity(s: str) -> str:
    s = (s or "").lower()
    if s in ("critical", "high"):
        return "error"
    if s in ("moderate", "low"):
        return "warn"
    return "info"
