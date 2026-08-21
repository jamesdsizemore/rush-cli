# Phase 37 Implementation Plan: Git Hotspots, Code Churn & Architectural Velocity Intelligence

> **Phase:** 37 of 40  
> **Milestone:** Git Intelligence, Architectural Velocity & Document Parity  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.9.0  
> **ADR References:** [ADR-0019: Native Graft Semantic Slicing & Tree-Sitter AST Engine](docs/adr/0019-native-graft-semantic-slicing-and-tree-sitter.md), [ADR-0024: Hardened Subprocess Git Invocations](docs/adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `tree-sitter==0.24.0`, `rich==13.9.4`, `mcp==1.28.1`  
> **Discovered External Engines:** `rumdl` (Rust markdown linter), `glow` (terminal markdown viewer), `miller` (`mlr` - high-speed NDJSON/CSV log processor)

---

## 1. Objective & Scope

Autonomous coding agents frequently make risky edits to core architectural bottlenecks without understanding the historical blast radius or commit churn of the modified modules. Furthermore, as features are added rapidly, internal documentation, README catalogs, and engine lists rapidly drift from code reality.

Phase 37 equips agents and developers with architectural velocity intelligence:
1. **Code Churn & Cyclomatic Complexity Hotspots (`rush git-hotspots`)**: Correlates Git commit frequency (churn) against AST cyclomatic complexity to identify fragile hotspot files at high risk of regression.
2. **Commit Blast Radius Analyzer (`rush git-blast-radius`)**: Traces import graphs and downstream test suites affected by modified files to predict breakages before merging.
3. **Git Repository Health Doctor (`rush git-doctor`)**: Analyzes dangling blobs, unreferenced commits, bloated packfiles, corrupted hooks, and recommends safe garbage collection commands (`git gc`, `git prune`).
4. **Zero-Drift Documentation Parity Guard (`rush doc-parity`)**: Automates verification and synchronization of documentation across all markdown files with discovered `rumdl` formatting.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Hotspot Ranking & Truncation)**: Limits hotspot reporting to the top 10 highest-risk modules rather than listing the entire repository.
- **`graft` (Targeted Blast-Radius Extraction)**: Extracts only the affected downstream symbol definitions rather than dumping full call-chains.
- **`context-mode` (Compact Tabular Matrix)**: Outputs concise markdown/NDJSON matrices mapping file churn vs complexity score.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/git/hotspots.py` (New: Git churn + Tree-Sitter complexity correlator)
- `src/rush/git/blast_radius.py` (New: Downstream dependency and test suite impact analyzer)
- `src/rush/git/doctor.py` (New: Repository packfile, reflog, and object database diagnostic tool)
- `src/rush/tools/doc_parity.py` (New: Documentation synchronization and `rumdl` engine wrapper)
- `src/rush/cli.py` (Modified: Register `rush git-hotspots`, `rush git-blast-radius`, `rush git-doctor`, `rush doc-parity`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Catalog specifications)

### Test & Fixture Files
- `tests/test_git_hotspots.py` (New: Commit churn counting and complexity calculations)
- `tests/test_git_blast_radius.py` (New: Import graph traversal and impacted test detection)
- `tests/test_git_doctor.py` (New: Packfile size analysis, orphan commit detection)
- `tests/test_doc_parity.py` (New: Parity check across markdown catalogs and tool registries)
- `tests/fixtures/git/repo_fixture/` (New: Synthetic Git commit history)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_git_hotspots.py
def test_hotspots_ranks_high_churn_complex_file(tmp_path):
    repo = init_git_repo(tmp_path)
    # Create high-churn complex file
    create_and_commit_churned_file(repo, "src/core.py", commits=15, complexity=25)
    create_and_commit_churned_file(repo, "src/simple.py", commits=1, complexity=1)
    
    hotspots = calculate_git_hotspots(tmp_path, top_n=5)
    assert len(hotspots) >= 1
    assert hotspots[0].path == "src/core.py"
    assert hotspots[0].risk_score > 50.0

# tests/test_git_blast_radius.py
def test_blast_radius_identifies_affected_tests(tmp_path):
    repo = init_sample_project(tmp_path)
    # Modify auth.py
    impact = analyze_commit_blast_radius(repo_root=tmp_path, target_files=["src/auth.py"])
    assert "tests/test_auth.py" in impact.affected_tests
    assert "src/api.py" in impact.affected_modules
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/git/hotspots.py`, `src/rush/git/blast_radius.py`, `src/rush/git/doctor.py`, and `src/rush/tools/doc_parity.py`.

### 4.3 REFACTOR Phase
Optimize Git log parsing using streaming `run_subprocess` buffers to ensure analysis completes in under 2 seconds on repositories with 10,000+ commits.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:45:00Z", "phase": 37, "tool": "rush_git_hotspots", "event": "hotspot_ranked", "file": "src/core.py", "churn": 34, "complexity": 28, "risk": 84.2}
{"timestamp": "2026-08-21T07:45:01Z", "phase": 37, "tool": "rush_git_blast_radius", "event": "impact_calculated", "affected_files": 12, "affected_tests": 4}
{"timestamp": "2026-08-21T07:45:02Z", "phase": 37, "tool": "rush_doc_parity", "event": "doc_synchronized", "files_checked": 164, "drift_detected": false}
```

---

## 6. Step-by-Step Task Specifications

### Task 37.1: Hotspot Risk Correlator (`src/rush/git/hotspots.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from rush.tools.base import ToolResult

@dataclass(frozen=True)
class HotspotRisk:
    path: str
    churn_count: int
    cyclomatic_complexity: int
    risk_score: float

def calculate_git_hotspots(repo_root: Path, top_n: int = 10) -> list[HotspotRisk]:
    """Calculate module risk by correlating Git revision frequency with AST complexity."""
    ...
```

### Task 37.2: Downstream Blast Radius Analyzer (`src/rush/git/blast_radius.py`)
Trace import graphs using Tree-Sitter to identify all modules and test files that depend on changed files.

### Task 37.3: Git Repository Health Doctor (`src/rush/git/doctor.py`)
Run non-destructive diagnostics on `.git/objects`, loose objects, packfiles, reflogs, and uncommitted stashes.

### Task 37.4: Documentation Parity Engine (`src/rush/tools/doc_parity.py`)
Audit and synchronize tool counts, engine counts, and link references across all documentation files. Discover `rumdl` for high-speed formatting.

### Task 37.5: CLI & FastMCP Registrations
Register all 4 tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Non-Destructive Doctor**: `rush git-doctor` must never run destructive commands (`git prune --now`) without user confirmation.
2. **Parity Invariant**: `scripts/sync_docs.py --check` must pass 100% after every documentation change.
3. **Performance**: Hotspot calculation must take <2s on medium repositories.
