# Configuration Schema Specification (`rush.toml`)

## Provider-continuation exclusion

No `[tools.continuity]` credential, endpoint, executable, or persistent network-grant schema exists. OmniRoute uses its fixed local `127.0.0.1:20128` endpoint and no Rush credential store. `9router_cli` reads `RUSH_9ROUTER_API_KEY` only for its child Codex process, maps it to `OPENAI_API_KEY`, and never persists it; 9Router owns model selection.

## Continuity has no persistent configuration grant

There is no `[tools.continuity]` permission field. Checkpoint creation is controlled only by the per-invocation cache-write permission, so configuration remains unable to escalate local persistence.

## Memory database path (Phase 61)

`.rush/memory.db` is the unified SQLite database selected by `TypedArtifactStore`. The central `RushConfig` schema has no `[memory]` or `memory_db_path` field; historical satellite path examples do not configure the current store. See [configuration overview](CONFIGURATION.md).

Rush uses a typed TOML configuration model defined via Python dataclasses in `src/rush/config.py`. Configuration is discovery-driven, bounded by the repository root, and validated against the canonical catalog of catalogued tools.

---

## 1. Schema Structure

```toml
# Root settings
log_level = "warn" # debug | info | warn | error

# Project path boundaries
[project]
src = ["src", "lib"]
test = ["tests", "test"]
exclude = ["**/.venv/**", "**/node_modules/**", "**/dist/**", "**/build/**"]

# Heuristic review configuration
[review]
max_file_lines = 400
use_graft = false
scaffold_markers = ["TODO", "FIXME", "HACK", "XXX"]
source_policy_exclude = ["tests/**", "fixtures/**"]
fail_on = []

# Tool-specific engine overrides
[tools.lint]
engine_args = ["--select", "E,F,W,I"]
check = true

[tools.format]
engine_args = []
check = true

[tools.security]
engine_args = ["--severity", "high,critical"]
check = true

[tools.ai-eval]
engine_args = []
check = true

# Historical/planned consumer settings below are not parsed by RushConfig.
# Bundle budget thresholds (Phase 36)
[bundle]
max_gzip_bytes = 153600 # 150 KB
forbidden_barrels = ["@mui/material", "lodash", "rxjs"]

# Quality Scorecard pillar weights (Phase 40)
[score.weights]
type_safety = 0.20
test_coverage = 0.25
code_health = 0.20
security = 0.15
token_economy = 0.10
governance = 0.10

# Agent safety & command guard (Phase 31)
[guard]
block_destructive_commands = true
max_subagent_depth = 3
confine_workspace_paths = true
```

---

## 2. Table Validation & Precedence Rules


1. **Exact Tool Matching**: Every `[tools.NAME]` table header must match one of the catalogued tools in `rush.catalog.TOOL_SPECS`. Any unrecognized tool name raises `RushConfigError`.
2. **Precedence Hierarchy**:
   ```text
   Built-in Defaults -> Nearest rush.toml (upward walk to .git root) -> Explicit CLI Arguments
   ```
3. **Safety Isolation**: Rush stops walking upward upon reaching the `.git` directory boundary, preventing accidental inheritance of parent directory configuration.
4. **Option Immutability**: Tool options in `ToolConfig.options` are wrapped in immutable `types.MappingProxyType` to prevent runtime mutation.

See [Configuration Reference](reference/configuration-reference.md) and [Configuration Cookbook](reference/configuration-cookbook.md).

### Plugin Table Schema ([plugins.<name>]) (Phase 56)
- `command` (string or list of strings, required): Invocation command.
- `timeout_seconds` (float, optional, default 30.0): Execution timeout.
- `patterns` (list of strings, optional, default ["*"]): File matching patterns.
- `description` (string, optional): Human-readable description.
- `channel_type` (string, optional, enum ["descriptor", "stdin", "provider"]): Protected secret delivery channel.
- `secret_refs` (list of strings, optional): Declared secret reference IDs (`secret:<NAME>`).
- `allowed_env` (list of strings, optional): Explicit allowed non-secret environment variable names.

## Invocation and Cache Schema Attributes (Phase 57)

- `[cache]`: `enabled` (default true), `dir` (default `.rush`), and `max_size_mb` (default 100). There is no maximum-age field in `RushConfig`.
- `[tools.<name>].pure` is not a supported configuration option; purity is operation metadata. Unknown tool options raise `RushConfigError`.

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
### `[release.provenance]`
Historical/planned schema proposal; not parsed by `RushConfig`. Use `rush attest --help` for actual invocation options.
- `builder_id` (string): Canonical builder URI.
- `allow_unsigned` (bool): Allow unsigned drafts (default: true).

### `[engines]`
Historical/planned schema proposal; not parsed by `RushConfig`.
- `isolated_path` (bool): Enforce fixed PATH isolation.
