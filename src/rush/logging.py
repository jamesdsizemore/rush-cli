"""stderr NDJSON logging with RUSH_LOG_LEVEL gate + secret redaction.

Architecture §7, requirement C5.

NEVER write to stdout from any rush code path. stdout is reserved for
MCP JSON-RPC frames and the final CLI output. Even debug logs go to stderr.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime

REDACT_KEYS = {"api_key", "token", "secret", "password", "authorization"}


class NdjsonHandler(logging.Handler):
    """Write log records as one JSON object per line, to stderr."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            payload = {
                "ts": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": self._redact(record.getMessage()),
            }
            if record.exc_info:
                payload["exc"] = self.format(record.exc_info)
            sys.stderr.write(json.dumps(payload, default=str) + "\n")
            sys.stderr.flush()
        except Exception:  # noqa: BLE001 - logging must never interrupt the caller
            # Logging must never raise. Swallow any formatter/IO failure.
            return

    @staticmethod
    def _redact(msg: str) -> str:
        low = msg.lower()
        for key in REDACT_KEYS:
            if key in low:
                return "[REDACTED — secret-like value]"
        return msg


def redact_secrets(msg: str) -> str:
    """Helper to redact sensitive keywords from arbitrary strings."""
    return NdjsonHandler._redact(msg)


def setup_logging(level: str | None = None) -> None:
    """Wire up stderr NDJSON logging under the ``rush`` logger.

    Idempotent — safe to call from CLI entrypoint and from tests.
    ``level`` falls back to RUSH_LOG_LEVEL env var, then "warn".
    """
    if level is None:
        level = os.environ.get("RUSH_LOG_LEVEL", "warn")

    log = logging.getLogger("rush")
    log.setLevel(getattr(logging, level.upper(), logging.WARNING))

    for h in list(log.handlers):
        log.removeHandler(h)
    log.addHandler(NdjsonHandler())
    # Don't propagate to root (avoids double-logging via other handlers).
    log.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the ``rush`` logger, e.g. ``get_logger("tools.lint")``."""
    if name is None:
        return logging.getLogger("rush")
    return logging.getLogger(f"rush.{name}")
