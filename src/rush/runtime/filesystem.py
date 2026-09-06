"""Runtime filesystem containment and atomic write primitives."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def resolve_contained_output(root: Path, relative: str | Path) -> Path:
    """Resolve a target path strictly within root without escaping or symlink traversal.

    Rejects absolute paths, parent-traversal components ('..'), and existing symlinks.
    """
    rel_str = str(relative)
    rel_path = Path(relative)
    if (
        rel_path.is_absolute()
        or rel_str.startswith(("/", "\\"))
        or bool(rel_path.drive)
    ):
        raise ValueError(f"Target path must be relative, got absolute: {rel_str!r}")
    if ".." in rel_path.parts:
        raise ValueError(
            f"Parent traversal '..' is forbidden in output path: {rel_str!r}"
        )

    resolved_root = root.resolve()
    candidate = resolved_root / rel_path

    # Check symlinks on each component before resolution
    cur = candidate
    while cur != resolved_root and cur.parent != cur:
        if cur.is_symlink():
            raise ValueError(f"symlink found in target path: {cur}")
        cur = cur.parent

    target = candidate.resolve()

    if not target.is_relative_to(resolved_root):
        raise ValueError(f"Resolved path {target} escapes root {resolved_root}")

    if target.is_symlink():
        raise ValueError(f"symlink found at resolved target: {target}")

    return target


def atomic_write_bytes(root: Path, relative: str | Path, data: bytes) -> Path:
    """Write bytes atomically to a contained target path, replacing any existing file."""
    target = resolve_contained_output(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)

    resolved_root = root.resolve()
    if not target.parent.resolve().is_relative_to(resolved_root):
        raise ValueError(f"Target parent directory escapes root {resolved_root}")

    temp_file = tempfile.NamedTemporaryFile(dir=target.parent, delete=False)  # noqa: SIM115
    temp_path = Path(temp_file.name)
    try:
        temp_file.write(data)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_file.close()

        if temp_path.is_symlink() or target.is_symlink():
            raise ValueError("Symlinks forbidden during atomic replacement")

        os.replace(temp_path, target)
        return target
    except Exception:
        temp_file.close()
        if temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
        raise


__all__ = [
    "atomic_write_bytes",
    "resolve_contained_output",
]
