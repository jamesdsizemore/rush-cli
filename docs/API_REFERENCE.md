# Python Internal API Reference

## Session continuity

`rush.tools.continuity.SessionContinuityTool.run(path, operation, name, files, handoff, permissions)` returns the canonical `ToolResult`. Operations are `save`, `list`, and `restore`; `save` is `skipped` without explicit cache-write permission, and a missing checkpoint is `skipped` rather than an exception. `handoff` accepts `current_goal`, `open_work`, `historic_instruction`, `failure_fingerprint`, and repository-relative `dependencies`; the persisted result exposes only the redacted receipt in `metadata.handoff`.

Coordination operations are `coordination_check`, `coordination_merge_preview`, and `coordination_recovery`. They return `metadata.coordination` evidence only: ownership state, manual-recovery/manual-reconciliation actions, conflict names, and bounded replay/failure receipt metadata. They do not write locks, merge code, execute a replay, or return a failed patch.

`operation="provider_resume"` accepts a checkpoint `name` and `provider_id`. Enabled direct CLI IDs are `claude_code`, `codex_cli`, and `antigravity_cli`; `omniroute_api` is a fixed `127.0.0.1:20128/v1/chat/completions` adapter using `model: "auto"`. Each requires `ExecutionPermissions(network=True)`. The route receives a bounded goal/frontier/freshness projection, never a raw transcript, historic instruction, failed patch, provider credential, or returned model text. `zai` is deliberately `skipped` as deferred and `9router_api` stays unavailable until its key/model contract is implemented.

Rush is packaged as a local CLI application and stdio Model Context Protocol (MCP) server. While Rush does not expose an external programmatic Python library, internal contributors and custom tool authors interact with the following stable core contracts in `src/rush/`.

---

## 1. Core Tool Contract (`src/rush/tools/base.py`)

### `ToolFn`
### `ToolFn`
The abstract base class for all 35 Rush tools.
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
    def review(self, files: dict[str, str], instructions: str | None = None) -> list[Finding]:
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
    def merge_source_files(base: str, branch_a: str, branch_b: str) -> tuple[bool, str]: ...
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

For guidelines on creating new tools or engines, see the [Developer Guide](DEVELOPER_GUIDE.md), [Tool Development Guide](developer/tool-development.md), and [Engine Development Guide](developer/engine-development.md).

