"""Ephemeral Git worktree sandbox manager for safe AI patch execution."""

from __future__ import annotations

import os
import stat
import uuid
from pathlib import Path

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.patch.contracts import DirtyWorkspaceError, PatchVerificationError
from rush.tools.common import run_subprocess


class PatchSandboxManager:
    """Manages isolated Git worktrees for safe patch testing and regression verification."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.physical_root = PhysicalRoot(self.repo_root)
        self.worktrees_dir = self.repo_root / ".rush" / "worktrees"
        self._owned_sandboxes: dict[Path, tuple[int, int]] = {}

    def _ensure_rush_dir(self) -> None:
        rush_dir = self.physical_root.open_contained(".rush", purpose="write")
        rush_dir.mkdir(parents=True, exist_ok=True)
        gitignore = self.physical_root.open_contained(
            ".rush/.gitignore", purpose="write"
        )
        if not gitignore.exists():
            gitignore.write_text("*\n", encoding="utf-8")
        worktrees_dir = self.physical_root.open_contained(
            ".rush/worktrees", purpose="write"
        )
        worktrees_dir.mkdir(parents=True, exist_ok=True)

    def create_sandbox(self) -> Path:
        # Pre-flight clean check: fail-closed if repo has uncommitted or untracked changes
        proc = run_subprocess(["git", "status", "--porcelain"], cwd=self.repo_root)
        if proc.returncode != 0:
            raise DirtyWorkspaceError(
                f"Failed to check git status: {proc.stderr or proc.stdout}"
            )
        dirty_lines = [
            line
            for line in proc.stdout.splitlines()
            if not line.strip().endswith(".rush/")
            and not line.strip().endswith(".rush")
        ]
        if dirty_lines:
            raise DirtyWorkspaceError(
                "Working directory has uncommitted changes. Patch sandbox refuses dirty workspace."
            )

        self._ensure_rush_dir()
        sandbox_id = f"sandbox_{uuid.uuid4().hex[:8]}"
        sandbox_path = self.physical_root.open_contained(
            f".rush/worktrees/{sandbox_id}"
        )
        if sandbox_path.exists():
            raise PatchVerificationError(
                "Allocated patch sandbox path already exists and is not invocation-owned."
            )

        head_proc = run_subprocess(["git", "rev-parse", "HEAD"], cwd=self.repo_root)
        if head_proc.returncode != 0 or not head_proc.stdout.strip():
            raise PatchVerificationError("Source checkout HEAD could not be verified.")
        source_head = head_proc.stdout.strip()

        proc = run_subprocess(
            ["git", "worktree", "add", "--detach", str(sandbox_path), "HEAD"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            raise PatchVerificationError("Git worktree creation failed.")

        sandbox_path = self.physical_root.open_contained(
            sandbox_path.relative_to(self.repo_root), purpose="write"
        )
        try:
            sandbox_stat = os.lstat(sandbox_path)
        except OSError as exc:
            raise PatchVerificationError(
                "Git worktree creation did not produce a verified checkout."
            ) from exc
        if not stat.S_ISDIR(sandbox_stat.st_mode):
            raise PatchVerificationError(
                "Git worktree creation did not produce a verified checkout."
            )
        sandbox_key = sandbox_path.absolute()
        self._owned_sandboxes[sandbox_key] = (
            sandbox_stat.st_dev,
            sandbox_stat.st_ino,
        )

        top_proc = run_subprocess(
            ["git", "rev-parse", "--show-toplevel"], cwd=sandbox_path
        )
        sandbox_head_proc = run_subprocess(
            ["git", "rev-parse", "HEAD"], cwd=sandbox_path
        )
        verified = (
            sandbox_path.is_dir()
            and top_proc.returncode == 0
            and Path(top_proc.stdout.strip()).resolve() == sandbox_path.resolve()
            and sandbox_head_proc.returncode == 0
            and sandbox_head_proc.stdout.strip() == source_head
        )
        if not verified:
            self.cleanup_sandbox(sandbox_path)
            raise PatchVerificationError(
                "Git worktree creation did not produce a verified checkout."
            )

        return sandbox_path

    def cleanup_sandbox(self, sandbox_path: Path) -> None:
        sandbox_key = Path(sandbox_path).absolute()
        owned_identity = self._owned_sandboxes.get(sandbox_key)
        if owned_identity is None:
            raise PatchVerificationError(
                "Patch sandbox cleanup is restricted to invocation-owned worktrees."
            )
        try:
            relative = sandbox_key.relative_to(self.repo_root)
            owned_path = self.physical_root.open_contained(relative, purpose="write")
        except (ContainmentError, ValueError) as exc:
            raise PatchVerificationError(
                "Invocation-owned patch sandbox failed containment revalidation."
            ) from exc
        if not owned_path.exists():
            self._owned_sandboxes.pop(sandbox_key, None)
            return
        current_stat = os.lstat(owned_path)
        if (
            current_stat.st_dev,
            current_stat.st_ino,
        ) != owned_identity or not stat.S_ISDIR(current_stat.st_mode):
            raise PatchVerificationError(
                "Invocation-owned patch sandbox identity changed before cleanup."
            )
        if not owned_path.resolve().is_relative_to(self.repo_root):
            raise ContainmentError(
                "PATH_ESCAPE_DISALLOWED",
                f"Sandbox path escapes physical root: {owned_path.resolve()}",
                str(sandbox_path),
            )

        removed = run_subprocess(
            ["git", "worktree", "remove", "--force", str(owned_path)],
            cwd=self.repo_root,
        )
        if removed.returncode != 0 or owned_path.exists():
            raise PatchVerificationError("Invocation-owned worktree cleanup failed.")
        self._owned_sandboxes.pop(sandbox_key, None)

    def cleanup_all(self) -> None:
        for sandbox_path in list(self._owned_sandboxes):
            self.cleanup_sandbox(sandbox_path)
