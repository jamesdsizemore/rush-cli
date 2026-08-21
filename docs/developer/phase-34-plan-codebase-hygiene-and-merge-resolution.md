# Phase 34 Implementation Plan: Codebase Hygiene, Deprecation Enforcement & Merge Resolution

> **Phase:** 34 of 40  
> **Milestone:** Codebase Hygiene & Structural Merge Resolution  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.6.0  
> **ADR References:** [ADR-0019: Native Graft Semantic Slicing & Tree-Sitter AST Engine](../adr/0019-native-graft-semantic-slicing-and-tree-sitter.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md), [ADR-0025: Polyglot Grammar Expansion via `tree-sitter-language-pack`](../adr/0025-polyglot-grammar-expansion.md)  
> **Pinned Dependencies:** `tree-sitter==0.24.0`, `tree-sitter-language-pack==0.4.0`, `mcp==1.28.1`  
> **Embedded Static Datasets:** `src/rush/data/pypi_top50k.bin` (1.2 MB), `src/rush/data/npm_top50k.bin` (1.4 MB)

---

## 1. Objective & Scope

As codebases evolve, autonomous coding agents often hallucinate dependencies that mimic legitimate libraries (typosquatting supply chain attacks), reintroduce deprecated methods or legacy internal APIs, and fail catastrophically when encountering Git merge conflicts containing standard `<<<<<<<`, `=======`, `>>>>>>>` markers.

Phase 34 addresses these critical vectors by delivering:
1. **Deprecation Sentinel (`rush deprecate`)**: Enforces explicit deprecation timelines, flagging usages of `@deprecated` docstrings, `@warnings.deprecated`, or custom configuration rules past their scheduled removal dates.
2. **Dependency Typosquatting Guard (`rush typo-squat`)**: Offline Double-Array Trie verification against the top 50,000 PyPI and npm package names to prevent agents from introducing hallucinated malicious dependencies (e.g. `reqeusts` vs `requests`).
3. **Tree-Sitter 3-Way AST Merge Conflict Resolver (`rush git-resolve`)**: Resolves non-overlapping structural conflicts at the AST node level (e.g. two agents adding different methods to the same class or modifying independent import statements) without corrupting syntax.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Conflict Node Slicing)**: `rush git-resolve` extracts only the specific AST conflict region rather than asking the LLM to rewrite the entire 500-line file.
- **`graft` (Structural AST Merge Trees)**: Parses `OURS`, `THEIRS`, and `BASE` syntax trees to identify independent AST insertions, reconciling them deterministically in pure Python before invoking any model.
- **`context-mode` (Trie-Powered Instant Checks)**: Typosquatting verification executes in sub-millisecond local Trie searches without LLM prompt overhead.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/tools/deprecate.py` (New: Deprecation scanner and timeline validator)
- `src/rush/tools/typo_squat.py` (New: Double-Array Trie typosquatting detector)
- `src/rush/git/resolve.py` (New: Tree-Sitter 3-way AST structural merge engine)
- `src/rush/data/pypi_top50k.bin` (New: Pre-compiled top PyPI packages Trie)
- `src/rush/data/npm_top50k.bin` (New: Pre-compiled top npm packages Trie)
- `src/rush/cli.py` (Modified: Register `rush deprecate`, `rush typo-squat`, `rush git-resolve`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Tool specs)

### Test & Fixture Files
- `tests/test_deprecate.py` (New: Version timeline enforcement and `@deprecated` detection)
- `tests/test_typo_squat.py` (New: Levenshtein distance calculations against Trie datasets)
- `tests/test_git_resolve.py` (New: 3-way AST merge conflict resolution across imports, functions, classes)
- `tests/fixtures/conflicts/conflict_sample.py` (New: Synthesized Git conflict markers)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_typo_squat.py
def test_typosquatting_detection():
    suspicious_deps = ["reqeusts", "collorama", "loddash"]
    findings = check_dependencies_for_typosquats(suspicious_deps)
    assert len(findings) == 3
    assert findings[0].canonical_name == "requests"
    assert findings[0].similarity_score > 0.85

# tests/test_git_resolve.py
def test_ast_merge_resolves_independent_function_additions():
    base = "class Service:\n    def ping(self): return 'pong'\n"
    ours = "class Service:\n    def ping(self): return 'pong'\n    def user_count(self): return 10\n"
    theirs = "class Service:\n    def ping(self): return 'pong'\n    def health(self): return 'ok'\n"
    
    merged_code = resolve_3way_ast_merge(base=base, ours=ours, theirs=theirs, language="python")
    assert "def user_count" in merged_code
    assert "def health" in merged_code
    assert merged_code.count("class Service:") == 1
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/tools/deprecate.py`, `src/rush/tools/typo_squat.py`, and `src/rush/git/resolve.py`.

### 4.3 REFACTOR Phase
Ensure 3-way AST merge handles syntax errors gracefully, falling back to clean structured error diagnostics if AST conflicts directly overlap on the same token.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:30:00Z", "phase": 34, "tool": "rush_typo_squat", "event": "typosquat_flagged", "package": "reqeusts", "suggested": "requests", "distance": 1}
{"timestamp": "2026-08-21T07:30:01Z", "phase": 34, "tool": "rush_deprecate", "event": "expired_api_used", "symbol": "legacy_auth", "deadline": "2026-01-01", "file": "src/api.py"}
{"timestamp": "2026-08-21T07:30:02Z", "phase": 34, "tool": "rush_git_resolve", "event": "conflict_resolved_ast", "file": "src/service.py", "nodes_merged": 2}
```

---

## 6. Step-by-Step Task Specifications

### Task 34.1: Double-Array Trie Typosquatting Checker (`src/rush/tools/typo_squat.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from rush.tools.base import ToolResult, Finding

def check_package_typosquats(manifest_path: Path) -> ToolResult:
    """Verify dependencies against embedded Trie dataset to detect hallucinated/typosquatted packages."""
    ...
```

### Task 34.2: Deprecation Timeline Validator (`src/rush/tools/deprecate.py`)
Extract deprecation decorators and docstrings, validating them against configured version milestones.

### Task 34.3: Tree-Sitter 3-Way AST Conflict Resolver (`src/rush/git/resolve.py`)
Parse Git conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`), construct separate ASTs for `OURS` and `THEIRS`, and merge non-colliding syntax nodes.

### Task 34.4: CLI & FastMCP Registrations
Register all 3 tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Zero False Positives in Typosquatting**: High threshold Levenshtein cutoff (>= 0.88) to prevent false alerts on legitimate novel packages.
2. **Merge Safety Invariant**: Merged code must pass AST validation (`ast.parse` for Python, Tree-Sitter for polyglot) before writing to disk.
3. **Doc Parity**: Synchronize and verify `/docs`.
