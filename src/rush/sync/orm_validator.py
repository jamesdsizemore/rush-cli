"""Alembic / Prisma / Django migration drift checker."""

from __future__ import annotations

from pathlib import Path
from rush.tools.common import run_subprocess


class OrmMigrationDriftValidator:
    """Detects uncommitted or pending database migrations."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def check_alembic(self) -> tuple[bool, str]:
        if not (self.repo_root / "alembic.ini").exists():
            return True, "Alembic not detected."

        proc = run_subprocess(["alembic", "check"], cwd=self.repo_root)
        if proc.returncode != 0:
            return False, f"Alembic schema drift detected: {proc.stderr or proc.stdout}"
        return True, "Alembic migrations are in sync with database models."
