# Phase 21 Implementation Plan: Flag-Salted Cryptographic Cache & Git Scoping

> **Phase:** 21 of 30  
> **Milestone:** Performance Acceleration & Git-Aware Scoping  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0 / v0.3.0  
> **ADR Reference:** [ADR-0014: Incremental Content-Hash Result Caching and Git Scoping](../adr/0014-incremental-content-hash-result-cache.md)

---

## 1. Objective & Scope

Eliminate redundant scanner invocations on unchanged files in large repositories by introducing an incremental SQLite cache (`.rush/cache.db`) and Git diff scoping flags (`--staged`, `--changed`, `--since <ref>`). 

Incorporate **Control 1 (Anti-Cache Poisoning)** and **Brooks-Sweep Recommendation 1 (CLI Flag Salting)** to ensure cache keys are cryptographically derived from file byte contents, tool names, engine versions, configuration table hashes, and sorted CLI execution flags.

---

## 2. File Rosters

### Allowed & Target Files
- `src/rush/cache.py` (New: SQLite cache manager)
- `src/rush/cli.py` (Modified: CLI flags and `rush cache` command)
- `src/rush/tools/common.py` (Modified: caching hooks around `run_subprocess` and `ToolResult`)
- `src/rush/config.py` (Modified: `[cache]` configuration table)
- `src/rush/logging.py` (Modified: `[rush-cache:LEVEL]` structured logger)

### Test & Fixture Files
- `tests/test_cache.py` (New: Cache hit/miss/tamper unit tests)
- `tests/test_git_scoping.py` (New: Git diff file filtering tests)
- `tests/fixtures/cache/sample_findings.json` (New: Mock fixture)

---

## 3. Test-Driven Development (TDD) Workflow

### 3.1 RED Phase (Author Tests First)
Write `tests/test_cache.py` and `tests/test_git_scoping.py` testing:
1. `test_compute_file_hash_sha256()`: Validates exact SHA-256 byte hashing.
2. `test_cache_key_salting_with_cli_flags()`: Asserts `--allow-slow` generates a distinct cache key from standard invocation.
3. `test_cache_tamper_detection()`: Asserts that modifying file content without changing `mtime` invalidates the cached result.
4. `test_cache_parameterized_queries()`: Asserts tool names with quotes or SQL injection payloads do not compromise SQLite.
5. `test_git_scoping_staged()`: Asserts `--staged` filters target files strictly to `git diff --cached --name-only`.
6. `test_git_scoping_changed()`: Asserts `--changed` filters target files to modified uncommitted files.

### 3.2 GREEN Phase (Implementation)
Implement `src/rush/cache.py`, update `cli.py`, `config.py`, and `common.py`.

### 3.3 REFACTOR Phase
Ensure SQLite database uses WAL mode (`PRAGMA journal_mode=WAL`), connection pooling is thread-safe, and cache stats are cleanly reported.

---

## 4. Step-by-Step Implementation Tasks

### Task 21.1: Core Cache Manager (`src/rush/cache.py`)
Implement the `ResultCache` class with SQLite storage:
```python
from __future__ import annotations
import hashlib
import sqlite3
from pathlib import Path
from rush.tools.base import ToolResult

def compute_file_hash(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def compute_cache_key(
    file_path: Path,
    tool_name: str,
    engine_version: str,
    config_hash: str,
    cli_flags: list[str],
) -> str:
    content_hash = compute_file_hash(file_path)
    flags_salt = ":".join(sorted(cli_flags))
    payload = f"{content_hash}|{tool_name}|{engine_version}|{config_hash}|{flags_salt}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

class ResultCache:
    def __init__(self, db_path: Path) -> None: ...
    def get(self, key: str) -> ToolResult | None: ...
    def set(self, key: str, result: ToolResult, file_path: Path) -> None: ...
    def clear(self) -> int: ...
    def stats(self) -> dict[str, int | float]: ...
```

### Task 21.2: Git Scoping Utilities (`src/rush/discovery/git.py`)
Implement git boundary resolvers:
```python
def get_staged_files(repo_root: Path) -> list[Path]: ...
def get_changed_files(repo_root: Path) -> list[Path]: ...
def get_files_since(repo_root: Path, ref: str) -> list[Path]: ...
```

### Task 21.3: CLI Flag Integration (`src/rush/cli.py`)
Add global flags:
- `--no-cache`: Bypass and do not write to result cache.
- `--staged`: Restrict scan scope to Git staged files.
- `--changed`: Restrict scan scope to modified uncommitted files.
- `--since <ref>`: Restrict scan scope to files changed since Git reference.
- `rush cache clean`: Evict all cached results.
- `rush cache stats`: Display cache size, hit rate, and entry count.

### Task 21.4: Error Logging & Tagging
Log cache operations to `stderr`:
- `[rush-cache:INFO] Cache HIT for {tool} on {file}`
- `[rush-cache:INFO] Cache MISS for {tool} on {file}`
- `[rush-cache:WARN] Invalidation triggered by modified CLI flags: {flags}`
- `[rush-cache:WARN] Database integrity check failed, purging cache`

---

## 5. Mandatory Documentation Synchronization

During development, update and synchronize:
1. `docs/reference/cli-reference.md` & `docs/CLI_REFERENCE.md` (Document `rush cache`, `--no-cache`, `--staged`, `--changed`, `--since`).
2. `docs/reference/configuration-reference.md` & `docs/CONFIG_SCHEMA.md` (Document `[cache]` configuration table).
3. `docs/USER_GUIDE.md` & `docs/user-guide/everyday-workflow.md` (Document fast incremental scanning with `--staged`).
4. Run `.venv/Scripts/python.exe scripts/sync_docs.py --update` to synchronize all 149+ docs.

---

## 6. Verification Commands & Exit Criteria

```bash
# 1. Run unit and adversarial tests
.venv/Scripts/python.exe -m pytest tests/test_cache.py tests/test_git_scoping.py -v

# 2. Run full pytest regression suite
.venv/Scripts/python.exe -m pytest tests/ -q

# 3. Verify documentation parity across tree
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 4. Lint and format
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 5. Verify Graft code graph
graft --dir .hermes/graft build . && graft --dir .hermes/graft check .
```
