"""AST-Merkle reactive cache invalidation engine storing node hashes in .rush/cache/merkle.json."""

import hashlib
import json
from pathlib import Path


class MerkleInvalidator:
    """Tracks AST node content hashes to perform reactive cache invalidation."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.cache_file = self.project_root / ".rush" / "cache" / "merkle.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.cache_file.exists():
            self.cache_file.write_text("{}", encoding="utf-8")

    def _read(self) -> dict[str, str]:
        try:
            return json.loads(self.cache_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _write(self, data: dict[str, str]) -> None:
        self.cache_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

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
        data = self._read()
        previous_hash = data.get(symbol_key)
        if previous_hash != current_hash:
            data[symbol_key] = current_hash
            self._write(data)
            return True
        return False
