"""Physical filesystem containment boundaries and anti-traversal validation."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class ContainmentError(Exception):
    """Raised when a path breaches physical workspace containment boundaries."""

    def __init__(self, code: str, message: str, path: str) -> None:
        super().__init__(f"[{code}] at '{path}': {message}")
        self.code = code
        self.message = message
        self.path = path


class PhysicalRoot:
    """Enforces strict physical filesystem containment within a designated root directory."""

    def __init__(self, root_path: Path | str) -> None:
        self.root_path = Path(root_path).resolve()
        if not self.root_path.exists():
            raise ValueError(f"Physical root path does not exist: {self.root_path}")
        if not self.root_path.is_dir():
            raise ValueError(f"Physical root path is not a directory: {self.root_path}")

    def open_contained(self, relative_path: Path | str, purpose: str = "read") -> Path:
        """Validate and resolve relative_path, ensuring it is physically contained within root.

        Guarantees:
        - Rejects absolute paths (leading '/', '\\', or drive letters).
        - Rejects parent traversals ('..' in parts).
        - Rejects symlinks on the target or any directory component down from root.
        - Rejects Windows reparse points / directory junctions (0x400 attribute).
        - Revalidates resolved path containment via is_relative_to().
        - Returns physically validated candidate Path object.
        """
        rel = Path(relative_path)
        rel_str = str(relative_path)

        # 1. Reject absolute paths (leading '/', '\\', or Windows drive letters)
        has_drive_letter = (
            len(rel_str) >= 2 and rel_str[1] == ":" and rel_str[0].isalpha()
        )
        if (
            rel.is_absolute()
            or rel_str.startswith(("/", "\\"))
            or bool(rel.drive)
            or has_drive_letter
        ):
            raise ContainmentError(
                "ABSOLUTE_PATH_DISALLOWED", "Path must be relative", rel_str
            )

        # 2. Reject parent traversal ('..' in parts)
        if ".." in rel.parts:
            raise ContainmentError(
                "PARENT_TRAVERSAL_DISALLOWED",
                "Parent traversal '..' is forbidden",
                rel_str,
            )

        candidate = self.root_path / rel

        # 3. Walk intermediate directory components to verify no symlinks or reparse points
        current = self.root_path
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        for part in rel.parts:
            current = current / part
            if current.is_symlink():
                raise ContainmentError(
                    "SYMLINK_DISALLOWED",
                    f"Symlink detected at component '{current}'",
                    rel_str,
                )
            try:
                st = os.lstat(current)
                file_attrs = getattr(st, "st_file_attributes", 0)
                if (file_attrs & reparse_flag) or (
                    os.name == "nt" and getattr(current, "is_junction", lambda: False)()
                ):
                    raise ContainmentError(
                        "REPARSE_POINT_DISALLOWED",
                        f"Reparse point/junction at '{current}'",
                        rel_str,
                    )
            except ContainmentError:
                raise
            except (FileNotFoundError, OSError):
                pass

        # 4. Containment verification on resolved path
        resolved = candidate.resolve()
        if not resolved.is_relative_to(self.root_path):
            raise ContainmentError(
                "PATH_ESCAPE_DISALLOWED",
                f"Path escapes physical root: {resolved}",
                rel_str,
            )

        if resolved.is_symlink() or candidate.is_symlink():
            raise ContainmentError(
                "SYMLINK_DISALLOWED", f"Target resolves to symlink: {resolved}", rel_str
            )

        return candidate
