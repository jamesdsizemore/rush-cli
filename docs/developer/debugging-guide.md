# Contributor Debugging & Diagnostics Guide

A comprehensive guide for debugging engine discovery, subprocess execution, MCP transport hangs, parser errors, and platform-specific behaviors.

For continuity, run a JSON save/restore and inspect only `metadata.handoff`: it is deliberately redacted and reports dependency `freshness`, a quarantined historic-instruction marker, and a failure receipt/tombstone. Diagnose a stale receipt by comparing declared paths, then save a fresh checkpoint; never add raw secrets, transcripts, or provider credentials to debugging output.

---

## 1. Structured Debugging Workflow

1. **Isolate stdout from stderr**: Run the problematic command with `--json` and inspect stdout (pure JSON result) and stderr (diagnostics).
   ```bash
   rush security . --json 2> debug.log
   ```
2. **Inspect Engine Discovery**: Run capabilities discovery to verify whether Rush locates external binaries:
   ```bash
   rush capabilities . --json
   ```
3. **Verify Environment Sanitation**: On Windows, foreign virtualenvs or global `PYTHONPATH` can leak into subprocesses. Always verify with:
   ```bash
   unset VIRTUAL_ENV PYTHONPATH
   ```

---

## 2. Common Failure Modes & Diagnostics

### Symptom: MCP Server Hangs Indefinitely
- **Root Cause**: An external engine was invoked without `stdin=subprocess.DEVNULL`, causing it to consume FastMCP's JSON-RPC standard input stream.
- **Resolution**: Ensure all command executions go through `run_subprocess()` in `src/rush/tools/common.py`.

### Symptom: Tool Returns `status: "error"`
- **Root Cause**: The engine emitted invalid JSON/XML/SARIF or exited with an unexpected crash code.
- **Resolution**: Inspect `raw` in the JSON result or check `tests/fixtures/engine_reports/<engine>/` to ensure parser handles malformed outputs gracefully.

### Symptom: Stale Finding Fingerprints
- **Root Cause**: Fingerprint calculation algorithm drifted or paths were not normalized with forward slashes.
- **Resolution**: Ensure finding paths are normalized relative to project root with forward slashes before hashing.

See [Testing Guide](testing-guide.md) and [Tool Development](tool-development.md).
