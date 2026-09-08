# Rush Configuration Overview

## Provider continuation has no persistent configuration

Rush does not store provider credentials, executable paths, OAuth profiles, endpoint URLs, or network grants in `rush.toml`. Each resume invocation supplies its own explicit `--allow-network`; installed CLI authentication stays owned by the CLI. `9router_cli` reads `RUSH_9ROUTER_API_KEY` only from the invoking process and passes it only to its Codex child; it has no `rush.toml` setting and no Rush-selected model.

## Session continuity permissions

`rush.toml` cannot grant session persistence. A caller must grant `--allow-cache-write` for each CLI save, or `allow_cache_write: true` for the corresponding MCP call; this prevents a repository configuration file from silently authorizing local writes.

Rush configuration is designed to be optional, lightweight, and local-first. Most repositories require zero configuration because Rush uses intelligent ecosystem discovery and sensible defaults across catalogued engine adapters.

---

## 1. Quick Start

Create a `rush.toml` file at your repository root:

```toml
log_level = "warn"

[project]
src = ["src"]
test = ["tests"]
exclude = ["**/.venv/**", "**/node_modules/**"]

[review]
max_file_lines = 400
use_graft = false
scaffold_markers = ["TODO", "FIXME", "HACK"]

[tools.lint]
check = true
```

---

## 2. Configuration Features

- **Automated Init (`rush init`)**: Automatically inspect your repository and write a tailored `rush.toml`.
- **Schema Validation (`rush config check`)**: Statically validates `rush.toml` against canonical schemas and tool catalogs.
- **Custom Plugins (`[plugins.<name>]`)**: Declare custom linter/analyzer script execution commands.
- **Local Dashboard**: Use the registered CLI `--port` option. The central configuration parser does not consume `[dashboard]`; working web interaction remains planned in Phase 66.
- **Automatic Upward Discovery**: Rush walks upward from the target directory until it finds the nearest `rush.toml` file or reaches the `.git` boundary.
- **Strict Catalog Validation**: Every `[tools.<name>]` section is validated against `TOOL_SPECS` in `src/rush/catalog.py` at parse time. Typographical errors raise actionable configuration errors immediately.
- **Engine Arguments Pass-Through**: Pass specific flags to underlying linters (e.g. `engine_args = ["--select", "E,F,W,I"]`).
- **Observability with `rush capabilities`**: Inspect how Rush perceives your configuration and installed tools using `rush capabilities . --json`.

---

## 3. Related Documentation

- [Configuration Reference](reference/configuration-reference.md): Full field-by-field specification and type constraints.
- [Configuration Cookbook](reference/configuration-cookbook.md): Production configurations for Python, TypeScript, polyglot, and cloud-native repositories.
- [Configuration Schema](CONFIG_SCHEMA.md): Schema validation rules.

## Context Intelligence & Preferences Configuration (Phases 41–43)

Historical/planned configuration sketch below. `RushConfig` does not parse `[context_intel]` or `[memory]`; these keys do not relocate stores, enable distillers, or authorize persistence. `.rush/memory.db` is selected by memory runtime code. Memory administration remains governed by [Phase 63](phase-plans/phase-63-memory-capabilities-vibecoder-plan.md).

```toml
[context_intel]
default_encoding = "cl100k_base"
enable_distillers = true
max_distilled_lines = 100

[context_intel.distillers]
pytest = true
cargo = true
ruff = true
vitest = true

[memory]
# Phase 61: preferences_path, failures_db_path, and invariants_path are legacy
# satellite paths absorbed into the unified store below; each is retained
# read-only with a `.migrated` suffix, never deleted (Invariant 5).
memory_db_path = ".rush/memory.db" # TypedArtifactStore — unified store for all 7 memory subjects (Phase 61)
preferences_path = ".rush/preferences.json" # legacy, .migrated after first Phase 61 run
sessions_path = ".rush/sessions" # still written: checkpoint_journal.py's save_checkpoint() keeps a physical .json artifact
ccr_cache_path = ".rush/cache/ccr.db"
failures_db_path = ".rush/memory/failures.db" # legacy, .migrated after first Phase 61 run
invariants_path = ".rush/memory/invariants.json" # legacy, .migrated after first Phase 61 run
```

## Phase 50a Quality & Security Suite Tool Configuration

```toml
[tools.error-catalog]
export_path = "docs/ERROR_CATALOG.md"

[tools.license-matrix]
allowed_licenses = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC"]

[tools.iam-audit]
output_policy_file = "reports/iam-policy.json"
```

## Phase 50b/50c Flagship Tool Configuration

```toml
[tools.attest]
artifact_path = "dist/app-0.1.0-py3-none-any.whl"
output_path = "dist/app-0.1.0.intoto.json"

[tools.license-matrix]
allowed_licenses = ["MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC"]

[tools.iam-audit]
output_policy_file = "reports/iam-policy.json"

[tools.dead-asset]
export_manifest = "reports/dead-assets.json"

[tools.pr-synthesize]
base_ref = "main"
export_path = "reports/pr-card.md"

[tools.prompt-eval]
pass_rate_threshold = 1.0
max_tokens_threshold = 50000
max_cost_threshold = 0.50

[tools.error-catalog]
export_path = "docs/ERROR_CATALOG.md"

[tools.mem-profile]
dynamic = false

[tools.cold-start]
dynamic = false

[tools.media-opt]
sanitize = false
optimize = false

[tools.offline-review]
model_path = "models/reviewer.onnx"

[tools.tui-diff]
base_ref = "HEAD~1"

[tools.benchmark]
threshold_percent = 5.0
```

These are separate examples; do not paste duplicate `[tools.*]` tables into one file. Artifact-producing options require per-invocation permission. Accepted analysis corrections remain planned in [Phase 64](phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md). Source: `src/rush/config.py::_parse` and `src/rush/catalog.py::TOOL_SPECS`; `rush config check .` reports malformed or unknown tool options.

### Plugin Configuration & Secret References (Phase 56)
In `rush.toml`, configure plugins under `[plugins.<name>]`:
```toml
[plugins.custom_scanner]
command = "python scan.py"
timeout_seconds = 30.0
patterns = ["*.py", "*.ts"]
description = "Custom security scanner"
channel_type = "stdin" # "descriptor", "stdin", "provider"
secret_refs = ["secret:API_KEY"]
allowed_env = ["RUSH_PROJECT_ROOT"]
```
Literal secrets are forbidden and will be rejected at parse time.

## Invocation Context & Cache Configuration (Phase 57)

Configuration digests (`effective_config_digest`) are derived from normalized tool configuration tables. Modifications to tool settings invalidate cached results deterministically without relying on ad-hoc salt defaults.

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
### `[release.provenance]` & `[engines]` (Phase 59)
Configure provenance builder URI, default output paths, and engine taxonomy support classes in `rush.toml`.
