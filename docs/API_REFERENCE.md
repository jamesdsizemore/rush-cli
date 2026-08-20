# Python Internal API Reference

Rush is packaged as a local CLI application and stdio Model Context Protocol (MCP) server. While Rush does not expose an external programmatic Python library, internal contributors and custom tool authors interact with the following stable core contracts in `src/rush/`.

---

## 1. Core Tool Contract (`src/rush/tools/base.py`)

### `ToolFn`
The abstract base class for all 34 Rush tools.
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
The abstract adapter for external quality binaries:
```python
class Engine:
    name: str
    binary: str

    def is_available(self) -> bool:
        """Checks whether binary exists on PATH."""
        ...

    def run(self, target: Path, options: dict[str, Any]) -> ToolResult:
        """Executes engine with run_subprocess and normalizes stdout/stderr to ToolResult."""
        ...
```

---

## 3. Subprocess Isolation (`src/rush/tools/common.py`)

```python
def run_subprocess(
    argv: list[str],
    cwd: Path | str | None = None,
    timeout: float = 120.0,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Runs external commands with stdin=DEVNULL, shell=False, and stdout/stderr capture."""
    ...
```

---

## 4. Execution Permissions (`src/rush/permissions.py`)

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

For guidelines on creating new tools or engines, see the [Developer Guide](DEVELOPER_GUIDE.md), [Tool Development Guide](developer/tool-development.md), and [Engine Development Guide](developer/engine-development.md).
