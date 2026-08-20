"""ScanCode toolkit adapter for deep license and copyright analysis."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class ScancodeEngine(Engine):
    name = "scancode"
    binary = "scancode"
    file_extensions = ()

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = [
            "--license",
            "--copyright",
            "--json-pp",
            "scancode-results.json",
            "--quiet",
        ]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=300)

        parsed = None
        report_file = (cwd or path) / "scancode-results.json"
        if report_file.exists():
            try:
                parsed = json.loads(report_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                parsed = None
        elif proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
            except json.JSONDecodeError:
                parsed = None

        findings_raw: list[dict] = []
        if isinstance(parsed, dict) and "files" in parsed:
            for file_entry in parsed["files"]:
                licenses = file_entry.get("licenses", [])
                for lic in licenses:
                    if (
                        lic.get("is_unknown")
                        or "gpl" in lic.get("key", "").lower()
                        or "agpl" in lic.get("key", "").lower()
                    ):
                        findings_raw.append(
                            {"path": file_entry.get("path"), "license": lic}
                        )

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"scancode exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            lic = item.get("license", {})
            spdx = lic.get("spdx_license_key") or lic.get("key", "Unknown")
            is_copyleft = "gpl" in spdx.lower() or "agpl" in spdx.lower()
            findings.append(
                {
                    "path": item.get("path", str(path)),
                    "line": lic.get("start_line", 0),
                    "column": 0,
                    "rule": f"license/{spdx.lower()}",
                    "severity": "warn" if is_copyleft else "info",
                    "message": f"Detected license {spdx} (copyleft risk: {is_copyleft})",
                }
            )

        exit_code = raw.get("exit_code", 0)
        status = (
            "warn"
            if any(f["severity"] == "warn" for f in findings)
            else ("ok" if exit_code == 0 else "error")
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"scancode: {len(findings)} flagged license notice(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
