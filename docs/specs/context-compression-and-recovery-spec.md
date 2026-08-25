# Specification: Context Compression & Restoration (CCR)

## P3 omission contract

When the continuity envelope cannot meet a requested token budget, the implementation must store the redacted omitted packed value through the existing CCR store and expose its stable content hash in recovery metadata. A missing hash is `not_found`; recovery must never fabricate content or promote it to instruction authority.

## 1. Overview
CCR stores explicitly supplied local chunks in `.rush/cache/ccr.db`. `rush context retrieve HASH --json` returns a canonical receipt with recovered content or structured `skipped`/`not_found`; it does not promise automatic capture, eviction policy, or provider delivery.

## 2. Restoration Tag Format
```html
<!-- ccr:chunk:SHA256_HASH -->
```

## 3. Retrieval Protocol
When an agent or developer requires the uncompressed verbatim content, it retrieves the original chunk using its SHA-256 fingerprint:
* **CLI**: `rush context retrieve <SHA256_HASH>`
* **FastMCP**: `rush_context_retrieve(chunk_hash="SHA256_HASH")`

## 4. Storage Architecture
* **Location**: `.rush/cache/ccr.db`
* **Table Schema**:
  ```sql
  CREATE TABLE chunks (
      hash TEXT PRIMARY KEY,
      content TEXT NOT NULL,
      byte_size INTEGER NOT NULL,
      created_at INTEGER NOT NULL,
      last_accessed_at INTEGER NOT NULL
  );
  ```
* **Eviction Policy**: Least Recently Used (LRU) with configurable size cap.
