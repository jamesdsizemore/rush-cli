"""Rush runtime boundary primitives (binaries, subprocesses, results, filesystem)."""

from __future__ import annotations

from .binaries import (
    _resolve_binary_cached,
    _venv_scripts_dir,
    clear_binary_cache,
    engine_on_path,
    resolve_binary,
)
from .filesystem import (
    atomic_write_bytes,
    resolve_contained_output,
)
from .result_helpers import (
    _redact_finding_message,
    elapsed_ms,
    error_result,
    exit_code_for,
    finding_fingerprint,
    normalize_findings,
    now_ms,
    skipped_result,
)
from .subprocesses import (
    MAX_SUBPROCESS_OUTPUT_CHARS,
    _bounded_redacted_output,
    _install_hint,
    run_engine,
    run_subprocess,
)

__all__ = [
    "MAX_SUBPROCESS_OUTPUT_CHARS",
    "_bounded_redacted_output",
    "_install_hint",
    "_redact_finding_message",
    "_resolve_binary_cached",
    "_venv_scripts_dir",
    "atomic_write_bytes",
    "clear_binary_cache",
    "elapsed_ms",
    "engine_on_path",
    "error_result",
    "exit_code_for",
    "finding_fingerprint",
    "normalize_findings",
    "now_ms",
    "resolve_binary",
    "resolve_contained_output",
    "run_engine",
    "run_subprocess",
    "skipped_result",
]
