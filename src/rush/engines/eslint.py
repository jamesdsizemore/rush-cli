"""eslint engine — JS/TS lint with --format=json.

JSON output schema (eslint >=8):
    [
        {
            "filePath": "/abs/path/to/file.ts",
            "messages": [
                {
                    "ruleId": "no-unused-vars",
                    "severity": 2,            # 1=warn, 2=error
                    "message": "'foo' is defined but never used.",
                    "line": 5,
                    "column": 7,
                    "nodeType": "Identifier",
                    "messageId": "unusedVar",
                    "fix": {"range": [42, 45], "text": ""}
                }
            ],
            "errorCount": 1,
            "warningCount": 0
        }
    ]
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

from ..tools.common import resolve_binary
from .base import Engine, EngineResult


class EslintEngine(Engine):
    name = "eslint"
    binary = "eslint"
    file_extensions = ("js", "jsx", "ts", "tsx", "mjs", "cjs")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Optional[Path] = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        argv = [
            binary_path,
            str(path),
            "--format=json",
            "--no-error-on-unmatched-pattern",  # don't error when path has no matching files
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

        findings_raw: list[dict] = []
        parsed = None
        stderr_text = proc.stderr or ""
        # eslint 9+ errors with "couldn't find an eslint.config" when no
        # config is present. Treat as a config issue (skip, not crash).
        if "couldn't find an eslint.config" in stderr_text or "eslint.config" in stderr_text and "couldn't" in stderr_text:
            return EngineResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                parsed=None,
                findings=[],
                summary="eslint: no eslint.config.(js|mjs|cjs) found",
                duration_ms=0,
            )

        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
            except json.JSONDecodeError:
                parsed = None

        # eslint exits 0 (clean), 1 (findings), 2 (config error). All valid.
        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"eslint exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> dict:
        from ..tools.common import elapsed_ms, normalize_findings
        from ..tools.base import ToolResult

        # No-config case: return skipped (don't crash, don't count as error)
        if "no eslint.config" in (raw.get("summary") or ""):
            return ToolResult(
                tool=tool_name,
                engine=self.name,
                engine_version=self.version(),
                status="skipped",
                duration_ms=raw.get("duration_ms", elapsed_ms(0)),
                summary=raw.get("summary", "eslint: no config"),
                findings=[],
                raw=None,
            )

        # Flatten the eslint list-of-files structure into a single findings list
        all_msgs: list[dict] = []
        for file_result in raw.get("findings", []):
            file_path = file_result.get("filePath", "")
            for m in file_result.get("messages", []):
                all_msgs.append({
                    "path": file_path,
                    "line": m.get("line", 0),
                    "column": m.get("column", 0),
                    "rule": m.get("ruleId") or "",
                    "severity": _eslint_severity(m.get("severity", 1)),
                    "message": m.get("message", ""),
                    "fix": m.get("fix"),
                })

        findings = normalize_findings(all_msgs)

        exit_code = raw.get("exit_code", 0)
        if exit_code >= 2:
            status = "error"
            summary = f"eslint config error (exit {exit_code})"
        elif findings:
            status = "fail" if any(f.get("severity") == "error" for f in findings) else "warn"
            summary = f"eslint: {len(findings)} issue(s)"
        else:
            status = "ok"
            summary = "eslint: no issues"

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


def _eslint_severity(n: int) -> str:
    return "error" if n >= 2 else "warn"
