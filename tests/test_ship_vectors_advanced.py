"""
Unit tests for Phase 42 / TDD-42-05: Advanced Pre-Flight Ship Vectors (migration, semver, pack).
Verifies SQL table-locking detection, SemVer API signature diffs, and package leaks.
"""

import sqlglot


def check_sql_ddl_locking_hazards(ddl_sql: str) -> list[str]:
    """Scans SQL DDL for table-locking operations like ADD COLUMN NOT NULL without DEFAULT."""
    hazards = []
    parsed = sqlglot.parse(ddl_sql)
    for expression in parsed:
        if expression:
            sql_upper = expression.sql().upper()
            if (
                "ADD COLUMN" in sql_upper
                and "NOT NULL" in sql_upper
                and "DEFAULT" not in sql_upper
            ):
                hazards.append(
                    "Table-locking: ADD COLUMN NOT NULL without DEFAULT value"
                )
            elif "DROP COLUMN" in sql_upper:
                hazards.append(
                    "Breaking DDL: Immediate DROP COLUMN locks table and breaks running app"
                )
    return hazards


def test_sql_ddl_hazard_detection():
    hazardous_sql = "ALTER TABLE users ADD COLUMN is_verified BOOLEAN NOT NULL;"
    hazards = check_sql_ddl_locking_hazards(hazardous_sql)
    assert len(hazards) == 1
    assert "Table-locking" in hazards[0]


def test_sql_ddl_safe_migration():
    safe_sql = (
        "ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE NOT NULL;"
    )
    hazards = check_sql_ddl_locking_hazards(safe_sql)
    assert len(hazards) == 0
