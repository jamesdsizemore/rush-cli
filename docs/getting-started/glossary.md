# Glossary

**Coding assistant** — A development tool that can inspect or change code. Some assistants can launch Rush through MCP.

**Engine** — An optional helper program Rush knows how to run, such as Ruff, ESLint, pytest, or pip-audit. Rush does not install engines.

**Finding** — One reported issue with a path, rule, severity, message, and optional location.

**Heuristic review** — A deterministic rule-based inspection. It is not human review and not an AI model judgment.

**MCP (Model Context Protocol)** — A standard that lets a compatible coding assistant launch a local tool and call named operations. Rush supports local stdio MCP only.

**Optional check** — A check that can be skipped when its engine, project files, evidence, or explicit permission is absent.

**Result status** — `ok`, `warn`, `fail`, `error`, or `skipped`. These describe the command result, not the developer.

**Rush catalog** — Developer term for the source metadata that defines Rush's known commands and engines. Users normally only need `rush --help`.

**SBOM (software bill of materials)** — A machine-readable inventory of software components, usually used for supply-chain review.

**Semantic drift** — A test-risk pattern where a self-healing UI locator binds to a different element and hides a broken user workflow. Rush's related command is experimental and guarded.

**stdio** — Standard input/output pipes used for local process communication. Rush's MCP mode reserves stdout for protocol messages.

**ToolResult** — Rush's consistent result object (`ToolResultV1`), containing 8 canonical fields (`schema_version`, `tool`, `engine`, `status`, `duration_ms`, `timestamp`, `summary`, `findings`). See [Result reference](../reference/result-reference.md).

### Context Intelligence Terms
* **TOON**: Ultra-compact pipe-table wire format.
* **CCR**: Context Compression & Restoration chunk storage.
* **HalluGuard**: Static AST import grounding verifier.
* **Ship Gate**: 7-vector pre-flight release readiness cockpit.

### Phases 44–46 Terms
* **Blast Radius**: Downstream impact analyzer.
* **ArchGuard**: Architectural boundary layer linter.
* **Context Packer**: Token-budgeted context assembler.
* **Gain HUD**: Real-time token savings terminal dashboard.


### Phase 47 Terms
* **Test Healer**: Autonomous flaky test repair tool.
* **API Differ**: Public signature breaking change detector.



### Phase 48 Terms
* **DB Drift Auditor**: Database schema drift linter.
* **Complexity Decomposer**: Spaghetti function refactor engine.
* **Type Synthesizer**: Runtime type guard generator.



### Phase 49 Terms
* **Trace Scanner**: Spec requirement auditor.
* **Flight Recorder**: Session replayer.
* **Swarm Merge**: 3-way AST conflict solver.



### Phase 50 Terms
* **SLSA Attestation**: Cryptographic build provenance statement.
* **License Matrix**: Dependency license scanner.
* **IAM Audit**: Least-privilege cloud policy generator.

### Phase 54 Terms
* **ToolResultV1**: Canonical typed schema kernel enforcing 8 required fields, ISO 8601 UTC timestamps, and standardized severity levels.
* **FindingV1**: Structured finding model with strict path, line, message, and severity contracts.
* **Operation Registry**: Reconciled taxonomy partitioning operations into `tool`, `admin`, and `service` domains.

### Phase 55 Terms
* **AtomicFile**: File writer ensuring changes are written atomically and durably to disk or fail completely without leaving corrupted partial files.
* **PhysicalRoot**: Security boundary ensuring commands and tools cannot read or write files outside the project directory.
* **VerifierRecord**: Security record that proves authorization without saving raw passwords or secret tokens.

- **Plugin Trust Ledger**: A secure file on your machine (`~/.rush/plugin_trust_ledger.json`) tracking which custom tools you have approved to run.
- **Snapshot Directory**: A protected copy of your plugin scripts where Rush runs them safely without risk of accidental changes.

## Phase 57 Concepts

- **Invocation Context**: The complete set of inputs, configurations, and permissions for a tool run.
- **Physical Target**: A file or directory contained safely within the project boundary.
- **Cache Decision**: Determination of whether a result can be retrieved from or saved to cache.

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

3. **Atomic Checkpoint Journals & Unified Store Persistence (`rush.memory.checkpoint_journal`)**:
   - `checkpoint_journal.py` is a thin compatibility view over `TypedArtifactStore` (`rush.memory.store`, Phase 61): `save_checkpoint()`/`restore_checkpoint()` write/read each checkpoint as one `MemoryArtifact` row (`family="handoff"`, `subject="active_context"`); canonical data lives in `.rush/memory.db`, not a per-checkpoint JSON file.
   - `save_checkpoint()` still writes a physical `.json` artifact via `rush.io.AtomicFile` and returns its `Path` (`dest.exists()` holds), preserving the pre-Phase-61 contract for existing callers; explicit schema version `1.0.0` is unchanged.
   - Corrupted or unparseable checkpoint files are preserved on disk, cryptographically digested with SHA-256, and surfaced in `list_checkpoints()` with status `corrupt` — unchanged by the Phase 61 migration.

4. **Contained Patch Verification & Atomic Rollback (`rush.patch`)**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Failed promotion or verification triggers automatic atomic rollback (`git reset --hard`, `git clean -fd`) restoring the working directory to its exact pre-patch commit and state.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.

### Phase 61 Terms
* **Typed Artifact**: `MemoryArtifact`, one row of the unified `TypedArtifactStore` schema.
* **Trust Tier**: `STATED`/`DERIVED`/`EXTERNAL_WRITE`/`IMPORTED` — new writes never enter at `STATED`.
* **Write-Promotion Rule**: the composed screen (ALLOW/REDACT/BLOCK + regex + schema + grounding + corroboration) a record must pass to reach `STATED`.
* **Transport Dispatcher**: per-tool cross-tool memory-handoff tier selector (native SDK → ACP → dedicated-file).
