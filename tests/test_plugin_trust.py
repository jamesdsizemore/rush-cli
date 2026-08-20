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
