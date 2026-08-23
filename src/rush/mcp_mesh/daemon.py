"""Local file-based lock manager coordinating concurrent agent edits."""

import json
import time
from pathlib import Path


class MeshLockManager:
    """Provides non-blocking file-level mutual exclusion locks for multi-agent swarm operations."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.locks_dir = self.project_root / ".rush" / "locks"
        self.locks_dir.mkdir(parents=True, exist_ok=True)

    def _lock_file_for(self, target_path: Path) -> Path:
        sanitized = (
            str(target_path).replace("/", "_").replace("\\", "_").replace(":", "_")
        )
        return self.locks_dir / f"{sanitized}.lock"

    def acquire(self, file_path: Path, agent_id: str, timeout_s: float = 5.0) -> bool:
        lock_p = self._lock_file_for(file_path)
        start = time.time()
        while time.time() - start < timeout_s:
            if not lock_p.exists():
                try:
                    lock_p.write_text(
                        json.dumps({"agent_id": agent_id, "acquired_at": time.time()}),
                        encoding="utf-8",
                    )
                    return True
                except Exception:  # noqa: BLE001, S110
                    pass
            time.sleep(0.05)
        return False

    def release(self, file_path: Path, agent_id: str) -> bool:
        lock_p = self._lock_file_for(file_path)
        if lock_p.exists():
            try:
                data = json.loads(lock_p.read_text(encoding="utf-8"))
                if data.get("agent_id") == agent_id:
                    lock_p.unlink(missing_ok=True)
                    return True
            except Exception:  # noqa: BLE001, S110
                pass
        return False
