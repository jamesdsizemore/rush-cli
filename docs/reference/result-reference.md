# Result and exit-code reference

## Context omission outcomes

`context_pack` returns `skipped` when the mandatory selected evidence exceeds its budget. If it records `metadata.context_envelope.recovery.state: "available"`, use the accompanying local CCR handle with `context_retrieve`. An absent chunk is `skipped`, never an invented result.

## Provider-resume outcomes

Provider resume returns canonical `ToolResult`: `ok` only for a successful supported CLI process; `skipped` for deferred, unavailable, denied, or `credential_unavailable` routes; and `error` for a failed process. The result metadata names only provider ID, transport, endpoint class where fixed, and state; it never includes provider stdout/stderr, credentials, a 9Router model, or full historical handoff content.

## Continuity outcome rules

The `continuity` tool uses `ok` for successful save/list/restore and empty lists, `skipped` for a denied save or absent checkpoint, and `error` for invalid operations or checkpoint names. `metadata.execution` shows that only the save operation requested cache-write permission. Save/restore additionally return `metadata.handoff`: redacted current goal/open work, `historic_instruction` as quarantined `historical_evidence`, dependency snapshots with `freshness`, and a failure receipt or tombstone; CLI and MCP use the same statuses and fields.

Context operations use `ok` for a bounded pack or recovered handle and `skipped` for insufficient budget or a missing handle. Their `metadata.context_envelope` identifies selected evidence, local token values, omissions, and recovery state.

Coordination uses `ok` only for available ownership, conflict-free preview, or available recovery evidence. It uses `skipped` for held/stale ownership, overlapping merge edits, and missing/corrupt replay evidence. `metadata.coordination` is receipt data only and contains no source merge, failed patch, or executable replay event.

Every CLI and MCP operation returns the same canonical ToolResult shape.

```json
{
  "tool": "lint",
  "engine": "ruff+eslint",
  "engine_version": null,
  "status": "warn",
  "duration_ms": 41,
  "summary": "lint [ruff+eslint]: 2 finding(s)",
  "findings": [
    {
      "fingerprint": "stable-derived-sha256",
      "path": "src/app.py",
      "line": 8,
      "column": 1,
      "end_line": null,
      "end_column": null,
      "rule": "F401",
      "severity": "warn",
      "message": "imported but unused",
      "fix": null,
      "provenance": "lint/ruff",
      "freshness": "unknown"
    }
  ],
  "raw": null
}
```

## ToolResult fields

| Field | Meaning |
|---|---|
| `tool` | Rush command name. |
| `engine` | Producing helper or `+`-joined aggregate; may be `null`. |
| `engine_version` | Detected version when available; may be `null`. |
| `status` | `ok`, `warn`, `fail`, `error`, or `skipped`. |
| `duration_ms` | measured elapsed milliseconds. |
| `summary` | concise explanation intended for people and automation logs. |
| `findings` | normalized issue objects in deterministic order. |
| `raw` | bounded engine-native detail or `null`; do not build stable automation around engine-specific raw shapes. |
| `metrics` | optional numeric/string measurements. |
| `artifacts` | optional paths to generated/imported artifacts. |
| `metadata` | optional execution context such as dry-run, Graft state, or `execution` metadata (`mode`: `imported`/`executed`/`skipped`, `requested_permissions`, `granted_permissions`, `producer`, `report_path`). Review aggregation records serial mode, child tool/engine/status summaries, and whether skipped/error children make the result partial; it never substitutes a clean status for those child states. |
| `review_kind`, `review_provider` | review-only fields; provider remains null unless the stub path is activated. |

## Finding fields

A finding always has path, line, rule, severity, and message values after normalization. It may include column/end coordinates, a fix description, provenance, a deterministic redaction-safe SHA-256 `fingerprint`, and `freshness`. Direct review findings also carry a local `evidence` source-location packet when no engine/Graft evidence exists; it contains only the already-reported path and line. Direct review evidence is `unknown` unless an internal caller supplies an explicit in-memory fingerprint baseline; then review aggregation labels it `existing` or `new`. Rush exposes no baseline-file write/update command in this release. Messages are redacted for obvious secret assignments and output is bounded.

## Status versus finding severity

Result status describes the whole operation (`ok`, `warn`, `fail`, `error`, `skipped`). Finding severity describes one issue.

In legacy TypedDicts, severities were `"info"`, `"warn"`, `"error"`. Under **Phase 54 (`rush.contracts.results:FindingV1`)**, canonical severities are strictly:
- `info`: informational diagnostic
- `warning`: advisory rule or style issue (replaces `warn`)
- `error`: functional, security, or build failure (subsumes `fail`)

### Legacy Severity Mapping Table
| Legacy Raw Severity | Canonical `FindingV1` Severity | Action |
|---|---|---|
| `"info"` | `"info"` | Identity |
| `"warn"` | `"warning"` | Canonical mapping |
| `"warning"` | `"warning"` | Identity |
| `"error"` | `"error"` | Identity |
| `"fail"` | `"error"` | Canonical mapping |
| Unknown / unmappable | *None* | Raises `ValidationErrorV1(code="INVALID_SEVERITY")` (Zero silent coercion) |

### ToolResultV1 Schema Version & Extension Boundary
`ToolResultV1` strictly requires:
- `schema_version: "1.0.0"`
- Unknown top-level keys are rejected with `ValidationErrorV1(code="UNKNOWN_TOP_LEVEL_KEY")`.
- Non-core fields (`metrics`, `artifacts`, `metadata`, `review_kind`, `review_provider`) reside within `extensions: dict[str, Any]`.

## Phase 50a Result Shapes

- `error-catalog`: `metadata.catalog` contains normalized RFC 7807 problem details dictionaries (`code`, `status`, `title`, `type`, `occurrences`). Exported markdown appears in `artifacts`.
- `license-matrix`: `metrics` records `total_packages`, `allowed_count`, `copyleft_violations_count`, and `manual_review_count`. Copyleft licenses yield `fail` status; unknown or compound licenses yield `warn` status.
- `iam-audit`: `metadata.policy` contains synthesized least-privilege IAM policy statement. Wildcard actions in Terraform emit `iam-wildcard-action` findings with `fail` status.

## Exit codes

| Result | Exit code | Automation meaning |
|---|---:|---|
| `ok` | 0 | completed cleanly |
| `warn` | 1 | completed with advisory evidence |
| `skipped` | 0 | did not run or had nothing applicable; inspect JSON |
| `fail` | 1 | completed and failed criteria |
| `error` | 2 | execution/reporting failure |

Example strict check:

```bash
result="$(rush lint . --json)"
printf '%s\n' "$result"
python -c 'import json,sys; s=json.load(sys.stdin)["status"]; raise SystemExit(0 if s=="ok" else 1)' <<<"$result"
```

Adapt shell syntax to your platform. Preserve the JSON in CI artifacts when it helps debugging, but never publish sensitive raw scanner output.

### Phase 50b Result Metadata
- `metadata.risk_tier`: Overall risk assessment (`"low"`, `"medium"`, `"high"`).
- `metadata.recommended_reviewers`: List of CODEOWNERS matched for the diff.
- `metadata.potential_savings_bytes`: Unreferenced asset byte savings.

### Phase 50c Result Metadata
- `metadata.slsa_predicate`: in-toto v1 SLSA provenance predicate dictionary.
- `metadata.unclosed_resources`: List of unclosed files/connections detected.
- `metadata.heavy_imports`: List of heavy top-level package imports flagged.
- `metadata.benchmark_stats`: Sample statistics (`mean`, `median`, `min`, `max`, `count`).

## Export Artifact Containment & Durability (Phase 55)

When exporting results via `--export-html` or `--export-sarif`, files are verified via `rush.io.PhysicalRoot` and written atomically via `rush.io.AtomicFile`. Destination paths that escape root or contain symlinks are blocked fail-closed.

### Plugin ToolResultV1 Output (Phase 56)
Plugin executions emit `ToolResultV1` with `tool="plugin"`, `engine="<name>"`, and findings adhering to `FindingV1` (`info`, `warning`, `error`).

## Cached ToolResultV1 Shapes (Phase 57)

Cached payloads conform to the canonical `ToolResultV1` schema, ensuring consistent deserialization across cached and uncached executions.

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
### `tool.attest` Result Reference (Phase 59)
Returns `ToolResultV1` with metadata containing `statement` (in-toto Statement v1) and `assurance='unsigned_draft'`.
