"""Unified diff parser and safe patch applier."""

from __future__ import annotations

from pathlib import Path

from rush.patch.diff_parser import UnifiedDiffParser
from rush.patch.syntax_guard import PatchSyntaxGuard
from rush.tools.common import run_subprocess


class PatchApplier:
    """Applies unified diff patches to target working directories with syntax verification."""

    @staticmethod
    def apply_patch_to_dir(target_dir: Path, unified_diff: str) -> tuple[bool, str]:
        if not target_dir.exists():
            return False, f"Target directory '{target_dir}' does not exist."

        try:
            parsed = UnifiedDiffParser.parse_patch(unified_diff, target_dir)
        except (ValueError, PermissionError, OSError) as e:
            return False, f"Diff security validation failed: {e}"

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
                return False, f"git apply failed: {proc.stderr or proc.stdout}"

            # Post-patch AST syntax verification
            for p_file in parsed:
                f_path = target_dir / p_file.new_path
                ok, err = PatchSyntaxGuard.validate_file_syntax(f_path)
                if not ok:
                    return (
                        False,
                        f"Post-patch syntax check failed on {p_file.new_path}: {err}",
                    )

            return True, "Patch applied cleanly with valid syntax."
        finally:
            if patch_file.exists():
                patch_file.unlink()
