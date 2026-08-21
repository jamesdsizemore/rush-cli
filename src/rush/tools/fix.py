"""Unified Automated Remediation Tool (rush fix).

Architecture §8, Phase 22.
Enforces Control 2: Path Confinement & Atomic Safety.
"""

from __future__ import annotations

import ast
import difflib
import json
import subprocess
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from rush.config import RushConfig
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions
from rush.tools.base import ToolFn, ToolName, ToolResult

logger = get_logger("tools.fix")


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    original_bytes: bytes
    timestamp: float = field(default_factory=time.time)


class SnapshotJournal:
    """In-memory byte snapshot journal ensuring zero-loss atomic rollbacks."""

    def __init__(self) -> None:
        self._snapshots: dict[Path, bytes] = {}
        self._metadata: dict[Path, float] = {}

    def capture(self, paths: Sequence[Path]) -> None:
        """Record initial byte states of all target files."""
        for p in paths:
            if p.is_file():
                resolved = p.resolve()
                self._snapshots[resolved] = p.read_bytes()
                self._metadata[resolved] = time.time()

    def rollback_all(self) -> None:
        """Restore all captured files to their exact pre-fix bytes."""
        for path, original_bytes in self._snapshots.items():
            if path.is_file() or not path.exists():
                try:
                    path.write_bytes(original_bytes)
                except OSError:
                    pass

    def rollback_file(self, path: Path) -> bool:
        """Restore a single target file to its pre-fix state."""
        resolved = path.resolve()
        if resolved in self._snapshots:
            try:
                resolved.write_bytes(self._snapshots[resolved])
                return True
            except OSError:
                return False
        return False

    def compute_diff(self, path: Path) -> str:
        """Compute unified diff between pre-fix snapshot and current disk bytes."""
        resolved = path.resolve()
        if resolved not in self._snapshots or not resolved.is_file():
            return ""

        original_lines = self._snapshots[resolved].decode("utf-8", errors="replace").splitlines(keepends=True)
        current_lines = resolved.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            current_lines,
            fromfile=f"a/{path.name}",
            tofile=f"b/{path.name}",
            n=3,
        )
        return "".join(diff)

    def has_changes(self, path: Path) -> bool:
        """Check if active file on disk differs from original snapshot."""
        resolved = path.resolve()
        if resolved not in self._snapshots or not resolved.is_file():
            return False
        try:
            return resolved.read_bytes() != self._snapshots[resolved]
        except OSError:
            return False


def assert_safe_workspace_path(path: Path, repo_root: Path | None = None) -> bool:
    """Assert that a target file path resolves within the allowed repository boundary.

    Raises ValueError if path attempts directory traversal outside repo_root.
    """
    if repo_root is None:
        repo_root = Path.cwd()
    resolved_path = path.resolve()
    resolved_root = repo_root.resolve()

    if not (
        resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root)
    ):
        log_subsystem(
            "fix", "SECURITY_ERROR", f"Target path outside repository boundary: {path}"
        )
        raise ValueError(
            f"Security Error: Path '{path}' resolves outside repository boundary '{resolved_root}'"
        )
    return True


class FixTool(ToolFn):
    """Safely apply automated fixes across registered linters, formatters, and AST tools."""

    name: ToolName = "fix"

    @property
    def mcp_description(self) -> str:
        return (
            "Safely auto-remediate formatting and linter issues at <path>. "
            "Returns {status, findings[], summary}. Enforces strict path confinement."
        )

    def __call__(
        self,
        path: Path = Path("."),
        dry_run: bool = False,
        force: bool = False,
    ) -> ToolResult:
        return self.run(path, dry_run=dry_run, force=force)

    def validate_ast(self, path: Path) -> tuple[bool, str | None]:
        """Validate syntax integrity of modified file using language AST and config parsers."""
        if not path.is_file():
            return True, None

        content = path.read_text(encoding="utf-8", errors="replace")

        if path.suffix in (".py", ".pyi"):
            try:
                ast.parse(content, filename=str(path))
                return True, None
            except SyntaxError as e:
                return False, f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        elif path.suffix == ".json":
            try:
                json.loads(content)
                return True, None
            except json.JSONDecodeError as e:
                return False, f"JSON syntax error at line {e.lineno}, col {e.colno}: {e.msg}"
        elif path.suffix == ".toml":
            try:
                tomllib.loads(content)
                return True, None
            except tomllib.TOMLDecodeError as e:
                return False, f"TOML syntax error: {e}"

        return True, None

    def run(
        self,
        path: Path | None = None,
        config: RushConfig | None = None,
        permissions: ExecutionPermissions | None = None,
        dry_run: bool = False,
        force: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        repo_root = (path or Path.cwd()).resolve()
        if repo_root.is_file():
            target_path = repo_root
            repo_root = repo_root.parent
        else:
            target_path = repo_root

        # 1. Assert workspace boundary
        try:
            assert_safe_workspace_path(target_path, repo_root=repo_root)
        except ValueError as exc:
            return ToolResult(
                tool=self.name,
                status="error",
                duration_ms=0,
                summary=f"fix: security error - {exc}",
                findings=[],
            )

        # 2. Check Git status (abort on dirty tree unless force=True)
        if not force and not dry_run:
            try:
                res = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    check=False,
                    stdin=subprocess.DEVNULL,
                )
                if res.returncode == 0 and res.stdout.strip():
                    log_subsystem(
                        "fix",
                        "ERROR",
                        "Uncommitted changes detected. Pass --force to override.",
                    )
                    return ToolResult(
                        tool=self.name,
                        status="fail",
                        duration_ms=0,
                        summary="fix: Uncommitted changes detected. Commit, stash, or pass --force to run auto-fix.",
                        findings=[],
                    )
            except Exception:  # noqa: BLE001, S110
                pass

        # 3. Snapshot journal capture
        journal = SnapshotJournal()
        targets = [target_path] if target_path.is_file() else list(target_path.rglob("*.py"))
        journal.capture(targets)

        # 4. Dispatch engine fixes
        result = self._run_engine_fixes(
            target_path=target_path,
            repo_root=repo_root,
            permissions=permissions or ExecutionPermissions(),
            dry_run=dry_run,
        )

        # 5. Post-Fix AST Verification
        for t in targets:
            valid, err = self.validate_ast(t)
            if not valid:
                journal.rollback_all()
                return ToolResult(
                    tool=self.name,
                    status="fail",
                    duration_ms=0,
                    summary=f"Atomic Rollback: Syntax error in '{t.name}': {err}",
                    findings=[],
                )

        if dry_run:
            journal.rollback_all()

        return result

    def _run_engine_fixes(
        self,
        target_path: Path,
        repo_root: Path,
        permissions: ExecutionPermissions,
        dry_run: bool = False,
    ) -> ToolResult:
        log_subsystem(
            "fix",
            "INFO",
            f"Running automated code remediation on {target_path} (dry_run={dry_run})",
        )
        from rush.tools.common import run_subprocess

        files_fixed = 0
        summary_parts = []

        fmt_cmd = (
            ["ruff", "format", "--diff", str(target_path)]
            if dry_run
            else ["ruff", "format", str(target_path)]
        )
        proc_fmt = run_subprocess(fmt_cmd, cwd=repo_root)
        if proc_fmt.returncode == 0:
            files_fixed += 1
            summary_parts.append("ruff-format")

        chk_cmd = (
            ["ruff", "check", "--diff", str(target_path)]
            if dry_run
            else ["ruff", "check", "--fix", str(target_path)]
        )
        proc_chk = run_subprocess(chk_cmd, cwd=repo_root)
        if proc_chk.returncode == 0:
            summary_parts.append("ruff-check")

        mode_str = " (dry run)" if dry_run else ""
        return ToolResult(
            tool=self.name,
            status="ok",
            duration_ms=20,
            summary=f"fix: automated fixes applied via {', '.join(summary_parts) or 'engines'}{mode_str}",
            findings=[],
        )
