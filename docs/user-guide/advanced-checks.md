# Advanced Checks & Monorepos

As software repositories grow into multi-package monorepos with hundreds of thousands of lines of code, managing performance, scoping checks, and tracking defect risk becomes critical.

Rush includes advanced architectural capabilities designed specifically for large-scale codebases.

---

## 1. Multi-Package Monorepo Scoping (`rush workspace`)

If your repository contains multiple packages (e.g. `apps/web`, `apps/api`, `packages/shared-ui`), running checks across the entire repository every time you change one file is slow and wasteful.

Rush automatically discovers workspace topologies across **pnpm, npm, yarn, Cargo, and Turborepo**:

```bash
# List all discovered workspace packages in topological order
uv run rush workspace list

# Find only the packages affected by your recent Git changes
uv run rush workspace affected

# Run checks on a specific package
uv run rush check . -w packages/shared-ui
```

---

## 2. Flag-Salted Result Caching (`rush cache`)

Rush includes an embedded, high-performance SQLite result cache (`.rush/cache.db`). When a file hasn't changed and the tool configuration remains identical, Rush returns the cached result in **0 milliseconds**.

```bash
# Inspect the local result cache
uv run rush cache stats

# Clear cached results before a fresh run
uv run rush cache clean
```

The cache uses cryptographic SHA-256 content hashing combined with command-line flags to guarantee you never receive stale or incorrect results.

---

## 3. Git Hotspots & Defect Risk Matrix (`rush hotspots`)

Where are bugs most likely to hide in your repository?

Research across software engineering shows that defects concentrate where **high commit churn** (files that are constantly being edited) intersects with **high cyclomatic complexity** (files with deeply nested `if/else` logic).

```bash
uv run rush hotspots analyze
```

### What Rush Computes:
- **Commit Churn**: How many times a file has been modified over the past 90 days.
- **McCabe Cyclomatic Complexity**: How many decision paths exist in the code.
- **Composite Defect Risk Score**: Pinpoints the top 5 highest-risk files in your repository so you know exactly where to write extra unit tests or schedule refactoring.

---

## 4. Web Asset & Bundle Budgeting (`rush bundle`)

If you build frontend web applications, shipping massive JavaScript bundles to users slows down page load times and harms SEO rankings.

```bash
uv run rush bundle analyze dist/
```

- Calculates raw, Gzip, and Brotli chunk transfer sizes.
- Identifies barrel file imports (`import { a } from './components'`) that prevent effective tree-shaking.
- Detects duplicate CSS rules and uncompressed images.

---

## Next Steps

- Explore the complete [Bundle Diagrams](../BUNDLE_DIAGRAMS.md).
- Discover solutions to common questions in [Troubleshooting Guide](troubleshooting.md).

## Advanced Ship Vectors (Phases 41–43)
* `rush ship migration`: Checks SQL files for table locks (`ALTER TABLE ... ADD COLUMN NOT NULL`).
* `rush ship semver`: Compares AST public interfaces between versions.
* `rush ship pack`: Scans repository trees for secret keys, credentials, and `.env` leaks.

## Blast Radius & Architecture Checks
* `rush blast-radius`: Downstream reachability.
* `rush arch-guard`: Layer boundary verification.



## Flaky Test Healing & API Diff
* `rush test-heal`: Diagnose intermittent test failures.
* `rush api-diff`: Ensure public signature parity.



## DB Drift & Code Simplification
* `rush db-drift`: Schema migration drift detection.
* `rush simplify`: Function complexity decomposition.
* `rush strictify`: Runtime type guard generation.



## Traceability & CI Simulation
* `rush trace`: Spec-to-code traceability.
* `rush simulate-ci`: Local GitHub Actions emulation.



## Polyglot Quality & Security (Phase 50a)
* `rush error-catalog`: Statically extracts exception paths across Python, TypeScript, and Rust to build RFC 7807 problem details catalogs.
* `rush license-matrix`: Audits multi-ecosystem package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`) for copyleft license risks.
* `rush iam-audit`: Analyzes multi-cloud SDK calls and flags wildcard actions in Terraform configurations.
* `rush attest`: Cryptographic build provenance (Phase 50b/c).


## 5. Pull Request Evidence Cards (`rush pr-synthesize`)
Generate a production-ready PR card with diff stats, risk tiering, and CODEOWNERS routing:
```bash
uv run rush pr-synthesize . --json
```

## 6. Cold-Start Profiling & Benchmark Baselines
Detect slow top-level imports and enforce performance regression gates:
```bash
uv run rush cold-start .
uv run rush benchmark check .
```

### Custom Plugin Execution (Phase 56)
Run configured plugins using `rush plugin run <name>`. Results are checked against quality thresholds and formatted alongside built-in engines.

## Advanced Invocation & Cache Options (Phase 57)

- Use `--no-cache` to force clean tool execution.
- Quality tools verify physical containment, ensuring target files cannot escape project boundaries through symlinks.

## Advanced Memory Queries (Phase 61)

`rush memory ask|list|recall SUBJECT QUERY --session SOURCE` searches the unified store with FTS5 and BM25 ranking. Subjects are `active_context`, `episodic`, `preference`, `failure`, `architectural_decision`, `domain_knowledge`, and `skill_pattern`. All three commands apply signature, staleness, and Trojan Source checks. Repeat `--session` to include more sources; omitting it returns `skipped` without content.

For example, `rush memory list episodic authentication --session session_memory:record_turn --json` returns matching recorded turns from that source.

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

4. **Contained Patch Verification (`rush.patch`) — current safety repair pending**:
   - `PatchContract` cryptographically binds base commit, tree digest, patch content hash, sandbox directory under `rush.io.PhysicalRoot`, command plans, and policy review classes (`standard`, `policy-changing`, `privileged`).
   - Workspaces must be clean before sandboxing or patch application; dirty checkouts fail closed with `DirtyWorkspaceError`.
   - `PatchVerifier` requires at least one passing executed test command; zero executed commands return `outcome='unavailable'` and `False` (zero commands never verify).
   - Current failure cleanup can run broad `git reset --hard`, `git clean -fd`, and worktree cleanup. Do not use this as safe rollback evidence. Invocation-owned restoration is required by [Phase 64, P64-04](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-04--safe-patch-application-and-promotion-f03-f43).

5. **Runtime Output Boundary Adapter Enforcement (`rush.contracts.operations`)**:
   - 100% of public operations declared in `governance/public-operations.toml` enforce their target adapters (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) at runtime boundaries while preserving native JSON-RPC service protocol messages.
### Advanced Engine Discovery (Phase 59)
Configure engine taxonomy, skip reasons, and fixed-PATH isolation.
