"""Phase 56 Workstream P56.1: User-Owned Trust Ledger & Reapproval Lifecycle Contract Tests.

Contract Test Ledger:
- T-56.01: test_plugin_execution_fails_closed_without_content_digest
- T-56.02: test_repository_receipt_never_authorizes
- T-56.03: test_cloned_repository_receipt_is_denied
- T-56.04: test_legacy_grant_requires_explicit_reapproval
- T-56.05: test_revoke_invalidates_launch
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from rush.plugins import (
    PluginTrustError,
    PluginTrustStore,
    TrustedPluginRecord,
    UntrustedPluginError,
)


def test_plugin_execution_fails_closed_without_content_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.01: Plugin execution fails closed when unhashed or unregistered in user ledger; child count == 0."""
    assert issubclass(UntrustedPluginError, PluginTrustError)
    user_ledger = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    store = PluginTrustStore(ledger_path=user_ledger)

    # Track any attempted child process spawns
    child_spawns: list[tuple[tuple, dict]] = []

    def forbidden_popen(*args, **kwargs):
        child_spawns.append((args, kwargs))
        raise AssertionError("Child process spawned for untrusted plugin!")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    # Case 1: Unregistered plugin
    dummy_digest = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
    assert store.is_trusted("unregistered_plugin", dummy_digest) is False

    with pytest.raises(UntrustedPluginError) as exc_unreg:
        store.assert_authorized("unregistered_plugin", dummy_digest)
    assert exc_unreg.value.code in ("UNTRUSTED_PLUGIN", "CLOSURE_UNREGISTERED")

    # Case 2: Unhashed / empty digest
    with pytest.raises(UntrustedPluginError) as exc_unhash:
        store.assert_authorized("unregistered_plugin", "")
    assert exc_unhash.value.code in ("UNHASHED_PLUGIN", "UNTRUSTED_PLUGIN")

    # Non-permissive assertion: strictly zero child processes created
    assert len(child_spawns) == 0


def test_repository_receipt_never_authorizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.02: Injects pre-existing .rush/trust.json in repo; asserts is_trusted() returns False until user explicitly runs grant; child count == 0."""
    repo_dir = tmp_path / "target_repo"
    repo_rush = repo_dir / ".rush"
    repo_rush.mkdir(parents=True)

    closure_digest = "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    repo_receipt = repo_rush / "trust.json"
    repo_receipt.write_text(
        json.dumps(
            {
                "injected_plugin": {
                    "closure_digest": closure_digest,
                    "snapshot_path": "/malicious/snapshot",
                    "granted_at": "2026-01-01T00:00:00Z",
                    "granted_by": "attacker",
                }
            }
        ),
        encoding="utf-8",
    )

    user_ledger = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    store = PluginTrustStore(repo_root=repo_dir, ledger_path=user_ledger)

    child_spawns: list[tuple[tuple, dict]] = []

    def forbidden_popen(*args, **kwargs):
        child_spawns.append((args, kwargs))
        raise AssertionError("Child process spawned from repository receipt!")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    # Repository receipt MUST NOT authorize the plugin
    assert store.is_trusted("injected_plugin", closure_digest) is False

    with pytest.raises(UntrustedPluginError):
        store.assert_authorized("injected_plugin", closure_digest)

    assert len(child_spawns) == 0

    # User explicitly grants trust in their own ledger
    snapshot_dir = tmp_path / "snapshots" / closure_digest
    snapshot_dir.mkdir(parents=True)
    rec = store.grant_trust("injected_plugin", closure_digest, snapshot_dir)
    assert rec.name == "injected_plugin"
    assert rec.closure_digest == closure_digest

    # Now, and only now, does is_trusted return True
    assert store.is_trusted("injected_plugin", closure_digest) is True
    store.assert_authorized("injected_plugin", closure_digest)
    assert len(child_spawns) == 0


def test_cloned_repository_receipt_is_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.03: Simulates cloned repo with foreign receipt; asserts authorization fails closed with code RECEIPT_NOT_AUTHORIZING."""
    cloned_repo = tmp_path / "cloned_repo"
    (cloned_repo / ".rush").mkdir(parents=True)

    fake_digest = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    (cloned_repo / ".rush" / "trust.json").write_text(
        json.dumps(
            {
                "trojan_plugin": {
                    "closure_digest": fake_digest,
                    "snapshot_path": "snapshots/trojan",
                    "granted_at": "2026-09-01T12:00:00Z",
                    "granted_by": "untrusted_upstream",
                }
            }
        ),
        encoding="utf-8",
    )

    user_ledger = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    store = PluginTrustStore(repo_root=cloned_repo, ledger_path=user_ledger)

    child_spawns: list[tuple[tuple, dict]] = []

    def forbidden_popen(*args, **kwargs):
        child_spawns.append((args, kwargs))
        raise AssertionError("Child process spawned for cloned repo receipt!")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    # Authorization must fail closed with exact code RECEIPT_NOT_AUTHORIZING
    with pytest.raises(UntrustedPluginError) as exc_info:
        store.assert_authorized("trojan_plugin", fake_digest)

    assert exc_info.value.code == "RECEIPT_NOT_AUTHORIZING"
    assert (
        "non-authorizing" in str(exc_info.value).lower()
        or "receipt" in str(exc_info.value).lower()
    )
    assert len(child_spawns) == 0


def test_legacy_grant_requires_explicit_reapproval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.04: Migrates older Phase 28 path grant; asserts plugin cannot run without explicit reapproval with complete closure digest."""
    from rush.plugins.trust import is_repo_trusted, trust_repo

    repo_dir = tmp_path / "legacy_repo"
    repo_dir.mkdir(parents=True)

    legacy_ledger = tmp_path / "trusted_repositories.json"
    trust_repo(repo_dir, ledger_file=legacy_ledger)
    assert is_repo_trusted(repo_dir, ledger_file=legacy_ledger) is True

    # User ledger for Phase 56 plugins
    user_ledger = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    store = PluginTrustStore(repo_root=repo_dir, ledger_path=user_ledger)

    child_spawns: list[tuple[tuple, dict]] = []

    def forbidden_popen(*args, **kwargs):
        child_spawns.append((args, kwargs))
        raise AssertionError("Child process spawned via legacy path grant!")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    closure_digest = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"

    # Legacy path grant does NOT authorize plugin execution
    assert store.is_trusted("legacy_plugin", closure_digest) is False
    with pytest.raises(UntrustedPluginError):
        store.assert_authorized("legacy_plugin", closure_digest)

    assert len(child_spawns) == 0

    # User explicitly reapproves with complete closure digest
    snapshot_dir = tmp_path / "snapshots" / closure_digest
    snapshot_dir.mkdir(parents=True)
    rec = store.grant_trust("legacy_plugin", closure_digest, snapshot_dir)
    assert rec.name == "legacy_plugin"
    assert rec.closure_digest == closure_digest

    # Now authorized
    assert store.is_trusted("legacy_plugin", closure_digest) is True
    store.assert_authorized("legacy_plugin", closure_digest)
    assert len(child_spawns) == 0


def test_revoke_invalidates_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.05: Grants trust, asserts is_trusted() == True; revokes trust; asserts immediate subsequent check/launch fails closed."""
    user_ledger = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    store = PluginTrustStore(ledger_path=user_ledger)

    closure_digest = "99887766554433221100aabbccddeeff99887766554433221100aabbccddeeff"
    snapshot_dir = tmp_path / "snapshots" / closure_digest
    snapshot_dir.mkdir(parents=True)

    # 1. Grant trust
    rec = store.grant_trust("secure_plugin", closure_digest, snapshot_dir)
    assert isinstance(rec, TrustedPluginRecord)
    assert store.is_trusted("secure_plugin", closure_digest) is True
    store.assert_authorized("secure_plugin", closure_digest)

    # 2. Revoke trust
    revoked = store.revoke_trust("secure_plugin")
    assert revoked is True

    # 3. Subsequent check immediately fails closed
    assert store.is_trusted("secure_plugin", closure_digest) is False

    child_spawns: list[tuple[tuple, dict]] = []

    def forbidden_popen(*args, **kwargs):
        child_spawns.append((args, kwargs))
        raise AssertionError("Child process spawned for revoked plugin!")

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    with pytest.raises(UntrustedPluginError) as exc_info:
        store.assert_authorized("secure_plugin", closure_digest)
    assert exc_info.value.code in ("UNTRUSTED_PLUGIN", "CLOSURE_UNREGISTERED")

    assert len(child_spawns) == 0
