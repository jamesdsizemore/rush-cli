"""Tests for Phase 28: Repository Trust Gating (Control 6).

Verifies:
- Repository trust ledger checking and mutation
- Blocking plugin execution on untrusted repository directories by default
- Authorizing execution via trust_repo or --allow-untrusted-plugins
"""

from __future__ import annotations

from pathlib import Path

from rush.plugins.trust import (
    is_repo_trusted,
    revoke_trust,
    trust_repo,
)


def test_trust_ledger_lifecycle(tmp_path: Path) -> None:
    ledger_file = tmp_path / "trusted.json"
    repo_dir = tmp_path / "my-project"
    repo_dir.mkdir()

    # Initial state: Untrusted
    assert not is_repo_trusted(repo_dir, ledger_file=ledger_file)

    # Trust repo
    trust_repo(repo_dir, ledger_file=ledger_file)
    assert is_repo_trusted(repo_dir, ledger_file=ledger_file)

    # Revoke trust
    revoke_trust(repo_dir, ledger_file=ledger_file)
    assert not is_repo_trusted(repo_dir, ledger_file=ledger_file)


def test_plugin_trust_store_sha256(tmp_path: Path) -> None:
    from rush.plugins.trust_store import PluginTrustStore

    script = tmp_path / "custom_linter.py"
    script.write_text("print('hello')", encoding="utf-8")

    store = PluginTrustStore(tmp_path)
    assert store.is_trusted("custom_linter", script) is False

    rec = store.grant_trust("custom_linter", script)
    assert rec.name == "custom_linter"
    assert store.is_trusted("custom_linter", script) is True

    # Mutating script breaks trust
    script.write_text("print('tampered')", encoding="utf-8")
    assert store.is_trusted("custom_linter", script) is False


def test_sandboxed_environment() -> None:
    import os

    from rush.plugins.sandboxed_env import SandboxedEnvironment

    os.environ["OPENAI_API_KEY"] = "sk-secret-123"
    sanitized = SandboxedEnvironment.get_sanitized_env()
    assert "OPENAI_API_KEY" not in sanitized
    assert sanitized["PYTHONUNBUFFERED"] == "1"


def test_plugin_manifest_validator() -> None:
    from rush.plugins.manifest_schema import PluginManifestValidator

    valid_spec = {"command": "echo test", "timeout_seconds": 15.0, "patterns": ["*.py"]}
    res = PluginManifestValidator.validate_spec_dict("my_plugin", valid_spec)
    assert res.is_valid is True

    invalid_spec = {"command": "", "timeout_seconds": -5.0}
    res_bad = PluginManifestValidator.validate_spec_dict("123-bad", invalid_spec)
    assert res_bad.is_valid is False
    assert len(res_bad.errors) > 0


def test_agent_skill_generator(tmp_path: Path, monkeypatch) -> None:
    from rush.plugins.closure import build_plugin_closure
    from rush.plugins.loader import PluginSpec
    from rush.plugins.skills_generator import AgentSkillGenerator
    from rush.plugins.trust_store import PluginTrustStore

    monkeypatch.chdir(tmp_path)
    ledger_path = tmp_path / "ledger.json"
    monkeypatch.setenv("RUSH_PLUGIN_TRUST_LEDGER", str(ledger_path))

    # Closure-less PluginSpec: no closure identity, so trust can never be established —
    # the "rush plugin run" line is omitted (fail-closed).
    spec = PluginSpec(
        name="custom_scanner",
        command=["python", "scan.py"],
        executable_path=Path("scan.py"),
        description="Custom Security Scanner",
    )
    skill_md = AgentSkillGenerator.generate_skill_markdown(spec)
    assert "name: custom_scanner" in skill_md
    assert "rush plugin run custom_scanner" not in skill_md

    # PluginSpec with a real closure whose digest has been explicitly trust-granted:
    # the "rush plugin run" line is present.
    plugin_root = tmp_path / "trusted_plugin"
    plugin_root.mkdir()
    entrypoint = plugin_root / "scan.py"
    entrypoint.write_text("print('scan')", encoding="utf-8")

    closure = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entrypoint,
        config={"name": "trusted_scanner", "command": ["python", "scan.py"]},
        plugin_name="trusted_scanner",
    )
    PluginTrustStore(ledger_path=ledger_path).grant_trust(
        "trusted_scanner", closure.closure_digest
    )

    trusted_spec = PluginSpec(
        name="trusted_scanner",
        command=["python", "scan.py"],
        executable_path=entrypoint,
        description="Trusted Scanner",
        closure=closure,
    )
    trusted_skill_md = AgentSkillGenerator.generate_skill_markdown(trusted_spec)
    assert "rush plugin run trusted_scanner" in trusted_skill_md
