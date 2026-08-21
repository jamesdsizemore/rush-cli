"""Tests for Phase 38: Agent Governance & Multi-IDE Scaffolding."""

from __future__ import annotations

from pathlib import Path

from rush.governance.audit_manifest import AuditManifestGenerator
from rush.governance.boundary_guard import WorkspaceBoundaryGuard
from rush.governance.mcp_configs import McpConfigGenerator
from rush.governance.parity_checker import RuleParityChecker
from rush.governance.scaffolder import RepoScaffolder
from rush.governance.subagent_guard import SubagentHierarchyValidator, SubagentInvocation
from rush.governance.synchronizer import AgentsMdSynchronizer


def test_agents_md_synchronizer(tmp_path: Path) -> None:
    agents_f = tmp_path / "AGENTS.md"
    agents_f.write_text("# Project Invariants\n- Run tests\n", encoding="utf-8")

    syncer = AgentsMdSynchronizer(tmp_path)
    results = syncer.sync_all()
    assert len(results) >= 5

    cursorrules = tmp_path / ".cursorrules"
    assert cursorrules.exists()
    assert "# Project Invariants" in cursorrules.read_text(encoding="utf-8")


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
