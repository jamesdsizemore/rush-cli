"""Tests for Phase 57 Invocation Cache Policy and Deterministic Gating.

Contracts:
- T-57.15 (R-005): Cryptographic key derivation, eligible decision, and bypass contracts.
- T-57.16: Cache key binds every context and target identity field (11 mutations).
- T-57.17: Missing identity returns bypass without key (strictly zero fallback salt).
- T-57.18: Mutation of artifact build ID, permissions, or target state causes cache miss.
- T-57.19: Explicit cache_policy="bypass" executes zero cache reads and zero cache writes.
- T-57.20: Cache set sanitizes secrets and validates ToolResultV1 contract.
- T-57.21: Cache get re-sanitizes raw entries and re-validates ToolResultV1.
- T-57.22: Only manifest pure operations use cache; impure operations bypass cache.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from rush.cache import ResultCache
from rush.contracts.results import ToolResultV1, ValidationErrorV1
from rush.invocation import (
    CacheDecision,
    InvocationContext,
    PhysicalTarget,
)
from rush.invocation.cache_policy import decide_cache
from rush.invocation.executor import InvocationExecutor


def _create_valid_context(
    workspace_root: Path,
    *,
    operation_id: str = "lint",
    cache_policy: str = "eligible",
    tool_revision: str = "rev-1.0.0",
    normalizer_revision: str = "norm-1.0.0",
    artifact_build_identity: str = "build-abc-123",
    effective_config_digest: str = "deadbeef" * 8,
    environment_digest: str = "feedface" * 8,
    permissions: tuple[str, ...] = ("read", "cache_write"),
    ordered_args: tuple[str, ...] = ("--verbose",),
    targets: tuple[PhysicalTarget, ...] | None = None,
) -> InvocationContext:
    if targets is None:
        targets = (
            PhysicalTarget(
                relative_path=Path("src/main.py"),
                state="present",
                capability="read",
                provenance="explicit",
                content_hash="a" * 64,
            ),
        )
    return InvocationContext(
        workspace_root=workspace_root,
        transport="cli",
        operation_id=operation_id,
        operation_kind="tool",
        targets=targets,
        effective_config_digest=effective_config_digest,
        permissions=permissions,
        ordered_args=ordered_args,
        declared_ignored_inputs=(),
        cache_policy=cache_policy,  # type: ignore[arg-type]
        artifact_build_identity=artifact_build_identity,
        tool_revision=tool_revision,
        normalizer_revision=normalizer_revision,
        environment_digest=environment_digest,
        request_id="req-12345",
    )


def _create_valid_tool_result(
    *,
    tool: str = "lint",
    status: str = "ok",
    summary: str = "clean execution",
) -> ToolResultV1:
    return ToolResultV1(
        schema_version="1.0.0",
        tool=tool,
        engine="ruff",
        engine_version="0.16.3",
        status=status,  # type: ignore[arg-type]
        duration_ms=42,
        summary=summary,
        findings=[],
        raw={"exit_code": 0},
        extensions={},
    )


def test_cache_identity_and_bypass_contracts(tmp_path: Path) -> None:
    """T-57.15 (R-005): Asserts complete cryptographic key derivation and proper bypass handling."""
    ctx = _create_valid_context(tmp_path)

    # 1. Eligible pure operation produces 64-character SHA-256 cache key
    decision = decide_cache(ctx, pure=True)
    assert isinstance(decision, CacheDecision)
    assert decision.decision == "eligible"
    assert decision.reason == "eligible"
    assert decision.cache_key is not None
    assert len(decision.cache_key) == 64
    assert int(decision.cache_key, 16) > 0  # Valid hex
    assert isinstance(decision.key_payload, dict)
    assert decision.key_payload["operation_id"] == "lint"
    assert decision.key_payload["artifact_build_identity"] == "build-abc-123"

    # 2. Impure operation returns bypass with no key
    decision_impure = decide_cache(ctx, pure=False)
    assert decision_impure.decision == "bypass"
    assert decision_impure.reason == "operation_not_pure"
    assert decision_impure.cache_key is None

    # 3. Explicit cache_policy="bypass" returns bypass with no key
    ctx_bypass = replace(ctx, cache_policy="bypass")
    decision_explicit = decide_cache(ctx_bypass, pure=True)
    assert decision_explicit.decision == "bypass"
    assert decision_explicit.reason == "explicit_bypass"
    assert decision_explicit.cache_key is None


def test_cache_key_binds_every_context_and_target_identity(tmp_path: Path) -> None:
    """T-57.16: Mutates each context/target field individually; asserts derived cache key changes on every single mutation."""
    base_ctx = _create_valid_context(tmp_path)
    base_decision = decide_cache(base_ctx, pure=True)
    assert base_decision.decision == "eligible"
    base_key = base_decision.cache_key
    assert base_key is not None

    mutations: list[tuple[str, InvocationContext]] = [
        # 1. operation_id
        ("operation_id", replace(base_ctx, operation_id="format")),
        # 2. ordered_args
        ("ordered_args", replace(base_ctx, ordered_args=("--verbose", "--diff"))),
        # 3. effective_config_digest
        (
            "effective_config_digest",
            replace(base_ctx, effective_config_digest="11" * 32),
        ),
        # 4. permissions
        ("permissions", replace(base_ctx, permissions=("read",))),
        # 5. artifact_build_identity
        (
            "artifact_build_identity",
            replace(base_ctx, artifact_build_identity="build-xyz-999"),
        ),
        # 6. tool_revision
        ("tool_revision", replace(base_ctx, tool_revision="rev-2.0.0")),
        # 7. normalizer_revision
        ("normalizer_revision", replace(base_ctx, normalizer_revision="norm-2.0.0")),
        # 8. environment_digest
        ("environment_digest", replace(base_ctx, environment_digest="22" * 32)),
        # 9. target relative_path
        (
            "target relative_path",
            replace(
                base_ctx,
                targets=(
                    PhysicalTarget(
                        relative_path=Path("src/other.py"),
                        state="present",
                        capability="read",
                        provenance="explicit",
                        content_hash="a" * 64,
                    ),
                ),
            ),
        ),
        # 10. target content_hash
        (
            "target content_hash",
            replace(
                base_ctx,
                targets=(
                    PhysicalTarget(
                        relative_path=Path("src/main.py"),
                        state="present",
                        capability="read",
                        provenance="explicit",
                        content_hash="b" * 64,
                    ),
                ),
            ),
        ),
        # 11. target state
        (
            "target state",
            replace(
                base_ctx,
                targets=(
                    PhysicalTarget(
                        relative_path=Path("src/main.py"),
                        state="deleted",
                        capability="read",
                        provenance="explicit",
                        content_hash="",
                    ),
                ),
            ),
        ),
    ]

    assert len(mutations) == 11, "Must verify exactly 11 distinct identity mutations"

    for field_name, mutated_ctx in mutations:
        mutated_decision = decide_cache(mutated_ctx, pure=True)
        assert mutated_decision.decision == "eligible", (
            f"Mutated context for '{field_name}' must remain eligible"
        )
        mutated_key = mutated_decision.cache_key
        assert mutated_key != base_key, (
            f"Cache key failed to change when mutating field: {field_name}"
        )


def test_missing_identity_returns_bypass_without_key(tmp_path: Path) -> None:
    """T-57.17: Omits a required identity field; asserts decide_cache() returns decision='bypass', cache_key=None."""
    base_ctx = _create_valid_context(tmp_path)

    # 1. Empty tool_revision
    ctx_no_tool_rev = replace(base_ctx, tool_revision="")
    dec_no_tool_rev = decide_cache(ctx_no_tool_rev, pure=True)
    assert dec_no_tool_rev.decision == "bypass"
    assert dec_no_tool_rev.cache_key is None
    assert "missing_identity" in dec_no_tool_rev.reason
    assert "tool_revision" in dec_no_tool_rev.reason

    # 2. Empty environment_digest
    ctx_no_env = replace(base_ctx, environment_digest="")
    dec_no_env = decide_cache(ctx_no_env, pure=True)
    assert dec_no_env.decision == "bypass"
    assert dec_no_env.cache_key is None
    assert "missing_identity" in dec_no_env.reason
    assert "environment_digest" in dec_no_env.reason

    # 3. Target with state='present' but missing content_hash
    ctx_no_hash = replace(
        base_ctx,
        targets=(
            PhysicalTarget(
                relative_path=Path("src/main.py"),
                state="present",
                capability="read",
                provenance="explicit",
                content_hash="",  # Missing content hash for present target
            ),
        ),
    )
    dec_no_hash = decide_cache(ctx_no_hash, pure=True)
    assert dec_no_hash.decision == "bypass"
    assert dec_no_hash.cache_key is None
    assert "missing_identity" in dec_no_hash.reason

    # 4. Empty artifact_build_identity
    ctx_no_build = replace(base_ctx, artifact_build_identity="")
    dec_no_build = decide_cache(ctx_no_build, pure=True)
    assert dec_no_build.decision == "bypass"
    assert dec_no_build.cache_key is None
    assert "missing_identity" in dec_no_build.reason


def test_artifact_behavior_config_permission_target_mutation_misses(
    tmp_path: Path,
) -> None:
    """T-57.18: Simulates cache lookup after mutating build ID, permission, or target state; asserts cache miss."""
    cache = ResultCache(db_path=tmp_path / "cache.db")
    ctx_base = _create_valid_context(tmp_path)
    dec_base = decide_cache(ctx_base, pure=True)
    assert dec_base.cache_key is not None

    result = _create_valid_tool_result(summary="cached success")
    cache.set(dec_base.cache_key, result)

    # Initial lookup hits
    hit = cache.get(dec_base.cache_key)
    assert hit is not None
    assert hit.summary == "cached success"

    # Mutate artifact_build_identity -> miss
    ctx_build = replace(ctx_base, artifact_build_identity="build-changed-456")
    dec_build = decide_cache(ctx_build, pure=True)
    assert dec_build.cache_key is not None
    assert dec_build.cache_key != dec_base.cache_key
    assert cache.get(dec_build.cache_key) is None

    # Mutate permissions -> miss
    ctx_perm = replace(ctx_base, permissions=("read",))
    dec_perm = decide_cache(ctx_perm, pure=True)
    assert dec_perm.cache_key is not None
    assert dec_perm.cache_key != dec_base.cache_key
    assert cache.get(dec_perm.cache_key) is None

    # Mutate target state -> miss
    ctx_target = replace(
        ctx_base,
        targets=(
            PhysicalTarget(
                relative_path=Path("src/main.py"),
                state="deleted",
                capability="read",
                provenance="explicit",
                content_hash="",
            ),
        ),
    )
    dec_target = decide_cache(ctx_target, pure=True)
    assert dec_target.cache_key is not None
    assert dec_target.cache_key != dec_base.cache_key
    assert cache.get(dec_target.cache_key) is None


def test_no_cache_performs_no_read_or_write(tmp_path: Path) -> None:
    """T-57.19: Invokes executor with context.cache_policy='bypass'; asserts spy verifies strictly 0 calls to cache read and 0 calls to cache write."""
    mock_cache = MagicMock()
    executor = InvocationExecutor(cache=mock_cache)

    expected_result = _create_valid_tool_result()
    executor.register("lint", lambda: expected_result, pure=True)

    ctx_bypass = _create_valid_context(tmp_path, cache_policy="bypass")
    res = executor.execute(ctx_bypass)

    assert res == expected_result
    # Strictly zero cache reads and zero cache writes
    assert mock_cache.get.call_count == 0
    assert mock_cache.set.call_count == 0


def test_cache_set_requires_sanitized_valid_tool_result(tmp_path: Path) -> None:
    """T-57.20: Stores result in cache; asserts result payload is sanitized via rush.safety.redactor.sanitize_value and validated via rush.contracts.results.validate_tool_result."""
    cache = ResultCache(db_path=tmp_path / "cache.db")
    key = "a" * 64
    secret_token = "Bearer sk-proj-1234567890abcdefghijklmnopqrstuvwxyz"

    # 1. Unsanitized secret in result is sanitized before storage
    unsanitized_result = {
        "schema_version": "1.0.0",
        "tool": "lint",
        "engine": "ruff",
        "engine_version": "0.16.3",
        "status": "ok",
        "duration_ms": 10,
        "summary": f"Execution finished with auth header: {secret_token}",
        "findings": [],
        "raw": None,
        "extensions": {},
    }
    cache.set(key, unsanitized_result)

    with sqlite3.connect(str(tmp_path / "cache.db")) as conn:
        row = conn.execute(
            "SELECT result_json FROM cache_entries WHERE key = ?", (key,)
        ).fetchone()
        assert row is not None
        db_json = row[0]
        # Must not store raw secret
        assert secret_token not in db_json
        # Must contain redacted sentinel
        assert "[REDACTED" in db_json

    # 2. Invalid result fails validation fail-closed
    invalid_result = {
        "schema_version": "1.0.0",
        "tool": "lint",
        "status": "not_a_valid_status",
        "duration_ms": -1,
        "summary": "invalid",
        "findings": [],
    }
    with pytest.raises(ValidationErrorV1):
        cache.set("b" * 64, invalid_result)


def test_cache_get_resanitizes_and_revalidates(tmp_path: Path) -> None:
    """T-57.21: Injects unsanitized or tampered result directly into cache storage; asserts cache.get() re-sanitizes and re-validates ToolResultV1 before returning."""
    cache = ResultCache(db_path=tmp_path / "cache.db")
    key = "c" * 64
    secret = "sk-ant-api03-abcdef1234567890abcdef1234567890"

    # Inject unsanitized payload directly into SQLite table
    raw_payload = json.dumps(
        {
            "schema_version": "1.0.0",
            "tool": "security",
            "engine": "trufflehog",
            "engine_version": "3.0.0",
            "status": "fail",
            "duration_ms": 120,
            "summary": f"Detected key {secret} in config",
            "findings": [],
            "raw": None,
            "extensions": {},
        }
    )
    with cache._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cache_entries (key, file_path, tool_name, engine, engine_version, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (key, "src/config.py", "security", "trufflehog", "3.0.0", raw_payload),
        )
        conn.commit()

    # cache.get() must re-sanitize and return validated ToolResultV1
    retrieved = cache.get(key)
    assert retrieved is not None
    assert isinstance(retrieved, ToolResultV1)
    assert secret not in retrieved.summary
    assert "[REDACTED" in retrieved.summary
    assert retrieved.tool == "security"
    assert retrieved.status == "fail"

    # Tampered corrupt schema entry fails closed (returns None)
    tampered_key = "d" * 64
    tampered_payload = json.dumps(
        {
            "schema_version": "1.0.0",
            "tool": "security",
            "status": "corrupted_nonexistent_status",
            "duration_ms": 10,
            "summary": "corrupted",
            "findings": [],
        }
    )
    with cache._get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cache_entries (key, file_path, tool_name, engine, engine_version, result_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tampered_key, "", "security", None, None, tampered_payload),
        )
        conn.commit()

    tampered_retrieved = cache.get(tampered_key)
    assert tampered_retrieved is None


def test_only_manifest_pure_operation_uses_cache(tmp_path: Path) -> None:
    """T-57.22: Registers operation with pure=False; asserts decide_cache() returns decision='bypass' and executor bypasses cache."""
    mock_cache = MagicMock()
    mock_cache.get.return_value = None
    executor = InvocationExecutor(cache=mock_cache)

    result_impure = _create_valid_tool_result(summary="impure executed")
    executor.register("db_migrate", lambda: result_impure, pure=False)

    ctx_impure = _create_valid_context(tmp_path, operation_id="db_migrate")

    # Purity check via decide_cache
    dec = decide_cache(ctx_impure, pure=False)
    assert dec.decision == "bypass"
    assert dec.reason == "operation_not_pure"
    assert dec.cache_key is None

    # Executor execution with pure=False never accesses cache
    res = executor.execute(ctx_impure)
    assert res == result_impure
    assert mock_cache.get.call_count == 0
    assert mock_cache.set.call_count == 0

    # In contrast, pure operation checks and sets cache
    result_pure = _create_valid_tool_result(summary="pure executed")
    executor.register("pure_check", lambda: result_pure, pure=True)
    ctx_pure = _create_valid_context(tmp_path, operation_id="pure_check")

    dec_pure = decide_cache(ctx_pure, pure=True)
    assert dec_pure.decision == "eligible"
    assert dec_pure.cache_key is not None

    res_pure = executor.execute(ctx_pure)
    assert res_pure == result_pure
    assert mock_cache.get.call_count == 1
    assert mock_cache.set.call_count == 1
