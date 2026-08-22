"""Verbatim symbol AST extractor with line numbers."""

from __future__ import annotations

from rush.codegraph.store import CodeGraphStore


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


# Graft Semantic Slicing Engine alias (ADR-0019)
GraftSemanticSlicer = VerbatimAstSlicer
