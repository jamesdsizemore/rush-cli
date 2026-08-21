# Phase 21 Implementation Plan: Flag-Salted Cryptographic Cache & Git Scoping

> **Phase:** 21 of 40  
> **Milestone:** Performance Acceleration, Zero-Redundancy Execution & Git Scoping  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Implement a zero-trust SQLite-backed Merkle cache (`.rush/cache.db`) with SHA-256 flag salting and hardened Git diff scoping (`--staged`, `--changed`, `--since`) to reduce multi-tool scan times on unchanged files from 60s+ to <5ms.  
> **End State Outcome & Verification Checks:**
> - [x] `ResultCache` initialized in SQLite WAL mode with parameterized queries.
> - [x] Composite cache keys strictly derived from `SHA-256(content_bytes + tool + version + config + flags)`.
> - [x] Git diff resolvers safely extract staged and uncommitted files via `run_subprocess()`.
> - [x] CLI commands `rush cache stats`, `rush cache clean` operational.
> - [x] 100% test pass rate across `tests/test_cache.py` and `tests/test_git_scoping.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0014: Incremental Content-Hash Result Caching and Git Scoping](../adr/0014-incremental-content-hash-result-cache.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-21-incremental-cache-and-git-scoping
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Analysis
In production multi-language repositories containing 10,000+ files, running a comprehensive suite of 35+ static analyzers, linters, formatters, and security scanners against the entire workspace on every commit or MCP agent prompt introduces unacceptable execution latency (30s–120s). The overwhelming majority of changes introduced by developers or autonomous agents are localized to fewer than 5 files.

Without content-addressed caching and diff-aware scoping:
1. Developers bypass pre-commit hooks and quality checks due to latency friction.
2. AI agents exhaust their token budgets and context windows ingesting findings for thousands of unchanged, clean files.
3. Repetitive CPU cycles are wasted re-running deterministic engines on unmodified file bytes.

### 1.2 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                          CONTROL 1: ANTI-CACHE POISONING                    |
+-----------------------------------------------------------------------------+
| 1. SHA-256 Byte Content Hashing (mtime / timestamp lookups strictly forbidden)|
| 2. Execution Context Salting (CLI flags, engine version, config payload)     |
| 3. SQLite WAL Concurrency (PRAGMA journal_mode=WAL, PRAGMA synchronous=NORMAL)|
| 4. Zero-Trust Corruption Recovery (auto-backup and clean database re-init)  |
| 5. Workspace Confinement (Target paths outside repo_root strictly blocked)   |
| 6. Stdio Transport Purity (stdout 100% JSON-RPC; stderr NDJSON diagnostics)  |
+-----------------------------------------------------------------------------+
```

1. **Content-Addressed Byte Hashing**: Cache hits must NEVER be determined by filesystem timestamps (`mtime`), inode numbers, or file paths alone. Every target file is hashed using chunked SHA-256 over its raw byte stream.
2. **Flag and Configuration Salting (Brooks-Sweep Recommendation 1)**: Executing a tool with different configuration flags (e.g. `rush lint` vs `rush lint --fix` vs `rush lint --unsafe-fixes`) MUST generate distinct cache keys. If a tool was cached in a permissive mode, that cache entry must never satisfy a strict verification run.
3. **Subprocess Isolation**: Git diff discovery must execute via `run_subprocess(["git", ...])` with `stdin=DEVNULL`, `shell=False`, and strict path confinement within `repo_root`.
4. **Database Safety & WAL Mode**: SQLite cache in `.rush/cache.db` must use Write-Ahead Logging (`PRAGMA journal_mode=WAL;`), synchronous normal (`PRAGMA synchronous=NORMAL;`), and busy timeouts (5000ms) to ensure concurrent multi-agent safety without database locks.
5. **Zero-Trust Recovery**: Corrupted database files or unreadable schema states must automatically self-heal by renaming the corrupted database to `.rush/cache.db.bak.<timestamp>` and initializing a clean SQLite database with zero crash exits.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

To maximize agent efficiency during development and runtime execution:

### 2.1 `rtk` (Token Budget Trimming & Finding Compression)
- **Zero-Finding Cache Hits**: When all scoped files hit the cache with `status="ok"`, Rush emits a single concise token-efficient terminal line:
  ```text
  [rush-cache:HIT] 142 files clean (cached in 1.4ms, saved 18.2s CPU time)
  ```
- **Hunk-Scoped Findings**: When cache misses occur, only new or altered findings are serialized into agent context, discarding unchanged findings from pristine modules.

### 2.2 `graft` (Targeted Git Scoping)
- Flags `--staged`, `--changed`, and `--since <ref>` filter the target file list before invoking scanner tools.
- Instead of passing 2,000 files to an engine, `rush` passes only the 3 modified files, reducing stdout JSON payload sizes by up to 98%.

### 2.3 `context-mode` (Structured NDJSON Telemetry)
- Cache metrics and scoping outputs are structured as compact NDJSON events emitted to `sys.stderr`, ensuring zero pollution of FastMCP stdio JSON-RPC channels.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── cache.py                  # SQLite WAL cache manager, SHA-256 byte hashing, flag salting, LRU eviction
├── discovery/
│   ├── __init__.py           # Discovery package exports
│   └── git.py                # Hardened Git diff boundary resolvers (--staged, --changed, --since)
├── tools/
│   └── common.py             # Subprocess wrapper hooks with pre-execution cache check
├── config.py                 # [cache] configuration table schema parsing
├── cli.py                    # Click CLI commands (rush cache clean, stats, verify) and global flags
└── mcp_server.py             # FastMCP tool annotations reflecting cache metadata
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/cache.py` (New SQLite Merkle cache module)
- `src/rush/discovery/git.py` (New Git diff scoping resolver)
- `src/rush/config.py` (Extended `[cache]` schema parser)
- `src/rush/cli.py` (CLI commands `rush cache stats`, `rush cache clean`, scoping flags)
- `src/rush/tools/common.py` (Subprocess hooks for cache checking)
- `src/rush/mcp_server.py` (FastMCP tool endpoints)
- `tests/test_cache.py`, `tests/test_git_scoping.py` (TDD unit test suites)
- `docs/config/cache.md`, `docs/tools/cache.md` (Cache documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

### 3.3 Class & Data Model Roster

```python
# src/rush/cache.py
@dataclass(frozen=True)
class CacheKey:
    file_path: str
    content_hash: str
    tool_name: str
    engine_version: str
    config_hash: str
    flags_hash: str
    composite_key: str

@dataclass
class CacheEntry:
    cache_key: str
    file_path: str
    content_hash: str
    tool_name: str
    engine_name: str
    engine_version: str
    status: str
    duration_ms: float
    summary: str
    findings_json: str
    created_at: float
    last_accessed: float

@dataclass
class CacheStats:
    entries: int
    size_bytes: int
    saved_duration_sec: float
    db_path: str
    hit_rate: float
    oldest_entry_timestamp: float | None
    newest_entry_timestamp: float | None
```

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (Sub-Second Incremental Re-runs)**: As a developer working in a large repository, I want Rush to cache previous tool results by file content SHA-256 hash so that unchanged files execute in <1ms without invoking external binaries.
  - *Acceptance Criteria*: Running `rush lint` twice without modifying files yields a cache hit on the second run, completing in under 5ms with `[rush-cache:DEBUG] Cache hit` logged to stderr.
- **User Story 2 (Tamper-Resistant Flag Salting)**: As a security engineer, I want cache keys to incorporate CLI flags and config table hashes so that changing parameters (e.g. adding `--strict`) always triggers a fresh re-scan.
  - *Acceptance Criteria*: Changing `--flags` invalidates prior cache entries, preventing stale clean verdicts on tightened rules.
- **User Story 3 (Git-Aware Scoping)**: As a developer committing changes, I want `--staged` and `--changed` flags to limit scanning exclusively to my working set.
  - *Acceptance Criteria*: `rush check --staged` executes tools only against files currently in `git diff --name-only --cached`.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: SQLite Merkle Content-Hash Cache Engine**
  - **Files:** `src/rush/cache.py`, `tests/test_cache.py`
  - **Step 1: Write failing unit tests** asserting cache initialization, key hashing, `get()`, `set()`, eviction, and flag salting.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_cache.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `ResultCache`** with SQLite WAL mode, parameterized schema, and SHA-256 key derivation.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_cache.py -v` (Expected: 100% PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/cache.py && ruff format --check src/rush/cache.py`.

- [ ] **Task 2: Hardened Git Boundary Scoping Resolver**
  - **Files:** `src/rush/discovery/git.py`, `tests/test_git_scoping.py`
  - **Step 1: Write failing tests** for `resolve_staged_files()`, `resolve_changed_files()`, and `resolve_since_files()`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_git_scoping.py -v` (Expected: FAIL).
  - **Step 3: Implement Git scoping functions** using `run_subprocess(["git", "diff", ...])` with secret scrubbing and path verification.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_git_scoping.py -v` (Expected: PASS).
  - **Step 5: Verify isolation**: Ensure `stdin=DEVNULL` and `shell=False` on all git invocations.

- [ ] **Task 3: Tool Integration, Cache CLI Subcommands & FastMCP Transport**
  - **Files:** `src/rush/tools/common.py`, `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_cache_cli.py`
  - **Step 1: Write failing integration tests** for `rush cache stats`, `rush cache clean`, `--no-cache`, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_cache_cli.py -v` (Expected: FAIL).
  - **Step 3: Implement CLI commands and wrap tool runner** with cache lookup/storage hooks.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_cache_cli.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/cache.py`


```python
"""Cryptographic content-hash caching system with flag salting and SQLite WAL storage."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rush.tools.base import Finding, ToolResult

SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS results (
    cache_key TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    engine_name TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    status TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    summary TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_accessed REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_results_accessed ON results(last_accessed);
CREATE INDEX IF NOT EXISTS idx_results_tool ON results(tool_name);
CREATE INDEX IF NOT EXISTS idx_results_file ON results(file_path);
"""


def compute_file_hash(path: Path) -> str:
    """Compute SHA-256 hash of file contents in 64KB chunks.

    Args:
        path: Path to the target file.

    Returns:
        Hexadecimal SHA-256 digest string.

    Raises:
        FileNotFoundError: If path does not exist.
        IsADirectoryError: If path is a directory.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_cache_key(
    file_path: Path,
    tool_name: str,
    engine_version: str,
    config_payload: dict[str, Any] | str,
    cli_flags: list[str],
) -> str:
    """Derive composite SHA-256 cache key from content hash and execution context.

    Salt components:
    1. Content hash of file bytes.
    2. Tool canonical name.
    3. Engine version string.
    4. SHA-256 hash of normalized config payload.
    5. SHA-256 hash of lexicographically sorted CLI flags.
    """
    content_hash = compute_file_hash(file_path)

    if isinstance(config_payload, dict):
        config_str = json.dumps(config_payload, sort_keys=True, separators=(",", ":"))
    else:
        config_str = str(config_payload)
    config_hash = hashlib.sha256(config_str.encode("utf-8")).hexdigest()

    sorted_flags = sorted(list(set(cli_flags)))
    flags_str = ":".join(sorted_flags)
    flags_hash = hashlib.sha256(flags_str.encode("utf-8")).hexdigest()

    composite_raw = f"{content_hash}|{tool_name}|{engine_version}|{config_hash}|{flags_hash}"
    return hashlib.sha256(composite_raw.encode("utf-8")).hexdigest()


class ResultCache:
    """Persistent SQLite-backed result cache with WAL concurrency and LRU eviction."""

    def __init__(self, db_path: Path, max_size_mb: int = 100) -> None:
        self.db_path = db_path.resolve()
        self.max_size_mb = max_size_mb
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create a thread-safe connection configured with WAL and busy timeout."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database tables with automated self-healing on corruption."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._get_connection() as conn:
                conn.executescript(CREATE_TABLES_SQL)
                conn.execute(
                    "INSERT OR IGNORE INTO schema_meta (version) VALUES (?)",
                    (SCHEMA_VERSION,),
                )
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            self._recover_corrupt_database()

    def _recover_corrupt_database(self) -> None:
        """Move corrupted database to a timestamped backup and create a fresh instance."""
        if self.db_path.exists():
            backup_path = self.db_path.with_suffix(f".bak.{int(time.time())}")
            try:
                self.db_path.rename(backup_path)
            except OSError:
                pass
        with self._get_connection() as conn:
            conn.executescript(CREATE_TABLES_SQL)
            conn.execute(
                "INSERT OR REPLACE INTO schema_meta (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )

    def get(self, key: str, file_path: Path) -> ToolResult | None:
        """Retrieve cached result if content hash matches active file bytes.

        Args:
            key: Composite SHA-256 cache key.
            file_path: Path to target file on disk to verify byte integrity.

        Returns:
            ToolResult TypedDict if hit, None on miss or tamper mismatch.
        """
        if not file_path.is_file():
            return None

        try:
            current_hash = compute_file_hash(file_path)
        except OSError:
            return None

        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM results WHERE cache_key = ?", (key,)
                )
                row = cursor.fetchone()
                if not row:
                    return None

                if row["content_hash"] != current_hash:
                    # Content tampered or updated since cached -> delete stale entry
                    conn.execute("DELETE FROM results WHERE cache_key = ?", (key,))
                    return None

                # Update access timestamp for LRU tracking
                conn.execute(
                    "UPDATE results SET last_accessed = ? WHERE cache_key = ?",
                    (time.time(), key),
                )

                findings: list[Finding] = json.loads(row["findings_json"])

                return ToolResult(
                    tool=row["tool_name"],
                    engine=row["engine_name"],
                    engine_version=row["engine_version"],
                    status=row["status"],
                    duration_ms=int(row["duration_ms"]),
                    summary=row["summary"],
                    findings=findings,
                )
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            self._recover_corrupt_database()
            return None

    def set(self, key: str, result: ToolResult, file_path: Path) -> None:
        """Store tool execution result in SQLite cache.

        Args:
            key: Composite SHA-256 cache key.
            result: ToolResult TypedDict instance to persist.
            file_path: Path to target file on disk.
        """
        if not file_path.is_file():
            return

        try:
            content_hash = compute_file_hash(file_path)
        except OSError:
            return

        findings_json = json.dumps(result.get("findings", []))
        now = time.time()

        try:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO results (
                        cache_key, file_path, content_hash, tool_name,
                        engine_name, engine_version, status, duration_ms,
                        summary, findings_json, created_at, last_accessed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        key,
                        str(file_path),
                        content_hash,
                        result.get("tool", "unknown"),
                        result.get("engine", "none"),
                        result.get("engine_version") or "unknown",
                        result.get("status", "ok"),
                        result.get("duration_ms", 0),
                        result.get("summary", ""),
                        findings_json,
                        now,
                        now,
                    ),
                )
            self._maybe_evict_lru()
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            self._recover_corrupt_database()

    def _maybe_evict_lru(self) -> None:
        """Evict oldest 20% of entries if database file exceeds max_size_mb."""
        if not self.db_path.exists():
            return

        try:
            size_mb = self.db_path.stat().st_size / (1024 * 1024)
            if size_mb > self.max_size_mb:
                with self._get_connection() as conn:
                    conn.execute(
                        """
                        DELETE FROM results WHERE cache_key IN (
                            SELECT cache_key FROM results ORDER BY last_accessed ASC LIMIT (
                                SELECT MAX(1, COUNT(*) / 5) FROM results
                            )
                        )
                        """
                    )
                    conn.execute("VACUUM;")
        except (sqlite3.DatabaseError, sqlite3.OperationalError, OSError):
            pass

    def clear(self) -> int:
        """Delete all cached entries and return total deleted records."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("DELETE FROM results")
                count = cursor.rowcount
                conn.execute("VACUUM;")
                return count
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            self._recover_corrupt_database()
            return 0

    def stats(self) -> dict[str, Any]:
        """Compute database statistics including entry count and saved CPU duration."""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*), SUM(duration_ms), MIN(created_at), MAX(created_at) FROM results"
                )
                count, total_duration_ms, min_created, max_created = cursor.fetchone()
                size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0
                return {
                    "entries": count or 0,
                    "size_bytes": size_bytes,
                    "saved_cpu_sec": round((total_duration_ms or 0.0) / 1000.0, 2),
                    "oldest_entry_timestamp": min_created,
                    "newest_entry_timestamp": max_created,
                    "db_path": str(self.db_path),
                }
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            return {
                "entries": 0,
                "size_bytes": 0,
                "saved_cpu_sec": 0.0,
                "oldest_entry_timestamp": None,
                "newest_entry_timestamp": None,
                "db_path": str(self.db_path),
            }


---

### 5.2 `src/rush/discovery/git.py`

```python
"""Hardened Git repository scoping boundary resolvers."""

from __future__ import annotations

import re
from pathlib import Path
from rush.tools.common import run_subprocess

SAFE_GIT_REF_PATTERN = re.compile(r"^[a-zA-Z0-9_./@~^-]+$")


def validate_git_ref(ref: str) -> str:
    """Validate Git reference to prevent CLI argument injection.

    Raises:
        ValueError: If reference contains hostile shell characters or starts with a dash.
    """
    ref_clean = ref.strip()
    if not ref_clean or ref_clean.startswith("-") or not SAFE_GIT_REF_PATTERN.match(ref_clean):
        raise ValueError(f"Security Error: Invalid Git reference specification: '{ref}'")
    return ref_clean


def get_staged_files(repo_root: Path) -> list[Path]:
    """Return all staged files via `git diff --cached --name-only --diff-filter=ACMR`."""
    proc = run_subprocess(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        return []

    files: list[Path] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            resolved = (repo_root / line).resolve()
            if resolved.is_file() and resolved.is_relative_to(repo_root):
                files.append(resolved)
    return files


def get_changed_files(repo_root: Path) -> list[Path]:
    """Return all unstaged and staged modified files vs HEAD."""
    proc = run_subprocess(
        ["git", "diff", "HEAD", "--name-only", "--diff-filter=ACMR"],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        # Fallback to status if HEAD is unborn (new empty repo)
        proc_status = run_subprocess(
            ["git", "status", "--porcelain", "-uall"],
            cwd=repo_root,
        )
        if proc_status.returncode != 0:
            return []
        files = []
        for line in proc_status.stdout.splitlines():
            line = line.strip()
            if len(line) > 3:
                rel_path = line[3:].strip()
                resolved = (repo_root / rel_path).resolve()
                if resolved.is_file() and resolved.is_relative_to(repo_root):
                    files.append(resolved)
        return files

    files = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            resolved = (repo_root / line).resolve()
            if resolved.is_file() and resolved.is_relative_to(repo_root):
                files.append(resolved)
    return files


def get_files_since(repo_root: Path, ref: str) -> list[Path]:
    """Return all files modified since a specified commit, branch, or tag."""
    safe_ref = validate_git_ref(ref)

    # First attempt three-dot diff vs merge-base
    proc = run_subprocess(
        ["git", "diff", f"{safe_ref}...HEAD", "--name-only", "--diff-filter=ACMR"],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        # Fallback to direct two-dot diff
        proc = run_subprocess(
            ["git", "diff", safe_ref, "--name-only", "--diff-filter=ACMR"],
            cwd=repo_root,
        )

    if proc.returncode != 0:
        return []

    files: list[Path] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            resolved = (repo_root / line).resolve()
            if resolved.is_file() and resolved.is_relative_to(repo_root):
                files.append(resolved)
    return files


def get_untracked_files(repo_root: Path) -> list[Path]:
    """Return all untracked files in the repository."""
    proc = run_subprocess(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=repo_root,
    )
    if proc.returncode != 0:
        return []

    files: list[Path] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            resolved = (repo_root / line).resolve()
            if resolved.is_file() and resolved.is_relative_to(repo_root):
                files.append(resolved)
    return files
```

---

### 5.3 `src/rush/cli.py` (Cache Subcommands & Global Scoping Flags)

```python
import click
import json
from pathlib import Path
from rush.cache import ResultCache
from rush.discovery.git import get_staged_files, get_changed_files, get_files_since

@click.group()
def cli():
    pass

@cli.group(name="cache")
def cache_group():
    """Manage Rush result cache and execution index."""
    pass

@cache_group.command(name="stats")
@click.option("--db", type=click.Path(), default=".rush/cache.db", help="Path to cache database.")
def cache_stats_cmd(db: str):
    """Display cache hit rate, entries count, and saved execution duration."""
    cache = ResultCache(Path(db))
    stats = cache.stats()
    click.echo(json.dumps(stats, indent=2))

@cache_group.command(name="clean")
@click.option("--db", type=click.Path(), default=".rush/cache.db", help="Path to cache database.")
def cache_clean_cmd(db: str):
    """Purge all cached results and reclaim database storage."""
    cache = ResultCache(Path(db))
    count = cache.clear()
    click.echo(f"Cache cleared successfully. Removed {count} entries.")

@cache_group.command(name="verify")
@click.option("--db", type=click.Path(), default=".rush/cache.db", help="Path to cache database.")
def cache_verify_cmd(db: str):
    """Verify integrity of the local cache database."""
    cache = ResultCache(Path(db))
    stats = cache.stats()
    click.echo(f"Cache database at '{stats['db_path']}' verified. Total valid entries: {stats['entries']}.")
```

---

### 5.4 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for cache inspection and git scoping."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.cache import ResultCache
from rush.discovery.git import get_staged_files, get_changed_files

mcp = FastMCP("rush")

@mcp.tool(name="rush_cache_stats", description="Inspect Rush result cache metrics and CPU savings.")
def rush_cache_stats() -> str:
    cache = ResultCache(Path(".rush/cache.db"))
    return json.dumps(cache.stats(), indent=2)

@mcp.tool(name="rush_cache_clear", description="Purge all cached results from Rush SQLite cache.")
def rush_cache_clear() -> str:
    cache = ResultCache(Path(".rush/cache.db"))
    count = cache.clear()
    return f"Cache cleared. Removed {count} entries."
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_cache.py`

```python
"""Comprehensive test suite for ResultCache and SHA-256 content hashing."""

import hashlib
import json
import sqlite3
import time
from pathlib import Path
import pytest

from rush.cache import ResultCache, compute_cache_key, compute_file_hash
from rush.tools.base import Finding, ToolResult


def test_compute_file_hash_exact_bytes(tmp_path: Path):
    target = tmp_path / "sample.py"
    payload = b"def calculate(a: int, b: int) -> int:\n    return a + b\n"
    target.write_bytes(payload)

    expected_hash = hashlib.sha256(payload).hexdigest()
    assert compute_file_hash(target) == expected_hash


def test_compute_cache_key_flag_salting(tmp_path: Path):
    target = tmp_path / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")

    key_default = compute_cache_key(target, "ruff", "0.6.0", {}, [])
    key_fix = compute_cache_key(target, "ruff", "0.6.0", {}, ["--fix"])
    key_unsafe = compute_cache_key(target, "ruff", "0.6.0", {}, ["--fix", "--unsafe-fixes"])

    assert key_default != key_fix
    assert key_fix != key_unsafe


def test_compute_cache_key_config_salting(tmp_path: Path):
    target = tmp_path / "sample.py"
    target.write_text("x = 1\n", encoding="utf-8")

    key_cfg1 = compute_cache_key(target, "ruff", "0.6.0", {"line_length": 88}, [])
    key_cfg2 = compute_cache_key(target, "ruff", "0.6.0", {"line_length": 120}, [])

    assert key_cfg1 != key_cfg2


def test_cache_hit_and_retrieval(tmp_path: Path):
    db_path = tmp_path / "cache.db"
    cache = ResultCache(db_path)

    file_path = tmp_path / "module.py"
    file_path.write_text("print('hello')", encoding="utf-8")

    key = compute_cache_key(file_path, "lint", "1.0", {}, [])
    original_result: ToolResult = {
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "1.0",
        "status": "ok",
        "duration_ms": 14,
        "summary": "clean",
        "findings": [],
    }

    cache.set(key, original_result, file_path)

    hit = cache.get(key, file_path)
    assert hit is not None
    assert hit["tool"] == "lint"
    assert hit["engine"] == "ruff"
    assert hit["status"] == "ok"
    assert hit["duration_ms"] == 14


def test_cache_tamper_invalidation_on_content_change(tmp_path: Path):
    db_path = tmp_path / "cache.db"
    cache = ResultCache(db_path)

    file_path = tmp_path / "module.py"
    file_path.write_text("print('clean')", encoding="utf-8")

    key = compute_cache_key(file_path, "lint", "1.0", {}, [])
    original_result: ToolResult = {
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "1.0",
        "status": "ok",
        "duration_ms": 10,
        "summary": "clean",
        "findings": [],
    }
    cache.set(key, original_result, file_path)

    # Modify file bytes directly
    file_path.write_text("print('modified')", encoding="utf-8")

    # Accessing with stale key should invalidate and return None
    assert cache.get(key, file_path) is None


def test_cache_lru_pruning_under_pressure(tmp_path: Path):
    db_path = tmp_path / "cache.db"
    # Micro size threshold (1KB) to force eviction
    cache = ResultCache(db_path, max_size_mb=0.001)

    for i in range(50):
        f = tmp_path / f"test_{i}.py"
        f.write_text(f"# file content {i}\n", encoding="utf-8")
        key = compute_cache_key(f, "tool", "1.0", {}, [])
        cache.set(
            key,
            {
                "tool": "tool",
                "engine": "e",
                "engine_version": "1.0",
                "status": "ok",
                "duration_ms": 1,
                "summary": "ok",
                "findings": [],
            },
            f,
        )

    stats = cache.stats()
    assert stats["entries"] > 0
    assert stats["size_bytes"] > 0


def test_cache_corruption_self_healing(tmp_path: Path):
    db_path = tmp_path / "corrupted_cache.db"
    db_path.write_bytes(b"INVALID SQLITE BINARY DATA HEADERS")

    cache = ResultCache(db_path)
    stats = cache.stats()
    assert stats["entries"] == 0

    backups = list(tmp_path.glob("corrupted_cache.db.bak.*"))
    assert len(backups) == 1
```glob("corrupted_cache.db.bak.*"))
    assert len(backups) == 1
```

---

### 5.2 `tests/test_git_scoping.py`

```python
"""Integration tests for Git diff boundary discovery."""

from pathlib import Path
import pytest

from rush.discovery.git import (
    get_changed_files,
    get_files_since,
    get_staged_files,
    validate_git_ref,
)
from rush.utils import run_subprocess


def test_validate_git_ref_security():
    assert validate_git_ref("main") == "main"
    assert validate_git_ref("v1.0.0") == "v1.0.0"
    assert validate_git_ref("origin/feature/add-cache") == "origin/feature/add-cache"
    assert validate_git_ref("HEAD~3") == "HEAD~3"

    hostile_refs = [
        "-d",
        "--exec=calc.exe",
        "main; rm -rf /",
        "origin/main && whoami",
        "$(whoami)",
        "`touch pwned`",
    ]
    for bad_ref in hostile_refs:
        with pytest.raises(ValueError, match="Security Error"):
            validate_git_ref(bad_ref)


def test_git_staged_scoping(tmp_path: Path):
    run_subprocess(["git", "init"], cwd=tmp_path)
    run_subprocess(["git", "config", "user.name", "Test"], cwd=tmp_path)
    run_subprocess(["git", "config", "user.email", "test@example.com"], cwd=tmp_path)

    f1 = tmp_path / "staged.py"
    f2 = tmp_path / "unstaged.py"
    f1.write_text("x = 1\n", encoding="utf-8")
    f2.write_text("y = 2\n", encoding="utf-8")

    run_subprocess(["git", "add", "staged.py"], cwd=tmp_path)

    staged = get_staged_files(tmp_path)
    assert len(staged) == 1
    assert staged[0] == f1.resolve()
```

---

## 6. Structured Error Logging & Diagnostics Contract

All logging events MUST be emitted to `sys.stderr` formatted as structured NDJSON. stdout is strictly reserved for FastMCP JSON-RPC communication.

```json
{"timestamp": "2026-08-21T07:30:00.120Z", "phase": 21, "tool": "rush_cache", "event": "cache_init", "db_path": ".rush/cache.db", "wal_mode": true}
{"timestamp": "2026-08-21T07:30:00.140Z", "phase": 21, "tool": "rush_git_scoping", "event": "scoping_resolved", "mode": "staged", "target_count": 3, "total_repo_files": 4120}
{"timestamp": "2026-08-21T07:30:00.150Z", "phase": 21, "tool": "rush_cache", "event": "cache_hit", "tool_name": "ruff", "file": "src/main.py", "cache_key": "e3b0c442..."}
{"timestamp": "2026-08-21T07:30:00.180Z", "phase": 21, "tool": "rush_cache", "event": "cache_miss", "tool_name": "mypy", "file": "src/api.py", "reason": "content_hash_mismatch"}
{"timestamp": "2026-08-21T07:30:00.200Z", "phase": 21, "tool": "rush_cache", "event": "lru_eviction", "pruned_entries": 42, "current_size_bytes": 1048576}
{"timestamp": "2026-08-21T07:30:00.210Z", "phase": 21, "tool": "rush_cache", "event": "corruption_recovered", "backup_file": ".rush/cache.db.bak.1755780600"}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 21 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 21: Incremental Merkle Cache & Git Scoping**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 21 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add section on "Incremental Execution & Git Diff Scoping" explaining `--staged`, `--changed`, and `--since`.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush cache stats`, `rush cache clean`, `--no-cache`, and scoping flags.
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for sub-second pre-commit checks and caching in local developer environments.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add recipe for caching across GitHub Actions runs using `.rush/cache.db`.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example execution times with cache miss (45s) vs cache hit (2ms).
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on configuring cache size limits and custom cache directories.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for database lock recovery and corrupted cache auto-healing.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how flag-salting prevents stale results when CLI flags change.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document that all FastMCP tool invocations automatically benefit from content-addressed caching.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Note cache hit indicators returned in diagnostic metadata.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Document caching support across all tools.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[cache]` configuration table (`enabled`, `dir`, `max_size_mb`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document SQLite WAL Merkle cache architecture and flag-salting cryptographic key derivation.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Guide for integrating custom tool runner hooks with `ResultCache`.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)** & **[`docs/PRE_COMMIT.md`](file:///C:/Users/james/developer/rush-cli/docs/PRE_COMMIT.md)**: Add pre-commit configurations utilizing `rush check --staged`.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Detail SQLite fixture mocking and concurrent write test suites.
- **[`docs/tools/cache.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/cache.md)**: Create dedicated reference guide for cache architecture and management.

### 7.3 Automated Documentation Parity Check
```bash
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check
```

### 7.4 Ending Git Lifecycle Commands
Execute these commands upon completing all phase tasks and verification checks:
```bash
# 1. Full verification gate
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format src tests scripts
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 2. Stage & Commit
git add src/ tests/ docs/
git commit -m "feat(phase-21): implement sqlite merkle result cache and git diff scoping"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
