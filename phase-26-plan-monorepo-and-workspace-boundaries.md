# Phase 26 Implementation Plan: Monorepo & Workspace Boundaries

> **Phase:** 26 of 40  
> **Milestone:** Monorepo Topologies & Polyglot Workspace Scoping  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0001: External Engine Boundary](docs/adr/0001-external-engine-boundary.md), [ADR-0024: Hardened Subprocess Git Invocations](docs/adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Large enterprise repositories frequently operate as polyglot monorepos containing multiple interdependent packages (Turborepo, Nx, pnpm workspaces, Cargo workspaces, Go multi-modules). Running scanners on the entire repository root often causes misconfiguration or runs wrong engine versions on sub-packages.

Phase 26 empowers Rush to detect monorepo topologies and execute targeted tool checks scoped to specific workspace packages (`--workspace <name>`, `--all-workspaces`, `--affected`). Workspace definitions are strictly validated against path traversal attacks (`../`) escaping repository boundaries.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Package-Scoped Truncation)**: Scans execute strictly within the target package directory, avoiding scanning unrelated monorepo packages and cutting token overhead by up to 90%.
- **`graft` (Topological Dependency Ordering)**: Identifies internal workspace dependency graphs (`packages/ui` -> `apps/web`) to scan changed leaf dependencies first.
- **`context-mode` (Monorepo Topology Matrix)**: Emits compact workspace topology trees in structured NDJSON.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/discovery/workspace.py` (New: Monorepo workspace detector and topological sorter)
- `src/rush/cli.py` (Modified: Add `--workspace`, `--all-workspaces`, and `--affected` flags)
- `src/rush/tools/common.py` (Modified: Inject package root working directories into subprocess dispatch)
- `src/rush/mcp_server.py` (Modified: FastMCP workspace scoping parameters)
- `src/rush/catalog.py` (Modified: Register workspace capabilities)

### Test & Fixture Files
- `tests/test_workspace.py` (New: Monorepo parsing, topological sorting, traversal prevention, and scoping tests)
- `tests/fixtures/monorepos/pnpm_repo/` (New: Sample pnpm workspace fixture)
- `tests/fixtures/monorepos/cargo_repo/` (New: Sample Cargo workspace fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_workspace.py
def test_detect_pnpm_workspace(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - 'packages/*'\n  - 'apps/*'\n")
    (tmp_path / "packages" / "core").mkdir(parents=True)
    (tmp_path / "packages" / "core" / "package.json").write_text('{"name": "@app/core"}')
    
    pkgs = discover_workspaces(tmp_path)
    assert len(pkgs) == 1
    assert pkgs[0].name == "@app/core"

def test_workspace_traversal_rejection(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - '../../external/*'\n")
    with pytest.raises(ValueError, match="Traversal path detected"):
        discover_workspaces(tmp_path)
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/discovery/workspace.py` and connect `--workspace` flags to CLI and FastMCP.

### 4.3 REFACTOR Phase
Ensure cache keys in `.rush/cache.db` include workspace package identifiers to prevent cross-package cache collisions.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:40:00Z", "phase": 26, "tool": "rush_workspace", "event": "topology_discovered", "monorepo_type": "pnpm", "packages_count": 8}
{"timestamp": "2026-08-21T07:40:01Z", "phase": 26, "tool": "rush_workspace", "event": "execution_scoped", "package": "@app/core", "cwd": "packages/core"}
{"timestamp": "2026-08-21T07:40:02Z", "phase": 26, "tool": "rush_workspace", "event": "scan_completed", "package": "@app/core", "status": "passed"}
```

---

## 6. Step-by-Step Task Specifications

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
    """Parse pnpm-workspace.yaml, package.json workspaces, Cargo.toml workspace, go.work."""
    ...

def topological_sort_workspaces(packages: list[WorkspacePackage]) -> list[WorkspacePackage]:
    """Sort workspace packages based on internal dependency hierarchy."""
    ...
```

### Task 26.2: CLI Scoping Flags (`src/rush/cli.py`)
Add `--workspace`, `--all-workspaces`, and `--affected` to tool and suite commands.

### Task 26.3: CLI & FastMCP Registrations
Register workspace parameters in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Path Confinement**: Disallow any workspace path resolving outside the repository root.
2. **Subprocess Isolation**: Subprocess calls must use `stdin=DEVNULL`, `shell=False`.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
