"""Ownership-bound cleanup for Rush-generated run artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

from rush.io.atomic_file import AtomicFile, SanitizedJsonValue
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.permissions import ExecutionPermissions, check_permissions
from rush.safety.redactor import sanitize_value

REGISTRY_PATH = Path(".rush/cleanup.json")
RUNS_PREFIX = (".rush", "runs")
ENTRY_KEYS = {"path", "sha256", "length", "producer", "device", "inode"}


class CleanupRegistryError(ValueError):
    """Raised when cleanup ownership data is malformed or unsafe."""


def _validate_registry_entry(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != ENTRY_KEYS:
        raise CleanupRegistryError("cleanup registry entry has invalid fields")
    path_value = raw["path"]
    relative = Path(path_value) if isinstance(path_value, str) else Path("/")
    if (
        not isinstance(path_value, str)
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.parts[:2] != RUNS_PREFIX
        or len(relative.parts) < 3
    ):
        raise CleanupRegistryError("cleanup registry path must be under .rush/runs/")
    if (
        not isinstance(raw["sha256"], str)
        or len(raw["sha256"]) != 64
        or any(char not in "0123456789abcdef" for char in raw["sha256"])
        or type(raw["length"]) is not int
        or raw["length"] < 0
        or not isinstance(raw["producer"], str)
        or not raw["producer"]
        or type(raw["device"]) is not int
        or type(raw["inode"]) is not int
    ):
        raise CleanupRegistryError("cleanup registry entry has invalid values")
    entry = dict(raw)
    entry["path"] = relative.as_posix()
    return entry


def _load_registry(physical_root: PhysicalRoot) -> list[dict[str, Any]]:
    registry_path = physical_root.open_contained(REGISTRY_PATH, purpose="read")
    if not registry_path.exists():
        return []
    try:
        registry_stat = os.lstat(registry_path)
        if not stat.S_ISREG(registry_stat.st_mode):
            raise CleanupRegistryError("cleanup registry is not an ordinary file")
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CleanupRegistryError(f"cleanup registry is malformed: {exc}") from exc
    if (
        not isinstance(raw, dict)
        or set(raw) != {"version", "artifacts"}
        or type(raw["version"]) is not int
        or raw["version"] != 1
        or not isinstance(raw["artifacts"], list)
    ):
        raise CleanupRegistryError("cleanup registry has invalid structure")
    entries = [_validate_registry_entry(entry) for entry in raw["artifacts"]]
    paths = [entry["path"] for entry in entries]
    if len(paths) != len(set(paths)):
        raise CleanupRegistryError("cleanup registry contains duplicate paths")
    return entries


def _read_owned_file(
    physical_root: PhysicalRoot, entry: dict[str, Any]
) -> tuple[Path | None, bytes | None, str | None]:
    try:
        target = physical_root.open_contained(entry["path"], purpose="read")
        before = os.lstat(target)
        if not stat.S_ISREG(before.st_mode):
            return None, None, "target is not an ordinary file"
        with target.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            content = handle.read()
            after = os.fstat(handle.fileno())
        identity = (entry["device"], entry["inode"])
        if (
            (before.st_dev, before.st_ino) != identity
            or (opened.st_dev, opened.st_ino) != identity
            or (after.st_dev, after.st_ino) != identity
        ):
            return None, None, "target identity changed"
        if (
            len(content) != entry["length"]
            or hashlib.sha256(content).hexdigest() != entry["sha256"]
        ):
            return None, None, "target content changed"
        return target, content, None
    except (ContainmentError, FileNotFoundError, OSError) as exc:
        return None, None, str(exc)


def register_owned_artifact(
    root: Path,
    path: Path,
    producer: str,
    permissions: ExecutionPermissions | None,
) -> dict[str, Any]:
    """Atomically record one unchanged Rush-owned ordinary run artifact."""
    allowed, missing = check_permissions(
        ExecutionPermissions(artifact_write=True), permissions
    )
    if not allowed:
        raise PermissionError(f"artifact registration requires {', '.join(missing)}")

    lexical_root = Path(root).absolute()
    physical_root = PhysicalRoot(root)
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            relative = candidate.relative_to(lexical_root)
        except ValueError as exc:
            raise CleanupRegistryError("artifact is outside project root") from exc
    else:
        relative = candidate
    if (
        ".." in relative.parts
        or relative.parts[:2] != RUNS_PREFIX
        or len(relative.parts) < 3
    ):
        raise CleanupRegistryError("artifact must be under .rush/runs/")

    target = physical_root.open_contained(relative, purpose="read")
    try:
        target_stat = os.lstat(target)
    except OSError as exc:
        raise CleanupRegistryError(f"artifact cannot be inspected: {exc}") from exc
    if not stat.S_ISREG(target_stat.st_mode):
        raise CleanupRegistryError("artifact is not an ordinary file")
    with target.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        content = handle.read()
    if (opened.st_dev, opened.st_ino) != (target_stat.st_dev, target_stat.st_ino):
        raise CleanupRegistryError("artifact identity changed during registration")

    entry: dict[str, Any] = {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "length": len(content),
        "producer": producer,
        "device": target_stat.st_dev,
        "inode": target_stat.st_ino,
    }
    entry = _validate_registry_entry(entry)
    entries = _load_registry(physical_root)
    entries = [existing for existing in entries if existing["path"] != entry["path"]]
    entries.append(entry)
    entries.sort(key=lambda item: item["path"])
    sanitized = SanitizedJsonValue.from_value({"version": 1, "artifacts": entries})
    AtomicFile(physical_root).write_json(
        REGISTRY_PATH,
        sanitized,
    )
    return next(
        item for item in sanitized.value["artifacts"] if item["path"] == entry["path"]
    )


def _delete_owned_file(
    physical_root: PhysicalRoot, entry: dict[str, Any]
) -> tuple[int | None, str | None]:
    target, content, error = _read_owned_file(physical_root, entry)
    if error is not None or target is None or content is None:
        return None, error or "target validation failed"

    try:
        target = physical_root.open_contained(entry["path"], purpose="delete")
        expected_identity = (entry["device"], entry["inode"])
        if os.unlink in os.supports_dir_fd and os.stat in os.supports_dir_fd:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            parent_fd = os.open(target.parent, flags)
            try:
                current = os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
                if (
                    not stat.S_ISREG(current.st_mode)
                    or (current.st_dev, current.st_ino) != expected_identity
                ):
                    return None, "target identity changed"
                os.unlink(target.name, dir_fd=parent_fd)
            finally:
                os.close(parent_fd)
        else:
            current = os.lstat(target)
            if (
                not stat.S_ISREG(current.st_mode)
                or (current.st_dev, current.st_ino) != expected_identity
            ):
                return None, "target identity changed"
            target.unlink()
    except (ContainmentError, FileNotFoundError, OSError) as exc:
        return None, str(exc)
    return len(content), None


class ScratchCleaner:
    """Preview or remove unchanged artifacts registered as Rush-owned."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    @staticmethod
    def _result(
        *,
        status: str,
        apply: bool,
        preview_items: list[str] | None = None,
        removed_items: list[str] | None = None,
        refused_items: list[str] | None = None,
        bytes_freed: int = 0,
        preview_bytes: int = 0,
        registry_updated: bool = False,
        error: str | None = None,
    ) -> dict[str, Any]:
        preview = preview_items or []
        removed = removed_items or []
        refused = refused_items or []
        result: dict[str, Any] = {
            "status": status,
            "apply": apply,
            "preview_count": len(preview),
            "preview_items": preview,
            "removed_count": len(removed),
            "removed_items": removed,
            "refused_count": len(refused),
            "refused_items": refused,
            "bytes_freed": bytes_freed,
            "preview_bytes": preview_bytes,
            "registry_updated": registry_updated,
        }
        if error is not None:
            result["error"] = error
        sanitized = sanitize_value(result).value
        return sanitized if isinstance(sanitized, dict) else result

    def clean(
        self,
        apply: bool = False,
        permissions: ExecutionPermissions | None = None,
    ) -> dict[str, Any]:
        if apply:
            allowed, missing = check_permissions(
                ExecutionPermissions(artifact_write=True), permissions
            )
            if not allowed:
                return self._result(
                    status="skipped",
                    apply=True,
                    error=f"cleanup apply requires {', '.join(missing)}",
                )

        try:
            physical_root = PhysicalRoot(self.project_root)
            entries = _load_registry(physical_root)
        except (ValueError, ContainmentError, OSError) as exc:
            return self._result(status="error", apply=apply, error=str(exc))

        candidates: list[tuple[dict[str, Any], int]] = []
        refused: list[str] = []
        for entry in entries:
            _target, content, error = _read_owned_file(physical_root, entry)
            if error is not None or content is None:
                refused.append(entry["path"])
            else:
                candidates.append((entry, len(content)))

        if not apply:
            return self._result(
                status="preview" if not refused else "warn",
                apply=False,
                preview_items=[entry["path"] for entry, _size in candidates],
                refused_items=refused,
                preview_bytes=sum(size for _entry, size in candidates),
            )

        removed: list[str] = []
        bytes_freed = 0
        for entry, _initial_size in candidates:
            size, error = _delete_owned_file(physical_root, entry)
            if error is not None or size is None:
                refused.append(entry["path"])
                continue
            removed.append(entry["path"])
            bytes_freed += size

        registry_updated = False
        if removed:
            remaining = [entry for entry in entries if entry["path"] not in removed]
            try:
                AtomicFile(physical_root).write_json(
                    REGISTRY_PATH,
                    SanitizedJsonValue.from_value(
                        {"version": 1, "artifacts": remaining}
                    ),
                )
                registry_updated = True
            except Exception as exc:  # noqa: BLE001
                return self._result(
                    status="error",
                    apply=True,
                    removed_items=removed,
                    refused_items=refused,
                    bytes_freed=bytes_freed,
                    registry_updated=False,
                    error=f"cleanup registry update failed: {exc}",
                )

        return self._result(
            status="warn" if refused else "ok",
            apply=True,
            removed_items=removed,
            refused_items=refused,
            bytes_freed=bytes_freed,
            registry_updated=registry_updated,
        )
