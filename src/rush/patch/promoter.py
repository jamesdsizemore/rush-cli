"""Atomic patch promoter from sandbox to developer working tree."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.patch.contracts import PatchContract
from rush.permissions import ExecutionPermissions
from rush.tools.common import run_subprocess


def _reserve_diff_file(physical_root: PhysicalRoot) -> Path:
    path = physical_root.open_contained(
        Path(".rush") / f"promote_{uuid.uuid4().hex}.patch", purpose="write"
    )
    with path.open("x"):
        pass
    return path


def _write_sandbox_diff(sandbox_dir: Path, output_path: Path) -> bool:
    result = run_subprocess(
        ["git", "diff", "--binary", f"--output={output_path}", "HEAD"],
        cwd=sandbox_dir,
    )
    return result.returncode == 0


def sandbox_diff_digest(sandbox_dir: Path, repo_root: Path) -> str:
    """Hash exact sandbox diff bytes without routing source through redacted output."""
    physical_root = PhysicalRoot(repo_root)
    patch_file = _reserve_diff_file(physical_root)
    try:
        if not _write_sandbox_diff(sandbox_dir, patch_file):
            raise ValueError("Sandbox diff could not be captured.")
        content = patch_file.read_bytes()
        return hashlib.sha256(content).hexdigest() if content else ""
    finally:
        owned_path = physical_root.open_contained(
            patch_file.relative_to(physical_root.root_path), purpose="write"
        )
        if owned_path.exists():
            owned_path.unlink()


class PatchPromoter:
    """Promotes verified file changes from an ephemeral sandbox to the main working tree."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.physical_root = PhysicalRoot(self.repo_root)

    def promote_sandbox_diff(
        self,
        sandbox_dir: Path,
        contract: PatchContract | None = None,
        *,
        permissions: ExecutionPermissions | None = None,
    ) -> tuple[bool, str]:
        if permissions is None or not permissions.artifact_write:
            return False, "Patch promotion requires explicit artifact-write permission."

        # 1. Policy check: ordinary promoter refuses policy-changing patches
        if contract and contract.review_class in ("policy-changing", "privileged"):
            return (
                False,
                (
                    f"Policy-changing patch with review_class '{contract.review_class}' "
                    "cannot receive ordinary verified promotion."
                ),
            )

        try:
            sandbox_relative = sandbox_dir.resolve().relative_to(self.repo_root)
            sandbox_dir = self.physical_root.open_contained(
                sandbox_relative, purpose="read"
            )
        except (ContainmentError, ValueError, OSError):
            return False, "Sandbox checkout is outside the source repository."
        sandbox_top = run_subprocess(
            ["git", "rev-parse", "--show-toplevel"], cwd=sandbox_dir
        )
        sandbox_head = run_subprocess(["git", "rev-parse", "HEAD"], cwd=sandbox_dir)
        if (
            sandbox_top.returncode != 0
            or Path(sandbox_top.stdout.strip()).resolve() != sandbox_dir.resolve()
            or sandbox_head.returncode != 0
            or (
                contract is not None
                and contract.base_commit
                and sandbox_head.stdout.strip() != contract.base_commit
            )
            or (
                contract is not None
                and contract.sandbox_path.resolve() != sandbox_dir.resolve()
            )
        ):
            return False, "Sandbox is not the verified checkout bound to this patch."

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

        # 3. Verify source identity before reading the sandbox patch.
        rev_proc = run_subprocess(["git", "rev-parse", "HEAD"], cwd=self.repo_root)
        if rev_proc.returncode != 0 or (
            contract is not None
            and contract.base_commit
            and rev_proc.stdout.strip() != contract.base_commit
        ):
            return False, "Source checkout identity changed before promotion."

        patch_file = _reserve_diff_file(self.physical_root)
        owns_patch_file = True
        if not _write_sandbox_diff(sandbox_dir, patch_file):
            patch_file.unlink()
            return False, "Sandbox diff could not be captured for promotion."
        if patch_file.stat().st_size == 0:
            patch_file.unlink()
            return False, "No diff found in sandbox to promote."

        current_status = run_subprocess(
            ["git", "status", "--porcelain"], cwd=self.repo_root
        )
        current_head = run_subprocess(["git", "rev-parse", "HEAD"], cwd=self.repo_root)
        if (
            current_status.returncode != 0
            or any(
                not line.strip().endswith((".rush/", ".rush"))
                for line in current_status.stdout.splitlines()
            )
            or current_head.returncode != 0
            or current_head.stdout.strip() != rev_proc.stdout.strip()
        ):
            patch_file.unlink()
            return False, "Source checkout identity changed before promotion."

        try:
            apply_proc = run_subprocess(
                ["git", "apply", "--whitespace=nowarn", str(patch_file)],
                cwd=self.repo_root,
            )
            if apply_proc.returncode == 0:
                return True, "Patch successfully promoted to main working tree."

            return False, f"Promotion failed: {apply_proc.stderr or apply_proc.stdout}"
        except Exception as e:  # noqa: BLE001
            return False, f"Promotion error: {e}"
        finally:
            if owns_patch_file:
                owned_path = self.physical_root.open_contained(
                    patch_file.relative_to(self.repo_root), purpose="write"
                )
                if owned_path.exists():
                    owned_path.unlink()
