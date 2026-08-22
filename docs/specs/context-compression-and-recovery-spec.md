# Specification: Context Compression & Restoration (CCR)

## 1. Overview
Context Compression & Restoration (CCR) provides deterministic, lossless caching for large tool outputs, code chunks, and execution logs. Large outputs are persisted in a local SQLite LRU chunk store (`.rush/cache/ccr.db`) and replaced in LLM context windows with lightweight restoration tags.

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
