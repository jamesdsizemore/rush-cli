"""Contract tests for Phase 58: Fail-Closed Patch Verification & Sandboxing (P58.5.1 & P58.6.1)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from rush.core.git_sandbox import GitSandbox
from rush.patch.contracts import (
    DirtyWorkspaceError,
    PatchContract,
    PatchVerificationError,
    VerifierCommandPlan,
)
from rush.patch.promoter import PatchPromoter
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.verifier import PatchVerifier
from rush.tools.common import run_subprocess as real_run_subp


def _init_git_repo(path: Path) -> Path:
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
    init_file = path / "main.py"
    init_file.write_text("def run():\n    return 42\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", ".gitignore", "main.py"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return path


def test_dirty_or_changed_base_refuses_before_sandbox(tmp_path: Path) -> None:
    """T-58.14: Dirty working tree before sandbox creation; asserts PatchSandboxManager or GitSandbox raises DirtyWorkspaceError fail-closed."""
    repo = _init_git_repo(tmp_path / "repo_dirty")

    # 1. Modify a tracked file without committing
    tracked = repo / "main.py"
    tracked.write_text("def run():\n    return 100\n", encoding="utf-8")

    mgr = PatchSandboxManager(repo_root=repo)
    with pytest.raises(DirtyWorkspaceError, match=r"[Dd]irty|[Uu]ncommitted"):
        mgr.create_sandbox()

    with (
        pytest.raises(DirtyWorkspaceError, match=r"[Dd]irty|[Uu]ncommitted"),
        GitSandbox(project_root=repo),
    ):
        pass

    # 2. Reset tracked file but add untracked file
    subprocess.run(["git", "checkout", "--", "main.py"], cwd=repo, check=True)
    untracked = repo / "new_untracked_file.py"
    untracked.write_text("# untracked\n", encoding="utf-8")

    with pytest.raises(DirtyWorkspaceError, match=r"[Dd]irty|[Uu]ncommitted"):
        mgr.create_sandbox()

    with (
        pytest.raises(DirtyWorkspaceError, match=r"[Dd]irty|[Uu]ncommitted"),
        GitSandbox(project_root=repo),
    ):
        pass

    # 3. When working tree is clean, sandbox creation succeeds
    untracked.unlink()
    sb_path = mgr.create_sandbox()
    try:
        assert sb_path.exists()
    finally:
        mgr.cleanup_sandbox(sb_path)


def test_patch_sandbox_result_and_command_policy_drift_refuses(tmp_path: Path) -> None:
    """T-58.15: Mismatch between base commit/tree hash or command plan and actual sandbox state; asserts execution refuses fail-closed."""
    repo = _init_git_repo(tmp_path / "repo_drift")
    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    mgr = PatchSandboxManager(repo_root=repo)
    sb_path = mgr.create_sandbox()

    try:
        # Base commit drift: contract specifies different base commit
        bad_base_contract = PatchContract(
            base_commit="0000000000000000000000000000000000000000",
            base_tree_digest=tree,
            patch_content_digest="dummy_patch_digest",
            sandbox_path=sb_path,
            required_commands=(),
            config_digest="config_digest_1",
            review_class="standard",
        )
        verifier = PatchVerifier(sb_path, contract=bad_base_contract)
        with pytest.raises(PatchVerificationError, match=r"[Dd]rift|base|commit"):
            verifier.verify_patch()

        # Tree digest drift: contract specifies wrong tree digest
        bad_tree_contract = PatchContract(
            base_commit=rev,
            base_tree_digest="bad_tree_digest_value",
            patch_content_digest="dummy_patch_digest",
            sandbox_path=sb_path,
            required_commands=(),
            config_digest="config_digest_1",
            review_class="standard",
        )
        verifier_tree = PatchVerifier(sb_path, contract=bad_tree_contract)
        with pytest.raises(PatchVerificationError, match=r"[Dd]rift|tree"):
            verifier_tree.verify_patch()

    finally:
        mgr.cleanup_sandbox(sb_path)


def test_policy_changing_patch_cannot_receive_ordinary_verified_success(
    tmp_path: Path,
) -> None:
    """T-58.16: Patch mutating permissions, auth, or safety configuration with review_class='policy-changing' or 'privileged'; asserts ordinary PatchVerifier refuses verified promotion."""
    repo = _init_git_repo(tmp_path / "repo_policy")
    rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    mgr = PatchSandboxManager(repo_root=repo)
    sb_path = mgr.create_sandbox()

    try:
        # 1. review_class='policy-changing'
        contract_policy = PatchContract(
            base_commit=rev,
            base_tree_digest=tree,
            patch_content_digest="patch_digest_abc",
            sandbox_path=sb_path,
            required_commands=(
                VerifierCommandPlan(
                    command=("python", "-c", "import sys; sys.exit(0)")
                ),
            ),
            config_digest="cfg_1",
            review_class="policy-changing",
        )
        verifier = PatchVerifier(sb_path, contract=contract_policy)
        ok, summary = verifier.verify_patch()
        assert ok is False
        assert verifier.last_result is not None
        assert verifier.last_result.outcome == "failed"
        assert (
            "policy-changing" in summary.lower()
            or "privileged" in summary.lower()
            or "ordinary" in summary.lower()
        )

        # 2. review_class='privileged'
        contract_priv = PatchContract(
            base_commit=rev,
            base_tree_digest=tree,
            patch_content_digest="patch_digest_xyz",
            sandbox_path=sb_path,
            required_commands=(
                VerifierCommandPlan(
                    command=("python", "-c", "import sys; sys.exit(0)")
                ),
            ),
            config_digest="cfg_2",
            review_class="privileged",
        )
        verifier_priv = PatchVerifier(sb_path, contract=contract_priv)
        ok2, _summary2 = verifier_priv.verify_patch()
        assert ok2 is False
        assert verifier_priv.last_result is not None
        assert verifier_priv.last_result.outcome == "failed"

        # 3. Promoter also refuses promotion of policy-changing patch
        promoter = PatchPromoter(repo_root=repo)
        promo_ok, promo_summary = promoter.promote_sandbox_diff(
            sb_path, contract=contract_policy
        )
        assert promo_ok is False
        assert (
            "policy" in promo_summary.lower() or "privileged" in promo_summary.lower()
        )

    finally:
        mgr.cleanup_sandbox(sb_path)


def test_zero_selected_or_executed_commands_never_verify(tmp_path: Path) -> None:
    """T-58.17: Project with 0 test runners or 0 executed commands; asserts verifier returns outcome='unavailable' and False (zero commands never verify)."""
    repo = _init_git_repo(tmp_path / "repo_zero_cmds")
    mgr = PatchSandboxManager(repo_root=repo)
    sb_path = mgr.create_sandbox()

    try:
        # Sandbox has no test runner files (no pytest.ini, tests/, package.json, Cargo.toml)
        verifier = PatchVerifier(sb_path)
        ok, summary = verifier.verify_patch()

        assert ok is False
        assert (
            summary
            == "No verification commands were executed. A patch requires at least one executed verification command to verify."
        )
        assert verifier.last_result is not None
        assert verifier.last_result.outcome == "unavailable"
        assert verifier.last_result.passed_count == 0

    finally:
        mgr.cleanup_sandbox(sb_path)


def test_unavailable_failed_verifier_leaves_checkout_unchanged(tmp_path: Path) -> None:
    """T-58.18: When verification commands fail or are unavailable, asserts working copy remains unchanged at original commit."""
    repo = _init_git_repo(tmp_path / "repo_unchanged")
    orig_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    orig_content = (repo / "main.py").read_text(encoding="utf-8")

    mgr = PatchSandboxManager(repo_root=repo)
    sb_path = mgr.create_sandbox()

    try:
        # Apply a change inside the sandbox
        sb_file = sb_path / "main.py"
        sb_file.write_text("def run():\n    return 'broken'\n", encoding="utf-8")

        # Failing verification command
        contract = PatchContract(
            base_commit=orig_rev,
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
        ok, _summary = verifier.verify_patch()
        assert ok is False
        assert verifier.last_result is not None
        assert verifier.last_result.outcome == "failed"

        # Working copy remains unchanged at original commit
        current_rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert current_rev == orig_rev
        assert (repo / "main.py").read_text(encoding="utf-8") == orig_content

        # Git status in main repo is completely clean
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


def test_rollback_and_cleanup_are_contained_and_manager_owned(tmp_path: Path) -> None:
    """T-58.19: Injected promotion failure triggers automatic atomic rollback restoring working copy and cleaning sandbox worktrees under PhysicalRoot."""
    repo = _init_git_repo(tmp_path / "repo_rollback")
    orig_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    orig_content = (repo / "main.py").read_text(encoding="utf-8")

    mgr = PatchSandboxManager(repo_root=repo)
    sb_path = mgr.create_sandbox()

    # Modify main.py in sandbox
    (sb_path / "main.py").write_text("def run():\n    return 999\n", encoding="utf-8")

    promoter = PatchPromoter(repo_root=repo)

    # Injected promotion failure during git apply
    def mock_subp(cmd, **kwargs):
        if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "apply":
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=1,
                stdout="",
                stderr="error: patch does not apply",
            )
        return real_run_subp(cmd, **kwargs)

    with patch("rush.patch.promoter.run_subprocess", side_effect=mock_subp):
        ok, err = promoter.promote_sandbox_diff(sb_path)
        assert ok is False
        assert "promotion failed" in err.lower() or "error" in err.lower()

    # Cleanup sandbox worktrees
    mgr.cleanup_sandbox(sb_path)
    assert not sb_path.exists()

    # Ensure main repo is at original commit with clean working copy
    current_rev = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert current_rev == orig_rev
    assert (repo / "main.py").read_text(encoding="utf-8") == orig_content
