# Specification: Database Migration Schema Drift Auditor

## 1. Overview
`DbDriftAuditor` (`src/rush/tools/db_drift.py`) statically inspects ORM data models (SQLAlchemy, SQLModel) and compares them against SQL migration scripts, flagging unmigrated columns, altered constraints, and missing tables.

## 2. CLI & FastMCP Reference
* `rush db-drift`
* `rush_db_drift()`
