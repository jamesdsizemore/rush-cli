"""Protected Secret Delivery Channels for Plugin Subprocesses.

Architecture §8, Phase 56.
Enforces Control 6: Protected Secret Transport & Ephemeral Resolution.
Guarantees literal secrets never appear in process argv or environment.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Literal

from rush.plugins.trust_store import PluginTrustError
from rush.safety.redactor import SECRET_PATTERNS

SUPPORTED_CHANNELS: set[str] = {"descriptor", "stdin", "provider"}


class SecretChannelError(PluginTrustError):
    """Raised when secret channel negotiation or transport fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message=message, code=code)


@dataclass(frozen=True)
class SecretDeliveryContext:
    """Encapsulates protected channel parameters for subprocess launch."""

    channel_type: Literal["descriptor", "stdin", "provider"] | str
    env_overrides: dict[str, str]
    stdin_payload: bytes | None = None
    pass_fds: tuple[int, ...] = ()
    parent_fd: int | None = None

    @property
    def write_fd(self) -> int | None:
        return self.parent_fd


def _is_literal_secret(text: str) -> bool:
    """Check if a string contains or is a raw literal secret token."""
    if not text or not isinstance(text, str):
        return False
    candidate = text.removeprefix("secret:")
    for pattern, _ in SECRET_PATTERNS[:6]:
        if pattern.search(candidate) is not None:
            return True
    if not text.startswith("secret:"):
        for pattern, _ in SECRET_PATTERNS[6:]:
            if pattern.search(text) is not None:
                return True
    return False


def negotiate_secret_channel(
    channel_type: str,
    secret_refs: list[str],
    secrets: dict[str, str],
) -> SecretDeliveryContext:
    """Negotiate a protected secret delivery channel for plugin execution.

    Args:
        channel_type: Supported channel type ('descriptor', 'stdin', 'provider').
        secret_refs: Declared secret reference identifiers (e.g. 'secret:API_KEY').
        secrets: Resolved secret values mapping reference names to secret strings.

    Returns:
        SecretDeliveryContext configuring scrubbed environment and channel descriptors.

    Raises:
        SecretChannelError: If channel is unsupported or literal secrets are supplied.
    """
    if channel_type not in SUPPORTED_CHANNELS:
        raise SecretChannelError(
            "UNSUPPORTED_SECRET_CHANNEL",
            f"Channel '{channel_type}' is not supported. Supported channels: {sorted(SUPPORTED_CHANNELS)}",
        )

    # Validate that secret_refs are references, not literal secret values
    for ref in secret_refs:
        if _is_literal_secret(ref):
            raise SecretChannelError(
                "LITERAL_SECRET_FORBIDDEN",
                f"Literal secret detected in secret reference '{ref}'. "
                "Secrets must be declared as references (e.g. 'secret:NAME').",
            )

    # Resolve declared secrets
    resolved_secrets: dict[str, str] = {}
    if secret_refs:
        for ref in secret_refs:
            key = ref.removeprefix("secret:")
            if key in secrets:
                resolved_secrets[key] = secrets[key]
            elif ref in secrets:
                resolved_secrets[key] = secrets[ref]
            else:
                resolved_secrets[key] = secrets.get(key, "")
    else:
        resolved_secrets = dict(secrets)

    if channel_type == "stdin":
        payload_bytes = json.dumps(resolved_secrets).encode("utf-8")
        return SecretDeliveryContext(
            channel_type="stdin",
            env_overrides={"RUSH_SECRET_CHANNEL": "stdin"},
            stdin_payload=payload_bytes,
            pass_fds=(),
            parent_fd=None,
        )

    if channel_type == "descriptor":
        read_fd, write_fd = os.pipe()
        env_overrides = {
            "RUSH_SECRET_CHANNEL": "descriptor",
            "RUSH_SECRET_FD": str(read_fd),
        }
        return SecretDeliveryContext(
            channel_type="descriptor",
            env_overrides=env_overrides,
            stdin_payload=None,
            pass_fds=(read_fd,),
            parent_fd=write_fd,
        )

    if channel_type == "provider":
        env_overrides = {
            "RUSH_SECRET_CHANNEL": "provider",
            "RUSH_SECRET_PROVIDER": "system",
        }
        return SecretDeliveryContext(
            channel_type="provider",
            env_overrides=env_overrides,
            stdin_payload=None,
            pass_fds=(),
            parent_fd=None,
        )

    raise SecretChannelError(
        "UNSUPPORTED_SECRET_CHANNEL",
        f"Channel '{channel_type}' is not supported.",
    )
