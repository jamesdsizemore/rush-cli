# Configuration reference

## Provider resume is invocation-scoped

There is no configuration table for provider executable paths, profiles, credentials, endpoints, or persistent network permission. Authentication is inherited from the already configured user-owned CLI, and `--allow-network` is required per invocation. `9router_cli` accepts only process environment `RUSH_9ROUTER_API_KEY`, maps it only to its Codex child, and never accepts a model setting.

## Continuity permissions

No `rush.toml` value enables checkpoint writes. Use `--allow-cache-write` only on a save invocation; MCP callers pass `allow_cache_write: true` for that individual call.

Rush configuration is optional. It discovers the nearest `rush.toml` while walking upward from the target and stops at the Git root or filesystem root.

## Precedence

```text
Built-in defaults -> nearest rush.toml -> explicit CLI arguments
```

Only behavior confirmed by implementation should drive policy. The parser accepts more fields than current tools consume.

## Root

```toml
log_level = "warn"
```

`log_level`: `debug`, `info`, `warn`, or `error`; default `warn`. `RUSH_LOG_LEVEL` supplies the CLI option default, and explicit `--log-level` wins for that invocation.

## `[project]`

```toml
[project]
src = ["src"]
test = ["tests"]
exclude = ["**/.venv/**", "**/node_modules/**"]
```

All are string lists. Defaults are shown. These fields are parsed but current command routing generally uses the supplied path and built-in collectors; do not assume they redefine every scan until a tool has a verified consumer.

## `[review]`

```toml
[review]
max_file_lines = 400
fail_on = []
use_graft = false
scaffold_markers = []
source_policy_exclude = []
```

- `max_file_lines`: threshold for the deterministic file-size heuristic; implemented.
- `use_graft`: requests local Graft context when available; implemented.
- `scaffold_markers`: exact strings to report as configured unfinished markers; implemented.
- `source_policy_exclude`: relative glob patterns excluded from scaffold-marker checks; implemented.
- `fail_on`: parsed but not currently enforced by review status logic.

## `[tools.NAME]`

```toml
[tools.lint]
engine_args = ["--select", "E,F,W,I"]
check = true
```

`NAME` must exactly match one of the catalog tool names (e.g. `lint`, `format`, `test`, `security`, `tdd`, `slop`, `complexity`). Unknown names raise `RushConfigError`.

## `[plugins.NAME]` (Phase 28)

```toml
[plugins.custom-linter]
command = "python scripts/my_linter.py"
description = "Custom AST rule scanner"
file_extensions = [".py"]
```

Custom quality engine plugins defined in `rush.toml`. Requires repository trust authorization via `rush trust` (Control 6).

## `[dashboard]` (Phase 27)

```toml
[dashboard]
port = 8080
host = "127.0.0.1"
```

Configures default binding port and parameters for the local in-memory web dashboard.

## `[bundle]` (Phase 36)

```toml
[bundle]
max_gzip_bytes = 153600
forbidden_barrels = ["@mui/material", "lodash", "rxjs"]
```

Enforces frontend JavaScript chunk transfer budgets and blocks unoptimized barrel file imports.

## `[score.weights]` (Phase 40)

```toml
[score.weights]
type_safety = 0.20
test_coverage = 0.25
code_health = 0.20
security = 0.15
token_economy = 0.10
governance = 0.10
```

Customizes the relative weighting for the 6-pillar composite quality scorecard.

## `[guard]` (Phase 31)

```toml
[guard]
block_destructive_commands = true
max_subagent_depth = 3
confine_workspace_paths = true
```

Configures agent safety boundaries, destructive command interception, and tree depth constraints.

## `[memory]` (Phase 61)

```toml
[memory]
memory_db_path = ".rush/memory.db"
preferences_path = ".rush/preferences.json"   # legacy, .migrated after first Phase 61 run
sessions_path = ".rush/sessions"              # still written by checkpoint_journal.py
ccr_cache_path = ".rush/cache/ccr.db"
failures_db_path = ".rush/memory/failures.db" # legacy, .migrated after first Phase 61 run
invariants_path = ".rush/memory/invariants.json" # legacy, .migrated after first Phase 61 run
```

`memory_db_path` is the unified SQLite WAL `TypedArtifactStore` covering all 7 memory subjects. The legacy satellite paths are absorbed into it and retained read-only with a `.migrated` suffix, never deleted.

## Phase 50a Quality & Security Tools Configuration

```toml
[tools.error-catalog]
operation = "audit"
export_docs = "docs/ERROR_CATALOG.md"
output_module = "src/rush/errors.py"

[tools.license-matrix]
project_license = "Apache-2.0"
allowed_licenses = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC"]
export_path = "reports/licenses.json"

[tools.iam-audit]
export_path = "reports/iam-policy.json"
```

Tool options are stored in immutable `types.MappingProxyType` inside `ToolConfig.options` and merged via `resolve_tool_options`.

## Validation behavior

Malformed TOML, unknown log levels, wrong value types, and unknown tool names fail configuration loading. Rush does not merge multiple files: nearest discovered file wins. Validate anytime with `rush config check .`.

See [Configuration cookbook](configuration-cookbook.md) and [developer configuration guide](../developer/configuration-development.md).


### `tools.provenance-ai`, `tools.dead-asset`, `tools.pr-synthesize`
Configures commit depth, asset prune permissions, and PR base branches.

### `tools.attest`, `tools.mem-profile`, `tools.cold-start`, `tools.offline-review`, `tools.benchmark`
Configures builder identifiers, dynamic profiling flags, model paths, and benchmark thresholds.

### [plugins] Configuration Table (Phase 56)
Configures custom external quality engines with pattern matching, timeout limits, and protected secret channels.

## Invocation & Cache Configuration Reference (Phase 57)

Configuration options for `[cache]` and `[tools.<name>]` control cache storage paths, TTL, and purity declarations.

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
