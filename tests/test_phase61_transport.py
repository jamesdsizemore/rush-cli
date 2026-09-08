"""Contract tests T-61.28 through T-61.31 for the Cross-Tool Transport Dispatcher
(Phase 61 §9 P61.10). Wholly new code — never exercises
`rush.continuity.providers.provider_command()`/`resume_provider()`, which is session-resume
CLI dispatch, a separate concern (§2.1 Drift 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.memory import transport
from rush.permissions import ExecutionPermissions


def test_native_sdk_tier_selected_when_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.28: native SDK importable for a tool -> dispatcher picks tier 1, not ACP or the
    dedicated-file fallback."""
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: True)
    monkeypatch.setattr(transport, "_acp_available", lambda tool: True)

    result = transport.dispatch(tmp_path, "claude_code", "codex_cli", "handoff content")

    assert result.tier == "native_sdk"
    assert result.status == "ok"
    assert not (tmp_path / transport.HANDOFF_FILE).exists()


def test_acp_tier_selected_when_no_native_sdk_but_acp_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.29: no native SDK but ACP support available -> tier 2 selected."""
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: False)
    monkeypatch.setattr(transport, "_acp_available", lambda tool: True)

    result = transport.dispatch(tmp_path, "codex_cli", "claude_code", "handoff content")

    assert result.tier == "acp"
    assert result.status == "ok"
    assert not (tmp_path / transport.HANDOFF_FILE).exists()


def test_dedicated_file_fallback_when_neither_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.30: neither native SDK nor ACP available -> tier 3 dedicated-file fallback to
    `.rush/memory/cross_tool_handoff.md`, gated behind `ExecutionPermissions(artifact_write=True)`
    — never `AGENTS.md`/`CLAUDE.md`. Also covers dedupe on `(source, content_hash)` and the
    explicit (non-automatic) cleanup function."""
    monkeypatch.setattr(transport, "_native_sdk_available", lambda tool: False)
    monkeypatch.setattr(transport, "_acp_available", lambda tool: False)

    denied = transport.dispatch(
        tmp_path, "antigravity_cli", "claude_code", "fact: x uses WAL"
    )
    assert denied.tier == "dedicated_file"
    assert denied.status == "skipped"
    assert not (tmp_path / transport.HANDOFF_FILE).exists()

    granted_result = transport.dispatch(
        tmp_path,
        "antigravity_cli",
        "claude_code",
        "fact: x uses WAL",
        granted=ExecutionPermissions(artifact_write=True),
    )
    assert granted_result.tier == "dedicated_file"
    assert granted_result.status == "ok"

    handoff_path = tmp_path / transport.HANDOFF_FILE
    assert handoff_path.exists()
    assert not (tmp_path / "AGENTS.md").exists()
    assert not (tmp_path / "CLAUDE.md").exists()

    before = handoff_path.read_text(encoding="utf-8")
    duplicate_result = transport.dispatch(
        tmp_path,
        "antigravity_cli",
        "claude_code",
        "fact: x uses WAL",
        granted=ExecutionPermissions(artifact_write=True),
    )
    assert duplicate_result.status == "ok"
    assert "Duplicate" in duplicate_result.detail
    assert handoff_path.read_text(encoding="utf-8") == before

    removed = transport.cleanup_handoff_file(tmp_path, max_blocks=0)
    assert removed == 1
    assert "content_hash=" not in handoff_path.read_text(encoding="utf-8")


def test_dispatcher_is_per_tool_not_global(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """T-61.31: two tools with different tier availability in the same run each get their own
    tier independently, not one global tier for the whole session."""
    native_sdk_tools = {"claude_code"}
    acp_tools = {"codex_cli"}
    monkeypatch.setattr(
        transport, "_native_sdk_available", lambda tool: tool in native_sdk_tools
    )
    monkeypatch.setattr(transport, "_acp_available", lambda tool: tool in acp_tools)

    result_a = transport.dispatch(
        tmp_path, "claude_code", "antigravity_cli", "content a"
    )
    result_b = transport.dispatch(tmp_path, "codex_cli", "antigravity_cli", "content b")
    result_c = transport.dispatch(
        tmp_path, "antigravity_cli", "claude_code", "content c"
    )

    assert result_a.tier == "native_sdk"
    assert result_b.tier == "acp"
    assert result_c.tier == "dedicated_file"
