"""Governance test for Phase 58: R-016 Physical Containment and Atomic Rollback."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.patch.contracts import (
    DirtyWorkspaceError,
    PatchContract,
    VerifierCommandPlan,
)
from rush.patch.promoter import PatchPromoter
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.verifier import PatchVerifier


def _create_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "RushTester"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "rush@example.com"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    gitignore = path / ".gitignore"
    gitignore.write_text(".rush/\n", encoding="utf-8")
    f = path / "app.py"
    f.write_text("def value():\n    return 1\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", ".gitignore", "app.py"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=path, check=True, capture_output=True
    )
    return path


def test_patch_sandbox_enforces_physical_containment_and_rollback(
    tmp_path: Path,
) -> None:
    """T-58.20 (R-016 Governance Test): Asserts physical containment under PhysicalRoot and atomic rollback on failure."""
    repo = _create_git_repo(tmp_path / "repo_governance")
    orig_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    orig_content = (repo / "app.py").read_text(encoding="utf-8")

    # 1. PhysicalRoot containment validation
    phys_root = PhysicalRoot(repo)
    # Relative path inside repo is valid
    assert phys_root.open_contained(".rush/worktrees") is not None

    # Traversal or escape outside repo raises ContainmentError
    with pytest.raises(ContainmentError):
        phys_root.open_contained("../escaped_dir")

    mgr = PatchSandboxManager(repo_root=repo)
    assert mgr.physical_root.root_path == repo.resolve()

    # 2. Pre-flight dirty workspace check fails closed
    dirty_file = repo / "temp.txt"
    dirty_file.write_text("uncommitted\n", encoding="utf-8")
    with pytest.raises(DirtyWorkspaceError):
        mgr.create_sandbox()
    dirty_file.unlink()

    # 3. Clean sandbox creation operates strictly under PhysicalRoot
    sb_path = mgr.create_sandbox()
    try:
        assert sb_path.exists()
        assert sb_path.is_relative_to(repo)
        # Sandbox must be inside .rush/worktrees
        assert (repo / ".rush" / "worktrees") in sb_path.parents

        # 4. Modifying sandbox and failing verifier executes atomic rollback
        (sb_path / "app.py").write_text(
            "def value():\n    return 99\n", encoding="utf-8"
        )

        contract = PatchContract(
            base_commit=orig_head,
            base_tree_digest=subprocess.run(
                ["git", "rev-parse", "HEAD^{tree}"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
            patch_content_digest="dummy",
            sandbox_path=sb_path,
            required_commands=(
                VerifierCommandPlan(
                    command=("python", "-c", "import sys; sys.exit(1)")
                ),
            ),
            config_digest="cfg",
            review_class="standard",
        )
        verifier = PatchVerifier(sb_path, contract=contract)
        ok, _ = verifier.verify_patch()
        assert ok is False
        assert verifier.last_result is not None
        assert verifier.last_result.outcome == "failed"

        # 5. Promotion refused; repo remains at orig_head and clean
        promoter = PatchPromoter(repo_root=repo)
        promo_ok, _promo_msg = promoter.promote_sandbox_diff(
            sb_path,
            contract=PatchContract(
                base_commit=orig_head,
                base_tree_digest="digest",
                patch_content_digest="dummy",
                sandbox_path=sb_path,
                required_commands=(),
                config_digest="cfg",
                review_class="policy-changing",
            ),
        )
        assert promo_ok is False
        current_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert current_head == orig_head
        assert (repo / "app.py").read_text(encoding="utf-8") == orig_content
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert status == ""

    finally:
        mgr.cleanup_sandbox(sb_path)
        assert not sb_path.exists()
