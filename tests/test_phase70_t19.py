"""Phase 70 T19 test matrix: attribute actual memory reads and writes.

Binding design: `.scratch/phase-70-design-gate/W3-T18-T22.md` `## T19` section
(required behavior B1-B8, code map, design, resolutions R19.1-R19.7, R19.D) plus
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` T19 packet.

The brief names `tests/test_phase70_memory_visibility.py::test_t19_memory_attribution`
as the home for this matrix; per the task packet it is written here instead, keeping
that exact test name. Every case below is real production code (real
`InvocationExecutor`, real `TypedArtifactStore`, real tool classes) -- never a
hardcoded stand-in result.

T19 is not implemented in this worktree. None of `record_observation`'s return,
`write_cache_fill`'s committed row, `CacheGateResult.revision`/`.source`,
`build_continuity_result(memory=...)`, or any `metadata.memory` /
`extensions.metadata.memory` attachment exists yet, so most cases are genuinely
RED (the feature is simply absent). A few cases assert a negative
("no receipt", "absence") that is already true today for the trivial reason that
nothing ever attaches a receipt -- those are keep-green guards, not RED cases;
each is commented `# keep-green:` at its assertion. See the report handed back
to the orchestrator for the case-by-case RED/keep-green accounting.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from rush.cli_support import rendering
from rush.config import load_config
from rush.continuity.context import pack_context
from rush.contracts.results import adapt_legacy_tool_result, validate_tool_result
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.mcp_support.tool_registry import (
    build_memory_bridge_handler,
    make_tool_wrapper,
)
from rush.memory.handoff import HandoffError, acknowledge_readback, prepare_handoff
from rush.memory.relations import add_relation
from rush.memory.retrieval import recall_page
from rush.memory.store import (
    MemoryArtifact,
    TypedArtifactStore,
    compute_content_signature,
)
from rush.permissions import ExecutionPermissions
from rush.token_economy.memory_cache_gate import (
    check_memory_before_pack,
    write_cache_fill,
)
from rush.tools.continuity import SessionContinuityTool as ContinuityTool
from rush.tools.memory import MemoryTool
from rush.tools.review import ReviewTool
from rush.workflows.project_run import execute_scan, plan_scan, resume_scan_run
from rush.workflows.projects import register_project

# --------------------------------------------------------------------------
# G8c (`MemoryTool._handoff` `dispatch`/`status`): owned by Phase 73 task
# 73-T05 per the owner's 2026-09-26 decision (recorded in the W3 brief R19.D);
# Phase 70 T19 builds and tests no competing version.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Local fixtures/helpers (kept local to this file per task instructions).
# --------------------------------------------------------------------------


def _write_memory_config(root: Path, *, record: bool = True) -> None:
    (root / "rush.toml").write_text(
        f"[tools.memory]\nrecord = {'true' if record else 'false'}\n",
        encoding="utf-8",
    )


def _write_target(root: Path, name: str = "mod.py") -> Path:
    target = root / name
    target.write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    return target


def _insert_stated_row(
    db_path: Path, artifact_id: str, subject: str, content: dict, source: str
) -> None:
    """Cribbed from `tests/test_phase62_review_memory.py`'s `_insert_stated_row`:
    `TypedArtifactStore.write()` rejects `trust_tier="STATED"` on insert (promotion
    is the only path), so a STATED row is seeded directly via SQL."""
    signature = compute_content_signature(content)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO memory_artifacts "
        "(id, family, subject, trust_tier, content, source, created_at, promoted_at, signature) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            artifact_id,
            "memory",
            subject,
            "STATED",
            json.dumps(content),
            source,
            time.time(),
            time.time(),
            signature,
        ),
    )
    conn.commit()
    conn.close()


def _seed_failure_1(root: Path, target_name: str = "mod.py") -> None:
    store = TypedArtifactStore(root)
    _insert_stated_row(
        store.db_path,
        "failure-1",
        "failure",
        {
            "target_file": target_name,
            "fix_commit": "abc1234",
            "error_message": "off-by-one in func",
        },
        source="migration:failure_ledger",
    )


_EXPECTED_FAILURE1_RECEIPT = {
    "version": 1,
    "used": [
        {
            "id": "failure-1",
            "revision": 1,
            "source": "migration:failure_ledger",
            "operation": "recall",
        }
    ],
    "written": [],
}


def _legacy_db(root: Path) -> Path:
    """Cribbed verbatim from `tests/test_memory_versions.py::_legacy_db`: a real
    older-compatible schema (predates `artifact_version`/`owner_scope` columns)."""
    db = root / ".rush" / "memory.db"
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE memory_artifacts (id TEXT PRIMARY KEY, family TEXT NOT NULL, "
            "subject TEXT NOT NULL, trust_tier TEXT NOT NULL, content TEXT NOT NULL, "
            "source TEXT NOT NULL, created_at REAL NOT NULL, symbol_ref TEXT, "
            "content_hash TEXT, corroboration_count INTEGER NOT NULL DEFAULT 0, "
            "promoted_at REAL, stale INTEGER NOT NULL DEFAULT 0, signature TEXT, "
            "origin_kind TEXT, origin_id TEXT, expires_at REAL, expired_at REAL, expired_by TEXT)"
        )
        conn.execute(
            "INSERT INTO memory_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "legacy-id",
                "memory",
                "preference",
                "IMPORTED",
                '{"value":"exact"}',
                "legacy-source",
                1.0,
                None,
                None,
                0,
                None,
                0,
                None,
                "preference",
                "theme",
                None,
                None,
                None,
            ),
        )
    return db


def _table_columns(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")}


def _memory_of(result: Any) -> Any:
    """Legacy dict -> `metadata.memory`; V1 -> `extensions.metadata.memory`."""
    if isinstance(result, dict):
        return result.get("metadata", {}).get("memory")
    extensions = getattr(result, "extensions", {}) or {}
    return extensions.get("metadata", {}).get("memory")


# ==========================================================================
# Review: exact receipt across CLI / MCP / V1 round-trip / strict validate.
# ==========================================================================


def _case_review_cli_json_exact_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_target(tmp_path)
    _seed_failure_1(tmp_path)
    monkeypatch.setattr(rendering, "ALL_TOOLS", [ReviewTool()])
    with pytest.raises(SystemExit):
        rendering._run_tool("review", tmp_path, as_json=True)
    payload = json.loads(capsys.readouterr().out)
    assert _memory_of(payload) == _EXPECTED_FAILURE1_RECEIPT


def _case_review_mcp_wrapper_exact_receipt(tmp_path: Path) -> None:
    _write_target(tmp_path)
    _seed_failure_1(tmp_path)
    executor = InvocationExecutor()
    tool = ReviewTool()
    executor.register(tool.name, tool.__call__)
    wrapped = make_tool_wrapper(tool, executor)
    result = wrapped(path=tmp_path)
    assert _memory_of(result) == _EXPECTED_FAILURE1_RECEIPT


def _case_review_v1_roundtrip_exact_receipt(tmp_path: Path) -> None:
    _write_target(tmp_path)
    _seed_failure_1(tmp_path)
    legacy = ReviewTool().run(tmp_path)
    v1 = adapt_legacy_tool_result(dict(legacy))
    assert _memory_of(v1) == _EXPECTED_FAILURE1_RECEIPT


def _case_review_strict_validate_passes(tmp_path: Path) -> None:
    _write_target(tmp_path)
    _seed_failure_1(tmp_path)
    legacy = ReviewTool().run(tmp_path)
    v1 = adapt_legacy_tool_result(dict(legacy))
    revalidated = validate_tool_result(v1.to_dict())
    assert _memory_of(revalidated) == _EXPECTED_FAILURE1_RECEIPT


def _case_review_stale_candidate_no_receipt(tmp_path: Path) -> None:
    target = _write_target(tmp_path)
    store = TypedArtifactStore(tmp_path)
    content = {"target_file": "mod.py", "fix_commit": "deadbee", "error_message": "x"}
    _insert_stated_row(
        store.db_path, "stale-1", "failure", content, source="migration:failure_ledger"
    )
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = 'stale-1'",
            (json.dumps({**content, "changed": True}),),
        )
        conn.commit()
    result = ReviewTool().run(target)
    # keep-green: a content-hash-changed (stale) candidate must never produce a receipt.
    assert _memory_of(result) is None


def _case_review_signature_mismatch_no_receipt(tmp_path: Path) -> None:
    target = _write_target(tmp_path)
    store = TypedArtifactStore(tmp_path)
    content = {"target_file": "mod.py", "fix_commit": "deadbee", "error_message": "x"}
    _insert_stated_row(
        store.db_path, "sig-1", "failure", content, source="migration:failure_ledger"
    )
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET signature = 'tampered' WHERE id = 'sig-1'"
        )
        conn.commit()
    result = ReviewTool().run(target)
    # keep-green: a tampered signature must never produce a receipt or a citation finding.
    assert _memory_of(result) is None
    citations = [
        f for f in result["findings"] if f.get("rule") == "memory-failure-citation"
    ]
    assert citations == []


def _case_review_dedup_two_files_one_receipt(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    pass\n", encoding="utf-8")
    store = TypedArtifactStore(tmp_path)
    content = {
        "target_file": "a.py",
        "fix_commit": "cafebee",
        "error_message": "shared bug: a.py and b.py both call the broken helper",
    }
    _insert_stated_row(
        store.db_path, "shared-1", "failure", content, source="migration:failure_ledger"
    )
    # The artifact names both a.py and b.py, so each file's review recall (one query per
    # target name) independently matches it; T19 must dedupe the receipt by
    # (id, revision, operation) once across both.
    result = ReviewTool().run(tmp_path)
    citations = [
        f
        for f in result["findings"]
        if f.get("rule") == "memory-failure-citation" and "shared-1" in f["message"]
    ]
    assert len(citations) == 2, citations
    memory = _memory_of(result)
    assert memory is not None, (
        "expected a deduplicated receipt, got no metadata.memory at all"
    )
    assert memory == {
        "version": 1,
        "used": [
            {
                "id": "shared-1",
                "revision": 1,
                "source": "migration:failure_ledger",
                "operation": "recall",
            }
        ],
        "written": [],
    }


def _case_review_virgin_project_no_rush_created(tmp_path: Path) -> None:
    target = _write_target(tmp_path)
    ReviewTool().run(target)
    assert not (tmp_path / ".rush").exists(), (
        "G3: review must not create .rush/memory.db for a virgin project with no memory "
        "state -- ReviewTool._recall_memory_citations currently constructs a full "
        "write-capable TypedArtifactStore unconditionally"
    )


def _case_review_older_compatible_store_no_migration(tmp_path: Path) -> None:
    db = _legacy_db(tmp_path)
    before = _table_columns(db)
    assert "artifact_version" not in before
    target = _write_target(tmp_path)
    ReviewTool().run(target)
    after = _table_columns(db)
    assert after == before, (
        "R19.3: review must use a read-only store for recall (no migration, no "
        "artifact_version/owner_scope columns added) -- currently constructs a full "
        "TypedArtifactStore, which migrates on every call"
    )
    # keep-green half of this case: no receipt from an unmigrated legacy row either.
    result = ReviewTool().run(target)
    assert _memory_of(result) is None


def _case_review_nested_file_uses_logical_root(tmp_path: Path) -> None:
    nested = tmp_path / "sub" / "dir"
    nested.mkdir(parents=True)
    # T8 root marker: tmp_path is the project's logical root.
    (tmp_path / "rush.toml").write_text("", encoding="utf-8")
    target = nested / "mod.py"
    target.write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    _seed_failure_1(tmp_path, target_name="mod.py")
    result = ReviewTool().run(target)
    assert _memory_of(result) == _EXPECTED_FAILURE1_RECEIPT, (
        "review.run() resolves root as path.parent (sub/dir), not the project's real "
        "logical root (tmp_path) where the artifact actually lives"
    )
    assert not (nested / ".rush").exists(), (
        "must not create a second store under sub/dir"
    )


# ==========================================================================
# Pack gate.
# ==========================================================================


def _write_ctx_source(root: Path, name: str = "ctx.py") -> str:
    """A real source file plus the exact sha256 `check_memory_before_pack`'s
    defended-recall staleness check compares against (`SourceValidationMemo.source_hash`,
    identical to `MerkleInvalidator.hash_content`) -- a fabricated hash makes every
    candidate look stale and skipped, which would hide the real T19 gap behind a
    fixture bug instead of exercising it."""
    import hashlib

    text = "def sym():\n    return 1\n"
    (root / name).write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case_pack_gate_hit_exact_receipt(tmp_path: Path) -> None:
    content_hash = _write_ctx_source(tmp_path)
    write_cache_fill(
        tmp_path,
        "ctx.py",
        "sym",
        {"packed_text": "hello", "source_content_hash": content_hash},
        token_budget=100,
        encoding="cl100k_base",
    )
    gate = check_memory_before_pack(
        "ctx.py", "sym", project_root=tmp_path, token_budget=100, encoding="cl100k_base"
    )
    assert gate.hit is True
    assert getattr(gate, "revision", None) == 1, (
        "CacheGateResult must gain a revision field"
    )
    assert getattr(gate, "source", None) == "context_pack"


def _case_pack_gate_miss_cache_write_written(tmp_path: Path) -> None:
    committed = write_cache_fill(
        tmp_path,
        "ctx.py",
        "sym",
        {"packed_text": "hello", "source_content_hash": "h1"},
        token_budget=100,
        encoding="cl100k_base",
    )
    assert committed is not None, (
        "write_cache_fill must return the committed MemoryArtifact"
    )
    assert committed.artifact_version == 1
    assert committed.source == "context_pack"


def _case_pack_gate_miss_no_grant_no_db(tmp_path: Path) -> None:
    # A miss without a cache_write grant: caller never invokes write_cache_fill at all.
    gate = check_memory_before_pack("ctx.py", "sym", project_root=tmp_path)
    assert gate.hit is False
    assert not (tmp_path / ".rush" / "memory.db").exists()


def _case_pack_gate_over_budget_spill_written_only(tmp_path: Path) -> None:
    target = tmp_path / "big.py"
    target.write_text("x = 1\n" * 2000, encoding="utf-8")
    granted = ExecutionPermissions(cache_write=True)
    result = pack_context(
        time.monotonic(),
        tmp_path,
        "big.py",
        "x",
        token_budget=1,
        granted=granted,
    )
    memory = result.get("metadata", {}).get("memory")
    assert memory is not None and memory.get("written"), (
        "an over-budget CCR-spill pack must still report a written cache_fill receipt "
        "(build_continuity_result has no memory= kwarg yet)"
    )
    assert memory.get("used") == []


# ==========================================================================
# Observation.
# ==========================================================================


class _ProbeTool:
    name = "probe"

    def __init__(self, status: str = "ok") -> None:
        self.status = status

    def __call__(self, path: Path, allow_cache_write: bool = False) -> dict[str, Any]:
        return {
            "tool": "probe",
            "engine": "probe-engine",
            "engine_version": "1.0",
            "status": self.status,
            "duration_ms": 1,
            "summary": "probe ran",
            "findings": [],
            "raw": {"detail": "value"},
        }


def _run_probe(root: Path, *, cache=None, allow_cache_write: bool = True) -> Any:
    tool = _ProbeTool()
    executor = InvocationExecutor(cache=cache)
    executor.register(tool.name, tool.__call__, pure=True)
    req = {
        "operation_id": "probe",
        "path": str(root / "t.py"),
        "allow_cache_write": allow_cache_write,
    }
    (root / "t.py").write_text("x = 1\n", encoding="utf-8")
    ctx = resolve_invocation(
        req, transport="cli", workspace_root=root, config=load_config(start=root)
    )
    return executor.execute(ctx)


def _observations(root: Path) -> list[dict[str, Any]]:
    db = root / ".rush" / "memory.db"
    if not db.exists():
        return []
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT id, artifact_version, source FROM memory_artifacts "
            "WHERE family='experience' AND subject='episodic'"
        ).fetchall()
    return [{"id": r[0], "artifact_version": r[1], "source": r[2]} for r in rows]


def _case_observation_record_cache_write_written_matches_row(tmp_path: Path) -> None:
    _write_memory_config(tmp_path)
    result = _run_probe(tmp_path)
    rows = _observations(tmp_path)
    assert len(rows) == 1
    memory = result.get("metadata", {}).get("memory")
    assert memory is not None, "InvocationExecutor discards record_observation's return"
    assert memory["written"] == [
        {
            "id": rows[0]["id"],
            "revision": rows[0]["artifact_version"],
            "source": rows[0]["source"],
            "operation": "observation",
        }
    ]


def _case_observation_denied_absent(tmp_path: Path) -> None:
    _write_memory_config(tmp_path)
    result = _run_probe(tmp_path, allow_cache_write=False)
    assert _observations(tmp_path) == []
    # keep-green: nothing was ever committed, so there is nothing to report.
    assert result.get("metadata", {}).get("memory") is None


def _case_observation_forced_write_failure_absent_original_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_memory_config(tmp_path)
    monkeypatch.setattr(
        TypedArtifactStore,
        "write",
        lambda self, artifact, **kw: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    result = _run_probe(tmp_path)
    assert _observations(tmp_path) == []
    assert result["status"] == "ok", (
        "a forced observation-write failure must preserve the original result"
    )
    assert result.get("metadata", {}).get("memory") is None


# ==========================================================================
# Result cache (G6: new contract for the cache-hit copy).
# ==========================================================================


class _DictCache:
    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any:
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        self._store[key] = value


def _case_result_cache_hit_moves_receipts_to_original_memory(tmp_path: Path) -> None:
    """New contract for `test_memory_observations.py::test_cached_result_keeps_original_execution_identity`
    (lines 178-212, flagged by G6): a cache hit must move receipts to
    `metadata.cache.original_memory`, not return the byte-identical `result1`."""
    _write_memory_config(tmp_path)
    tool = _ProbeTool()
    cache = _DictCache()
    executor = InvocationExecutor(cache=cache)
    executor.register(tool.name, tool.__call__, pure=True)
    req = {
        "operation_id": "probe",
        "path": str(tmp_path / "t.py"),
        "allow_cache_write": True,
    }
    (tmp_path / "t.py").write_text("x = 1\n", encoding="utf-8")
    config = load_config(start=tmp_path)

    ctx1 = resolve_invocation(
        req, transport="cli", workspace_root=tmp_path, config=config
    )
    result1 = executor.execute(ctx1)
    assert len(_observations(tmp_path)) == 1

    ctx2 = resolve_invocation(
        req, transport="cli", workspace_root=tmp_path, config=config
    )
    result2 = executor.execute(ctx2)

    assert len(_observations(tmp_path)) == 1, (
        "a cache hit must not create a fresh observation"
    )

    memory1 = result1.get("metadata", {}).get("memory")
    assert memory1 is not None and memory1.get("written"), (
        "result1 must carry the committed observation as a written receipt -- "
        "InvocationExecutor discards record_observation's return today"
    )
    assert result2 is not result1, (
        "G6: a cache hit must return a fresh copy with receipts moved, not the same "
        "object result1 (the executor's cache-hit branch does `return cached_result` "
        "with no deepcopy at all today)"
    )
    original_memory = (
        result2.get("metadata", {}).get("cache", {}).get("original_memory")
    )
    assert original_memory == memory1, (
        "cache hit must move the original invocation's receipts into "
        "metadata.cache.original_memory"
    )
    assert result2.get("metadata", {}).get("memory") != memory1


def _case_result_cache_bytes_unchanged_in_sqlite(tmp_path: Path) -> None:
    from rush.cache import ResultCache

    _write_memory_config(tmp_path)
    cache = ResultCache(tmp_path / ".rush" / "cache.db")
    tool = _ProbeTool()
    executor = InvocationExecutor(cache=cache)
    executor.register(tool.name, tool.__call__, pure=True)
    req = {
        "operation_id": "probe",
        "path": str(tmp_path / "t.py"),
        "allow_cache_write": True,
    }
    (tmp_path / "t.py").write_text("x = 1\n", encoding="utf-8")
    config = load_config(start=tmp_path)
    ctx1 = resolve_invocation(
        req, transport="cli", workspace_root=tmp_path, config=config
    )
    executor.execute(ctx1)

    with sqlite3.connect(
        cache.db_path if hasattr(cache, "db_path") else tmp_path / ".rush" / "cache.db"
    ) as conn:
        before = [
            row[0] for row in conn.execute("SELECT result_json FROM cache_entries")
        ]

    ctx2 = resolve_invocation(
        req, transport="cli", workspace_root=tmp_path, config=config
    )
    executor.execute(ctx2)

    with sqlite3.connect(
        cache.db_path if hasattr(cache, "db_path") else tmp_path / ".rush" / "cache.db"
    ) as conn:
        after = [
            row[0] for row in conn.execute("SELECT result_json FROM cache_entries")
        ]

    assert before == after, "the stored ResultCache bytes must never change on a hit"


def _case_result_cache_single_observation_on_miss_then_hit(tmp_path: Path) -> None:
    _write_memory_config(tmp_path)
    tool = _ProbeTool()
    cache = _DictCache()
    executor = InvocationExecutor(cache=cache)
    executor.register(tool.name, tool.__call__, pure=True)
    req = {
        "operation_id": "probe",
        "path": str(tmp_path / "t.py"),
        "allow_cache_write": True,
    }
    (tmp_path / "t.py").write_text("x = 1\n", encoding="utf-8")
    config = load_config(start=tmp_path)
    for _ in range(3):
        ctx = resolve_invocation(
            req, transport="cli", workspace_root=tmp_path, config=config
        )
        executor.execute(ctx)
    assert len(_observations(tmp_path)) == 1


def _case_typed_gate_hit_vs_result_cache_hit_differ(tmp_path: Path) -> None:
    content_hash = _write_ctx_source(tmp_path)
    write_cache_fill(
        tmp_path,
        "ctx.py",
        "sym",
        {"packed_text": "hi", "source_content_hash": content_hash},
        token_budget=100,
    )
    typed_gate = check_memory_before_pack(
        "ctx.py", "sym", project_root=tmp_path, token_budget=100
    )
    assert typed_gate.hit is True
    assert getattr(typed_gate, "artifact_id", None) is not None
    assert getattr(typed_gate, "revision", None) == 1, (
        "a real typed-memory-cache-gate hit must carry a real artifact id/revision"
    )

    (tmp_path / "resultcache").mkdir(exist_ok=True)
    _write_memory_config(tmp_path / "resultcache")
    tool = _ProbeTool()
    cache = _DictCache()
    executor = InvocationExecutor(cache=cache)
    executor.register(tool.name, tool.__call__, pure=True)
    root2 = tmp_path / "resultcache"
    (root2 / "t.py").write_text("x = 1\n", encoding="utf-8")
    req = {
        "operation_id": "probe",
        "path": str(root2 / "t.py"),
        "allow_cache_write": True,
    }
    config2 = load_config(start=root2)
    ctx1 = resolve_invocation(
        req, transport="cli", workspace_root=root2, config=config2
    )
    executor.execute(ctx1)
    ctx2 = resolve_invocation(
        req, transport="cli", workspace_root=root2, config=config2
    )
    result_cache_hit = executor.execute(ctx2)
    # A pure result-cache-only hit must never manufacture a memory id/revision from its
    # cache key -- distinct from the typed-gate hit above, which carries a real one.
    assert result_cache_hit.get("metadata", {}).get(
        "memory"
    ) is None or "id" not in str(result_cache_hit.get("metadata", {}).get("memory"))


# ==========================================================================
# MemoryTool.
# ==========================================================================


def _case_memorytool_write_written_entry(tmp_path: Path) -> None:
    tool = MemoryTool()
    result = tool(
        path=tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"body": "x"},
        source="unit-test",
        allow_cache_write=True,
    )
    assert result["status"] == "ok", result
    memory = result.get("metadata", {}).get("memory")
    assert memory is not None
    raw = result["raw"]
    assert memory["written"] == [
        {
            "id": raw["id"],
            "revision": raw["artifact_version"],
            "source": raw["source"],
            "operation": "write",
        }
    ]


def _case_memorytool_promote_both_entries(tmp_path: Path) -> None:
    tool = MemoryTool()
    result = tool(
        path=tmp_path,
        operation="promote",
        subject="domain_knowledge",
        content={"body": "y"},
        source="unit-test",
        user_stated=True,
        allow_cache_write=True,
    )
    assert result["status"] == "ok", result
    memory = result.get("metadata", {}).get("memory")
    assert memory is not None
    assert len(memory["written"]) == 2, (
        "promote commits both a candidate-create and a promotion decision"
    )


def _case_memorytool_compact_recall_used_matches_page_items(tmp_path: Path) -> None:
    tool = MemoryTool()
    write_result = tool(
        path=tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"body": "csv export helper"},
        source="csv-helper",
        allow_cache_write=True,
    )
    artifact_id = write_result["raw"]["id"]
    recall_result = tool(
        path=tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="csv",
        request={"view": "compact", "limit": 8},
        session_allowlist=["csv-helper"],
    )
    assert recall_result["status"] == "ok", recall_result
    items = recall_result["raw"]["data"]["items"]
    assert any(item["id"] == artifact_id for item in items)
    memory = recall_result.get("metadata", {}).get("memory")
    assert memory is not None
    assert {u["id"] for u in memory["used"]} == {item["id"] for item in items}


def _case_memorytool_permission_denied_absent(tmp_path: Path) -> None:
    tool = MemoryTool()
    result = tool(
        path=tmp_path,
        operation="write",
        subject="domain_knowledge",
        content={"body": "z"},
        source="unit-test",
        # no allow_cache_write grant
    )
    assert result["status"] == "skipped"
    # keep-green: a denied write never commits, so it can never report a receipt.
    assert result.get("metadata", {}).get("memory") is None


def _case_memorytool_bridge_receive_raw_no_receipts(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    session, capability, _initial = prepare_handoff(
        store,
        root=tmp_path,
        audience="codex_cli",
        granted_ids=["A1"],
        session_allowlist=["tool_a"],
    )
    handler = build_memory_bridge_handler(
        root=tmp_path, session_id=session.session_id, capability=capability
    )
    result = handler("receive", {})
    # keep-green: `build_memory_bridge_handler` returns `result["raw"]` only, structurally,
    # so it can never carry a metadata.memory block.
    assert isinstance(result, dict)
    assert "metadata" not in result
    assert "memory" not in result


# ==========================================================================
# Scan.
# ==========================================================================


def _fixture_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    return root


def _case_scan_staged_manifest_and_aggregate_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Covers three T19 §6 "Scan" bullets in one real scan: (1) a staged review
    candidate must cite the *live* store, not a deleted staging tempdir (G2); (2) the
    manifest child keeps its own receipt; (3) the aggregate unions child receipts."""
    from rush.tools.review import ReviewTool as _ReviewTool
    from rush.workflows import project_run

    monkeypatch.setattr(project_run, "ALL_TOOLS", [_ReviewTool()])
    root = _fixture_project(tmp_path)
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    _seed_failure_1(root, target_name="app.py")

    plan = plan_scan(record.project_id, data_root=data_root)
    run = execute_scan(plan, permissions=ExecutionPermissions(), data_root=data_root)

    by_id = {item.candidate.candidate_id: item for item in run.candidate_results}
    review_result = by_id["review"].result
    child_memory = review_result.get("metadata", {}).get("memory")
    assert child_memory is not None and child_memory["used"], (
        "G2: the review candidate runs against a temp staging copy with no .rush -- "
        "its recall must still cite the real project's live store, not the deleted "
        "staging tempdir"
    )
    aggregate_memory = run.aggregate.get("metadata", {}).get("memory")
    assert aggregate_memory is not None
    assert aggregate_memory["used"] == child_memory["used"], (
        "aggregate must union child receipts"
    )


def _case_scan_no_cross_root_receipt_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.tools.review import ReviewTool as _ReviewTool
    from rush.workflows import project_run

    monkeypatch.setattr(project_run, "ALL_TOOLS", [_ReviewTool()])

    (tmp_path / "a").mkdir()
    root_a = _fixture_project(tmp_path / "a")
    data_root_a = tmp_path / "a" / "rush-data"
    record_a = register_project(root_a, data_root=data_root_a)
    _seed_failure_1(root_a, target_name="app.py")

    root_b = tmp_path / "b" / "project"
    root_b.mkdir(parents=True)
    (root_b / "app.py").write_text("def unreviewed():\n    pass\n", encoding="utf-8")
    data_root_b = tmp_path / "b" / "rush-data"
    record_b = register_project(root_b, data_root=data_root_b)
    # no failure-1 seeded in project b

    plan_b = plan_scan(record_b.project_id, data_root=data_root_b)
    run_b = execute_scan(
        plan_b, permissions=ExecutionPermissions(), data_root=data_root_b
    )
    by_id_b = {item.candidate.candidate_id: item for item in run_b.candidate_results}
    # keep-green: project b never saw project a's artifact, so it can never cite it.
    memory_b = by_id_b["review"].result.get("metadata", {}).get("memory")
    assert memory_b is None or all(
        u["id"] != "failure-1" for u in memory_b.get("used", [])
    )
    assert record_a.project_id != record_b.project_id


def _case_scan_resume_original_memory_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Attempt 1: `review` recalls failure-1 and is retained; `review-late` fails
    and is re-attempted. Between attempts failure-2 is seeded, so the resumed
    `review-late` recalls both. Retained receipts belong in
    `metadata.cache.original_memory`; `metadata.memory` holds only this attempt's."""
    from rush.workflows import project_run

    class _LateReview:
        name = "review-late"

        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, path: Path) -> Any:
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("review-late fails on its first attempt")
            return ReviewTool().run(path)

    monkeypatch.setattr(project_run, "ENGINE_SPECS", {})
    monkeypatch.setattr(project_run, "ALL_TOOLS", [ReviewTool(), _LateReview()])
    root = _fixture_project(tmp_path)
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    _seed_failure_1(root, target_name="app.py")
    plan = plan_scan(record.project_id, data_root=data_root)

    def _boom(*_a: Any, **_k: Any) -> Any:
        raise RuntimeError("simulated crash before aggregate")

    with monkeypatch.context() as crash_patch:
        crash_patch.setattr(project_run, "aggregate_results", _boom)
        with pytest.raises(RuntimeError, match="simulated crash"):
            execute_scan(
                plan,
                permissions=ExecutionPermissions(artifact_write=True),
                data_root=data_root,
            )

    _insert_stated_row(
        TypedArtifactStore(root).db_path,
        "failure-2",
        "failure",
        {
            "target_file": "app.py",
            "fix_commit": "def5678",
            "error_message": "second recorded failure",
        },
        source="migration:failure_ledger",
    )

    runs_dir = root / ".rush" / "runs"
    run_id = next(p.name for p in runs_dir.iterdir() if p.is_dir())

    resumed = resume_scan_run(
        record.project_id,
        run_id,
        permissions=ExecutionPermissions(artifact_write=True),
        data_root=data_root,
    )
    metadata: dict[str, Any] = dict(resumed.aggregate.get("metadata") or {})

    def _recall(artifact_id: str) -> dict[str, Any]:
        return {
            "id": artifact_id,
            "revision": 1,
            "source": "migration:failure_ledger",
            "operation": "recall",
        }

    assert metadata.get("cache", {}).get("retained_candidates") == ["review"]
    assert metadata.get("cache", {}).get("original_memory") == {
        "version": 1,
        "used": [_recall("failure-1")],
        "written": [],
    }, "retained children's receipts belong in metadata.cache.original_memory"
    assert metadata.get("memory") == {
        "version": 1,
        # B3 first-use order = recall's BM25 rank (shorter failure-2 ranks first).
        "used": [_recall("failure-2"), _recall("failure-1")],
        "written": [],
    }, "metadata.memory holds only this attempt's receipts (review-late)"


# ==========================================================================
# Absence + compact projection.
# ==========================================================================


def _case_absence_when_unused_no_memory_key(tmp_path: Path) -> None:
    target = _write_target(tmp_path)
    result = ReviewTool().run(target)
    # keep-green: no memory config, no artifacts seeded -- there must be no "memory" key
    # at all (never an empty-but-present block).
    assert "memory" not in result.get("metadata", {})


def _case_compact_projection_large_receipts_stay_within_budget(tmp_path: Path) -> None:
    """RED-via-T16: the byte-bounded compact projection this depends on is T16's
    deliverable and is not implemented in this worktree either. This case still
    asserts T19's own literal requirement -- a large `used` receipt set must not
    blow the result past `max_bytes`, with the full result recoverable -- via
    `recall_page`'s existing max_bytes budgeting, which T19 must reuse."""
    tool = MemoryTool()
    for i in range(50):
        tool(
            path=tmp_path,
            operation="write",
            subject="domain_knowledge",
            content={"body": f"needle entry {i}"},
            source="bulk-source",
            allow_cache_write=True,
        )
    recall_result = tool(
        path=tmp_path,
        operation="recall",
        subject="domain_knowledge",
        query="needle",
        request={"view": "compact", "limit": 50},
        session_allowlist=["bulk-source"],
    )
    assert recall_result["status"] == "ok", recall_result
    memory = recall_result.get("metadata", {}).get("memory")
    assert memory is not None, (
        "no metadata.memory exists to bound in the first place (T19 not implemented)"
    )
    serialized = json.dumps(memory)
    assert len(serialized.encode("utf-8")) <= 8000


# ==========================================================================
# Provenance attribution link + checkpoint save/restore.
# ==========================================================================


def _case_provenance_attribution_link_returns_written_artifact(tmp_path: Path) -> None:
    from rush.session_memory import record_fix_attribution

    commit = {"hash": "abc123", "is_fix": True}
    committed = record_fix_attribution(tmp_path, commit, failure_id="failure-1")
    assert committed is not None, (
        "record_fix_attribution discards migration.write_if_new's committed row -- "
        "T19 needs it returned so the ToolResult can carry a written attribution_link receipt"
    )
    assert committed.source == "provenance_ai:attribution_link"


def _case_checkpoint_save_written_entry(tmp_path: Path) -> None:
    tool = ContinuityTool()
    result = tool.run(
        tmp_path,
        operation="save",
        name="handoff",
        files=["src/rush/cli.py"],
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )
    assert result["status"] == "ok", result
    memory = result.get("metadata", {}).get("memory")
    assert memory is not None and memory.get("written"), (
        "checkpoint save must report a written checkpoint receipt"
    )


def _case_checkpoint_restore_fallback_used_entry(tmp_path: Path) -> None:
    tool = ContinuityTool()
    save_result = tool.run(
        tmp_path,
        operation="save",
        name="handoff",
        files=["src/rush/cli.py"],
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )
    assert save_result["status"] == "ok", save_result
    # The fallback path: the checkpoint journal is migrated into the store, which
    # renames `handoff.json` to `.migrated`, so restore must read the store row.
    from rush.memory.migration import migrate_checkpoint_journal

    assert migrate_checkpoint_journal(tmp_path) == 1
    sessions = tmp_path / ".rush" / "sessions"
    assert not (sessions / "handoff.json").exists()
    assert (sessions / "handoff.json.migrated").exists()
    with sqlite3.connect(tmp_path / ".rush" / "memory.db") as conn:
        (row_id, row_version, row_source) = conn.execute(
            "SELECT id, artifact_version, source FROM memory_artifacts "
            "WHERE origin_kind = 'checkpoint' AND origin_id = 'handoff'"
        ).fetchone()
    restore_result = tool.run(
        tmp_path,
        operation="restore",
        name="handoff",
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )
    assert restore_result["status"] == "ok", restore_result
    memory = restore_result.get("metadata", {}).get("memory")
    assert memory == {
        "version": 1,
        "used": [
            {
                "id": row_id,
                "revision": row_version,
                "source": row_source,
                "operation": "restore",
            }
        ],
        "written": [],
    }, "a restore fallback read must report a used checkpoint receipt"
    assert (row_version, row_source) == (1, "migration:checkpoint_journal")


# ==========================================================================
# R19.D: T22/G8 product defects T19 now owns.
# ==========================================================================


def _case_ack_non_object(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    session, capability, _initial = prepare_handoff(
        store,
        root=tmp_path,
        audience="codex_cli",
        granted_ids=["A1"],
        session_allowlist=["tool_a"],
    )
    with pytest.raises(HandoffError):
        acknowledge_readback(
            store,
            session_id=session.session_id,
            capability=capability,
            readbacks=["not-an-object"],  # type: ignore[list-item]
        )


def _case_link_version_overflow(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(
        MemoryArtifact(
            id="a1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="IMPORTED",
            content={"text": "x"},
            source="allowed",
            created_at=1.0,
        )
    )
    result = add_relation(
        store,
        source_id="a1",
        source_version=1,
        target_id="a1",
        target_version=2**70,
        kind="depends_on",
    )
    assert result["code"] == "E_INPUT", (
        "add_relation must reject an out-of-range version as a validation error before "
        "SQLite binding, not raise OverflowError from _endpoint_exists"
    )


def _case_receive_version_overflow(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    session, capability, _initial = prepare_handoff(
        store,
        root=tmp_path,
        audience="codex_cli",
        granted_ids=["A1"],
        session_allowlist=["tool_a"],
    )
    with pytest.raises(HandoffError):
        acknowledge_readback(
            store,
            session_id=session.session_id,
            capability=capability,
            readbacks=[{"id": "A1", "version": 2**70, "digest": "0" * 64}],
        )


def _case_recall_relations_real(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    store.write(
        MemoryArtifact(
            id="a1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="IMPORTED",
            content={"text": "needle alpha"},
            source="allowed",
            created_at=1.0,
        )
    )
    store.write(
        MemoryArtifact(
            id="a2",
            family="memory",
            subject="domain_knowledge",
            trust_tier="IMPORTED",
            content={"text": "beta"},
            source="allowed",
            created_at=1.0,
        )
    )
    relation = add_relation(
        store,
        source_id="a1",
        source_version=1,
        target_id="a2",
        target_version=1,
        kind="depends_on",
    )
    assert relation["code"] == "OK"

    page = recall_page(
        store, subject="domain_knowledge", query="needle", session_allowlist=["allowed"]
    )
    item = next(i for i in page["items"] if i["id"] == "a1")
    assert item["relations"] != [], (
        "_candidate_to_item hard-codes relations=[] (retrieval.py:291-294) even though a "
        "real relation exists via related_artifacts()"
    )


# ==========================================================================
# Case registry + parametrized entry point.
# ==========================================================================

_CASES: dict[str, Any] = {
    "review-cli-json-exact-receipt": _case_review_cli_json_exact_receipt,
    "review-mcp-wrapper-exact-receipt": _case_review_mcp_wrapper_exact_receipt,
    "review-v1-roundtrip-exact-receipt": _case_review_v1_roundtrip_exact_receipt,
    "review-strict-validate-passes": _case_review_strict_validate_passes,
    "review-stale-candidate-no-receipt": _case_review_stale_candidate_no_receipt,
    "review-signature-mismatch-no-receipt": _case_review_signature_mismatch_no_receipt,
    "review-dedup-two-files-one-receipt": _case_review_dedup_two_files_one_receipt,
    "review-virgin-project-no-rush-created": _case_review_virgin_project_no_rush_created,
    "review-older-compatible-store-no-migration": _case_review_older_compatible_store_no_migration,
    "review-nested-file-uses-logical-root": _case_review_nested_file_uses_logical_root,
    "pack-gate-hit-exact-receipt": _case_pack_gate_hit_exact_receipt,
    "pack-gate-miss-cache-write-written": _case_pack_gate_miss_cache_write_written,
    "pack-gate-miss-no-grant-no-db": _case_pack_gate_miss_no_grant_no_db,
    "pack-gate-over-budget-spill-written-only": _case_pack_gate_over_budget_spill_written_only,
    "observation-record-cache-write-written-matches-row": _case_observation_record_cache_write_written_matches_row,
    "observation-denied-absent": _case_observation_denied_absent,
    "result-cache-hit-moves-receipts-to-original-memory": _case_result_cache_hit_moves_receipts_to_original_memory,
    "result-cache-bytes-unchanged-in-sqlite": _case_result_cache_bytes_unchanged_in_sqlite,
    "result-cache-single-observation-on-miss-then-hit": _case_result_cache_single_observation_on_miss_then_hit,
    "typed-gate-hit-vs-result-cache-hit-differ": _case_typed_gate_hit_vs_result_cache_hit_differ,
    "memorytool-write-written-entry": _case_memorytool_write_written_entry,
    "memorytool-promote-both-entries": _case_memorytool_promote_both_entries,
    "memorytool-compact-recall-used-matches-page-items": _case_memorytool_compact_recall_used_matches_page_items,
    "memorytool-permission-denied-absent": _case_memorytool_permission_denied_absent,
    "memorytool-bridge-receive-raw-no-receipts": _case_memorytool_bridge_receive_raw_no_receipts,
    "absence-when-unused-no-memory-key": _case_absence_when_unused_no_memory_key,
    "compact-projection-large-receipts-stay-within-budget": _case_compact_projection_large_receipts_stay_within_budget,
    "provenance-attribution-link-returns-written-artifact": _case_provenance_attribution_link_returns_written_artifact,
    "checkpoint-save-written-entry": _case_checkpoint_save_written_entry,
    "checkpoint-restore-fallback-used-entry": _case_checkpoint_restore_fallback_used_entry,
    "ack-non-object": _case_ack_non_object,
    "link-version-overflow": _case_link_version_overflow,
    "receive-version-overflow": _case_receive_version_overflow,
    "recall-relations-real": _case_recall_relations_real,
}

# Cases that need a `monkeypatch` fixture in addition to `tmp_path`.
_CASES.update(
    {
        "observation-forced-write-failure-absent-original-preserved": _case_observation_forced_write_failure_absent_original_preserved,
        "scan-staged-manifest-and-aggregate-receipts": _case_scan_staged_manifest_and_aggregate_receipts,
        "scan-no-cross-root-receipt-leakage": _case_scan_no_cross_root_receipt_leakage,
        "scan-resume-original-memory-retained": _case_scan_resume_original_memory_retained,
    }
)


def _invoke_case(
    fn: Any,
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Binds only the fixtures each case function actually declares -- most cases take
    just `tmp_path`; a few also need `monkeypatch` and/or `capsys`."""
    import inspect

    available = {"tmp_path": tmp_path, "monkeypatch": monkeypatch, "capsys": capsys}
    params = inspect.signature(fn).parameters
    fn(**{name: value for name, value in available.items() if name in params})


@pytest.mark.parametrize("case", sorted(_CASES))
def test_t19_memory_attribution(
    case: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _invoke_case(
        _CASES[case], tmp_path=tmp_path, monkeypatch=monkeypatch, capsys=capsys
    )
