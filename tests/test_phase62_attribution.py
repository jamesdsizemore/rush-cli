"""Phase 62 P62.5 contract tests: AI-attribution trail.

Covers T-62.09, T-62.10 (phase-62-memory-integration-layer-plan.md §6.5 Invariant 4, §7). Both
tests seed a `STATED` failure record directly via SQL (matching `test_phase62_review_memory.py`'s
`_insert_stated_row` convention) since `TypedArtifactStore.write()` rejects `trust_tier="STATED"`
on insert (promotion is the only path — Phase 61 Invariant 1).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from rush.memory.migration import read_origin_kind_by_symbol
from rush.memory.store import TypedArtifactStore, compute_content_signature
from rush.session_memory import find_attribution_link
from rush.tools.provenance_ai import GitTrailerParser

RAW_LOG = "abc1234\x00Jane Dev\x00jane@example.com\x001700000000\x00fix: off-by-one in func\x01"


def _insert_stated_row(
    db_path: Path, artifact_id: str, subject: str, content: dict, source: str
) -> None:
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


def test_fix_commit_links_to_originating_failure_record(tmp_path: Path):
    store = TypedArtifactStore(tmp_path)
    _insert_stated_row(
        store.db_path,
        "failure-1",
        "failure",
        {"target_file": "mod.py", "error_message": "off-by-one in func"},
        source="migration:failure_ledger",
    )

    commits = GitTrailerParser.parse_commit_records(RAW_LOG)
    fix_commit = next(c for c in commits if c["is_fix"])
    assert fix_commit["hash"] == "abc1234"

    linked = GitTrailerParser.link_fix_commits_to_failure(
        commits, "failure-1", tmp_path
    )

    assert linked == ["abc1234"]
    assert find_attribution_link(tmp_path, "failure-1") == "abc1234"


def test_attribution_stores_sha_not_full_commit_content(tmp_path: Path):
    store = TypedArtifactStore(tmp_path)
    _insert_stated_row(
        store.db_path,
        "failure-2",
        "failure",
        {"target_file": "mod.py", "error_message": "null deref"},
        source="migration:failure_ledger",
    )

    commits = GitTrailerParser.parse_commit_records(RAW_LOG)
    GitTrailerParser.link_fix_commits_to_failure(commits, "failure-2", tmp_path)

    stored = read_origin_kind_by_symbol(tmp_path, "attribution_link", "failure-2")
    assert len(stored) == 1
    content = stored[0]
    assert content["commit_sha"] == "abc1234"
    assert "body" not in content
    assert "diff" not in content
    serialized = json.dumps(content)
    assert "fix: off-by-one in func" not in serialized
