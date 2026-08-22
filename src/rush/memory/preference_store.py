"""User and agent preference store persisting to .rush/preferences.json."""

import json
from pathlib import Path
from typing import Any


class PreferenceStore:
    """Manages persistent developer preferences."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.store_file = self.project_root / ".rush" / "preferences.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.store_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_file.exists():
            self.store_file.write_text("{}", encoding="utf-8")

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.store_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self.store_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        return self._read().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = value
        self._write(data)

    def delete(self, key: str) -> bool:
        data = self._read()
        if key in data:
            del data[key]
            self._write(data)
            return True
        return False

    def list_all(self) -> dict[str, Any]:
        return self._read()
