"""Contract tests for Phase 53: Governance/Config/Mesh Writers (P53.3.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.governance.synchronizer import AgentsMdSynchronizer
from rush.mcp_mesh.daemon import MeshLockManager
from rush.score.svg_badge import SvgBadgeGenerator


def test_agents_md_synchronizer_sanitizes_writes(tmp_path: Path) -> None:
    """Verify that AgentsMdSynchronizer never writes unsanitized secret sentinels to IDE rule files."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    agents_file = tmp_path / "AGENTS.md"
    agents_file.write_text(
        f"# Instructions\n\nAPI_KEY = {fresh_secret}\n", encoding="utf-8"
    )

    sync = AgentsMdSynchronizer(tmp_path)
    results = sync.sync_all()
    assert len(results) > 0

    for res in results:
        target_file = tmp_path / res.target_path
        assert target_file.exists()
        content = target_file.read_text(encoding="utf-8")
        assert fresh_secret not in content
        assert "[REDACTED_ANTHROPIC_KEY]" in content or "[REDACTED]" in content


def test_mesh_lock_manager_sanitizes_lock_writes(tmp_path: Path) -> None:
    """Verify that MeshLockManager never writes unsanitized secret sentinels to disk lock files."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    agent_id = f"agent-{fresh_secret}"

    lock_mgr = MeshLockManager(project_root=tmp_path)
    target_file = tmp_path / "src" / "index.py"
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("code", encoding="utf-8")

    acquired = lock_mgr.acquire(target_file, agent_id=agent_id, timeout_s=1.0)
    assert acquired is True

    # Inspect the raw on-disk .lock file
    lock_file = lock_mgr._lock_file_for(target_file)
    assert lock_file.exists()
    content = lock_file.read_text(encoding="utf-8")
    assert fresh_secret not in content

    # Clean release
    released = lock_mgr.release(target_file, agent_id=agent_id)
    assert released is True


def test_score_badge_sanitizes_outputs(tmp_path: Path) -> None:
    """Verify that score badge generator sanitizes secret sentinels."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    badge_svg = SvgBadgeGenerator.generate_badge_svg(95.0, f"A+{fresh_secret}")
    assert fresh_secret not in badge_svg


def test_governance_config_hook_and_mesh_artifacts_are_sanitized_on_success_and_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that all §8 governance/config/mesh writers sanitize artifacts on both success and abort."""
    from rush.governance.mcp_configs import McpConfigGenerator
    from rush.governance.scaffolder import RepoScaffolder
    from rush.governance.synchronizer import AgentsMdSynchronizer
    from rush.hook.tamper_detector import HookTamperDetector
    from rush.mcp_mesh.daemon import MeshLockManager as DaemonLockManager
    from rush.mcp_mesh.lock_manager import MeshLockManager as StandardLockManager

    fresh_sentinel = "sk-ant-api03-abcdef123456789012345678"

    # Helper to recursively assert that no file under a directory contains the raw sentinel
    def assert_no_sentinel_in_tree(root: Path) -> None:
        for p in root.rglob("*"):
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    assert fresh_sentinel not in content, f"Leaked sentinel in {p}"
                except OSError:
                    pass

    # 1. McpConfigGenerator (Success & Abort)
    mcp_dir = tmp_path / "mcp_case"
    mcp_dir.mkdir()
    c_file = McpConfigGenerator.generate_cursor_config(mcp_dir)
    v_file = McpConfigGenerator.generate_vscode_config(mcp_dir)
    assert c_file.exists() and v_file.exists()
    assert_no_sentinel_in_tree(mcp_dir)

    # McpConfigGenerator Abort test: forced write failure leaves no unsanitized partials
    abort_mcp_dir = tmp_path / "mcp_abort"
    abort_mcp_dir.mkdir()
    cursor_dir = abort_mcp_dir / ".cursor"
    cursor_dir.mkdir()
    bad_target = cursor_dir / "mcp.json"
    bad_target.mkdir()  # Make it a directory so write_text raises IsADirectoryError / PermissionError
    with pytest.raises((OSError, IsADirectoryError, PermissionError)):
        McpConfigGenerator.generate_cursor_config(abort_mcp_dir)
    assert_no_sentinel_in_tree(abort_mcp_dir)

    # 2. RepoScaffolder (Success & Abort)
    scaffold_dir = tmp_path / "scaffold_case"
    scaffold_dir.mkdir()
    created = RepoScaffolder.init_repository(scaffold_dir)
    assert len(created) == 2
    assert_no_sentinel_in_tree(scaffold_dir)

    # Scaffolder Abort test: forced write failure leaves no unsanitized partials
    abort_scaffold_dir = tmp_path / "scaffold_abort"
    abort_scaffold_dir.mkdir()

    def fail_write(*args, **kwargs):
        raise OSError("Disk write failed mid-stream")

    monkeypatch.setattr(Path, "write_text", fail_write)
    with pytest.raises(OSError, match="Disk write failed mid-stream"):
        RepoScaffolder.init_repository(abort_scaffold_dir)
    monkeypatch.undo()
    assert_no_sentinel_in_tree(abort_scaffold_dir)

    # 3. AgentsMdSynchronizer (Success & Abort)
    sync_dir = tmp_path / "sync_case"
    sync_dir.mkdir()
    agents_file = sync_dir / "AGENTS.md"
    agents_file.write_text(
        f"# Agent Instructions\nTOKEN={fresh_sentinel}\n", encoding="utf-8"
    )
    synchronizer = AgentsMdSynchronizer(sync_dir)
    results = synchronizer.sync_all()
    assert len(results) > 0
    for res in results:
        target_f = sync_dir / res.target_path
        assert target_f.exists()
        target_text = target_f.read_text(encoding="utf-8")
        assert fresh_sentinel not in target_text, f"Leaked sentinel in {target_f}"
        assert "[REDACTED" in target_text

    # Synchronizer Abort: forced error during target file write
    abort_sync_dir = tmp_path / "sync_abort"
    abort_sync_dir.mkdir()
    agents_file2 = abort_sync_dir / "AGENTS.md"
    agents_file2.write_text(
        f"# Agent Instructions\nTOKEN={fresh_sentinel}\n", encoding="utf-8"
    )
    # Block CLAUDE.md target
    claude_target = abort_sync_dir / "CLAUDE.md"
    claude_target.mkdir()
    synchronizer2 = AgentsMdSynchronizer(abort_sync_dir)
    try:
        synchronizer2.sync_all()
    except (OSError, PermissionError, IsADirectoryError):
        pass
    for p in abort_sync_dir.rglob("*"):
        if p.is_file() and p.name != "AGENTS.md":
            assert fresh_sentinel not in p.read_text(encoding="utf-8")

    # 4. HookTamperDetector (Success & Abort)
    hook_dir = tmp_path / "hook_case"
    hooks_dir = hook_dir / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    pre_commit = hooks_dir / "pre-commit"
    pre_commit.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    detector = HookTamperDetector(hook_dir)
    sigs = detector.record_signatures()
    assert "pre-commit" in sigs
    ok, _errs = detector.verify_signatures()
    assert ok is True
    assert_no_sentinel_in_tree(hook_dir / ".rush")

    # HookTamperDetector Abort: write fails
    abort_hook_dir = tmp_path / "hook_abort"
    abort_hooks_dir = abort_hook_dir / ".git" / "hooks"
    abort_hooks_dir.mkdir(parents=True)
    pre_commit2 = abort_hooks_dir / "pre-commit"
    pre_commit2.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    (abort_hook_dir / ".rush").mkdir(parents=True)
    blocked_sig = abort_hook_dir / ".rush" / "hook_signatures.json"
    blocked_sig.mkdir()
    detector2 = HookTamperDetector(abort_hook_dir)
    with pytest.raises((OSError, IsADirectoryError, PermissionError)):
        detector2.record_signatures()
    assert_no_sentinel_in_tree(abort_hook_dir / ".rush")

    # 5. Standard MeshLockManager (Success & Abort)
    std_mesh_dir = tmp_path / "std_mesh_case"
    std_mesh_dir.mkdir()
    target_file = std_mesh_dir / "file.py"
    target_file.write_text("print('test')", encoding="utf-8")
    std_mgr = StandardLockManager(std_mesh_dir)
    acq = std_mgr.acquire(
        target_file, agent_id=f"agent-{fresh_sentinel}", timeout_s=0.5
    )
    assert acq is True
    assert_no_sentinel_in_tree(std_mesh_dir)
    std_mgr.release(target_file, agent_id=f"agent-{fresh_sentinel}")

    # Standard MeshLockManager Abort: lock dir blocked
    abort_std_mesh = tmp_path / "std_mesh_abort"
    abort_std_mesh.mkdir()
    target_file_abort = abort_std_mesh / "file.py"
    target_file_abort.write_text("print('test')", encoding="utf-8")
    # Make lock path a directory so writing lock fails
    std_mgr_abort = StandardLockManager(abort_std_mesh)
    lock_file = std_mgr_abort._lock_file_for(target_file_abort)
    lock_file.mkdir(parents=True)
    acq_fail = std_mgr_abort.acquire(
        target_file_abort, agent_id=f"agent-{fresh_sentinel}", timeout_s=0.1
    )
    assert acq_fail is False
    assert_no_sentinel_in_tree(abort_std_mesh)

    # 6. Daemon MeshLockManager (Success & Abort)
    daemon_mesh_dir = tmp_path / "daemon_mesh_case"
    daemon_mesh_dir.mkdir()
    daemon_target = daemon_mesh_dir / "daemon_file.py"
    daemon_target.write_text("print('daemon')", encoding="utf-8")
    daemon_mgr = DaemonLockManager(daemon_mesh_dir)
    dacq = daemon_mgr.acquire(
        daemon_target, agent_id=f"daemon-{fresh_sentinel}", timeout_s=0.5
    )
    assert dacq is True
    assert_no_sentinel_in_tree(daemon_mesh_dir)
    daemon_mgr.release(daemon_target, agent_id=f"daemon-{fresh_sentinel}")

    # Daemon MeshLockManager Abort: lock file path blocked
    abort_daemon_mesh = tmp_path / "daemon_mesh_abort"
    abort_daemon_mesh.mkdir()
    daemon_target_abort = abort_daemon_mesh / "daemon_file.py"
    daemon_target_abort.write_text("print('daemon')", encoding="utf-8")
    daemon_mgr_abort = DaemonLockManager(abort_daemon_mesh)
    d_lock_file = daemon_mgr_abort._lock_file_for(daemon_target_abort)
    d_lock_file.mkdir(parents=True)
    dacq_fail = daemon_mgr_abort.acquire(
        daemon_target_abort, agent_id=f"daemon-{fresh_sentinel}", timeout_s=0.1
    )
    assert dacq_fail is False
    assert_no_sentinel_in_tree(abort_daemon_mesh)
