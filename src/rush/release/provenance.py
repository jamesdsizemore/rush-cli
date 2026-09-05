"""SHA-256 checksums manifest and build provenance generator."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


class ProvenanceError(Exception):
    """Base exception for provenance and attestation failures."""


class ArtifactProvenanceVerifier:
    """Computes deterministic SHA-256 checksum manifests and verifies release distribution artifacts."""

    @staticmethod
    def generate_checksums_manifest(dist_dir: Path) -> Path:
        if not dist_dir.exists():
            dist_dir.mkdir(parents=True, exist_ok=True)

        manifest_file = dist_dir / "checksums.sha256"
        lines = []

        for p in sorted(dist_dir.iterdir(), key=lambda x: x.name):
            if p.is_file() and p.name != "checksums.sha256":
                sha = hashlib.sha256()
                with open(p, "rb") as f:
                    while chunk := f.read(65536):
                        sha.update(chunk)
                lines.append(f"{sha.hexdigest()}  {p.name}")

        from rush.safety.redactor import sanitize_value

        manifest_text = "\n".join(lines) + ("\n" if lines else "")
        clean_manifest = sanitize_value(manifest_text).value
        manifest_file.write_text(clean_manifest, encoding="utf-8")
        return manifest_file

    @staticmethod
    def verify(
        statement: dict[str, Any],
        signature: str | bytes | None = None,
        *,
        raise_on_error: bool = True,
    ) -> bool:
        """Verifies cryptographic signature for a provenance statement.

        Fails closed on unsigned draft statements.
        """
        if not signature:
            if raise_on_error:
                raise ProvenanceError(
                    "Cannot verify unsigned provenance statement without cryptographic signature"
                )
            return False
        return False


__all__ = ["ArtifactProvenanceVerifier", "ProvenanceError"]
