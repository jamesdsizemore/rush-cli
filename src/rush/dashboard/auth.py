"""Cryptographic session authentication token generator."""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import secrets
import threading
import time
from dataclasses import dataclass


def _digest(value: str) -> str:
    """One-way digest of a bearer/session secret (P69-01.3 CONNECT): stored in
    place of the plaintext so a bootstrap token or session cookie can never be
    lifted verbatim from `DashboardAuth`'s own internal state (e.g. `vars()`,
    a serialization bug, a memory dump). `csrf_token` stays plaintext on the
    `Session` record -- unlike a bootstrap/cookie secret, it is legitimately
    re-served to its already-authenticated holder on every `GET /api/session`
    reload (`test_reload_restores_cookie_session_without_bearer_storage`),
    so it is never looked up by digest and has no round-trip-retrieval
    requirement to violate."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def new_session_owner_scope_id() -> str:
    """A non-secret, per-session identity for `owner_scope` use (P69-07 subsection b).

    `Session` carries no identifier that may be reused as a memory-ownership label:
    `cookie_digest` is the digest of a live bearer secret and `csrf_token` is a live
    anti-forgery secret -- storing either inside persisted memory content would leak an
    authentication value into the memory store. This mints a separate opaque id that
    authenticates nothing, is never accepted as a credential anywhere, and lives exactly
    as long as the `Session` it belongs to.
    """
    return secrets.token_urlsafe(12)


@dataclass
class Session:
    cookie_digest: str
    csrf_token: str
    created_at: float
    expires_at: float
    # P69-07 subsection b: the session's `owner_scope` identity. Defaulted so any
    # future `Session(...)` construction still gets a real, distinct id rather than
    # silently sharing or omitting one.
    owner_scope_id: str = dataclasses.field(default_factory=new_session_owner_scope_id)


@dataclass
class _Bootstrap:
    digest: str
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
        # S11: one owning lock across bootstrap lookup, expiry/used checks,
        # consumption, and the resulting session insertion. Reentrant so
        # `exchange_bootstrap` can call the same lock-held verifier without
        # deadlocking itself -- direct method callers get the same
        # single-use guarantee HTTP concurrency previously masked with a
        # route-only lock.
        self._lock = threading.RLock()
        self.issue_bootstrap()

    def issue_bootstrap(self) -> str:
        """Issue a fresh one-use launch token, invalidating any prior one."""
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._bootstrap = _Bootstrap(digest=_digest(token), issued_at=time.time())
        return token

    def verify_bootstrap(self, provided: str | None) -> bool:
        with self._lock:
            return self._verify_bootstrap_locked(provided)

    def _verify_bootstrap_locked(self, provided: str | None) -> bool:
        bootstrap = self._bootstrap
        if bootstrap is None or bootstrap.used or not provided:
            return False
        if time.time() - bootstrap.issued_at > BOOTSTRAP_TTL_SECONDS:
            return False
        return hmac.compare_digest(bootstrap.digest, _digest(provided))

    def exchange_bootstrap(self, provided: str | None) -> tuple[Session, str] | None:
        """Consume the bootstrap token once and mint a new cookie session.
        Returns `(session, cookie_value)` -- `cookie_value` is the plaintext
        secret the caller must hand to the browser via Set-Cookie; only its
        digest is retained on `session` itself.

        S11: verification and consumption happen under one held lock, so
        two concurrent callers can never both observe an unused token as
        valid -- exactly one exchange mints a session per issued token,
        whether callers go through HTTP or call this method directly."""
        with self._lock:
            if not self._verify_bootstrap_locked(provided):
                return None
            assert self._bootstrap is not None
            self._bootstrap.used = True
            return self._create_session_locked()

    def _create_session_locked(self) -> tuple[Session, str]:
        now = time.time()
        cookie_value = secrets.token_urlsafe(32)
        session = Session(
            cookie_digest=_digest(cookie_value),
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + SESSION_TTL_SECONDS,
        )
        self._sessions[session.cookie_digest] = session
        return session, cookie_value

    def get_session(self, cookie_value: str | None) -> Session | None:
        if not cookie_value:
            return None
        digest = _digest(cookie_value)
        with self._lock:
            session = self._sessions.get(digest)
            if session is None:
                return None
            if time.time() > session.expires_at:
                del self._sessions[digest]
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

    def live_secret_values(self) -> tuple[str, ...]:
        """S12 point 1: lock-protected snapshot of every currently-live
        plaintext secret this server can always redact by exact match --
        the control capability plus each active session's CSRF token
        (legitimately re-served in plaintext on `GET /api/session` reload).
        The bootstrap token and session cookie value are never retained in
        plaintext once minted, so they are never in this set; see
        `match_presented_secret` for those two."""
        with self._lock:
            return (
                self.control_capability,
                *(session.csrf_token for session in self._sessions.values()),
            )

    def match_presented_secret(self, candidate: str | None) -> bool:
        """S12 point 3: hash-only check for whether `candidate` -- a value a
        caller already extracted from the *current* request, e.g. a
        presented bootstrap token or session cookie -- digests to a
        currently-live bootstrap or session secret, using constant-time
        comparison against the stored digest snapshot. Never retains or
        logs `candidate`; a caller uses a True result to decide its own
        already-known value is safe to redact, never to redact a blind
        substring."""
        if not candidate:
            return False
        digest = _digest(candidate)
        with self._lock:
            if (
                self._bootstrap is not None
                and not self._bootstrap.used
                and hmac.compare_digest(self._bootstrap.digest, digest)
            ):
                return True
            for session_digest in self._sessions:
                if hmac.compare_digest(session_digest, digest):
                    return True
        return False
