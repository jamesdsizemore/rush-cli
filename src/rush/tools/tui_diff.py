"""TUI Diff and findings delta computation tool.

Computes finding deltas (new regressions, resolved issues, unchanged findings)
and Git commit status, rendering rich CLI summary tables and raw MCP data structures.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms, run_subprocess


def _finding_key(f: dict[str, Any]) -> str:
    fingerprint = f.get("fingerprint")
    if fingerprint:
        return str(fingerprint)
    path = f.get("path", "")
    line = f.get("line", 0)
    rule = f.get("rule") or f.get("rule_id") or ""
    msg = f.get("message", "")
    return f"{path}:{line}:{rule}:{msg}"


class TuiDiffTool(ToolFn):
    name: ToolName = "tui-diff"

    @property
    def mcp_description(self) -> str:
        return (
            "Compute Git commit and quality findings deltas at <path>; renders "
            "Rich tables in CLI. Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
        **options: object,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, permissions=permissions, **options)

    def render_table(
        self,
        base_findings: list[dict[str, Any]],
        current_findings: list[dict[str, Any]],
    ) -> str:
        base_map = {_finding_key(f): f for f in base_findings}
        curr_map = {_finding_key(f): f for f in current_findings}

        new_keys = set(curr_map) - set(base_map)
        resolved_keys = set(base_map) - set(curr_map)
        unchanged_keys = set(base_map) & set(curr_map)

        lines: list[str] = [
            "=" * 70,
            f"Findings Delta: {len(new_keys)} New | {len(resolved_keys)} Resolved | {len(unchanged_keys)} Unchanged",
            "=" * 70,
        ]

        if new_keys:
            lines.append("\n[NEW / REGRESSIONS]")
            for k in sorted(new_keys):
                f = curr_map[k]
                lines.append(
                    f"  + [{f.get('severity', 'warn')}] {f.get('path')}:{f.get('line')} - {f.get('rule')}: {f.get('message')}"
                )

        if resolved_keys:
            lines.append("\n[RESOLVED]")
            for k in sorted(resolved_keys):
                f = base_map[k]
                lines.append(
                    f"  - [{f.get('severity', 'info')}] {f.get('path')}:{f.get('line')} - {f.get('rule')}: {f.get('message')}"
                )

        lines.append("=" * 70)
        return "\n".join(lines)

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        base_findings: list[dict[str, Any]] | None = None,
        current_findings: list[dict[str, Any]] | None = None,
        base_ref: str = "HEAD~1",
        **options: object,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        p = Path(path)
        root = p if p.is_dir() else p.parent

        base_list = base_findings or []
        curr_list = current_findings or []

        base_map = {_finding_key(f): f for f in base_list}
        curr_map = {_finding_key(f): f for f in curr_list}

        new_keys = set(curr_map) - set(base_map)
        resolved_keys = set(base_map) - set(curr_map)
        unchanged_keys = set(base_map) & set(curr_map)

        new_findings: list[Finding] = []
        for k in sorted(new_keys):
            f = curr_map[k]
            new_findings.append(
                Finding(
                    path=f.get("path", str(path)),
                    line=f.get("line", 1),
                    column=f.get("column", 1),
                    rule="tui-diff/new-finding-regression",
                    severity="warn" if f.get("severity") != "error" else "error",
                    message=f"New finding regression: [{f.get('rule')}] {f.get('message')}",
                    remediation="Remediate new quality/security defect before committing.",
                )
            )

        # Git diff stats if available
        git_res = run_subprocess(["git", "diff", "--stat", base_ref], cwd=root)
        diff_stat = git_res.stdout.strip() if git_res.returncode == 0 else ""

        status: ToolStatus = "warn" if new_findings else "ok"
        summary = (
            f"tui-diff: {len(new_findings)} new regression(s), {len(resolved_keys)} resolved, "
            f"{len(unchanged_keys)} unchanged finding(s)"
        )

        return ToolResult(
            tool=self.name,
            engine="tui-diff",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=new_findings,
            metrics={
                "new_findings_count": len(new_keys),
                "resolved_findings_count": len(resolved_keys),
                "unchanged_findings_count": len(unchanged_keys),
            },
            raw={
                "new_findings": [curr_map[k] for k in new_keys],
                "resolved_findings": [base_map[k] for k in resolved_keys],
                "unchanged_findings": [curr_map[k] for k in unchanged_keys],
                "diff_stat": diff_stat,
            },
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="tui-diff",
                )
            },
        )
