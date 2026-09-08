"""User and agent preference store persisting to .rush/preferences.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rush.memory.migration import read_origin, read_origin_kind
from rush.memory.transactions import CASMapTransaction


class PreferenceStore:
    """Manages persistent developer preferences."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve() if project_root else Path.cwd().resolve()
        )
        self.store_file = self.project_root / ".rush" / "preferences.json"
        self.tx = CASMapTransaction(
            file_path=self.store_file, root_path=self.project_root
        )
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.store_file.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, Any]:
        return self.tx.read(allow_missing=True).data

    def _write(self, data: dict[str, Any]) -> None:
        def mutator(_old: dict[str, Any]) -> dict[str, Any]:
            return data

        self.tx.update(mutator, max_retries=20)

    def get(self, key: str, default: Any = None) -> Any:
        data = self._read()
        if key in data:
            return data[key]
        migrated = read_origin(self.project_root, "preference", key)
        if migrated is not None:
            return migrated.get("value", default)
        return default

    def set(self, key: str, value: Any) -> None:
        def mutator(data: dict[str, Any]) -> dict[str, Any]:
            data[key] = value
            return data

        self.tx.update(mutator, max_retries=20)

    def delete(self, key: str) -> bool:
        snapshot = self.tx.read(allow_missing=True)
        if key not in snapshot.data:
            return False

        deleted = False

        def mutator(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal deleted
            if key in data:
                del data[key]
                deleted = True
            return data

        self.tx.update(mutator, max_retries=20)
        return deleted

    def list_all(self) -> dict[str, Any]:
        data = dict(self._read())
        for entry in read_origin_kind(self.project_root, "preference"):
            key = entry.get("key")
            if key is not None and key not in data:
                data[key] = entry.get("value")
        return data
