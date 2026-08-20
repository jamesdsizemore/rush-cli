# Tool Development & Registration Guide

This guide details how to implement, register, and test a new quality tool in `src/rush/tools/`.

---

## 1. Tool Lifecycle & Architecture

Every tool is an instance of `ToolFn` defined in `src/rush/tools/base.py`.

```python
class MyTool(ToolFn):
    name = "mytool"
    description = "Deterministic code analysis tool."

    def run(
        self,
        path: Path,
        *,
        config: RushConfig | None = None,
        permissions: ExecutionPermissions | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Internal execution with typed configs and permissions."""
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
        """FastMCP schema surface."""
        ...
```

---

---

## 2. 7-Step Tool Registration Checklist

1. **Implement Tool Class**: Create `src/rush/tools/<name>.py` extending `ToolFn` (e.g. `TddGuardTool`).
2. **Register in `ALL_TOOLS`**: Add instance to `src/rush/tools/__init__.py` (maintaining 35 tools).
3. **Register in Catalog**: Add `ToolSpec` to `src/rush/catalog.py` under `TOOL_SPECS` and update `CATALOG_TOOLS_MATURITY`.
4. **Register Engine Adapters**: Add engine classes in `src/rush/engines/` and register in `ENGINES` dictionary in `src/rush/engines/__init__.py`.
5. **Add Fixtures & Reference Tests**: Add JSON fixtures to `tests/fixtures/engine_reports/` and reference test suite `tests/test_<engine>_reference.py`.
6. **Update Parity Audit**: Add fixture suite path to `PARSER_FIXTURE_SUITES` in `src/rush/catalog.py`.
7. **Synchronize All 130 Docs**: Run `python scripts/sync_docs.py --update` to verify and auto-sync all documentation files across the repository.

---

## 3. Exporter & Reporting Integration

All `ToolFn` executions support unified artifact generation:
- **CLI Exporter Flags**:
  - `--export-html <path>`: Generates standalone interactive dashboard via `src/rush/html_export.py`.
  - `--export-sarif <path>`: Generates standard static analysis interchange JSON via `src/rush/sarif.py`.
  - `--json`: Emits raw `ToolResult` JSON payload.
- **FastMCP Protocol Integration**:
  - Tools expose clean JSON-serializable parameters on `__call__`.
  - Stdio messages strictly use `stdout` for JSON-RPC frames while diagnostics write to `stderr`.

See [Engine Development](engine-development.md) and [Coding Standards](coding-standards.md).
