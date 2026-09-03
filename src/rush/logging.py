"""stderr NDJSON logging with RUSH_LOG_LEVEL gate + secret redaction.

Architecture §7, requirement C5.

NEVER write to stdout from any rush code path. stdout is reserved for
MCP JSON-RPC frames and the final CLI output. Even debug logs go to stderr.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import UTC, datetime


class NdjsonHandler(logging.Handler):
    """Write log records as one JSON object per line, to stderr."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            from rush.safety.redactor import SecretRedactor

            msg = record.getMessage()
            clean_msg = SecretRedactor.redact_text(msg)
            payload: dict[str, str] = {
                "ts": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": clean_msg,
            }
            if record.exc_info:
                if isinstance(record.exc_info, tuple):
                    tb_lines = traceback.format_exception(*record.exc_info)
                else:
                    tb_lines = traceback.format_exception(record.exc_info)
                exc_text = "".join(tb_lines).strip()
                payload["exc"] = SecretRedactor.redact_text(exc_text)

            sys.stderr.write(json.dumps(payload, default=str) + "\n")
            sys.stderr.flush()
        except Exception:  # noqa: BLE001 - logging must never interrupt the caller
            # Logging must never raise. Emit safe structured fallback to stderr.
            try:
                fallback = {
                    "ts": datetime.now(UTC).isoformat(),
                    "level": "ERROR",
                    "logger": "rush.logging",
                    "msg": "[LOGGING_FALLBACK: formatting failed]",
                }
                sys.stderr.write(json.dumps(fallback) + "\n")
                sys.stderr.flush()
            except Exception:  # noqa: BLE001, S110
                pass

    @staticmethod
    def _redact(msg: str) -> str:
        from rush.safety.redactor import SecretRedactor

        return SecretRedactor.redact_text(msg)


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


def log_subsystem(subsystem: str, level: str, msg: str) -> None:
    """Write structured subsystem message to stderr.

    Format: [rush-<subsystem>:<LEVEL>] <redacted_msg>
    """
    clean_msg = redact_secrets(msg)
    tag = f"[rush-{subsystem}:{level.upper()}]"
    try:
        # Also log to standard Python logger
        log = get_logger(subsystem)
        lvl_num = getattr(logging, level.upper(), logging.INFO)
        log.log(lvl_num, f"{tag} {clean_msg}")
    except Exception:  # noqa: BLE001, S110
        pass
