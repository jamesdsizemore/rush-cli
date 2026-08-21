"""SHA-256 checksums manifest and build provenance generator."""

from __future__ import annotations

import hashlib
from pathlib import Path


class ArtifactProvenanceVerifier:
    """Computes deterministic SHA-256 checksum manifests for release distribution artifacts."""

    @staticmethod
    def generate_checksums_manifest(dist_dir: Path) -> Path:
        if not dist_dir.exists():
            dist_dir.mkdir(parents=True, exist_ok=True)

        manifest_file = dist_dir / "checksums.sha256"
        lines = []

        for p in sorted(dist_dir.iterdir()):
            if p.is_file() and p.name != "checksums.sha256":
                sha = hashlib.sha256()
                with open(p, "rb") as f:
                    while chunk := f.read(65536):
                        sha.update(chunk)
                lines.append(f"{sha.hexdigest()}  {p.name}")

        manifest_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return manifest_file
