from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.safety.redactor import SanitizationResult, sanitize_value


class AtomicWriteError(Exception):
    """Raised when an atomic write operation encounters a failure."""

    def __init__(
        self,
        code: str,
        message: str,
        temp_path: str | None = None,
        target_path: str | None = None,
    ) -> None:
        super().__init__(f"[{code}] target '{target_path}': {message}")
        self.code = code
        self.message = message
        self.temp_path = temp_path
        self.target_path = target_path


@dataclass(frozen=True)
class SanitizedBytes:
    data: bytes
    redaction_count: int = 0

    @classmethod
    def from_bytes(cls, raw: bytes) -> SanitizedBytes:
        """Sanitize UTF-8 decodable byte streams or wrap raw non-text binary data safely."""
        try:
            text = raw.decode("utf-8")
            res = sanitize_value(text)
            return cls(
                data=str(res.value).encode("utf-8"), redaction_count=res.redaction_count
            )
        except UnicodeDecodeError:
            # Binary data (images, bytecode) contains no string secrets; wrap directly
            return cls(data=raw, redaction_count=0)


@dataclass(frozen=True)
class SanitizedJsonValue:
    value: Any
    redaction_count: int = 0

    @classmethod
    def from_value(cls, raw: Any) -> SanitizedJsonValue:
        """Sanitize arbitrary Python data structures recursively before serialization."""
        res = sanitize_value(raw)
        return cls(value=res.value, redaction_count=res.redaction_count)


class AtomicFile:
    """Provides fail-closed, durable atomic file replacement within a PhysicalRoot."""

    def __init__(self, physical_root: PhysicalRoot) -> None:
        self.physical_root = physical_root

    def write_bytes(
        self,
        relative_path: Path | str,
        content: SanitizedBytes | SanitizationResult,
    ) -> Path:
        """Write sanitized bytes atomically using same-directory temporary file and fsync durability."""
        if not isinstance(content, (SanitizedBytes, SanitizationResult)):
            raise TypeError(
                "AtomicFile accepts only sanitized contracts (SanitizedBytes or SanitizationResult)"
            )

        if isinstance(content, SanitizedBytes):
            byte_data = content.data
        elif isinstance(content.value, bytes):
            byte_data = content.value
        elif isinstance(content.value, str):
            byte_data = content.value.encode("utf-8")
        else:
            byte_data = str(content.value).encode("utf-8")

        target = self.physical_root.open_contained(relative_path, purpose="write")
        target.parent.mkdir(parents=True, exist_ok=True)

        temp_path: Path | None = None
        owned_temp = False

        try:
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".rush_tmp_", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                owned_temp = True
                temp_file.write(byte_data)
                temp_file.flush()
                os.fsync(temp_file.fileno())

            # Pre-replace anti-swap TOCTOU verification
            if temp_path.is_symlink() or target.is_symlink():
                raise ContainmentError(
                    "SYMLINK_DISALLOWED",
                    "Symlink introduced prior to replace",
                    str(target),
                )

            os.replace(temp_path, target)
            return target
        except Exception as exc:
            if owned_temp and temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            if isinstance(exc, ContainmentError):
                raise
            raise AtomicWriteError(
                "WRITE_FAILED",
                str(exc),
                temp_path=str(temp_path) if temp_path is not None else None,
                target_path=str(target),
            ) from exc

    def write_json(
        self,
        relative_path: Path | str,
        content: SanitizedJsonValue | SanitizationResult,
    ) -> Path:
        """Serialize sanitized JSON structure and write atomically."""
        if not isinstance(content, (SanitizedJsonValue, SanitizationResult)):
            raise TypeError(
                "AtomicFile accepts only sanitized contracts (SanitizedJsonValue or SanitizationResult)"
            )

        raw_val = content.value
        serialized = json.dumps(
            raw_val,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        sanitized_bytes = SanitizedBytes(
            data=serialized, redaction_count=content.redaction_count
        )
        return self.write_bytes(relative_path, sanitized_bytes)
