"""Contract tests for Phase 53: Exception Diagnostics and Logging Invariants (P53.5.1)."""

from __future__ import annotations

import io
import json
import logging
import sys

import pytest

from rush.logging import NdjsonHandler


def test_exception_emits_one_complete_redacted_ndjson_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that logging an exception emits complete redacted NDJSON to stderr and never drops the record."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_buf)

    test_logger = logging.getLogger("rush.test_diagnostics")
    test_logger.handlers.clear()
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = False
    test_logger.addHandler(NdjsonHandler())

    try:
        raise ValueError(
            f"Failed connecting to https://admin:{fresh_secret}@api.provider.com"
        )
    except ValueError as exc:
        test_logger.error("Encountered unexpected upstream error", exc_info=exc)

    output = stderr_buf.getvalue().strip()
    assert len(output) > 0, (
        "Logging exception produced empty stderr output; diagnostic was dropped!"
    )

    lines = output.splitlines()
    assert len(lines) == 1, f"Expected exactly 1 NDJSON line, got {len(lines)}"

    record = json.loads(lines[0])
    assert record["level"] == "ERROR"
    assert record["logger"] == "rush.test_diagnostics"
    assert "Encountered unexpected upstream error" in record["msg"]
    assert "exc" in record
    assert "ValueError" in record["exc"]
    assert fresh_secret not in record["exc"]
    assert fresh_secret not in record["msg"]


def test_mcp_stdout_remains_json_rpc_only(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify that logging operations NEVER write anything to stdout."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_buf)
    monkeypatch.setattr(sys, "stderr", stderr_buf)

    test_logger = logging.getLogger("rush.test_stdout")
    test_logger.handlers.clear()
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = False
    test_logger.addHandler(NdjsonHandler())

    test_logger.info("Informational message")
    test_logger.warning("Warning message")
    test_logger.error("Error message")

    assert stdout_buf.getvalue() == "", "stdout was contaminated by logging output!"
    assert len(stderr_buf.getvalue()) > 0, "stderr should have received log records"


def test_formatter_failure_emits_one_safe_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that any exception during log formatting produces one safe fallback NDJSON to stderr and zero stdout."""
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout_buf)
    monkeypatch.setattr(sys, "stderr", stderr_buf)

    test_logger = logging.getLogger("rush.test_fallback")
    test_logger.handlers.clear()
    test_logger.setLevel(logging.DEBUG)
    test_logger.propagate = False
    test_logger.addHandler(NdjsonHandler())

    class BrokenMessage:
        def __str__(self) -> str:
            raise RuntimeError("Forced formatting crash")

    test_logger.info("Message with %s", BrokenMessage())

    assert stdout_buf.getvalue() == "", (
        "stdout was contaminated during formatter fallback!"
    )
    output = stderr_buf.getvalue().strip()
    assert len(output) > 0, "Fallback record was not emitted to stderr!"

    lines = output.splitlines()
    assert len(lines) == 1, f"Expected exactly 1 fallback line, got {len(lines)}"

    record = json.loads(lines[0])
    assert record["level"] == "ERROR"
    assert record["logger"] == "rush.logging"
    assert record["msg"] == "[LOGGING_FALLBACK: formatting failed]"
