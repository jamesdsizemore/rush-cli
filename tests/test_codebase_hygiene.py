"""Tests for Phase 34: Codebase Hygiene & AST Merge Resolution."""

from __future__ import annotations

import ast

from rush.hygiene.ast_merger import ASTConflictMerger
from rush.hygiene.class_merger import AstClassMerger
from rush.hygiene.dict_merger import AstDictMerger
from rush.hygiene.import_merger import AstImportMerger
from rush.hygiene.list_merger import AstListMerger
from rush.hygiene.unused_import_cleaner import UnusedImportCleaner


def test_ast_import_merger() -> None:
    branch_a = "import os\nfrom pathlib import Path"
    branch_b = "import sys\nfrom pathlib import Path, PurePath"

    merged = AstImportMerger.merge_import_blocks("", branch_a, branch_b)
    assert "import os" in merged
    assert "import sys" in merged
    assert "from pathlib import Path, PurePath" in merged


def test_ast_class_merger() -> None:
    class_a_code = """
class Worker:
    def process_a(self): pass
"""
    class_b_code = """
class Worker:
    def process_b(self): pass
"""
    tree_a = ast.parse(class_a_code)
    tree_b = ast.parse(class_b_code)

    merged = AstClassMerger.merge_classes(tree_a.body[0], tree_b.body[0])
    methods = [n.name for n in merged.body if isinstance(n, ast.FunctionDef)]
    assert "process_a" in methods
    assert "process_b" in methods


def test_ast_dict_merger() -> None:
    dict_a = ast.parse("{'a': 1, 'b': 2}").body[0].value
    dict_b = ast.parse("{'b': 2, 'c': 3}").body[0].value

    merged_dict = AstDictMerger.merge_dicts(dict_a, dict_b)
    keys = [k.value for k in merged_dict.keys]
    assert keys == ["a", "b", "c"]


def test_ast_list_merger() -> None:
    list_a = ast.parse("['x', 'y']").body[0].value
    list_b = ast.parse("['y', 'z']").body[0].value

    merged_list = AstListMerger.merge_lists(list_a, list_b)
    values = [e.value for e in merged_list.elts]
    assert values == ["x", "y", "z"]


def test_unused_import_cleaner() -> None:
    source = "import os\nimport sys\n\ndef main(): pass\n"
    cleaned = UnusedImportCleaner.clean_unused_imports(source, {"os"})
    assert "import os" not in cleaned
    assert "import sys" in cleaned


def test_ast_conflict_merger_full() -> None:
    branch_a = """
import os

class App:
    def start(self): pass
"""
    branch_b = """
import sys

class App:
    def stop(self): pass
"""
    ok, result = ASTConflictMerger.merge_source_files("", branch_a, branch_b)
    assert ok is True
    assert "import os" in result
    assert "import sys" in result
    assert "def start(self):" in result
    assert "def stop(self):" in result
