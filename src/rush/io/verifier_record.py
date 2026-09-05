"""One-way non-recoverable capability verifier record and validation."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class VerifierError(Exception):
    """Raised when verifier creation or validation fails."""


def _calculate_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not text:
        return 0.0
    entropy = 0.0
    length = len(text)
    for char in set(text):
        p = text.count(char) / length
        entropy -= p * math.log2(p)
    return entropy


@dataclass(frozen=True)
class VerifierRecord:
    """A one-way non-recoverable capability verifier record."""

    version: str
    salt: str
    algorithm: str
    work_factor: int
    verifier: str
    created_at: str

    @classmethod
    def create(
        cls,
        raw_capability: str | bytes,
        *,
        work_factor: int = 100_000,
        algorithm: str = "pbkdf2_sha256",
    ) -> VerifierRecord:
        """Create a non-recoverable verifier record from a raw capability."""
        raw_str = (
            raw_capability.decode("utf-8", errors="replace")
            if isinstance(raw_capability, bytes)
            else str(raw_capability)
        )

        if len(raw_str.strip()) < 16:
            raise VerifierError("Capability length must be at least 16 characters")

        if _calculate_entropy(raw_str) < 2.5:
            raise VerifierError("Capability entropy too low (< 2.5 bits/symbol)")

        salt_bytes = secrets.token_bytes(32)
        raw_bytes = raw_str.encode("utf-8")

        digest = hashlib.pbkdf2_hmac("sha256", raw_bytes, salt_bytes, work_factor)
        created_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        return cls(
            version="1.0.0",
            salt=salt_bytes.hex(),
            algorithm=algorithm,
            work_factor=work_factor,
            verifier=digest.hex(),
            created_at=created_at,
        )

    def verify(self, candidate: str | bytes) -> bool:
        """Verify a candidate capability in constant time."""
        candidate_str = (
            candidate.decode("utf-8", errors="replace")
            if isinstance(candidate, bytes)
            else str(candidate)
        )
        candidate_bytes = candidate_str.encode("utf-8")
        salt_bytes = bytes.fromhex(self.salt)

        candidate_digest = hashlib.pbkdf2_hmac(
            "sha256", candidate_bytes, salt_bytes, self.work_factor
        ).hex()
        return hmac.compare_digest(self.verifier, candidate_digest)

    def to_dict(self) -> dict[str, Any]:
        """Serialize verifier metadata. Guaranteed to contain zero raw capability information."""
        return {
            "version": self.version,
            "salt": self.salt,
            "algorithm": self.algorithm,
            "work_factor": self.work_factor,
            "verifier": self.verifier,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerifierRecord:
        """Reconstruct a VerifierRecord from serialized dictionary."""
        return cls(
            version=str(data["version"]),
            salt=str(data["salt"]),
            algorithm=str(data["algorithm"]),
            work_factor=int(data["work_factor"]),
            verifier=str(data["verifier"]),
            created_at=str(data["created_at"]),
        )
