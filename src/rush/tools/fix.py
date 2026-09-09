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
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rush.config import RushConfig
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions
from rush.tools.base import ToolFn, ToolName, ToolResult, ToolStatus

logger = get_logger("tools.fix")


@dataclass(frozen=True)
class FileSnapshot:
    path: Path
    original_bytes: bytes
    timestamp: float = field(default_factory=time.time)


class SnapshotJournal:
    """In-memory byte snapshot journal ensuring zero-loss atomic rollbacks."""

    def __init__(self) -> None:
        self._snapshots: dict[Path, tuple[bytes, int]] = {}
        self._metadata: dict[Path, float] = {}

    def capture(self, paths: Sequence[Path]) -> list[str]:
        """Record initial byte states of all target files."""
        errors: list[str] = []
        for p in paths:
            try:
                if p.is_symlink():
                    errors.append(f"{p}: snapshot refused; target is a symbolic link")
                    continue
                resolved = p.resolve()
                if resolved != p:
                    errors.append(f"{p}: snapshot refused; target path is redirected")
                    continue
                if not p.exists():
                    errors.append(f"{p}: snapshot refused; target is missing")
                    continue
                if not p.is_file():
                    errors.append(
                        f"{p}: snapshot refused; target is not a regular file"
                    )
                    continue
                self._snapshots[resolved] = (p.read_bytes(), p.stat().st_mode)
                self._metadata[resolved] = time.time()
            except OSError as exc:
                errors.append(f"{p}: snapshot failed: {exc}")
        return errors

    def rollback_all(self) -> list[str]:
        """Restore all captured files to their exact pre-fix bytes."""
        errors: list[str] = []
        for path, (original_bytes, original_mode) in self._snapshots.items():
            try:
                if path.is_symlink():
                    errors.append(f"{path}: restore refused; target is a symbolic link")
                    continue
                if path.resolve() != path:
                    errors.append(f"{path}: restore refused; target path is redirected")
                    continue
                if path.exists() and not path.is_file():
                    errors.append(
                        f"{path}: restore refused; target is not a regular file"
                    )
                    continue
                path.write_bytes(original_bytes)
                path.chmod(original_mode)
            except OSError as exc:
                errors.append(f"{path}: {exc}")
        return errors

    def rollback_file(self, path: Path) -> bool:
        """Restore a single target file to its pre-fix state."""
        resolved = path.resolve()
        if resolved in self._snapshots:
            try:
                original_bytes, original_mode = self._snapshots[resolved]
                resolved.write_bytes(original_bytes)
                resolved.chmod(original_mode)
                return True
            except OSError:
                return False
        return False

    def compute_diff(self, path: Path) -> str:
        """Compute unified diff between pre-fix snapshot and current disk bytes."""
        resolved = path.resolve()
        if resolved not in self._snapshots or not resolved.is_file():
            return ""

        original_lines = (
            self._snapshots[resolved][0]
            .decode("utf-8", errors="replace")
            .splitlines(keepends=True)
        )
        current_lines = resolved.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines(keepends=True)

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
            original_bytes, original_mode = self._snapshots[resolved]
            return (
                resolved.read_bytes() != original_bytes
                or resolved.stat().st_mode != original_mode
            )
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
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        return self.run(
            path,
            dry_run=dry_run,
            force=force,
            permissions=ExecutionPermissions(artifact_write=allow_artifact_write),
        )

    def validate_ast(self, path: Path) -> tuple[bool, str | None]:
        """Validate syntax integrity of modified file using language AST and config parsers."""
        if path.is_symlink():
            return False, "target became a symbolic link"
        if not path.exists():
            return False, "target is missing"
        if not path.is_file():
            return False, "target is not a regular file"

        content = path.read_text(encoding="utf-8", errors="replace")

        if path.suffix in (".py", ".pyi"):
            try:
                ast.parse(content, filename=str(path))
                return True, None
            except SyntaxError as e:
                return (
                    False,
                    f"Python SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}",
                )
        elif path.suffix == ".json":
            try:
                json.loads(content)
                return True, None
            except json.JSONDecodeError as e:
                return (
                    False,
                    f"JSON syntax error at line {e.lineno}, col {e.colno}: {e.msg}",
                )
        elif path.suffix == ".toml":
            try:
                tomllib.loads(content)
                return True, None
            except tomllib.TOMLDecodeError as e:
                return False, f"TOML syntax error: {e}"

        return True, None

    @staticmethod
    def _restore_owned_targets(
        journal: SnapshotJournal, result: ToolResult
    ) -> ToolResult:
        errors = journal.rollback_all()
        if not errors:
            return result
        from rush.tools.common import _bounded_redacted_output

        evidence = [_bounded_redacted_output(error) for error in errors]
        result["summary"] = (
            f"{result['summary']}; rollback failed: {'; '.join(evidence)}"
        )
        result["metadata"] = {
            **(result.get("metadata") or {}),
            "rollback_errors": evidence,
        }
        return result

    def run(
        self,
        path: Path | None = None,
        config: RushConfig | None = None,
        permissions: ExecutionPermissions | None = None,
        dry_run: bool = False,
        force: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        from rush.tools.common import (
            _bounded_redacted_output,
            elapsed_ms,
            now_ms,
            resolve_binary,
            run_subprocess,
        )

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
                if res.returncode != 0:
                    safe_error = _bounded_redacted_output(res.stderr)
                    return ToolResult(
                        tool=self.name,
                        status="error",
                        duration_ms=0,
                        summary=f"fix: Git status failed: {safe_error or 'no stderr'}",
                        findings=[],
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
            except Exception as exc:  # noqa: BLE001
                safe_error = _bounded_redacted_output(str(exc))
                return ToolResult(
                    tool=self.name,
                    status="error",
                    duration_ms=0,
                    summary=f"fix: Git status failed: {safe_error}",
                    findings=[],
                )

        granted = permissions or ExecutionPermissions()
        if not dry_run:
            from rush.permissions import check_permissions

            allowed, missing = check_permissions(
                ExecutionPermissions(artifact_write=True), granted
            )
            if not allowed:
                return ToolResult(
                    tool=self.name,
                    engine="ruff",
                    status="skipped",
                    duration_ms=0,
                    summary=f"skipped: fix apply requires {', '.join(missing)}",
                    findings=[],
                )

        # 3. Ask Ruff for its exact eligible files so native excludes remain active.
        started = now_ms()
        ruff = resolve_binary("ruff")
        if ruff is None:
            return ToolResult(
                tool=self.name,
                engine="ruff",
                status="skipped",
                duration_ms=elapsed_ms(started),
                summary="skipped: Ruff is not installed",
                findings=[],
            )
        try:
            discovery = run_subprocess(
                [ruff, "check", "--show-files", "--no-cache", str(target_path)],
                cwd=repo_root,
            )
        except KeyboardInterrupt:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            safe_error = _bounded_redacted_output(str(exc))
            return ToolResult(
                tool=self.name,
                engine="ruff",
                status="error",
                duration_ms=elapsed_ms(started),
                summary=f"fix: Ruff target discovery failed: {safe_error}",
                findings=[],
            )
        discovery_stderr = _bounded_redacted_output(discovery.stderr)
        if discovery.returncode != 0:
            return ToolResult(
                tool=self.name,
                engine="ruff",
                status="error",
                duration_ms=elapsed_ms(started),
                summary=f"fix: Ruff target discovery failed ({discovery.returncode}): {discovery_stderr or 'no stderr'}",
                findings=[],
                raw={"stderr": discovery_stderr},
            )

        targets: list[Path] = []
        for line in discovery.stdout.splitlines():
            candidate = Path(line)
            if candidate.suffix not in {".py", ".pyi"}:
                continue
            if not candidate.is_absolute():
                candidate = repo_root / candidate
            resolved = candidate.resolve()
            try:
                resolved.relative_to(repo_root)
            except ValueError:
                return ToolResult(
                    tool=self.name,
                    engine="ruff",
                    status="error",
                    duration_ms=0,
                    summary=f"fix: Python target outside repository: {candidate}",
                    findings=[],
                )
            targets.append(candidate)
        targets = sorted(set(targets))
        journal = SnapshotJournal()
        if not dry_run:
            capture_errors = journal.capture(targets)
            if capture_errors:
                evidence = [_bounded_redacted_output(error) for error in capture_errors]
                return ToolResult(
                    tool=self.name,
                    engine="ruff",
                    status="error",
                    duration_ms=elapsed_ms(started),
                    summary=f"fix: snapshot failed: {'; '.join(evidence)}",
                    findings=[],
                    metadata={"snapshot_errors": evidence},
                )

        # 4. Dispatch engine fixes and validate every mutation exit.
        try:
            result = self._run_engine_fixes(
                ruff=ruff,
                targets=targets,
                repo_root=repo_root,
                permissions=granted,
                dry_run=dry_run,
                started=started,
                initial_stderr=discovery_stderr,
            )
            if result["status"] == "error":
                return (
                    self._restore_owned_targets(journal, result)
                    if not dry_run
                    else result
                )
            if result["status"] == "skipped":
                return result

            for target in targets:
                valid, error = self.validate_ast(target)
                if not valid:
                    result = ToolResult(
                        tool=self.name,
                        engine="ruff",
                        status="error",
                        duration_ms=elapsed_ms(started),
                        summary=f"fix: invalid AST in '{target.name}': {error}",
                        findings=[],
                    )
                    return (
                        self._restore_owned_targets(journal, result)
                        if not dry_run
                        else result
                    )
            return result
        except KeyboardInterrupt as exc:
            if not dry_run:
                errors = journal.rollback_all()
                if errors:
                    exc.add_note(
                        "fix rollback failed: "
                        + "; ".join(_bounded_redacted_output(error) for error in errors)
                    )
            raise
        except Exception as exc:  # noqa: BLE001
            safe_error = _bounded_redacted_output(str(exc))
            result = ToolResult(
                tool=self.name,
                engine="ruff",
                status="error",
                duration_ms=elapsed_ms(started),
                summary=f"fix: Ruff execution or AST validation failed: {safe_error}",
                findings=[],
            )
            return (
                self._restore_owned_targets(journal, result) if not dry_run else result
            )

    def _run_engine_fixes(
        self,
        ruff: str,
        targets: Sequence[Path],
        repo_root: Path,
        permissions: ExecutionPermissions,
        dry_run: bool = False,
        started: int = 0,
        initial_stderr: str = "",
    ) -> ToolResult:
        from rush.tools.common import (
            _bounded_redacted_output,
            elapsed_ms,
            run_subprocess,
        )

        log_subsystem(
            "fix",
            "INFO",
            f"Running automated code remediation on {len(targets)} Python files (dry_run={dry_run})",
        )
        if not targets:
            return ToolResult(
                tool=self.name,
                engine="ruff",
                status="skipped",
                duration_ms=elapsed_ms(started),
                summary="skipped: no Python targets",
                findings=[],
            )

        target_args = [str(path) for path in targets]
        fmt_cmd = [
            ruff,
            "format",
            *(["--diff"] if dry_run else []),
            "--no-cache",
            *target_args,
        ]
        proc_fmt = run_subprocess(fmt_cmd, cwd=repo_root)
        stderr = _bounded_redacted_output(
            "\n".join(filter(None, [initial_stderr, proc_fmt.stderr]))
        )
        format_changed = dry_run and proc_fmt.returncode == 1
        if proc_fmt.returncode != 0 and not format_changed:
            return ToolResult(
                tool=self.name,
                engine="ruff",
                status="error",
                duration_ms=elapsed_ms(started),
                summary=f"fix: Ruff format failed ({proc_fmt.returncode}): {stderr or 'no stderr'}",
                findings=[],
                raw={"stderr": stderr},
            )

        chk_cmd = [
            ruff,
            "check",
            *(["--diff"] if dry_run else ["--fix"]),
            "--no-cache",
            *target_args,
        ]
        proc_chk = run_subprocess(chk_cmd, cwd=repo_root)
        stderr = _bounded_redacted_output(
            "\n".join(filter(None, [stderr, proc_chk.stderr]))
        )
        if proc_chk.returncode not in {0, 1}:
            return ToolResult(
                tool=self.name,
                engine="ruff",
                status="error",
                duration_ms=elapsed_ms(started),
                summary=f"fix: Ruff check failed ({proc_chk.returncode}): {stderr or 'no stderr'}",
                findings=[],
                raw={"stderr": stderr},
            )

        remaining_findings = proc_chk.returncode == 1
        if dry_run:
            proc_verify = run_subprocess(
                [ruff, "check", "--no-cache", *target_args], cwd=repo_root
            )
            stderr = _bounded_redacted_output(
                "\n".join(filter(None, [stderr, proc_verify.stderr]))
            )
            if proc_verify.returncode not in {0, 1}:
                return ToolResult(
                    tool=self.name,
                    engine="ruff",
                    status="error",
                    duration_ms=elapsed_ms(started),
                    summary=f"fix: Ruff read-only check failed ({proc_verify.returncode}): {stderr or 'no stderr'}",
                    findings=[],
                    raw={"stderr": stderr},
                )
            remaining_findings = remaining_findings or proc_verify.returncode == 1

        status: ToolStatus = "warn" if format_changed or remaining_findings else "ok"
        mode_str = " (dry run)" if dry_run else ""
        return ToolResult(
            tool=self.name,
            engine="ruff",
            status=status,
            duration_ms=elapsed_ms(started),
            summary=(
                f"fix: Ruff format/check completed{mode_str}"
                if status == "ok"
                else f"fix: Ruff format completed; lint findings remain{mode_str}"
            ),
            findings=[],
            raw={"stderr": stderr},
        )
