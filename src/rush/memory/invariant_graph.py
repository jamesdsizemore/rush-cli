"""Causal architectural invariant decision graph stored in .rush/memory/invariants.json."""

import json
from pathlib import Path
from typing import Any


class InvariantGraph:
    """Maintains project rules and invariant relationships."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.graph_file = self.project_root / ".rush" / "memory" / "invariants.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.graph_file.exists():
            self.graph_file.write_text("{}", encoding="utf-8")

    def _read(self) -> dict[str, Any]:
        try:
            return json.loads(self.graph_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _write(self, data: dict[str, Any]) -> None:
        self.graph_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_invariant(self, rule_id: str, description: str, rationale: str) -> None:
        data = self._read()
        data[rule_id] = {
            "description": description,
            "rationale": rationale,
            "status": "active",
        }
        self._write(data)

    def get_all(self) -> dict[str, Any]:
        return self._read()
