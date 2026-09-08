# Privacy and data handling

## Recoverable omission privacy

Before an omitted context payload is retained for CCR recovery, Rush applies the same value redaction boundary used for returned context. The recovery handle is local; mined mistake rationale is redacted and stored with a `trust_tier` (`DERIVED` — Phase 61's unified typed-artifact schema, never `STATED` on entry), never promoted to instruction authority.

## Provider-resume projection

Continuity sends only current goal, open work, and freshness to a supported CLI or fixed local provider route. It excludes historical instructions, transcripts, failed patches, credentials, and provider output; those values are neither returned nor persisted. `9router_cli` uses `RUSH_9ROUTER_API_KEY` only as a child-process `OPENAI_API_KEY` and sends no model argument. Z.AI is never invoked.

## Local behavior

Rush reads the target and invokes installed local engines. It has no telemetry implementation. MCP uses stdio; the separate dashboard starts a loopback HTTP server with open Phase 66 defects. Human output goes to CLI stdout; MCP stdout is protocol-only; NDJSON logs go to stderr.

Continuity checkpoints stay local under `.rush/`. Before persistence, Rush redacts secret-shaped values and stores only a bounded handoff receipt: current goal/open work, dependency hashes, historic-instruction presence, and a failure receipt. It does not persist provider credentials, raw transcripts, historic-instruction text, or failed patches. As of Phase 61, every write to the unified `TypedArtifactStore` (`.rush/memory.db`) runs `sanitize_value()` inside `write()` itself — a caller cannot bypass redaction by forgetting to call it.

## External engines

An engine is a separate program. Some dependency scanners may need advisory data or package metadata; Rush cannot make a universal offline promise for third-party tools. Contained adapters disable known downloads/remote references where their contract requires it, such as Checkov external modules and Spectral remote references.

## Model behavior

Default review is deterministic. `--use-graft` explicitly requests local Graft context. `--llm` can send findings to a configured Anthropic/OpenAI provider; it falls back to heuristic results when no valid completion is returned.

## Secrets

Normalized finding messages and logs redact obvious secret assignments, and secret findings should not include captured values. Redaction is defense in depth, not permission to publish raw external scanner output. Rotate any real exposed credential.

## Review evidence retention

Rush does not operate a durable evidence store or upload review data. Direct
review returns local source-location evidence, deterministic fingerprints, and
freshness metadata in the current result only. A supplied report remains a
user-owned local input; Rush neither writes a review baseline by default nor
uses Git history to infer scope. See [scanner governance](../maintainers/scanner-governance.md)
for maintainer retention, error-budget, and deprecation policy.

## End-to-End Recursive Sanitization (Phase 53)

The shared sanitizer is a defense-in-depth mechanism. Custom token-outline MCP output still bypasses it (F07); this is not universal secret-exclusion proof:
- `sanitize_value` redacts secrets from dictionary values AND keys.
- Dict key collision suffixing ensures no data loss occurs when separate keys share redaction targets.
- Pre-truncation subprocess handling ensures secrets cut off by character limits are redacted before truncation.
- Output formats (CLI, MCP, SARIF, HTML, Cache) and persistent writers (state, mesh, logs, artifacts) enforce deep sanitization.

## Non-Recoverable Capability Verification (Phase 55)

All persistent capabilities, lock identifiers, and trust tokens are stored using `rush.io.VerifierRecord`. This uses PBKDF2-HMAC-SHA256 (100,000 iterations, 32-byte salt) and constant-time verification. Raw capabilities are never stored on disk, eliminating token disclosure in state files.

### Plugin Credential Confinement (Phase 56)
Secrets are strictly excluded from process command lines and environment blocks. Ephemeral descriptors and stdin payloads provide point-to-point credential delivery.

## Cache Storage & Prompt Privacy (Phase 57)

Data written to the invocation cache is sanitized prior to persistence. Prompts sent to LLM providers are guarded against unintended redirect exfiltration.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

The following component contracts are not whole-application guarantees. Checkpoint/governance symlink escapes, sandbox fallback, destructive cleanup and custom-output redaction defects remain open; see [Known issues](../KNOWN_ISSUES.md).

1. **Capability Locks & Verifier Custody (`rush.mcp_mesh`)**:
   - Callers retain high-entropy capability tokens (`LockCapabilityInput`) delivered exclusively via protected channels (`stdin`, `descriptor`, or sensitive MCP parameters); argv and environment leakage are rejected fail-closed.
   - `MeshLockManager` stores verifier-only records (`LockLeaseRecord`) generated via `rush.io.VerifierRecord` (PBKDF2-HMAC-SHA256, 100k rounds) with monotonic generation counters and `rush.io.PhysicalRoot` containment under `.rush/locks`.
   - Renewal and release verify caller capability in constant time (`hmac.compare_digest`); wrong, low-entropy, or stale tokens fail closed.

2. **CAS Map Transactions & Persistent Memory (`rush.memory`)**:
   - `CASMapTransaction` enforces optimistic concurrency with monotonic version numbers and atomic file replacement (`rush.io.AtomicFile`) using sanitized JSON payloads (`SanitizedJsonValue`).
   - Store states are truthfully separated into distinct typed exceptions: `StoreNotFoundError`, `StoreCorruptionError` (retaining raw bytes and SHA-256 digest), `StoreValidationError`, `StoreIOError`, and `CASConflictError` (exhausted retries fail closed).
   - `PreferenceStore`, `InvariantGraph`, and `MerkleInvalidator` eliminate silent empty dict fallbacks.

3. **Atomic Checkpoint Journals & Unified Store Persistence (`rush.memory.checkpoint_journal`)**:
   - `checkpoint_journal.py` is a thin compatibility view over `TypedArtifactStore` (`rush.memory.store`, Phase 61): `save_checkpoint()`/`restore_checkpoint()` write/read each checkpoint as one `MemoryArtifact` row (`family="handoff"`, `subject="active_context"`); canonical data lives in `.rush/memory.db`, not a per-checkpoint JSON file.
   - `save_checkpoint()` still writes a physical `.json` artifact via `rush.io.AtomicFile` and returns its `Path` (`dest.exists()` holds), preserving the pre-Phase-61 contract for existing callers; explicit schema version `1.0.0` is unchanged.
   - Corrupted or unparseable checkpoint files are preserved on disk, cryptographically digested with SHA-256, and surfaced in `list_checkpoints()` with status `corrupt` — unchanged by the Phase 61 migration.

4. **Contained Patch Verification & Atomic Rollback (`rush.patch`)**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Current rollback uses broad reset/clean and can discard unrelated work. Exact restoration remains planned in [P64-01/P64-04](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md); [F01/F43](../reports/phase-64-66-application-review.md) remain open.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
