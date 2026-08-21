# Phase 21 Implementation Plan: Flag-Salted Cryptographic Cache & Git Scoping

> **Phase:** 21 of 40  
> **Milestone:** Performance Acceleration & Git-Aware Scoping  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **ADR References:** [ADR-0014: Incremental Content-Hash Result Caching and Git Scoping](../adr/0014-incremental-content-hash-result-cache.md), [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`

---

## 1. Objective & Scope

Eliminate redundant scanner invocations on unchanged files in large repositories by introducing an incremental SQLite cache (`.rush/cache.db`) and Git diff scoping flags (`--staged`, `--changed`, `--since <ref>`). 

To prevent cache poisoning and non-deterministic cache hits, cache keys are cryptographically derived from file byte contents (SHA-256), tool names, engine versions, configuration table hashes, and sorted CLI execution flags.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Cache Hit Pruning)**: When a file has a valid cache hit, skip scanner execution entirely and emit a 1-line cached summary, reducing agent processing time and token consumption to near zero.
- **`graft` (Targeted Git Scoping)**: Use Git diff boundaries (`--staged`, `--changed`) to filter target file lists down to modified files only, avoiding scanning thousands of untouched files.
- **`context-mode` (Compact Cache Stats)**: `rush cache stats` outputs a concise JSON / NDJSON summary of cache hits, misses, and byte savings.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/cache.py` (New: SQLite WAL cache manager with flag salting and anti-tamper verification)
- `src/rush/discovery/git.py` (New: Git diff boundary resolvers for `--staged`, `--changed`, `--since`)
- `src/rush/tools/common.py` (Modified: Caching wrapper hooks around `run_subprocess` and `ToolResult`)
- `src/rush/config.py` (Modified: `[cache]` configuration table parsing)
- `src/rush/cli.py` (Modified: CLI flags `--no-cache`, `--staged`, `--changed`, `--since` and `rush cache`)
- `src/rush/mcp_server.py` (Modified: Expose cache status to FastMCP tools)

### Test & Fixture Files
- `tests/test_cache.py` (New: Cache hit/miss, tampering detection, WAL mode, concurrency)
- `tests/test_git_scoping.py` (New: Git diff filtering for staged, changed, and historical refs)
- `tests/fixtures/cache/sample_findings.json` (New: Cache serialization fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_cache.py
def test_compute_file_hash_sha256(tmp_path):
    f = tmp_path / "hello.py"
    f.write_text("print('hello')\n", encoding="utf-8")
    h = compute_file_hash(f)
    assert len(h) == 64
    assert h == hashlib.sha256(b"print('hello')\n").hexdigest()

def test_cache_key_salting_with_cli_flags(tmp_path):
    f = tmp_path / "sample.py"
    f.write_text("x = 1\n", encoding="utf-8")
    k1 = compute_cache_key(f, "ruff", "0.6.0", "cfg1", ["--fix"])
    k2 = compute_cache_key(f, "ruff", "0.6.0", "cfg1", ["--fix", "--unsafe"])
    assert k1 != k2

def test_cache_tamper_detection(tmp_path):
    db_path = tmp_path / "cache.db"
    cache = ResultCache(db_path)
    target = tmp_path / "target.py"
    target.write_text("a = 1", encoding="utf-8")
    
    key = compute_cache_key(target, "lint", "1.0", "c", [])
    cache.set(key, ToolResult(tool="lint", engine="ruff", status="passed"), target)
    
    # Tamper with file content without invalidating key directly
    target.write_text("a = 2 (modified)", encoding="utf-8")
    new_key = compute_cache_key(target, "lint", "1.0", "c", [])
    assert cache.get(new_key) is None

# tests/test_git_scoping.py
def test_git_scoping_staged(tmp_path):
    repo = init_git_repo(tmp_path)
    staged_file = tmp_path / "staged.py"
    staged_file.write_text("y = 2", encoding="utf-8")
    stage_file(repo, "staged.py")
    
    files = get_staged_files(tmp_path)
    assert len(files) == 1
    assert files[0].name == "staged.py"
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/cache.py` and `src/rush/discovery/git.py`. Integrate into `src/rush/tools/common.py` and `src/rush/cli.py`.

### 4.3 REFACTOR Phase
Ensure SQLite database uses WAL mode (`PRAGMA journal_mode=WAL`), connection pooling is thread-safe, and cache stats are cleanly reported.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:15:00Z", "phase": 21, "tool": "rush_cache", "event": "cache_hit", "tool_name": "ruff", "file": "src/main.py"}
{"timestamp": "2026-08-21T07:15:01Z", "phase": 21, "tool": "rush_cache", "event": "cache_miss", "tool_name": "mypy", "file": "src/main.py", "reason": "content_hash_changed"}
{"timestamp": "2026-08-21T07:15:02Z", "phase": 21, "tool": "rush_git_scoping", "event": "scope_resolved", "flag": "--staged", "files_selected": 3, "files_skipped": 142}
```

---

## 6. Step-by-Step Task Specifications

### Task 21.1: SQLite WAL Result Cache Manager (`src/rush/cache.py`)
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

### Task 21.2: Git Diff Boundary Resolvers (`src/rush/discovery/git.py`)
Implement `get_staged_files()`, `get_changed_files()`, and `get_files_since()` using `run_subprocess(["git", ...])`.

### Task 21.3: CLI Flags & Management (`src/rush/cli.py`)
Add global flags: `--no-cache`, `--staged`, `--changed`, `--since <ref>` and subcommands `rush cache clean`, `rush cache stats`.

### Task 21.4: FastMCP Transport Integration (`src/rush/mcp_server.py`)
Add cache metadata into FastMCP tool responses (`cached: true/false`).

---

## 7. Semantic Drift Review & Verification Gate

1. **Subprocess Isolation**: Git diff discovery must execute with `stdin=DEVNULL`, `shell=False`.
2. **Deterministic Invalidation**: Altering CLI flags (e.g. adding `--unsafe`) must generate a distinct cache key.
3. **Doc Parity**: Run `python scripts/sync_docs.py --update` and verify zero drift.
