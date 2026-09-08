"""Contract test for Phase 61 P61.8 — Skill/Pattern Family (T-61.27)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.plugins.loader import PluginSpec
from rush.plugins.skills_generator import AgentSkillGenerator


def test_skill_candidate_requires_trust_store_grant_before_execution_path_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mined skill candidate with no `PluginTrustStore.grant_trust()` call has no
    working `rush plugin run` path in its generated SKILL.md until trust is explicitly
    granted."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RUSH_PLUGIN_TRUST_LEDGER", str(tmp_path / "ledger.json"))

    spec = PluginSpec(
        name="mined_candidate",
        command=["python", "mined.py"],
        executable_path=tmp_path / "mined.py",
        description="Mined skill candidate",
    )

    skill_md = AgentSkillGenerator.generate_skill_markdown(spec)

    assert "rush plugin run" not in skill_md
