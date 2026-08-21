# Phase 33 Implementation Plan: Full-Stack Architecture, Sync & Type Safety Gates

> **Phase:** 33 of 40  
> **Milestone:** Full-Stack Type & Environment Parity Enforcement  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.5.0  
> **ADR References:** [ADR-0019: Native Graft Semantic Slicing & Tree-Sitter AST Engine](docs/adr/0019-native-graft-semantic-slicing-and-tree-sitter.md), [ADR-0024: Hardened Subprocess Git Invocations](docs/adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `tree-sitter==0.24.0`, `tree-sitter-typescript==0.23.2`, `tree-sitter-python==0.23.6`, `mcp==1.28.1`

---

## 1. Objective & Scope

Autonomous coding agents commonly modify backend API route models (Pydantic / FastAPI / Django) without updating the corresponding frontend TypeScript interfaces or OpenAPI specifications, leading to silent runtime breakage. Additionally, agents frequently introduce new environment variable references in code without adding them to `.env.example` or CI secret manifests.

Phase 33 establishes full-stack contract validation by delivering:
1. **Cross-Tier Schema & Type Sync (`rush schema-sync`)**: AST-level bidirectional type synchronization between Python Pydantic/SQLAlchemy models and TypeScript interfaces/Zod schemas.
2. **Environment Variable Parity Guard (`rush env-sync`)**: AST static analysis extracting `os.environ.get()` and `process.env` references to verify parity against `.env.example` and production manifests.
3. **API Specification Drift Detector (`rush api-drift`)**: Verifies route signatures, HTTP methods, and status codes against OpenAPI / Swagger JSON/YAML schemas.
4. **Git Remote Drift & Divergence Detector (`rush git-sync-status`)**: Scans tracking branches against `origin` without altering HEAD to alert agents of upstream divergence before committing changes.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Schema Diff Compression)**: Instead of dumping complete TypeScript and Python files into context, `rush schema-sync` computes minimal field-level discrepancy diffs (e.g. `+ user_id: string (missing in frontend)`).
- **`graft` (Targeted Model AST Slicing)**: Tree-Sitter parses and extracts only the class definitions inheriting from `BaseModel` or `TypedDict` and frontend `interface` / `type` blocks, ignoring helper logic and database queries.
- **`context-mode` (Strict Compact Diagnostics)**: Outputs discrepancy matrices in compact NDJSON format.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/tools/schema_sync.py` (New: Cross-tier Pydantic / TypeScript AST type comparator)
- `src/rush/tools/env_sync.py` (New: AST environment variable reference extractor and manifest verifier)
- `src/rush/tools/api_drift.py` (New: OpenAPI schema vs route handler AST drift auditor)
- `src/rush/git/sync_status.py` (New: Non-destructive remote branch drift analyzer)
- `src/rush/cli.py` (Modified: Register `rush schema-sync`, `rush env-sync`, `rush api-drift`, `rush git-sync-status`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Catalog specs)

### Test & Fixture Files
- `tests/test_schema_sync.py` (New: Pydantic to TypeScript interface alignment tests)
- `tests/test_env_sync.py` (New: Python & JS environment variable extraction and missing key tests)
- `tests/test_api_drift.py` (New: OpenAPI drift detection for altered route paths and parameters)
- `tests/test_git_sync_status.py` (New: Tracking branch divergence, ahead/behind counting)
- `tests/fixtures/sync/models.py` & `models.ts` (New: Paired test models)
- `tests/fixtures/sync/openapi.json` (New: OpenAPI schema fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_schema_sync.py
def test_schema_sync_detects_missing_field_in_typescript():
    py_code = """
class UserProfile(BaseModel):
    id: int
    email: str
    is_active: bool
"""
    ts_code = """
export interface UserProfile {
    id: number;
    email: string;
}
"""
    diffs = compare_py_ts_models(py_code, ts_code)
    assert len(diffs) == 1
    assert diffs[0].field_name == "is_active"
    assert diffs[0].missing_in == "typescript"

# tests/test_env_sync.py
def test_env_sync_finds_undeclared_env_vars(tmp_path):
    src = tmp_path / "app.py"
    src.write_text('stripe_key = os.environ.get("STRIPE_SECRET_KEY")')
    example_env = tmp_path / ".env.example"
    example_env.write_text('DATABASE_URL=postgres://localhost/db')
    
    missing = find_missing_env_vars(repo_root=tmp_path)
    assert "STRIPE_SECRET_KEY" in missing

# tests/test_git_sync_status.py
def test_git_sync_status_detects_ahead_behind(tmp_path):
    repo = init_git_repo_with_remote(tmp_path)
    status = check_remote_sync_status(repo_root=tmp_path)
    assert status.is_diverged is False
    assert status.ahead_count >= 0
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/tools/schema_sync.py`, `src/rush/tools/env_sync.py`, `src/rush/tools/api_drift.py`, and `src/rush/git/sync_status.py`.

### 4.3 REFACTOR Phase
Ensure Tree-Sitter AST traversal handles optional fields, unions (`int | None`), nullable types, and camelCase/snake_case automatic mapping.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:25:00Z", "phase": 33, "tool": "rush_schema_sync", "event": "type_mismatch", "model": "UserProfile", "field": "is_active", "py_type": "bool", "ts_type": "missing"}
{"timestamp": "2026-08-21T07:25:01Z", "phase": 33, "tool": "rush_env_sync", "event": "missing_env_var", "variable": "STRIPE_SECRET_KEY", "file": "src/billing.py", "line": 42}
{"timestamp": "2026-08-21T07:25:02Z", "phase": 33, "tool": "rush_git_sync_status", "event": "remote_drift", "branch": "main", "ahead": 2, "behind": 1}
```

---

## 6. Step-by-Step Task Specifications

### Task 33.1: Tree-Sitter Cross-Tier Model AST Extractor (`src/rush/tools/schema_sync.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from rush.tools.base import ToolResult, Finding

@dataclass(frozen=True)
class SchemaDiscrepancy:
    model_name: str
    field_name: str
    expected_type: str
    actual_type: str
    missing_in: str  # "python" | "typescript"

def audit_schema_synchronization(py_dir: Path, ts_dir: Path) -> ToolResult:
    """Extract Pydantic and TypeScript interfaces via Tree-Sitter and report discrepancies."""
    ...
```

### Task 33.2: Environment Variable Parity Scanner (`src/rush/tools/env_sync.py`)
Scan Python and JS/TS source trees for `os.environ`, `os.getenv`, `process.env`, and compare against `.env.example`.

### Task 33.3: OpenAPI Route Drift Auditor (`src/rush/tools/api_drift.py`)
Extract route decorators (`@app.get`, `@router.post`) and verify path parameters and response models against `openapi.json`.

### Task 33.4: Non-Destructive Git Sync Status (`src/rush/git/sync_status.py`)
Execute `git rev-list --left-right --count HEAD...@{u}` safely to report divergence without modifying the active index.

### Task 33.5: CLI & FastMCP Registrations
Register all 4 tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Naming Conventions**: Automatic normalization between `snake_case` (Python) and `camelCase` (TypeScript).
2. **Subprocess Isolation**: Git sync check must never run `git fetch` with network flags unless explicitly authorized; use local tracking refs by default.
3. **Doc Parity**: Synchronize and verify `/docs`.
