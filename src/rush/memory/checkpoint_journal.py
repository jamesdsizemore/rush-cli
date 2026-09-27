"""Session checkpoint journal storing developer context snapshots in .rush/sessions/."""

from __future__ import annotations

import functools
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from rush.io.atomic_file import AtomicFile, SanitizedJsonValue
from rush.io.physical_paths import PhysicalRoot
from rush.memory.migration import read_origin_kind_refs_readonly, read_origin_readonly
from rush.memory.store import MemoryArtifact, TypedArtifactStore, note_memory_read
from rush.memory.trust import default_entry_tier
from rush.safety.redactor import SecretRedactor

_SESSIONS = Path(".rush") / "sessions"


class CheckpointJournal:
    """Manages session checkpoints and replay state.

    T10 (R10.2): construction has no side effects. Only a write (`save_checkpoint`,
    or the writer-side `session_dir` accessor) creates the root and `.rush/sessions`;
    `restore_checkpoint`/`list_checkpoints` read JSON first, then `memory.db`
    read-only, and create nothing."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()

    @functools.cached_property
    def session_dir(self) -> Path:
        """The contained `.rush/sessions` directory, created on first access."""
        return self._ensure_session_dir()

    def _ensure_session_dir(self) -> Path:
        self.project_root.mkdir(parents=True, exist_ok=True)
        physical = PhysicalRoot(self.project_root)
        directory = self.project_root
        for rel in (Path(".rush"), _SESSIONS):
            directory = physical.open_contained(rel, purpose="write")
            directory.mkdir(exist_ok=True)
        return directory

    @property
    def physical_root(self) -> PhysicalRoot:
        """The containment root; the project root must already exist."""
        return PhysicalRoot(self.project_root)

    def _readable_root(self) -> PhysicalRoot | None:
        """The containment root for reads; `None` when the root does not exist."""
        return PhysicalRoot(self.project_root) if self.project_root.is_dir() else None

    def save_checkpoint(
        self, name: str, metadata: dict[str, Any], files: list[str]
    ) -> Path:
        """Saves a point-in-time session checkpoint using AtomicFile and schema 1.0.0."""
        self._ensure_session_dir()
        timestamp = int(time.time())

        checkpoint_data, _ = SecretRedactor.redact_value(
            {
                "schema_version": "1.0.0",
                "checkpoint_id": name,
                "name": name,
                "status": "ok",
                "created_at": timestamp,
                "metadata": metadata,
                "files": files,
            }
        )
        rel_path = _SESSIONS / f"{name}.json"
        atomic = AtomicFile(PhysicalRoot(self.project_root))
        sanitized = SanitizedJsonValue.from_value(checkpoint_data)
        result = atomic.write_json(rel_path, sanitized)
        self._write_handoff_artifact(name, checkpoint_data, timestamp)
        return result

    def _write_handoff_artifact(
        self, name: str, checkpoint_data: dict[str, Any], created_at: float
    ) -> None:
        """Forward-writes the checkpoint (receipt included) as one `family="handoff"` row.

        No `origin_kind`/`origin_id` is set here (unlike `migration.migrate_checkpoint_journal`'s
        one-shot absorption of pre-existing files) so this per-save write never collides with, or
        gets skipped by, that idempotent migration's `(origin_kind, origin_id)` uniqueness check.
        """
        TypedArtifactStore(self.project_root).write(
            MemoryArtifact(
                id=str(uuid.uuid4()),
                family="handoff",
                subject="active_context",
                trust_tier=default_entry_tier("local_tool"),
                content=checkpoint_data,
                source="checkpoint_journal:save_checkpoint",
                created_at=created_at,
                symbol_ref=SecretRedactor.redact_text(name),
            )
        )

    def restore_checkpoint(self, name: str) -> dict[str, Any] | None:
        """Retrieves a checkpoint by name.

        Tries the physical `.json` file first; if it is absent (already renamed `.migrated` by
        `migration.migrate_checkpoint_journal`), falls back to the `TypedArtifactStore` row so this
        method stays the sole existence authority `continuity.py`'s `_run_restore` relies on.
        The store read is `read_origin_readonly`: nothing is created or migrated.
        """
        physical = self._readable_root()
        if physical is None:
            return None
        target = physical.open_contained(_SESSIONS / f"{name}.json", purpose="read")
        if target.exists():
            try:
                target = physical.open_contained(
                    _SESSIONS / f"{name}.json", purpose="read"
                )
                data = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return None
                return data
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                return None
        physical.open_contained(Path(".rush") / "memory.db", purpose="read")
        migrated = read_origin_readonly(self.project_root, "checkpoint", name)
        if migrated is None or migrated.get("status") == "corrupt":
            return None
        return migrated

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """Lists all saved session checkpoints, retaining and digesting corrupt records."""
        results = []
        physical_names = set()
        physical = self._readable_root()
        if physical is None:
            return []
        session_dir = physical.open_contained(_SESSIONS, purpose="read")
        candidates = session_dir.glob("*.json") if session_dir.is_dir() else ()
        for candidate in candidates:
            p = physical.open_contained(_SESSIONS / candidate.name, purpose="read")
            if not p.is_file():
                continue
            physical_names.add(p.stem)
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise TypeError(
                        f"Checkpoint data in '{p.name}' is not a JSON object"
                    )
                if "checkpoint_id" not in data:
                    data["checkpoint_id"] = data.get("name", p.stem)
                if "name" not in data:
                    data["name"] = data.get("checkpoint_id", p.stem)
                if "status" not in data:
                    data["status"] = "ok"
                results.append(data)
            except (
                OSError,
                json.JSONDecodeError,
                UnicodeDecodeError,
                TypeError,
                ValueError,
            ) as exc:
                try:
                    p = physical.open_contained(_SESSIONS / p.name, purpose="read")
                    raw_bytes = p.read_bytes()
                    digest = hashlib.sha256(raw_bytes).hexdigest()
                except OSError:
                    raw_bytes = b""
                    digest = hashlib.sha256(b"").hexdigest()
                mtime = 0
                try:
                    p = physical.open_contained(_SESSIONS / p.name, purpose="read")
                    mtime = int(p.stat().st_mtime)
                except OSError:
                    pass
                results.append(
                    {
                        "checkpoint_id": p.stem,
                        "name": p.stem,
                        "status": "corrupt",
                        "raw_bytes_digest": digest,
                        "error_message": str(exc),
                        "created_at": mtime,
                    }
                )
        seen = physical_names | {str(entry["checkpoint_id"]) for entry in results}
        physical.open_contained(Path(".rush") / "memory.db", purpose="read")
        for entry, ref in read_origin_kind_refs_readonly(
            self.project_root, "checkpoint"
        ):
            identity = str(entry.get("checkpoint_id") or entry.get("name"))
            if identity not in seen:
                results.append(entry)
                seen.add(identity)
                # T19: only a store row this listing actually returns is read.
                if ref is not None:
                    note_memory_read(*ref)
        return sorted(results, key=lambda x: x.get("created_at", 0), reverse=True)
