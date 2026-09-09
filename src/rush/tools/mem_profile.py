"""Memory profiling and resource lifecycle audit tool.

Performs static AST analysis for unclosed resources (files, sockets, handles)
and optional dynamic subprocess memory profiling guarded by --allow-slow.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms, run_subprocess


class _ResourceLifecycleVisitor(ast.NodeVisitor):
    """Detects open() and socket/connection allocations outside context managers."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[Finding] = []
        self._with_targets: set[str] = set()

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if isinstance(item.optional_vars, ast.Name):
                self._with_targets.add(item.optional_vars.id)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            if isinstance(item.optional_vars, ast.Name):
                self._with_targets.add(item.optional_vars.id)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        # Check if right-hand side is open() or socket.socket() or sqlite3.connect()
        call_name = self._get_call_name(node.value)
        if call_name in (
            "open",
            "socket.socket",
            "sqlite3.connect",
            "urllib.request.urlopen",
        ):
            # Check if assigned var has a matching .close() in the same scope or if inside a With
            # For simplicity, if assigned to a variable outside with, check if .close() is called
            var_name = None
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                var_name = node.targets[0].id

            # If inside With, it's safe
            if var_name and var_name not in self._with_targets:
                self.findings.append(
                    Finding(
                        path=self.filename,
                        line=node.lineno,
                        column=node.col_offset,
                        rule="mem-profile/unclosed-resource",
                        severity="warn",
                        message=(
                            f"Resource allocated by '{call_name}()' assigned to '{var_name}' "
                            "without context manager. Use 'with ... as ...' to ensure deterministic cleanup."
                        ),
                        remediation=f"Refactor to 'with {call_name}(...) as {var_name}:'.",
                    )
                )
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        # open() called as bare expression without saving or context manager
        call_name = self._get_call_name(node.value)
        if call_name in (
            "open",
            "socket.socket",
            "sqlite3.connect",
            "urllib.request.urlopen",
        ):
            self.findings.append(
                Finding(
                    path=self.filename,
                    line=node.lineno,
                    column=node.col_offset,
                    rule="mem-profile/unclosed-resource",
                    severity="warn",
                    message=(
                        f"Resource allocated by bare '{call_name}()' expression is immediately orphaned."
                    ),
                    remediation="Wrap allocation in a 'with' statement.",
                )
            )
        self.generic_visit(node)

    def _get_call_name(self, node: ast.AST) -> str | None:
        if not isinstance(node, ast.Call):
            return None
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            val = node.func.value
            if isinstance(val, ast.Name):
                return f"{val.id}.{node.func.attr}"
            elif isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
                return f"{val.value.id}.{val.attr}.{node.func.attr}"
        return None


class MemProfileTool(ToolFn):
    name: ToolName = "mem-profile"

    @property
    def mcp_description(self) -> str:
        return (
            "Audit memory usage and unclosed resources at <path>; dynamic probe "
            "requires --allow-slow. Returns {status, findings[], summary}."
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

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        dynamic: bool | None = None,
        **options: object,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        p = Path(path)
        granted_perms = permissions or ExecutionPermissions()
        if dynamic is None:
            tool_config = getattr(config, "tools", {}).get(self.name)
            dynamic = getattr(tool_config, "options", {}).get("dynamic", False)

        if dynamic and not getattr(granted_perms, "slow", False):
            return ToolResult(
                tool=self.name,
                engine="mem-profile",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="mem-profile: Dynamic memory probe requires --allow-slow permission.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="mem-profile",
                    )
                },
            )

        # Collect python files
        py_files: list[Path] = []
        if p.is_file() and p.suffix == ".py":
            py_files.append(p)
        elif p.is_dir():
            py_files.extend(sorted(p.glob("**/*.py")))

        if not py_files and not (p.is_file() and p.suffix == ".py"):
            return ToolResult(
                tool=self.name,
                engine="mem-profile",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"mem-profile: No Python files found at {path}.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="mem-profile",
                    )
                },
            )

        findings: list[Finding] = []
        for py_path in py_files:
            try:
                source = py_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_path))
                visitor = _ResourceLifecycleVisitor(str(py_path))
                visitor.visit(tree)
                findings.extend(visitor.findings)
            except SyntaxError:
                continue

        peak_memory_bytes = 0
        dynamic_measured = False
        if dynamic and getattr(granted_perms, "slow", False) and py_files:
            # Run dynamic tracemalloc probe on target
            target_py = py_files[0]
            target_literal = json.dumps(str(target_py.resolve()))
            report_prefix = f"rush-memory-{uuid.uuid4().hex}:"
            code = (
                "import tracemalloc, runpy, json, sys\n"
                "tracemalloc.start()\n"
                f"runpy.run_path({target_literal}, run_name='__main__')\n"
                "current, peak = tracemalloc.get_traced_memory()\n"
                "tracemalloc.stop()\n"
                f"print('\\n' + {report_prefix!r} + json.dumps({{'peak_bytes': peak, 'current_bytes': current}}))\n"
            )
            try:
                res = run_subprocess(
                    [sys.executable, "-c", code],
                    cwd=p if p.is_dir() else p.parent,
                    timeout=int(options.get("timeout_seconds", 120)),
                )
            except subprocess.TimeoutExpired:
                return ToolResult(
                    tool=self.name,
                    engine="mem-profile",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="mem-profile: Target timed out during dynamic measurement.",
                    findings=findings,
                    metrics={"completed": False, "peak_memory_bytes": None},
                    raw=None,
                    metadata={"terminal_reason": "timeout"},
                )
            if res.returncode != 0:
                return ToolResult(
                    tool=self.name,
                    engine="mem-profile",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="mem-profile: Target failed during dynamic measurement.",
                    findings=findings,
                    metrics={
                        "completed": False,
                        "peak_memory_bytes": None,
                        "target_exit_code": res.returncode,
                    },
                    raw=None,
                    metadata={
                        "terminal_reason": "target_failed",
                        "target_exit_code": res.returncode,
                    },
                )
            if not res.stdout.strip():
                return ToolResult(
                    tool=self.name,
                    engine="mem-profile",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="mem-profile: Dynamic measurement produced no report.",
                    findings=findings,
                    metrics={"completed": False, "peak_memory_bytes": None},
                    raw=None,
                    metadata={"terminal_reason": "incomplete"},
                )
            try:
                report = res.stdout.strip().splitlines()[-1]
                if not report.startswith(report_prefix):
                    raise ValueError("missing profiler report")
                data = json.loads(report.removeprefix(report_prefix))
                if not isinstance(data, dict):
                    raise TypeError("invalid memory report")
                peak = data.get("peak_bytes")
                if isinstance(peak, bool) or not isinstance(peak, int) or peak < 0:
                    raise ValueError("invalid peak bytes")
                peak_memory_bytes = peak
                dynamic_measured = True
            except (json.JSONDecodeError, ValueError, TypeError, IndexError):
                return ToolResult(
                    tool=self.name,
                    engine="mem-profile",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="mem-profile: Dynamic measurement report was invalid.",
                    findings=findings,
                    metrics={"completed": False, "peak_memory_bytes": None},
                    raw=None,
                    metadata={"terminal_reason": "incomplete"},
                )

        status: ToolStatus = "warn" if findings else "ok"
        summary = f"mem-profile: Audited {len(py_files)} file(s), {len(findings)} unclosed resource finding(s)"
        if dynamic:
            summary += f", peak memory: {peak_memory_bytes / 1024:.1f} KB"

        return ToolResult(
            tool=self.name,
            engine="mem-profile",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics={
                "files_audited": len(py_files),
                "unclosed_resources_count": len(findings),
                "peak_memory_bytes": peak_memory_bytes,
                "completed": not dynamic or dynamic_measured,
            },
            raw={"unclosed_resources": len(findings)},
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="mem-profile",
                )
            },
        )
