# ADR 0004: Bounded subprocess execution

## Context
Rush’s MCP transport shares stdin with the host process and scanner output can be unsafe.

## Decision
Every external invocation uses list-only `run_subprocess()` with `stdin=DEVNULL`, explicit optional cwd, timeout, captured bounded output, and no shell. Timeout/cancellation map to public `error` with metadata.

## Rejected alternatives
Shell commands, inherited stdin, adapter-specific runners, and new public timeout statuses were rejected.

## Consequences
`Engine.version()` and adapters use the shared helper. Tests: `tests/test_phase00_subprocess.py` and engine tests.

## Compatibility and operations
No command can consume MCP JSON-RPC input. Diagnostics remain on stderr.
