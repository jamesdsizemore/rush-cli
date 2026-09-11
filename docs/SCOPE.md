# Rush Scope & Architectural Boundaries

This document defines what is explicitly in-scope and out-of-scope for Rush CLI and its Model Context Protocol (MCP) server.

---

## 1. Explicitly In-Scope

- **Unified CLI & MCP Front Door**: Exposing catalogued tools and FastMCP tools (`rush_<name>`) with identical implementations.
- **Dynamic Engine Discovery**: Discovering catalogued engine adapters from the environment with non-fatal `skipped` reporting for absent tools.
- **Normalized Canonical Findings**: Returning stable SHA-256 fingerprints, file coordinates, and standardized severity across all linters, security scanners, and test runners.
- **Automated Secret Redaction**: Masking tokens, passwords, and private keys as `[REDACTED]` in output.
- **Execution Permission System**: Gating slow, network, download, build, browser, and artifact-write operations behind explicit invocation flags (`--allow-*`).
- **Subprocess Isolation**: Executing external tools with `stdin=DEVNULL`, `shell=False`, and timeout limits to safeguard MCP stdio transports.
- **Dual-Mode Operation**: Importing structured reports (JSON/XML/SARIF) or executing live engine runners.

---

## 2. Explicitly Out-of-Scope

- **Engine Bundling**: Rush does not bundle external binaries (Node.js, Go, Rust, Java, or C++ executables) or download them at runtime.
- **Remote Network Daemon**: Rush is not an HTTP API, background daemon, or hosted service. MCP communication occurs strictly over local stdio pipes.
- **Destructive Auto-Fixing by Default**: Inspection commands are read-only. Formatting without `--check` is an intentional, explicit action.
- **Automated Git Mutation**: Rush does not commit, create Git tags, rewrite history, or push branches to remote repositories.

See [v0.2 Scope Specification](V0_2_SCOPE.md) and [Design Principles](DESIGN_PRINCIPLES.md).

## Physical Scope & Target Containment (Phase 57)

Target paths are resolved under `rush.io.PhysicalRoot`. Directory junctions, symlinks pointing outside the workspace, and parent traversals (`..`) are rejected fail-closed with `ScopeWideningError`. `.rush/memory.db` (Phase 61's unified `TypedArtifactStore`) is a fixed repository-relative path under this same containment boundary, not user-relocatable outside the workspace.

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
### Build Artifacts & Provenance Scope (Phase 59)
Exported attestation files must be written within workspace boundaries under `rush.io.PhysicalRoot` and require explicit `artifact_write` permission.
