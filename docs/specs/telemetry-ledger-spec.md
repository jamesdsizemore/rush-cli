# Specification: Token Economy Telemetry Ledger

## 1. Overview
The `TelemetryStore` (`src/rush/token_economy/telemetry.py`) records all token distillation, AST skeletonization, and TOON serialization events in a persistent SQLite database (`.rush/telemetry/tokens.db`).

## 2. Table Schema
```sql
CREATE TABLE IF NOT EXISTS token_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp INTEGER NOT NULL,
    tool_name TEXT NOT NULL,
    raw_tokens INTEGER NOT NULL,
    compressed_tokens INTEGER NOT NULL,
    duration_ms REAL NOT NULL
);
```

## 3. Metrics Computed
* `net_tokens_saved = sum(raw_tokens) - sum(compressed_tokens)`
* `compression_ratio = net_tokens_saved / sum(raw_tokens)`
* `dollar_savings_est = net_tokens_saved * $0.000003` (Blended model pricing)
