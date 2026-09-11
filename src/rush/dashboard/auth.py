"""Cryptographic session authentication token generator."""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass


class SessionAuthManager:
    """Manages 256-bit CSPRNG session bearer tokens."""

    def __init__(self) -> None:
        self.session_token = secrets.token_urlsafe(32)

    def verify_token(self, provided_token: str | None) -> bool:
        if not provided_token:
            return False
        return hmac.compare_digest(self.session_token, provided_token)


# --- Phase 66 P66-01: canonical per-server authenticated API -----------------
#
# DashboardAuth is the per-instance auth/session/control boundary for the new
# canonical dashboard API (server.py's create_dashboard_server). It is never a
# class attribute or module-level singleton -- every server instance builds
# its own DashboardAuth, so two concurrently-running servers can never observe
# or influence each other's bootstrap token, cookie session, CSRF token, or
# control capability.

BOOTSTRAP_TTL_SECONDS = 300  # one-use launch token, 5 minutes (spec 3.7)
SESSION_TTL_SECONDS = 8 * 60 * 60  # cookie session, 8 hours (spec 3.7)


@dataclass
class Session:
    cookie_value: str
    csrf_token: str
    created_at: float
    expires_at: float


@dataclass
class _Bootstrap:
    token: str
    issued_at: float
    used: bool = False


class DashboardAuth:
    """Per-server bootstrap/session/CSRF/control-capability authentication."""

    def __init__(self, server_id: str | None = None) -> None:
        self.server_id = server_id or secrets.token_hex(8)
        self.cookie_name = f"rush_session_{self.server_id}"
        self.control_capability = secrets.token_urlsafe(32)
        self._bootstrap: _Bootstrap | None = None
        self._sessions: dict[str, Session] = {}
        self.issue_bootstrap()

    def issue_bootstrap(self) -> str:
        """Issue a fresh one-use launch token, invalidating any prior one."""
        token = secrets.token_urlsafe(32)
        self._bootstrap = _Bootstrap(token=token, issued_at=time.time())
        return token

    def verify_bootstrap(self, provided: str | None) -> bool:
        bootstrap = self._bootstrap
        if bootstrap is None or bootstrap.used or not provided:
            return False
        if time.time() - bootstrap.issued_at > BOOTSTRAP_TTL_SECONDS:
            return False
        return hmac.compare_digest(bootstrap.token, provided)

    def exchange_bootstrap(self, provided: str | None) -> Session | None:
        """Consume the bootstrap token once and mint a new cookie session."""
        if not self.verify_bootstrap(provided):
            return None
        assert self._bootstrap is not None
        self._bootstrap.used = True
        return self._create_session()

    def _create_session(self) -> Session:
        now = time.time()
        session = Session(
            cookie_value=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + SESSION_TTL_SECONDS,
        )
        self._sessions[session.cookie_value] = session
        return session

    def get_session(self, cookie_value: str | None) -> Session | None:
        if not cookie_value:
            return None
        session = self._sessions.get(cookie_value)
        if session is None:
            return None
        if time.time() > session.expires_at:
            del self._sessions[cookie_value]
            return None
        return session

    def verify_csrf(self, cookie_value: str | None, csrf_header: str | None) -> bool:
        session = self.get_session(cookie_value)
        if session is None or not csrf_header:
            return False
        return hmac.compare_digest(session.csrf_token, csrf_header)

    def verify_control(self, provided: str | None) -> bool:
        if not provided:
            return False
        return hmac.compare_digest(self.control_capability, provided)
