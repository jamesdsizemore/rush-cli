"""Codebase hygiene, dead code detection, and 3-way AST merge resolution."""

from __future__ import annotations

from rush.hygiene.ast_merger import ASTConflictMerger
from rush.hygiene.class_merger import AstClassMerger
from rush.hygiene.dead_code import DeadCodeFinding, PolyglotDeadCodeDetector
from rush.hygiene.dict_merger import AstDictMerger
from rush.hygiene.import_merger import AstImportMerger
from rush.hygiene.list_merger import AstListMerger
from rush.hygiene.set_merger import AstSetMerger
from rush.hygiene.unused_import_cleaner import UnusedImportCleaner

__all__ = [
    "ASTConflictMerger",
    "AstClassMerger",
    "AstDictMerger",
    "AstImportMerger",
    "AstListMerger",
    "AstSetMerger",
    "DeadCodeFinding",
    "PolyglotDeadCodeDetector",
    "UnusedImportCleaner",
]
