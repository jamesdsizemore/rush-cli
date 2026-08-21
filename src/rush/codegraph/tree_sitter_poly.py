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
