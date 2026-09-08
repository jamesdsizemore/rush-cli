"""Causal architectural invariant decision graph stored in .rush/memory/invariants.json."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rush.memory.migration import read_origin_kind
from rush.memory.transactions import CASMapTransaction


class InvariantGraph:
    """Maintains project rules and invariant relationships."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (
            Path(project_root).resolve() if project_root else Path.cwd().resolve()
        )
        self.graph_file = self.project_root / ".rush" / "memory" / "invariants.json"
        self.tx = CASMapTransaction(
            file_path=self.graph_file, root_path=self.project_root
        )
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, Any]:
        return self.tx.read(allow_missing=True).data

    def _write(self, data: dict[str, Any]) -> None:
        def mutator(_old: dict[str, Any]) -> dict[str, Any]:
            return data

        self.tx.update(mutator, max_retries=20)

    def add_invariant(self, rule_id: str, description: str, rationale: str) -> None:
        def mutator(data: dict[str, Any]) -> dict[str, Any]:
            data[rule_id] = {
                "description": description,
                "rationale": rationale,
                "status": "active",
            }
            return data

        self.tx.update(mutator, max_retries=20)

    def get_all(self) -> dict[str, Any]:
        data = dict(self._read())
        for entry in read_origin_kind(self.project_root, "invariant_graph"):
            rule_id = entry.get("rule_id")
            if rule_id is not None and rule_id not in data:
                data[rule_id] = {k: v for k, v in entry.items() if k != "rule_id"}
        return data
