# Security Policy & Vulnerability Reporting

## Provider resume

Resume requires `--allow-network`. Native CLI routes use typed argv and discard provider stdout/stderr. Windows batch launchers use a fixed `cmd.exe` profile whose checkpoint-controlled projection is carried only in a per-process delayed-expansion environment variable, never in CMD syntax. OmniRoute uses one fixed localhost HTTP request and discards the response after semantic validation. `9router_cli` copies `RUSH_9ROUTER_API_KEY` only into its Codex child environment at fixed local 9Router and never sends a model argument. Rush does not persist credentials or change provider profiles.

Rush prioritizes code security, execution isolation, and responsible disclosure.

Continuity saves require explicit cache-write permission. A checkpoint records a redacted receipt, not a credential or executable instruction: historic instructions carry a `trust_tier` (`EXTERNAL_WRITE`/`DERIVED`/`IMPORTED` — never `STATED` on entry, Phase 61's unified typed-artifact schema, replacing the earlier binary quarantine flag), and failed attempts resolve only to a redacted ledger receipt or an explicit tombstone.

Coordination inspection is read-only. Held and stale locks, merge conflicts, and replay history are reported as bounded evidence; Rush does not release locks, apply a merge, execute recorded events, or retry failed patches.

---

## 1. The 7 Defensive Controls

These seven intended controls have current exceptions: F01–F08/F43 describe data-loss, containment, output and permission defects. [Known issues](KNOWN_ISSUES.md) links the required Phase 64 repairs; these controls are not blanket guarantees.

1. **Control 1 (Flag-Salted Cryptographic Caching)**: Cache keys incorporate file content hashes and runtime CLI flags (`src/rush/cache.py`), preventing stale result pollution or bypass via command-line manipulation.
2. **Control 2 (Path Boundary Confinement & Monorepo Scoping)**: Tools strictly validate target paths against the repository root (`assert_safe_workspace_path` and `discover_workspaces`), rejecting `..` traversal escapes.
3. **Control 3 (Shell Injection Prevention & Typed Arguments)**: Package installation (`src/rush/tools/setup_wizard.py`) validates package names via strict regex `^[a-zA-Z0-9@_./-]+$` and executes subprocesses with typed argv lists (`shell=False`, `stdin=DEVNULL`).
4. **Control 4 (Binary Integrity & Anti-Shadowing)**: Environment doctor (`src/rush/tools/doctor.py`) checks PATH precedence (virtualenv -> system PATH) and flags binary shadowing vulnerabilities in current working directories.
5. **Control 5 (Dashboard Auth, Loopback Binding, DNS Rebinding & CSRF Protection)**: The stdlib server (`src/rush/dashboard/server.py`) binds to loopback and generates a URL-safe token. Client/server auth and endpoint mismatches, shared class state and prefix-based authority checks remain open (F37/F39/F40); repairs are planned in Phase 66.
6. **Control 6 (Repository Trust Gating)**: Custom script plugins and hooks are blocked in untrusted repository directories by default until explicitly authorized via `rush trust` (`src/rush/plugins/trust.py`), preventing RCE on newly cloned checkouts.
7. **Control 7 (Patch Confinement & XML Session Memory Framing)**: Automated patches (`src/rush/patch_generator.py`) shield sensitive paths (`.git/`, `.env`, `.rush/cache.db`), and multi-turn session history (`src/rush/session_memory.py`) is framed in strict XML boundary tags (`<rush_session_memory>`) with XML escaping to neutralize prompt injection.

---

## 2. Security Architecture Highlights

1. **Subprocess Isolation**: External engines are launched using `stdin=subprocess.DEVNULL`, `shell=False`, and a 120s timeout, preventing arbitrary shell expansion and MCP pipe corruption.
2. **Automated Secret Redaction**: High-entropy strings, API keys, tokens, and credentials identified by secret scanners or stderr logs are masked as `[REDACTED]`.
3. **Execution Permissions**: Destructive, network-accessing, or resource-heavy operations require explicit `--allow-*` permissions.
4. **Offline Safety**: All security adapters default to local, offline analysis.

---

## 2. Reporting a Vulnerability

If you discover a security vulnerability in Rush CLI:
1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately via GitHub Security Advisories or by emailing maintainers.
3. Include a detailed description, steps to reproduce, and a proof of concept.
4. Never include real production secrets, API keys, or private code in vulnerability reports.

See [Security Model](safety/security-model.md), [Incident & Security Runbook](maintainers/incident-and-security.md), and [Permissions](safety/permissions.md).

## Supply Chain & Import Security (Phases 41–43)
`rush hallu-guard` and `rush ship pack` provide static defense against:
1. Typosquatted dependencies and hallucinated package imports.
2. Accidental inclusion of sensitive keys, `.env` files, or certificates in package builds.
3. Risky table-locking SQL migrations in production deployments.

## Architectural Layer Isolation (Phase 46)
`rush arch-guard` prevents sensitive infrastructure code (database clients, crypto keys) from being imported into untrusted presentation or domain layers.


## Safe Ephemeral Sandboxing (Phase 47)
Current `GitSandbox` can fall back to an empty directory after worktree failure (F05); test healing repeats pytest and produces a comment-only patch (F12). Verified isolated repair remains planned in P64-04/P64-12.



## Schema Integrity & Type Safety (Phase 48)
`rush db-drift` currently conflates table columns; `rush strictify` invents overbroad guards (F16/F17). Grounded constraints and table-aware migration comparison remain planned in P64-15.



## Multi-Agent Concurrency & Auditability (Phase 49)
`MeshLockManager` prevents split-brain race conditions when multiple agent processes work in parallel, while `FlightRecorder` provides immutable audit logs of all tool calls and state transitions.



## Polyglot Quality & Security Catalog (Phase 50a)
`rush error-catalog`, `rush license-matrix`, and `rush iam-audit` provide offline static security checks:
1. `rush error-catalog`: Statically indexes raised exceptions across Python, TypeScript, and Rust without executing code, normalizing error codes to RFC 7807 problem details to prevent leaking internal stack traces.
2. `rush license-matrix`: Audits polyglot package dependencies against an SPDX allowlist and flags copyleft risks (GPL, AGPL, LGPL, SSPL) across manifests.
3. `rush iam-audit`: Enforces least-privilege cloud IAM policies from static multi-cloud SDK calls (AWS, GCP, Azure) and detects dangerous wildcard actions (`*`) in Terraform configurations.
Exporting artifacts requires explicit `--allow-artifact-write` permission and strictly validates target paths against directory traversal (`..`).

## Flagship Provenance & Verification (Phase 50b/50c)
`rush attest` produces in-toto Statement v1 / SLSA Provenance v1 unsigned drafts with SHA-256 artifact digests for release builds. Cryptographic signing and builder verification are handled by downstream CI release workflows.

## Phase 50b Security: Read-Only Invariants & Safe PR Cards
- **Read-Only Git Inspection**: `provenance-ai` and `pr-synthesize` only read Git logs and diffs. They never rewrite history or create commits.
- **Zero-Deletion Default**: `dead-asset` never deletes files unless explicit `--prune` and `--allow-artifact-write` are provided with SHA-256 validation.
- **Offline Card Synthesis**: PR cards are generated locally without external GitHub API tokens.

## Phase 50c Security: Honest Provenance & Profiling Safety
- **Honest SLSA Drafts**: In-toto statements clearly state `assurance: unsigned_draft` without fraudulent Level 3 assertions.
- **Dynamic Execution Permission Gates**: Dynamic profiling (`tracemalloc`, `-X importtime`) requires explicit `--allow-slow`.
- **Cache Write Guard**: Benchmark baselines write only under `--allow-cache-write`.
- **Air-Gapped Offline Review**: Local model evaluation never performs outbound HTTP/HTTPS network calls.

## Complete Recursive Sanitization & Safe Diagnostics (Phase 53)
- **Universal Recursive Kernel (`sanitize_value`)**: Enforces deep sanitization across mappings, sequences, strings, and exceptions. Sanitizes dictionary keys as well as values.
- **Deterministic Key Collision Handling**: If secret redaction produces colliding keys, entries are suffixed with `__collision_{i}` to prevent silent loss, and collision metadata is recorded.
- **Fail-Closed Unsupported Objects**: Objects lacking safe serialization produce `[UNSUPPORTED_TYPE:<name>]` instead of disclosing raw internal representations.
- **Pre-Truncation Redaction**: Subprocess stdout/stderr sanitization runs strictly before truncation to prevent secret leakage at slice boundaries.
- **Sealed Serialization & Persistent Boundaries**: Output generators (SARIF, HTML, ResultCache, CLI JSON) and disk writers (governance rules, mesh locks, security audit logs, patch memory, session flights, preferences, invariant graphs, attestations, IAM policies, dead asset manifests, and benchmarks) enforce copy-sanitization prior to emission or disk writes without mutating execution inputs.
- **Fail-Safe Structured Diagnostics**: `NdjsonHandler.emit` formats exception tracebacks with credential redaction and includes a structured fallback handler, guaranteeing stderr log records are never silently dropped. Stdout remains strictly dedicated to JSON-RPC and CLI outputs.

## Physical Containment & Non-Recoverable Capability Invariants (Phase 55)
- **Control 2 Enhancement (Physical Containment)**: `PhysicalRoot.open_contained()` validates that paths cannot escape workspace roots via directory or file symlinks, Windows reparse points / junctions, or parent traversal components.
- **Fail-Closed Atomic Replacement**: `AtomicFile` ensures files are written with fsync durability and atomic replacement. Injected faults leave destination files in an old-valid or new-valid state; partial writes never persist.
- **Zero Raw Capability Persistence**: Coordination locks, plugin trust records, and persistent tokens must be stored as `VerifierRecord` instances, preventing capability leakage from state files.

### Plugin Security & Content-Addressed Trust Gating (Phase 56)
- **User-Owned Ledger**: Plugin authorization resides exclusively in user configuration (`~/.rush/plugin_trust_ledger.json`). Cloned repositories cannot supply pre-authorized trust receipts.
- **Complete Closure Verification**: Changes to any imported file, configuration value, or environment requirement invalidate the closure digest, requiring explicit user reapproval.
- **Immutable Snapshot Isolation**: Execution runs from byte-copied snapshot directories (`~/.rush/snapshots/<closure_digest>/`), eliminating in-place TOCTOU mutation.
- **Secret Protection**: Literal secrets are strictly forbidden in manifests. Secrets are transported via protected descriptor pipes or stdin JSON handshake protocols invisible to process table observers.

## Control 7: Invocation Containment, Cache Identity & Provider Egress (Phase 57)

- **Target Containment**: Physical paths are bound within the project directory using `rush.io.PhysicalRoot`. Directory junctions, symlinks, and path swaps fail closed with `ScopeWideningError`.
- **Cache Poisoning Prevention**: Cache keys cryptographically bind operation identity, effective configuration digest, active permissions, environment, and physical target content hashes. Missing identities yield `decision = "bypass"` (zero fallback salts).
- **Cross-Origin Egress Protection**: AI review calls strictly validate destination URLs against approved HTTPS origins (`api.openai.com`, `api.anthropic.com`). Cross-origin redirects are refused fail-closed without leaking authorization tokens or prompt payloads.

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
### Supply Chain Provenance & Engine Verification (Phase 59)
- Default provenance statements are explicitly unsigned drafts and never claim SLSA Level 3 without cryptographic attestation.
- `StrictProvenanceParser` enforces JSON object pair uniqueness and Unicode NFKC normalization to prevent parser differential attacks.
- `ProvenancePolicyVerifier` enforces allowlisted DSSE signatures, builder IDs, and artifact hashes.
- External engine discovery enforces pinned versions and forbids ambient PATH pollution.
