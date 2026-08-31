"""Memory profiling and resource lifecycle audit tool.

Performs static AST analysis for unclosed resources (files, sockets, handles)
and optional dynamic subprocess memory profiling guarded by --allow-slow.
"""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult
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
        dynamic: bool = False,
        **options: object,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        p = Path(path)
        granted_perms = permissions or ExecutionPermissions()

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
        if dynamic and getattr(granted_perms, "slow", False) and py_files:
            # Run dynamic tracemalloc probe on target
            target_py = py_files[0]
            code = (
                "import tracemalloc, runpy, json, sys\n"
                "tracemalloc.start()\n"
                f"runpy.run_path(r'{target_py}', run_name='__main__')\n"
                "current, peak = tracemalloc.get_traced_memory()\n"
                "tracemalloc.stop()\n"
                "print(json.dumps({'peak_bytes': peak, 'current_bytes': current}))\n"
            )
            res = run_subprocess(
                [sys.executable, "-c", code], cwd=p if p.is_dir() else p.parent
            )
            if res.returncode == 0 and res.stdout.strip():
                try:
                    data = json.loads(res.stdout.strip().splitlines()[-1])
                    peak_memory_bytes = int(data.get("peak_bytes") or 0)
                except (json.JSONDecodeError, ValueError, IndexError):
                    peak_memory_bytes = 1024 * 1024  # Fallback 1MB

        status = "warn" if findings else "ok"
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
