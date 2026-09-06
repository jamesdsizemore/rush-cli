"""Database schema drift analysis rules, model collectors, and migration parsers."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any


def _extract_model_fields(node: ast.ClassDef) -> set[str]:
    """Extract declared non-private fields from an AST class definition."""
    fields: set[str] = set()
    for item in node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            if not item.target.id.startswith("_"):
                fields.add(item.target.id)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("_"):
                    fields.add(target.id)
    return fields


def collect_models(project_root: Path) -> dict[str, set[str]]:
    """Scan src/ for ORM models and return mapping of class name to declared fields."""
    orm_fields: dict[str, set[str]] = {}
    src_dir = project_root / "src"
    if not src_dir.is_dir():
        return orm_fields

    for py_file in src_dir.glob("**/*.py"):
        try:
            code = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    fields = _extract_model_fields(node)
                    if fields and len(fields) > 1:
                        orm_fields[node.name] = fields
        except Exception:  # noqa: BLE001, S110
            pass
    return orm_fields


def _scan_alembic_columns(project_root: Path) -> set[str]:
    """Extract column names declared in alembic Python migrations."""
    columns: set[str] = set()
    for mig_file in project_root.glob("**/migrations/**/*.py"):
        try:
            content = mig_file.read_text(encoding="utf-8", errors="ignore")
            cols = re.findall(r"sa\.Column\(['\"](\w+)['\"]", content)
            columns.update(cols)
        except Exception:  # noqa: BLE001, S110
            pass
    return columns


def _scan_sql_columns(project_root: Path) -> set[str]:
    """Extract column names declared in raw SQL migration files."""
    columns: set[str] = set()
    for sql_file in project_root.glob("**/*.sql"):
        try:
            content = sql_file.read_text(encoding="utf-8", errors="ignore")
            cols = re.findall(
                r"\b([a-zA-Z0-9_]+)\s+(?:VARCHAR|TEXT|INTEGER|BOOLEAN|TIMESTAMP|DATETIME)\b",
                content,
                re.IGNORECASE,
            )
            for col in cols:
                columns.add(col.lower())
        except Exception:  # noqa: BLE001, S110
            pass
    return columns


def collect_migrations(project_root: Path) -> dict[str, set[str]]:
    """Scan project for migration files and return dictionary of migrated column names."""
    all_cols = _scan_alembic_columns(project_root) | _scan_sql_columns(project_root)
    return {"all": all_cols}


def evaluate_drift(
    models: dict[str, set[str]], migrations: dict[str, set[str]]
) -> list[dict[str, Any]]:
    """Compare ORM model fields against migrated columns to detect missing migrations."""
    drift_issues: list[dict[str, Any]] = []
    migrated = migrations.get("all", set())
    if not migrated:
        return drift_issues

    for model_name, fields in models.items():
        unmigrated = [f for f in fields if f.lower() not in migrated and f != "id"]
        if unmigrated:
            drift_issues.append(
                {
                    "model": model_name,
                    "unmigrated_fields": unmigrated,
                    "details": f"Model '{model_name}' has fields {unmigrated} missing from migrations.",
                }
            )
    return drift_issues
