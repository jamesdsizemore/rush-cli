"""Cold start and import overhead audit tool.

Performs static AST inventory of Python top-level imports (flagging heavy or
wildcard imports) and optional dynamic -X importtime execution guarded by --allow-slow.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms, run_subprocess

HEAVY_PACKAGES: frozenset[str] = frozenset(
    {
        "torch",
        "tensorflow",
        "transformers",
        "pandas",
        "numpy",
        "scipy",
        "matplotlib",
        "boto3",
        "google.cloud",
        "azure",
        "playwright",
        "spacy",
        "nltk",
        "onnxruntime",
        "sympy",
        "sklearn",
        "polars",
    }
)


class _ImportVisitor(ast.NodeVisitor):
    """Inspects top-level imports in Python source code."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.findings: list[Finding] = []
        self.total_imports: int = 0
        self.heavy_imports: list[str] = []
        self._scope_depth: int = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scope_depth += 1
        self.generic_visit(node)
        self._scope_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scope_depth += 1
        self.generic_visit(node)
        self._scope_depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope_depth += 1
        self.generic_visit(node)
        self._scope_depth -= 1

    def visit_Import(self, node: ast.Import) -> None:
        self.total_imports += len(node.names)
        if self._scope_depth == 0:  # Top-level
            for alias in node.names:
                base_pkg = alias.name.split(".")[0]
                if base_pkg in HEAVY_PACKAGES or alias.name in HEAVY_PACKAGES:
                    self.heavy_imports.append(alias.name)
                    self.findings.append(
                        Finding(
                            path=self.filename,
                            line=node.lineno,
                            column=node.col_offset,
                            rule="cold-start/heavy-top-level-import",
                            severity="warn",
                            message=(
                                f"Heavy package '{alias.name}' imported at module top-level adds cold-start latency. "
                                "Consider lazy importing inside function/method."
                            ),
                            remediation=f"Move 'import {alias.name}' inside the function where it is used.",
                        )
                    )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.total_imports += len(node.names)
        if self._scope_depth == 0:  # Top-level
            module_name = node.module or ""
            base_pkg = module_name.split(".")[0] if module_name else ""

            # Check for wildcard import
            if any(alias.name == "*" for alias in node.names):
                self.findings.append(
                    Finding(
                        path=self.filename,
                        line=node.lineno,
                        column=node.col_offset,
                        rule="cold-start/wildcard-import",
                        severity="warn",
                        message=f"Wildcard import 'from {module_name} import *' bloats namespace and hinders startup optimization.",
                        remediation="Explicitly list imported symbols instead of '*'.",
                    )
                )

            if base_pkg in HEAVY_PACKAGES or module_name in HEAVY_PACKAGES:
                self.heavy_imports.append(module_name)
                self.findings.append(
                    Finding(
                        path=self.filename,
                        line=node.lineno,
                        column=node.col_offset,
                        rule="cold-start/heavy-top-level-import",
                        severity="warn",
                        message=(
                            f"Heavy package '{module_name}' imported at module top-level adds cold-start latency. "
                            "Consider lazy importing inside function/method."
                        ),
                        remediation=f"Move 'from {module_name} import ...' inside the function where it is used.",
                    )
                )
        self.generic_visit(node)


class ColdStartTool(ToolFn):
    name: ToolName = "cold-start"

    @property
    def mcp_description(self) -> str:
        return (
            "Audit import overhead and cold-start latency at <path>; dynamic -X "
            "importtime requires --allow-slow. Returns {status, findings[], summary}."
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
                engine="cold-start",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="cold-start: Dynamic import timing requires --allow-slow permission.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="cold-start",
                    )
                },
            )

        py_files: list[Path] = []
        if p.is_file() and p.suffix == ".py":
            py_files.append(p)
        elif p.is_dir():
            py_files.extend(sorted(p.glob("**/*.py")))

        if not py_files:
            return ToolResult(
                tool=self.name,
                engine="cold-start",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"cold-start: No Python files found at {path}.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="cold-start",
                    )
                },
            )

        findings: list[Finding] = []
        total_imports = 0
        heavy_imports_found: list[str] = []

        for py_path in py_files:
            try:
                source = py_path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(source, filename=str(py_path))
                visitor = _ImportVisitor(str(py_path))
                visitor.visit(tree)
                findings.extend(visitor.findings)
                total_imports += visitor.total_imports
                heavy_imports_found.extend(visitor.heavy_imports)
            except SyntaxError:
                continue

        dynamic_measured = False
        slowest_imports: list[dict[str, Any]] = []

        if dynamic and getattr(granted_perms, "slow", False) and py_files:
            target_file = py_files[0]
            # Run python -X importtime on target
            try:
                res = run_subprocess(
                    [sys.executable, "-X", "importtime", str(target_file.resolve())],
                    cwd=p if p.is_dir() else p.parent,
                    timeout=int(options.get("timeout_seconds", 120)),
                )
            except subprocess.TimeoutExpired:
                return ToolResult(
                    tool=self.name,
                    engine="cold-start",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="cold-start: Target timed out during dynamic measurement.",
                    findings=findings,
                    metrics={"completed": False, "import_time_measured": False},
                    raw=None,
                    metadata={"terminal_reason": "timeout"},
                )
            # stderr contains import timings e.g.:
            # import time: self [us] | cumulative [us] | imported_module
            if res.returncode != 0:
                return ToolResult(
                    tool=self.name,
                    engine="cold-start",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="cold-start: Target failed during dynamic measurement.",
                    findings=findings,
                    metrics={"completed": False, "import_time_measured": False},
                    raw=None,
                    metadata={
                        "terminal_reason": "target_failed",
                        "target_exit_code": res.returncode,
                    },
                )
            for line in res.stderr.splitlines():
                m = re.search(
                    r"import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+([a-zA-Z0-9_\.]+)", line
                )
                if m:
                    self_us = int(m.group(1))
                    cum_us = int(m.group(2))
                    mod_name = m.group(3)
                    slowest_imports.append(
                        {
                            "module": mod_name,
                            "self_us": self_us,
                            "cumulative_us": cum_us,
                        }
                    )
            if not slowest_imports:
                return ToolResult(
                    tool=self.name,
                    engine="cold-start",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary="cold-start: Dynamic measurement produced no import trace.",
                    findings=findings,
                    metrics={"completed": False, "import_time_measured": False},
                    raw=None,
                    metadata={"terminal_reason": "incomplete"},
                )
            dynamic_measured = True

        status: ToolStatus = "warn" if findings else "ok"
        summary = (
            f"cold-start: Audited {len(py_files)} file(s), {total_imports} import(s), "
            f"{len(heavy_imports_found)} heavy top-level import(s)"
        )
        if dynamic_measured:
            summary += (
                f", dynamic import timings captured ({len(slowest_imports)} imports)"
            )

        metrics: dict[str, Any] = {
            "files_audited": len(py_files),
            "total_imports": total_imports,
            "heavy_imports_count": len(heavy_imports_found),
        }
        if dynamic:
            metrics["import_time_measured"] = dynamic_measured
            metrics["measured_import_count"] = len(slowest_imports)
        metrics["completed"] = not dynamic or dynamic_measured

        return ToolResult(
            tool=self.name,
            engine="cold-start",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics=metrics,
            raw={
                "heavy_imports": heavy_imports_found,
                "slowest_imports": slowest_imports[:10],
            },
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="cold-start",
                )
            },
        )
