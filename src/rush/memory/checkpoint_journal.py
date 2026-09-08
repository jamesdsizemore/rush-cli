"""Session checkpoint journal storing developer context snapshots in .rush/sessions/."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any

from rush.io.atomic_file import AtomicFile, SanitizedJsonValue
from rush.io.physical_paths import PhysicalRoot
from rush.memory.migration import read_origin, read_origin_kind
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.memory.trust import default_entry_tier
from rush.safety.redactor import SecretRedactor


class CheckpointJournal:
    """Manages session checkpoints and replay state."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.session_dir = self.project_root / ".rush" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.physical_root = PhysicalRoot(self.project_root)

    def save_checkpoint(
        self, name: str, metadata: dict[str, Any], files: list[str]
    ) -> Path:
        """Saves a point-in-time session checkpoint using AtomicFile and schema 1.0.0."""
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
        rel_path = Path(".rush") / "sessions" / f"{name}.json"
        atomic = AtomicFile(self.physical_root)
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
        """
        target = self.session_dir / f"{name}.json"
        if target.exists():
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return None
                return data
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                return None
        migrated = read_origin(self.project_root, "checkpoint", name)
        if migrated is None or migrated.get("status") == "corrupt":
            return None
        return migrated

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """Lists all saved session checkpoints, retaining and digesting corrupt records."""
        results = []
        physical_names = set()
        for p in self.session_dir.glob("*.json"):
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
                    raw_bytes = p.read_bytes()
                    digest = hashlib.sha256(raw_bytes).hexdigest()
                except OSError:
                    raw_bytes = b""
                    digest = hashlib.sha256(b"").hexdigest()
                mtime = 0
                try:
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
        for entry in read_origin_kind(self.project_root, "checkpoint"):
            identity = str(entry.get("checkpoint_id") or entry.get("name"))
            if identity not in seen:
                results.append(entry)
                seen.add(identity)
        return sorted(results, key=lambda x: x.get("created_at", 0), reverse=True)
