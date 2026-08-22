"""Tests for Phase 31: Agent Safety & Worktree Sandboxing."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.safety.audit_logger import SecurityAuditLogger
from rush.safety.ephemeral_mount import EphemeralMountManager
from rush.safety.guard import AgentSafetyGuard
from rush.safety.interceptor import DangerousCommandInterceptor
from rush.safety.path_confiner import WorkspacePathConfiner
from rush.safety.redactor import SecretRedactor


def test_agent_safety_guard_protected_files(tmp_path: Path) -> None:
    guard = AgentSafetyGuard(tmp_path)
    assert guard.is_file_protected("AGENTS.md") is True
    assert guard.is_file_protected("rush.toml") is True
    assert guard.is_file_protected(".git/config") is True
    assert guard.is_file_protected("src/rush/main.py") is False

    with pytest.raises(PermissionError, match="immutable governance file"):
        guard.validate_write_target("AGENTS.md")


def test_dangerous_command_interceptor() -> None:
    safe, reason = DangerousCommandInterceptor.inspect_command(
        "git reset --hard HEAD~1"
    )
    assert safe is False
    assert "git reset --hard" in (reason or "")

    safe_rm, _reason_rm = DangerousCommandInterceptor.inspect_command("rm -rf /")
    assert safe_rm is False

    safe_good, _ = DangerousCommandInterceptor.inspect_command("pytest tests/")
    assert safe_good is True


def test_workspace_path_confiner(tmp_path: Path) -> None:
    confiner = WorkspacePathConfiner(tmp_path)
    safe_path = confiner.confine_path("src/app.py")
    assert safe_path.is_relative_to(tmp_path)

    with pytest.raises(PermissionError, match="Path traversal blocked"):
        confiner.confine_path("../../../etc/passwd")


def test_secret_redactor() -> None:
    raw = "My OpenAI key is sk-1234567890abcdef1234567890 and Anthropic sk-ant-api03-abcdef123456789012345678"
    redacted = SecretRedactor.redact_text(raw)
    assert "sk-1234567890abcdef1234567890" not in redacted
    assert "[REDACTED_OPENAI_KEY]" in redacted
    assert "[REDACTED_ANTHROPIC_KEY]" in redacted

    entropy = SecretRedactor.calculate_entropy("4b89cf12948e94a8c9120489")
    assert entropy > 2.0


def test_security_audit_logger(tmp_path: Path) -> None:
    logger = SecurityAuditLogger(tmp_path)
    hash1 = logger.log_security_event("COMMAND_BLOCKED", {"cmd": "git reset --hard"})
    assert len(hash1) == 64
    assert (tmp_path / ".rush" / "audit.log").exists()


def test_ephemeral_mount_manager() -> None:
    workspace = EphemeralMountManager.create_ephemeral_workspace()
    assert workspace.exists()
    assert "rush_ephemeral_" in workspace.name
