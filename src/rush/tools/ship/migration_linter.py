"""Zero-downtime SQL table-lock migration hazard linter via sqlglot."""

from pathlib import Path
from typing import Any

import sqlglot


class MigrationLinter:
    """Audits SQL migrations for dangerous exclusive table locks."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def check_sql(self, sql_content: str) -> list[str]:
        hazards: list[str] = []
        try:
            expressions = sqlglot.parse(sql_content)
        except Exception as e:  # noqa: BLE001
            return [f"SQL syntax error in migration: {e}"]

        for expression in expressions:
            if expression:
                sql_upper = expression.sql().upper()
                if (
                    "ADD COLUMN" in sql_upper
                    and "NOT NULL" in sql_upper
                    and "DEFAULT" not in sql_upper
                ):
                    hazards.append(
                        "Table-locking hazard: ADD COLUMN NOT NULL without DEFAULT value."
                    )
                elif "DROP COLUMN" in sql_upper:
                    hazards.append(
                        "Breaking DDL: DROP COLUMN immediately causes downtime for old app replicas."
                    )
                elif "RENAME TABLE" in sql_upper:
                    hazards.append(
                        "Breaking DDL: RENAME TABLE invalidates active connection pools."
                    )
        return hazards

    def lint_migrations(self, migrations_dir: Path | None = None) -> dict[str, Any]:
        target = migrations_dir or (self.project_root / "migrations")
        findings: list[dict[str, Any]] = []

        if target.exists() and target.is_dir():
            for sql_file in target.glob("**/*.sql"):
                content = sql_file.read_text(encoding="utf-8", errors="ignore")
                hazards = self.check_sql(content)
                if hazards:
                    findings.append(
                        {
                            "file": str(sql_file.relative_to(self.project_root)),
                            "hazards": hazards,
                        }
                    )

        return {
            "passed": len(findings) == 0,
            "findings_count": len(findings),
            "findings": findings,
        }
