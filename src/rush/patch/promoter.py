"""Atomic patch promoter from sandbox to developer working tree."""

from __future__ import annotations

from pathlib import Path

from rush.tools.common import run_subprocess


class PatchPromoter:
    """Promotes verified file changes from an ephemeral sandbox to the main working tree."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def promote_sandbox_diff(self, sandbox_dir: Path) -> tuple[bool, str]:
        proc = run_subprocess(["git", "diff"], cwd=sandbox_dir)
        if proc.returncode != 0 or not proc.stdout.strip():
            return False, "No diff found in sandbox to promote."

        patch_file = self.repo_root / ".promote.patch"
        try:
            patch_file.write_text(proc.stdout, encoding="utf-8")
            apply_proc = run_subprocess(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=self.repo_root,
            )
            if apply_proc.returncode == 0:
                return True, "Patch successfully promoted to main working tree."
            return False, f"Promotion failed: {apply_proc.stderr or apply_proc.stdout}"
        finally:
            if patch_file.exists():
                patch_file.unlink()
