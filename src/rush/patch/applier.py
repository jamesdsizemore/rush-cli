"""Unified diff parser and safe patch applier."""

from __future__ import annotations

import shutil
from pathlib import Path

from rush.io.physical_paths import PhysicalRoot
from rush.patch.contracts import DirtyWorkspaceError
from rush.patch.diff_parser import UnifiedDiffParser
from rush.patch.syntax_guard import PatchSyntaxGuard
from rush.tools.common import run_subprocess


class PatchApplier:
    """Applies unified diff patches to target working directories with syntax verification."""

    @staticmethod
    def apply_patch_to_dir(
        target_dir: Path, unified_diff: str, check_clean: bool = False
    ) -> tuple[bool, str]:
        if not target_dir.exists():
            return False, f"Target directory '{target_dir}' does not exist."

        # Physical containment validation
        PhysicalRoot(target_dir)

        try:
            parsed = UnifiedDiffParser.parse_patch(unified_diff, target_dir)
        except (ValueError, PermissionError, OSError) as e:
            return False, f"Diff security validation failed: {e}"

        # If inside a git repository, check status and capture pre-patch commit HEAD
        is_git_repo = (target_dir / ".git").exists() or (
            target_dir.parent / ".git"
        ).exists()
        pre_patch_head: str | None = None
        if is_git_repo:
            status_proc = run_subprocess(
                ["git", "status", "--porcelain"], cwd=target_dir
            )
            if (
                check_clean
                and status_proc.returncode == 0
                and status_proc.stdout.strip()
            ):
                raise DirtyWorkspaceError(
                    "Target repository has uncommitted changes. PatchApplier refuses dirty workspace."
                )
            head_proc = run_subprocess(["git", "rev-parse", "HEAD"], cwd=target_dir)
            if head_proc.returncode == 0:
                pre_patch_head = head_proc.stdout.strip()

        patch_file = target_dir / ".temp_patch.diff"
        try:
            patch_file.write_text(unified_diff, encoding="utf-8")
            proc = run_subprocess(
                [
                    "git",
                    "apply",
                    "--ignore-whitespace",
                    "--whitespace=nowarn",
                    str(patch_file),
                ],
                cwd=target_dir,
            )
            if proc.returncode != 0:
                PatchApplier._rollback(target_dir, pre_patch_head)
                return False, f"git apply failed: {proc.stderr or proc.stdout}"

            # Post-patch AST syntax verification
            for p_file in parsed:
                f_path = target_dir / p_file.new_path
                ok, err = PatchSyntaxGuard.validate_file_syntax(f_path)
                if not ok:
                    PatchApplier._rollback(target_dir, pre_patch_head)
                    return (
                        False,
                        f"Post-patch syntax check failed on {p_file.new_path}: {err}",
                    )

            return True, "Patch applied cleanly with valid syntax."
        finally:
            if patch_file.exists():
                patch_file.unlink()

    @staticmethod
    def _rollback(target_dir: Path, target_commit: str | None) -> None:
        if target_commit:
            run_subprocess(["git", "reset", "--hard", target_commit], cwd=target_dir)
            run_subprocess(["git", "clean", "-fd"], cwd=target_dir)
        worktrees_dir = target_dir / ".rush" / "worktrees"
        if worktrees_dir.exists():
            for item in list(worktrees_dir.iterdir()):
                if item.is_dir():
                    run_subprocess(
                        ["git", "worktree", "remove", "--force", str(item)],
                        cwd=target_dir,
                    )
                    if item.exists():
                        shutil.rmtree(item, ignore_errors=True)
