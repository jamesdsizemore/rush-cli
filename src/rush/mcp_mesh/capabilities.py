"""Protected capability token generation, input custody, and lease records for mesh locks."""

from __future__ import annotations

import math
import secrets
from dataclasses import dataclass
from typing import Any, Literal

ChannelType = Literal["stdin", "descriptor", "mcp_sensitive"]
VALID_CHANNELS: tuple[str, ...] = ("stdin", "descriptor", "mcp_sensitive")
FORBIDDEN_CHANNELS: tuple[str, ...] = ("argv", "env", "environment")


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
class LockCapabilityInput:
    """Represents caller-provided capability token delivered via protected channels."""

    token: str
    agent_id: str
    channel_type: Literal["stdin", "descriptor", "mcp_sensitive"] = "stdin"

    def __post_init__(self) -> None:
        if (
            self.channel_type in FORBIDDEN_CHANNELS
            or self.channel_type not in VALID_CHANNELS
        ):
            raise ValueError(
                f"Channel '{self.channel_type}' is not supported for lock capability input. "
                "Capabilities in argv or environment are rejected; only protected stdin, "
                "descriptor, or mcp_sensitive allowed."
            )


@dataclass(frozen=True)
class LockLeaseRecord:
    """Verifier-only metadata persisted to disk via AtomicFile. Never contains raw token."""

    resource_path: str
    owner_agent_id: str
    generation: int
    verifier_record: dict[str, Any]
    acquired_at: float
    expires_at: float
    physical_root: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_path": self.resource_path,
            "owner_agent_id": self.owner_agent_id,
            "agent_id": self.owner_agent_id,  # backward compatibility alias
            "generation": self.generation,
            "verifier_record": self.verifier_record,
            "acquired_at": self.acquired_at,
            "expires_at": self.expires_at,
            "physical_root": self.physical_root,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockLeaseRecord:
        owner = data.get("owner_agent_id") or data.get("agent_id") or "unknown"
        return cls(
            resource_path=str(data.get("resource_path", "")),
            owner_agent_id=str(owner),
            generation=int(data.get("generation", 1)),
            verifier_record=dict(data.get("verifier_record", {})),
            acquired_at=float(data.get("acquired_at", 0.0)),
            expires_at=float(data.get("expires_at", 0.0)),
            physical_root=str(data.get("physical_root", "")),
        )


def create_capability(
    agent_id: str, channel_type: str = "stdin"
) -> tuple[LockCapabilityInput, str]:
    """Generate high-entropy secret token (secrets.token_urlsafe(32)) and return (LockCapabilityInput, raw_token)."""
    if channel_type in FORBIDDEN_CHANNELS or channel_type not in VALID_CHANNELS:
        raise ValueError(
            f"Channel '{channel_type}' is not supported for lock capability input. "
            "Capabilities in argv or environment are rejected; only protected stdin, "
            "descriptor, or mcp_sensitive allowed."
        )
    raw_token = secrets.token_urlsafe(32)
    cap = LockCapabilityInput(
        token=raw_token,
        agent_id=agent_id,
        channel_type=channel_type,  # type: ignore[arg-type]
    )
    return cap, raw_token
