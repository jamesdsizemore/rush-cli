"""AST-Merkle reactive cache invalidation engine storing node hashes in .rush/cache/merkle.json."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from rush.memory.transactions import CASMapTransaction


class MerkleInvalidator:
    """Tracks AST node content hashes to perform reactive cache invalidation."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve() if project_root else Path.cwd().resolve()
        )
        self.cache_file = self.project_root / ".rush" / "cache" / "merkle.json"
        self.tx = CASMapTransaction(
            file_path=self.cache_file, root_path=self.project_root
        )
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, str]:
        return self.tx.read(allow_missing=True).data

    def _write(self, data: dict[str, str]) -> None:
        def mutator(_old: dict[str, Any]) -> dict[str, Any]:
            return data

        self.tx.update(mutator, max_retries=20)

    def hash_content(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def snapshot_paths(
        project_root: Path, paths: list[str]
    ) -> dict[str, dict[str, str]]:
        """Return a read-only content-hash snapshot for repository-local paths."""
        root = project_root.resolve()
        snapshots: dict[str, dict[str, str]] = {}
        for raw_path in paths:
            candidate = (root / raw_path).resolve()
            if root not in candidate.parents or not candidate.is_file():
                snapshots[raw_path] = {"state": "missing"}
                continue
            with candidate.open("rb") as source:
                snapshots[raw_path] = {
                    "state": "present",
                    "sha256": hashlib.file_digest(source, "sha256").hexdigest(),
                }
        return snapshots

    def check_and_update(self, symbol_key: str, content: str) -> bool:
        """Returns True if the content changed and invalidated the cache entry."""
        current_hash = self.hash_content(content)
        snapshot = self.tx.read(allow_missing=True)
        if snapshot.data.get(symbol_key) == current_hash:
            return False

        changed = False

        def mutator(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal changed
            if data.get(symbol_key) != current_hash:
                data[symbol_key] = current_hash
                changed = True
            return data

        self.tx.update(mutator, max_retries=20)
        return changed
