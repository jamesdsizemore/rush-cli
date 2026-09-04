# Phase 54 Implementation Plan — ToolResultV1 Schema Kernel and Operation Adapters

## 1. Purpose and Status

- **Operation:** Create the implementation plan for remediation Phase 54 (Remediation Phase 3).
- **Planning status:** Implementation-ready after §4 admission gate passes.
- **Implementation status:** Not authorized (Planning & Review Phase).
- **Authority:** Governing Roadmap finding R-011 schema-definition requirements (`docs/developer/repository-remediation-plan.md`).
- **Predecessor:** Accepted Phase 53 sanitization kernel, write boundaries, and JSON-safe value contract (`src/rush/safety/redactor.py:sanitize_value`, `governance/remediation-phase-53.toml`).
- **Successors:** Phase 56 consumes the plugin adapter (`ToolOperationAdapter`); Phase 57 migrates public tools and generic invocation; Phase 58 completes eligible runtime tool producer migration.
- **Scope Boundary:** Define, validate, and prove the `rush.contracts` schema kernel, deterministic serializer, legacy adapters, and operation adapter registry in isolation. Do NOT claim repository-wide runtime tool migration in this phase.
- **Protected Boundaries:** Roadmap, CLI/MCP command registrations, plugin execution engine, persistence/patch writers, `pyproject.toml`, `uv.lock`.
- **Amendment Rule:** Add any new schema field, vocabulary, compatibility mapping, adapter class, or write path to this plan before implementation.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite without explicit user instruction.

---

## 2. Authority, Evidence, and Closed Decisions

### 2.1 Authority Order
User Instructions → `AGENTS.md` → `GEMINI.md` → `docs/developer/repository-remediation-plan.md` (Roadmap) → `governance/remediation-contracts.toml` (Finding R-011) → Phase 53 Sanitizer Contract → current `src/rush/tools/base.py` and `src/rush/tools/common.py`.

### 2.2 Current Baseline Evidence
- `src/rush/tools/base.py` declares `Finding` severity as `Severity = Literal["info", "warn", "error"]`, while engines and exporters emit `fail` and `warning`.
- `src/rush/tools/common.py:normalize_findings` silently coerces unknown severities to `default_severity` ("warn"), disguising unhandled engine formats.
- `src/rush/tools/base.py:ToolResult` lacks a `schema_version` field, allowing unversioned payloads to circulate.
- Arbitrary untyped dictionary keys and prose error strings are returned across different tools and manual MCP wrappers without a central validation gate.
- `governance/public-operations.toml` catalogs 146 public operations across 3 kinds (`67 tool`, `62 admin`, `17 service`), but lacks a formal runtime adapter registry binding each operation to its target contract.

### 2.3 Closed Decisions (Immutable Architecture Invariants)
1. **Tool Status Vocabulary:** Statuses are strictly `Literal["ok", "warn", "fail", "error", "skipped"]`. No other values are permitted.
2. **Finding Severity Vocabulary:** Canonical severities in `FindingV1` are strictly `Literal["info", "warning", "error"]`.
3. **Deterministic Legacy Severity Mapping:**
   - Legacy finding severity `"warn"` maps strictly to `"warning"`.
   - Legacy finding severity `"fail"` maps strictly to `"error"`.
   - Legacy finding severity `"info"` maps strictly to `"info"`.
   - Legacy finding severity `"error"` maps strictly to `"error"`.
   - Legacy finding severity `"warning"` maps strictly to `"warning"`.
   - Any unknown/missing severity that cannot be adapted raises a structured `ValidationErrorV1(code="INVALID_SEVERITY", ...)`. Silent default coercion is strictly prohibited.
4. **Schema Versioning:** `ToolResultV1.schema_version` is the exact string constant `"1.0.0"`.
5. **Top-Level Rejection:** Any unapproved top-level key outside the canonical specification is rejected with `ValidationErrorV1(code="UNKNOWN_TOP_LEVEL_KEY", ...)`.
6. **Namespaced Extensions:** Optional and engine-specific metadata (`metrics`, `artifacts`, `metadata`, `review_kind`, `review_provider`, etc.) must reside within the `extensions: dict[str, Any]` dictionary. Extension keys must be valid namespaced identifiers.
7. **Canonical Validation Errors:** When validation fails, functions return or raise a structured `ValidationErrorV1` with `code`, `message`, `path`, and `invalid_value`. Raw dictionary dumps or unstructured prose error strings are forbidden.
8. **Dependency Invariant (Pure Python Standard Library):** Pydantic and external schema libraries are strictly prohibited. The schema kernel must be built exclusively using Python 3.12 standard library `dataclasses`, `typing`, `json`, and the Phase 53 `sanitize_value` redactor kernel.
9. **Sanitization Precedence:** Input data is sanitized via `rush.safety.redactor:sanitize_value` *prior* to validation and serialization, guaranteeing that validated V1 artifacts never disclose secrets.
10. **Operation Classification Boundary:**
    - `kind = "tool"` operations (67 operations) MUST target `ToolResultV1`.
    - `kind = "admin"` operations (62 operations) MUST target their named admin contracts (e.g., `ClickExitCode`, `AdminJsonContract`), and use `ToolResultV1` only when specifically designated.
    - `kind = "service"` operations (17 operations) MUST target protocol/liveness frames. Service protocol messages (such as stdio JSON-RPC `initialize` and `tools/list`) are NEVER wrapped in `ToolResultV1`.

---

## 3. Goals, Outcomes, Exclusions, and Invariants

### 3.1 Outcomes
- New package `src/rush/contracts/` containing:
  - `src/rush/contracts/__init__.py`: Public contract exports.
  - `src/rush/contracts/results.py`: `ToolResultV1`, `FindingV1`, `ValidationErrorV1`, `validate_tool_result`, `validate_finding`, `serialize_tool_result`, `adapt_legacy_finding`, and `adapt_legacy_tool_result`.
  - `src/rush/contracts/operations.py`: `OperationAdapter` hierarchy (`ToolOperationAdapter`, `AdminOperationAdapter`, `ServiceOperationAdapter`) and `OperationRegistry`.
- Exact test fixtures in `tests/fixtures/remediation/`:
  - `tool_result_v1_valid.json`: Canonical valid V1 result payload.
  - `tool_result_v1_invalid.json`: Test suite of invalid payloads exercising every validation failure code.
- Contract test suites:
  - `tests/test_phase54_result_schema.py`: 7 tests covering V1 schema, severities, namespacing, deterministic serialization, legacy mappings, and error shapes.
  - `tests/test_phase54_operation_adapters.py`: 4 tests covering tool, admin, service adapters, and 100% reconciliation of all 146 operations from `governance/public-operations.toml`.
- Total Phase 54 contract tests: 11 tests. Total test suite baseline: 1,041 + 11 = 1,052 passed tests.
- Complete documentation alignment across `/docs` and all subfolders.

### 3.2 Exclusions
- Do NOT rewrite or alter runtime tool implementations in `src/rush/tools/` (runtime migration is owned by Phase 57 and Phase 58).
- Do NOT alter CLI command signatures or MCP tool registrations in this phase.
- Do NOT add external dependencies to `pyproject.toml`.

### 3.3 Core Invariant: Zero Simulated Completion & Zero Downscoping
- Never propose, suggest, or execute downscoping to match degraded code.
- Zero placeholder or deferred stubs returning `"unknown"`, `"deferred"`, or simulated dictionaries.
- Zero tautological or permissive test assertions (`assert val in ("ok", "warn", "skipped")` is forbidden for contract tests; assert exact domain values).
- All 11 contract tests must assert exact computations against realistic fixtures.

---

## 4. Admission and Predecessor Gate

Before starting Phase 54 implementation, verify that all predecessor conditions are met:

```powershell
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 1. Verify Phase 53 completed and clean in governance
.venv/Scripts/python.exe -c "import tomllib; d=tomllib.load(open('governance/remediation-phase-53.toml', 'rb')); assert d['phase']['status'] == 'completed'; print('Phase 53 Status: OK')"

# 2. Verify Phase 53 sanitization kernel is operational
.venv/Scripts/python.exe -c "from rush.safety.redactor import sanitize_value; res = sanitize_value({'key': 'sk-ant-api03-12345'}); assert 'sk-ant-api03-12345' not in str(res.sanitized); print('Sanitizer Kernel: OK')"

# 3. Verify test baseline (1,041 passing)
.venv/Scripts/python.exe -m pytest tests/ -q

# 4. Verify clean linter baseline
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
```

## 5. Requirement-Ownership Ledger

| Finding / Requirement | Description | Assigned Tasks | Verifiable Closure Proof |
|---|---|---|---|
| **R-011.1** | `ToolResultV1` & `FindingV1` schema specification | P54.1.1, P54.1.2 | `tests/test_phase54_result_schema.py::test_tool_result_v1_requires_exact_fields_and_vocabularies` |
| **R-011.2** | Strict rejection of unknown top-level keys & severities | P54.1.1, P54.1.2 | `tests/test_phase54_result_schema.py::test_finding_v1_rejects_unknown_severity` |
| **R-011.3** | Namespaced JSON-safe extension boundary | P54.1.1, P54.1.2 | `tests/test_phase54_result_schema.py::test_extensions_are_namespaced_json_safe` |
| **R-011.4** | Deterministic canonical JSON serialization | P54.1.1, P54.1.2 | `tests/test_phase54_result_schema.py::test_serializer_is_deterministic` |
| **R-011.5** | Exact legacy mapping (`warn`→`warning`, `fail`→`error`) | P54.2.1, P54.2.2 | `tests/test_phase54_result_schema.py::test_legacy_warn_maps_only_to_warning`, `test_legacy_fail_maps_only_to_error` |
| **R-011.6** | Structured `ValidationErrorV1` (no raw fallback) | P54.2.1, P54.2.2 | `tests/test_phase54_result_schema.py::test_unknown_legacy_value_returns_canonical_validation_error` |
| **R-011.7** | Operation adapter hierarchy (`tool`, `admin`, `service`) | P54.3.1, P54.3.2 | `tests/test_phase54_operation_adapters.py::test_tool_operation_targets_tool_result_v1`, `test_admin_operation_uses_named_contract`, `test_service_liveness_is_not_wrapped_as_tool_result` |
| **R-011.8** | 100% manifest operation reconciliation (146 ops) | P54.3.1, P54.3.2 | `tests/test_phase54_operation_adapters.py::test_every_manifest_operation_has_one_adapter` |
| **R-011.9** | Exhaustive `/docs` updates & handoff governance | P54.4.1 | Documentation audit diff, `governance/remediation-phase-54.toml`, `docs/developer/phase-54-implementation-evidence.md` |

---

## 6. Shared Contracts and Data Specifications

### 6.1 `FindingV1` Data Specification (`src/rush/contracts/results.py`)

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

FindingSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class FindingV1:
    path: str
    line: int
    column: int
    rule_id: str
    severity: FindingSeverity
    message: str
    fingerprint: str
    rule: str | None = None
    fix: dict[str, Any] | None = None
    remediation: dict[str, Any] | str | None = None
    evidence: dict[str, Any] | str | None = None
    provenance: str | None = None
    freshness: str | None = None
    patch: str | None = None
    suggested_fix: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
```

**Validation Invariants for `FindingV1`:**
1. `path`: Must be a string with forward slashes; empty string permitted for project-level findings.
2. `line`: Integer >= 0.
3. `column`: Integer >= 0.
4. `rule_id`: Non-empty string.
5. `severity`: Strictly one of `"info"`, `"warning"`, `"error"`.
6. `message`: Non-empty redacted string.
7. `fingerprint`: 64-character lowercase hexadecimal SHA-256 string.
8. `extensions`: Must be a dictionary containing only JSON-safe primitives, lists, and dicts.
9. Any unknown key outside the above fields raises `ValidationErrorV1(code="UNKNOWN_TOP_LEVEL_KEY", ...)`.

### 6.2 `ToolResultV1` Data Specification (`src/rush/contracts/results.py`)

```python
ToolStatus = Literal["ok", "warn", "fail", "error", "skipped"]


@dataclass(frozen=True)
class ToolResultV1:
    schema_version: Literal["1.0.0"]
    tool: str
    engine: str | None
    engine_version: str | None
    status: ToolStatus
    duration_ms: int
    summary: str
    findings: list[FindingV1]
    raw: Any | None = None
    extensions: dict[str, Any] = field(default_factory=dict)
```

**Validation Invariants for `ToolResultV1`:**
1. `schema_version`: Must be exactly `"1.0.0"`.
2. `tool`: Non-empty string identifying the tool (e.g., `"lint"`).
3. `engine`: String or `None`.
4. `engine_version`: String or `None`.
5. `status`: Strictly one of `"ok"`, `"warn"`, `"fail"`, `"error"`, `"skipped"`.
6. `duration_ms`: Integer >= 0.
7. `summary`: String.
8. `findings`: List of valid `FindingV1` instances.
9. `raw`: Optional JSON-safe data (strings, numbers, booleans, lists, dicts, or `None`). Opaque objects must be sanitized.
10. `extensions`: Dictionary of namespaced JSON-safe values. Any non-core fields (`metrics`, `artifacts`, `metadata`, `review_kind`, `review_provider`) reside here.
11. Any unknown top-level key outside the 10 defined fields raises `ValidationErrorV1(code="UNKNOWN_TOP_LEVEL_KEY", ...)`.

### 6.3 Structured Validation Error (`ValidationErrorV1`)

```python
@dataclass(frozen=True)
class ValidationErrorV1(Exception):
    code: str
    message: str
    path: str
    invalid_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "validation_error",
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "invalid_value": (
                self.invalid_value
                if isinstance(self.invalid_value, (str, int, float, bool, type(None)))
                else str(self.invalid_value)
            ),
        }

    def __str__(self) -> str:
        return f"[{self.code}] at '{self.path}': {self.message}"
```

**Canonical Error Codes:**
- `MISSING_REQUIRED_FIELD`: A required field (e.g., `schema_version`, `tool`, `summary`) is absent.
- `UNKNOWN_TOP_LEVEL_KEY`: An unrecognized key was found at the top level of `ToolResultV1` or `FindingV1`.
- `INVALID_STATUS`: The status is not in `("ok", "warn", "fail", "error", "skipped")`.
- `INVALID_SEVERITY`: The severity is not in `("info", "warning", "error")`.
- `INVALID_SCHEMA_VERSION`: The schema version is not `"1.0.0"`.
- `INVALID_TYPE`: A field value does not match its required type (e.g., negative duration, non-integer line).
- `NON_JSON_SAFE_VALUE`: An extension or raw field contains an un-serializable/opaque object.
- `UNNAMESPACED_EXTENSION`: An extension key does not conform to valid naming conventions.

### 6.4 Serialization and Conversion Functions

```python
def validate_finding(data: Any, path_prefix: str = "findings") -> FindingV1:
    """Validate raw mapping or object against FindingV1 contract."""
    ...


def validate_tool_result(data: Any) -> ToolResultV1:
    """Validate raw mapping or object against ToolResultV1 contract."""
    ...


def serialize_tool_result(result: ToolResultV1 | dict[str, Any]) -> str:
    """Sanitize, validate, and serialize ToolResultV1 to byte-deterministic JSON string.

    Uses json.dumps with sort_keys=True, separators=(',', ':'), ensure_ascii=False.
    """
    ...


def adapt_legacy_finding(legacy: dict[str, Any]) -> FindingV1:
    """Convert a legacy Finding dictionary into a canonical FindingV1 instance.

    Maps: 'warn' -> 'warning', 'fail' -> 'error'. Rejects unknown severities.
    """
    ...


def adapt_legacy_tool_result(legacy: dict[str, Any]) -> ToolResultV1:
    """Convert a legacy ToolResult dictionary into a canonical ToolResultV1 instance.

    Sets schema_version='1.0.0', converts findings via adapt_legacy_finding,
    and packages extra fields (metrics, artifacts, metadata) into extensions.
    """
    ...
```

### 6.5 Operation Adapter Hierarchy (`src/rush/contracts/operations.py`)

```python
from abc import ABC, abstractmethod
from typing import Any, Literal

OperationKind = Literal["tool", "admin", "service"]


class BaseOperationAdapter(ABC):
    operation_id: str
    kind: OperationKind
    target_contract_id: str

    @abstractmethod
    def validate_output(self, output: Any) -> Any:
        """Validate that operation output conforms to target contract."""
        ...


class ToolOperationAdapter(BaseOperationAdapter):
    kind = "tool"
    target_contract_id = "ToolResultV1"

    def validate_output(self, output: Any) -> ToolResultV1:
        # Must return valid ToolResultV1 or raise ValidationErrorV1
        ...


class AdminOperationAdapter(BaseOperationAdapter):
    kind = "admin"

    def __init__(self, operation_id: str, target_contract_id: str):
        self.operation_id = operation_id
        self.target_contract_id = target_contract_id

    def validate_output(self, output: Any) -> Any:
        # Validates against named admin contract (e.g. ClickExitCode, AdminJson)
        ...


class ServiceOperationAdapter(BaseOperationAdapter):
    kind = "service"

    def __init__(self, operation_id: str, target_contract_id: str = "ServiceProtocol"):
        self.operation_id = operation_id
        self.target_contract_id = target_contract_id

    def validate_output(self, output: Any) -> Any:
        # Validates protocol message dict without ToolResult wrapping
        ...


class OperationRegistry:
    def __init__(self):
        self._adapters: dict[str, BaseOperationAdapter] = {}

    def register(self, adapter: BaseOperationAdapter) -> None:
        ...

    def get_adapter(self, operation_id: str) -> BaseOperationAdapter:
        ...

    def reconcile_manifest(self, manifest_path: Path) -> dict[str, Any]:
        """Verify that 100% of the 146 operations in public-operations.toml are registered."""
        ...
```

---

## 7. Contract-Test Inventory

| Test ID | Test Function | Test File | Target Contract Tested |
|---|---|---|---|
| **T-54.01** | `test_tool_result_v1_requires_exact_fields_and_vocabularies` | `tests/test_phase54_result_schema.py` | All 8 required fields, valid statuses, rejection of missing fields |
| **T-54.02** | `test_finding_v1_rejects_unknown_severity` | `tests/test_phase54_result_schema.py` | Severity must be `info|warning|error`; unknown raises `ValidationErrorV1` |
| **T-54.03** | `test_extensions_are_namespaced_json_safe` | `tests/test_phase54_result_schema.py` | Extensions dict must be JSON-safe; unknown top-level keys rejected |
| **T-54.04** | `test_serializer_is_deterministic` | `tests/test_phase54_result_schema.py` | Sorted keys, compact separators, identical bytes across insertion orders |
| **T-54.05** | `test_legacy_warn_maps_only_to_warning` | `tests/test_phase54_result_schema.py` | Legacy finding severity `warn` converts strictly to `warning` |
| **T-54.06** | `test_legacy_fail_maps_only_to_error` | `tests/test_phase54_result_schema.py` | Legacy finding severity `fail` converts strictly to `error` |
| **T-54.07** | `test_unknown_legacy_value_returns_canonical_validation_error` | `tests/test_phase54_result_schema.py` | Unmappable status/severity raises structured `ValidationErrorV1` |
| **T-54.08** | `test_tool_operation_targets_tool_result_v1` | `tests/test_phase54_operation_adapters.py` | All 67 `kind="tool"` operations bind to `ToolOperationAdapter` and `ToolResultV1` |
| **T-54.09** | `test_admin_operation_uses_named_contract` | `tests/test_phase54_operation_adapters.py` | All 62 `kind="admin"` operations bind to `AdminOperationAdapter` and named contracts |
| **T-54.10** | `test_service_liveness_is_not_wrapped_as_tool_result` | `tests/test_phase54_operation_adapters.py` | All 17 `kind="service"` operations bind to `ServiceOperationAdapter` (no ToolResult) |
| **T-54.11** | `test_every_manifest_operation_has_one_adapter` | `tests/test_phase54_operation_adapters.py` | All 146 operations in `public-operations.toml` are registered and reconciled |

---

## 8. File, Dependency, and Documentation Governance

### 8.1 Files to Create and Modify

```text
# New Source Files
src/rush/contracts/__init__.py
src/rush/contracts/results.py
src/rush/contracts/operations.py

# New Test Files & Fixtures
tests/test_phase54_result_schema.py
tests/test_phase54_operation_adapters.py
tests/fixtures/remediation/tool_result_v1_valid.json
tests/fixtures/remediation/tool_result_v1_invalid.json

# Existing Source Files Modified for Compatibility & Helpers
src/rush/tools/base.py
src/rush/tools/common.py
src/rush/tools/__init__.py

# Governance Manifests Updated
governance/remediation-contracts.toml
governance/public-operations.toml
governance/remediation-phase-54.toml  (New)

# Implementation Evidence Document
docs/developer/phase-54-implementation-evidence.md  (New)
```

### 8.2 Comprehensive `/docs` Documentation Audit and Update Ledger

An exhaustive scan across `/docs` and all its subfolders identified **138 documentation files** containing references to `ToolResult`, `Finding`, schemas, statuses, severities, and Phase 54. The following ledger groups these files and defines the exact updates required upon Phase 54 completion:

#### Group 1: Core Specifications & Operational Reference Documents (18 files — Must be updated in Phase 54)
1. [`docs/JSON_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/JSON_SCHEMA.md): Add Section 3 specifying `ToolResultV1` (`schema_version: "1.0.0"`), `FindingV1` canonical severities (`info|warning|error`), strict unknown key rejection, namespaced `extensions`, and `ValidationErrorV1` schema.
2. [`docs/API_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/API_REFERENCE.md): Document `rush.contracts.results` and `rush.contracts.operations`, listing all classes and helper functions while retaining legacy TypedDict definitions for backward compatibility.
3. [`docs/reference/result-reference.md`](file:///C:/Users/james/developer/rush-cli/docs/reference/result-reference.md): Detail `ToolResultV1` envelope, `FindingV1` fields, the legacy mapping table (`warn`→`warning`, `fail`→`error`), and validation error codes.
4. [`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md): Document that tool commands return `ToolResultV1` JSON under `--json`, whereas admin commands return named admin contracts or standard exit codes.
5. [`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md): Detail tool operation return contracts (`ToolResultV1`) vs service protocol methods (unwrapped JSON-RPC frames).
6. [`docs/reference/mcp-tool-reference.md`](file:///C:/Users/james/developer/rush-cli/docs/reference/mcp-tool-reference.md): Add notice regarding `ToolResultV1` schema adoption and canonical finding severity tiers.
7. [`docs/developer/tool-development.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/tool-development.md): Update authoring guide to instruct using `rush.contracts.results` and adapter helpers.
8. [`docs/developer/architecture.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/architecture.md): Add Architecture Section on `src/rush/contracts/`, detailing the two-phase lifecycle (Sanitize via Phase 53 -> Validate via Phase 54).
9. [`docs/maintainers/versioning-and-compatibility.md`](file:///C:/Users/james/developer/rush-cli/docs/maintainers/versioning-and-compatibility.md): Add Section on Result Schema Evolution, documenting `schema_version = "1.0.0"` and compatibility rules.
10. [`docs/developer/testing-guide.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/testing-guide.md): Add Section 11 documenting Phase 54 contract test suites (`tests/test_phase54_*.py`).
11. [`docs/maintainers/release-playbook.md`](file:///C:/Users/james/developer/rush-cli/docs/maintainers/release-playbook.md): Add Phase 54 Schema Kernel Pre-Release Verification Gate.
12. [`docs/developer/debugging-guide.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/debugging-guide.md): Add troubleshooting section for `ValidationErrorV1` error codes.
13. [`docs/user-guide/checking-code.md`](file:///C:/Users/james/developer/rush-cli/docs/user-guide/checking-code.md): Align finding severity explanations with canonical `info`, `warning`, `error` tiers.
14. [`docs/getting-started/glossary.md`](file:///C:/Users/james/developer/rush-cli/docs/getting-started/glossary.md): Update `ToolResult` and `Finding` definitions to reflect `ToolResultV1`, `FindingV1`, and `schema_version`.
15. [`docs/GLOSSARY.md`](file:///C:/Users/james/developer/rush-cli/docs/GLOSSARY.md): Update `ToolResult` and `Finding` definitions to reflect `ToolResultV1`, `FindingV1`, and `schema_version`.
16. [`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md): Document that MCP tool calls return `ToolResultV1` while protocol routes remain unwrapped.
17. [`docs/SAFETY.md`](file:///C:/Users/james/developer/rush-cli/docs/SAFETY.md): Document that Phase 54 validation runs downstream of Phase 53 sanitization.
18. [`docs/PRIVACY.md`](file:///C:/Users/james/developer/rush-cli/docs/PRIVACY.md): Document that Phase 54 validation runs downstream of Phase 53 sanitization.

#### Group 2: Governance, Evidence & Tracking Documents (8 files — Updated during Phase 54 implementation)
19. [`governance/remediation-phase-54.toml`](file:///C:/Users/james/developer/rush-cli/governance/remediation-phase-54.toml): Create completed phase record with baseline (1,041), completed (1,052), and 11 contract tests.
20. [`governance/remediation-contracts.toml`](file:///C:/Users/james/developer/rush-cli/governance/remediation-contracts.toml): Mark Finding R-011 as completed.
21. [`governance/public-operations.toml`](file:///C:/Users/james/developer/rush-cli/governance/public-operations.toml): Reconcile target contract IDs for all 146 operations.
22. [`docs/developer/phase-54-implementation-evidence.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/phase-54-implementation-evidence.md): Create evidence document with passing test commands, matrix, and verification logs.
23. [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md): Mark Phase 54 milestone row as Complete.
24. [`docs/developer/issues.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/issues.md): Record `ISS-054-01` and `ISS-054-02` as Closed.
25. [`README.md`](file:///C:/Users/james/developer/rush-cli/README.md): Update test badge to 1,052 passed.
26. [`CHANGELOG.md`](file:///C:/Users/james/developer/rush-cli/CHANGELOG.md): Document Phase 54 changes under `[0.3.0]`.

#### Group 3: Phase Plans & Future Remediation Handoffs
27. [`docs/phase-plans/phase-54-tool-result-schema-kernel-plan.md`](file:///C:/Users/james/developer/rush-cli/docs/phase-plans/phase-54-tool-result-schema-kernel-plan.md): The implementation plan itself.
28. [`docs/phase-plans/README.md`](file:///C:/Users/james/developer/rush-cli/docs/phase-plans/README.md): Update Phase 54 status in master index.
29. [`docs/phase-plans/phase-56-content-addressed-plugin-trust-plan.md`](file:///C:/Users/james/developer/rush-cli/docs/phase-plans/phase-56-content-addressed-plugin-trust-plan.md): Cite `rush.contracts.operations:ToolOperationAdapter` for sandboxed plugin output.
30. [`docs/phase-plans/phase-57-invocation-scope-operations-cache-egress-plan.md`](file:///C:/Users/james/developer/rush-cli/docs/phase-plans/phase-57-invocation-scope-operations-cache-egress-plan.md): Cite Phase 54 adapters for migrating CLI and MCP public routes.
31. [`docs/phase-plans/phase-58-lock-persistence-patch-fail-closed-plan.md`](file:///C:/Users/james/developer/rush-cli/docs/phase-plans/phase-58-lock-persistence-patch-fail-closed-plan.md): Cite Phase 54 kernel for completing eligible runtime tool producer output migration.

#### Group 4: Historical ADRs & Retrospective Reports (Preserved)
- Architectural Decision Records (`docs/adr/0002-normalized-finding-and-evidence-model.md`, `0011`, `0015`, `0039`, `docs/maintainers/adr/012-extensible-plugin-architecture.md`) and historical phase plans (Phases 20–50c) remain preserved as historical design records, with notes reflecting that `ToolResultV1` supersedes the legacy shape.

## 9. Ordered workstreams and atomic task cards

### P54.0 — Admission and Baseline Evidence

#### P54.0.1 — EVIDENCE: Record schema producers, vocabularies, and operation classes

- **Task ID and binary outcome:** P54.0.1; finding severity producers, current vocabularies, and all 146 manifest operations are cataloged with assigned ownership.
- **Start goal:** Freeze schema kernel scope and establish concrete baseline.
- **Prerequisites:** §4 Admission Gate passed.
- **Documentation impact:** None (internal evidence record only).
- **Dependency impact:** None (standard library only).
- **Allowed writes:**
  - `governance/remediation-contracts.toml` (R-011 seam fields)
  - `docs/developer/phase-54-implementation-evidence.md` (New baseline evidence log)
- **Allowed reads:**
  - `src/rush/tools/base.py`
  - `src/rush/tools/common.py`
  - `src/rush/tools/__init__.py`
  - `governance/public-operations.toml`
  - `governance/remediation-contracts.toml`
- **Prohibited:** Modifying tool implementations in `src/rush/tools/`, altering CLI/MCP registrations, adding external dependencies.
- **Actions:**
  1. Inspect finding severity producers across `src/rush/tools/` to catalogue all emitted severities (`warn`, `fail`, `info`, `error`, `warning`).
  2. Inspect `governance/public-operations.toml` to confirm exactly 146 operations (`67 tool`, `62 admin`, `17 service`).
  3. Record baseline evidence and contract targets in `docs/developer/phase-54-implementation-evidence.md`.
  4. Verify that R-011 seam fields in `governance/remediation-contracts.toml` point to `src/rush/contracts/results.py` and `src/rush/contracts/operations.py`.
- **Evidence:** Documented producer/vocabulary matrix and 146 operation classification count in evidence log.
- **Stop condition:** Any unclassified operation in `governance/public-operations.toml` or missing contract mapping.
- **Verified outcome:** P54.1.1 and P54.3.1 may start.

---

### P54.1 — Schema Types and Deterministic Serialization

#### P54.1.1 — RED: Define exact V1 types, vocabularies, and deterministic serialization tests

- **Task ID and binary outcome:** P54.1.1; exactly four contract tests fail solely because `rush.contracts.results` symbols are not yet implemented.
- **Start goal:** Pin required fields, vocabularies, extension boundaries, and deterministic serialization bytes with failing tests.
- **Prerequisites:** P54.0.1 complete.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:**
  - `tests/test_phase54_result_schema.py` (New)
  - `tests/fixtures/remediation/tool_result_v1_valid.json` (New)
  - `tests/fixtures/remediation/tool_result_v1_invalid.json` (New)
- **Allowed reads:**
  - `src/rush/tools/base.py`
  - `src/rush/safety/redactor.py`
  - `docs/phase-plans/phase-54-tool-result-schema-kernel-plan.md` §6
- **Prohibited:** Implementing production code in `src/rush/contracts/`, modifying existing tests, using skip/xfail.
- **Actions:**
  1. Create `tests/fixtures/remediation/tool_result_v1_valid.json` with canonical valid fields: `schema_version="1.0.0"`, `tool="lint"`, `engine="ruff"`, `engine_version="0.9.9"`, `status="ok"`, `duration_ms=42`, `summary="all clean"`, `findings=[]`, `raw=None`, `extensions={}`.
  2. Create `tests/fixtures/remediation/tool_result_v1_invalid.json` with invalid payloads exercising validation failure codes: missing `schema_version`, invalid status (`"passed"`), invalid severity (`"fatal"`), bad schema version (`"2.0.0"`), unknown top-level key (`"extra_prop"`), and negative duration (`-1`).
  3. Create `tests/test_phase54_result_schema.py` implementing the first 4 contract tests:
     - `test_tool_result_v1_requires_exact_fields_and_vocabularies` (T-54.01): Validates all 8 core fields; tests rejection of missing `schema_version`, invalid status, and missing `tool`.
     - `test_finding_v1_rejects_unknown_severity` (T-54.02): Validates `FindingV1` with `info`, `warning`, `error`; asserts that unknown severities (`warn`, `fail`, `critical`) raise `ValidationErrorV1(code="INVALID_SEVERITY")`.
     - `test_extensions_are_namespaced_json_safe` (T-54.03): Asserts that `extensions` accepts arbitrary JSON-safe dictionary structures, while unknown top-level keys on `ToolResultV1` or `FindingV1` raise `ValidationErrorV1(code="UNKNOWN_TOP_LEVEL_KEY")`.
     - `test_serializer_is_deterministic` (T-54.04): Serializes identical `ToolResultV1` data initialized with different dictionary key insertion orders; verifies identical JSON string outputs matching canonical byte sorting (`sort_keys=True, separators=(',', ':')`).
  4. Run `.venv/Scripts/python.exe -m pytest tests/test_phase54_result_schema.py -q`. Verify all 4 tests fail strictly with `ModuleNotFoundError: No module named 'rush.contracts'` or `ImportError` (clean RED state).
- **Evidence:** Terminal failure log showing 4 failed tests due to absent module.
- **Stop condition:** Any test passes or fails for reasons other than missing contract symbols.
- **Verified outcome:** P54.1.2 may proceed to implement the results contract.

#### P54.1.2 — GREEN: Implement V1 schema types, validation, and deterministic serialization

- **Task ID and binary outcome:** P54.1.2; all four schema contract tests pass with byte-deterministic output and zero test regressions.
- **Start goal:** Satisfy P54.1.1 contract tests by creating `rush.contracts.results`.
- **Prerequisites:** Recorded P54.1.1 RED state.
- **Documentation impact:** None.
- **Dependency impact:** None (Python standard library only; Pydantic strictly prohibited).
- **Allowed writes:**
  - `src/rush/contracts/__init__.py` (New)
  - `src/rush/contracts/results.py` (New)
  - `tests/fixtures/remediation/tool_result_v1_valid.json` (Fixture adjustment if needed)
  - `tests/test_phase54_result_schema.py` (Only to retain or strengthen assertions)
- **Allowed reads:**
  - §6 specification
  - Phase 53 `rush.safety.redactor:sanitize_value`
- **Prohibited:** External dependencies, legacy adapters (deferred to P54.2), editing `src/rush/tools/base.py` (deferred to P54.2).
- **Actions:**
  1. Create `src/rush/contracts/__init__.py` exposing `ToolResultV1`, `FindingV1`, `ValidationErrorV1`, `validate_tool_result`, `validate_finding`, `serialize_tool_result`.
  2. Create `src/rush/contracts/results.py` containing:
     - `FindingSeverity = Literal["info", "warning", "error"]`
     - `ToolStatus = Literal["ok", "warn", "fail", "error", "skipped"]`
     - `@dataclass(frozen=True) class FindingV1`
     - `@dataclass(frozen=True) class ToolResultV1`
     - `@dataclass(frozen=True) class ValidationErrorV1(Exception)`
     - `validate_finding(data: Any, path_prefix: str = "findings") -> FindingV1`: Validates required fields, checks types, rejects unknown top-level keys, validates severity against canonical vocabulary.
     - `validate_tool_result(data: Any) -> ToolResultV1`: Validates 8 core fields, validates `status` against canonical vocabulary, checks `schema_version == "1.0.0"`, rejects unknown top-level keys, validates each finding.
     - `serialize_tool_result(result: ToolResultV1 | dict[str, Any]) -> str`: Sanitizes input via `rush.safety.redactor:sanitize_value`, validates via `validate_tool_result`, and serializes via `json.dumps(..., sort_keys=True, separators=(',', ':'), ensure_ascii=False)`.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_phase54_result_schema.py -q`. Verify all 4 tests pass (GREEN).
  4. Run full test suite `.venv/Scripts/python.exe -m pytest tests/ -q` to verify zero regression across baseline (1,041 + 4 = 1,045 passed).
- **Evidence:** 4 passing tests in `test_phase54_result_schema.py`, zero regression on existing tests.
- **Stop condition:** Validation accepts an unknown top-level key or uses non-standard error structures.
- **Verified outcome:** P54.2.1 and P54.3.1 may start.

---

### P54.2 — Deterministic Legacy Mapping and Helper Routing

#### P54.2.1 — RED: Define deterministic legacy conversion and error handling tests

- **Task ID and binary outcome:** P54.2.1; exactly three legacy mapping tests fail on absent adapter functions.
- **Start goal:** Pin deterministic legacy mapping rules (`warn`→`warning`, `fail`→`error`) and structured error handling.
- **Prerequisites:** P54.1.2 complete.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:**
  - `tests/test_phase54_result_schema.py`
  - `tests/test_base.py`
- **Allowed reads:**
  - `src/rush/tools/base.py`
  - `src/rush/tools/common.py`
  - `src/rush/contracts/results.py`
- **Prohibited:** Implementing adapters in `src/rush/contracts/results.py` prematurely, permissive fallback.
- **Actions:**
  1. Add 3 legacy mapping contract tests to `tests/test_phase54_result_schema.py`:
     - `test_legacy_warn_maps_only_to_warning` (T-54.05): Passes legacy dict with `severity="warn"`; asserts `FindingV1.severity == "warning"`.
     - `test_legacy_fail_maps_only_to_error` (T-54.06): Passes legacy dict with `severity="fail"`; asserts `FindingV1.severity == "error"`. Also verifies `info`→`info`, `error`→`error`, `warning`→`warning`.
     - `test_unknown_legacy_value_returns_canonical_validation_error` (T-54.07): Passes unmappable legacy dicts (e.g. `severity="critical"`, non-dict payload, invalid status); asserts that `ValidationErrorV1` is raised with canonical `code="INVALID_SEVERITY"` or `"INVALID_STATUS"` (prohibiting silent default coercion).
  2. Add unit assertions in `tests/test_base.py` verifying legacy `normalize_findings`, `error_result`, and `skipped_result` callers maintain behavioral parity when routed to V1 adapters.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_phase54_result_schema.py -k "legacy" -q`. Verify all 3 tests fail with `ImportError: cannot import name 'adapt_legacy_finding'` (RED state).
- **Evidence:** Terminal failure log showing 3 failed legacy tests due to absent adapter functions.
- **Stop condition:** Any test passes or permits unmappable values to fall back to silent defaults.
- **Verified outcome:** P54.2.2 may proceed to implement legacy adapters.

#### P54.2.2 — GREEN: Implement legacy mapping functions and integrate with tool helpers

- **Task ID and binary outcome:** P54.2.2; legacy mappings and canonical errors pass through one path with backward compatibility preserved.
- **Start goal:** Satisfy P54.2.1 by implementing `adapt_legacy_finding` and `adapt_legacy_tool_result`, and wiring `src/rush/tools/base.py` / `common.py`.
- **Prerequisites:** Recorded P54.2.1 RED state.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:**
  - `src/rush/contracts/results.py`
  - `src/rush/contracts/__init__.py`
  - `src/rush/tools/base.py`
  - `src/rush/tools/common.py`
  - `src/rush/tools/__init__.py`
- **Allowed reads:**
  - P54.2.1 tests
  - `src/rush/tools/base.py`
  - `src/rush/tools/common.py`
- **Prohibited:** Changing tool runtime implementations, breaking existing legacy `ToolResult` TypedDict callers.
- **Actions:**
  1. In `src/rush/contracts/results.py`, implement:
     - `LEGACY_SEVERITY_MAP: dict[str, FindingSeverity] = {"info": "info", "warn": "warning", "warning": "warning", "error": "error", "fail": "error"}`
     - `adapt_legacy_finding(legacy: dict[str, Any]) -> FindingV1`: Maps legacy keys, converts severity using `LEGACY_SEVERITY_MAP` (raises `ValidationErrorV1(code="INVALID_SEVERITY")` if not present), populates fingerprint (generating SHA-256 if missing), routes extra keys into `extensions`.
     - `adapt_legacy_tool_result(legacy: dict[str, Any]) -> ToolResultV1`: Injects `schema_version="1.0.0"`, converts findings list via `adapt_legacy_finding`, moves non-core keys (`metrics`, `artifacts`, etc.) into `extensions`, validates and returns `ToolResultV1`.
  2. Export `adapt_legacy_finding` and `adapt_legacy_tool_result` in `src/rush/contracts/__init__.py`.
  3. In `src/rush/tools/common.py`:
     - Update `normalize_findings` to utilize `LEGACY_SEVERITY_MAP` while retaining legacy TypedDict return compatibility.
     - Ensure `error_result` and `skipped_result` produce canonical status values and valid schema-compatible structures.
  4. In `src/rush/tools/base.py`:
     - Re-export `ToolResultV1`, `FindingV1`, `ValidationErrorV1` alongside legacy `ToolResult` and `Finding` TypedDicts.
  5. Run `.venv/Scripts/python.exe -m pytest tests/test_phase54_result_schema.py tests/test_base.py -q`. Verify all 7 tests in `test_phase54_result_schema.py` pass (GREEN).
  6. Run `.venv/Scripts/python.exe -m pytest tests/ -q` to verify full baseline integrity (1,041 + 7 = 1,048 passed).
- **Evidence:** 7 passing tests in `test_phase54_result_schema.py`, 0 regressions in existing tests.
- **Stop condition:** Silent coercion of invalid severities persists in any helper.
- **Verified outcome:** P54.3.1 may proceed.

---

### P54.3 — Operation Adapters and Manifest Reconciliation

#### P54.3.1 — RED: Define operation adapter contracts and 100% manifest reconciliation tests

- **Task ID and binary outcome:** P54.3.1; exactly four tests fail solely due to absent `rush.contracts.operations` module.
- **Start goal:** Pin operation adapter class behavior (`tool`, `admin`, `service`) and assert 100% manifest reconciliation.
- **Prerequisites:** P54.0.1 and P54.1.2 complete.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:**
  - `tests/test_phase54_operation_adapters.py` (New)
- **Allowed reads:**
  - `governance/public-operations.toml`
  - `src/rush/contracts/results.py`
- **Prohibited:** Implementing adapters in `src/rush/contracts/operations.py` prematurely.
- **Actions:**
  1. Create `tests/test_phase54_operation_adapters.py` implementing the 4 adapter contract tests:
     - `test_tool_operation_targets_tool_result_v1` (T-54.08): Asserts that `ToolOperationAdapter.validate_output(payload)` enforces `ToolResultV1` validation and returns a validated `ToolResultV1` instance.
     - `test_admin_operation_uses_named_contract` (T-54.09): Asserts that `AdminOperationAdapter.validate_output(payload)` validates against named admin contract (e.g. exit code int or admin payload dict) and does NOT wrap in `ToolResultV1`.
     - `test_service_liveness_is_not_wrapped_as_tool_result` (T-54.10): Asserts that `ServiceOperationAdapter.validate_output(payload)` preserves JSON-RPC protocol message frames (such as `initialize`, `tools/list`) and explicitly rejects `ToolResultV1` wrapping.
     - `test_every_manifest_operation_has_one_adapter` (T-54.11): Loads `governance/public-operations.toml` (all 146 operations); instantiates `OperationRegistry`; reconciles every operation; asserts that exactly 67 operations map to `ToolOperationAdapter`, 62 operations map to `AdminOperationAdapter`, 17 operations map to `ServiceOperationAdapter`, and 0 operations are unmapped or invalid.
  2. Run `.venv/Scripts/python.exe -m pytest tests/test_phase54_operation_adapters.py -q`. Verify all 4 tests fail strictly with `ModuleNotFoundError: No module named 'rush.contracts.operations'` or `ImportError` (RED state).
- **Evidence:** Terminal failure log showing 4 failed tests in `test_phase54_operation_adapters.py`.
- **Stop condition:** Any test passes prematurely or manifest operations count differs from 146.
- **Verified outcome:** P54.3.2 may proceed to implement operation adapters.

#### P54.3.2 — GREEN: Implement operation adapters and registry with 100% manifest reconciliation

- **Task ID and binary outcome:** P54.3.2; every entry in `governance/public-operations.toml` maps to exactly one adapter class with zero runtime transport rewrites.
- **Start goal:** Satisfy P54.3.1 by implementing `rush.contracts.operations` and reconciling all 146 manifest operations.
- **Prerequisites:** Recorded P54.3.1 RED state.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:**
  - `src/rush/contracts/operations.py` (New)
  - `src/rush/contracts/__init__.py`
  - `governance/public-operations.toml` (Reconcile target contract IDs if needed)
  - `tests/test_phase54_operation_adapters.py` (Only to strengthen assertions)
- **Allowed reads:**
  - P54.3.1 tests
  - `governance/public-operations.toml`
  - `src/rush/contracts/results.py`
- **Prohibited:** Changing CLI command or MCP transport registrations at runtime.
- **Actions:**
  1. Create `src/rush/contracts/operations.py` containing:
     - `OperationKind = Literal["tool", "admin", "service"]`
     - `BaseOperationAdapter(ABC)`: Abstract base defining `operation_id`, `kind`, `target_contract_id`, and abstract `validate_output(self, output: Any) -> Any`.
     - `ToolOperationAdapter(BaseOperationAdapter)`: `kind="tool"`, `target_contract_id="ToolResultV1"`. Validates via `validate_tool_result`.
     - `AdminOperationAdapter(BaseOperationAdapter)`: `kind="admin"`. Validates integer exit codes or admin dictionary contracts without `ToolResultV1` wrapping.
     - `ServiceOperationAdapter(BaseOperationAdapter)`: `kind="service"`. Validates protocol frames and ensures no `ToolResultV1` wrapping occurs.
     - `OperationRegistry`: Stores mapping of `operation_id -> BaseOperationAdapter`. Provides `register(adapter)`, `get_adapter(operation_id)`, `reconcile_manifest(path) -> ReconciliationReport`. Automatically constructs default adapters based on manifest `kind` and `contract_id`.
  2. Export adapters and registry in `src/rush/contracts/__init__.py`.
  3. Verify and reconcile any missing `contract_id` fields in `governance/public-operations.toml` so every entry has an explicit target contract (`ToolResultV1`, `AdminExitCode`, `AdminJson`, `ServiceProtocol`, etc.).
  4. Run `.venv/Scripts/python.exe -m pytest tests/test_phase54_operation_adapters.py -q`. Verify all 4 tests pass (GREEN).
  5. Run all Phase 54 tests and existing public operations test:
     `.venv/Scripts/python.exe -m pytest tests/test_phase54_result_schema.py tests/test_phase54_operation_adapters.py tests/test_phase51_public_operations.py tests/test_mcp.py -q`.
  6. Run full test suite `.venv/Scripts/python.exe -m pytest tests/ -q` to verify zero regression across baseline (1,041 + 11 = 1,052 passed).
- **Evidence:** 4 passing tests in `test_phase54_operation_adapters.py`, 11 total Phase 54 passing tests, 1,052 total passing tests.
- **Stop condition:** Any manifest operation cannot be adapted or causes validation failure.
- **Verified outcome:** P54.4.1 may start.

---

### P54.4 — Verification, Comprehensive Documentation, and Governance Handoff

#### P54.4.1 — VERIFY, DOCUMENT, AND RECORD GOVERNANCE HANDOFF

- **Task ID and binary outcome:** P54.4.1; all 16 Group 1 specification documents, 8 Group 2 governance/evidence documents, and Phase 54 governance records are fully synchronized, with all 11 contract tests passing and 0 unclosed successor IDs prematurely resolved.
- **Start goal:** Prove kernel isolation, update all cataloged documentation, and publish exact contracts for Phase 56–58 handoff.
- **Prerequisites:** P54.1.2, P54.2.2, P54.3.2 all complete with all 11 contract tests green.
- **Documentation impact:** Update 16 Group 1 specification documents and 8 Group 2 governance/evidence documents according to the §8.2 ledger.
- **Dependency impact:** None.
- **Allowed writes:**
  - Group 1 Core Documents:
    1. `docs/JSON_SCHEMA.md`
    2. `docs/API_REFERENCE.md`
    3. `docs/reference/result-reference.md`
    4. `docs/CLI_REFERENCE.md`
    5. `docs/MCP_REFERENCE.md`
    6. `docs/reference/mcp-tool-reference.md`
    7. `docs/developer/tool-development.md`
    8. `docs/developer/architecture.md`
    9. `docs/maintainers/versioning-and-compatibility.md`
    10. `docs/developer/testing-guide.md`
    11. `docs/maintainers/release-playbook.md`
    12. `docs/developer/debugging-guide.md`
    13. `docs/user-guide/checking-code.md`
    14. `docs/getting-started/glossary.md`
    15. `docs/GLOSSARY.md`
    16. `docs/MCP.md`
    17. `docs/SAFETY.md`
    18. `docs/PRIVACY.md`
  - Group 2 Governance & Evidence Documents:
    19. `governance/remediation-phase-54.toml` (create)
    20. `governance/remediation-contracts.toml` (mark R-011 completed)
    21. `governance/public-operations.toml` (reconciled contract IDs)
    22. `docs/developer/phase-54-implementation-evidence.md` (create)
    23. `docs/developer/backlog.md` (mark Phase 54 complete)
    24. `docs/developer/issues.md` (record ISS-054-01 & ISS-054-02 closed)
    25. `README.md` (update test badge to 1,052 passed)
    26. `CHANGELOG.md` (document Phase 54 additions under [0.3.0])
- **Allowed reads:** All test results, governance manifests, §8.2 audit ledger.
- **Prohibited:** Marking runtime migrations as complete (runtime migration remains owned by Phase 57 and Phase 58).
- **Actions:**
  1. Apply documentation updates for each file in Group 1 and Group 2 as specified in §8.2.
  2. Create `governance/remediation-phase-54.toml` documenting: phase status = `"completed"`, test baseline = 1041, test count = 1052, 11 contract tests.
  3. Update `governance/remediation-contracts.toml` to mark Finding R-011 status = `"completed"`.
  4. Create `docs/developer/phase-54-implementation-evidence.md` recording all test outputs, test IDs, verification commands, and architecture diagrams.
  5. Run Section 10 delivery gate commands:
     - Pytest focused: `tests/test_phase54_*.py`, `tests/test_base.py`, `tests/test_phase51_public_operations.py`.
     - Pytest full: `tests/` (1,052 passing).
     - Ruff check and format check: `ruff check src tests scripts` and `ruff format --check src tests scripts`.
     - Git status: `git diff --check`, `git status --short --branch`.
  6. Verify that Phase 56, Phase 57, and Phase 58 handoff contracts are intact and runtime migration IDs remain unclosed.
- **Evidence:** Full test execution logs, documentation diff, completed governance manifests, clean linter outputs.
- **Stop condition:** Any linter error, git whitespace error, failing test, or omitted documentation update.
- **Verified outcome:** Phase 54 is 100% complete, verified, documented, and ready for handoff.

---

## 10. Final verification and delivery gate

```powershell
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null

# 1. Focused contract test suite
.venv/Scripts/python.exe -m pytest tests/test_phase54_result_schema.py tests/test_phase54_operation_adapters.py tests/test_base.py tests/test_phase51_public_operations.py -q

# 2. Full test suite execution (1,052 passing expected)
.venv/Scripts/python.exe -m pytest tests/ -q

# 3. Linter and formatting check
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 4. Git hygiene checks
git diff --check
git diff --name-only
git status --short --branch
```

---

## 11. Exit checklist and successor evidence

- [ ] Ordinary RED evidence precedes each GREEN task; no skip, xfail, or permissive assertions.
- [ ] Canonical finding severity vocabulary is strictly `Literal["info", "warning", "error"]`.
- [ ] Tool status vocabulary is strictly `Literal["ok", "warn", "fail", "error", "skipped"]`.
- [ ] Exact deterministic legacy mappings are implemented (`warn`→`warning`, `fail`→`error`).
- [ ] Unmappable or invalid values raise structured `ValidationErrorV1`, never silent fallback.
- [ ] Schema version is fixed at constant `"1.0.0"`.
- [ ] Unknown top-level keys are rejected with `ValidationErrorV1(code="UNKNOWN_TOP_LEVEL_KEY")`.
- [ ] Extensions dictionary accepts namespaced JSON-safe structures.
- [ ] Byte-deterministic JSON serialization is verified across varying insertion orders.
- [ ] Zero Pydantic or external schema dependencies introduced.
- [ ] 100% of the 146 operations in `governance/public-operations.toml` map to one adapter class (`67 tool`, `62 admin`, `17 service`).
- [ ] Stdio protocol messages (`initialize`, `tools/list`) remain unwrapped protocol frames.
- [ ] No runtime tool implementations, CLI command registrations, or MCP bindings altered.
- [ ] All 18 Group 1 specification documents updated as per §8.2.
- [ ] All 8 Group 2 governance, evidence, and tracking documents updated as per §8.2.
- [ ] `governance/remediation-phase-54.toml` created with complete test and closure records.
- [ ] Finding R-011 marked completed in `governance/remediation-contracts.toml`.
- [ ] Successor phases (Phase 56, 57, 58) receive exact schema specifications and adapter interfaces without premature closure of runtime migration tasks.
