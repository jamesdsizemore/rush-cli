"""Unified diff parser and safe patch applier."""

from __future__ import annotations

import stat
from pathlib import Path

from rush.io.atomic_file import AtomicFile, AtomicWriteError, SanitizedBytes
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.patch.contracts import DirtyWorkspaceError
from rush.patch.syntax_guard import PatchSyntaxGuard
from rush.patch_generator import apply_unified_patch, patch_target_paths
from rush.tools.common import run_subprocess


class PatchApplier:
    """Applies unified diff patches to target working directories with syntax verification."""

    @staticmethod
    def apply_patch_to_dir(
        target_dir: Path, unified_diff: str, check_clean: bool = False
    ) -> tuple[bool, str]:
        if not target_dir.exists():
            return False, f"Target directory '{target_dir}' does not exist."

        physical_root = PhysicalRoot(target_dir)
        target_paths = patch_target_paths(unified_diff)
        if target_paths is None:
            return False, "Diff security validation failed: malformed patch."
        snapshots: dict[str, tuple[bytes, int]] = {}
        try:
            for relative_path in target_paths:
                target = physical_root.open_contained(relative_path, purpose="read")
                if not target.is_file():
                    return False, f"Patch target '{relative_path}' does not exist."
                snapshots[relative_path] = (
                    target.read_bytes(),
                    stat.S_IMODE(target.stat().st_mode),
                )
        except (ContainmentError, OSError) as exc:
            return False, f"Diff security validation failed: {exc}"

        # If inside a git repository, optionally require a clean checkout.
        is_git_repo = (target_dir / ".git").exists() or (
            target_dir.parent / ".git"
        ).exists()
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
        try:
            if not apply_unified_patch(unified_diff, target_dir):
                restored = PatchApplier._restore_owned(target_dir, snapshots)
                return (
                    False,
                    "Patch application failed."
                    if restored
                    else "Patch application failed and owned targets could not be restored.",
                )

            # Post-patch AST syntax verification
            for relative_path in snapshots:
                f_path = physical_root.open_contained(relative_path, purpose="read")
                ok, err = PatchSyntaxGuard.validate_file_syntax(f_path)
                if not ok:
                    restored = PatchApplier._restore_owned(target_dir, snapshots)
                    return (
                        False,
                        f"Post-patch syntax check failed on {relative_path}: {err}"
                        + ("" if restored else "; owned targets could not be restored"),
                    )

            return True, "Patch applied cleanly with valid syntax."
        except KeyboardInterrupt:
            PatchApplier._restore_owned(target_dir, snapshots)
            raise
        except Exception:  # noqa: BLE001
            restored = PatchApplier._restore_owned(target_dir, snapshots)
            return (
                False,
                "Patch verification failed unexpectedly."
                if restored
                else "Patch verification failed and owned targets could not be restored.",
            )

    @staticmethod
    def _restore_owned(
        target_dir: Path, snapshots: dict[str, tuple[bytes, int]]
    ) -> bool:
        physical_root = PhysicalRoot(target_dir)
        writer = AtomicFile(physical_root)
        restored = True
        for relative_path, (content, mode) in snapshots.items():
            try:
                target = physical_root.open_contained(relative_path, purpose="write")
                if not target.exists() or target.read_bytes() != content:
                    writer.write_bytes(relative_path, SanitizedBytes(content))
                target = physical_root.open_contained(relative_path, purpose="write")
                if stat.S_IMODE(target.stat().st_mode) != mode:
                    target.chmod(mode)
            except (AtomicWriteError, ContainmentError, OSError):
                restored = False
        return restored
