"""Governance test for Phase 58: R-016 Physical Containment and Atomic Rollback."""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.patch.applier import PatchApplier
from rush.patch.contracts import (
    DirtyWorkspaceError,
    PatchContract,
    PatchVerificationError,
    VerifierCommandPlan,
)
from rush.patch.promoter import PatchPromoter, sandbox_diff_digest
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.verifier import PatchVerifier
from rush.permissions import ExecutionPermissions


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


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _patch_contract(repo: Path, sandbox: Path) -> PatchContract:
    return PatchContract(
        base_commit=_git(repo, "rev-parse", "HEAD").strip(),
        base_tree_digest=_git(repo, "rev-parse", "HEAD^{tree}").strip(),
        patch_content_digest="test-patch",
        sandbox_path=sandbox,
        required_commands=(),
        config_digest="test-config",
    )


def test_worktree_creation_failure_errors_without_child_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    commands: list[tuple[str, ...]] = []

    def fail_worktree(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        del kwargs
        commands.append(tuple(command))
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(
                command, 0, stdout="source-head\n", stderr=""
            )
        if command[:3] == ["git", "worktree", "add"]:
            return subprocess.CompletedProcess(
                command, 1, stdout="", stderr="synthetic worktree failure"
            )
        pytest.fail(f"child command executed after failed worktree creation: {command}")

    monkeypatch.setattr("rush.patch.sandbox.run_subprocess", fail_worktree)

    with pytest.raises(PatchVerificationError, match="worktree"):
        PatchSandboxManager(repo).create_sandbox()

    assert [command[:3] for command in commands] == [
        ("git", "status", "--porcelain"),
        ("git", "rev-parse", "HEAD"),
        ("git", "worktree", "add"),
    ]
    assert list((repo / ".rush" / "worktrees").iterdir()) == []


def test_sandbox_requires_verified_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _create_git_repo(tmp_path / "repo")

    def false_success(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        cwd = kwargs.get("cwd")
        if command[:2] == ["git", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if command == ["git", "rev-parse", "HEAD"] and cwd == repo:
            return subprocess.CompletedProcess(
                command, 0, stdout="source-head\n", stderr=""
            )
        if command[:3] == ["git", "worktree", "add"]:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="not a checkout"
        )

    monkeypatch.setattr("rush.patch.sandbox.run_subprocess", false_success)

    with pytest.raises(PatchVerificationError, match="verified checkout"):
        PatchSandboxManager(repo).create_sandbox()


def test_sandbox_is_verified_checkout(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    manager = PatchSandboxManager(repo)
    sandbox = manager.create_sandbox()
    try:
        assert (
            Path(_git(sandbox, "rev-parse", "--show-toplevel").strip()).resolve()
            == sandbox
        )
        assert (
            _git(sandbox, "rev-parse", "HEAD").strip()
            == _git(repo, "rev-parse", "HEAD").strip()
        )
    finally:
        manager.cleanup_sandbox(sandbox)


def test_promotion_requires_artifact_write_grant(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    manager = PatchSandboxManager(repo)
    sandbox = manager.create_sandbox()
    try:
        (sandbox / "app.py").write_text(
            "def value():\n    return 2\n", encoding="utf-8"
        )

        ok, message = PatchPromoter(repo).promote_sandbox_diff(
            sandbox, contract=_patch_contract(repo, sandbox)
        )

        assert ok is False
        assert "artifact-write" in message
        assert (repo / "app.py").read_text(encoding="utf-8") == (
            "def value():\n    return 1\n"
        )
    finally:
        manager.cleanup_sandbox(sandbox)


def test_failed_promotion_preserves_unrelated_state_and_sibling_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    notes = repo / "notes.txt"
    notes.write_text("committed\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    _git(repo, "commit", "-m", "notes")
    manager = PatchSandboxManager(repo)
    sandbox = manager.create_sandbox()
    sibling = manager.create_sandbox()
    (sandbox / "app.py").write_text("def value():\n    return 2\n", encoding="utf-8")
    original_run = __import__(
        "rush.patch.promoter", fromlist=["run_subprocess"]
    ).run_subprocess

    def fail_apply(command: list[str], **kwargs: object) -> object:
        if command[:2] == ["git", "apply"]:
            notes.write_text("staged\n", encoding="utf-8")
            _git(repo, "add", "notes.txt")
            notes.write_text("staged and unstaged\n", encoding="utf-8")
            (repo / "sentinel.txt").write_text("untracked\n", encoding="utf-8")
            return subprocess.CompletedProcess(
                command, 1, stdout="", stderr="synthetic apply failure"
            )
        return original_run(command, **kwargs)

    monkeypatch.setattr("rush.patch.promoter.run_subprocess", fail_apply)
    try:
        ok, _ = PatchPromoter(repo).promote_sandbox_diff(
            sandbox,
            contract=_patch_contract(repo, sandbox),
            permissions=ExecutionPermissions(artifact_write=True),
        )

        assert ok is False
        assert notes.read_bytes() == b"staged and unstaged\n"
        assert _git(repo, "diff", "--cached", "--", "notes.txt")
        assert (repo / "sentinel.txt").read_bytes() == b"untracked\n"
        assert str(sibling) in _git(repo, "worktree", "list", "--porcelain")
        assert sibling.exists()
        assert (repo / "app.py").read_bytes() == b"def value():\n    return 1\n"
    finally:
        monkeypatch.setattr("rush.patch.promoter.run_subprocess", original_run)
        manager.cleanup_sandbox(sandbox)
        manager.cleanup_sandbox(sibling)


def test_failed_patch_restores_only_patch_targets(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    notes = repo / "notes.txt"
    notes.write_text("committed\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    _git(repo, "commit", "-m", "notes")
    notes.write_text("staged\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    notes.write_text("staged and unstaged\n", encoding="utf-8")
    sentinel = repo / "sentinel.txt"
    sentinel.write_text("untracked\n", encoding="utf-8")
    cached_before = _git(repo, "diff", "--cached")
    patch_text = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def value():
-    return 1
+    return (
"""

    ok, _ = PatchApplier.apply_patch_to_dir(repo, patch_text)

    assert ok is False
    assert (repo / "app.py").read_bytes() == b"def value():\n    return 1\n"
    assert notes.read_bytes() == b"staged and unstaged\n"
    assert _git(repo, "diff", "--cached") == cached_before
    assert sentinel.read_bytes() == b"untracked\n"


def test_promotion_preserves_preexisting_patch_file(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    existing = repo / ".promote.patch"
    existing.write_bytes(b"user-owned patch\n")
    existing.chmod(0o640)
    _git(repo, "add", ".promote.patch")
    _git(repo, "commit", "-m", "user patch")
    original_mode = stat.S_IMODE(existing.stat().st_mode)
    manager = PatchSandboxManager(repo)
    sandbox = manager.create_sandbox()
    try:
        (sandbox / "app.py").write_text(
            "def value():\n    return 2\n", encoding="utf-8"
        )

        ok, _ = PatchPromoter(repo).promote_sandbox_diff(
            sandbox,
            contract=_patch_contract(repo, sandbox),
            permissions=ExecutionPermissions(artifact_write=True),
        )

        assert ok is True
        assert existing.read_bytes() == b"user-owned patch\n"
        assert stat.S_IMODE(existing.stat().st_mode) == original_mode
    finally:
        manager.cleanup_sandbox(sandbox)


def test_failed_worktree_add_preserves_preexisting_allocated_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    allocated = repo / ".rush" / "worktrees" / "sandbox_deadbeef"
    allocated.mkdir(parents=True)
    sentinel = allocated / "owned-by-user.txt"
    sentinel.write_bytes(b"preserve\n")
    monkeypatch.setattr(
        "rush.patch.sandbox.uuid.uuid4", lambda: SimpleNamespace(hex="deadbeef00")
    )

    with pytest.raises(PatchVerificationError):
        PatchSandboxManager(repo).create_sandbox()

    assert sentinel.read_bytes() == b"preserve\n"


def test_patch_validator_exception_restores_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    original = (repo / "app.py").read_bytes()
    patch_text = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def value():
-    return 1
+    return 2
"""
    monkeypatch.setattr(
        "rush.patch.applier.PatchSyntaxGuard.validate_file_syntax",
        lambda _path: (_ for _ in ()).throw(OSError("synthetic validator failure")),
    )

    ok, _ = PatchApplier.apply_patch_to_dir(repo, patch_text)

    assert ok is False
    assert (repo / "app.py").read_bytes() == original


def test_failed_patch_recreates_deleted_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    target = repo / "app.py"
    original = target.read_bytes()
    patch_text = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def value():
-    return 1
+    return 2
"""

    def delete_then_fail(_patch: str, _root: Path) -> bool:
        target.unlink()
        return False

    monkeypatch.setattr("rush.patch.applier.apply_unified_patch", delete_then_fail)

    ok, _ = PatchApplier.apply_patch_to_dir(repo, patch_text)

    assert ok is False
    assert target.read_bytes() == original


def test_failed_patch_restores_target_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    target = repo / "app.py"
    target.chmod(0o640)
    patch_text = """--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 def value():
-    return 1
+    return 2
"""

    def change_mode_then_fail(_patch: str, _root: Path) -> bool:
        target.chmod(0o600)
        return False

    monkeypatch.setattr("rush.patch.applier.apply_unified_patch", change_mode_then_fail)

    ok, _ = PatchApplier.apply_patch_to_dir(repo, patch_text)

    assert ok is False
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_promotion_preserves_secret_shaped_source_bytes(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    secret_shaped = "sk-ant-abcdefghijklmnopqrstuvwxyz012345"
    manager = PatchSandboxManager(repo)
    sandbox = manager.create_sandbox()
    try:
        (sandbox / "app.py").write_text(
            f'def value():\n    return "{secret_shaped}"\n', encoding="utf-8"
        )

        ok, _ = PatchPromoter(repo).promote_sandbox_diff(
            sandbox,
            contract=_patch_contract(repo, sandbox),
            permissions=ExecutionPermissions(artifact_write=True),
        )

        assert ok is True
        assert (repo / "app.py").read_text(encoding="utf-8") == (
            f'def value():\n    return "{secret_shaped}"\n'
        )
    finally:
        manager.cleanup_sandbox(sandbox)


def test_sandbox_rejects_redirected_rush_before_write(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    outside = tmp_path / "outside-rush"
    outside.mkdir()
    rush_path = repo / ".rush"
    rush_path.symlink_to(outside, target_is_directory=True)
    _git(repo, "add", "-f", ".rush")
    _git(repo, "commit", "-m", "redirect rush")

    with pytest.raises(ContainmentError):
        PatchSandboxManager(repo).create_sandbox()

    assert list(outside.iterdir()) == []


def test_cleanup_all_preserves_sibling_manager_worktree(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    first_manager = PatchSandboxManager(repo)
    sibling_manager = PatchSandboxManager(repo)
    first = first_manager.create_sandbox()
    sibling = sibling_manager.create_sandbox()
    try:
        with pytest.raises(PatchVerificationError, match="invocation-owned"):
            first_manager.cleanup_sandbox(sibling)

        first_manager.cleanup_all()

        assert not first.exists()
        assert sibling.exists()
        assert str(sibling) in _git(repo, "worktree", "list", "--porcelain")
    finally:
        if first.exists():
            first_manager.cleanup_sandbox(first)
        sibling_manager.cleanup_sandbox(sibling)


def test_sandbox_diff_digest_uses_exact_unredacted_bytes(tmp_path: Path) -> None:
    repo = _create_git_repo(tmp_path / "repo")
    manager = PatchSandboxManager(repo)
    sandbox = manager.create_sandbox()
    try:
        first = "sk-ant-abcdefghijklmnopqrstuvwxyz012345"
        second = "sk-ant-abcdefghijklmnopqrstuvwxyz012346"
        (sandbox / "app.py").write_text(
            f'def value():\n    return "{first}"\n', encoding="utf-8"
        )
        first_digest = sandbox_diff_digest(sandbox, repo)
        (sandbox / "app.py").write_text(
            f'def value():\n    return "{second}"\n# changed long tail\n',
            encoding="utf-8",
        )
        second_digest = sandbox_diff_digest(sandbox, repo)

        assert len(first_digest) == 64
        assert len(second_digest) == 64
        assert first_digest != second_digest
    finally:
        manager.cleanup_sandbox(sandbox)


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
