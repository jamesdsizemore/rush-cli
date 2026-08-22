"""Cryptographic SHA-256 trust manager for plugins and custom engines."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrustedPluginRecord:
    name: str
    file_path: str
    sha256_hash: str
    granted_at: float
    granted_by: str = "local_user"


class PluginTrustStore:
    """Manages the local cryptographic trust store located at .rush/trust.json."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.trust_file = self.repo_root / ".rush" / "trust.json"

    def _compute_sha256(self, file_path: Path) -> str:
        sha = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                sha.update(chunk)
        return sha.hexdigest()

    def load_trust_store(self) -> dict[str, TrustedPluginRecord]:
        if not self.trust_file.exists():
            return {}
        try:
            raw_data = json.loads(self.trust_file.read_text(encoding="utf-8"))
            records = {}
            for name, item in raw_data.items():
                records[name] = TrustedPluginRecord(
                    name=name,
                    file_path=item["file_path"],
                    sha256_hash=item["sha256_hash"],
                    granted_at=item["granted_at"],
                    granted_by=item.get("granted_by", "local_user"),
                )
            return records
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return {}

    def is_trusted(self, plugin_name: str, executable_path: Path) -> bool:
        if not executable_path.exists() or not executable_path.is_file():
            return False
        store = self.load_trust_store()
        record = store.get(plugin_name)
        if not record:
            return False
        current_hash = self._compute_sha256(executable_path)
        return record.sha256_hash == current_hash

    def grant_trust(
        self, plugin_name: str, executable_path: Path
    ) -> TrustedPluginRecord:
        self.trust_file.parent.mkdir(parents=True, exist_ok=True)
        store = self.load_trust_store()
        current_hash = self._compute_sha256(executable_path)
        rel_path = (
            str(executable_path.relative_to(self.repo_root))
            if executable_path.is_relative_to(self.repo_root)
            else str(executable_path)
        )
        record = TrustedPluginRecord(
            name=plugin_name,
            file_path=rel_path,
            sha256_hash=current_hash,
            granted_at=time.time(),
            granted_by="local_user",
        )
        data = {
            k: {
                "file_path": v.file_path,
                "sha256_hash": v.sha256_hash,
                "granted_at": v.granted_at,
                "granted_by": v.granted_by,
            }
            for k, v in store.items()
        }
        data[plugin_name] = {
            "file_path": record.file_path,
            "sha256_hash": record.sha256_hash,
            "granted_at": record.granted_at,
            "granted_by": record.granted_by,
        }
        self.trust_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return record

    def revoke_trust(self, plugin_name: str) -> bool:
        if not self.trust_file.exists():
            return False
        store = self.load_trust_store()
        if plugin_name in store:
            data = {
                k: {
                    "file_path": v.file_path,
                    "sha256_hash": v.sha256_hash,
                    "granted_at": v.granted_at,
                    "granted_by": v.granted_by,
                }
                for k, v in store.items()
                if k != plugin_name
            }
            self.trust_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
        return False
