"""CAS map transactions providing optimistic concurrency and strict integrity validation."""

from __future__ import annotations

import copy
import hashlib
import json
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.io.atomic_file import AtomicFile, AtomicWriteError, SanitizedJsonValue
from rush.io.physical_paths import ContainmentError, PhysicalRoot


class StoreError(Exception):
    """Base exception for all map store transaction errors."""


class StoreNotFoundError(StoreError):
    """Raised when the store file does not exist and allow_missing is False."""


class StoreCorruptionError(StoreError):
    """Raised when the store file contains corrupt data that cannot be decoded or parsed."""

    def __init__(self, message: str, raw_bytes: bytes, digest: str) -> None:
        super().__init__(f"{message} (digest: {digest})")
        self.raw_bytes = raw_bytes
        self.digest = digest


class StoreValidationError(StoreError):
    """Raised when the store payload schema is invalid (missing version: int or data: dict)."""


class StoreIOError(StoreError):
    """Raised when an underlying I/O or filesystem failure occurs."""


class CASConflictError(StoreError):
    """Raised when an optimistic concurrency CAS version conflict occurs or retries are exhausted."""


@dataclass(frozen=True)
class VersionedSnapshot[T]:
    version: int
    data: T
    content_hash: str


_file_locks: dict[Path, threading.RLock] = {}
_file_locks_guard = threading.Lock()


def _get_file_lock(path: Path) -> threading.RLock:
    with _file_locks_guard:
        resolved = path.resolve()
        if resolved not in _file_locks:
            _file_locks[resolved] = threading.RLock()
        return _file_locks[resolved]


class CASMapTransaction:
    """Provides optimistic concurrency CAS transactions over contained JSON map files."""

    def __init__(self, file_path: Path, root_path: Path | None = None) -> None:
        file_path_p = Path(file_path)
        if root_path is not None:
            self.root_path = Path(root_path).resolve()
            self.root_path.mkdir(parents=True, exist_ok=True)
            self.physical_root = PhysicalRoot(self.root_path)
            if file_path_p.is_absolute():
                self.relative_path = file_path_p.resolve().relative_to(self.root_path)
            else:
                self.relative_path = file_path_p
        else:
            if file_path_p.is_absolute():
                resolved_file = file_path_p.resolve()
                self.root_path = resolved_file.parent
                self.root_path.mkdir(parents=True, exist_ok=True)
                self.physical_root = PhysicalRoot(self.root_path)
                self.relative_path = Path(resolved_file.name)
            else:
                self.root_path = Path.cwd().resolve()
                self.physical_root = PhysicalRoot(self.root_path)
                self.relative_path = file_path_p

        self.file_path = self.physical_root.open_contained(
            self.relative_path, purpose="read"
        )

    def read(self, allow_missing: bool = False) -> VersionedSnapshot[dict[str, Any]]:
        """Read and validate snapshot state fail-closed."""
        lock = _get_file_lock(self.file_path)
        with lock:
            try:
                if not self.file_path.exists():
                    if allow_missing:
                        return VersionedSnapshot(version=0, data={}, content_hash="")
                    raise StoreNotFoundError(f"Store file not found: {self.file_path}")
                raw = self.file_path.read_bytes()
            except StoreNotFoundError:
                raise
            except FileNotFoundError:
                if allow_missing:
                    return VersionedSnapshot(version=0, data={}, content_hash="")
                raise StoreNotFoundError(
                    f"Store file not found: {self.file_path}"
                ) from None
            except OSError as exc:
                raise StoreIOError(f"I/O error reading store file: {exc}") from exc

            try:
                text = raw.decode("utf-8")
                payload = json.loads(text)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                digest = hashlib.sha256(raw).hexdigest()
                raise StoreCorruptionError(
                    f"Corrupt store file: {exc}", raw_bytes=raw, digest=digest
                ) from exc

            if not isinstance(payload, dict):
                raise StoreValidationError("Store payload must be a JSON object")

            if (
                "version" not in payload
                or type(payload["version"]) is not int
                or payload["version"] < 0
            ):
                raise StoreValidationError(
                    "Store payload must contain non-negative integer 'version'"
                )

            if "data" not in payload or not isinstance(payload["data"], dict):
                raise StoreValidationError(
                    "Store payload must contain dictionary 'data'"
                )

            content_hash = hashlib.sha256(raw).hexdigest()
            return VersionedSnapshot(
                version=payload["version"],
                data=payload["data"],
                content_hash=content_hash,
            )

    def write(
        self, new_data: dict[str, Any], expected_version: int
    ) -> VersionedSnapshot[dict[str, Any]]:
        """Atomically perform compare-and-swap write with monotonic version increment."""
        if not isinstance(new_data, dict):
            raise StoreValidationError("Store payload 'data' must be a dict")

        lock = _get_file_lock(self.file_path)
        with lock:
            current = self.read(allow_missing=True)
            if current.version != expected_version:
                raise CASConflictError(
                    f"CAS version conflict: expected {expected_version}, but found {current.version}"
                )

            next_version = expected_version + 1
            payload = {
                "schema_version": "1.0.0",
                "version": next_version,
                "data": new_data,
            }
            sanitized = SanitizedJsonValue.from_value(payload)

            try:
                atomic = AtomicFile(self.physical_root)
                target = atomic.write_json(self.relative_path, sanitized)
                raw = target.read_bytes()
            except StoreError:
                raise
            except (AtomicWriteError, OSError, ContainmentError) as exc:
                raise StoreIOError(f"I/O error writing store file: {exc}") from exc

            digest = hashlib.sha256(raw).hexdigest()
            written_payload = json.loads(raw.decode("utf-8"))
            return VersionedSnapshot(
                version=next_version,
                data=written_payload["data"],
                content_hash=digest,
            )

    def update(
        self,
        mutator: Callable[[dict[str, Any]], dict[str, Any]],
        max_retries: int = 3,
    ) -> VersionedSnapshot[dict[str, Any]]:
        """Optimistic concurrency loop applying mutator with retry on CAS conflict."""
        if max_retries <= 0:
            raise CASConflictError("max_retries must be greater than 0")

        for attempt in range(max_retries):
            snapshot = self.read(allow_missing=True)
            current_data = copy.deepcopy(snapshot.data)
            mutated_data = mutator(current_data)
            try:
                return self.write(mutated_data, expected_version=snapshot.version)
            except CASConflictError:
                if attempt == max_retries - 1:
                    raise CASConflictError(
                        f"Exceeded max retries ({max_retries}) due to concurrent CAS conflicts"
                    ) from None
                time.sleep(0.005 * (2**attempt + random.uniform(0.0, 0.5)))

        raise CASConflictError(
            f"Exceeded max retries ({max_retries}) due to concurrent CAS conflicts"
        )
