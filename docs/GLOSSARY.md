# Glossary of Terms

A comprehensive reference for terms, architectural concepts, and acronyms used across Rush CLI, MCP transports, and documentation.

---

**AI Evaluator** — Specialized tools (Promptfoo, Garak, DeepEval, Guardrails) that probe and grade LLM prompts, agent workflows, and safety policies.

**Canonical ToolResult (`ToolResultV1`)** — The standard JSON dictionary returned by every Rush quality tool, containing `schema_version` ("1.0.0"), `tool`, `engine`, `status`, `duration_ms`, `timestamp`, `summary`, `findings`, and optional `raw`/`metadata`.

**Deterministic Aggregation** — Multi-engine result combination with strict status precedence (`error > fail > warn > ok > skipped`), sum of durations, and coordinate-sorted findings.

**Engine Adapter** — An isolated Python class in `src/rush/engines/` that discovers an external executable, constructs bounded CLI arguments, executes the process safely, and normalizes output.

**Execution Permissions** — Granular, explicit opt-in flags (`--allow-network`, `--allow-download`, `--allow-cache-write`, `--allow-build`, `--allow-slow`, `--allow-artifact-write`, `--allow-browser`) required for resource-intensive or mutating operations.

**FastMCP** — The Model Context Protocol SDK used by Rush to register local stdio tools (`rush_<name>`) matching CLI commands.

**Finding Fingerprint** — A deterministic SHA-256 hash calculated from normalized finding attributes (path, line, rule, message) used for tracking and baseline comparisons.

**Graft** — A code knowledge graph tool that traces call graphs and symbol relationships. Rush can consume local Graft context during reviews via `--use-graft`.

**Heuristic Review** — Deterministic Python AST and structure analysis for code maintainability, function lengths, and scaffold markers without requiring an external AI provider.

**Model Context Protocol (MCP)** — An open protocol that enables AI coding assistants (Cursor, Claude Code, Windsurf) to securely query local tools over stdio.

**Maturity Level** — Status classification for catalog tools (`real_adapter`, `importer`, `browser_runtime`, `catalog_only`, `guarded_placeholder`).

**Redaction** — Automated masking of API keys, tokens, and credentials as `[REDACTED]` before findings or logs are emitted.

**Subprocess Isolation** — Executing external tools with `stdin=DEVNULL`, `shell=False`, and timeout limits to protect the MCP transport from pollution or hanging.

**Transport Dispatcher** (Phase 61) — `src/rush/memory/transport.py`'s per-tool tier selector for cross-tool memory handoff: native SDK → ACP → dedicated-file fallback, chosen independently for each tool in a run, never one global protocol for the whole session.

**Trust Tier** (Phase 61) — The 4-value taxonomy (`STATED`/`DERIVED`/`EXTERNAL_WRITE`/`IMPORTED`) on every `MemoryArtifact` row; new writes never enter at `STATED` — only the write-promotion rule can promote a record to it.

**Typed Artifact** (Phase 61) — `MemoryArtifact`, one row of the unified `TypedArtifactStore` schema (`src/rush/memory/store.py`), tagged with a `family` (`handoff`/`experience`/`memory`/`skill`) and a `subject` (one of 7 memory subjects), replacing eight prior satellite files/formats.

**Vibecoder Guardrails** — Specialized quality checks (such as `sloppylint`, `markdown-unfluff`, `git-guard`, `safe-env`, `diff-cover`) designed to catch AI slop, hallucinations, and untracked code artifacts before shipping.

**Write-Promotion Rule** (Phase 61) — `evaluate_promotion()` in `src/rush/memory/trust.py`: a candidate record is promoted to `STATED` only after passing an ALLOW/REDACT/BLOCK screen, a regex pre-filter, a full-schema-populated check, a grounding check, and either direct user statement or corroboration ≥ 2.

See [Getting Started Glossary](getting-started/glossary.md) and [Result Reference](reference/result-reference.md).

### Context Intelligence & Ship Gate Terms (Phases 41–43)

* **AST Skeletonization**: Replacing function/method implementation bodies with `...` or `/* ... */` while preserving signatures, type annotations, and docstrings for minimal token footprint.
* **BPE (Byte-Pair Encoding)**: Token counting algorithm (`tiktoken` cl100k/o200k) used for exact budget estimation.
* **CCR (Context Compression & Restoration)**: Lossless chunk caching protocol replacing large text blobs with `<!-- ccr:chunk:HASH -->` tags backed by local SQLite storage.
* **Command Distiller**: Regex/AST parser that extracts concise failure frames from verbose build and test outputs (e.g., `pytest`, `cargo`, `vitest`).
* **Grounding Verifier**: Static AST analyzer that confirms imported packages and symbols are physically present in the standard library or installed environment.
* **HalluGuard**: Real-time pre-execution defense preventing AI agents from hallucinating nonexistent packages or typosquatting dependencies.
* **Merkle Invalidator**: AST node hashing mechanism using SHA-256 to invalidate cached memories only when specific AST subtrees change.
* **Mistake Miner**: Bi-temporal Git revert analyzer extracting historical regression post-mortems into active guardrails.
* **Ship Cockpit**: Parallel 7-vector release readiness evaluator checking scratch hygiene, environment parity, docs links, SQL table locks, API compatibility, package safety, and test confidence.
* **TOON (Token-Oriented Object Notation)**: Compact pipe-delimited table serialization format cutting 40–65% of JSON token overhead in MCP tool responses.

### Context Packing, Telemetry & Blast Radius Terms (Phases 44–46)
* **ArchGuard**: Declarative architectural boundary validator enforcing directional dependency rules between software layers.
* **Blast Radius**: The downstream set of modules, API routes, and test suites affected by modifying a target source file.
* **Cache Aligner**: Pre-processor that pads invariant prompt prefixes above 1,024 tokens to maximize provider KV prompt cache hits.
* **Context Packer**: Algorithm that extracts verbatim focus symbols while compressing peripheral code to meet strict token budgets.
* **Stale Read Sweeper**: Optimizer that collapses older conversation turns' file contents into 1-line signatures.
* **Telemetry Ledger**: SQLite database (`.rush/telemetry/tokens.db`) tracking token savings and estimated dollar reductions.
* **Terse Persona**: Agent response shaper stripping conversational fluff and filler words for concise output.


### Test Healing & API Diff Terms (Phase 47)
* **ApiDiffer**: AST semantic diffing engine flagging removed exports or altered signatures.
* **GitSandbox**: Ephemeral throwaway worktree context manager ensuring clean isolation.
* **TestHealer**: Autonomous engine executing perturbation stress runs to stabilize flaky tests.



### DB Drift & Code Simplification Terms (Phase 48)
* **ComplexityDecomposer**: AST tool measuring cognitive branch depth and proposing helper abstractions.
* **DbDriftAuditor**: Static linter checking ORM classes against SQL migration statements.
* **TypeSynthesizer**: Generator creating defensive runtime type guards for untyped arguments.



### Traceability & Swarm Terms (Phase 49)
* **FlightRecorder**: Subsystem capturing deterministic agent tool invocation histories.
* **MeshLockManager**: Mutex coordinator preventing concurrent agent file overwrite races.
* **SwarmMergeSolver**: AST-level reconciler merging non-overlapping class and function edits.
* **TraceScanner**: Requirement matrix scanner validating spec IDs against AST source nodes.



### Attestation, Security Suite & Quality Terms (Phase 50)
* **AttestationTool**: Subsystem generating in-toto Statement v1 / SLSA Provenance v1 unsigned drafts with SHA-256 artifact digests.
* **DeadAssetTool**: Tool scanning for unreferenced fonts and images to reduce bundle weight with guarded prune verification.
* **ErrorCatalogTool**: AST exception extractor generating RFC 7807 problem details and Markdown error catalogs.
* **IamAuditTool**: Static analyzer synthesizing least-privilege AWS IAM JSON policies from boto3/botocore SDK calls.
* **LicenseMatrixTool**: Compliance tool classifying dependency licenses against allowed SPDX identifiers and flagging manual review needs.
* **MemProfileTool**: Static resource leak scanner and dynamic memory profiling probe under `--allow-slow`.
* **MediaOptTool**: SVG script security sanitizer and Pillow PNG/WebP raster image optimizer.
* **OfflineReviewTool**: Air-gapped local ONNX model code review runner with zero network connectivity.
* **PromptEvalTool**: Golden coding prompt matrix evaluator comparing sequence matches, patch matches, token counts, and dollar budgets.
* **ProvenanceAiTool**: Git commit trailer attribution analyzer evaluating AI co-authorship and model provenance metadata.
* **PrSynthesizeTool**: Pull request description generator synthesizing Git diff statistics and ToolResult quality evidence.
* **TuiDiffTool**: Git finding delta computer and Rich terminal comparison table renderer.

### Schema Kernel & Operation Terms (Phase 54)
* **FindingV1**: Typed model for static analysis findings enforcing valid severity (`info`, `warning`, `error`), non-empty identifier, and line coordinates.
* **OperationRegistry**: Central taxonomy registering and reconciling all 146 public operations across `tool`, `admin`, and `service` domains.
* **ToolOperationAdapter**: Execution envelope validating and serializing tool results to `ToolResultV1`.
* **ToolResultV1**: Fail-closed canonical schema kernel specification (`schema_version: "1.0.0"`) with ISO 8601 UTC timestamps and 8 mandatory keys.
* **ValidationErrorV1**: Structured validation failure record carrying machine-readable reason codes (`MISSING_REQUIRED_KEY`, `INVALID_TYPE`, `INVALID_STATUS`, `INVALID_TIMESTAMP`, `INVALID_SEVERITY`).

### File I/O & Physical Containment Terms (Phase 55)
* **AtomicFile**: Primitive providing fail-closed, durable atomic file replacement using same-directory temporary files (`.rush_tmp_`), explicit `flush()`, `os.fsync()`, and manager-owned cleanup.
* **ContainmentError**: Exception raised when a path breaches physical workspace boundaries via absolute formatting, parent traversal (`..`), symlinks, or Windows reparse points.
* **PhysicalRoot**: Boundary validator ensuring that all filesystem operations remain strictly confined to a designated physical directory.
* **SanitizedBytes / SanitizedJsonValue**: Typed wrappers ensuring that only sanitized, secret-redacted data can be passed to atomic write primitives.
* **VerifierRecord**: A cryptographically salted, high-work-factor one-way verification record ensuring authorization capabilities cannot be recovered from persistent disk storage.

- **Plugin Closure**: The complete cryptographic manifest encompassing an external plugin's entrypoint, all local files, configs, allowed environment names, declared secret references, runtime identity, and platform binding.
- **Content-Addressed Snapshot**: An immutable, physical byte-copied mirror of a plugin's closure stored under `rush.io.PhysicalRoot` in `~/.rush/snapshots/<closure_digest>/` from which subprocesses execute.
- **User Trust Ledger**: The authoritative, user-owned store located at `~/.rush/plugin_trust_ledger.json` recording user-granted plugin execution authorizations.
- **Protected Secret Channel**: A secure transport mechanism (anonymous descriptor pipe or stdin JSON handshake) used to deliver credentials to plugin subprocesses without exposing them in command arguments or environment tables.

## Phase 57 Architectural Terms

- **`InvocationContext`**: The authoritative, immutable execution context constructed before any tool or command runs.
- **`PhysicalTarget`**: A contained workspace target with verified physical existence, state, provenance, and content hash.
- **`CacheDecision`**: The deterministic outcome (`eligible` or `bypass`) indicating whether an invocation can be cached.
- **`Effective Origin`**: The verified destination origin of an HTTP provider call, ensuring requests target approved HTTPS endpoints.

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
- **Provenance Draft:** An explicitly unsigned build statement capturing artifact identity and build parameters without claiming cryptographic accreditation.
- **Strict Provenance Parser:** A parser that enforces key uniqueness and Unicode NFKC normalization to block parser differential attacks.
- **Engine Support Policy:** The single source of truth (`engine-support.toml`) governing engine classification and skip policies.
- **Fixed-PATH Isolation:** Execution context isolating binary lookup from host developer environments.
