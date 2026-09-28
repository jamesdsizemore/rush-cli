"""Stylelint adapter for CSS, SCSS, and CSS-in-JS linting."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult, ownership_kwargs


class StylelintEngine(Engine):
    name = "stylelint"
    binary = "stylelint"
    file_extensions = ("css", "scss", "sass", "less")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["--formatter", "json"]
        argv = [binary_path, *default_args, *args, str(path)]

        proc = run_subprocess(
            argv,
            cwd=cwd or path,
            timeout=120,
            **ownership_kwargs(owner_instance_id, run_id),
        )

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    # M20: Stylelint's own top-level `source` field is not a
                    # generic `_PATH_KEYS` name (`engines/staging.py`
                    # deliberately never treats every key literally named
                    # `source` as a path -- an unrelated engine's own
                    # `source` field could mean anything else). Adapter-
                    # specific remap, in place, before this decoded `parsed`
                    # object becomes both `findings_raw[].source` and this
                    # result's own `raw` field -- one remap fixes both, and
                    # is a no-op (returns the value unchanged) once this
                    # engine ever runs outside a staged attempt.
                    from .staging import active_staging, map_staged_path

                    staging = active_staging()
                    for file_res in parsed:
                        source = file_res.get("source")
                        if staging is not None and isinstance(source, str):
                            file_res["source"] = map_staged_path(
                                source, staging.staged_root, staging.original_root
                            )
                        for warning in file_res.get("warnings", []):
                            findings_raw.append(
                                {"source": file_res.get("source"), **warning}
                            )
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"stylelint exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        for item in raw.get("findings", []):
            severity = item.get("severity", "warning").lower()
            findings.append(
                {
                    "path": item.get("source", str(path)),
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": f"stylelint/{item.get('rule', 'syntax')}",
                    "severity": "error" if severity == "error" else "warn",
                    "message": item.get("text", "Stylelint CSS rule violation"),
                }
            )

        exit_code = raw.get("exit_code", 0)
        status: ToolStatus = (
            "fail"
            if any(f["severity"] == "error" for f in findings)
            else ("warn" if findings else ("ok" if exit_code == 0 else "error"))
        )

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=f"stylelint: {len(findings)} stylesheet issue(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
