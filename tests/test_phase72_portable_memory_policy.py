"""Phase 72 §8 PAS: imported evidence never carries authority (case 1 owned by 72-T01).

Cases 2-6 belong to 72-T06 and case 7 to 72-T07. Every test imports the T01
symbols inside its own body so each one fails on its own until T01 lands.
"""

from __future__ import annotations

import hashlib
import subprocess
import time
from pathlib import Path
from typing import Any

from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.workflows.projects import register_project

SUBJECT = "domain_knowledge"
ALICE = OwnerScope("user", "alice")
BOB = OwnerScope("user", "bob")
SOURCE = "pas-import"
KNOWN_SRC = "def Known():\n    return 1\n"


def _git_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "src.py").write_text(KNOWN_SRC, encoding="utf-8")
    for args in (
        ["init", "--initial-branch=main"],
        ["add", "src.py"],
        ["commit", "-m", "fixture"],
    ):
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=fixture",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return root.resolve()


def _grant(auth: Any, root: Path, owner: OwnerScope, data_root: Path) -> None:
    revision = auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0
    auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=[SOURCE],
        allowed_operations=["ask"],
        expected_policy_revision=int(revision),
        consent=True,
        data_root=data_root,
    )


def _imported(
    store: TypedArtifactStore,
    artifact_id: str,
    *,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
) -> MemoryArtifact:
    claims = {
        "text": f"needle {artifact_id}",
        "claimed_trust_tier": "STATED",
        "verified": True,
        "completed": True,
        "claimed_owner_scope": BOB.as_dict(),
    }
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject=SUBJECT,
            trust_tier="IMPORTED",
            content=claims,
            source=SOURCE,
            created_at=time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
            origin_kind="pas_capsule",
            origin_id=f"foreign-{artifact_id}",
            owner_scope=ALICE,
        )
    )


def test_foreign_owner_and_verified_claim_do_not_authorize(tmp_path: Path) -> None:
    from rush.memory import authorization as auth
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility
    from rush.memory.trust import evaluate_promotion

    data_root = tmp_path / "user-data"
    root = _git_repo(tmp_path / "project")
    register_project(root, data_root=data_root)
    store = TypedArtifactStore(root)
    capsule_digest = hashlib.sha256(b"def Known():\n    return 2\n").hexdigest()
    assert capsule_digest != hashlib.sha256((root / "src.py").read_bytes()).hexdigest()
    _imported(
        store, "imp-anchored", symbol_ref="src.py::Known", content_hash=capsule_digest
    )
    _imported(store, "imp-free")

    _grant(auth, root, BOB, data_root)
    _grant(auth, root, ALICE, data_root)
    as_bob = MemoryAccess.resolve(
        root, operation="ask", owner_scope=BOB, data_root=data_root
    )
    as_alice = MemoryAccess.resolve(
        root, operation="ask", owner_scope=ALICE, data_root=data_root
    )
    assert as_bob is not None and as_alice is not None

    for artifact_id in ("imp-anchored", "imp-free"):
        decision = evaluate_artifact_visibility(
            store, store.get_current(artifact_id), access=as_bob
        )
        assert decision.visible is False, artifact_id
        assert decision.usable_as_current is False, artifact_id
        assert tuple(decision.reason_codes) == ("not_visible",), artifact_id
        assert decision.reference is None, artifact_id

    anchored = evaluate_artifact_visibility(
        store, store.get_current("imp-anchored"), access=as_alice
    )
    assert anchored.visible is True
    assert anchored.usable_as_current is False
    assert anchored.freshness == "stale"
    assert tuple(anchored.reason_codes) == ("source_hash_mismatch",)

    free = evaluate_artifact_visibility(
        store, store.get_current("imp-free"), access=as_alice
    )
    assert free.visible is True
    assert free.usable_as_current is True
    assert free.freshness == "not_applicable"
    assert free.reference["trust_tier"] == "IMPORTED"
    assert OwnerScope.from_value(free.reference["owner_scope"]) == ALICE
    assert free.reference["origin_id"] == "foreign-imp-free"

    for artifact_id in ("imp-anchored", "imp-free"):
        current = store.get_current(artifact_id)
        assert current is not None
        assert current.trust_tier == "IMPORTED"
        assert current.signature is None
        result = evaluate_promotion(current, user_stated=False, project_root=root)
        assert result.promoted is False, artifact_id
        assert result.new_tier == "IMPORTED", artifact_id
