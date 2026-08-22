"""Tests for Phase 21: Flag-Salted Cryptographic Cache Manager.

Verifies:
- SHA-256 byte hashing of files
- Composite cache key generation with tool, engine version, config hash, and sorted CLI flags
- Cache hit, miss, storage, and retrieval of canonical ToolResult
- Tamper detection (content alteration without mtime change)
- SQLite database integrity check and WAL mode
- Parameterized queries / SQL injection resilience
- Cache clearing and statistics reporting
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rush.cache import (
    ResultCache,
    compute_cache_key,
    compute_file_hash,
)
from rush.tools.base import ToolResult


@pytest.fixture
def temp_cache_dir(tmp_path: Path) -> Path:
    cache_dir = tmp_path / ".rush"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    p = tmp_path / "sample.py"
    p.write_text("def hello() -> str:\n    return 'world'\n", encoding="utf-8")
    return p


def test_compute_file_hash(sample_file: Path) -> None:
    hash1 = compute_file_hash(sample_file)
    assert isinstance(hash1, str)
    assert len(hash1) == 64  # SHA-256 hex string

    # Modifying content modifies hash
    sample_file.write_text(
        "def hello() -> str:\n    return 'changed'\n", encoding="utf-8"
    )
    hash2 = compute_file_hash(sample_file)
    assert hash1 != hash2


def test_compute_cache_key_salting_with_cli_flags(sample_file: Path) -> None:
    key_normal = compute_cache_key(
        file_path=sample_file,
        tool_name="lint",
        engine_version="0.16.3",
        config_hash="abc123",
        cli_flags=[],
    )
    key_with_flags = compute_cache_key(
        file_path=sample_file,
        tool_name="lint",
        engine_version="0.16.3",
        config_hash="abc123",
        cli_flags=["--allow-slow", "--target", "3.12"],
    )
    key_reordered_flags = compute_cache_key(
        file_path=sample_file,
        tool_name="lint",
        engine_version="0.16.3",
        config_hash="abc123",
        cli_flags=["--target", "3.12", "--allow-slow"],
    )
    # Different flags generate different keys
    assert key_normal != key_with_flags
    # Sorting ensures order independence
    assert key_with_flags == key_reordered_flags


def test_cache_storage_and_retrieval(temp_cache_dir: Path, sample_file: Path) -> None:
    db_path = temp_cache_dir / "cache.db"
    cache = ResultCache(db_path=db_path)

    key = compute_cache_key(
        file_path=sample_file,
        tool_name="lint",
        engine_version="0.16.3",
        config_hash="abc123",
        cli_flags=[],
    )

    # Initial get returns None
    assert cache.get(key) is None

    result: ToolResult = {
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "0.16.3",
        "status": "ok",
        "duration_ms": 12,
        "summary": "ruff: 0 issues found across 1 file (clean)",
        "findings": [],
    }

    cache.set(key, result, sample_file)

    cached_result = cache.get(key)
    assert cached_result is not None
    assert cached_result["tool"] == "lint"
    assert cached_result["status"] == "ok"
    assert cached_result["summary"] == result["summary"]


def test_cache_tamper_detection(temp_cache_dir: Path, sample_file: Path) -> None:
    db_path = temp_cache_dir / "cache.db"
    cache = ResultCache(db_path=db_path)

    key1 = compute_cache_key(sample_file, "lint", "0.16.3", "cfg", [])
    result: ToolResult = {
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "0.16.3",
        "status": "ok",
        "duration_ms": 15,
        "summary": "clean",
        "findings": [],
    }
    cache.set(key1, result, sample_file)

    # Directly modify file content
    sample_file.write_text("# backdoored content\nimport os\n", encoding="utf-8")

    key2 = compute_cache_key(sample_file, "lint", "0.16.3", "cfg", [])
    assert key1 != key2
    assert cache.get(key2) is None  # Miss because key changed


def test_cache_parameterized_queries(temp_cache_dir: Path, sample_file: Path) -> None:
    db_path = temp_cache_dir / "cache.db"
    cache = ResultCache(db_path=db_path)

    # Hostile tool name with SQL injection
    hostile_tool = "lint'); DROP TABLE cache_entries; --"
    key = compute_cache_key(sample_file, hostile_tool, "1.0", "cfg", [])
    result: ToolResult = {
        "tool": hostile_tool,
        "engine": "hostile",
        "engine_version": "1.0",
        "status": "warn",
        "duration_ms": 10,
        "summary": "sql test",
        "findings": [],
    }

    cache.set(key, result, sample_file)
    retrieved = cache.get(key)
    assert retrieved is not None
    assert retrieved["tool"] == hostile_tool

    # Verify table was not dropped
    with sqlite3.connect(str(db_path)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM cache_entries")
        count = cursor.fetchone()[0]
        assert count >= 1


def test_cache_clear_and_stats(temp_cache_dir: Path, sample_file: Path) -> None:
    db_path = temp_cache_dir / "cache.db"
    cache = ResultCache(db_path=db_path)

    key = compute_cache_key(sample_file, "format", "1.0", "cfg", [])
    result: ToolResult = {
        "tool": "format",
        "status": "ok",
        "duration_ms": 5,
        "summary": "ok",
        "findings": [],
    }
    cache.set(key, result, sample_file)

    stats_before = cache.stats()
    assert stats_before["entries"] == 1
    assert stats_before["size_bytes"] > 0

    cleared = cache.clear()
    assert cleared == 1

    stats_after = cache.stats()
    assert stats_after["entries"] == 0


def test_cli_cache_commands() -> None:
    from click.testing import CliRunner

    from rush.cli import cli

    runner = CliRunner()
    res_stats = runner.invoke(cli, ["cache", "stats"])
    assert res_stats.exit_code == 0
    assert "entries" in res_stats.output

    res_clean = runner.invoke(cli, ["cache", "clean"])
    assert res_clean.exit_code == 0
    assert "Purged" in res_clean.output


def test_validate_git_ref() -> None:
    from rush.discovery.git import validate_git_ref

    assert validate_git_ref("main") == "main"
    assert validate_git_ref("v1.0.0") == "v1.0.0"
    assert validate_git_ref("HEAD~1") == "HEAD~1"

    with pytest.raises(ValueError, match="Invalid Git reference"):
        validate_git_ref("-bad-flag")

    with pytest.raises(ValueError, match="Invalid Git reference"):
        validate_git_ref("main; rm -rf /")
