# JSON Schema & Output Specification

## Context recovery handle

For an insufficient `context_pack` budget with cache-write permission, `metadata.context_envelope` carries `omissions` and `recovery: {state: "available", handle: <sha256>}`. The handle identifies a redacted local CCR chunk. Without permission, recovery is `{state: "not_created", reason: "cache_write_required"}` and no chunk is created. `context_retrieve` redacts any legacy chunk before returning `recovery.state: "recovered"` or structured `not_found`; it does not infer or recreate a handle.

## Continuity `ToolResult`

`continuity` returns `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, `raw`, `artifacts`, and `metadata`. `metadata.operation` identifies `save`, `list`, or `restore`; `metadata.execution` records requested and granted permissions. A saved or restored receipt appears at `metadata.handoff` with `version`, `current_goal`, `open_work`, `historic_instruction`, `dependencies`, `freshness`, `failure_receipt`, `session_memory`, and `redaction_count`. `historic_instruction` and bounded historical session-memory records are labelled `historical_evidence`; receipt failures expose a fingerprint/redacted error, an explicit tombstone, or structured unavailable evidence—never a failed patch. Empty lists are `ok`; missing checkpoints and denied saves are `skipped`.

For `context_pack` and `context_retrieve`, `metadata.context_envelope` contains `selected_evidence`, `tokens` (`estimated`, `actual`, `budget`), `omissions`, and `recovery`. An overflow also carries `telemetry`; an omitted, undelivered payload is `{state: "not_measured", reason: "omitted_context_not_delivered", provider_cost: null}` and creates no savings event. `actual` is `null` unless a local measurement exists; missing recovery is explicit and an insufficient budget is `skipped`.

For coordination operations, `metadata.coordination` contains a state and only safe receipt fields. A stale lock includes `{state: "stale", owner, action: "manual_recovery_required"}`; an overlapping merge includes `{state: "merge_conflict", conflicts, action: "manual_reconciliation_required"}`. Recovery nests replay counts and a redacted failure receipt; malformed replay and corrupt ledger evidence are structured unavailable states. It never includes replay payloads or failed patches.

For `provider_resume`, `metadata.provider_route` includes `provider_id`, `transport`, and `state`; the fixed-loopback OmniRoute route also includes `endpoint_class`. `state: "completed"` means a supported direct CLI process exited successfully or OmniRoute returned a non-empty OpenAI-compatible completion; it does not attest that the provider completed the requested work because Rush deliberately discards provider output. A missing profile, checkpoint, permission, unsupported route, or deferred route is structured `skipped`. Provider process output, response body, and credential values are never included in the `ToolResult`.

Rush produces standardized, machine-readable JSON output for all 38 tools when invoked with `--json` or via FastMCP.

---

## 1. ToolResult Schema Specification

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ToolResult",
  "type": "object",
  "required": [
    "tool",
    "engine",
    "engine_version",
    "status",
    "duration_ms",
    "summary",
    "findings",
    "raw"
  ],
  "properties": {
    "tool": {
      "type": "string",
      "description": "Name of the Rush tool (e.g. lint, security, ai-eval)"
    },
    "engine": {
      "type": ["string", "null"],
      "description": "Name of the engine or multi-engine aggregate (e.g. ruff+eslint)"
    },
    "engine_version": {
      "type": ["string", "null"],
      "description": "Detected version string of the engine"
    },
    "status": {
      "type": "string",
      "enum": ["ok", "warn", "fail", "error", "skipped"],
      "description": "Overall status of the tool execution"
    },
    "duration_ms": {
      "type": "integer",
      "minimum": 0,
      "description": "Execution duration in milliseconds"
    },
    "summary": {
      "type": "string",
      "description": "Concise, human-readable summary message"
    },
    "findings": {
      "type": "array",
      "items": { "$ref": "#/$defs/Finding" },
      "description": "List of normalized issue findings"
    },
    "raw": {
      "description": "Optional raw engine output for debugging"
    },
    "metrics": {
      "type": "object",
      "description": "Numeric or string metric measurements (e.g. complexity, memory, lines)"
    },
    "artifacts": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Paths to generated or imported artifact files"
    },
    "metadata": {
      "type": "object",
      "description": "Execution context and permission metadata"
    }
  },
  "$defs": {
    "Finding": {
      "type": "object",
      "required": ["fingerprint", "path", "line", "rule", "severity", "message", "provenance", "freshness"],
      "properties": {
        "fingerprint": { "type": "string" },
        "path": { "type": "string" },
        "line": { "type": "integer" },
        "column": { "type": ["integer", "null"] },
        "end_line": { "type": ["integer", "null"] },
        "end_column": { "type": ["integer", "null"] },
        "rule": { "type": "string" },
        "severity": { "type": "string", "enum": ["info", "warn", "error"] },
        "message": { "type": "string" },
        "fix": { "type": ["string", "null"] },
        "provenance": { "type": "string" },
        "freshness": { "type": "string", "enum": ["unknown", "existing", "new"] }
      }
    }
  }
}
```

See [Result Reference](reference/result-reference.md).

---

## 2. Serialization Sanitization Invariant (Phase 53)

All JSON emissions (CLI `--json`, FastMCP responses, SARIF, cache entries) conform to the recursive sanitization contract:
1. **Key & Value Redaction**: Every string value and dictionary key within `ToolResult`, including nested `raw`, `findings`, and `metadata`, is stripped of recognized secret patterns (API keys, bearer tokens, private keys, passwords, URL credentials).
2. **Loss-Visible Key Collisions**: If key redaction creates collision within an object, keys are suffixed with `__collision_{i}` to prevent silent loss of data.
3. **Fail-Closed Placeholder**: Unsupported or opaque object types within `raw` or `metadata` serialize as `"[UNSUPPORTED_TYPE:<type>]"` rather than leaking uninspected string representations.

---

## 3. ToolResultV1 & FindingV1 Specification (Phase 54)

`ToolResultV1` establishes the canonical, version-enforced output contract implemented in `src/rush/contracts/results.py`:

### 3.1 ToolResultV1 JSON Schema
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "ToolResultV1",
  "type": "object",
  "required": [
    "schema_version",
    "tool",
    "status",
    "duration_ms",
    "summary",
    "findings"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": { "type": "string", "const": "1.0.0" },
    "tool": { "type": "string", "minLength": 1 },
    "engine": { "type": ["string", "null"] },
    "engine_version": { "type": ["string", "null"] },
    "status": { "type": "string", "enum": ["ok", "warn", "fail", "error", "skipped"] },
    "duration_ms": { "type": "integer", "minimum": 0 },
    "summary": { "type": "string" },
    "findings": {
      "type": "array",
      "items": { "$ref": "#/$defs/FindingV1" }
    },
    "raw": {},
    "extensions": {
      "type": "object",
      "description": "Namespaced JSON-safe container for engine-specific or optional metrics/artifacts"
    }
  },
  "$defs": {
    "FindingV1": {
      "type": "object",
      "required": [
        "path",
        "line",
        "column",
        "rule_id",
        "severity",
        "message",
        "fingerprint"
      ],
      "additionalProperties": false,
      "properties": {
        "path": { "type": "string" },
        "line": { "type": "integer", "minimum": 0 },
        "column": { "type": "integer", "minimum": 0 },
        "rule_id": { "type": "string", "minLength": 1 },
        "severity": { "type": "string", "enum": ["info", "warning", "error"] },
        "message": { "type": "string" },
        "fingerprint": { "type": "string", "pattern": "^[0-9a-f]{64}$" },
        "rule": { "type": ["string", "null"] },
        "fix": { "type": ["object", "null"] },
        "remediation": { "type": ["object", "string", "null"] },
        "evidence": { "type": ["object", "string", "null"] },
        "provenance": { "type": ["string", "null"] },
        "freshness": { "type": ["string", "null"] },
        "patch": { "type": ["string", "null"] },
        "suggested_fix": { "type": ["string", "null"] },
        "extensions": { "type": "object" }
      }
    }
  }
}
```

### 3.2 Canonical Severity and Legacy Mapping
- **Finding Severities**: Canonical severities in `FindingV1` are strictly `"info"`, `"warning"`, and `"error"`.
- **Legacy Mappings**:
  - Legacy finding severity `"warn"` maps strictly to `"warning"`.
  - Legacy finding severity `"fail"` maps strictly to `"error"`.
  - Any unmappable or missing severity raises `ValidationErrorV1(code="INVALID_SEVERITY")`. Silent default coercion is strictly prohibited.

### 3.3 Strict Top-Level Key Rejection
Any unrecognized key at the top-level of `ToolResultV1` or `FindingV1` raises `ValidationErrorV1(code="UNKNOWN_TOP_LEVEL_KEY")`. Extensions and auxiliary fields (`metrics`, `artifacts`, `metadata`) must be encapsulated within `extensions: dict[str, Any]`.

### 3.4 ValidationErrorV1 Structure
When validation fails, validation functions raise `ValidationErrorV1` carrying:
```json
{
  "error": "validation_error",
  "code": "MISSING_REQUIRED_FIELD | UNKNOWN_TOP_LEVEL_KEY | INVALID_STATUS | INVALID_SEVERITY | INVALID_SCHEMA_VERSION | INVALID_TYPE | NON_JSON_SAFE_VALUE",
  "message": "Human-readable failure description",
  "path": "field.subfield[index]",
  "invalid_value": "..."
}
```

### Plugin Closure & Trust Ledger Schemas (Phase 56)
- `PluginClosureManifest`: Validates `schema_version`, `plugin_name`, `entrypoint`, `file_manifest`, `config_digest`, `allowed_env_names`, `declared_secret_refs`, `runtime_identity`, `platform_identity`, `closure_digest`.
- `TrustedPluginRecord`: Validates `name`, `closure_digest`, `snapshot_path`, `granted_at`, `granted_by`, `verifier_record`.
- Plugin Subprocess Output: Validated against canonical `ToolResultV1` schema with `FindingV1` records.

## Invocation & Cache JSON Schemas (Phase 57)

Schemas for `InvocationContext`, `PhysicalTarget`, `CacheDecision`, and cached `ToolResultV1` payloads are validated against Phase 54 schema kernels.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

Rush implements closed-loop resilience, fail-closed security, and physical containment across multi-agent concurrency, persistent memory, and AI-driven patch remediation (Findings R-009, R-010, R-011, R-016):

1. **Capability Locks & Verifier Custody (`rush.mcp_mesh`)**:
   - Callers retain high-entropy capability tokens (`LockCapabilityInput`) delivered exclusively via protected channels (`stdin`, `descriptor`, or sensitive MCP parameters); argv and environment leakage are rejected fail-closed.
   - `MeshLockManager` stores verifier-only records (`LockLeaseRecord`) generated via `rush.io.VerifierRecord` (PBKDF2-HMAC-SHA256, 100k rounds) with monotonic generation counters and `rush.io.PhysicalRoot` containment under `.rush/locks`.
   - Renewal and release verify caller capability in constant time (`hmac.compare_digest`); wrong, low-entropy, or stale tokens fail closed.

2. **CAS Map Transactions & Persistent Memory (`rush.memory`)**:
   - `CASMapTransaction` enforces optimistic concurrency with monotonic version numbers and atomic file replacement (`rush.io.AtomicFile`) using sanitized JSON payloads (`SanitizedJsonValue`).
   - Store states are truthfully separated into distinct typed exceptions: `StoreNotFoundError`, `StoreCorruptionError` (retaining raw bytes and SHA-256 digest), `StoreValidationError`, `StoreIOError`, and `CASConflictError` (exhausted retries fail closed).
   - `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` eliminate silent empty dict fallbacks.

3. **Atomic Checkpoint Journals & Corrupt Evidence (`rush.memory.checkpoint_journal`)**:
   - Session checkpoints are written via `rush.io.AtomicFile` using explicit schema version `1.0.0`.
   - Corrupted or unparseable checkpoint files are preserved on disk, cryptographically digested with SHA-256, and surfaced in `list_checkpoints()` with status `corrupt`.

4. **Contained Patch Verification & Atomic Rollback (`rush.patch`)**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Failed promotion or verification triggers automatic atomic rollback (`git reset --hard`, `git clean -fd`) restoring the working directory to its exact pre-patch commit and state.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### in-toto Statement v1 / SLSA Provenance v1 Schema
Pinned schema following `https://in-toto.io/Statement/v1` and `https://slsa.dev/provenance/v1` with `ProvenanceDraft` container.
