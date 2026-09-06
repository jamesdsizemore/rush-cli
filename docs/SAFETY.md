# Safety overview

## Bounded provider handoff

Provider resume is opt-in, projection-limited, and non-retrying. OmniRoute uses one fixed loopback API request and validates semantic completion without retaining its response. `9router_cli` runs Codex through fixed local 9Router with a child-process-only credential, no model argument, and no output retention. Z.AI is deferred without invocation. There is no automatic provider routing, OAuth flow, or profile mutation.

Rush is designed to make the safe action the default.

- **No implicit installs.** Missing optional engines return `skipped`.
- **No silent source rewrite.** Review/check commands are read-only; formatter mutation is an explicit path and `--check` is available.
- **No hidden publication.** Release is dry-run; publication execution is intentionally unavailable.
- **No history rewrite.** Commit-message checking never changes Git.
- **No network service.** MCP is local stdio only.
- **Explicit execution permissions.** Browser, slow, network, download, build, and artifact-write operations require explicit permission flags (`--allow-*`) and report structured `metadata.execution`.
- **No model marketing beyond implementation.** Review is deterministic; Graft is explicit; `--llm` makes no provider call.
- **No secrets in normalized logs/results.** Obvious secret assignments are redacted, but raw external tool behavior still deserves care.
- **No automatic coordination recovery.** Continuity may surface local ownership, stale evidence, merge conflicts, and redacted recovery receipts, but it never unlocks, merges, replays, or retries on the caller’s behalf.
- **No historic instruction promotion.** Session handoff stores historic-instruction presence only as quarantined evidence; it never becomes a current directive.
- **No silent stale replay.** Restore recomputes declared dependency hashes and labels changed or missing dependencies `stale`; legacy checkpoints remain `unknown` rather than being migrated automatically.
- **Autonomous Agent Safety & Worktree Sandboxing.** Dangerous shell commands (`rm -rf`, `drop table`, `reset --hard`) are intercepted via `rush guard check-cmd`; filesystem writes are strictly confined to workspace boundaries via `rush guard check-path`; AI remediation patches run in isolated Git worktree sandboxes with circuit breakers.
- **Subagent Acyclic Invocations.** Hierarchical agent execution trees are validated to guarantee bounded call depth and acyclic DAG topology.

```mermaid
flowchart TD
  A[Request / Agent Command] --> B{Safe Command & In-Bounds Path?}
  B -- no --> C[Intercept & Block Execution]
  B -- yes --> D{Ordinary local check?}
  D -- yes --> E[Run applicable installed engine]
  D -- no --> F{Explicit granted permission?}
  F -- no --> G[Return skipped / refuse]
  F -- yes --> H[Run bounded capability in Worktree Sandbox]
  E --> I[Normalize and redact result]
  H --> I
```

Read [Permissions](safety/permissions.md), [Privacy](safety/privacy-and-data-handling.md), and [Security model](safety/security-model.md).


## Context Safety, Grounding & Secret Redaction (Phases 41–43)
* **Secret Redaction**: `PackageLinter` and all Rush transports redact keys as `[REDACTED]`.
* **Phantom Package Defense**: `GroundingVerifier` parses AST imports against `sys.stdlib_module_names` and `importlib.metadata.distributions()` to block supply-chain typosquatting and hallucinated libraries.
* **Failure Ledger**: `FailureLedger` records failed patch AST fingerprints in `.rush/memory/failures.db` to prevent repetitive error loops.

## Sanitization & Write Boundary Invariants (Phase 53)
- **Deep Recursive Redaction**: `sanitize_value` applies recursive masking to all strings, sequences, and dictionary keys/values across CLI, MCP, and exported reports.
- **Fail-Closed Type Safety**: Unrecognized object instances cannot leak raw state; they fail closed with `[UNSUPPORTED_TYPE:<name>]`.
- **Pre-Truncation Guarantee**: Subprocess outputs are completely sanitized before length caps are enforced, eliminating secret fragments at truncation seams.
- **Write-Boundary Shielding**: Every persistent writer (governance rules, mesh locks, audit logs, patch memory, session flights, preferences, invariant graphs, and report artifacts) runs sanitization before disk writes.
- **Resilient Diagnostics**: `NdjsonHandler` safely formats exception tracebacks with credential masking and guarantees structured error fallback rather than swallowing diagnostic records.

## Fail-Closed Schema Validation & Boundary Isolation (Phase 54)
- **Downstream Schema Verification**: Tool results run Phase 54 schema validation downstream of Phase 53 sanitization, guaranteeing that structurally invalid findings or malformed statuses are caught before emission.
- **Fail-Closed Result Normalization**: Invalid results raise structured `ValidationErrorV1` records with standard error codes (`MISSING_REQUIRED_KEY`, `INVALID_TYPE`, `INVALID_STATUS`, `INVALID_TIMESTAMP`, `INVALID_SEVERITY`).
- **Operation Isolation**: Public operations are partitioned into `tool`, `admin`, and `service` domains. Service operations (e.g. MCP transport initialization) are prohibited from returning wrapped tool results, maintaining protocol security.

## Physical Containment & Durable Atomic Replacement (Phase 55)
- **Physical Boundary Enforcement**: Workspace paths are validated by `PhysicalRoot` to defeat symlink escapes, parent traversal, and Windows junction/reparse points.
- **Durable Atomic Replacement**: Files written via `AtomicFile` execute in destination directories using `.rush_tmp_` prefix with explicit `flush()` and `os.fsync()` before rename.
- **Old-or-New Destination Guarantee**: Destination files are guaranteed to remain in either their original valid state or new valid state; partial writes are wiped via manager-owned cleanup.

### Plugin Execution Safety & Fail-Closed Boundaries (Phase 56)
- External plugins run under fail-closed verification: any missing trust record, altered byte, symlink escape, or unsupported secret channel denies execution and spawns zero child processes.
- Process command lines and environment tables never contain sensitive credentials.
- All plugin outputs are parsed, sanitized via redactor, and adapted to canonical `ToolResultV1`.

## Single Execution Boundary and Fail-Closed Egress (Phase 57)

- **Zero Runtime TypeError Retries**: Callables are adapted once during registration. If an operation raises an internal `TypeError` after side effects, the error propagates directly without retry.
- **Provider Egress Truthfulness**: The `review_kind = "llm"` label is assigned strictly after receiving a non-empty, schema-valid response from an approved HTTPS origin. Network failures, timeouts, or permission denials fall back to heuristic reviews or structured error states.

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
### Build Claim Truthfulness & Engine Safety (Phase 59)
Rush guarantees truthful build claims: unsigned provenance drafts are never reported as signed or accredited with SLSA levels. Missing distribution packages fail closed with skipped status. Supported engines cannot pass when all tests are skipped.
