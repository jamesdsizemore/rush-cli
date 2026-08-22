"""Session checkpoint journal storing developer context snapshots in .rush/sessions/."""

import json
import time
from pathlib import Path
from typing import Any


class CheckpointJournal:
    """Manages session checkpoints and replay state."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.session_dir = self.project_root / ".rush" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def save_checkpoint(
        self, name: str, metadata: dict[str, Any], files: list[str]
    ) -> Path:
        """Saves a point-in-time session checkpoint."""
        timestamp = int(time.time())
        checkpoint_data = {
            "name": name,
            "created_at": timestamp,
            "metadata": metadata,
            "files": files,
        }
        dest = self.session_dir / f"{name}.json"
        dest.write_text(json.dumps(checkpoint_data, indent=2), encoding="utf-8")
        return dest

    def restore_checkpoint(self, name: str) -> dict[str, Any] | None:
        """Retrieves a checkpoint by name."""
        target = self.session_dir / f"{name}.json"
        if not target.exists():
            return None
        return json.loads(target.read_text(encoding="utf-8"))

    def list_checkpoints(self) -> list[dict[str, Any]]:
        """Lists all saved session checkpoints."""
        results = []
        for p in self.session_dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append(data)
            except Exception:  # noqa: BLE001, S112
                continue
        return sorted(results, key=lambda x: x.get("created_at", 0), reverse=True)
