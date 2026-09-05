"""Atomic patch promoter from sandbox to developer working tree."""

from __future__ import annotations

import shutil
from pathlib import Path

from rush.io.physical_paths import PhysicalRoot
from rush.patch.contracts import PatchContract
from rush.tools.common import run_subprocess


class PatchPromoter:
    """Promotes verified file changes from an ephemeral sandbox to the main working tree."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.physical_root = PhysicalRoot(self.repo_root)

    def promote_sandbox_diff(
        self, sandbox_dir: Path, contract: PatchContract | None = None
    ) -> tuple[bool, str]:
        # 1. Policy check: ordinary promoter refuses policy-changing patches
        if contract and contract.review_class in ("policy-changing", "privileged"):
            return (
                False,
                (
                    f"Policy-changing patch with review_class '{contract.review_class}' "
                    "cannot receive ordinary verified promotion."
                ),
            )

        # 2. Check working tree clean before applying (ignoring .rush metadata)
        proc_status = run_subprocess(
            ["git", "status", "--porcelain"], cwd=self.repo_root
        )
        if proc_status.returncode != 0:
            return (
                False,
                f"Git status check failed on '{self.repo_root}': {proc_status.stderr or proc_status.stdout}",
            )

        dirty_lines = [
            line
            for line in proc_status.stdout.splitlines()
            if not line.strip().endswith(".rush/")
            and not line.strip().endswith(".rush")
        ]
        if dirty_lines:
            return (
                False,
                "Main working tree has uncommitted changes. Refusing promotion.",
            )

        # 3. Capture pre-patch git commit HEAD
        rev_proc = run_subprocess(["git", "rev-parse", "HEAD"], cwd=self.repo_root)
        pre_patch_head = rev_proc.stdout.strip() if rev_proc.returncode == 0 else "HEAD"

        proc = run_subprocess(["git", "diff"], cwd=sandbox_dir)
        if proc.returncode != 0 or not proc.stdout.strip():
            return False, "No diff found in sandbox to promote."

        patch_file = self.repo_root / ".promote.patch"
        try:
            from rush.safety.redactor import sanitize_value

            clean_diff = sanitize_value(proc.stdout).value
            patch_file.write_text(clean_diff, encoding="utf-8")
            apply_proc = run_subprocess(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=self.repo_root,
            )
            if apply_proc.returncode == 0:
                return True, "Patch successfully promoted to main working tree."

            # Promotion failed: atomic rollback
            self.rollback(pre_patch_head)
            return False, f"Promotion failed: {apply_proc.stderr or apply_proc.stdout}"
        except Exception as e:  # noqa: BLE001
            self.rollback(pre_patch_head)
            return False, f"Promotion error: {e}"
        finally:
            if patch_file.exists():
                patch_file.unlink()

    def rollback(self, target_commit: str = "HEAD") -> None:
        """Atomic rollback restoring working tree to pre-patch state and cleaning sandbox worktrees."""
        if target_commit:
            run_subprocess(
                ["git", "reset", "--hard", target_commit], cwd=self.repo_root
            )
        run_subprocess(["git", "clean", "-fd"], cwd=self.repo_root)
        self.cleanup_worktrees()

    def cleanup_worktrees(self) -> None:
        worktrees_dir = self.repo_root / ".rush" / "worktrees"
        if worktrees_dir.exists():
            for entry in list(worktrees_dir.iterdir()):
                if entry.is_dir():
                    run_subprocess(
                        ["git", "worktree", "remove", "--force", str(entry)],
                        cwd=self.repo_root,
                    )
                    if entry.exists():
                        shutil.rmtree(entry, ignore_errors=True)
