# Python Internal API Reference

## Recoverable context and coordination evidence

`SessionContinuityTool.run(..., operation="context_pack")` stores redacted omitted packed context in local `CCRStore` only with `ExecutionPermissions(cache_write=True)` when its token budget is insufficient. Without that permission, it returns `recovery.state: "not_created"` with reason `cache_write_required` and creates no local recovery state. A permitted canonical `metadata.context_envelope.recovery.handle` can be supplied to `context_retrieve`; it is not an instruction or a transcript import, and retrieval redacts legacy CCR content before returning it. An omitted payload is not delivered, so its telemetry is `not_measured` with `provider_cost: null` and no savings-ledger event. `coordination_recovery` also returns bounded mined mistake records labelled `historical_evidence`, alongside replay and failure receipts; malformed replay or a corrupt ledger becomes structured unavailable evidence.

## Session continuity

`rush.tools.continuity.SessionContinuityTool.run(path, operation, name, files, handoff, permissions)` returns the canonical `ToolResult`. Operations are `save`, `list`, and `restore`; `save` is `skipped` without explicit cache-write permission, and a missing checkpoint is `skipped` rather than an exception. `handoff` accepts `current_goal`, `open_work`, `historic_instruction`, `failure_fingerprint`, and repository-relative `dependencies`; the persisted result exposes only the redacted receipt in `metadata.handoff`, including at most five historical session-memory records labelled `historical_evidence`.

Coordination operations are `coordination_check`, `coordination_merge_preview`, and `coordination_recovery`. They return `metadata.coordination` evidence only: ownership state, manual-recovery/manual-reconciliation actions, conflict names, and bounded replay/failure receipt metadata. They do not write locks, merge code, execute a replay, or return a failed patch.

`operation="provider_resume"` accepts a checkpoint `name` and `provider_id`. Enabled direct CLI IDs are `claude_code`, `codex_cli`, `antigravity_cli`, and `9router_cli`; `omniroute_api` is a fixed `127.0.0.1:20128/v1/chat/completions` adapter using `model: "auto"`. `9router_cli` invokes Codex with `OPENAI_BASE_URL=http://127.0.0.1:20128` and an ephemeral `OPENAI_API_KEY` from `RUSH_9ROUTER_API_KEY`; it never sends a model argument. Each requires `ExecutionPermissions(network=True)`. The route receives a bounded goal/frontier/freshness projection, never a raw transcript, historic instruction, failed patch, provider credential, or returned model text. On Windows batch launchers, the projection is passed only through a per-process delayed-expansion environment variable, not CMD command syntax. `zai` is deliberately `skipped` as deferred and direct `9router_api` remains unavailable.

Rush is packaged as a local CLI application and stdio Model Context Protocol (MCP) server. While Rush does not expose an external programmatic Python library, internal contributors and custom tool authors interact with the following stable core contracts in `src/rush/`.

---

## 1. Core Tool Contract (`src/rush/tools/base.py`)

### `ToolFn`
The abstract base class for catalogued tools. The signature sketch below illustrates intended arguments; actual callable signatures differ by tool. Use the runtime registration schema in [MCP reference](reference/mcp-tool-reference.md) and source definitions for exact types/defaults.
```python
class ToolFn:
    name: str
    description: str

    def run(
        self,
        path: Path,
        *,
        config: RushConfig | None = None,
        permissions: ExecutionPermissions | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Internal execution entry point. Accepts typed configuration and execution permissions."""
        ...

    def __call__(
        self,
        path: str = ".",
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """FastMCP execution surface. Exposes only JSON-schema-compatible types."""
        ...
```

### `ToolResult`
The canonical dictionary shape returned by all tools:
```python
class ToolResult(TypedDict):
    tool: str
    engine: str | None
    engine_version: str | None
    status: Literal["ok", "warn", "fail", "error", "skipped"]
    duration_ms: int
    summary: str
    findings: list[Finding]
    raw: Any | None
    metrics: NotRequired[dict[str, Any]]
    artifacts: NotRequired[list[str]]
    metadata: NotRequired[dict[str, Any]]
```

### `Finding`
Individual issue reported by an engine or heuristic:
```python
class Finding(TypedDict):
    fingerprint: str
    path: str
    line: int
    column: int | None
    end_line: int | None
    end_column: int | None
    rule: str
    severity: Literal["info", "warn", "error"]
    message: str
    fix: str | None
    provenance: str
    freshness: Literal["unknown", "existing", "new"]
```

---

## 1.1 Contracts Kernel (`src/rush/contracts/`)

Phase 54 introduces the immutable contract types in `rush.contracts`, providing standard library schema definitions, validation, and adapter boundaries:

### Result Contracts (`src/rush/contracts/results.py`)

- **`ToolResultV1`**: Frozen dataclass enforcing `schema_version = "1.0.0"`, status vocabulary (`"ok"`, `"warn"`, `"fail"`, `"error"`, `"skipped"`), `duration_ms >= 0`, `findings: list[FindingV1]`, and namespaced `extensions: dict[str, Any]`.
- **`FindingV1`**: Frozen dataclass enforcing canonical severities (`"info"`, `"warning"`, `"error"`), non-negative line/column, 64-character hex fingerprint, and namespaced `extensions`.
- **`ValidationErrorV1(Exception)`**: Structured exception holding `code`, `message`, `path`, and `invalid_value`. Canonical codes include `MISSING_REQUIRED_FIELD`, `UNKNOWN_TOP_LEVEL_KEY`, `INVALID_STATUS`, `INVALID_SEVERITY`, `INVALID_SCHEMA_VERSION`, `INVALID_TYPE`, `NON_JSON_SAFE_VALUE`.
- **`validate_tool_result(data: Any) -> ToolResultV1`**: Strict validator rejecting unknown top-level keys and invalid values.
- **`validate_finding(data: Any, path_prefix: str) -> FindingV1`**: Validates finding structures against `FindingV1`.
- **`serialize_tool_result(result: ToolResultV1 | dict[str, Any]) -> str`**: Sanitizes via Phase 53 `sanitize_value`, validates via `validate_tool_result`, and encodes deterministically using sorted keys and compact separators `(',', ':')`.
- **`adapt_legacy_finding(legacy: dict[str, Any]) -> FindingV1`**: Converts legacy findings, strictly mapping `"warn"` -> `"warning"` and `"fail"` -> `"error"`, synthesizing missing fingerprints, and routing unrecognized keys to `extensions`.
- **`adapt_legacy_tool_result(legacy: dict[str, Any]) -> ToolResultV1`**: Adapts legacy `ToolResult` dictionaries into `ToolResultV1` with `schema_version = "1.0.0"`.

### Operation Adapters (`src/rush/contracts/operations.py`)

- **`BaseOperationAdapter`**: Abstract base defining `operation_id`, `kind: Literal["tool", "admin", "service"]`, `target_contract_id`, and abstract `validate_output(output)`.
- **`ToolOperationAdapter`**: Binds `kind = "tool"` operations to `ToolResultV1`.
- **`AdminOperationAdapter`**: Binds `kind = "admin"` operations to named admin contracts (such as integer exit codes or admin payload dictionaries).
- **`ServiceOperationAdapter`**: Binds `kind = "service"` operations to protocol frames, strictly rejecting `ToolResultV1` wrapping on stdio JSON-RPC frames (`initialize`, `tools/list`).
- **`OperationRegistry`**: Central registry that reconciles 100% of the 146 operations from `governance/public-operations.toml`.

---

## 2. Engine Adapter Contract (`src/rush/engines/base.py`)

### `Engine`
The abstract adapter for external quality binaries (86 total):
```python
class Engine:
    name: str
    binary: str

    def is_available(self) -> bool:
        """Checks whether binary exists on PATH using cache."""
        ...

    def run(self, target: Path, options: dict[str, Any]) -> ToolResult:
        """Executes engine with run_subprocess and normalizes stdout/stderr to ToolResult."""
        ...
```

---

## 3. Subprocess Isolation & Resolution (`src/rush/tools/common.py`)

```python
def run_subprocess(
    argv: list[str],
    cwd: Path | str | None = None,
    timeout: float = 120.0,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Runs external commands with stdin=DEVNULL, shell=False, and stdout/stderr capture."""
    ...


def resolve_binary(binary_name: str) -> str | None:
    """Resolves binary location using in-memory @lru_cache for performance."""
    ...
```

---

## 4. Exporters & Report Generation

### HTML Dashboard Exporter (`src/rush/html_export.py`)
```python
def export_to_html(result: ToolResult, output_path: Path | str) -> Path:
    """Renders a self-contained, standalone HTML report with dark mode and filterable tables."""
    ...
```

### SARIF 2.1.0 Exporter (`src/rush/sarif.py`)
```python
def export_to_sarif(result: ToolResult, output_path: Path | str) -> Path:
    """Converts normalized findings into standard SARIF 2.1.0 JSON format."""
    ...
```

---

## 5. Pluggable LLM Provider Layer (`src/rush/providers/`)

```python
class LLMProvider(ABC):
    @abstractmethod
    def review(
        self, files: dict[str, str], instructions: str | None = None
    ) -> list[Finding]:
        """Review code files using provider LLM."""
        ...


class AnthropicProvider(LLMProvider): ...


class OpenAIProvider(LLMProvider): ...
```

---

## 6. Execution Permissions (`src/rush/permissions.py`)

```python
@dataclass(frozen=True)
class ExecutionPermissions:
    allow_network: bool = False
    allow_download: bool = False
    allow_cache_write: bool = False
    allow_build: bool = False
    allow_slow: bool = False
    allow_artifact_write: bool = False
    allow_browser: bool = False
```

---

## 7. Agent Safety & Worktree Sandboxing (`src/rush/safety/`)

```python
class AgentSafetyGuard:
    """Intercepts destructive shell commands and validates repository boundary paths."""

    def inspect_command(self, cmd: str) -> tuple[bool, str | None]: ...
    def inspect_path(self, path: Path) -> tuple[bool, str | None]: ...


class SecretRedactor:
    """Shannon-entropy and regex secret scrubber for logs and stdout streams."""

    def redact_text(self, text: str) -> str: ...
```

---

## 8. Token Economy & CodeGraph Slicing (`src/rush/token_economy/`, `src/rush/codegraph/`)

```python
class FastBPETokenCounter:
    """Calculates exact Byte-Pair Encoding token counts for model context windows."""

    def count_tokens(self, text: str) -> int: ...


class PythonAstOutlineCompressor:
    """Compresses Python AST by preserving signatures while stripping function bodies."""

    def compress_source(self, source_code: str) -> str: ...


class CodeGraphStore:
    """SQLite-backed Code Property Graph index store for symbols and call paths."""

    def insert_node(self, node: GraphNode) -> None: ...
    def find_nodes_by_symbol(self, symbol_name: str) -> list[GraphNode]: ...
```

---

## 9. Full-Stack Static Sync & Codebase Hygiene (`src/rush/sync/`, `src/rush/hygiene/`)

```python
class TypeScriptContractGenerator:
    """Transpiles OpenAPI JSON schemas into typed TypeScript interface declarations."""

    @staticmethod
    def generate_interfaces(openapi_json: str) -> str: ...


class ASTConflictMerger:
    """Reconciles conflicting Python ASTs across 3-way Git merge branches."""

    @staticmethod
    def merge_source_files(
        base: str, branch_a: str, branch_b: str
    ) -> tuple[bool, str]: ...
```

---

## 10. Bundle Budgets & Git Hotspots Analytics (`src/rush/bundle/`, `src/rush/hotspots/`)

```python
class BundleChunkCalculator:
    """Measures raw, Gzip, and Brotli chunk transfer sizes across build dist directories."""

    @staticmethod
    def measure_directory(dist_dir: Path) -> list[ChunkSizeReport]: ...


class RiskMatrixCalculator:
    """Computes composite defect risk scores by combining commit churn and McCabe cyclomatic complexity."""

    def analyze_hotspots(self) -> list[HotspotRiskScore]: ...
```

---

## 11. Agent Governance, Pre-Commit Hooks & Quality Scorecard (`src/rush/governance/`, `src/rush/hook/`, `src/rush/score/`)

```python
class AgentsMdSynchronizer:
    """Compiles canonical AGENTS.md instructions to .cursorrules, .clinerules, etc."""

    def sync_all(self) -> list[SyncResult]: ...


class FastIncrementalAstLinter:
    """Sub-millisecond AST parser for Git staged Python source files."""

    @staticmethod
    def lint_staged_python(file_paths: list[Path]) -> list[str]: ...


class CompositeScorecardCalculator:
    """Computes deterministic 0–100% 6-pillar quality scores and letter grades."""

    @classmethod
    def compute_scorecard(cls, pillars: PillarScores) -> ScorecardReport: ...
```

## 12. Phase 50a Quality & Security Subsystem Contracts (`src/rush/tools/`)

```python
class ErrorCatalogTool(ToolFn):
    """Polyglot exception parser producing RFC 7807 problem details catalogs across Python, TypeScript, and Rust."""
    name: str = "error-catalog"


class LicenseMatrixTool(ToolFn):
    """Audits pyproject.toml, package.json, and Cargo.toml for copyleft and license risks."""
    name: str = "license-matrix"


class IamAuditTool(ToolFn):
    """Statically parses multi-cloud SDK calls (AWS/GCP/Azure) and Terraform wildcard actions to synthesize minimal policies."""
    name: str = "iam-audit"
```

For guidelines on creating new tools or engines, see the [Developer Guide](DEVELOPER_GUIDE.md), [Tool Development Guide](developer/tool-development.md), and [Engine Development Guide](developer/engine-development.md).


## 13. Phase 50b Tools (`src/rush/tools/`)
- `ProvenanceAiTool`: Subclasses `ToolFn`. Audits AI code attribution and provenance via Git trailers.
- `DeadAssetTool`: Subclasses `ToolFn`. Scans unreferenced static assets and computes space savings.
- `PrSynthesizeTool`: Subclasses `ToolFn`. Synthesizes semantic PR markdown card with risk tiering and CODEOWNERS routing.

## 14. Phase 50c Tools (`src/rush/tools/`)
- `AttestationTool`: Generates in-toto Statement v1 unsigned provenance drafts.
- `MemProfileTool`: Analyzes static unclosed resources and samples dynamic RSS memory.
- `ColdStartTool`: Identifies heavy top-level imports and parses `-X importtime`.
- `OfflineReviewTool`: Executes air-gapped local ONNX code review.
- `BenchmarkTool`: Compares performance samples against baselines using stdlib `statistics`.

### 1.2 File I/O & Containment Primitives (`rush.io`) (Phase 55)

- **`rush.io.PhysicalRoot(root_path: Path | str)`**:
  - `open_contained(relative_path: Path | str, purpose: str = "read") -> Path`: Validates that `relative_path` is contained strictly within `root_path`. Rejects absolute paths, traversal (`..`), symlinks, and Windows reparse points fail-closed.
- **`rush.io.AtomicFile(physical_root: PhysicalRoot)`**:
  - `write_bytes(relative_path: Path | str, content: SanitizedBytes | SanitizationResult) -> Path`: Writes bytes atomically with fsync durability and owned temp cleanup.
  - `write_json(relative_path: Path | str, content: SanitizedJsonValue | SanitizationResult) -> Path`: Writes sanitized JSON structures atomically.
- **`rush.io.SanitizedBytes(data: bytes, redaction_count: int = 0)`**: Wrapper for sanitized byte data.
- **`rush.io.SanitizedJsonValue(value: Any, redaction_count: int = 0)`**: Wrapper for sanitized JSON structures.
- **`rush.io.VerifierRecord`**:
  - `create(raw_capability: str | bytes, *, work_factor: int = 100_000, algorithm: str = "pbkdf2_sha256") -> VerifierRecord`: Creates non-recoverable verifier.
  - `verify(candidate: str | bytes) -> bool`: Verifies candidate in constant time.
  - `to_dict() -> dict[str, Any]` and `from_dict(data: dict[str, Any]) -> VerifierRecord`.

### rush.plugins (Phase 56 Primitives)
- `PluginClosureManifest`: Cryptographic closure covering code, config, env names, runtime, and platform.
- `build_plugin_closure(plugin_root, entrypoint, config, allowed_env_names, declared_secret_refs)`: Constructs verified closure manifest.
- `PluginSnapshotStore`: Manages immutable byte snapshots in `~/.rush/snapshots/<closure_digest>/` under `PhysicalRoot`.
- `PluginTrustStore`: User-owned trust ledger managing authorization records via `AtomicFile` and `VerifierRecord`.
- `HardenedPluginExecutor`: Pre-spawn reverification, protected secret channel negotiation, and `ToolResultV1` execution.
- `SecretDeliveryContext`: Transport parameters for descriptor pipe, stdin handshake, or provider channels.

## `rush.invocation` Module Reference (Phase 57)

The `rush.invocation` subsystem coordinates unified execution across CLI and MCP:
- `InvocationContext`: Frozen dataclass containing workspace root, transport, operation ID, physical targets, config digest, permissions, and build identities.
- `PhysicalTarget`: Frozen dataclass describing contained target path, state (`present|deleted|renamed`), capability, provenance, and SHA-256 content hash.
- `resolve_invocation(request, transport, ...)`: Normalizes arguments and constructs authoritative `InvocationContext`.
- `decide_cache(context, pure=True)`: Determines cache eligibility and derives deterministic SHA-256 cache key.
- `InvocationExecutor`: Registers operations, adapts callable signatures, and executes operations under a single execution boundary.

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
### Module `rush.release.provenance_policy`
- `StatementV1`, `SLSAPredicateV1`, `ProvenanceDraft`: Immutable AST models for in-toto Statement v1.
- `StrictProvenanceParser`: Strict JSON parser rejecting duplicate and ambiguous keys.
- `SignedProvenancePolicy`, `ProvenancePolicyVerifier`: DSSE cryptographic envelope verification.

### Module `rush.engines.support_policy`
- `EngineSupportPolicy`: Taxonomy loader and conformance validator.

## `rush.memory` Module Reference (Phase 61)

### Module `rush.memory.store`
- `MemoryArtifact`: frozen dataclass carrying `id`, `family`, `subject`, `trust_tier`, `content`, `source`, `created_at`, `symbol_ref`, `content_hash`, `corroboration_count`, `promoted_at`, `stale`, `signature`, `origin_kind`, `origin_id`, and `expired`. The database additionally stores `expires_at`, `expired_at`, and `expired_by`; hydration derives `expired` from `expired_at`.
- `TypedArtifactStore`: `write()`, `promote(id, user_stated=..., candidate_sources=...)`, `recall(subject, query, session_allowlist)`, and `search(subject, query)`. `promote()` evaluates persisted sanitized content and returns the stored artifact plus `PromotionResult`; approval atomically persists the tier, checksum, timestamp, and corroboration count. `search()` provides raw FTS5 matches for internal existence/rank checks; callers consuming content must use defended `recall()`. SQLite WAL, `.rush/memory.db`.

### Module `rush.memory.trust`
- `TrustTier` (`STATED`/`DERIVED`/`EXTERNAL_WRITE`/`IMPORTED`), `PromotionDenialReason`, `PromotionResult`.
- `default_entry_tier(source_kind)`: never returns `"STATED"`.
- `evaluate_promotion(artifact, *, user_stated)`: composed ALLOW/REDACT/BLOCK screen, regex pre-filter, schema-completeness check, grounding check (`resolve_symbol_ref`), corroboration threshold (`count_corroboration`).
- `evaluate_conflict(new_artifact, existing_stated_artifact)`: `Literal["add","update","delete","none"]` reconciliation against an existing `STATED` row.

### Module `rush.memory.migration`
- One idempotent function per absorbed source: `migrate_preference_store`, `migrate_invariant_graph`, `migrate_checkpoint_journal`, `migrate_failure_ledger`, `migrate_patch_memory`, `migrate_flight_recorder`, `migrate_hook_signatures`, `migrate_session_memory`.

### Module `rush.memory.transport`
- `dispatch(root, tool, source, content, granted, *, acp_command=None, timeout_seconds=30)`: per-tool native Claude SDK → ACP → dedicated-file selection. ACP requires the optional `acp` SDK and explicit adapter argv; no provider command is guessed. SDK/ACP delivery requires network permission, denies tool execution, and returns success only after a terminal protocol acknowledgement. Delivery errors and timeouts return `error`; capability absence uses the artifact-write-gated file fallback. Acknowledgement confirms delivery, not durable model memory. This synchronous API must be called outside an active event loop.

## `rush.memory` Module Reference (Phase 62)

### Module `rush.memory.maintenance`
- `run_maintenance_cycle(task, *, batch_size=500, project_root=None)`: dispatches to one of 4 `MaintenanceTask` variants (`promotion_sweep`/`staleness_sweep`/`skill_admission_check`/`expiry_sweep`). The supplied root scopes the store, lock, expiry, and grounding checks. Acquires/releases a `MeshLockManager` lease; per-row failures enter `MaintenanceRunResult.errors`. Public CLI/MCP calls require cache-write permission before constructing resources.

### Module `rush.memory.expiry`
- `ExpiryPolicy`, `DEFAULT_POLICIES`: first-match-wins `(subject, trust_tier)` TTL table (`"*"` subject wildcard) — `STATED` never expires, `DERIVED` 14 days, `EXTERNAL_WRITE` 30 days, `IMPORTED` 90 days.
- `sweep_expired()`: stamps `expired_at`/`expired_by` on rows past their configured TTL; dispatched from `run_maintenance_cycle("expiry_sweep")`.

### Module `rush.memory.decision_schema`
- `DecisionRecordFields`: remediation-shaped fields (7 total) reused by `mistake_miner.py`'s pure candidate-shaping function; `status` defaults `"in_progress"`, accepts `"completed"`.

### Module `rush.token_economy.memory_cache_gate`
- `check_memory_before_pack(context_path, target_symbol, subject="domain_knowledge")`: defended `search()`-then-`recall()` cache lookup wired into `pack_context()` immediately before `ContextPacker.pack()`. On a miss, `pack_context()` separately writes a `DERIVED` row only with cache-write permission. Cache fills retain the file's content hash for symbol and whole-file packs; changed, missing, or unreadable files invalidate the cached content.

### Module `rush.tools.memory`
- `MemoryTool(ToolFn)`: `name = "memory"`, operations `ask`/`write`/`promote`/`list`/`recall`/`maintain`, returns canonical `ToolResult` dictionaries. All content queries require a session allowlist and apply recall defenses. Writes, promotions, and maintenance require cache-write permission; maintenance operates on the requested `path`.
- `FixedPathEnvironment`: Context manager for isolated PATH execution.
