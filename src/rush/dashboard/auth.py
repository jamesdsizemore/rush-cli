"""Cryptographic session authentication token generator."""

from __future__ import annotations

import hmac
import secrets
from typing import Any


class SessionAuthManager:
    """Manages 256-bit CSPRNG session bearer tokens."""

    def __init__(self) -> None:
        self.session_token = secrets.token_urlsafe(32)

    def verify_token(self, provided_token: str | None) -> bool:
        if not provided_token:
            return False
        return hmac.compare_digest(self.session_token, provided_token)
