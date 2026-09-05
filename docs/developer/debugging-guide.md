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

### Symptom: `error-catalog` or `iam-audit` Returns `status: "skipped"` on Export
- **Root Cause**: Writing output artifacts to disk requires explicit authorization.
- **Resolution**: Pass `--allow-artifact-write` in the CLI or set `allow_artifact_write=True` in MCP invocations.

### Symptom: `ToolConfig.options` Mutation Raises `TypeError`
- **Root Cause**: Tool configuration options are wrapped in immutable `types.MappingProxyType` to prevent concurrency corruption.
- **Resolution**: Call `resolve_tool_options(tool_name, config_options, invocation_options)` from `rush.config` to compute a merged dictionary.

See [Testing Guide](testing-guide.md) and [Tool Development](tool-development.md).


### Phase 50b Troubleshooting
- **`provenance-ai` returns `shallow_history: True`**: The repository is a shallow clone (`.git/shallow` exists or `git rev-parse --is-shallow-repository` is true). Historical commit trailers prior to clone depth are omitted.
- **`dead-asset` unreferenced warnings**: Assets are flagged if neither filename nor relative path appears in source files. Check for dynamic string interpolation in templates.
- **`pr-synthesize` CODEOWNERS matching**: Rules are matched against relative file paths from repository root using standard `fnmatch` patterns.

### Phase 50c Troubleshooting
- **`attest` subject is `source-tree` instead of package**: No built distribution file (`.whl` or `.tar.gz`) was found in `dist/`. Run `uv build` first, or specify `--artifact-path`.
- **`mem-profile` returns `skipped` for dynamic mode**: Dynamic profiling requires explicit `--allow-slow` permission.
- **`cold-start` heavy import warnings**: Move heavy package imports (`torch`, `pandas`, `boto3`) inside the function or method where they are used.
- **`offline-review` returns `skipped`**: The ONNX model `.rush/models/review.onnx` or the `onnxruntime` package is not present.
- **`benchmark` returns `skipped`**: No baseline was found in `.rush/baselines.json`. Run `rush benchmark check . --record --allow-cache-write` to establish a baseline.

### Phase 53 Troubleshooting: Diagnostics & Write Boundaries
- **Disappearing exception tracebacks (R-008)**: Previously, logging an exception with `exc_info` failed silently inside `NdjsonHandler.emit` due to tuple formatting. This is resolved: all exceptions emit complete single-line redacted NDJSON to stderr with a fallback JSON emitter on formatting failure.
- **Sanitized dictionary keys & collision suffixing**: If two dictionary keys contain distinct secrets that both redact to `"[REDACTED — secret-like value]"`, the second key is deterministically suffixed with `__collision_1` and recorded in collision metadata rather than overwriting the first key.
- **Strict stderr logging**: MCP JSON-RPC requires that stdout contain zero logging output. Logging must always go through `get_logger()` or `NdjsonHandler` to ensure only stderr is used.

### Phase 54 Troubleshooting: ToolResultV1 Schema Validation
- **`ValidationErrorV1` failure codes**:
  - `MISSING_REQUIRED_KEY`: One of the 8 canonical fields (`schema_version`, `tool`, `engine`, `status`, `duration_ms`, `timestamp`, `summary`, `findings`) was missing from output.
  - `INVALID_TYPE`: Field type does not conform (e.g. `duration_ms` is negative or float, `findings` is not a list).
  - `INVALID_STATUS`: Status is not one of `ok`, `warn`, `fail`, `error`, `skipped`.
  - `INVALID_TIMESTAMP`: Timestamp is not a valid ISO 8601 UTC string ending in `Z`.
  - `FINDING_MISSING_REQUIRED_KEY`: Finding is missing `id`, `path`, `line`, `message`, or `severity`.
  - `INVALID_SEVERITY`: Finding severity is not one of `info`, `warning`, `error`.
  - `SERVICE_TOOL_RESULT_PROHIBITED`: A service-kind operation (e.g. MCP protocol handler) attempted to return a wrapped `ToolResultV1`.
