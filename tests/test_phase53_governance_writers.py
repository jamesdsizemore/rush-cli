"""Contract tests for Phase 53: Governance/Config/Mesh Writers (P53.3.1)."""

from __future__ import annotations

from pathlib import Path

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
