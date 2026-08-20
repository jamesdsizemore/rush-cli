# Phase 26 Implementation Plan: Monorepo & Workspace Boundaries

> **Phase:** 26 of 30  
> **Milestone:** Monorepo Topologies & Polyglot Workspace Scoping  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0001: External Engine Boundary](../adr/0001-external-engine-boundary.md)

---

## 1. Objective & Scope

Empower Rush to detect monorepo topologies (Turborepo, Nx, pnpm workspaces, Cargo workspaces, Go multi-modules) and execute targeted tool checks scoped to specific workspace packages (`--workspace <name>`, `--all-workspaces`).

Incorporate **Workspace Boundary Confinement** to validate workspace definitions against path traversal attacks (`../`) escaping repository roots.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/discovery/workspace.py` (New: Monorepo workspace detector and topological sorter)
- `src/rush/cli.py` (Modified: Add `--workspace` and `--all-workspaces` flags)
- `src/rush/tools/common.py` (Modified: Inject package root working directories into subprocess dispatch)
- `src/rush/logging.py` (Modified: `[rush-workspace:LEVEL]` logging tags)

### Test & Fixture Files
- `tests/test_workspace.py` (New: Monorepo parsing, topological sorting, and scoping tests)
- `tests/fixtures/monorepos/` (New: Sample Turborepo, pnpm, and Cargo workspace fixtures)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase
Write tests in `tests/test_workspace.py`:
1. `test_detect_pnpm_workspace()`: Parses `pnpm-workspace.yaml` packages.
2. `test_detect_cargo_workspace()`: Parses `[workspace]` in `Cargo.toml`.
3. `test_workspace_traversal_rejection()`: Verifies packages with path `../../external` are rejected with security error.
4. `test_workspace_topological_sort()`: Verifies internal dependency graph is sorted in build order.

### 3.2 GREEN Phase
Implement `workspace.py` and integrate `--workspace` into Click CLI.

### 3.3 REFACTOR Phase
Ensure caching keys include workspace root identifiers to prevent cross-package collision.

---

## 4. Step-by-Step Implementation Tasks

### Task 26.1: Workspace Boundary Discovery (`src/rush/discovery/workspace.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class WorkspacePackage:
    name: str
    path: Path
    dependencies: list[str]

def discover_workspaces(root: Path) -> list[WorkspacePackage]:
    packages: list[WorkspacePackage] = []
    # Parse pnpm-workspace.yaml, package.json workspaces, Cargo.toml workspace, go.work
    return packages

def topological_sort_workspaces(packages: list[WorkspacePackage]) -> list[WorkspacePackage]:
    # Topological sort for internal monorepo dependencies
    ...
```

### Task 26.2: CLI Scoping Flag (`src/rush/cli.py`)
Add `--workspace` and `--all-workspaces` to tool and suite commands.

### Task 26.3: Stderr Diagnostics & Logging
- `[rush-workspace:INFO] Discovered {count} workspace packages in monorepo`
- `[rush-workspace:INFO] Scoping execution to workspace package '{name}'`
- `[rush-workspace:SECURITY_ERROR] Traversal path detected in workspace definition: {path}`

---

## 5. Mandatory Documentation Synchronization

During development, update:
1. `docs/CLI_REFERENCE.md` & `docs/reference/cli-reference.md` (Document `--workspace` and `--all-workspaces`).
2. `docs/USER_GUIDE.md` & `docs/user-guide/monorepos.md` (Monorepo best practices guide).
3. Run `python scripts/sync_docs.py --update` to maintain 100% doc sync.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run workspace unit tests
.venv/Scripts/python.exe -m pytest tests/test_workspace.py -v

# 2. Full test suite verification
.venv/Scripts/python.exe -m pytest tests/ -q

# 3. Documentation parity verification
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 4. Lint and format
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 5. Graft code graph check
graft --dir .hermes/graft build . && graft --dir .hermes/graft check .
```
