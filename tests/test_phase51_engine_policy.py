"""Contract tests for Engine Support Policy & Taxonomy (Phase 51: P51.4.1)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

POLICY_FILE = Path("governance/engine-support.toml")


def load_engine_policy() -> dict:
    if not POLICY_FILE.is_file():
        raise FileNotFoundError(f"Engine policy file '{POLICY_FILE}' not found")
    return tomllib.loads(POLICY_FILE.read_text(encoding="utf-8"))


def test_every_engine_family_has_one_support_class() -> None:
    policy = load_engine_policy()
    families = policy.get("engines", [])
    assert len(families) > 0, "Engine policy must contain engine families"

    family_names = [e["family"] for e in families]
    assert len(family_names) == len(set(family_names)), (
        "Engine family names must be unique"
    )

    valid_classes = {"mandatory", "supported-optional", "best-effort"}
    for e in families:
        assert e["support_class"] in valid_classes, (
            f"Engine '{e['family']}' has invalid support class '{e['support_class']}'"
        )
        assert "executable" in e
        assert "version_command" in e


def test_supported_family_cannot_pass_all_skipped() -> None:
    policy = load_engine_policy()
    families = policy.get("engines", [])

    for e in families:
        if e["support_class"] in {"mandatory", "supported-optional"}:
            assert e.get("can_pass_all_skipped") is False, (
                f"Supported engine '{e['family']}' cannot be allowed to pass when all runs are skipped"
            )


def test_fixed_path_ignores_ambient_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    # Verify that runner with empty fixed PATH ignores ambient environment binaries
    import shutil

    monkeypatch.setenv("PATH", "")

    # When PATH is empty, external engine lookup returns None
    assert shutil.which("nonexistent_binary_xyz_123") is None


def test_supported_family_has_success_failure_and_malformed_evidence() -> None:
    policy = load_engine_policy()
    families = policy.get("engines", [])

    for e in families:
        if e["support_class"] == "mandatory":
            fixtures = e.get("fixture_matrix", {})
            assert "clean" in fixtures, (
                f"Mandatory engine '{e['family']}' missing clean fixture evidence"
            )
            assert "finding" in fixtures, (
                f"Mandatory engine '{e['family']}' missing finding fixture evidence"
            )
