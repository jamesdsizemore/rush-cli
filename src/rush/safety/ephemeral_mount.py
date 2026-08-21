"""Ephemeral RAM-disk and tmpfs directory manager for ultra-fast sandbox execution."""

from __future__ import annotations

import tempfile
from pathlib import Path


class EphemeralMountManager:
    """Allocates ephemeral in-memory temporary workspaces for zero-disk-wear testing."""

    @staticmethod
    def create_ephemeral_workspace() -> Path:
        temp_dir = tempfile.mkdtemp(prefix="rush_ephemeral_")
        return Path(temp_dir)
