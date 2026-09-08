"""Phase 62 P62.2 contract tests: review/development reading memory.

Covers T-62.03, T-62.04 (phase-62-memory-integration-layer-plan.md §7). Both tests seed a
`STATED` record directly via SQL (matching `test_phase61_store.py`'s `_insert_stated_row`
convention) since `TypedArtifactStore.write()` rejects `trust_tier="STATED"` on insert
(promotion is the only path — Phase 61 Invariant 1).
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from rush.memory.store import TypedArtifactStore, compute_content_signature
from rush.tools.review import ReviewTool


def _write_target(tmp_path: Path, name: str = "mod.py") -> Path:
    target = tmp_path / name
    target.write_text(
        '"""Module docstring."""\n\n\ndef func():\n    """Doc."""\n    return 1\n',
        encoding="utf-8",
    )
    return target


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


def test_review_finding_cites_prior_failure_memory(tmp_path: Path):
    target = _write_target(tmp_path)
    store = TypedArtifactStore(tmp_path)
    _insert_stated_row(
        store.db_path,
        "failure-1",
        "failure",
        {
            "target_file": "mod.py",
            "fix_commit": "abc1234",
            "error_message": "off-by-one in func",
        },
        source="migration:failure_ledger",
    )

    result = ReviewTool().run(target)

    citations = [
        f for f in result["findings"] if f.get("rule") == "memory-failure-citation"
    ]
    assert len(citations) == 1
    assert "abc1234" in citations[0]["message"]


def test_review_cites_architectural_decision(tmp_path: Path):
    target = _write_target(tmp_path)
    store = TypedArtifactStore(tmp_path)
    _insert_stated_row(
        store.db_path,
        "adr-1",
        "architectural_decision",
        {
            "target_file": "mod.py",
            "rule_id": "no-bare-except",
            "decision": "always catch specific exceptions",
        },
        source="migration:invariant_graph",
    )

    result = ReviewTool().run(target)

    citations = [
        f
        for f in result["findings"]
        if f.get("rule") == "memory-architectural-decision-citation"
    ]
    assert len(citations) == 1
    assert "always catch specific exceptions" in citations[0]["message"]
