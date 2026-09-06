"""ORM-to-migration schema drift auditor comparing data models against SQL migrations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rush.tools.db_drift_rules import (
    collect_migrations,
    collect_models,
    evaluate_drift,
)


class DbDriftAuditor:
    """Detects columns in ORM models (SQLAlchemy, SQLModel) that lack corresponding SQL migration statements."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def audit_drift(self) -> dict[str, Any]:
        models = collect_models(self.project_root)
        migrations = collect_migrations(self.project_root)
        drift_issues = evaluate_drift(models, migrations)

        return {
            "passed": len(drift_issues) == 0,
            "drift_count": len(drift_issues),
            "drift_issues": drift_issues,
        }


__all__ = [
    "DbDriftAuditor",
    "collect_migrations",
    "collect_models",
    "evaluate_drift",
]
