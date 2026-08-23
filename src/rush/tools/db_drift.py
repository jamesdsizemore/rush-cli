"""ORM-to-migration schema drift auditor comparing data models against SQL migrations."""

import ast
import re
from pathlib import Path
from typing import Any


class DbDriftAuditor:
    """Detects columns in ORM models (SQLAlchemy, SQLModel) that lack corresponding SQL migration statements."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def audit_drift(self) -> dict[str, Any]:
        orm_fields: dict[str, set[str]] = {}
        migration_columns: dict[str, set[str]] = {}

        # 1. Scan for ORM models in src/
        for py_file in (self.project_root / "src").glob("**/*.py"):
            try:
                code = py_file.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(code)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Detect model classes (e.g. inherits from Base, Model, SQLModel)
                        fields = set()
                        for item in node.body:
                            if isinstance(item, ast.AnnAssign) and isinstance(
                                item.target, ast.Name
                            ):
                                if not item.target.id.startswith("_"):
                                    fields.add(item.target.id)
                            elif isinstance(item, ast.Assign):
                                for target in item.targets:
                                    if isinstance(
                                        target, ast.Name
                                    ) and not target.id.startswith("_"):
                                        fields.add(target.id)
                        if fields and len(fields) > 1:
                            orm_fields[node.name] = fields
            except Exception:  # noqa: BLE001, S110
                pass

        # 2. Scan for migration files (SQL, Alembic migrations)
        for mig_file in self.project_root.glob("**/migrations/**/*.py"):
            try:
                content = mig_file.read_text(encoding="utf-8", errors="ignore")
                cols = re.findall(r"sa\.Column\(['\"](\w+)['\"]", content)
                for col in cols:
                    migration_columns.setdefault("all", set()).add(col)
            except Exception:  # noqa: BLE001, S110
                pass

        for sql_file in self.project_root.glob("**/*.sql"):
            try:
                content = sql_file.read_text(encoding="utf-8", errors="ignore")
                cols = re.findall(
                    r"\b([a-zA-Z0-9_]+)\s+(?:VARCHAR|TEXT|INTEGER|BOOLEAN|TIMESTAMP|DATETIME)\b",
                    content,
                    re.IGNORECASE,
                )
                for col in cols:
                    migration_columns.setdefault("all", set()).add(col.lower())
            except Exception:  # noqa: BLE001, S110
                pass

        drift_issues: list[dict[str, Any]] = []
        migrated = migration_columns.get("all", set())

        if migrated:
            for model_name, fields in orm_fields.items():
                unmigrated = [
                    f for f in fields if f.lower() not in migrated and f != "id"
                ]
                if unmigrated:
                    drift_issues.append(
                        {
                            "model": model_name,
                            "unmigrated_fields": unmigrated,
                            "details": f"Model '{model_name}' has fields {unmigrated} missing from migrations.",
                        }
                    )

        return {
            "passed": len(drift_issues) == 0,
            "drift_count": len(drift_issues),
            "drift_issues": drift_issues,
        }
