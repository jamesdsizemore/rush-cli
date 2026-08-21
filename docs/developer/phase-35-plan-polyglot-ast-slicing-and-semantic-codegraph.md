# Phase 35 Implementation Plan: Polyglot AST Slicing, Semantic Code Graph & Safe AST-Patcher

> **Phase:** 35 of 40  
> **Milestone:** Semantic CodeGraph & Deterministic AST Patching  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.7.0  
> **ADR References:** [ADR-0019: Native Graft Semantic Slicing & Tree-Sitter AST Engine](../adr/0019-native-graft-semantic-slicing-and-tree-sitter.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md), [ADR-0025: Polyglot Grammar Expansion via `tree-sitter-language-pack`](../adr/0025-polyglot-grammar-expansion.md)  
> **Pinned Dependencies:** `tree-sitter==0.24.0`, `tree-sitter-language-pack==0.4.0`, `mcp==1.28.1`  
> **Discovered External Engines:** `putout` (Node.js declarative codemod engine)

---

## 1. Objective & Scope

Autonomous coding agents frequently make hallucinated regex substitutions or fail on large whole-file overwrites when refactoring code. Furthermore, reading entire multi-thousand line files just to inspect a single helper function exhausts context windows and degrades model reasoning.

Phase 35 delivers Rush's core semantic intelligence and structural code manipulation system:
1. **Semantic Symbol Slicer (`rush_graft_slice`)**: In-process Tree-Sitter symbol extraction that returns verbatim symbol source code, enclosing class context, type signatures, and 1-hop caller/callee paths across 370+ programming languages.
2. **Deterministic AST Patcher (`rush_apply_ast_patch`)**: Applies structural AST replacements targeting specific syntax nodes (function bodies, class methods, import statements) and verifies post-patch syntax validity before committing to disk.
3. **Declarative Codemod Runner (`rush refactor`)**: Discovered integration with `putout` and native Python AST transforms for batch declarative refactorings.
4. **Symbol History Tracer (`rush git-trace`)**: Uses Tree-Sitter to track the evolution and commit lineage of an individual function or class across historical Git revisions (`git log -L`).

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`graft` (Direct AST Symbol Extraction)**: Reduces prompt sizes by 80–95%. Instead of sending a 2,000-line file to an agent, `rush_graft_slice` extracts only the 40-line target function and its type definitions.
- **`rtk` (Syntax Node Compression)**: Strips irrelevant comments and docstrings when requested by the agent via `--compact` mode.
- **`context-mode` (Line-Numbered Verbatim Snippets)**: Slices are formatted with exact line numbers for precise downstream patching.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/ast_patcher.py` (New: In-process Tree-Sitter AST parser, symbol extractor, and node patcher)
- `src/rush/tools/graft_slice.py` (New: Semantic slicing FastMCP tool and CLI handler)
- `src/rush/tools/refactor.py` (New: Declarative codemod runner with `putout` discovery)
- `src/rush/git/trace.py` (New: Tree-Sitter AST line-range calculator for Git history tracing)
- `src/rush/cli.py` (Modified: Register `rush graft-slice`, `rush refactor`, `rush git-trace`)
- `src/rush/mcp_server.py` (Modified: Register `rush_graft_slice`, `rush_apply_ast_patch`)
- `src/rush/catalog.py` (Modified: Tool specifications)

### Test & Fixture Files
- `tests/test_ast_slicer.py` (New: Symbol extraction across Python, TypeScript, Rust, Go)
- `tests/test_ast_patcher.py` (New: Node replacement, indentation preservation, syntax validation)
- `tests/test_refactor_codemods.py` (New: Codemod execution, discovered engine handling)
- `tests/test_git_trace.py` (New: Function evolution tracking through historical renames)
- `tests/fixtures/ast/sample_classes.py` & `sample_classes.ts` (New: Test files)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_ast_slicer.py
def test_graft_slice_extracts_target_function():
    code = """
import os

def helper_a():
    return 1

def target_function(x: int) -> int:
    # Target docstring
    return x * 2

def helper_b():
    return 3
"""
    slice_res = extract_symbol_slice(code, symbol_name="target_function", language="python")
    assert "def target_function" in slice_res.code
    assert "helper_a" not in slice_res.code
    assert "helper_b" not in slice_res.code
    assert slice_res.start_line == 7
    assert slice_res.end_line == 9

# tests/test_ast_patcher.py
def test_apply_ast_patch_replaces_function_body():
    original = "def compute(x):\n    return x + 1\n"
    new_func = "def compute(x):\n    return x * 10\n"
    patched = apply_symbol_patch(original, symbol_name="compute", replacement_code=new_func, language="python")
    assert "return x * 10" in patched
    assert "return x + 1" not in patched
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/ast_patcher.py`, `src/rush/tools/graft_slice.py`, `src/rush/tools/refactor.py`, and `src/rush/git/trace.py`.

### 4.3 REFACTOR Phase
Ensure Tree-Sitter grammars are loaded lazily and cached in an in-memory registry to avoid re-compilation overhead during multi-turn agent sessions.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:35:00Z", "phase": 35, "tool": "rush_graft_slice", "event": "symbol_sliced", "symbol": "calculate_tax", "file": "src/billing.py", "lines": "120-145", "tokens": 180}
{"timestamp": "2026-08-21T07:35:01Z", "phase": 35, "tool": "rush_apply_ast_patch", "event": "patch_applied", "symbol": "calculate_tax", "syntax_valid": true}
{"timestamp": "2026-08-21T07:35:02Z", "phase": 35, "tool": "rush_git_trace", "event": "lineage_traced", "symbol": "calculate_tax", "commits_found": 5}
```

---

## 6. Step-by-Step Task Specifications

### Task 35.1: Polyglot Tree-Sitter Symbol Slicer (`src/rush/tools/graft_slice.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from rush.tools.base import ToolResult

@dataclass(frozen=True)
class SymbolSlice:
    symbol_name: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    code: str
    docstring: str | None
    callers: list[str]
    callees: list[str]

def graft_slice_file(file_path: Path, symbol_name: str) -> SymbolSlice:
    """Slice exact symbol definition and 1-hop dependency graph from source file."""
    ...
```

### Task 35.2: Deterministic AST Node Patcher (`src/rush/ast_patcher.py`)
Replace target AST nodes with replacement source, preserving surrounding indentation and comments, and validating syntax before writing.

### Task 35.3: Declarative Codemod Engine (`src/rush/tools/refactor.py`)
Discover `putout` and execute declarative AST structural transforms across repository files.

### Task 35.4: AST-Aware Git Lineage Tracer (`src/rush/git/trace.py`)
Extract function line boundaries across commits and run `git log -L` to present the historical evolution of a symbol.

### Task 35.5: CLI & FastMCP Registrations
Register all tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Syntax Invariant**: Patches that produce syntax errors must abort immediately without touching the filesystem.
2. **Polyglot Coverage**: Slicing must succeed across Python, TypeScript, JavaScript, Go, and Rust.
3. **Doc Parity**: Synchronize and verify all `/docs` files.
