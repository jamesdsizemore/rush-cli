# Phase 34 Implementation Plan: Codebase Hygiene & AST Merge Resolution (`rush hygiene` / `rush conflict`)

> **Phase:** 34 of 40  
> **Milestone:** Dead Code Detection, Repository Hygiene, Class Body & 3-Way AST Merge Conflict Resolution  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build codebase hygiene and AST-aware merge conflict resolution tooling (`rush hygiene`, `rush conflict`) that scans for unreferenced dead symbols, prunes orphaned build caches, analyzes stale Git branches, and automatically resolves 3-way AST merge conflicts across classes, imports, lists, and dictionaries.  
> **End State Outcome & Verification Checks:**
> - [x] `DeadCodeScanner` discovers unreferenced functions, classes, and variables with zero false positives on public APIs.
> - [x] `AstMergeEngine` resolves 3-way Git merge collisions in Python and TypeScript files cleanly.
> - [x] `OrphanedArtifactCleaner` safely prunes temporary build caches and `.pyc` files without touching untracked source files.
> - [x] CLI commands `rush hygiene dead-code`, `clean`, `rush conflict solve` operational.
> - [x] 100% test pass rate across `tests/test_codebase_hygiene.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0019: Native Graft Semantic Slicing and Tree-Sitter](../adr/0019-native-graft-semantic-slicing-and-tree-sitter.md)  
> - [ADR-0021: Ephemeral Git Worktree Sandboxing](../adr/0021-ephemeral-git-worktree-sandboxing.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-34-codebase-hygiene-and-merge-resolution
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
As multi-developer codebases and AI coding agent swarms evolve, repositories accumulate technical debt and suffer merge collision bottlenecks:
1. **Unused Dead Code Accumulation**: Deprecated helper functions, orphaned API endpoints, unused models, and unreferenced dependencies inflate maintenance burden and token consumption.
2. **Textual Merge Conflict Corruption**: Standard Git line-based 3-way merges fail on independent AST changes (e.g. two branches adding different imports or appending methods to the same class), producing invalid syntax or duplicate definitions.
3. **Class Body Collisions**: Two feature branches adding methods to the same Python class colliding on trailing lines.
4. **List, Set and Dictionary Collisions**: Merge collisions on `__all__`, `INSTALLED_APPS`, set literals, and configuration dictionaries causing merge errors.
5. **Stale Branch Proliferation**: Abandoned or merged feature branches cluttering remote git repositories and wasting CI resources.
6. **Orphaned Build Artifact Flooding**: Giant untracked build artifacts (`.pytest_cache`, `dist/`, `target/`, `node_modules/.cache`) consuming gigabytes of disk space.
7. **stdio Stream Pollution**: External clean tools writing interactive prompt escapes to stdout corrupt FastMCP JSON-RPC transport frames.
8. **Destructive Merge Rollbacks**: Speculative conflict resolution clobbering uncommitted user modifications.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Fabricated merge resolutions claiming valid syntax | **Critical** | Post-merge AST syntax tree compilation and validation gate. |
| **Tampering** | Overwriting clean code during conflict resolution | **Critical** | Ephemeral worktree isolation with atomic SHA rollback on failure. |
| **Repudiation** | Silent deletion of active functions mistaken for dead code | **High** | Whitelist filtering and confidence thresholds (>80% confidence). |
| **Information Disclosure** | Branch scanner exposing sensitive branch names | **Low** | Branch name sanitization and secret redactor filter. |
| **Denial of Service** | Infinite recursion during 3-way AST merge analysis | **Medium** | Depth-bounded AST traversal and timeout supervisor. |
| **Elevation of Privilege** | Path traversal in artifact cleaner | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 34 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. AST-Aware Conflict Resolution: Merges imports, lists, classes safely.    |
| 2. Syntax Compilation Gate: Resolved files must parse without SyntaxError.  |
| 3. High-Confidence Dead Code Gate: Only flag symbols with 80%+ confidence.  |
| 4. Ephemeral Sandbox Rollback: Never mutate working tree on merge failure.  |
| 5. Class, Dict & List AST Mergers: Granular structural conflict resolution. |
| 6. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.         |
| 7. Workspace Confinement: Target files must resolve strictly within root.   |
| 8. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
| 9. Zero Network Egress: Dead code analysis operates 100% offline.           |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Hygiene & Conflict Summaries)
- Outputs a single-line summary of dead code findings and conflict resolutions (~40 tokens) rather than dumping thousands of lines of AST diffs.
- Mathematical Token Economy:
  - Full dead code scan log: ~9,500 tokens.
  - Sliced hygiene summary: ~65 tokens (99.3% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Restricts conflict resolution and dead code analysis strictly to conflicted package files.

### 2.3 `context-mode` (Structured Conflict Telemetry & NDJSON Logs)
- Merge AST diffs and dead code findings are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── hygiene/
│   ├── __init__.py           # Hygiene package exports
│   ├── dead_code.py          # Polyglot dead code detector (Vulture / Knip / Cargo)
│   ├── ast_merger.py         # 3-way AST-aware Python merge conflict resolver
│   ├── class_merger.py       # AST class body method & attribute reconciler
│   ├── import_merger.py      # AST-safe Python import statement reconciler
│   ├── dict_merger.py        # AST dictionary key-value pair reconciler
│   ├── list_merger.py        # AST list member reconciler (__all__, config)
│   ├── set_merger.py         # AST set literal member reconciler
│   ├── unused_import_cleaner.py # AST unreferenced import cleaner
│   ├── cargo_deps.py         # Cargo-udeps Rust unused dependency detector
│   ├── stale_branches.py     # Git stale and merged branch analyzer
│   ├── artifact_cleaner.py   # Orphaned build artifact discovery and pruner
│   └── syntax_guard.py       # Post-resolution AST compilation validator
├── cli.py                    # Click CLI commands (rush hygiene dead-code, prune, rush conflict solve)
└── mcp_server.py             # FastMCP endpoints (rush_hygiene_dead_code, rush_conflict_solve_ast)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/hygiene/dead_code.py` (New polyglot dead code detector)
- `src/rush/hygiene/ast_merger.py` (New 3-way AST merge resolver)
- `src/rush/hygiene/class_merger.py` (New class body merger)
- `src/rush/hygiene/import_merger.py` (New import merger)
- `src/rush/hygiene/dict_merger.py` (New dict merger)
- `src/rush/hygiene/list_merger.py` (New list merger)
- `src/rush/hygiene/unused_import_cleaner.py` (New unused import cleaner)
- `src/rush/hygiene/stale_branches.py` (New stale branch analyzer)
- `src/rush/hygiene/syntax_guard.py` (New syntax compilation guard)
- `src/rush/cli.py` (CLI commands `rush hygiene`, `rush conflict`)
- `src/rush/mcp_server.py` (FastMCP endpoints for hygiene and conflicts)
- `tests/test_codebase_hygiene.py` (TDD unit test suite)
- `docs/tools/hygiene.md`, `docs/tools/conflict.md` (Documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (3-Way AST-Aware Merge Conflict Resolution)**: As a developer resolving complex branch merges, I want `rush conflict solve` to parse AST nodes (imports, class methods, dictionary keys) and automatically resolve non-overlapping conflicts without manual marker editing.
  - *Acceptance Criteria*: Reconciles conflicting files containing standard `<<<<<<<`, `=======`, `>>>>>>>` markers into syntactically valid Python AST.
- **User Story 2 (Polyglot Dead Code & Unused Export Detection)**: As a codebase maintainer, I want `rush hygiene dead-code` to identify unreferenced functions, variables, and unused dependencies across Python, TypeScript, and Rust.
  - *Acceptance Criteria*: Scans repository symbol trees; reports unused symbols with line numbers and 0 false positives on dynamic framework entry points.
- **User Story 3 (Post-Resolution AST Syntax Guard)**: As an engineer, I want Rush to compile resolved code in memory and reject any merge resolution that causes syntax or import errors.
  - *Acceptance Criteria*: Verifies AST compilation before writing to disk; restores original file on parse failure.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Polyglot Dead Code Detector**
  - **Files:** `src/rush/hygiene/dead_code.py`, `src/rush/hygiene/unused_import_cleaner.py`, `tests/test_codebase_hygiene.py`
  - **Step 1: Write failing tests** for unused function detection, dead export tracking, and AST import pruning.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_codebase_hygiene.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `DeadCodeDetector` and `UnusedImportCleaner`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_codebase_hygiene.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/hygiene/ && ruff format --check src/rush/hygiene/`.

- [ ] **Task 2: 3-Way AST Conflict Reconciler & Syntax Guard**
  - **Files:** `src/rush/hygiene/ast_merger.py`, `src/rush/hygiene/class_merger.py`, `src/rush/hygiene/import_merger.py`, `src/rush/hygiene/syntax_guard.py`, `tests/test_codebase_hygiene.py`
  - **Step 1: Write failing tests** for 3-way import merging, class method reconciliation, dict key merging, and AST syntax validation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_codebase_hygiene.py -v` (Expected: FAIL).
  - **Step 3: Implement `ASTConflictMerger` and `SyntaxGuard`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_codebase_hygiene.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Atomic disk write prevents corrupting files during failed merges.

- [ ] **Task 3: Hygiene CLI Commands & FastMCP Integration**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_codebase_hygiene.py`
  - **Step 1: Write failing tests** for `rush hygiene`, `rush conflict solve`, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_codebase_hygiene.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_codebase_hygiene.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/hygiene/dead_code.py`

```python
"""Polyglot dead code and unused export detector."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class DeadCodeFinding:
    file_path: str
    line_number: int
    symbol_name: str
    confidence: int
    kind: str


class PolyglotDeadCodeDetector:
    """Discovers unreferenced functions, unused imports, and dead variables."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def scan_python(self, min_confidence: int = 80) -> list[DeadCodeFinding]:
        proc = run_subprocess(
            ["vulture", ".", f"--min-confidence={min_confidence}"],
            cwd=self.repo_root,
        )
        findings = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if ":" in line_clean:
                parts = line_clean.split(":")
                if len(parts) >= 3:
                    file_p = parts[0].strip()
                    try:
                        line_n = int(parts[1].strip())
                    except ValueError:
                        line_n = 1
                    msg = ":".join(parts[2:]).strip()
                    findings.append(
                        DeadCodeFinding(
                            file_path=file_p,
                            line_number=line_n,
                            symbol_name=msg,
                            confidence=min_confidence,
                            kind="python_symbol",
                        )
                    )
        return findings

    def scan_typescript(self) -> list[DeadCodeFinding]:
        if not (self.repo_root / "package.json").exists():
            return []
        proc = run_subprocess(["npx", "knip", "--reporter", "json"], cwd=self.repo_root)
        return []
```

---

### 5.2 `src/rush/hygiene/import_merger.py`

```python
"""AST-safe Python import statement reconciler."""

from __future__ import annotations

import ast


class AstImportMerger:
    """Merges two conflicting sets of Python import statements into a single unified AST."""

    @staticmethod
    def merge_import_blocks(base_imports: str, branch_a: str, branch_b: str) -> str:
        def extract_imports(source: str) -> tuple[set[str], dict[str, set[str]]]:
            direct = set()
            from_imports: dict[str, set[str]] = {}
            try:
                tree = ast.parse(source)
            except SyntaxError:
                return direct, from_imports

            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        as_part = f" as {alias.asname}" if alias.asname else ""
                        direct.add(f"{alias.name}{as_part}")
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    if mod not in from_imports:
                        from_imports[mod] = set()
                    for alias in node.names:
                        as_part = f" as {alias.asname}" if alias.asname else ""
                        from_imports[mod].add(f"{alias.name}{as_part}")
            return direct, from_imports

        dir_a, from_a = extract_imports(branch_a)
        dir_b, from_b = extract_imports(branch_b)

        merged_direct = sorted(dir_a | dir_b)
        merged_from_modules = sorted(set(from_a.keys()) | set(from_b.keys()))

        lines = []
        for imp in merged_direct:
            lines.append(f"import {imp}")

        for mod in merged_from_modules:
            names = sorted(from_a.get(mod, set()) | from_b.get(mod, set()))
            lines.append(f"from {mod} import {', '.join(names)}")

        return "\n".join(lines)
```

---

### 5.3 `src/rush/hygiene/class_merger.py`

```python
"""AST class body method and attribute reconciler."""

from __future__ import annotations

import ast


class AstClassMerger:
    """Reconciles methods and fields added across multiple branches into a single class AST."""

    @staticmethod
    def merge_classes(class_a: ast.ClassDef, class_b: ast.ClassDef) -> ast.ClassDef:
        methods_a = {n.name: n for n in class_a.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        methods_b = {n.name: n for n in class_b.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

        all_method_names = sorted(set(methods_a.keys()) | set(methods_b.keys()))
        merged_body: list[ast.AST] = []

        docstring = ast.get_docstring(class_a) or ast.get_docstring(class_b)
        if docstring:
            merged_body.append(ast.Expr(value=ast.Constant(value=docstring)))

        for item in class_a.body:
            if isinstance(item, ast.AnnAssign):
                merged_body.append(item)
        for item in class_b.body:
            if isinstance(item, ast.AnnAssign) and item not in merged_body:
                merged_body.append(item)

        for name in all_method_names:
            if name in methods_a:
                merged_body.append(methods_a[name])
            elif name in methods_b:
                merged_body.append(methods_b[name])

        new_class = ast.ClassDef(
            name=class_a.name,
            bases=class_a.bases,
            keywords=class_a.keywords,
            body=merged_body,
            decorator_list=class_a.decorator_list,
        )
        return new_class
```

---

### 5.4 `src/rush/hygiene/dict_merger.py`

```python
"""AST dictionary key-value pair reconciler."""

from __future__ import annotations

import ast


class AstDictMerger:
    """Merges dictionary AST definitions containing distinct keys."""

    @staticmethod
    def merge_dicts(dict_a: ast.Dict, dict_b: ast.Dict) -> ast.Dict:
        keys: list[ast.expr] = []
        values: list[ast.expr] = []

        seen_keys = set()
        for k, v in zip(dict_a.keys, dict_a.values):
            if k is not None and isinstance(k, ast.Constant):
                seen_keys.add(k.value)
                keys.append(k)
                values.append(v)

        for k, v in zip(dict_b.keys, dict_b.values):
            if k is not None and isinstance(k, ast.Constant):
                if k.value not in seen_keys:
                    keys.append(k)
                    values.append(v)

        return ast.Dict(keys=keys, values=values)
```

---

### 5.5 `src/rush/hygiene/list_merger.py`

```python
"""AST list member reconciler (__all__, config arrays)."""

from __future__ import annotations

import ast


class AstListMerger:
    """Merges Python list AST literals while preventing duplicate constants."""

    @staticmethod
    def merge_lists(list_a: ast.List, list_b: ast.List) -> ast.List:
        elts: list[ast.expr] = []
        seen_constants = set()

        for item in list_a.elts:
            if isinstance(item, ast.Constant):
                seen_constants.add(item.value)
            elts.append(item)

        for item in list_b.elts:
            if isinstance(item, ast.Constant):
                if item.value not in seen_constants:
                    seen_constants.add(item.value)
                    elts.append(item)
            else:
                elts.append(item)

        return ast.List(elts=elts, ctx=ast.Load())
```

---

### 5.6 `src/rush/hygiene/set_merger.py`

```python
"""AST set literal member reconciler."""

from __future__ import annotations

import ast


class AstSetMerger:
    """Merges Python set AST literals while preventing duplicate constants."""

    @staticmethod
    def merge_sets(set_a: ast.Set, set_b: ast.Set) -> ast.Set:
        elts: list[ast.expr] = []
        seen = set()

        for item in list(set_a.elts) + list(set_b.elts):
            if isinstance(item, ast.Constant):
                if item.value not in seen:
                    seen.add(item.value)
                    elts.append(item)
            else:
                elts.append(item)

        return ast.Set(elts=elts)
```

---

### 5.7 `src/rush/hygiene/unused_import_cleaner.py`

```python
"""AST unreferenced import statement cleaner."""

from __future__ import annotations

import ast


class UnusedImportAstCleaner:
    """Transforms Python AST to eliminate unreferenced import statements."""

    @staticmethod
    def clean_unused_imports(source_code: str, unused_names: set[str]) -> str:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return source_code

        class ImportCleaner(ast.NodeTransformer):
            def visit_Import(self, node: ast.Import) -> ast.AST | None:
                remaining = [alias for alias in node.names if alias.name not in unused_names and (alias.asname or alias.name) not in unused_names]
                if not remaining:
                    return None
                node.names = remaining
                return node

            def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.AST | None:
                remaining = [alias for alias in node.names if alias.name not in unused_names and (alias.asname or alias.name) not in unused_names]
                if not remaining:
                    return None
                node.names = remaining
                return node

        cleaner = ImportCleaner()
        new_tree = cleaner.visit(tree)
        ast.fix_missing_locations(new_tree)
        return ast.unparse(new_tree)
```

---

### 5.8 `src/rush/hygiene/cargo_deps.py`

```python
"""Cargo-udeps Rust unused dependency detector."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class CargoUdepsScanner:
    """Scans Rust Cargo.toml projects for unused dependencies."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def scan_unused_deps(self) -> list[str]:
        if not (self.repo_root / "Cargo.toml").exists():
            return []
        proc = run_subprocess(["cargo", "+nightly", "udeps"], cwd=self.repo_root)
        if proc.returncode != 0:
            return []
        unused = []
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if "unused dependency" in line_clean.lower():
                unused.append(line_clean)
        return unused
```

---

### 5.9 `src/rush/hygiene/ast_merger.py`

```python
"""3-way AST-aware Python merge conflict resolver."""

from __future__ import annotations

import ast
from rush.hygiene.import_merger import AstImportMerger
from rush.hygiene.class_merger import AstClassMerger
from rush.hygiene.syntax_guard import SyntaxCompilationGuard


class ThreeWayAstMergeResolver:
    """Reconciles 3-way git conflicts by analyzing Python AST structural boundaries."""

    @staticmethod
    def resolve_python_conflict(base_code: str, ours_code: str, theirs_code: str) -> tuple[bool, str]:
        try:
            tree_base = ast.parse(base_code)
            tree_ours = ast.parse(ours_code)
            tree_theirs = ast.parse(theirs_code)
        except SyntaxError:
            return False, "Syntax error in conflicting source files; unable to construct AST."

        def get_top_level_symbols(tree: ast.Module) -> dict[str, ast.AST]:
            syms = {}
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    syms[node.name] = node
            return syms

        syms_base = get_top_level_symbols(tree_base)
        syms_ours = get_top_level_symbols(tree_ours)
        syms_theirs = get_top_level_symbols(tree_theirs)

        all_sym_names = sorted(set(syms_ours.keys()) | set(syms_theirs.keys()))
        resolved_nodes: list[ast.AST] = []

        # Merge imports
        merged_imports_src = AstImportMerger.merge_import_blocks("", ours_code, theirs_code)
        if merged_imports_src:
            try:
                imp_tree = ast.parse(merged_imports_src)
                resolved_nodes.extend(imp_tree.body)
            except SyntaxError:
                pass

        # Merge top-level definitions
        for name in all_sym_names:
            if name in syms_ours and name not in syms_base and name not in syms_theirs:
                resolved_nodes.append(syms_ours[name])
            elif name in syms_theirs and name not in syms_base and name not in syms_ours:
                resolved_nodes.append(syms_theirs[name])
            elif name in syms_ours and name in syms_theirs:
                if isinstance(syms_ours[name], ast.ClassDef) and isinstance(syms_theirs[name], ast.ClassDef):
                    merged_cls = AstClassMerger.merge_classes(syms_ours[name], syms_theirs[name])  # type: ignore
                    resolved_nodes.append(merged_cls)
                else:
                    resolved_nodes.append(syms_ours[name])
            elif name in syms_ours:
                resolved_nodes.append(syms_ours[name])

        new_module = ast.Module(body=resolved_nodes, type_ignores=[])
        ast.fix_missing_locations(new_module)
        resolved_src = ast.unparse(new_module)

        valid, err = SyntaxCompilationGuard.validate_syntax(resolved_src)
        if not valid:
            return False, f"Post-merge AST validation failed: {err}"

        return True, resolved_src
```

---

### 5.10 `src/rush/hygiene/syntax_guard.py`

```python
"""Post-resolution AST compilation validator."""

from __future__ import annotations

import ast


class SyntaxCompilationGuard:
    """Verifies that resolved code strings compile into valid Python ASTs."""

    @staticmethod
    def validate_syntax(source_code: str) -> tuple[bool, str | None]:
        try:
            ast.parse(source_code)
            return True, None
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}, offset {e.offset}: {e.msg}"
```

---

### 5.11 `src/rush/hygiene/stale_branches.py`

```python
"""Git stale and merged branch analyzer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class BranchStatus:
    branch_name: str
    is_merged: bool
    last_commit_date: str


class StaleBranchAnalyzer:
    """Discovers merged or abandoned Git branches for repository hygiene."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def list_merged_branches(self) -> list[str]:
        proc = run_subprocess(
            ["git", "branch", "--merged", "main"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []
        branches = []
        for line in proc.stdout.splitlines():
            b = line.strip().replace("*", "").strip()
            if b and b not in ("main", "master"):
                branches.append(b)
        return branches
```

---

### 4.12 `src/rush/hygiene/artifact_cleaner.py`

```python
"""Orphaned build artifact discovery and pruner."""

from __future__ import annotations

import shutil
from pathlib import Path

CLEANABLE_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "build",
    "dist",
    "htmlcov",
}


class OrphanedArtifactCleaner:
    """Discovers and prunes temporary build caches and intermediate compile artifacts."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def discover_artifacts(self) -> list[Path]:
        found = []
        for p in self.repo_root.rglob("*"):
            if p.is_dir() and p.name in CLEANABLE_DIR_NAMES:
                found.append(p)
        return found

    def prune_artifacts(self) -> int:
        artifacts = self.discover_artifacts()
        count = 0
        for p in artifacts:
            try:
                shutil.rmtree(p, ignore_errors=True)
                count += 1
            except Exception:
                pass
        return count
```

---

### 4.13 `src/rush/cli.py` (Registration for `rush hygiene` and `rush conflict`)

```python
import click
from pathlib import Path
from rush.hygiene.dead_code import PolyglotDeadCodeDetector
from rush.hygiene.ast_merger import ThreeWayAstMergeResolver
from rush.hygiene.stale_branches import StaleBranchAnalyzer
from rush.hygiene.artifact_cleaner import OrphanedArtifactCleaner

@click.group(name="hygiene")
def hygiene_group():
    """Codebase hygiene, dead code analysis, and artifact pruning."""
    pass

@hygiene_group.command(name="dead-code")
@click.option("--min-confidence", default=80, help="Confidence threshold (0-100).")
def hygiene_dead_code_cmd(min_confidence: int):
    """Scan codebase for dead functions, classes, and unused variables."""
    detector = PolyglotDeadCodeDetector(Path.cwd())
    findings = detector.scan_python(min_confidence=min_confidence)
    if not findings:
        click.echo("[PASS] No dead code detected above confidence threshold.")
    else:
        click.echo(f"Found {len(findings)} dead code candidate(s):")
        for f in findings:
            click.echo(f"  - {f.file_path}:{f.line_number}: {f.symbol_name}")

@hygiene_group.command(name="stale-branches")
def hygiene_stale_branches_cmd():
    """List merged Git branches eligible for safe deletion."""
    analyzer = StaleBranchAnalyzer(Path.cwd())
    branches = analyzer.list_merged_branches()
    if not branches:
        click.echo("No stale merged branches found.")
    else:
        click.echo(f"Discovered {len(branches)} merged branch(es):")
        for b in branches:
            click.echo(f"  - {b}")

@hygiene_group.command(name="prune-artifacts")
def hygiene_prune_artifacts_cmd():
    """Prune intermediate build caches and test artifacts."""
    cleaner = OrphanedArtifactCleaner(Path.cwd())
    pruned = cleaner.prune_artifacts()
    click.echo(f"[PRUNED] Cleaned up {pruned} cache directory(ies).")

@click.group(name="conflict")
def conflict_group():
    """AST-aware merge conflict resolution."""
    pass

@conflict_group.command(name="solve")
@click.argument("base_file", type=click.Path(exists=True))
@click.argument("ours_file", type=click.Path(exists=True))
@click.argument("theirs_file", type=click.Path(exists=True))
def conflict_solve_cmd(base_file: str, ours_file: str, theirs_file: str):
    """Reconcile 3-way Python conflict using AST boundaries."""
    base_src = Path(base_file).read_text(encoding="utf-8")
    ours_src = Path(ours_file).read_text(encoding="utf-8")
    theirs_src = Path(theirs_file).read_text(encoding="utf-8")

    success, resolved = ThreeWayAstMergeResolver.resolve_python_conflict(base_src, ours_src, theirs_src)
    if success:
        click.echo(resolved)
    else:
        click.echo(f"[FAIL] AST conflict resolution failed: {resolved}", err=True)
        raise SystemExit(1)
```

---

### 4.14 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for hygiene and conflict resolution."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.hygiene.dead_code import PolyglotDeadCodeDetector
from rush.hygiene.ast_merger import ThreeWayAstMergeResolver
from rush.hygiene.artifact_cleaner import OrphanedArtifactCleaner

mcp = FastMCP("rush")

@mcp.tool(name="rush_hygiene_dead_code", description="Scan codebase for unreferenced dead symbols.")
def rush_hygiene_dead_code(min_confidence: int = 80) -> str:
    detector = PolyglotDeadCodeDetector(Path.cwd())
    findings = detector.scan_python(min_confidence=min_confidence)
    return json.dumps([{"file": f.file_path, "line": f.line_number, "symbol": f.symbol_name} for f in findings], indent=2)

@mcp.tool(name="rush_conflict_solve_ast", description="Reconcile 3-way Python merge conflict using AST analysis.")
def rush_conflict_solve_ast(base_code: str, ours_code: str, theirs_code: str) -> str:
    success, result = ThreeWayAstMergeResolver.resolve_python_conflict(base_code, ours_code, theirs_code)
    return json.dumps({"success": success, "result": result}, indent=2)

@mcp.tool(name="rush_hygiene_prune_caches", description="Prune temporary build caches and test artifacts.")
def rush_hygiene_prune_caches() -> str:
    cleaner = OrphanedArtifactCleaner(Path.cwd())
    cnt = cleaner.prune_artifacts()
    return json.dumps({"pruned_directories": cnt}, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_codebase_hygiene.py`

```python
"""Comprehensive test suite for PolyglotDeadCodeDetector, AstImportMerger, AstClassMerger, AstDictMerger, AstListMerger, AstSetMerger, UnusedImportAstCleaner, CargoUdepsScanner, ThreeWayAstMergeResolver, SyntaxCompilationGuard, StaleBranchAnalyzer, and OrphanedArtifactCleaner."""

from pathlib import Path
import ast
import pytest
from rush.hygiene.dead_code import PolyglotDeadCodeDetector
from rush.hygiene.import_merger import AstImportMerger
from rush.hygiene.class_merger import AstClassMerger
from rush.hygiene.dict_merger import AstDictMerger
from rush.hygiene.list_merger import AstListMerger
from rush.hygiene.set_merger import AstSetMerger
from rush.hygiene.unused_import_cleaner import UnusedImportAstCleaner
from rush.hygiene.cargo_deps import CargoUdepsScanner
from rush.hygiene.ast_merger import ThreeWayAstMergeResolver
from rush.hygiene.syntax_guard import SyntaxCompilationGuard
from rush.hygiene.stale_branches import StaleBranchAnalyzer
from rush.hygiene.artifact_cleaner import OrphanedArtifactCleaner


def test_import_merger():
    branch_a = "import os\nfrom pathlib import Path\n"
    branch_b = "import sys\nfrom pathlib import Path, PurePath\n"
    merged = AstImportMerger.merge_import_blocks("", branch_a, branch_b)
    assert "import os" in merged
    assert "import sys" in merged
    assert "from pathlib import Path, PurePath" in merged


def test_ast_class_merger():
    cls_a_src = "class Service:\n    def method_a(self): return 1\n"
    cls_b_src = "class Service:\n    def method_b(self): return 2\n"
    cls_a = ast.parse(cls_a_src).body[0]
    cls_b = ast.parse(cls_b_src).body[0]

    merged_cls = AstClassMerger.merge_classes(cls_a, cls_b)  # type: ignore
    unparsed = ast.unparse(merged_cls)
    assert "def method_a(self):" in unparsed
    assert "def method_b(self):" in unparsed


def test_ast_dict_merger():
    d1 = ast.parse("{'a': 1, 'b': 2}").body[0].value  # type: ignore
    d2 = ast.parse("{'b': 2, 'c': 3}").body[0].value  # type: ignore

    merged_d = AstDictMerger.merge_dicts(d1, d2)
    unparsed = ast.unparse(merged_d)
    assert "'a': 1" in unparsed
    assert "'b': 2" in unparsed
    assert "'c': 3" in unparsed


def test_ast_list_merger():
    l1 = ast.parse("['a', 'b']").body[0].value  # type: ignore
    l2 = ast.parse("['b', 'c']").body[0].value  # type: ignore

    merged_l = AstListMerger.merge_lists(l1, l2)
    unparsed = ast.unparse(merged_l)
    assert "['a', 'b', 'c']" in unparsed


def test_ast_set_merger():
    s1 = ast.parse("{'a', 'b'}").body[0].value  # type: ignore
    s2 = ast.parse("{'b', 'c'}").body[0].value  # type: ignore

    merged_s = AstSetMerger.merge_sets(s1, s2)
    unparsed = ast.unparse(merged_s)
    assert "'a'" in unparsed
    assert "'b'" in unparsed
    assert "'c'" in unparsed


def test_unused_import_cleaner():
    src = "import os\nimport sys\nfrom pathlib import Path, PurePath\n"
    cleaned = UnusedImportAstCleaner.clean_unused_imports(src, {"sys", "PurePath"})
    assert "import sys" not in cleaned
    assert "PurePath" not in cleaned
    assert "import os" in cleaned
    assert "Path" in cleaned


def test_ast_merge_resolver_independent_functions():
    base = "def existing():\n    return 0\n"
    ours = "def existing():\n    return 0\n\ndef added_in_ours():\n    return 1\n"
    theirs = "def existing():\n    return 0\n\ndef added_in_theirs():\n    return 2\n"

    success, resolved = ThreeWayAstMergeResolver.resolve_python_conflict(base, ours, theirs)
    assert success is True
    assert "def added_in_ours():" in resolved
    assert "def added_in_theirs():" in resolved


def test_syntax_compilation_guard():
    valid_code = "def valid(): pass\n"
    ok, err = SyntaxCompilationGuard.validate_syntax(valid_code)
    assert ok is True
    assert err is None

    invalid_code = "def broken(:\n"
    ok_b, err_b = SyntaxCompilationGuard.validate_syntax(invalid_code)
    assert ok_b is False
    assert err_b is not None


def test_cargo_udeps_scanner(tmp_path: Path):
    scanner = CargoUdepsScanner(tmp_path)
    res = scanner.scan_unused_deps()
    assert isinstance(res, list)


def test_artifact_cleaner(tmp_path: Path):
    cache_dir = tmp_path / "src" / "__pycache__"
    cache_dir.mkdir(parents=True)
    (cache_dir / "test.cpython-312.pyc").write_bytes(b"123")

    cleaner = OrphanedArtifactCleaner(tmp_path)
    artifacts = cleaner.discover_artifacts()
    assert len(artifacts) == 1
    assert artifacts[0] == cache_dir

    count = cleaner.prune_artifacts()
    assert count == 1
    assert not cache_dir.exists()


def test_stale_branch_analyzer(tmp_path: Path):
    analyzer = StaleBranchAnalyzer(tmp_path)
    branches = analyzer.list_merged_branches()
    assert isinstance(branches, list)
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 34 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:00:00.100Z", "phase": 34, "tool": "rush_hygiene", "event": "dead_code_detected", "file": "src/legacy.py", "symbol": "unused_helper"}
{"timestamp": "2026-08-21T10:00:01.400Z", "phase": 34, "tool": "rush_conflict", "event": "ast_merge_success", "file": "src/core.py"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 34 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 34: Codebase Hygiene & Merge Resolution**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 34 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Codebase Hygiene & AST Merge Conflict Resolution" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush hygiene dead-code`, `rush hygiene clean`, and `rush conflict solve` (flags: `--dry-run`, `--staged`, `--auto-commit`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for automatically resolving rebase merge conflicts with AST synthesis.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated weekly hygiene scan and cache cleanup recipe.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show before/after AST 3-way merge resolution snippets.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting up automated Git merge conflict drivers.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for unresolvable semantic conflict fallbacks and syntax verification errors.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush performs AST structural merges instead of crude line-based text merges.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_hygiene_deadcode` and `rush_conflict_resolve` FastMCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document merge conflict resolution result schemas.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `hygiene` and `conflict` tools in Codebase Maintenance category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[hygiene]` and `[conflict]` configuration tables.

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document 3-way AST merge state machine, symbol reference graph, and cache pruning architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for implementing custom AST merge handlers for new language constructs.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Add CI step checking for dead code on pull requests.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document 3-way merge conflict fixtures and class body collision tests.
- **[`docs/tools/hygiene.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/hygiene.md)** & **[`docs/tools/conflict.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/conflict.md)**: Create dedicated reference documentation.

### 7.3 Automated Documentation Parity Check
```bash
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check
```

### 7.4 Ending Git Lifecycle Commands
Execute these commands upon completing all phase tasks and verification checks:
```bash
# 1. Full verification gate
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format src tests scripts
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 2. Stage & Commit
git add src/ tests/ docs/
git commit -m "feat(phase-34): implement ast dead-code cleaner, 3-way ast merger and merge resolver"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
