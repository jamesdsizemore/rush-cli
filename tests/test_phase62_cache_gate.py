"""Phase 62 P62.1 contract tests: token-savings cache front-end for pack_context().

Covers T-62.01, T-62.02, T-62.18, T-62.19, T-62.20 (phase-62-memory-integration-layer-plan.md §7).
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from rush.codegraph.context_packer import ContextPacker
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.token_economy.memory_cache_gate import check_memory_before_pack
from rush.tools.continuity import SessionContinuityTool


def _write_target(tmp_path: Path) -> Path:
    target = tmp_path / "service.py"
    target.write_text(
        "def func():\n    return 1\n\n\ndef other():\n    return 2\n",
        encoding="utf-8",
    )
    return target


def _seed_cache_row(tmp_path: Path, target: Path, *, packed_text: str) -> None:
    TypedArtifactStore(tmp_path).write(
        MemoryArtifact(
            id="cached-1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={
                "target_file": str(target),
                "target_symbol": "func",
                "max_tokens": 1_000_000,
                "tokens": 7,
                "packed_text": packed_text,
                "cache_key": "service.py:func",
            },
            source="context_pack",
            created_at=time.time(),
            symbol_ref="service.py::func",
            content_hash=MerkleInvalidator(tmp_path).hash_content(target.read_text()),
        )
    )


def test_cache_hit_returns_stored_content_without_new_pack(tmp_path: Path):
    target = _write_target(tmp_path)
    _seed_cache_row(tmp_path, target, packed_text="CACHED PACKED TEXT")

    with patch.object(ContextPacker, "pack") as spy_pack:
        result = SessionContinuityTool().run(
            tmp_path,
            operation="context_pack",
            context_path="service.py",
            target_symbol="func",
            token_budget=1_000_000,
        )

    spy_pack.assert_not_called()
    assert result["status"] == "ok"
    assert result["raw"]["packed_text"] == "CACHED PACKED TEXT"
    assert result["raw"]["tokens"] == 7


def test_cache_miss_falls_through_to_pack(tmp_path: Path):
    _write_target(tmp_path)

    original_pack = ContextPacker.pack
    with patch.object(ContextPacker, "pack", autospec=True) as spy_pack:
        spy_pack.side_effect = original_pack
        result = SessionContinuityTool().run(
            tmp_path,
            operation="context_pack",
            context_path="service.py",
            target_symbol="func",
            token_budget=1_000_000,
        )

    spy_pack.assert_called_once()
    assert result["status"] == "ok"
    assert result["raw"]["tokens"] > 0


def test_cache_hit_with_failed_recall_defense_falls_through_to_pack(tmp_path: Path):
    target = _write_target(tmp_path)
    _seed_cache_row(tmp_path, target, packed_text="\u202eTROJAN PAYLOAD")

    original_pack = ContextPacker.pack
    with patch.object(ContextPacker, "pack", autospec=True) as spy_pack:
        spy_pack.side_effect = original_pack
        result = SessionContinuityTool().run(
            tmp_path,
            operation="context_pack",
            context_path="service.py",
            target_symbol="func",
            token_budget=1_000_000,
        )

    spy_pack.assert_called_once()
    assert result["status"] == "ok"
    assert result["raw"]["tokens"] > 0


def test_cache_miss_write_back_requires_cache_write_permission(tmp_path: Path):
    _write_target(tmp_path)

    with patch.object(TypedArtifactStore, "write") as spy_write:
        result = SessionContinuityTool().run(
            tmp_path,
            operation="context_pack",
            context_path="service.py",
            target_symbol="func",
            token_budget=1_000_000,
            permissions=ExecutionPermissions(cache_write=False),
        )

    spy_write.assert_not_called()
    assert result["status"] == "ok"
    assert result["raw"]["tokens"] > 0


def test_cache_miss_write_back_uses_derived_trust_tier_and_exact_key(tmp_path: Path):
    _write_target(tmp_path)

    result = SessionContinuityTool().run(
        tmp_path,
        operation="context_pack",
        context_path="service.py",
        target_symbol="func",
        token_budget=1_000_000,
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert result["status"] == "ok"

    store = TypedArtifactStore(tmp_path)
    written = store.search("domain_knowledge", '"service.py:func"')
    assert len(written) == 1
    assert written[0].trust_tier == "DERIVED"
    assert written[0].content["cache_key"] == "service.py:func"

    # A second, different (context_path, target_symbol) pair must still miss —
    # not a fuzzy/partial FTS match against the row just written above.
    gate = check_memory_before_pack("service.py", "other", project_root=tmp_path)
    assert gate.hit is False
