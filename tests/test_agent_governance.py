"""Tests for Phase 38: Agent Governance & Multi-IDE Scaffolding."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.governance.audit_manifest import AuditManifestGenerator
from rush.governance.boundary_guard import WorkspaceBoundaryGuard
from rush.governance.mcp_configs import McpConfigGenerator
from rush.governance.parity_checker import RuleParityChecker
from rush.governance.subagent_guard import (
    SubagentHierarchyValidator,
    SubagentInvocation,
)
from rush.governance.synchronizer import AgentsMdSynchronizer
from rush.io.atomic_file import AtomicFile
from rush.io.physical_paths import ContainmentError


def test_agents_md_synchronizer(tmp_path: Path) -> None:
    agents_f = tmp_path / "AGENTS.md"
    agents_f.write_text("# Project Invariants\n- Run tests\n", encoding="utf-8")

    syncer = AgentsMdSynchronizer(tmp_path)
    results = syncer.sync_all()
    assert len(results) >= 5

    cursorrules = tmp_path / ".cursorrules"
    assert cursorrules.exists()
    assert "# Project Invariants" in cursorrules.read_text(encoding="utf-8")


@pytest.mark.parametrize("escape_kind", ["file", "parent", "traversal"])
def test_sync_rejects_escape_before_any_write(
    tmp_path: Path, monkeypatch, escape_kind
) -> None:
    from rush.governance import synchronizer

    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# Rules", encoding="utf-8")
    first = root / ".cursorrules"
    first.write_bytes(b"original\xff")
    first.chmod(0o640)
    before_mode = first.stat().st_mode
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = "sk-ant-api03-abcdef123456789012345678"
    victim = outside / "rules.md"
    victim.write_text(secret, encoding="utf-8")
    if escape_kind == "file":
        (root / ".windsurfrules").symlink_to(victim)
        second = ".windsurfrules"
    elif escape_kind == "parent":
        (root / ".github").symlink_to(outside, target_is_directory=True)
        second = ".github/rules.md"
    else:
        second = "../outside/rules.md"
    monkeypatch.setattr(
        synchronizer, "IDE_TARGETS", {".cursorrules": "first", second: "second"}
    )

    with pytest.raises(ContainmentError) as failure:
        AgentsMdSynchronizer(root).sync_all()

    assert secret not in str(failure.value)
    assert first.read_bytes() == b"original\xff"
    assert first.stat().st_mode == before_mode
    assert victim.read_text(encoding="utf-8") == secret


@pytest.mark.parametrize("existing", [True, False])
@pytest.mark.parametrize("cancelled", [False, True])
def test_sync_second_write_failure_restores_first(
    tmp_path: Path, monkeypatch, existing, cancelled
) -> None:
    from rush.governance import synchronizer

    (tmp_path / "AGENTS.md").write_text("# New rules", encoding="utf-8")
    first = tmp_path / ".cursorrules"
    if existing:
        first.write_bytes(b"original\xff")
        first.chmod(0o640)
    original_mode = first.stat().st_mode if existing else None
    second = tmp_path / ".windsurfrules"
    second.write_bytes(b"second original")
    neighbor = tmp_path / "notes.txt"
    neighbor.write_bytes(b"unrelated")
    monkeypatch.setattr(
        synchronizer, "IDE_TARGETS", {first.name: "first", second.name: "second"}
    )
    original_write = AtomicFile.write_bytes
    original_text_write = Path.write_text
    secret = "sk-ant-api03-abcdef123456789012345678"

    def fail_second(writer, relative_path, content):
        if str(relative_path) == second.name:
            if cancelled:
                raise KeyboardInterrupt()
            raise OSError(secret)
        return original_write(writer, relative_path, content)

    def fail_legacy_second(path, *args, **kwargs):
        if path == second:
            if cancelled:
                raise KeyboardInterrupt()
            raise OSError(secret)
        return original_text_write(path, *args, **kwargs)

    monkeypatch.setattr(AtomicFile, "write_bytes", fail_second)
    monkeypatch.setattr(Path, "write_text", fail_legacy_second)
    with pytest.raises(KeyboardInterrupt if cancelled else OSError) as failure:
        AgentsMdSynchronizer(tmp_path).sync_all()

    if existing:
        assert first.read_bytes() == b"original\xff"
        assert first.stat().st_mode == original_mode
    else:
        assert not first.exists()
    assert second.read_bytes() == b"second original"
    assert neighbor.read_bytes() == b"unrelated"
    assert secret not in str(failure.value)


def test_sync_rejects_symlinked_canonical_file(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside.md"
    secret = "sk-ant-api03-abcdef123456789012345678"
    outside.write_text(secret, encoding="utf-8")
    (root / "AGENTS.md").symlink_to(outside)

    with pytest.raises(ContainmentError) as failure:
        AgentsMdSynchronizer(root).sync_all()

    assert secret not in str(failure.value)
    assert list(root.iterdir()) == [root / "AGENTS.md"]
    assert outside.read_text(encoding="utf-8") == secret


def test_mcp_config_generator(tmp_path: Path) -> None:
    cursor_json = McpConfigGenerator.generate_cursor_config(tmp_path)
    assert cursor_json.exists()
    assert "rush" in cursor_json.read_text(encoding="utf-8")


def test_workspace_boundary_guard(tmp_path: Path) -> None:
    guard = WorkspaceBoundaryGuard(tmp_path)
    assert guard.is_safe_path(tmp_path / "src" / "main.py")
    assert not guard.is_safe_path(tmp_path.parent / "escape.txt")


def test_subagent_hierarchy_validator() -> None:
    validator = SubagentHierarchyValidator(max_depth=3)
    valid_invocations = [
        SubagentInvocation("orchestrator", "worker1"),
        SubagentInvocation("orchestrator", "worker2"),
    ]
    ok, err = validator.validate_invocations(valid_invocations)
    assert ok is True

    cyclic_invocations = [
        SubagentInvocation("agentA", "agentB"),
        SubagentInvocation("agentB", "agentA"),
    ]
    ok, err = validator.validate_invocations(cyclic_invocations)
    assert ok is False
    assert "Cyclic" in (err or "")


def test_rule_parity_checker(tmp_path: Path) -> None:
    agents_f = tmp_path / "AGENTS.md"
    agents_f.write_text("# Test", encoding="utf-8")

    checker = RuleParityChecker(tmp_path)
    violations = checker.check_parity()
    assert len(violations) > 0  # missing targets before sync

    syncer = AgentsMdSynchronizer(tmp_path)
    syncer.sync_all()

    violations_after = checker.check_parity()
    assert len(violations_after) == 0


def test_audit_manifest_generator(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Test", encoding="utf-8")
    gen = AuditManifestGenerator(tmp_path)
    manifest = gen.generate_manifest()
    assert manifest["status"] == "VALID"
    assert len(manifest["canonical_agents_md_sha256"]) == 64
