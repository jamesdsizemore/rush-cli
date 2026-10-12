"""Phase 72 §8 PAS: imported evidence never carries authority (case 1 owned by
72-T01, cases 2-6 by 73-T09/CODEC, case 7 by 72-T07).

Every test imports the symbols a producing task adds inside its own body so each one
fails on its own until that task lands. The CODEC cases drive the public `capsule`
operation through the shared helpers of `tests/test_memory_capsule.py`.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from rush.memory.store import (
    MemoryArtifact,
    MemorySubject,
    OwnerScope,
    TypedArtifactStore,
)
from rush.workflows.projects import register_project

cap = importlib.import_module("tests.test_memory_capsule")

SUBJECT: MemorySubject = "domain_knowledge"
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
    assert free.reference is not None
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


# --- 73-T09/CODEC: cases 2-6 -----------------------------------------------------


def _receipts(env: Any) -> list[dict[str, Any]]:
    if not env.db.exists():
        return []
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM mutation_receipts ORDER BY rowid")
        return [dict(r) for r in rows]


def _plant_import_failure(env: Any, after: int) -> None:
    """A trigger that aborts the insert of the imported row past `after` rows: the
    import transaction must roll back everything it wrote before that point."""
    cap.raw_sql(
        env,
        "CREATE TRIGGER planted_failure BEFORE INSERT ON memory_artifacts "
        "WHEN NEW.trust_tier = 'IMPORTED' AND (SELECT COUNT(*) FROM memory_artifacts "
        f"WHERE trust_tier = 'IMPORTED') >= {int(after)} "
        "BEGIN SELECT RAISE(ABORT, 'planted failure'); END",
    )


def _state(env: Any) -> tuple[Any, ...]:
    """Imported rows, store revision and receipt count: what a rolled-back or refused
    import must leave exactly as it found it."""
    return (
        cap.imported_rows(env),
        cap.store_revision(env.db),
        len(_receipts(env)),
    )


def _overlay_rows(env: Any) -> Any:
    """`env` re-aimed at the overlay store, so the row helpers edit its rows."""
    import dataclasses

    return dataclasses.replace(env, root=env.data_root / "user")


def test_imported_constraint_needs_local_applicability_review(tmp_path: Path) -> None:
    src = cap.make_env(tmp_path, "src")
    dest = cap.make_env(tmp_path, "dest", owner=cap.BOB, seed=False)
    cap.put_evidence(
        dest,
        "local-c1",
        body={
            "kind": "constraint",
            "constraint_id": "c1",
            "text": "Rewrite history freely",
        },
    )
    prior = cap.row_of(dest, "local-c1")
    capsule_file = cap.export_file(src, "review.json")
    origin = json.loads(capsule_file.read_bytes())["origin"]

    # a worktree the capsule does not claim needs an approved mapping first
    refused, _same = cap.imported(dest, capsule_file, transport="cli")
    cap.assert_denied(refused, "E_PERMISSION", "mapping_required")
    assert not cap.imported_rows(dest)
    mapping_id = cap.approved_mapping(dest, origin)

    # no confirmation: every imported record stays pending, owned by the local grant
    receipts_before = len(_receipts(dest))
    preview, done = cap.imported(
        dest, capsule_file, transport="cli", mapping_id=mapping_id
    )
    assert preview.code == "OK" and done.code == "OK", (preview, done)
    assert [r["applicability"] for r in preview.data["records"]] == ["pending"] * 5
    assert [m["applicability"] for m in done.data["mappings"]] == ["pending"] * 5
    first_rows = cap.imported_rows(dest)
    assert len(first_rows) == 5
    for row in first_rows:
        assert (row["owner_scope_kind"], row["owner_scope_id"]) == ("user", "bob")
        assert row["trust_tier"] == "IMPORTED" and row["artifact_version"] == 1
        assert row["symbol_ref"] is None and row["content_hash"] is None
        assert json.loads(row["content"])["authority"] == "imported_unverified"
    assert cap.row_of(dest, "local-c1") == prior, "the local constraint is untouched"
    receipts = _receipts(dest)
    assert len(receipts) == receipts_before + 1
    dumped = json.dumps(receipts[-1], default=str)
    assert done.data["effect_id"] in dumped and done.data["invocation_id"] in dumped

    # one selected constraint becomes active; a contradictory local one is not replaced
    preview, done = cap.imported(
        dest, capsule_file, transport="cli", mapping_id=mapping_id, confirm=["c1"]
    )
    assert preview.code == "OK" and done.code == "OK", (preview, done)
    assert [m["applicability"] for m in done.data["mappings"]] == [
        "pending",
        "active",
        "pending",
        "pending",
        "pending",
    ]
    assert all(cap.row_of(dest, r["id"]) == r for r in first_rows), "prior imports"
    assert cap.row_of(dest, "local-c1") == prior

    # an unknown id is refused whole: nothing is written, nothing is received
    settled = _state(dest)
    _prev, unknown = cap.imported(
        dest, capsule_file, transport="cli", mapping_id=mapping_id, confirm=["zz"]
    )
    assert unknown.code == "E_INPUT", unknown
    assert _state(dest) == settled

    # the preview binds the selection: changed and omitted ids conflict, none writes
    base = {
        "input": str(capsule_file),
        "mapping_id": mapping_id,
        "invocation_id": cap.new_uuid(),
    }
    bound = cap.call(
        "cli",
        dest.root,
        {**base, "action": "preview_import", "confirm_constraint_ids": ["c1"]},
    )
    assert bound.code == "OK", bound
    apply_request = {
        **base,
        "action": "import",
        "apply": True,
        "expected_digest": bound.data["digest"],
        "expected_store_revision": cap.preview_store_revision(bound.data),
    }
    for label, confirm in (
        ("omitted", None),
        ("changed", ["c1", "c2"]),
        ("other", ["c2"]),
    ):
        request = dict(apply_request)
        if confirm is not None:
            request["confirm_constraint_ids"] = confirm
        res = cap.call("cli", dest.root, request)
        cap.assert_denied(res, "E_VERSION", "recovery_required")
        assert _state(dest) == settled, label
    committed = cap.call(
        "cli", dest.root, {**apply_request, "confirm_constraint_ids": ["c1"]}
    )
    assert committed.code == "OK", committed
    assert len(cap.imported_rows(dest)) == 15

    # a failure mid-transaction rolls back every row, receipt and revision it wrote
    existing = len(cap.imported_rows(dest))
    _plant_import_failure(dest, existing + 2)
    settled = _state(dest)
    invocation = cap.new_uuid()
    again, failed = cap.imported(
        dest,
        capsule_file,
        transport="cli",
        mapping_id=mapping_id,
        invocation_id=invocation,
        confirm=["c2"],
    )
    assert again.code == "OK" and failed.code != "OK", failed
    assert _state(dest) == settled
    assert cap.row_of(dest, "local-c1") == prior
    cap.raw_sql(dest, "DROP TRIGGER planted_failure")
    _prev, retried = cap.imported(
        dest,
        capsule_file,
        transport="cli",
        mapping_id=mapping_id,
        invocation_id=invocation,
        confirm=["c2"],
    )
    assert retried.code == "OK" and not retried.data.get("replayed"), retried
    assert len(cap.imported_rows(dest)) == existing + 5


def test_preview_no_files_then_atomic_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cap.assert_preservation_oracle_complete(tmp_path)
    dest = cap.make_env(tmp_path, "dest", create_store=False)
    raw = cap.fixture_bytes("rush_v1_two_constraints_two_evidence.json")
    capsule_file = dest.outside / "claimed.json"
    capsule_file.write_bytes(cap._with_origin(raw, dest.project_id, dest.worktree_id))
    before = dest.effects()
    for transport in ("inproc", "cli"):
        preview = cap.call(
            transport,
            dest.root,
            {
                "action": "preview_import",
                "input": str(capsule_file),
                "invocation_id": cap.new_uuid(),
            },
        )
        assert preview.code == "OK", (transport, preview)
        assert dest.effects() == before, transport
        assert not (dest.root / ".rush").exists(), transport
        assert not (dest.data_root / "dashboard" / "project_locks").exists()

    # the store appears only by publishing a complete database in one step
    observed: list[tuple[bool, int]] = []

    def watching(real: Any) -> Any:
        def wrapper(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
            if os.path.basename(os.fspath(dst)) == "memory.db":
                with contextlib.closing(
                    sqlite3.connect(f"file:{os.fspath(src)}?mode=ro", uri=True)
                ) as conn:
                    count = conn.execute(
                        "SELECT COUNT(*) FROM memory_artifacts "
                        "WHERE trust_tier = 'IMPORTED'"
                    ).fetchone()[0]
                observed.append((os.path.exists(dst), int(count)))
            return real(src, dst, *args, **kwargs)

        return wrapper

    for name in ("replace", "rename", "link"):
        monkeypatch.setattr(os, name, watching(getattr(os, name)))
    _preview, done = cap.imported(dest, capsule_file)
    assert done.code == "OK", done
    assert observed and set(observed) == {(False, 5)}, observed
    assert len(cap.imported_rows(dest)) == 5
    monkeypatch.undo()

    # an existing store applies all-or-nothing as well
    live = cap.make_env(tmp_path, "live")
    live_file = cap.export_file(live, "live.json")
    _plant_import_failure(live, 2)
    settled = _state(live)
    preview, failed = cap.imported(live, live_file)
    assert preview.code == "OK" and failed.code != "OK", failed
    assert _state(live) == settled


def test_changed_capsule_policy_and_artifact_version_conflict(tmp_path: Path) -> None:
    from rush.memory import authorization as auth

    env = cap.make_env(tmp_path, "dest")
    assert env.store is not None and env.grant is not None
    env.store.write(
        MemoryArtifact(
            id="local-c1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"kind": "constraint", "constraint_id": "c1", "text": "local"},
            source=cap.SRC,
            created_at=time.time(),
            owner_scope=env.owner,
        )
    )
    capsule_file = cap.export_file(env, "conflict.json")

    def previewed() -> dict[str, Any]:
        base = {"input": str(capsule_file), "invocation_id": cap.new_uuid()}
        preview = cap.call_inproc(env.root, {**base, "action": "preview_import"})
        assert preview.code == "OK", preview
        versions = preview.data.get("expected_versions")
        if versions is None:
            versions = preview.data["preview_binding"]["existing_versions"]
        assert versions == {"local-c1": cap.row_of(env, "local-c1")["artifact_version"]}
        return {
            **base,
            "action": "import",
            "apply": True,
            "expected_digest": preview.data["digest"],
            "expected_store_revision": cap.preview_store_revision(preview.data),
        }

    def refused(request: dict[str, Any], code: str, reason: str, label: str) -> None:
        settled = _state(env)
        res = cap.call_inproc(env.root, request)
        cap.assert_denied(res, code, reason)
        assert _state(env) == settled, label

    # the capsule bytes changed since the preview
    request = previewed()
    capsule_file.write_bytes(
        cap.mutated_capsule(
            capsule_file.read_bytes(),
            lambda d: d["task"].__setitem__("description", "changed after preview"),
        )
    )
    refused(request, "E_VERSION", "recovery_required", "capsule bytes")

    # the policy revision changed since the preview
    capsule_file = cap.export_file(env, "conflict2.json")
    request = previewed()
    cap.make_env(tmp_path, "unrelated-project")
    refused(request, "E_VERSION", "recovery_required", "policy revision")

    # a local artifact version moved since the preview
    request = previewed()
    env.store.edit(
        "local-c1",
        {"kind": "constraint", "constraint_id": "c1", "text": "edited locally"},
        expected_version=1,
        scope="domain_knowledge",
        owner_scope=env.owner,
        apply=True,
    )
    assert cap.row_of(env, "local-c1")["artifact_version"] == 2
    refused(request, "E_VERSION", "store_changed", "artifact version")

    # the grant was revoked since the preview: the policy denies before any write
    request = previewed()
    auth.revoke_memory_scope(
        grant_id=env.grant["grant_id"],
        expected_policy_revision=cap.revision_of(env.data_root),
        consent=True,
        data_root=env.data_root,
    )
    refused(request, "E_PERMISSION", "revoked", "grant")
    assert not cap.imported_rows(env)


def test_replay_and_distinct_import_identity(tmp_path: Path) -> None:
    env = cap.make_env(tmp_path, "dest")
    capsule_file = cap.export_file(env, "identity.json")
    first_invocation = cap.new_uuid()
    base = {"input": str(capsule_file), "invocation_id": first_invocation}
    preview = cap.call_inproc(env.root, {**base, "action": "preview_import"})
    request = {
        **base,
        "action": "import",
        "apply": True,
        "expected_digest": preview.data["digest"],
        "expected_store_revision": cap.preview_store_revision(preview.data),
    }
    first = cap.call_inproc(env.root, request)
    assert first.code == "OK", first
    rows = cap.imported_rows(env)
    receipts = _receipts(env)
    assert len(rows) == 5

    # the identical request replays the stored receipt: no new row, receipt or revision
    settled = _state(env)
    replay = cap.call_inproc(env.root, request)
    assert replay.code == "OK" and replay.data["replayed"] is True, replay
    assert replay.data["effect_id"] == first.data["effect_id"]
    assert replay.data["mappings"] == first.data["mappings"]
    assert _state(env) == settled and _receipts(env) == receipts

    # another invocation of the same capsule is another effect with its own identity
    _prev, second = cap.imported(env, capsule_file)
    assert second.code == "OK" and not second.data.get("replayed"), second
    assert second.data["effect_id"] != first.data["effect_id"]
    assert second.data["invocation_id"] != first.data["invocation_id"]
    assert len(cap.imported_rows(env)) == 10
    assert all(cap.row_of(env, r["id"]) == r for r in rows), (
        "the first import is intact"
    )
    after = _receipts(env)
    assert len(after) == len(receipts) + 1
    assert second.data["effect_id"] in json.dumps(after[-1], default=str)

    # the same invocation over different capsule bytes is a conflict, not a replay
    other = tmp_path / "other-bytes.json"
    other.write_bytes(
        cap.mutated_capsule(
            capsule_file.read_bytes(),
            lambda d: d["task"].__setitem__("description", "different capsule"),
        )
    )
    changed_base = {"input": str(other), "invocation_id": first_invocation}
    changed_preview = cap.call_inproc(
        env.root, {**changed_base, "action": "preview_import"}
    )
    assert changed_preview.code == "OK", changed_preview
    settled = _state(env)
    conflict = cap.call_inproc(
        env.root,
        {
            **changed_base,
            "action": "import",
            "apply": True,
            "expected_digest": changed_preview.data["digest"],
            "expected_store_revision": cap.preview_store_revision(changed_preview.data),
        },
    )
    cap.assert_denied(conflict, "E_VERSION", "effect_digest_conflict")
    assert _state(env) == settled

    # the same invocation into another store is another target, so another identity
    elsewhere = cap.make_env(tmp_path, "elsewhere")
    foreign_file = elsewhere.outside / "identity.json"
    foreign_file.write_bytes(
        cap._with_origin(
            capsule_file.read_bytes(), elsewhere.project_id, elsewhere.worktree_id
        )
    )
    moved_base = {"input": str(foreign_file), "invocation_id": first_invocation}
    moved_preview = cap.call_inproc(
        elsewhere.root, {**moved_base, "action": "preview_import"}
    )
    moved = cap.call_inproc(
        elsewhere.root,
        {
            **moved_base,
            "action": "import",
            "apply": True,
            "expected_digest": moved_preview.data["digest"],
            "expected_store_revision": cap.preview_store_revision(moved_preview.data),
        },
    )
    assert moved.code == "OK" and not moved.data.get("replayed"), moved
    assert moved.data["effect_id"] != first.data["effect_id"]


def test_export_personal_scope_and_required_secret_redaction(tmp_path: Path) -> None:
    env = cap.make_env(tmp_path, "project")
    owner = cap.overlay_owner(env)
    overlay_root = env.data_root / "user"
    overlay_root.mkdir(parents=True, exist_ok=True)
    overlay_store = TypedArtifactStore(overlay_root)
    cap.put_evidence(
        env, "ov1", owner=owner, source=cap.OVERLAY_SRC, store=overlay_store
    )
    stored = json.loads(cap.row_of(env, "cp1")["content"])
    stored["evidence_refs"] = [
        *stored["evidence_refs"],
        {"artifact_id": "ov1", "version": 1},
    ]
    cap.plant_content(env, "cp1", stored)
    personal: dict[str, Any] = {"selectors": {"include_personal": True}}

    def preview(name: str, fmt: str = "rush_v1", **extra: Any) -> Any:
        return cap.call_inproc(
            env.root,
            {
                "action": "preview_export",
                "format": fmt,
                "output": str(env.outside / name),
                "invocation_id": cap.new_uuid(),
                **extra,
            },
        )

    # include_personal without the overlay grant is refused by the owner check
    denied = preview("no-grant.json", **personal)
    cap.assert_denied(denied, "E_OWNER", "owner_not_granted")
    cap.grant_for(
        env.root,
        owner,
        env.data_root,
        sources=(cap.OVERLAY_SRC, cap.IMPORT_SRC),
        ops=("overlay_read", "expand"),
    )

    # a personal ref without include_personal blocks the export, grant or not
    before = env.effects()
    blocked = preview("personal.json")
    cap.assert_denied(blocked, "E_PERMISSION", "export_blocked")
    assert env.effects() == before and not (env.outside / "personal.json").exists()

    # with include_personal and the overlay grant the personal evidence is exported
    out, _p, done = cap.exported(env, "personal.json", **personal)
    assert done.code == "OK", done
    document = cap.verify_rush_v1(out.read_bytes())
    assert "ov1" in [e["artifact_id"] for e in document["evidence"]]
    assert document["scope"]["personal_owner"] == cap.owner_hex(owner)

    # a required body holding a secret is blocked whole: no output, no store change
    secret = "ghp_" + "a" * 36
    clean_ev1 = json.loads(cap.row_of(env, "ev1")["content"])
    for fmt in ("rush_v1", "pas_v1"):
        name = f"secret-{fmt}.json"
        base = {
            "format": fmt,
            "output": str(env.outside / name),
            "invocation_id": cap.new_uuid(),
            **personal,
        }
        clean = cap.call_inproc(env.root, {**base, "action": "preview_export"})
        assert clean.code == "OK", clean
        cap.plant_content(env, "ev1", {"note": f"token {secret}"})
        before = env.effects()
        blocked = cap.call_inproc(env.root, {**base, "action": "preview_export"})
        cap.assert_denied(blocked, "E_PERMISSION", "export_blocked")
        assert "digest" not in blocked.data
        final = cap.call_inproc(
            env.root,
            {**base, "action": "export", "expected_digest": clean.data["digest"]},
        )
        cap.assert_denied(final, "E_PERMISSION", "export_blocked")
        assert not (env.outside / name).exists()
        assert env.effects() == before
        assert secret not in json.dumps(blocked.raw) + json.dumps(final.raw)
        cap.plant_content(env, "ev1", clean_ev1)

    # the same secret in a personal body is blocked as well
    overlay_env = _overlay_rows(env)
    cap.plant_content(overlay_env, "ov1", {"note": f"token {secret}"})
    blocked = preview("personal-secret.json", **personal)
    cap.assert_denied(blocked, "E_PERMISSION", "export_blocked")

    # control: with clean required bodies the export succeeds and holds no token
    cap.plant_content(overlay_env, "ov1", cap.evidence_body("ov1"))
    out, _p, done = cap.exported(env, "clean.json", **personal)
    assert done.code == "OK", done
    assert secret.encode() not in out.read_bytes()


def test_import_review_cli_tui_same_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R13 (72-T07): the CLI and the TUI review one imported capsule to the same state.

    One capsule exported from a project is previewed by `rush memory capsule
    preview-import` and by the TUI's `I` form: the records, store revision and capsule
    digest are equal. After the TUI applies it, the CLI `list --json` row and the TUI
    list row of every imported record agree on `(id, artifact_version, trust_tier)` and
    both show the pending applicability; an explicit CLI confirmation moves both."""
    import json

    from click.testing import CliRunner

    from rush.cli import cli
    from rush.memory import authorization as auth
    from rush.memory.retrieval import MemoryAccess
    from rush.setup.provision import default_data_root
    from rush.tui import (
        ProjectState,
        TuiState,
        _dispatch_key,
        _pump,
        default_scan_actions,
    )

    data_root = default_data_root()
    root = tmp_path / "project"
    root.mkdir()
    root = root.resolve()
    register_project(root, data_root=data_root)
    store = TypedArtifactStore(root)
    for artifact_id, text in (
        ("evidence-a", "needle evidence a"),
        ("evidence-b", "needle b"),
    ):
        store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject=SUBJECT,
                trust_tier="EXTERNAL_WRITE",
                content={"text": text},
                source="r13-src",
                created_at=time.time(),
                owner_scope=ALICE,
            )
        )
    revision = int(
        auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0
    )
    auth.grant_memory_scope(
        project_root=root,
        owner_scope=ALICE,
        approved_sources=["r13-src"],
        allowed_operations=["ask", "expand", "list", "history", "write"],
        expected_policy_revision=revision,
        consent=True,
        data_root=data_root,
    )
    access = MemoryAccess.resolve(
        root, operation="ask", owner_scope=ALICE, data_root=data_root
    )
    assert access is not None
    checkpoint = {
        "kind": "checkpoint",
        "schema_version": 1,
        "project_id": access.project_id,
        "worktree_id": access.worktree_id,
        "task_id": "r13-task",
        "event_kind": "checkpoint",
        "description": "review the import",
        "objective": "one state in the CLI and the TUI",
        "next_action": "confirm the constraint",
        "implemented": ["export"],
        "unresolved": ["import review"],
        "decisions": [{"text": "review before apply", "origin_ref": "plan"}],
        "blockers": [],
        "discoveries": [],
        "disproved": [],
        "requirements": [
            {
                "id": "c1",
                "text": "never skip review",
                "authority": "user",
                "provenance": "plan",
            }
        ],
        "checks": [
            {
                "command": ["pytest"],
                "exit_code": 0,
                "status": "passed",
                "source_revision": "rev1",
                "receipt_id": "receipt-1",
            }
        ],
        "evidence_refs": [
            {"artifact_id": "evidence-a", "version": 1},
            {"artifact_id": "evidence-b", "version": 1},
        ],
        "source": {"commit": None, "branch": None, "dirty": False},
    }
    store.write(
        MemoryArtifact(
            id="r13-checkpoint",
            family="experience",
            subject="episodic",
            trust_tier="EXTERNAL_WRITE",
            content=checkpoint,
            source="r13-src",
            created_at=time.time(),
            owner_scope=ALICE,
        )
    )
    monkeypatch.chdir(root)
    runner = CliRunner()

    def run_cli(*args: str, allow: tuple[str, ...] = ()) -> dict[str, Any]:
        result = runner.invoke(cli, ["memory", *args, *allow, "--json"])
        assert result.stdout, (args, result.output)
        return json.loads(result.stdout)

    capsule = tmp_path / "review.rush-capsule.json"
    preview = run_cli("capsule", "preview-export", "--output", str(capsule))
    assert preview["raw"]["code"] == "OK", preview
    exported = run_cli(
        "capsule",
        "export",
        "--output",
        str(capsule),
        "--invocation-id",
        preview["raw"]["data"]["invocation_id"],
        "--expected-digest",
        preview["raw"]["data"]["digest"],
        allow=("--allow-artifact-write",),
    )
    assert exported["raw"]["code"] == "OK", exported
    assert capsule.is_file()

    # CLI preview.
    cli_preview = run_cli("capsule", "preview-import", "--input", str(capsule))
    assert cli_preview["raw"]["code"] == "OK", cli_preview
    cli_data = cli_preview["raw"]["data"]

    # TUI preview through the `I` form with the same file.
    actions = default_scan_actions()
    state = TuiState(
        projects=[ProjectState(name="r13", root=root, project_id=access.project_id)],
        data_root=data_root,
    )
    state.memory_owner_scope_kind, state.memory_owner_scope_id = "user", "alice"
    state.terminal_size = (160, 50)

    def keys(*pressed: str) -> None:
        for key in pressed:
            _dispatch_key(state, key, actions)
            for _ in range(400):
                _pump(state, actions)
                if state.memory_request is None:
                    break
                time.sleep(0.005)

    keys("f3", "4", "I")
    assert state.mode == "memory_import"
    keys(*str(capsule), "enter")
    tui_data = (state.memory_import_preview or {}).get(
        "data", state.memory_import_preview
    )
    assert tui_data, state.memory_message
    for key in ("records", "store_revision", "capsule_digest"):
        assert tui_data[key] == cli_data[key], key
    # The digest and the invocation id belong to one preview and differ per call.
    assert tui_data["invocation_id"] and tui_data["digest"]

    keys("y")

    # After the TUI import, the CLI list and the TUI list agree on every imported row.
    listed = run_cli("list")
    cli_rows = {
        (r["reference"]["artifact_id"], r["reference"]["artifact_version"]): r
        for r in listed["raw"]["items"]
        if r["reference"]["trust_tier"] == "IMPORTED"
    }
    assert cli_rows, "the import wrote no IMPORTED row"
    tui_rows: dict[tuple[str, int], str] = {}
    for subject in sorted({r["reference"]["subject"] for r in cli_rows.values()}):
        for _ in range(8):
            if state.memory_subject == subject:
                break
            keys("S")
        keys("/", "enter")
        view = state.memory_view_state or {}
        badges = {row["artifact_id"]: row["badges"] for row in view.get("rows", [])}
        for item in state.memory_items:
            ref = item["reference"]
            if ref["trust_tier"] == "IMPORTED":
                row_key = (ref["artifact_id"], ref["artifact_version"])
                tui_rows[row_key] = ",".join(badges.get(ref["artifact_id"], []))
    assert set(tui_rows) == set(cli_rows), (tui_rows, cli_rows)
    for row_key, row in cli_rows.items():
        assert row.get("applicability") == "pending", row
        assert "pending" in tui_rows[row_key].split(","), (row_key, tui_rows[row_key])
