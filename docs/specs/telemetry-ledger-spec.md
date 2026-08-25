# Specification: Token Economy Telemetry Ledger

## 1. Overview
`TelemetryStore` records only events explicitly supplied by Rush callers in local `.rush/telemetry/tokens.db`; it is not telemetry sent off-machine and its derived cost estimate is not a provider invoice.

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
