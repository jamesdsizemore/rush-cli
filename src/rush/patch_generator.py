"""Unified diff generation and confined patch application."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

from rush.io.atomic_file import AtomicFile, AtomicWriteError, SanitizedBytes
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.logging import get_logger, log_subsystem

logger = get_logger("patch_generator")

PROTECTED_PATHS = frozenset({".git", ".env", ".rush/cache.db", "id_rsa", "id_ed25519"})
_HUNK_HEADER = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))?"
    r" \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@(?: .*)?$"
)


def generate_unified_diff(original: str, modified: str, file_path: str) -> str:
    """Generate canonical unified diff string from two text snapshots."""
    lines = difflib.unified_diff(
        original.splitlines(keepends=True),
        modified.splitlines(keepends=True),
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
    )
    rendered: list[str] = []
    for line in lines:
        if line.startswith((" ", "+", "-")) and not line.endswith("\n"):
            rendered.extend((line + "\n", "\\ No newline at end of file\n"))
        else:
            rendered.append(line)
    return "".join(rendered)


def _header_path(line: str, prefix: str) -> str | None:
    if not line.startswith(prefix):
        return None
    value = line[len(prefix) :].rstrip("\n").split("\t", 1)[0]
    if value == "/dev/null":
        return None
    if value.startswith(("a/", "b/")):
        return value[2:]
    return value


def _is_file_header(lines: list[str], position: int) -> bool:
    return (
        lines[position].startswith("--- ")
        and position + 1 < len(lines)
        and lines[position + 1].startswith("+++ ")
    )


def _parse_patch(
    patch_str: str,
) -> list[tuple[str, list[tuple[int, int, int, int, list[str]]]]] | None:
    if not patch_str or "GIT binary patch" in patch_str or "Binary files " in patch_str:
        return None
    lines = patch_str.splitlines(keepends=True)
    files: list[tuple[str, list[tuple[int, int, int, int, list[str]]]]] = []
    position = 0
    while position < len(lines):
        if lines[position].startswith("diff --git "):
            position += 1
            continue
        while position < len(lines) and lines[position].startswith(
            (
                "index ",
                "old mode ",
                "new mode ",
                "new file mode ",
                "deleted file mode ",
                "similarity index ",
                "dissimilarity index ",
                "rename from ",
                "rename to ",
                "copy from ",
                "copy to ",
            )
        ):
            position += 1
        if position >= len(lines) or not _is_file_header(lines, position):
            return None
        old_path = _header_path(lines[position], "--- ")
        new_path = _header_path(lines[position + 1], "+++ ")
        if not old_path or not new_path or old_path != new_path:
            return None
        position += 2
        hunks: list[tuple[int, int, int, int, list[str]]] = []
        while position < len(lines) and not (
            lines[position].startswith("diff --git ")
            or _is_file_header(lines, position)
        ):
            match = _HUNK_HEADER.match(lines[position].rstrip("\n"))
            if match is None:
                return None
            old_start = int(match["old_start"])
            old_count = int(match["old_count"] or 1)
            new_count = int(match["new_count"] or 1)
            position += 1
            hunk_lines: list[str] = []
            old_seen = new_seen = 0
            while old_seen < old_count or new_seen < new_count:
                if position >= len(lines):
                    return None
                line = lines[position]
                if line.startswith("\\ No newline at end of file"):
                    if not hunk_lines:
                        return None
                    hunk_lines[-1] = hunk_lines[-1].rstrip("\n")
                    position += 1
                    continue
                if not line.startswith((" ", "+", "-")):
                    return None
                hunk_lines.append(line)
                if line[0] in " -":
                    old_seen += 1
                if line[0] in " +":
                    new_seen += 1
                position += 1
            if old_seen != old_count or new_seen != new_count:
                return None
            while position < len(lines) and lines[position].startswith(
                "\\ No newline at end of file"
            ):
                if not hunk_lines:
                    return None
                hunk_lines[-1] = hunk_lines[-1].rstrip("\n")
                position += 1
            hunks.append(
                (
                    old_start,
                    old_count,
                    int(match["new_start"]),
                    new_count,
                    hunk_lines,
                )
            )
        if not hunks:
            return None
        if any(path == new_path for path, _hunks in files):
            return None
        files.append((new_path, hunks))
    return files or None


def _apply_hunks(
    original: str, hunks: list[tuple[int, int, int, int, list[str]]]
) -> str | None:
    source = original.splitlines(keepends=True)
    cursor = 0
    output: list[str] = []
    for old_start, old_count, new_start, new_count, hunk_lines in hunks:
        start = old_start if old_count == 0 else old_start - 1
        if start < cursor or start > len(source):
            return None
        output.extend(source[cursor:start])
        expected_new_start = len(output) if new_count == 0 else len(output) + 1
        if new_start != expected_new_start:
            return None
        cursor = start
        for line in hunk_lines:
            content = line[1:]
            if line[0] == "+":
                output.append(content)
                continue
            if cursor >= len(source) or source[cursor] != content:
                return None
            if line[0] == " ":
                output.append(source[cursor])
            cursor += 1
    output.extend(source[cursor:])
    return "".join(output)


def _validate_target(physical_root: PhysicalRoot, relative_path: str) -> Path:
    if any(part == ".." for part in Path(relative_path).parts):
        raise ValueError(
            "Security Error: Patch target resolves outside repository root"
        )
    if any(
        protected == relative_path or protected in Path(relative_path).parts
        for protected in PROTECTED_PATHS
    ):
        raise ValueError(
            f"Security Error: Protected system file cannot be modified: {relative_path}"
        )
    try:
        target = physical_root.open_contained(relative_path, purpose="write")
    except ContainmentError as exc:
        raise ValueError(
            "Security Error: Patch target resolves outside repository root"
        ) from exc
    if not target.is_file():
        raise FileNotFoundError(relative_path)
    return target


def _validate_relative_path(physical_root: PhysicalRoot, relative_path: str) -> None:
    if any(part == ".." for part in Path(relative_path).parts):
        raise ValueError(
            "Security Error: Patch target resolves outside repository root"
        )
    if any(
        protected == relative_path or protected in Path(relative_path).parts
        for protected in PROTECTED_PATHS
    ):
        raise ValueError(
            f"Security Error: Protected system file cannot be modified: {relative_path}"
        )
    try:
        physical_root.open_contained(relative_path, purpose="write")
    except ContainmentError as exc:
        raise ValueError(
            "Security Error: Patch target resolves outside repository root"
        ) from exc


def patch_target_paths(unified_diff: str) -> tuple[str, ...] | None:
    """Return validated parsed target paths for one complete unified diff."""
    parsed = _parse_patch(unified_diff)
    if parsed is None:
        return None
    return tuple(relative_path for relative_path, _hunks in parsed)


def apply_unified_patch(patch_str: str, repo_root: Path) -> bool:
    """Apply complete contained diff; return False without writes on mismatch."""
    physical_root = PhysicalRoot(repo_root)
    for line in patch_str.splitlines():
        if line.startswith("+++ "):
            relative_path = _header_path(line, "+++ ")
            if relative_path is not None:
                _validate_relative_path(physical_root, relative_path)
            break
    parsed = _parse_patch(patch_str)
    if parsed is None:
        log_subsystem("patch", "ERROR", "Patch is malformed or binary")
        return False
    updates: list[tuple[str, bytes, int]] = []
    try:
        for relative_path, hunks in parsed:
            target = _validate_target(physical_root, relative_path)
            updated = _apply_hunks(
                target.read_bytes().decode("utf-8"),
                hunks,
            )
            if updated is None:
                log_subsystem(
                    "patch", "ERROR", f"Patch context does not match: {relative_path}"
                )
                return False
            updates.append(
                (relative_path, updated.encode("utf-8"), target.stat().st_mode & 0o777)
            )
    except (FileNotFoundError, UnicodeDecodeError):
        return False
    writer = AtomicFile(physical_root)
    try:
        for relative_path, content, mode in updates:
            writer.write_bytes(relative_path, SanitizedBytes(content)).chmod(mode)
    except (AtomicWriteError, OSError):
        return False
    log_subsystem("patch", "INFO", f"Applied patch to {len(updates)} file(s)")
    return True
