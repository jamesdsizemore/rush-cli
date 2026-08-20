"""GraphQL-Inspector adapter for schema diffing and breaking change detection."""

from __future__ import annotations

import json
from pathlib import Path

from ..tools.base import ToolResult
from ..tools.common import resolve_binary, run_subprocess
from .base import Engine, EngineResult


class GraphQLInspectorEngine(Engine):
    name = "graphql-inspector"
    binary = "graphql-inspector"
    file_extensions = ("graphql", "gql", "json")

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        default_args = ["validate", str(path), "--format", "json"]
        argv = [binary_path, *default_args, *args]

        proc = run_subprocess(argv, cwd=cwd or path, timeout=120)

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "changes" in parsed:
                    findings_raw = parsed["changes"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"graphql-inspector exit {proc.returncode}",
            duration_ms=0,
        )

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings = []
        for item in raw.get("findings", []):
            is_breaking = item.get("criticality", {}).get(
                "level"
            ) == "BREAKING" or item.get("breaking", False)
            findings.append(
                {
                    "path": str(path),
                    "line": 0,
                    "column": 0,
                    "rule": f"graphql/{item.get('type', 'schema-change').lower()}",
                    "severity": "fail" if is_breaking else "warn",
                    "message": item.get(
                        "message", "GraphQL schema change or validation issue"
                    ),
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
            summary=f"graphql-inspector: {len(findings)} schema finding(s)",
            findings=findings,
            raw=raw.get("parsed"),
        )
