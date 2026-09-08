# Rush with coding assistants

## Provider-resume parity

MCP `rush_continuity` `provider_resume` uses the same shared operation as the CLI. `claude_code`, `codex_cli`, `antigravity_cli`, fixed-loopback `omniroute_api`, and `9router_cli` are implemented, and network permission is explicit. `9router_cli` runs Codex through fixed local 9Router with a child-process-only credential and no model argument. `9router_api` remains unavailable; Z.AI is deferred without process or credential access.

## Session continuity

MCP exposes the catalogued `rush_continuity` tool with `path`, `operation` (`save`, `list`, or `restore`), optional `name`/`files`, and `allow_cache_write`. It returns the same canonical object as `rush session`; saving without the explicit boolean permission returns `skipped` and does not create a checkpoint.

## Memory (Phase 61)

MCP exposes the catalogued `rush_memory` tool with `operation` (`ask`, `write`, `promote`, `list`, `recall`, `maintain`) over the unified `TypedArtifactStore`. `ask`, `list`, and `recall` require a non-empty `session_allowlist` and apply the same content defenses. `write`, `promote`, and `maintain` require `allow_cache_write: true`; denied calls return `status="skipped"`. Maintenance operates on the repository selected by `path`, including its lock and grounding checks.

A compatible coding assistant can launch Rush as a local child process and ask it to run the same checks available in the terminal. MCP is the protocol; stdio is the local pipe used to carry requests and results.

```mermaid
sequenceDiagram
  participant Assistant
  participant Rush as rush mcp serve
  participant Engine as Optional engine
  Assistant->>Rush: tool call on stdin
  Rush->>Engine: contained local process, stdin detached
  Engine-->>Rush: captured report
  Rush-->>Assistant: ToolResult on stdout
  Rush-->>Assistant: diagnostics on stderr only
```

No port opens. Rush does not become a background network daemon. Configure a client using [MCP client setup](integrations/mcp-client-setup.md), then use prompts from [Working with AI agents](user-guide/working-with-ai-agents.md).

The assistant does not gain a working model review through Rush: default review remains deterministic and `--llm` can call a configured provider.

## Transport Purity & Response Sanitization (Phase 53)
- **Stdout Invariant**: `sys.stdout` carries only valid JSON-RPC frames during `rush mcp serve`. Logging, progress indicators, and diagnostics are strictly confined to `sys.stderr`.
- **Fail-Safe Diagnostics**: Diagnostic errors emitted to `sys.stderr` are serialized as structured NDJSON records with fully formatted, credential-redacted stack traces. If formatting encounters an error, a structured fallback line is written so diagnostics never silently vanish.
- **Recursive Response Sanitization**: All `ToolResult` dictionaries and MCP responses are sanitized via `sanitize_value`, ensuring that secrets and API keys are redacted from both values and nested keys.

## Operation Taxonomy & Schema Kernel Integration (Phase 54)
- **Tool Operation Separation**: Tool operations (`kind = "tool"`, e.g. `rush_lint`, `rush_security`) return validated `ToolResultV1` structures compliant with schema version `1.0.0`.
- **Protocol Frame Integrity**: Service and protocol-level operations (`kind = "service"`, e.g. `mcp.initialize`, `mcp.ping`, `mcp.list_tools`) return raw protocol frames without `ToolResultV1` wrapping. `ServiceOperationAdapter` enforces this separation fail-closed.
- **Admin Operation Routing**: Admin commands (`kind = "admin"`, e.g. cache purges, info queries) return typed operation envelopes or direct status payloads.

## Next

Use [client setup](integrations/mcp-client-setup.md) and the [tool reference](reference/mcp-tool-reference.md).

## Workspace Physical Containment for MCP Tools (Phase 55)
- **Path Containment Invariant**: All MCP tools operating on local file paths are validated against `PhysicalRoot` to defeat symlink path traversal and Windows reparse point escapes.
- **Atomic Persistence**: Server-side session and scratch writes utilize `AtomicFile` to eliminate race conditions and corrupted partial files during tool execution.

### Plugin Execution Security under MCP (Phase 56)
Plugin executions initiated via MCP administrative endpoints enforce user-owned ledger authorization and snapshot integrity. Cloned repository receipts are strictly rejected as non-authorizing evidence.

## Dual-Transport Parity and Immutability (Phase 57)

FastMCP tools in Rush achieve 100% contract parity with the CLI:
- Every core tool call is routed through `resolve_invocation(request, transport="mcp")`.
- MCP tool handlers receive frozen copies of declared configuration, preventing mutable configuration leakage.
- All core tools emit canonical `ToolResultV1` schemas across both CLI and MCP.

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
   - Current rollback uses broad `git reset --hard`/`git clean -fd` and can destroy unrelated changes. It does not restore an exact pre-invocation index/worktree. Status: planned — bounded restoration in P64-01/P64-04, [Phase 64 runtime plan](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md); [application review](reports/phase-64-66-application-review.md) F01/F43.

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### Provenance & Engine Tools (Phase 59)
- `tool.attest`: Generates truthful in-toto v1 SLSA provenance unsigned drafts with real artifact digests.
- `service.engines`: Engine discovery reflecting deterministic taxonomy.
