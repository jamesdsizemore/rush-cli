# Specification: Database Migration Schema Drift Auditor

Status: planned — complete table/column identity, migration ordering and incomplete-evidence handling are owned by [P64-15](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-15--ground-schema-drift-and-type-guards-f1617). Current implementation loses table identity and can treat missing migrations as synchronized (F16); its current success result does not prove schema agreement.

## 1. Overview
`DbDriftAuditor` (`src/rush/tools/db_drift.py`) statically inspects ORM data models (SQLAlchemy, SQLModel) and compares them against SQL migration scripts, flagging unmigrated columns, altered constraints, and missing tables.

## 2. CLI & FastMCP Reference
* `rush db-drift`
* `rush_db_drift()`
