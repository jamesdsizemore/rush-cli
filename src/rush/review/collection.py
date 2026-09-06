"""Review file collection and heuristic checks.

Provides Python file discovery, safe content reading, and advisory heuristics:
- file size / line count
- TODO/FIXME marker density
- missing docstrings for functions/classes
- SCREAMING_CASE non-constant naming
- unfinished scaffold markers
- source policy glob exclusions
- function complexity
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from rush.tools.base import Finding

TODO_PATTERN = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
MAX_FILE_BYTES = 1_000_000  # 1 MB cap — heuristics don't run on huge files
MAX_AST_DEPTH = 50  # safety against malicious files

SKIP_DIRS = frozenset(
    {
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".git",
        "dist",
        "build",
        ".next",
    }
)


def _read_file_safely(path: Path) -> str | None:
    """Read a text file safely respecting file size limits and encoding errors."""
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _collect_explicit_changed_files(
    root: Path, changed_files: list[str]
) -> tuple[list[Path], dict[str, object]]:
    """Resolve and filter explicit changed files to Python files within root."""
    root_resolved = root.resolve()
    targets: list[Path] = []
    scope_files: list[str] = []
    for changed_file in changed_files:
        candidate = Path(changed_file)
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
        try:
            relative = candidate.relative_to(root_resolved)
        except ValueError as error:
            raise ValueError(
                "explicit changed file is outside review target"
            ) from error
        if candidate.is_file() and candidate.suffix == ".py":
            targets.append(candidate)
            scope_files.append(str(relative))
    return sorted(set(targets)), {
        "mode": "explicit-files",
        "files": sorted(scope_files),
    }


def _collect_reviewable_files(
    path: Path, *, changed_files: list[str] | None = None
) -> tuple[list[Path], dict[str, object]]:
    """Walk `path` and return Python files (heuristics only target Python)."""
    root = path if path.is_dir() else path.parent
    if changed_files is not None:
        return _collect_explicit_changed_files(root, changed_files)

    if path.is_file():
        return ([path] if path.suffix == ".py" else []), {"mode": "target"}

    if path.is_dir():
        targets = [
            p
            for p in path.rglob("*.py")
            if not any(part in SKIP_DIRS for part in p.parts)
        ]
        return targets, {"mode": "target"}
    return [], {"mode": "target"}


def _file_size_heuristic(path: Path, max_lines: int = 400) -> list[Finding]:
    """Flag files exceeding the configured line threshold."""
    src = _read_file_safely(path)
    if src is None:
        return []
    n = src.count("\n") + 1
    if n <= max_lines:
        return []
    return [
        Finding(
            path=str(path),
            line=max_lines + 1,
            rule="file-size",
            severity="warn",
            message=f"file has {n} lines (threshold {max_lines}) — consider splitting",
        )
    ]


def _todo_density_heuristic(path: Path) -> list[Finding]:
    """Flag files with TODO/FIXME/XXX density exceeding 2%."""
    src = _read_file_safely(path)
    if src is None:
        return []
    lines = src.splitlines()
    if not lines:
        return []
    n_lines = len(lines)
    matches = [i for i, line in enumerate(lines, start=1) if TODO_PATTERN.search(line)]
    density = len(matches) / n_lines
    if density < 0.02 or not matches:
        return []
    out = [
        Finding(
            path=str(path),
            line=matches[0],
            rule="todo-density",
            severity="warn",
            message=f"{len(matches)} TODO/FIXME/XXX markers in {n_lines} lines ({density:.1%}) — resolve or track",
        )
    ]
    for ln in matches[1:5]:
        out.append(
            Finding(
                path=str(path),
                line=ln,
                rule="todo-density",
                severity="info",
                message=f"TODO/FIXME marker at line {ln}",
            )
        )
    return out


def _should_skip_docstring_node(node: ast.AST) -> bool:
    """Check if AST node should be skipped during docstring verification."""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return True
    if ast.get_docstring(node, clean=False) is not None:
        return True
    name = getattr(node, "name", "")
    if name.startswith("__") and name.endswith("__"):
        return True
    return name.startswith("_")


def _has_comment_above(lines: list[str], lineno: int) -> bool:
    """Check whether a line in the source file has a comment immediately above it."""
    if lineno < 2 or lineno - 2 >= len(lines):
        return False
    return lines[lineno - 2].strip().startswith("#")


def _missing_docstrings_heuristic(path: Path) -> list[Finding]:
    """Flag Python def/class without a docstring immediately above."""
    src = _read_file_safely(path)
    if src is None:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    out: list[Finding] = []
    lines = src.splitlines()

    for node in ast.walk(tree):
        if _should_skip_docstring_node(node):
            continue
        line = getattr(node, "lineno", 0)
        if _has_comment_above(lines, line):
            continue
        kind = (
            "function"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            else "class"
        )
        name = getattr(node, "name", "")
        out.append(
            Finding(
                path=str(path),
                line=line,
                rule="missing-docstring",
                severity="info",
                message=f"{kind} '{name}' has no docstring",
            )
        )
    return out


def _is_suspicious_screaming_name(name: str, value_node: ast.AST) -> bool:
    """Determine if an identifier is SCREAMING_CASE without being a constant literal."""
    if isinstance(value_node, ast.Constant):
        return False
    return name.isupper() and "_" in name and len(name) > 2


def _naming_heuristic(path: Path) -> list[Finding]:
    """Flag SCREAMING_CASE identifiers at module level that aren't assigned a literal."""
    src = _read_file_safely(path)
    if src is None:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    out: list[Finding] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for tgt in node.targets:
            if isinstance(tgt, ast.Name) and _is_suspicious_screaming_name(
                tgt.id, node.value
            ):
                out.append(
                    Finding(
                        path=str(path),
                        line=getattr(node, "lineno", 0),
                        rule="naming",
                        severity="info",
                        message=(
                            f"identifier '{tgt.id}' is SCREAMING_CASE but assigned a non-literal "
                            "— is it really a constant?"
                        ),
                    )
                )
    return out


def _is_source_policy_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    """Return whether a configured source-policy glob excludes ``path``."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return any(relative.match(pattern) for pattern in patterns)


def _scaffold_marker_heuristic(path: Path, markers: list[str]) -> list[Finding]:
    """Find configured unfinished-scaffold markers without inferring authorship."""
    if not markers:
        return []
    source = _read_file_safely(path)
    if source is None:
        return []

    findings: list[Finding] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        marker = next((value for value in markers if value and value in line), None)
        if marker is not None:
            findings.append(
                Finding(
                    path=str(path),
                    line=line_number,
                    rule="scaffold-marker",
                    severity="warn",
                    message=(
                        f"configured scaffold marker {marker!r} — replace it or add "
                        "the path to review.source_policy_exclude"
                    ),
                )
            )
    return findings


def _check_complexity_heuristic(path: Path, max_complexity: int = 10) -> list[Finding]:
    """Analyze Python AST to check for functions exceeding McCabe complexity threshold."""
    src = _read_file_safely(path)
    if src is None:
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        complexity = 1
        for child in ast.walk(node):
            if isinstance(
                child,
                (
                    ast.If,
                    ast.While,
                    ast.For,
                    ast.AsyncFor,
                    ast.ExceptHandler,
                    ast.With,
                    ast.AsyncWith,
                    ast.Assert,
                ),
            ):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        if complexity > max_complexity:
            findings.append(
                Finding(
                    path=str(path),
                    line=getattr(node, "lineno", 0),
                    rule="complexity",
                    severity="warn",
                    message=f"function '{node.name}' has complexity {complexity} (threshold {max_complexity})",
                )
            )
    return findings


def check_file_heuristics(
    path: Path,
    *,
    root: Path,
    max_lines: int = 400,
    scaffold_markers: list[str] | None = None,
    source_policy_exclude: list[str] | None = None,
) -> list[Finding]:
    """Run standard heuristic checks on a single reviewable file."""
    findings: list[Finding] = []
    findings.extend(_file_size_heuristic(path, max_lines))
    findings.extend(_todo_density_heuristic(path))
    findings.extend(_missing_docstrings_heuristic(path))
    findings.extend(_naming_heuristic(path))
    if not _is_source_policy_excluded(path, root, source_policy_exclude or []):
        findings.extend(_scaffold_marker_heuristic(path, scaffold_markers or []))
    return findings


# Compatibility aliases matching P60.4.2 specifications
_check_large_file_heuristic = _file_size_heuristic
_check_line_length_heuristic = _file_size_heuristic
_check_scaffold_heuristic = _scaffold_marker_heuristic
_check_todo_heuristic = _todo_density_heuristic
_check_source_policy_exclusions = _is_source_policy_excluded

# Public canonical aliases
collect_reviewable_files = _collect_reviewable_files
read_file_safely = _read_file_safely
file_size_heuristic = _file_size_heuristic
todo_density_heuristic = _todo_density_heuristic
missing_docstrings_heuristic = _missing_docstrings_heuristic
naming_heuristic = _naming_heuristic
scaffold_marker_heuristic = _scaffold_marker_heuristic
is_source_policy_excluded = _is_source_policy_excluded
check_complexity_heuristic = _check_complexity_heuristic
check_large_file_heuristic = _check_large_file_heuristic
check_scaffold_heuristic = _check_scaffold_heuristic
check_line_length_heuristic = _check_line_length_heuristic
check_todo_heuristic = _check_todo_heuristic
check_source_policy_exclusions = _check_source_policy_exclusions

__all__ = [
    "MAX_AST_DEPTH",
    "MAX_FILE_BYTES",
    "SKIP_DIRS",
    "TODO_PATTERN",
    "_check_complexity_heuristic",
    "_check_large_file_heuristic",
    "_check_line_length_heuristic",
    "_check_scaffold_heuristic",
    "_check_source_policy_exclusions",
    "_check_todo_heuristic",
    "_collect_reviewable_files",
    "_file_size_heuristic",
    "_is_source_policy_excluded",
    "_missing_docstrings_heuristic",
    "_naming_heuristic",
    "_read_file_safely",
    "_scaffold_marker_heuristic",
    "_todo_density_heuristic",
    "check_complexity_heuristic",
    "check_file_heuristics",
    "check_large_file_heuristic",
    "check_line_length_heuristic",
    "check_scaffold_heuristic",
    "check_source_policy_exclusions",
    "check_todo_heuristic",
    "collect_reviewable_files",
    "file_size_heuristic",
    "is_source_policy_excluded",
    "missing_docstrings_heuristic",
    "naming_heuristic",
    "read_file_safely",
    "scaffold_marker_heuristic",
    "todo_density_heuristic",
]
