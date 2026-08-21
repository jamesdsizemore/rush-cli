"""Tests for Phase 35: Polyglot AST Slicing & Semantic CodeGraph."""

from __future__ import annotations

from pathlib import Path

from rush.codegraph.python_ast import PythonCodeGraphBuilder
from rush.codegraph.slicer import VerbatimAstSlicer
from rush.codegraph.store import CodeGraphStore, GraphEdge, GraphNode
from rush.codegraph.traverser import CallGraphTraverser
from rush.codegraph.tree_sitter_poly import PolyglotSymbolExtractor


def test_codegraph_store(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = CodeGraphStore(db)

    node = GraphNode(
        id="file.py:my_fn:1",
        file_path="file.py",
        symbol_name="my_fn",
        kind="function",
        start_line=1,
        end_line=5,
        content="def my_fn(): pass",
    )
    store.insert_node(node)

    found = store.find_nodes_by_symbol("my_fn")
    assert len(found) == 1
    assert found[0].symbol_name == "my_fn"


def test_python_ast_indexer(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = CodeGraphStore(db)

    py_source = """
class MyService:
    def handle_request(self):
        return 42
"""
    PythonCodeGraphBuilder.index_python_file(Path("service.py"), py_source, store)
    classes = store.find_nodes_by_symbol("MyService")
    functions = store.find_nodes_by_symbol("handle_request")
    assert len(classes) == 1
    assert len(functions) == 1


def test_verbatim_ast_slicer(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = CodeGraphStore(db)

    node = GraphNode(
        id="app.py:start_server:10",
        file_path="app.py",
        symbol_name="start_server",
        kind="function",
        start_line=10,
        end_line=15,
        content="def start_server():\n    print('server running')",
    )
    store.insert_node(node)

    slicer = VerbatimAstSlicer(store)
    slices = slicer.slice_symbol("start_server")
    assert len(slices) == 1
    assert "Lines 10-15" in slices[0]
    assert "def start_server():" in slices[0]


def test_call_graph_traversal(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = CodeGraphStore(db)

    caller = GraphNode("a.py:caller_fn:1", "a.py", "caller_fn", "function", 1, 3, "def caller_fn(): callee_fn()")
    callee = GraphNode("b.py:callee_fn:1", "b.py", "callee_fn", "function", 1, 3, "def callee_fn(): pass")
    store.insert_node(caller)
    store.insert_node(callee)
    store.insert_edge(GraphEdge("a.py:caller_fn:1", "b.py:callee_fn:1", "CALLS"))

    traverser = CallGraphTraverser(store)
    callees = traverser.trace_callees("caller_fn")
    assert len(callees) == 1
    assert callees[0].callee.symbol_name == "callee_fn"

    callers = traverser.trace_callers("callee_fn")
    assert len(callers) == 1
    assert callers[0].caller.symbol_name == "caller_fn"


def test_polyglot_symbol_extractor(tmp_path: Path) -> None:
    db = tmp_path / "test.db"
    store = CodeGraphStore(db)

    ts_source = "export function calculateTotal(items: number[]): number {\n  return 0;\n}"
    PolyglotSymbolExtractor.extract_typescript_symbols(Path("calc.ts"), ts_source, store)
    ts_nodes = store.find_nodes_by_symbol("calculateTotal")
    assert len(ts_nodes) == 1
    assert ts_nodes[0].kind == "function"

    rs_source = "pub fn execute_command(cmd: &str) -> bool {\n    true\n}"
    PolyglotSymbolExtractor.extract_rust_symbols(Path("exec.rs"), rs_source, store)
    rs_nodes = store.find_nodes_by_symbol("execute_command")
    assert len(rs_nodes) == 1
    assert rs_nodes[0].kind == "fn"
