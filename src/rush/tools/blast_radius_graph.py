"""Reverse import graph construction and reachability traversal for blast radius analysis."""

from __future__ import annotations

import ast
from pathlib import Path


def _extract_imported_modules(py_file: Path) -> set[str]:
    """Parse a python file and return all imported module identifiers."""
    modules: set[str] = set()
    try:
        code = py_file.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
    except Exception:  # noqa: BLE001, S110
        pass
    return modules


def build_reverse_import_graph(
    root: Path, target_stems: set[str] | None = None
) -> dict[str, set[str]]:
    """Build reverse import graph mapping imported modules to dependent relative paths."""
    graph: dict[str, set[str]] = {}
    for py_file in root.glob("**/*.py"):
        path_str = str(py_file)
        if any(ign in path_str for ign in (".venv", ".git", ".rush")):
            continue
        rel_path = str(py_file.relative_to(root))
        for mod in _extract_imported_modules(py_file):
            if target_stems is not None and not any(tm in mod for tm in target_stems):
                continue
            graph.setdefault(mod, set()).add(rel_path)
    return graph


def walk_impacted_paths(
    graph: dict[str, set[str]],
    seeds: set[str] | list[str],
    max_depth: int = 5,
) -> set[str]:
    """Walk reverse import graph from seed module names up to max_depth, returning all impacted paths."""
    impacted: set[str] = set()
    current_seeds = {
        Path(s).stem if isinstance(s, (str, Path)) else str(s) for s in seeds
    }
    visited_seeds: set[str] = set()

    depth = 0
    while current_seeds and depth < max_depth:
        next_seeds: set[str] = set()
        for seed in current_seeds:
            if seed in visited_seeds:
                continue
            visited_seeds.add(seed)
            for mod, dependents in graph.items():
                if seed in mod:
                    for dep in dependents:
                        if dep not in impacted:
                            impacted.add(dep)
                            next_seeds.add(Path(dep).stem)
        current_seeds = next_seeds
        depth += 1

    return impacted
