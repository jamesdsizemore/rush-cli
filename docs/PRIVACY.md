# Privacy & Data Handling Guarantees

## Provider-resume data boundary

Only `current_goal`, `open_work`, and `freshness` are projected to a supported CLI or fixed local provider route. Historic instructions, transcripts, failed patches, credentials, and provider output are excluded and no provider response is persisted. `9router_cli` passes `RUSH_9ROUTER_API_KEY` only as its child Codex process's `OPENAI_API_KEY`, never records it, and sends no model argument.

Rush is strictly local-first. It contains no telemetry, analytics tracking, external data collection, or remote reporting servers.

Session handoff state is also local: secret-shaped values are redacted before session-memory and checkpoint persistence; provider credentials, raw historic instructions, raw transcripts, and failed patches are excluded from the receipt. Redaction is a safety layer, not permission to store credentials.

---

## 1. Core Privacy Invariants

1. **Local-Only Execution**: Rush runs locally, but explicitly requested provider review and external engines can make network calls. There is no Rush-hosted telemetry service; this does not mean every engine is offline.
2. **Zero Telemetry**: Rush does not phone home, track usage statistics, or log user behavior.
3. **Automated Secret Redaction**: Any secret, password, private key, or credential identified in scanner findings or error logs is masked as `[REDACTED]` prior to emission.
4. **Offline Default Posture**: Engine network behavior depends on the selected route. AI eval lacks required grants (F08); `review --llm` can send findings to a configured provider. Do not infer offline execution from a generic tool label.
5. **No Stealth Model Invocations**: The `rush review --llm` option can call a configured provider and send findings. Default review uses deterministic local heuristics.

---

## 2. Model Context Protocol (MCP) Privacy

When Rush runs as a local stdio MCP server for an AI coding assistant:
- The conversation occurs entirely through local standard input/output (`stdio`) pipes on the host machine.
- Rush does not open any network ports, HTTP listeners, or WebSocket servers.
- The AI assistant only receives the structured `ToolResult` JSON payload explicitly requested by the assistant.

See [Privacy and Data Handling Guide](safety/privacy-and-data-handling.md) and [Security Model](safety/security-model.md).

---

## 3. Serialization & Persistent Storage Privacy (Phase 53)

The shared sanitizer provides the following mechanisms. Pattern-based redaction is not proof that no secret can escape; custom token-outline MCP output still bypasses the boundary (F07), pending P64-05:
1. **Recursive Sanitizer Kernel**: `sanitize_value` redacts credentials, bearer tokens, API keys, and sensitive URL credentials from both dictionary keys and values.
2. **Immutable Input Isolation**: Data passed to execution operations is never modified in-place; sanitization occurs strictly on detached serialization copies.
3. **Loss-Visible Key Collisions**: Colliding redacted dictionary keys are preserved deterministically via suffixing rather than discarded, preventing silent state corruption while logging collision metadata.
4. **Clean Persistent State**: Audit logs, SQLite patch memory, session flight logs, preferences, and generated artifacts (SARIF, HTML, in-toto statements, IAM policies) are sanitized before writing to disk. As of Phase 61, every write to the unified `TypedArtifactStore` (`.rush/memory.db`) runs through `sanitize_value()` inside `TypedArtifactStore.write()` itself — a caller cannot bypass redaction by forgetting to call it (Invariant 2, `docs/ARCHITECTURE.md`'s "Phase 61 Architecture" section).
5. **Redacted Diagnostics**: Stderr NDJSON logs redact secrets from both log messages and full exception tracebacks, ensuring diagnostic clarity without credential exposure.

---

## 4. Schema Normalization & Operation Boundary Privacy (Phase 54)

1. **Sanitization-First Serialization**: In Phase 54, `serialize_tool_result()` executes secret sanitization (Phase 53) before structural schema validation, preventing un-sanitized data from ever reaching serialized envelopes.
2. **Canonical Finding Normalization**: Findings are coerced into immutable `FindingV1` records with normalized file paths, line coordinates, and standardized severity levels (`info`, `warning`, `error`), scrubbing unpredictable engine error fields.
3. **Service Protocol Separation**: Service operations (like MCP connection initialization) run through isolated `ServiceOperationAdapter` layers, ensuring raw communication frames remain separate from tool result data.

## 5. Non-Recoverable Capability Privacy (Phase 55)

1. **One-Way Verifier Storage**: Stored capabilities, authorization tokens, and lock proofs are persisted as `VerifierRecord` hashes derived via PBKDF2-HMAC-SHA256 (100k rounds, 32-byte salt).
2. **Zero Raw Capability Exposure**: `VerifierRecord` instances contain zero raw token information, omit raw values from `to_dict()` and `repr()`, and perform verification in constant time via `hmac.compare_digest`.
3. **Entropy Validation**: Capabilities must have Shannon entropy >= 2.5 bits/symbol and length >= 16 characters, preventing predictable or low-entropy secrets.

### Plugin Data Handling and Secret Invisibility (Phase 56)
- Secrets referenced by plugins (`secret:<ID>`) are resolved ephemerally at launch and piped via protected descriptors or stdin.
- Child process `argv` and environment are scrubbed; process listings (`ps`, `/proc`) cannot observe secrets.
- Plugin stdout and stderr are sanitized by `rush.safety.redactor.sanitize_value()` before inclusion in results or logs.

## Invocation & Cache Data Hygiene (Phase 57)

- **Cache Sanitization**: All data written to or retrieved from `ResultCache` is recursively sanitized via `rush.safety.redactor.sanitize_value` and validated against `ToolResultV1`.
- **Egress Redirection Containment**: When making remote AI provider requests, HTTP redirects to unauthorized or unapproved origins immediately strip sensitive headers and terminate execution, preventing token exfiltration.

## Phase 58 Architecture: Capability Locks, CAS Memory, and Fail-Closed Patch Verification

These Phase 58 component contracts are not whole-application safety guarantees. Checkpoint symlink reads, governance symlink writes, sandbox fallback and patch cleanup remain open ([application review](reports/phase-64-66-application-review.md) F03–F05/F43; [Phase 64 runtime plan](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) P64-03/P64-04).

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
   - Current rollback uses broad `git reset --hard`/`git clean -fd` and can destroy unrelated changes. It does not restore an exact pre-invocation index/worktree. Status: planned — patch-sandbox restoration in P64-04, [Phase 64 runtime plan](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md); [application review](reports/phase-64-66-application-review.md) F43.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### Provenance Data Scrubbing (Phase 59)
All provenance drafts and attestation metadata are sanitized via `rush.safety.redactor.sanitize_value` prior to serialization, ensuring zero private developer paths or secrets leak into public statements.
