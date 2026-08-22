"""SHA-256 governance provenance manifest generator."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from rush.governance.synchronizer import IDE_TARGETS


class AuditManifestGenerator:
    """Generates signed provenance manifests certifying repository governance state."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def generate_manifest(self) -> dict:
        agents_f = self.repo_root / "AGENTS.md"
        agents_sha = ""
        if agents_f.exists():
            agents_sha = hashlib.sha256(agents_f.read_bytes()).hexdigest()

        targets_sha = {}
        for rel_p in IDE_TARGETS:
            f = self.repo_root / rel_p
            if f.exists():
                targets_sha[rel_p] = hashlib.sha256(f.read_bytes()).hexdigest()

        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "canonical_agents_md_sha256": agents_sha,
            "synchronized_targets": targets_sha,
            "status": "VALID" if agents_sha else "MISSING_CANONICAL",
        }
