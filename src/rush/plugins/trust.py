"""Repository Trust Ledger (Control 6: Repository Trust Gating).

Architecture §8, Phase 28.
Prevents Remote Code Execution (RCE) via untrusted plugins in cloned repositories.
"""

from __future__ import annotations

import json
from pathlib import Path

from rush.logging import get_logger, log_subsystem

logger = get_logger("plugins.trust")

DEFAULT_TRUST_LEDGER_PATH = Path.home() / ".rush" / "trusted_repositories.json"


def get_trust_ledger_path() -> Path:
    return DEFAULT_TRUST_LEDGER_PATH


def is_repo_trusted(repo_root: Path, ledger_file: Path | None = None) -> bool:
    """Check if repository directory has been explicitly approved in the local trust ledger."""
    ledger_path = ledger_file or get_trust_ledger_path()
    if not ledger_path.is_file():
        return False
    try:
        data = json.loads(ledger_path.read_text(encoding="utf-8"))
        trusted_paths = data.get("trusted_paths", [])
        return str(repo_root.resolve()) in trusted_paths
    except Exception as exc:  # noqa: BLE001
        log_subsystem("trust", "ERROR", f"Failed to read trust ledger: {exc}")
        return False


def trust_repo(repo_root: Path, ledger_file: Path | None = None) -> None:
    """Add repository directory to local trust ledger."""
    ledger_path = ledger_file or get_trust_ledger_path()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    trusted: list[str] = []
    if ledger_path.is_file():
        try:
            trusted = json.loads(ledger_path.read_text(encoding="utf-8")).get(
                "trusted_paths", []
            )
        except Exception:  # noqa: BLE001
            trusted = []

    resolved = str(repo_root.resolve())
    if resolved not in trusted:
        trusted.append(resolved)

    ledger_path.write_text(
        json.dumps({"trusted_paths": trusted}, indent=2), encoding="utf-8"
    )
    log_subsystem("trust", "INFO", f"Repository marked as trusted: {resolved}")


def revoke_trust(repo_root: Path, ledger_file: Path | None = None) -> None:
    """Remove repository directory from local trust ledger."""
    ledger_path = ledger_file or get_trust_ledger_path()
    if not ledger_path.is_file():
        return
    try:
        trusted: list[str] = json.loads(ledger_path.read_text(encoding="utf-8")).get(
            "trusted_paths", []
        )
        resolved = str(repo_root.resolve())
        if resolved in trusted:
            trusted.remove(resolved)
            ledger_path.write_text(
                json.dumps({"trusted_paths": trusted}, indent=2), encoding="utf-8"
            )
            log_subsystem("trust", "INFO", f"Trust revoked for repository: {resolved}")
    except Exception as exc:  # noqa: BLE001
        log_subsystem("trust", "ERROR", f"Failed to update trust ledger: {exc}")
