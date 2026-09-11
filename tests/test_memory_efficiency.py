"""MC04 §9.0 duplicate-retrieval-work removal and real cost accounting
(docs/phase-plans/MC04.md).

Covers: `memory_cache_gate.py`/`review.py` sharing one `defended_recall()` query instead of a
`search()`-then-`recall()` pair, a request-local `SourceValidationMemo` so N candidates that
share one backing source file are hashed/API-diffed once (not once per row), a complete cache
identity (budget/tokenizer/scope) on `pack_context()`'s cache, and `TelemetryStore` recording
real (deduplicated, opt-in-gated) retrieval/expansion/packing/handoff costs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

from rush.continuity.context import pack_context
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.retrieval import defended_recall
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.token_economy.memory_cache_gate import check_memory_before_pack
from rush.token_economy.telemetry import TelemetryStore
from rush.tools.api_diff import ApiDiffer
from rush.tools.memory import MemoryTool
from rush.tools.review import ReviewTool

GRANTED = ExecutionPermissions(cache_write=True)


def _write_artifact(
    store: TypedArtifactStore,
    artifact_id: str,
    *,
    subject: str,
    source: str,
    content: dict,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject=subject,
            trust_tier="DERIVED",
            content=content,
            source=source,
            created_at=time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
        )
    )


def test_cache_and_review_do_one_defended_search(tmp_path: Path) -> None:
    """Two cache rows, then two failure citations, each pair sharing one source file: each
    consumer's own request issues exactly one `search_candidates()` query (never the old
    `search()`-then-`recall()` double query), and returned evidence stays correct."""
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n", encoding="utf-8")
    file_hash = MerkleInvalidator(tmp_path).hash_content(target.read_text())
    store = TypedArtifactStore(tmp_path)
    for artifact_id in ("cache-a", "cache-b"):
        _write_artifact(
            store,
            artifact_id,
            subject="domain_knowledge",
            source="context_pack",
            content={
                "cache_key": "module.py:hello",
                "packed_text": "cached",
                "tokens": 2,
            },
            symbol_ref="module.py::hello",
            content_hash=file_hash,
        )

    original_search_candidates = TypedArtifactStore.search_candidates
    original_hash_content = MerkleInvalidator.hash_content
    with (
        patch.object(
            TypedArtifactStore,
            "search_candidates",
            autospec=True,
            side_effect=original_search_candidates,
        ) as spy_search,
        patch.object(
            MerkleInvalidator,
            "hash_content",
            autospec=True,
            side_effect=original_hash_content,
        ) as spy_hash,
    ):
        gate = check_memory_before_pack("module.py", "hello", project_root=tmp_path)

    assert gate.hit is True
    assert gate.content["packed_text"] == "cached"
    assert spy_search.call_count == 1
    assert spy_hash.call_count == 1

    review_target = tmp_path / "mod.py"
    review_target.write_text("def thing():\n    return 1\n", encoding="utf-8")
    review_hash = MerkleInvalidator(tmp_path).hash_content(review_target.read_text())
    for artifact_id in ("failure-a", "failure-b"):
        _write_artifact(
            store,
            artifact_id,
            subject="failure",
            source="migration:failure_ledger",
            content={"target_file": "mod.py", "fix_commit": f"commit-{artifact_id}"},
            symbol_ref="mod.py::thing",
            content_hash=review_hash,
        )

    with (
        patch.object(
            TypedArtifactStore,
            "search_candidates",
            autospec=True,
            side_effect=original_search_candidates,
        ) as spy_search2,
        patch.object(
            MerkleInvalidator,
            "hash_content",
            autospec=True,
            side_effect=original_hash_content,
        ) as spy_hash2,
    ):
        result = ReviewTool().run(review_target)

    citations = [
        f for f in result["findings"] if f.get("rule") == "memory-failure-citation"
    ]
    assert len(citations) == 2
    # One query per subject searched (failure, architectural_decision) against one target.
    assert spy_search2.call_count == 2
    # Both failure rows share the same backing file: hashed once, not once per citation.
    assert spy_hash2.call_count == 1


def test_shared_source_validated_once_per_request(tmp_path: Path) -> None:
    """Three candidates sharing one backing source file: `defended_recall()` hashes and
    API-diffs that file exactly once per call, not once per candidate."""
    target = tmp_path / "shared.py"
    target.write_text("def shared():\n    return 1\n", encoding="utf-8")
    file_hash = MerkleInvalidator(tmp_path).hash_content(target.read_text())
    store = TypedArtifactStore(tmp_path)
    for artifact_id in ("s1", "s2", "s3"):
        _write_artifact(
            store,
            artifact_id,
            subject="domain_knowledge",
            source="context_pack",
            content={"needle": "shared marker", "id_tag": artifact_id},
            symbol_ref="shared.py::shared",
            content_hash=file_hash,
        )

    original_hash_content = MerkleInvalidator.hash_content
    original_diff_symbol = ApiDiffer.diff_symbol
    with (
        patch.object(
            MerkleInvalidator,
            "hash_content",
            autospec=True,
            side_effect=original_hash_content,
        ) as spy_hash,
        patch.object(
            ApiDiffer, "diff_symbol", autospec=True, side_effect=original_diff_symbol
        ) as spy_diff,
    ):
        results = defended_recall(
            store, "domain_knowledge", "shared marker", ["context_pack"]
        )

    assert {artifact.id for artifact in results} == {"s1", "s2", "s3"}
    assert all(not artifact.stale for artifact in results)
    assert spy_hash.call_count == 1
    assert spy_diff.call_count == 1


def test_same_size_source_edit_invalidates_next_request(tmp_path: Path) -> None:
    """A same-length source edit still changes the content hash: the next request misses."""
    target = tmp_path / "module.py"
    original_body = "def hello():\n    return 1\n"
    edited_body = "def hello():\n    return 2\n"
    assert len(original_body) == len(edited_body)
    target.write_text(original_body, encoding="utf-8")

    first = pack_context(
        time.monotonic(), tmp_path, "module.py", "hello", 10_000, GRANTED
    )
    assert "return 1" in json.dumps(first)
    assert check_memory_before_pack("module.py", "hello", project_root=tmp_path).hit

    target.write_text(edited_body, encoding="utf-8")
    gate = check_memory_before_pack("module.py", "hello", project_root=tmp_path)
    assert gate.hit is False

    second = pack_context(
        time.monotonic(), tmp_path, "module.py", "hello", 10_000, GRANTED
    )
    assert "return 2" in json.dumps(second)


def test_cache_key_changes_with_budget_scope_and_tokenizer(tmp_path: Path) -> None:
    """A cached pack is only a hit under the exact budget/scope/tokenizer it was written
    under; any one of those changing misses even though `context_path`/`target_symbol`
    (the literal `cache_key`) are unchanged."""
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n", encoding="utf-8")
    pack_context(time.monotonic(), tmp_path, "module.py", "hello", 10_000, GRANTED)

    assert (
        check_memory_before_pack(
            "module.py",
            "hello",
            project_root=tmp_path,
            token_budget=10_000,
            encoding="cl100k_base",
        ).hit
        is True
    )
    assert (
        check_memory_before_pack(
            "module.py",
            "hello",
            project_root=tmp_path,
            token_budget=1,
            encoding="cl100k_base",
        ).hit
        is False
    )
    assert (
        check_memory_before_pack(
            "module.py",
            "hello",
            project_root=tmp_path,
            token_budget=10_000,
            encoding="o200k_base",
        ).hit
        is False
    )
    assert (
        check_memory_before_pack(
            "module.py", "hello", "skill_pattern", project_root=tmp_path
        ).hit
        is False
    )


def test_producer_hash_not_replaced_by_later_read(tmp_path: Path) -> None:
    """The `content_hash` a producer (`write_cache_fill()`) stored never gets overwritten by
    a later read's own (possibly different) source hash — even when that later read correctly
    rejects the row as stale."""
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n", encoding="utf-8")
    pack_context(time.monotonic(), tmp_path, "module.py", "hello", 10_000, GRANTED)

    store = TypedArtifactStore(tmp_path)
    written = store.search("domain_knowledge", '"module.py:hello"')
    assert len(written) == 1
    producer_hash = written[0].content_hash
    assert producer_hash

    target.write_text("def hello():\n    return 2\n", encoding="utf-8")
    gate = check_memory_before_pack("module.py", "hello", project_root=tmp_path)
    assert gate.hit is False

    unchanged = store.search("domain_knowledge", '"module.py:hello"')
    assert len(unchanged) == 1
    assert unchanged[0].content_hash == producer_hash


def test_expansion_and_handoff_costs_are_not_double_counted(tmp_path: Path) -> None:
    """Distinct expansion events sum correctly with a handoff event; replaying an
    already-recorded `(request_id, event_id)` pair never inflates the total, and persistence
    requires `opt_in`/`cache_write`."""
    telemetry = TelemetryStore(tmp_path)

    assert (
        telemetry.record_memory_event(
            "expansion", 10, request_id="req-1", event_id="expand-a", opt_in=True
        )
        is True
    )
    assert (
        telemetry.record_memory_event(
            "expansion", 20, request_id="req-1", event_id="expand-b", opt_in=True
        )
        is True
    )
    assert telemetry.get_memory_event_total(kind="expansion") == 30

    assert (
        telemetry.record_memory_event(
            "handoff", 5, request_id="req-1", event_id="handoff-a", opt_in=True
        )
        is True
    )
    assert telemetry.get_memory_event_total() == 35

    # Replay of an already-recorded pair, even with a different token count, is a no-op.
    assert (
        telemetry.record_memory_event(
            "expansion", 999, request_id="req-1", event_id="expand-a", opt_in=True
        )
        is False
    )
    assert telemetry.get_memory_event_total(kind="expansion") == 30
    assert telemetry.get_memory_event_total() == 35

    # Neither opt_in nor cache_write: nothing persists.
    assert (
        telemetry.record_memory_event(
            "packing", 100, request_id="req-2", event_id="pack-a"
        )
        is False
    )
    assert telemetry.get_memory_event_total() == 35


def test_read_only_recall_never_persists_telemetry(tmp_path: Path) -> None:
    """A pure defended lookup (cache-gate miss/hit check, review citations) never touches
    `TelemetryStore` at all; only real produced work (a cache miss's actual pack) is metered,
    and a subsequent cache hit records nothing further."""
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n", encoding="utf-8")

    check_memory_before_pack("module.py", "hello", project_root=tmp_path)
    ReviewTool().run(target)
    assert not (tmp_path / ".rush" / "telemetry").exists()

    pack_context(time.monotonic(), tmp_path, "module.py", "hello", 10_000, GRANTED)
    total_after_miss = TelemetryStore(tmp_path).get_memory_event_total()
    assert total_after_miss > 0

    gate = check_memory_before_pack("module.py", "hello", project_root=tmp_path)
    assert gate.hit is True
    assert TelemetryStore(tmp_path).get_memory_event_total() == total_after_miss


def test_cache_view_dimension_is_compared_when_supplied(tmp_path: Path) -> None:
    """T105's second finding: `check_memory_before_pack()`'s `view` param (symmetric with
    `token_budget`/`encoding`) rejects a hit when the caller's view disagrees with the stored
    `cache_identity.view`. Currently inert in production since `pack_context()` doesn't pass
    it, but the comparison itself is real."""
    target = tmp_path / "module.py"
    target.write_text("def hello():\n    return 1\n", encoding="utf-8")
    pack_context(
        time.monotonic(), tmp_path, "module.py", "hello", 10_000, GRANTED, as_v1=True
    )

    assert check_memory_before_pack(
        "module.py",
        "hello",
        project_root=tmp_path,
        token_budget=10_000,
        encoding="cl100k_base",
        view="v1",
    ).hit
    assert not check_memory_before_pack(
        "module.py",
        "hello",
        project_root=tmp_path,
        token_budget=10_000,
        encoding="cl100k_base",
        view="v2",
    ).hit
    assert check_memory_before_pack(
        "module.py",
        "hello",
        project_root=tmp_path,
        token_budget=10_000,
        encoding="cl100k_base",
    ).hit


def test_memory_tool_recall_and_expand_record_real_telemetry(tmp_path: Path) -> None:
    """T105's first finding: MemoryTool's compact `recall` and `expand` operations now
    record real `retrieval`/`expansion` TelemetryStore events when the caller grants
    `cache_write` (mirrors every other real telemetry call site). No grant means no
    telemetry, and the response shape is unchanged either way."""
    tool = MemoryTool()
    written = tool.run(
        tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"text": "needle alpha"},
        source="allowed",
        permissions=GRANTED,
    )
    artifact_id = written["raw"]["id"]
    version = written["raw"]["artifact_version"]

    ungranted = tool.run(
        tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
        request={"view": "compact"},
    )
    assert ungranted["raw"]["code"] == "OK"
    assert not (tmp_path / ".rush" / "telemetry").exists()

    granted_recall = tool.run(
        tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
        request={"view": "compact"},
        permissions=GRANTED,
    )
    assert granted_recall["raw"]["code"] == "OK"
    assert TelemetryStore(tmp_path).get_memory_event_total(kind="retrieval") > 0

    expanded = tool.run(
        tmp_path,
        operation="expand",
        session_allowlist=["allowed"],
        request={"id": artifact_id, "version": version},
        permissions=GRANTED,
    )
    assert expanded["raw"]["code"] == "OK"
    assert TelemetryStore(tmp_path).get_memory_event_total(kind="expansion") > 0
