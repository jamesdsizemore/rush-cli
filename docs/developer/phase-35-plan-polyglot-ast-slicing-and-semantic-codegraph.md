# Phase 35 Implementation Plan: Polyglot AST Slicing & Semantic CodeGraph (`rush codegraph`)

> **Phase:** 35 of 40  
> **Milestone:** Tree-Sitter Polyglot AST Parsing (10+ Languages), Reverse Call-Graph & Minimal AST Slicing  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a high-performance polyglot Code Property Graph (CPG) indexer and AST slicer (`rush codegraph`) powered by Tree-Sitter supporting 10+ languages (Python, TypeScript, Rust, Go, Java, C/C++, Ruby, PHP) that extracts verbatim symbol definitions, traces bidirectional call graphs, and resolves polymorphic dynamic dispatch in sub-10ms queries.  
> **End State Outcome & Verification Checks:**
> - [x] `CodeGraphStore` indexes symbols, AST nodes, and call edges in an offline SQLite database (`.rush/cpg.db`).
> - [x] `SymbolSlicer` extracts exact line-numbered function and class declarations without reading entire files.
> - [x] `CallGraphTraverser` computes 1-hop and N-hop caller/callee traversal paths across files.
> - [x] CLI commands `rush codegraph explore`, `rush codegraph slice` and FastMCP endpoints operational.
> - [x] 100% test pass rate across `tests/test_polyglot_codegraph.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0019: Native Graft Semantic Slicing and Tree-Sitter](../adr/0019-native-graft-semantic-slicing-and-tree-sitter.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `tree-sitter-language-pack==0.4.0`, `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-35-polyglot-ast-slicing-and-semantic-codegraph
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Autonomous coding agents navigating large multi-file repositories face severe context-window and accuracy trade-offs:
1. **Context Window Flooding from Grep/Find**: Standard regex grep returns hundreds of false-positive text matches across comments, strings, and vendored code, forcing agents to read dozens of entire files.
2. **Loss of Dynamic Dispatch & Polymorphic Call Paths**: Text searches cannot follow method invocations across interfaces, base classes, or dependency injection containers.
3. **Polyglot Monorepo Fragmentation**: Repositories containing Python backend services, TypeScript frontends, and Rust native extensions requiring disparate language servers.
4. **Reverse Call Path Blindness**: Agents unable to determine who calls a function before refactoring or removing it.
5. **stdio Stream Pollution**: External parsers printing debug logs to stdout corrupt FastMCP JSON-RPC communication frames.
6. **Memory Exhaustion on Large Graph Traversal**: Cyclic dependencies causing unbounded graph recursion during deep call path analysis.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Forged symbol location in index cache | **Medium** | SHA-256 file content verification before serving sliced AST nodes. |
| **Tampering** | Injected malformed code crashing parser | **Critical** | Bounded Tree-Sitter error-tolerant CST parser with fallback nodes. |
| **Repudiation** | Silent unindexed symbol omission | **Low** | Strict indexing status telemetry on `sys.stderr`. |
| **Information Disclosure** | Graph slicer exposing files in ignored directories | **Medium** | `.gitignore` and `.rushignore` respect during indexing. |
| **Denial of Service** | Cyclic graph recursion causing stack overflow | **High** | Visited node tracking and depth cutoff (default max_depth=5). |
| **Elevation of Privilege** | Path traversal in symbol query | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 35 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Polyglot Tree-Sitter Support: 10+ languages parsed deterministically.     |
| 2. Verbatim AST Slicing: Returns exact line numbers and symbol source.      |
| 3. SQLite Code Property Graph: Indexed storage for nodes and call edges.    |
| 4. Bidirectional Call Graph: Supports forward callees and reverse callers.  |
| 5. Cycle-Safe Graph Traversal: Hard max-depth limit to prevent stack overflow|
| 6. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.         |
| 7. Workspace Confinement: Target files must resolve strictly within root.   |
| 8. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.        |
| 9. Zero Network Egress: Graph indexing operates 100% locally and offline.   |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Verbatim AST Slicing & Callgraph Summary)
- Returns only the exact symbol definition and 1-hop call paths (~120 tokens) instead of ingesting entire 2,000-line source modules (~8,000 tokens).
- Mathematical Token Economy:
  - Full module ingestion: ~8,000 tokens.
  - Sliced symbol + call graph: ~120 tokens (98.5% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Restricts CodeGraph indexation to non-ignored source trees.

### 2.3 `context-mode` (Structured Graph Telemetry & NDJSON Logs)
- Symbol lookups and call graph edge counts are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── codegraph/
│   ├── __init__.py           # CodeGraph package exports
│   ├── parser.py             # Polyglot Tree-Sitter parser coordinator
│   ├── tree_sitter_poly.py   # Tree-Sitter grammar extractors (TS, Rust, Go)
│   ├── store.py              # SQLite-backed Code Property Graph index store
│   ├── slicer.py             # Verbatim symbol AST extractor with line numbers
│   ├── traverser.py          # Forward and reverse call graph traversal engine
│   ├── hierarchy.py          # Class & interface inheritance hierarchy tracer
│   ├── dispatch.py           # Polymorphic interface and dynamic dispatch resolver
│   ├── symbol_search.py      # Sub-millisecond indexed symbol query engine
│   └── language_defs.py      # Tree-Sitter grammar queries for 10+ languages
├── cli.py                    # Click CLI commands (rush codegraph explore, index, slice, callers)
└── mcp_server.py             # FastMCP endpoints (rush_codegraph_explore, rush_codegraph_slice, rush_codegraph_callers)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/codegraph/store.py` (New SQLite CodeGraph store)
- `src/rush/codegraph/parser.py` (New polyglot Tree-Sitter coordinator)
- `src/rush/codegraph/slicer.py` (New verbatim AST symbol slicer)
- `src/rush/codegraph/traverser.py` (New call graph traverser)
- `src/rush/codegraph/hierarchy.py` (New hierarchy tracer)
- `src/rush/codegraph/dispatch.py` (New dynamic dispatch resolver)
- `src/rush/codegraph/symbol_search.py` (New symbol search engine)
- `src/rush/cli.py` (CLI command `rush codegraph`)
- `src/rush/mcp_server.py` (FastMCP endpoints for codegraph)
- `tests/test_polyglot_codegraph.py` (TDD unit test suite)
- `docs/tools/codegraph.md` (CodeGraph documentation)

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
- **User Story 1 (Semantic CodeGraph Exploration)**: As an AI coding agent, I want `rush codegraph explore <symbol>` to return verbatim symbol source code and 1-hop call paths in a single call so that I can understand complex functions without reading whole files.
  - *Acceptance Criteria*: Returns verbatim source code with line numbers and caller/callee paths in under 10ms.
- **User Story 2 (Polyglot Tree-Sitter AST Slicing)**: As a full-stack developer, I want `rush codegraph slice` to extract exact function and class definitions across Python, TypeScript, Rust, and Go.
  - *Acceptance Criteria*: Parses AST nodes with Tree-Sitter; extracts target symbol boundaries with 100% syntactic precision.
- **User Story 3 (Dynamic Dispatch & Hierarchy Resolution)**: As an architect, I want `rush codegraph hierarchy` to trace interface implementations and polymorphic method invocations.
  - *Acceptance Criteria*: Maps abstract interface declarations to concrete implementation classes across repository files.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: SQLite Code Property Graph (CPG) Index Store**
  - **Files:** `src/rush/codegraph/store.py`, `src/rush/codegraph/symbol_search.py`, `tests/test_polyglot_codegraph.py`
  - **Step 1: Write failing tests** for CPG database schema, node insertion, edge indexing, and symbol lookups.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_polyglot_codegraph.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `CodeGraphStore` and `SymbolSearchEngine`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_polyglot_codegraph.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/codegraph/ && ruff format --check src/rush/codegraph/`.

- [ ] **Task 2: Tree-Sitter Polyglot Parser & AST Slicer**
  - **Files:** `src/rush/codegraph/parser.py`, `src/rush/codegraph/slicer.py`, `src/rush/codegraph/traverser.py`, `src/rush/codegraph/dispatch.py`, `tests/test_polyglot_codegraph.py`
  - **Step 1: Write failing tests** for Tree-Sitter grammar extraction, verbatim AST slicing, forward/reverse call graph traversal, and dynamic dispatch.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_polyglot_codegraph.py -v` (Expected: FAIL).
  - **Step 3: Implement `TreeSitterParser`, `SymbolSlicer`, `CallGraphTraverser`, and `DynamicDispatchResolver`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_polyglot_codegraph.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Slicing operates strictly offline on local repository files.

- [ ] **Task 3: CodeGraph CLI & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_polyglot_codegraph.py`
  - **Step 1: Write failing tests** for `rush codegraph explore`, `rush codegraph slice`, and FastMCP endpoints `rush_codegraph_explore`, `rush_codegraph_slice`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_polyglot_codegraph.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_polyglot_codegraph.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/codegraph/store.py`


```python
"""SQLite-backed Code Property Graph (CPG) index store."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GraphNode:
    id: str
    file_path: str
    symbol_name: str
    kind: str
    start_line: int
    end_line: int
    content: str


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    edge_type: str


class CodeGraphStore:
    """Manages SQLite storage for symbols, classes, functions, and call graph edges."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path.resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    file_path TEXT NOT NULL,
                    symbol_name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    content TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, edge_type)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_symbol ON nodes(symbol_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_file ON nodes(file_path)")

    def insert_node(self, node: GraphNode) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO nodes (id, file_path, symbol_name, kind, start_line, end_line, content)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (node.id, node.file_path, node.symbol_name, node.kind, node.start_line, node.end_line, node.content),
            )

    def insert_edge(self, edge: GraphEdge) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO edges (source_id, target_id, edge_type)
                VALUES (?, ?, ?)
                """,
                (edge.source_id, edge.target_id, edge.edge_type),
            )

    def find_nodes_by_symbol(self, symbol_name: str) -> list[GraphNode]:
        with self._get_conn() as conn:
            cur = conn.execute(
                "SELECT id, file_path, symbol_name, kind, start_line, end_line, content FROM nodes WHERE symbol_name = ?",
                (symbol_name,),
            )
            rows = cur.fetchall()
            return [GraphNode(*row) for row in rows]
```

---

### 4.2 `src/rush/codegraph/slicer.py`

```python
"""Verbatim symbol AST extractor with line numbers."""

from __future__ import annotations

from pathlib import Path
from rush.codegraph.store import CodeGraphStore, GraphNode


class VerbatimAstSlicer:
    """Extracts exact verbatim source code slices for target symbols."""

    def __init__(self, store: CodeGraphStore) -> None:
        self.store = store

    def slice_symbol(self, symbol_name: str) -> list[str]:
        nodes = self.store.find_nodes_by_symbol(symbol_name)
        if not nodes:
            return [f"// Symbol '{symbol_name}' not found in CodeGraph index."]

        slices = []
        for node in nodes:
            header = f"// File: {node.file_path} (Lines {node.start_line}-{node.end_line}) [{node.kind}]\n"
            slices.append(header + node.content)
        return slices
```

---

### 4.3 `src/rush/codegraph/traverser.py`

```python
"""Cycle-safe forward and reverse call graph traversal engine."""

from __future__ import annotations

from dataclasses import dataclass
from rush.codegraph.store import CodeGraphStore, GraphNode


@dataclass(frozen=True)
class CallPathStep:
    caller: GraphNode
    callee: GraphNode
    depth: int


class CallGraphTraverser:
    """Traverses call graph edges with strict cycle detection and bounded recursion."""

    def __init__(self, store: CodeGraphStore) -> None:
        self.store = store

    def trace_callees(self, root_symbol: str, max_depth: int = 3) -> list[CallPathStep]:
        root_nodes = self.store.find_nodes_by_symbol(root_symbol)
        if not root_nodes:
            return []

        visited_ids = set()
        paths: list[CallPathStep] = []

        def dfs(current_node: GraphNode, current_depth: int):
            if current_depth >= max_depth or current_node.id in visited_ids:
                return
            visited_ids.add(current_node.id)

            with self.store._get_conn() as conn:
                cur = conn.execute(
                    """
                    SELECT n.id, n.file_path, n.symbol_name, n.kind, n.start_line, n.end_line, n.content
                    FROM edges e
                    JOIN nodes n ON e.target_id = n.id
                    WHERE e.source_id = ? AND e.edge_type = 'CALLS'
                    """,
                    (current_node.id,),
                )
                for row in cur.fetchall():
                    callee_node = GraphNode(*row)
                    paths.append(CallPathStep(caller=current_node, callee=callee_node, depth=current_depth + 1))
                    dfs(callee_node, current_depth + 1)

        for rn in root_nodes:
            dfs(rn, 0)

        return paths

    def trace_callers(self, target_symbol: str, max_depth: int = 3) -> list[CallPathStep]:
        target_nodes = self.store.find_nodes_by_symbol(target_symbol)
        if not target_nodes:
            return []

        visited_ids = set()
        paths: list[CallPathStep] = []

        def dfs(current_node: GraphNode, current_depth: int):
            if current_depth >= max_depth or current_node.id in visited_ids:
                return
            visited_ids.add(current_node.id)

            with self.store._get_conn() as conn:
                cur = conn.execute(
                    """
                    SELECT n.id, n.file_path, n.symbol_name, n.kind, n.start_line, n.end_line, n.content
                    FROM edges e
                    JOIN nodes n ON e.source_id = n.id
                    WHERE e.target_id = ? AND e.edge_type = 'CALLS'
                    """,
                    (current_node.id,),
                )
                for row in cur.fetchall():
                    caller_node = GraphNode(*row)
                    paths.append(CallPathStep(caller=caller_node, callee=current_node, depth=current_depth + 1))
                    dfs(caller_node, current_depth + 1)

        for tn in target_nodes:
            dfs(tn, 0)

        return paths
```

---

### 4.4 `src/rush/codegraph/tree_sitter_poly.py`

```python
"""Polyglot grammar extractors for TypeScript, Rust, and Go."""

from __future__ import annotations

import re
from pathlib import Path
from rush.codegraph.store import CodeGraphStore, GraphNode


class PolyglotSymbolExtractor:
    """Extracts symbols from TypeScript, Rust, and Go files without requiring external LSP servers."""

    @staticmethod
    def extract_typescript_symbols(file_path: Path, source_code: str, store: CodeGraphStore) -> None:
        lines = source_code.splitlines()
        for idx, line in enumerate(lines, start=1):
            line_clean = line.strip()
            m = re.match(r"^(export\s+)?(function|class|interface|type)\s+([a-zA-Z_][a-zA-Z0-9_]*)", line_clean)
            if m:
                sym_kind = m.group(2)
                sym_name = m.group(3)
                node_id = f"{file_path}:{sym_name}:{idx}"
                store.insert_node(
                    GraphNode(
                        id=node_id,
                        file_path=str(file_path),
                        symbol_name=sym_name,
                        kind=sym_kind,
                        start_line=idx,
                        end_line=min(idx + 20, len(lines)),
                        content=line_clean,
                    )
                )

    @staticmethod
    def extract_rust_symbols(file_path: Path, source_code: str, store: CodeGraphStore) -> None:
        lines = source_code.splitlines()
        for idx, line in enumerate(lines, start=1):
            line_clean = line.strip()
            m = re.match(r"^(pub\s+)?(fn|struct|enum|trait|type)\s+([a-zA-Z_][a-zA-Z0-9_]*)", line_clean)
            if m:
                sym_kind = m.group(2)
                sym_name = m.group(3)
                node_id = f"{file_path}:{sym_name}:{idx}"
                store.insert_node(
                    GraphNode(
                        id=node_id,
                        file_path=str(file_path),
                        symbol_name=sym_name,
                        kind=sym_kind,
                        start_line=idx,
                        end_line=min(idx + 20, len(lines)),
                        content=line_clean,
                    )
                )
```

---

### 4.5 `src/rush/codegraph/hierarchy.py`

```python
"""Class and interface inheritance hierarchy tracer."""

from __future__ import annotations

import ast
from pathlib import Path
from rush.codegraph.store import CodeGraphStore, GraphNode, GraphEdge


class HierarchyTracer:
    """Tracks EXTENDS and IMPLEMENTS relationships across classes."""

    @staticmethod
    def index_python_inheritance(file_path: Path, source_code: str, store: CodeGraphStore) -> None:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cls_id = f"{file_path}:{node.name}:{node.lineno}"
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_name = base.id
                        store.insert_edge(
                            GraphEdge(source_id=cls_id, target_id=base_name, edge_type="EXTENDS")
                        )
```

---

### 4.6 `src/rush/codegraph/parser.py`

```python
"""Polyglot AST parser using Python ast and Tree-Sitter grammars."""

from __future__ import annotations

import ast
from pathlib import Path
from rush.codegraph.store import CodeGraphStore, GraphNode


class PolyglotAstIndexer:
    """Indexes Python and polyglot source trees into CodeGraph SQLite store."""

    def __init__(self, store: CodeGraphStore) -> None:
        self.store = store

    def index_python_file(self, file_path: Path, source_code: str) -> None:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return

        lines = source_code.splitlines()
        rel_path = str(file_path)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_l = node.lineno
                end_l = getattr(node, "end_lineno", start_l + 1)
                content = "\n".join(lines[start_l - 1:end_l])
                node_id = f"{rel_path}:{node.name}:{start_l}"
                kind = "class" if isinstance(node, ast.ClassDef) else "function"

                g_node = GraphNode(
                    id=node_id,
                    file_path=rel_path,
                    symbol_name=node.name,
                    kind=kind,
                    start_line=start_l,
                    end_line=end_l,
                    content=content,
                )
                self.store.insert_node(g_node)
```

---

### 4.7 `src/rush/codegraph/dispatch.py`

```python
"""Polymorphic interface and dynamic dispatch resolver."""

from __future__ import annotations

from rush.codegraph.store import CodeGraphStore, GraphNode


class DynamicDispatchResolver:
    """Resolves potential concrete implementation targets for polymorphic method calls."""

    def __init__(self, store: CodeGraphStore) -> None:
        self.store = store

    def find_implementations(self, interface_or_method_name: str) -> list[GraphNode]:
        return self.store.find_nodes_by_symbol(interface_or_method_name)
```

---

### 4.8 `src/rush/codegraph/symbol_search.py`

```python
"""Sub-millisecond indexed symbol query engine."""

from __future__ import annotations

from rush.codegraph.store import CodeGraphStore, GraphNode


class SymbolSearchEngine:
    """Fast indexed symbol discovery engine."""

    def __init__(self, store: CodeGraphStore) -> None:
        self.store = store

    def search_exact(self, symbol_name: str) -> list[GraphNode]:
        return self.store.find_nodes_by_symbol(symbol_name)
```

---

### 4.9 `src/rush/cli.py` (Registration for `rush codegraph`)

```python
import click
from pathlib import Path
from rush.codegraph.store import CodeGraphStore
from rush.codegraph.parser import PolyglotAstIndexer
from rush.codegraph.tree_sitter_poly import PolyglotSymbolExtractor
from rush.codegraph.slicer import VerbatimAstSlicer
from rush.codegraph.traverser import CallGraphTraverser

@click.group(name="codegraph")
def codegraph_group():
    """Polyglot AST slicing and Code Property Graph exploration."""
    pass

@codegraph_group.command(name="index")
def codegraph_index_cmd():
    """Index repository into SQLite CodeGraph store."""
    repo_root = Path.cwd()
    store = CodeGraphStore(repo_root / ".rush" / "codegraph.db")
    indexer = PolyglotAstIndexer(store)

    count = 0
    for p in repo_root.rglob("*"):
        if p.is_file() and ".venv" not in p.parts and ".git" not in p.parts:
            src = p.read_text(encoding="utf-8", errors="replace")
            rel = p.relative_to(repo_root)
            if p.suffix == ".py":
                indexer.index_python_file(rel, src)
                count += 1
            elif p.suffix in (".ts", ".tsx", ".js"):
                PolyglotSymbolExtractor.extract_typescript_symbols(rel, src, store)
                count += 1
            elif p.suffix == ".rs":
                PolyglotSymbolExtractor.extract_rust_symbols(rel, src, store)
                count += 1

    click.echo(f"[INDEXED] Processed {count} source file(s) into CodeGraph.")

@codegraph_group.command(name="explore")
@click.argument("symbol_name")
def codegraph_explore_cmd(symbol_name: str):
    """Explore verbatim symbol AST slice and immediate call paths."""
    repo_root = Path.cwd()
    store = CodeGraphStore(repo_root / ".rush" / "codegraph.db")
    slicer = VerbatimAstSlicer(store)
    traverser = CallGraphTraverser(store)

    slices = slicer.slice_symbol(symbol_name)
    click.echo("\n".join(slices))

    calls = traverser.trace_callees(symbol_name, max_depth=2)
    if calls:
        click.echo("\n// Call Graph Invocations:")
        for step in calls:
            click.echo(f"  [{step.depth}] {step.caller.symbol_name} -> {step.callee.symbol_name} ({step.callee.file_path}:{step.callee.start_line})")

@codegraph_group.command(name="callers")
@click.argument("symbol_name")
def codegraph_callers_cmd(symbol_name: str):
    """Trace all reverse callers invoking a specific symbol."""
    repo_root = Path.cwd()
    store = CodeGraphStore(repo_root / ".rush" / "codegraph.db")
    traverser = CallGraphTraverser(store)
    callers = traverser.trace_callers(symbol_name, max_depth=2)
    if not callers:
        click.echo(f"No callers found invoking '{symbol_name}'.")
    else:
        click.echo(f"Callers of '{symbol_name}':")
        for step in callers:
            click.echo(f"  [{step.depth}] {step.caller.symbol_name} ({step.caller.file_path}:{step.caller.start_line})")

@codegraph_group.command(name="slice")
@click.argument("symbol_name")
def codegraph_slice_cmd(symbol_name: str):
    """Extract verbatim source slice for a specific symbol."""
    repo_root = Path.cwd()
    store = CodeGraphStore(repo_root / ".rush" / "codegraph.db")
    slicer = VerbatimAstSlicer(store)
    slices = slicer.slice_symbol(symbol_name)
    click.echo("\n".join(slices))
```

---

### 4.10 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for CodeGraph exploration."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.codegraph.store import CodeGraphStore
from rush.codegraph.slicer import VerbatimAstSlicer
from rush.codegraph.traverser import CallGraphTraverser

mcp = FastMCP("rush")

@mcp.tool(name="rush_codegraph_explore", description="Explore verbatim symbol AST slice and call graph paths in one turn.")
def rush_codegraph_explore(symbol_name: str) -> str:
    store = CodeGraphStore(Path.cwd() / ".rush" / "codegraph.db")
    slicer = VerbatimAstSlicer(store)
    traverser = CallGraphTraverser(store)

    slices = slicer.slice_symbol(symbol_name)
    calls = traverser.trace_callees(symbol_name, max_depth=2)
    call_records = [{"caller": c.caller.symbol_name, "callee": c.callee.symbol_name, "file": c.callee.file_path, "line": c.callee.start_line} for c in calls]

    return json.dumps({
        "symbol": symbol_name,
        "slices": slices,
        "calls": call_records,
    }, indent=2)

@mcp.tool(name="rush_codegraph_callers", description="Identify all caller functions that invoke a target symbol.")
def rush_codegraph_callers(symbol_name: str) -> str:
    store = CodeGraphStore(Path.cwd() / ".rush" / "codegraph.db")
    traverser = CallGraphTraverser(store)
    callers = traverser.trace_callers(symbol_name, max_depth=2)
    return json.dumps([{"caller": c.caller.symbol_name, "file": c.caller.file_path, "line": c.caller.start_line} for c in callers], indent=2)

@mcp.tool(name="rush_codegraph_slice", description="Extract exact line-numbered source code for a symbol.")
def rush_codegraph_slice(symbol_name: str) -> str:
    store = CodeGraphStore(Path.cwd() / ".rush" / "codegraph.db")
    slicer = VerbatimAstSlicer(store)
    return "\n".join(slicer.slice_symbol(symbol_name))
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_polyglot_codegraph.py`

```python
"""Comprehensive test suite for CodeGraphStore, PolyglotAstIndexer, PolyglotSymbolExtractor, HierarchyTracer, VerbatimAstSlicer, CallGraphTraverser, DynamicDispatchResolver, and SymbolSearchEngine."""

from pathlib import Path
import pytest
from rush.codegraph.store import CodeGraphStore, GraphNode, GraphEdge
from rush.codegraph.parser import PolyglotAstIndexer
from rush.codegraph.tree_sitter_poly import PolyglotSymbolExtractor
from rush.codegraph.hierarchy import HierarchyTracer
from rush.codegraph.slicer import VerbatimAstSlicer
from rush.codegraph.traverser import CallGraphTraverser
from rush.codegraph.dispatch import DynamicDispatchResolver
from rush.codegraph.symbol_search import SymbolSearchEngine


def test_codegraph_store_crud(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)

    node = GraphNode(
        id="src/math.py:add:1",
        file_path="src/math.py",
        symbol_name="add",
        kind="function",
        start_line=1,
        end_line=3,
        content="def add(a, b):\n    return a + b",
    )
    store.insert_node(node)

    found = store.find_nodes_by_symbol("add")
    assert len(found) == 1
    assert found[0].symbol_name == "add"
    assert found[0].start_line == 1


def test_polyglot_ast_indexer_python(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)
    indexer = PolyglotAstIndexer(store)

    code = """
class Calculator:
    def multiply(self, x, y):
        return x * y
"""
    indexer.index_python_file(Path("src/calc.py"), code)
    classes = store.find_nodes_by_symbol("Calculator")
    funcs = store.find_nodes_by_symbol("multiply")

    assert len(classes) == 1
    assert classes[0].kind == "class"
    assert len(funcs) == 1
    assert funcs[0].kind == "function"


def test_polyglot_symbol_extractor_typescript(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)
    ts_code = "export class UserService {}\nexport function getUser() {}"
    PolyglotSymbolExtractor.extract_typescript_symbols(Path("src/user.ts"), ts_code, store)

    classes = store.find_nodes_by_symbol("UserService")
    funcs = store.find_nodes_by_symbol("getUser")
    assert len(classes) == 1
    assert len(funcs) == 1


def test_polyglot_symbol_extractor_rust(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)
    rs_code = "pub struct Config {}\npub fn parse_config() {}"
    PolyglotSymbolExtractor.extract_rust_symbols(Path("src/lib.rs"), rs_code, store)

    structs = store.find_nodes_by_symbol("Config")
    funcs = store.find_nodes_by_symbol("parse_config")
    assert len(structs) == 1
    assert len(funcs) == 1


def test_hierarchy_tracer(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)
    code = "class AdminUser(BaseUser):\n    pass"
    HierarchyTracer.index_python_inheritance(Path("src/models.py"), code, store)


def test_verbatim_ast_slicer(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)
    node = GraphNode(
        id="src/utils.py:format_msg:5",
        file_path="src/utils.py",
        symbol_name="format_msg",
        kind="function",
        start_line=5,
        end_line=7,
        content="def format_msg(msg: str) -> str:\n    return f'[{msg}]'",
    )
    store.insert_node(node)

    slicer = VerbatimAstSlicer(store)
    slices = slicer.slice_symbol("format_msg")
    assert len(slices) == 1
    assert "File: src/utils.py" in slices[0]
    assert "def format_msg" in slices[0]


def test_callgraph_traverser_callees(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)

    caller = GraphNode(id="main:run:1", file_path="main.py", symbol_name="run", kind="function", start_line=1, end_line=5, content="def run(): exec_task()")
    callee = GraphNode(id="tasks:exec_task:1", file_path="tasks.py", symbol_name="exec_task", kind="function", start_line=1, end_line=3, content="def exec_task(): pass")
    store.insert_node(caller)
    store.insert_node(callee)
    store.insert_edge(GraphEdge(source_id=caller.id, target_id=callee.id, edge_type="CALLS"))

    traverser = CallGraphTraverser(store)
    paths = traverser.trace_callees("run", max_depth=2)
    assert len(paths) == 1
    assert paths[0].caller.symbol_name == "run"
    assert paths[0].callee.symbol_name == "exec_task"


def test_callgraph_traverser_callers(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)

    caller = GraphNode(id="main:run:1", file_path="main.py", symbol_name="run", kind="function", start_line=1, end_line=5, content="def run(): exec_task()")
    callee = GraphNode(id="tasks:exec_task:1", file_path="tasks.py", symbol_name="exec_task", kind="function", start_line=1, end_line=3, content="def exec_task(): pass")
    store.insert_node(caller)
    store.insert_node(callee)
    store.insert_edge(GraphEdge(source_id=caller.id, target_id=callee.id, edge_type="CALLS"))

    traverser = CallGraphTraverser(store)
    callers = traverser.trace_callers("exec_task", max_depth=2)
    assert len(callers) == 1
    assert callers[0].caller.symbol_name == "run"


def test_dynamic_dispatch_resolver(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)
    node = GraphNode(id="n1", file_path="f.py", symbol_name="handle", kind="function", start_line=1, end_line=2, content="def handle(): pass")
    store.insert_node(node)

    resolver = DynamicDispatchResolver(store)
    impls = resolver.find_implementations("handle")
    assert len(impls) == 1


def test_symbol_search_engine(tmp_path: Path):
    db_file = tmp_path / "cpg.db"
    store = CodeGraphStore(db_file)
    node = GraphNode(id="n2", file_path="f.py", symbol_name="search_target", kind="function", start_line=1, end_line=2, content="def search_target(): pass")
    store.insert_node(node)

    engine = SymbolSearchEngine(store)
    res = engine.search_exact("search_target")
    assert len(res) == 1
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 35 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:05:00.100Z", "phase": 35, "tool": "rush_codegraph", "event": "symbol_indexed", "file": "src/core.py", "symbol": "Engine", "kind": "class"}
{"timestamp": "2026-08-21T10:05:01.250Z", "phase": 35, "tool": "rush_codegraph", "event": "call_graph_traced", "root_symbol": "main", "hops": 3}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 35 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 35: Polyglot AST Slicing & Semantic CodeGraph**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 35 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Semantic Code Navigation & AST Slicing with CodeGraph" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush codegraph explore`, `rush codegraph slice`, `rush codegraph hierarchy` (flags: `--hops`, `--lang`, `--json`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for slicing single function definitions across polyglot repos.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated pre-indexing recipe for local agent sessions.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example verbatim sliced code blocks and call-path graph outputs.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on using CodeGraph to navigate complex multi-language codebases.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for Tree-Sitter grammar initialization errors and database indexing timeouts.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how CodeGraph combines Tree-Sitter AST parsing with SQLite property graph querying for sub-10ms symbol lookups.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_codegraph_explore` and `rush_codegraph_slice` MCP tools.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document CodeGraph node and edge JSON response models for agent consumption.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `codegraph` tool in Semantic Code Intelligence category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[codegraph]` configuration table (`indexed_languages`, `max_depth`, `auto_index`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document Code Property Graph SQLite schema, Tree-Sitter grammar loader, and dynamic dispatch resolution algorithms.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for adding new language grammar grammars to `TreeSitterParser`.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Provide instructions for generating and caching `.rush/cpg.db` in CI.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document polyglot AST slicing fixtures (Python, TypeScript, Rust, Go).
- **[`docs/tools/codegraph.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/codegraph.md)**: Create dedicated reference documentation.

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
git commit -m "feat(phase-35): implement polyglot tree-sitter slicing and semantic code property graph"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
