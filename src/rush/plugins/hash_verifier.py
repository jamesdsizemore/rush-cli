"""Sub-millisecond pre-execution hash verifier."""

from __future__ import annotations

import hashlib
from pathlib import Path


class PreExecutionHashVerifier:
    """Provides high-performance SHA-256 byte hashing for plugin files."""

    @staticmethod
    def verify_hash(file_path: Path, expected_sha256: str) -> bool:
        if not file_path.exists() or not file_path.is_file():
            return False
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest().lower() == expected_sha256.lower()

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()
