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

### 1.1 Result Schema Kernel & Contracts (Phase 54)

Every tool output is validated against the canonical `ToolResultV1` schema (`schema_version: "1.0.0"`) defined in `src/rush/contracts/results.py`:
- Use `ToolResultV1` and `FindingV1` dataclasses for typed, fail-closed results.
- `serialize_tool_result()` automatically sanitizes secrets (Phase 53) and enforces validation (Phase 54).
- Legacy dictionaries can be migrated via `adapt_legacy_tool_result()` and `adapt_legacy_finding()`.
- Operation routing is managed via `src/rush/contracts/operations.py` (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`).

---

---

## 2. 7-Step Tool Registration Checklist

1. **Implement Tool Class**: Create `src/rush/tools/<name>.py` extending `ToolFn` (e.g. `TddGuardTool`).
2. **Register in `ALL_TOOLS`**: Add instance to `src/rush/tools/__init__.py` (maintaining 52 tools across core and flagship suites).
3. **Register in Catalog**: Add `ToolSpec` to `src/rush/catalog.py` under `TOOL_SPECS` and update `_TOOL_MATURITY`.
4. **Register Engine Adapters**: Add engine classes in `src/rush/engines/` and register in `ENGINES` dictionary in `src/rush/engines/__init__.py`.
5. **Add Fixtures & Reference Tests**: Add JSON fixtures to `tests/fixtures/engine_reports/` and reference test suite `tests/test_<engine>_reference.py`.
6. **Update Parity Audit**: Add fixture suite path to `PARSER_FIXTURE_SUITES` in `src/rush/catalog.py`.
7. **Synchronize Docs**: Update user guides, CLI reference, and tool guides under `docs/tools/`.

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

## Developing Ship Vectors and Distillers (Phases 41–43)
* Implement distillers by extending `BaseDistiller` in `src/rush/token_economy/distillers/base.py`.
* Implement ship vectors by creating modular linters in `src/rush/tools/ship/` and adding them to `ShipCockpit.evaluate_gate()`.

## Developing Phase 50a Quality & Security Catalog Tools
* **Polyglot Error Extraction (`error-catalog`)**: Inherit from `ToolFn`, implement language-specific AST and regex extractors (`.py`, `.ts`, `.rs`), map exceptions to RFC 7807 problem details, and gate markdown export behind `--allow-artifact-write`.
* **Dependency License Compliance (`license-matrix`)**: Parse package manifests (`pyproject.toml`, `package.json`, `Cargo.toml`), normalize licenses to SPDX identifiers, and classify into Permissive, Weak Copyleft, Strong Copyleft, or ManualReview.
* **Least-Privilege IAM Audit (`iam-audit`)**: Parse multi-cloud SDK calls (AWS boto3, GCP google.cloud, Azure blob), scan Terraform `.tf` configurations for wildcard actions (`*`), synthesize minimal least-privilege JSON policies, and gate export behind `--allow-artifact-write`.


### Phase 50b: Attribution & PR Evidence Tools
- `provenance-ai`: Parses Git log trailers (`Co-authored-by:`, `Generated-by:`, `Model:`, `Agent:`), detects shallow clones, and records survival state.
- `dead-asset`: Polyglot asset cross-referencing across templates, styles, and scripts; computes potential savings; guarded pruning strictly gated.
- `pr-synthesize`: Evaluates `git diff --numstat`, aggregates quality evidence, computes risk tier (`low`/`medium`/`high`), and routes CODEOWNERS.

### Phase 50c: Performance Profiling, Offline Review & Provenance Tools
- `attest`: Generates in-toto Statement v1 / SLSA v1.0 unsigned drafts binding real artifact hashes from `dist/`.
- `mem-profile`: Static AST unclosed resource analysis and dynamic memory sampling guarded by `--allow-slow`.
- `cold-start`: Static heavy top-level import detection and dynamic `-X importtime` execution under `--allow-slow`.
- `offline-review`: Local air-gapped ONNX review runner; gracefully skips when ONNX models or runners are absent.
- `benchmark`: Repeated benchmark execution using stdlib `statistics`, storing baselines in `.rush/baselines.json`.
