"""72-T01: safe reads, authority and symbol containment (T004 design gate, §5).

Every test imports the T01 symbols (`MemoryAccess`, `evaluate_artifact_visibility`,
...) inside its own body so each one fails on its own until T01 lands. The
module-level imports below are existing code only.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from rush.memory.store import (
    MemoryArtifact,
    OwnerScope,
    TypedArtifactStore,
    legacy_owner_scope,
    readonly_view_reason,
)
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.tools.memory import MemoryTool
from rush.workflows.projects import register_project

SUBJECT = "domain_knowledge"
ALICE = OwnerScope("user", "alice")
BOB = OwnerScope("user", "bob")
DAY = 86400.0
KNOWN_SRC = "def Known():\n    return 1\n"
PAYLOAD_COLUMNS = ("payload_hash", "payload_hash_origin")
OVERLAY_SOURCE = "personal-preferences"


# --- helpers (existing code and stdlib only) --------------------------------


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _payload_sha(content: dict[str, Any]) -> str:
    return _sha_text(json.dumps(content))


def _git(root: Path, *args: str) -> None:
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


def _git_repo(root: Path, files: dict[str, str], *, branch: str = "main") -> Path:
    root.mkdir(parents=True)
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(root, "init", f"--initial-branch={branch}")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "fixture")
    return root.resolve()


def _row(
    store: TypedArtifactStore,
    artifact_id: str,
    owner: OwnerScope | None,
    marker: str,
    *,
    source: str = "source-a",
    subject: str = SUBJECT,
    trust: str = "DERIVED",
    created_at: float | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
    content: dict[str, Any] | None = None,
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject=subject,  # type: ignore[arg-type]
            trust_tier=trust,  # type: ignore[arg-type]
            content=content if content is not None else {"text": f"needle {marker}"},
            source=source,
            created_at=created_at if created_at is not None else time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
            owner_scope=owner,
        )
    )


def _version(db: Path, artifact_id: str) -> int:
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT artifact_version FROM memory_artifacts WHERE id = ?",
            (artifact_id,),
        ).fetchone()
    assert row is not None, artifact_id
    return int(row[0])


def _tamper(db: Path, artifact_id: str) -> None:
    """Rewrite the current row's persisted payload (and its version row) behind the
    store's back, keeping it valid JSON."""
    version = _version(db, artifact_id)
    with sqlite3.connect(db) as conn:
        (raw,) = conn.execute(
            "SELECT content FROM memory_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        content = json.loads(raw)
        content["tampered"] = True
        text = json.dumps(content)
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = ?", (text, artifact_id)
        )
        conn.execute(
            "UPDATE memory_artifact_versions SET content = ? "
            "WHERE artifact_id = ? AND artifact_version = ?",
            (text, artifact_id, version),
        )
        conn.commit()


def _break_signature(db: Path, artifact_id: str) -> None:
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET signature = ? WHERE id = ?",
            ("0" * 64, artifact_id),
        )
        conn.commit()


def _columns(db: Path, table: str) -> set[str]:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _payload_row(db: Path, artifact_id: str) -> tuple[Any, Any]:
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT payload_hash, payload_hash_origin FROM memory_artifacts "
            "WHERE id = ?",
            (artifact_id,),
        ).fetchone()
    assert row is not None, artifact_id
    return row[0], row[1]


def _payload_version_row(db: Path, artifact_id: str, version: int) -> tuple[Any, ...]:
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT content, payload_hash, payload_hash_origin "
            "FROM memory_artifact_versions "
            "WHERE artifact_id = ? AND artifact_version = ?",
            (artifact_id, version),
        ).fetchone()
    assert row is not None, (artifact_id, version)
    return tuple(row)


def _drop_payload_columns(db: Path) -> None:
    """An older T01-era database: both payload columns removed from both tables."""
    for table in ("memory_artifacts", "memory_artifact_versions"):
        missing = set(PAYLOAD_COLUMNS) - _columns(db, table)
        assert not missing, f"{table} has no payload columns to drop: {missing}"
    with contextlib.closing(sqlite3.connect(db)) as conn:
        for table in ("memory_artifacts", "memory_artifact_versions"):
            for column in PAYLOAD_COLUMNS:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()


def _ids(page: dict[str, Any]) -> list[str]:
    return [item["id"] for item in page["items"]]


def _dump(value: Any) -> str:
    def default(obj: Any) -> Any:
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        return str(obj)

    return json.dumps(value, default=default, sort_keys=True)


def _assert_not(decision: Any) -> None:
    assert decision.visible is False
    assert decision.usable_as_current is False
    assert decision.freshness == "unknown"
    assert tuple(decision.reason_codes) == ("not_visible",)
    assert decision.reference is None


def _grant(
    auth: Any,
    root: Path,
    owner: OwnerScope,
    data_root: Path,
    *,
    sources: tuple[str, ...] = ("source-a",),
    ops: tuple[str, ...] = ("ask", "expand", "list"),
) -> dict[str, Any]:
    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )


def _revision(auth: Any, data_root: Path) -> int:
    return int(auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0)


def _registered(path: Path, data_root: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    register_project(path, data_root=data_root)
    return path.resolve()


def _raw(result: Any) -> dict[str, Any]:
    return result["raw"]


def _items(result: Any) -> list[dict[str, Any]]:
    return list(_raw(result).get("data", {}).get("items") or [])


def _embed_spy() -> tuple[list[list[str]], Any]:
    calls: list[list[str]] = []

    def embed(config: Any, texts: Any) -> list[list[float]]:
        calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]

    return calls, embed


def _embed_config() -> Any:
    from rush.memory.embeddings import EmbeddingConfig

    return EmbeddingConfig(
        endpoint="http://127.0.0.1:9/embed", model="fixture", model_digest="d0"
    )


def _pause_first_call(monkeypatch: Any, module: Any, name: str) -> tuple[Any, Any]:
    entered, release = threading.Event(), threading.Event()
    original = getattr(module, name)
    calls = {"n": 0}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            entered.set()
            release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, name, wrapper)
    return entered, release


def _run_in_thread(func: Any) -> tuple[threading.Thread, dict[str, Any]]:
    box: dict[str, Any] = {}

    def target() -> None:
        box["result"] = func()

    thread = threading.Thread(target=target)
    thread.start()
    return thread, box


def _no_sidecars(db: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        assert not Path(f"{db}{suffix}").exists(), f"{db}{suffix}"


def _paging_key_rows(db: Path) -> int:
    uri = f"file:{db}?immutable=1"
    with sqlite3.connect(uri, uri=True) as conn:
        names = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "memory_cursor_key" not in names:
            return 0
        return int(conn.execute("SELECT COUNT(*) FROM memory_cursor_key").fetchone()[0])


# --- 1 ----------------------------------------------------------------------


def test_t01_denied_current_routes_and_authority(tmp_path: Path) -> None:
    from rush.memory import authorization as auth
    from rush.memory.expiry import sweep_expired
    from rush.memory.retrieval import (
        MemoryAccess,
        defended_recall,
        evaluate_artifact_visibility,
        expand_artifact,
        hybrid_page,
        recall_page,
    )

    data_root = tmp_path / "user-data"
    root = _git_repo(tmp_path / "project", {"src_mod.py": KNOWN_SRC}, branch="trunk")
    register_project(root, data_root=data_root)
    store = TypedArtifactStore(root)
    now = time.time()
    markers = {
        "row-a1": "mk-a1-alpha",
        "row-a2": "mk-a2-bravo",
        "row-a3": "mk-a3-charlie",
        "row-b1": "mk-b1-delta",
        "row-u1": "mk-u1-echo",
        "row-t1": "mk-t1-foxtrot",
    }
    _row(store, "row-a1", ALICE, markers["row-a1"])
    _row(store, "row-a2", ALICE, markers["row-a2"])
    _row(store, "row-a3", ALICE, markers["row-a3"], created_at=now - 30 * DAY)
    _row(store, "row-b1", BOB, markers["row-b1"])
    _row(
        store,
        "row-u1",
        ALICE,
        markers["row-u1"],
        symbol_ref="src_mod.py::Known",
        content_hash=_sha_file(root / "src_mod.py"),
    )
    _row(store, "row-t1", ALICE, markers["row-t1"])
    store.archive(
        "row-a2", expected_version=1, scope=SUBJECT, owner_scope=ALICE, apply=True
    )
    assert sweep_expired(root, owner_scope=ALICE, candidate_ids=["row-a3"]) == 1
    _, promotion = store.promote(
        "row-t1", user_stated=True, expected_version=1, owner_scope=ALICE
    )
    assert promotion.promoted is True
    _tamper(store.db_path, "row-t1")
    excluded = ["row-a2", "row-a3", "row-b1", "row-u1", "row-t1"]

    _grant(auth, root, ALICE, data_root)
    ask = MemoryAccess.resolve(root, operation="ask", data_root=data_root)
    expand = MemoryAccess.resolve(root, operation="expand", data_root=data_root)
    assert ask is not None and expand is not None
    assert ask.historical_allowed is False

    page = recall_page(
        store, subject=SUBJECT, query="needle", access=ask, limit=20, now=time.time()
    )
    assert _ids(page) == ["row-a1"]

    calls, embed = _embed_spy()
    hybrid = hybrid_page(
        store,
        subject=SUBJECT,
        query="needle",
        access=ask,
        embed_config=_embed_config(),
        embed_fn=embed,
        limit=20,
    )
    assert _ids(hybrid) == ["row-a1"]
    embedded = [text for batch in calls for text in batch if text != "needle"]
    assert embedded and all(markers["row-a1"] in text for text in embedded)

    defended = defended_recall(store, SUBJECT, "needle", None, access=ask)
    assert [a.id for a in defended] == ["row-a1"]

    view, state = TypedArtifactStore.open_readonly_view(root)
    assert view is not None, state
    try:
        viewed = view.recall(SUBJECT, "needle", access=ask, mode="ordinary")
    finally:
        view.close()
    assert [a.id for a in viewed] == ["row-a1"]

    ordinary_json = _dump([page, hybrid, defended, viewed, calls])
    for artifact_id in excluded:
        assert artifact_id not in ordinary_json
        assert markers[artifact_id] not in ordinary_json

    ok = expand_artifact(
        store, artifact_id="row-a1", version=1, access=expand, now=time.time()
    )
    assert ok["code"] == "OK"
    missing = expand_artifact(store, artifact_id="zz-missing", version=1, access=expand)
    assert missing["code"] == "E_NOT_VISIBLE"
    baseline = {k: v for k, v in missing.items() if k != "id"}
    denials = [
        expand_artifact(
            store,
            artifact_id=artifact_id,
            version=_version(store.db_path, artifact_id),
            access=expand,
        )
        for artifact_id in excluded
    ]
    denials.append(
        expand_artifact(
            store,
            artifact_id="row-b1",
            version=_version(store.db_path, "row-b1") + 5,
            access=expand,
        )
    )
    for denial in denials:
        assert denial["code"] == "E_NOT_VISIBLE"
        assert {k: v for k, v in denial.items() if k != "id"} == baseline
    denial_json = _dump(denials)
    for artifact_id in excluded:
        assert markers[artifact_id] not in denial_json

    # Historical mode under ask access is not authorized.
    for artifact_id in excluded:
        _assert_not(
            evaluate_artifact_visibility(
                store,
                store.get_current(artifact_id),
                access=ask,
                mode="historical",
            )
        )

    _grant(auth, root, ALICE, data_root, ops=("ask", "expand", "list", "history"))
    history = MemoryAccess.resolve(root, operation="historical", data_root=data_root)
    assert history is not None and history.historical_allowed is True

    def historical(artifact_id: str) -> Any:
        return evaluate_artifact_visibility(
            store, store.get_current(artifact_id), access=history, mode="historical"
        )

    expected = {
        "row-a2": ("archived",),
        "row-a3": ("expired",),
        "row-u1": ("api_baseline_unknown",),
        "row-t1": ("integrity_payload_mismatch", "integrity_signature_mismatch"),
    }
    for artifact_id, reasons in expected.items():
        decision = historical(artifact_id)
        assert decision.visible is True, artifact_id
        assert decision.usable_as_current is False, artifact_id
        assert tuple(decision.reason_codes) == reasons, artifact_id
    assert historical("row-u1").freshness == "unknown"
    current = historical("row-a1")
    assert current.visible is True and current.usable_as_current is True
    assert current.freshness == "not_applicable"

    for mode, access in (("ordinary", ask), ("inspect", ask), ("historical", history)):
        _assert_not(
            evaluate_artifact_visibility(
                store, store.get_current("row-b1"), access=access, mode=mode
            )
        )


# --- 2 ----------------------------------------------------------------------


def _containment_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, TypedArtifactStore, dict[str, Any], TypedArtifactStore]:
    """Test 2's repo, rows and non-git root (shared with the X5 test)."""
    outside = tmp_path / "outside.py"
    outside.write_text(KNOWN_SRC, encoding="utf-8")
    root = _git_repo(
        tmp_path / "repo",
        {
            "pkg/mod.py": KNOWN_SRC + "\n\ndef Other(a):\n    return a\n",
            "bad_base.py": "def Fixed(:\n",
            "pkg/broken.py": "def Gone():\n    return 1\n",
            "web/app.js": "function Known() { return 1; }\n",
        },
    )
    (root / "pkg/mod.py").write_text(KNOWN_SRC, encoding="utf-8")
    (root / "bad_base.py").write_text("def Fixed():\n    return 1\n", encoding="utf-8")
    (root / "pkg/broken.py").write_text("def Gone(:\n", encoding="utf-8")
    (root / "link.py").symlink_to(outside)
    store = TypedArtifactStore(root)
    mod_hash = _sha_file(root / "pkg/mod.py")
    rows: dict[str, tuple[str | None, str | None, str, tuple[str, ...]]] = {
        "c1": ("pkg/mod.py::Known", mod_hash, "current", ()),
        "r1": ("pkg/mod.py::Other", mod_hash, "stale", ("api_changed",)),
        "h1": ("pkg/mod.py::Known", "0" * 64, "stale", ("source_hash_mismatch",)),
        "n1": ("pkg/mod.py::Known", None, "unknown", ("source_hash_missing",)),
        "j1": (
            "web/app.js::Known",
            _sha_file(root / "web/app.js"),
            "unknown",
            ("parser_unsupported",),
        ),
        "bb1": (
            "bad_base.py::Fixed",
            _sha_file(root / "bad_base.py"),
            "unknown",
            ("api_baseline_unknown",),
        ),
        "br1": (
            "pkg/broken.py::Gone",
            _sha_file(root / "pkg/broken.py"),
            "unknown",
            ("api_baseline_unknown",),
        ),
        "o1": (
            "../outside.py::Known",
            _sha_file(outside),
            "unknown",
            ("source_not_contained",),
        ),
        "ab1": (
            f"{outside}::Known",
            _sha_file(outside),
            "unknown",
            ("source_not_contained",),
        ),
        "l1": (
            "link.py::Known",
            _sha_file(outside),
            "unknown",
            ("source_not_contained",),
        ),
        "m1": ("missing.py::Known", "0" * 64, "unknown", ("source_missing",)),
        "x1": ("pkg/mod.py", mod_hash, "unknown", ("symbol_ref_malformed",)),
        "unanchored": (None, None, "not_applicable", ()),
    }
    for artifact_id, (ref, digest, _, _) in rows.items():
        _row(
            store,
            artifact_id,
            None,
            f"mk-{artifact_id}",
            source="src",
            symbol_ref=ref,
            content_hash=digest,
        )

    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "mod.py").write_text(KNOWN_SRC, encoding="utf-8")
    plain_store = TypedArtifactStore(plain)
    _row(
        plain_store,
        "g1",
        None,
        "mk-g1",
        source="src",
        symbol_ref="mod.py::Known",
        content_hash=_sha_file(plain / "mod.py"),
    )
    return root, outside, store, rows, plain_store


@pytest.mark.posix_only
def test_t01_symbol_containment_and_unknown_freshness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import retrieval
    from rush.memory.retrieval import defended_recall, recall_page
    from rush.memory.trust import evaluate_promotion, resolve_symbol_ref
    from rush.tools.api_diff import ApiDiffer

    root, outside, store, rows, plain_store = _containment_fixture(tmp_path)
    outside_real = outside.resolve()

    reads: list[Path] = []
    original_read_text = Path.read_text

    def spy_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(Path(os.path.realpath(self)))
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy_read_text)

    contained = {
        "pkg/mod.py::Known": True,
        "pkg/mod.py::Missing": False,
        f"{outside}::Known": False,
        "../outside.py::Known": False,
        "link.py::Known": False,
    }
    for ref, expected in contained.items():
        assert resolve_symbol_ref(ref, root) is expected, ref
    assert outside_real not in reads

    differ = ApiDiffer(project_root=root)
    assert differ.diff_symbol(root / "web/app.js", "Known") == "unknown"
    assert differ.diff_symbol(root / "pkg/broken.py", "Gone") == "unknown"
    assert differ.diff_symbol(root / "bad_base.py", "Fixed") == "unknown"
    assert differ.diff_symbol(outside, "Known") == "unknown"
    removed = differ.diff_symbol(root / "pkg/mod.py", "Other")
    assert isinstance(removed, dict) and removed["symbol"] == "Other"
    assert differ.diff_symbol(root / "pkg/mod.py", "Known") is None
    assert outside_real not in reads

    hashed: list[Path] = []
    diffed: list[Path] = []
    original_hash = retrieval.SourceValidationMemo.source_hash
    original_diff = ApiDiffer.diff_symbol

    def spy_hash(self: Any, file_path: Path) -> Any:
        hashed.append(Path(os.path.realpath(file_path)))
        return original_hash(self, file_path)

    def spy_diff(self: Any, file_path: Path, *args: Any, **kwargs: Any) -> Any:
        diffed.append(Path(os.path.realpath(file_path)))
        return original_diff(self, file_path, *args, **kwargs)

    monkeypatch.setattr(retrieval.SourceValidationMemo, "source_hash", spy_hash)
    monkeypatch.setattr(ApiDiffer, "diff_symbol", spy_diff)

    legacy = retrieval.MemoryAccess.legacy(root, ["src"])
    assert legacy.historical_allowed is True
    for artifact_id, (_, _, freshness, reasons) in rows.items():
        decision = retrieval.evaluate_artifact_visibility(
            store, store.get_current(artifact_id), access=legacy, mode="historical"
        )
        assert decision.visible is True, artifact_id
        assert decision.freshness == freshness, artifact_id
        assert tuple(decision.reason_codes) == reasons, artifact_id
        assert decision.usable_as_current is (
            freshness in ("current", "not_applicable")
        ), artifact_id
    plain_decision = retrieval.evaluate_artifact_visibility(
        plain_store,
        plain_store.get_current("g1"),
        access=retrieval.MemoryAccess.legacy(plain_store.project_root, ["src"]),
        mode="historical",
    )
    assert plain_decision.freshness == "unknown"
    assert tuple(plain_decision.reason_codes) == ("api_baseline_unknown",)
    assert plain_decision.usable_as_current is False

    page = recall_page(
        store, subject=SUBJECT, query="needle", session_allowlist=["src"]
    )
    assert set(_ids(page)) == {"c1", "unanchored"}
    defended = defended_recall(store, SUBJECT, "needle", ["src"])
    assert {a.id for a in defended} == {"c1", "unanchored"}

    assert outside_real not in reads
    assert outside_real not in hashed
    assert outside_real not in diffed
    assert (root / "web/app.js").resolve() not in diffed

    for ref in ("../outside.py::Known", f"{outside}::Known", "link.py::Known"):
        result = evaluate_promotion(
            MemoryArtifact(
                id="promo",
                family="memory",
                subject=SUBJECT,
                trust_tier="DERIVED",
                content={"text": "needle promo"},
                source="src",
                created_at=time.time(),
                symbol_ref=ref,
                content_hash=_sha_file(outside),
            ),
            user_stated=True,
            project_root=root,
        )
        assert result.promoted is False, ref
        assert result.denial_reason == "failed_grounding_check", ref
    assert outside_real not in reads


# --- 3 ----------------------------------------------------------------------


def test_t01_edit_and_update_content_drop_stated_authority(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    owner = legacy_owner_scope(root)
    for artifact_id in ("p-edit", "p-update"):
        _row(store, artifact_id, None, f"mk-{artifact_id}", source="src")
        _, promotion = store.promote(artifact_id, user_stated=True, expected_version=1)
        assert promotion.promoted is True
        assert store.get_current(artifact_id).trust_tier == "STATED"

    edited = {"text": "needle edited"}
    updated = {"text": "needle updated"}
    store.edit(
        "p-edit",
        edited,
        expected_version=2,
        scope=SUBJECT,
        owner_scope=owner,
        apply=True,
    )
    store.update_content("p-update", updated, expected_version=2)

    for artifact_id, content in (("p-edit", edited), ("p-update", updated)):
        current = store.get_current(artifact_id)
        assert current is not None
        assert current.content == content
        assert current.trust_tier == "DERIVED", artifact_id
        assert current.signature is None, artifact_id
        assert current.promoted_at is None, artifact_id
        with sqlite3.connect(store.db_path) as conn:
            versions = conn.execute(
                "SELECT artifact_version, trust_tier FROM memory_artifact_versions "
                "WHERE artifact_id = ? ORDER BY artifact_version",
                (artifact_id,),
            ).fetchall()
        assert [v for v, _ in versions] == [1, 2, 3], artifact_id
        assert versions[1][1] == "STATED"
        assert versions[2][1] == "DERIVED", artifact_id

    recalled = store.recall(SUBJECT, "needle", ["src"], mode="ordinary")
    assert {a.id for a in recalled} == {"p-edit", "p-update"}

    for artifact_id, content in (("p-edit", edited), ("p-update", updated)):
        digest, origin = _payload_row(store.db_path, artifact_id)
        assert digest == _payload_sha(content)
        assert origin == "write"
        _, version_digest, _ = _payload_version_row(store.db_path, artifact_id, 3)
        assert version_digest == _payload_sha(content)


# --- 4 ----------------------------------------------------------------------


def test_t01_payload_hash_written_and_tamper_excluded(tmp_path: Path) -> None:
    from rush.memory import retrieval
    from rush.memory.expiry import sweep_expired
    from rush.memory.retrieval import defended_recall, recall_page

    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    db = store.db_path
    for table in ("memory_artifacts", "memory_artifact_versions"):
        assert set(PAYLOAD_COLUMNS) <= _columns(db, table), table

    written = _row(store, "w-plain", None, "mk-plain", source="src")
    digest, origin = _payload_row(db, "w-plain")
    assert digest == _payload_sha(written.content) and origin == "write"
    content, v_digest, v_origin = _payload_version_row(db, "w-plain", 1)
    assert v_digest == _sha_text(content) == digest and v_origin == "write"
    assert store.get_version_payload("w-plain", 1) == (content, digest)
    assert store.get_version_payload("w-plain", 99) is None
    assert store.get_version_payload("zz-missing", 1) is None
    assert store.get_version_content("w-plain", 1) == content

    def assert_version_bound(artifact_id: str) -> None:
        version = _version(db, artifact_id)
        content, v_digest, v_origin = _payload_version_row(db, artifact_id, version)
        assert v_digest == _sha_text(content), artifact_id
        assert v_origin == "write", artifact_id
        assert _payload_row(db, artifact_id) == (v_digest, "write"), artifact_id
        assert store.get_version_payload(artifact_id, version) == (content, v_digest)

    _row(store, "w-archive", None, "mk-archive", source="src")
    store.archive("w-archive", expected_version=1, scope=SUBJECT, apply=True)
    assert _version(db, "w-archive") == 2
    assert_version_bound("w-archive")

    _row(store, "w-edit", None, "mk-edit", source="src")
    store.edit(
        "w-edit",
        {"text": "needle mk-edit changed"},
        expected_version=1,
        scope=SUBJECT,
        owner_scope=legacy_owner_scope(root),
        apply=True,
    )
    assert_version_bound("w-edit")

    _row(store, "w-update", None, "mk-update", source="src")
    store.update_content("w-update", {"text": "needle mk-update changed"})
    assert_version_bound("w-update")

    _row(
        store,
        "w-expire",
        None,
        "mk-expire",
        source="src",
        created_at=time.time() - 30 * DAY,
    )
    assert sweep_expired(root, candidate_ids=["w-expire"]) == 1
    assert_version_bound("w-expire")

    _row(store, "w-tampered", None, "mk-tampered", source="src")
    _tamper(db, "w-tampered")

    page = recall_page(
        store, subject=SUBJECT, query="needle", session_allowlist=["src"]
    )
    assert "w-tampered" not in _ids(page)
    assert {"w-plain", "w-edit", "w-update"} <= set(_ids(page))
    defended = defended_recall(store, SUBJECT, "needle", ["src"])
    assert "w-tampered" not in {a.id for a in defended}

    decision = retrieval.evaluate_artifact_visibility(
        store,
        store.get_current("w-tampered"),
        access=retrieval.MemoryAccess.legacy(root, ["src"]),
        mode="historical",
    )
    assert decision.visible is True
    assert decision.usable_as_current is False
    assert "integrity_payload_mismatch" in decision.reason_codes


# --- 5 ----------------------------------------------------------------------


def test_t01_policy_revocation_and_revision_change_close_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import authorization as auth
    from rush.memory import retrieval
    from rush.memory.retrieval import recall_page
    from rush.token_economy.telemetry import TelemetryStore

    data_root = default_data_root()
    root = _registered(tmp_path / "project", data_root)
    store = TypedArtifactStore(root)
    for i in range(3):
        _row(store, f"row-p{i}", ALICE, f"mk-p{i}")
    grant = _grant(auth, root, ALICE, data_root, ops=("ask", "expand"))

    tool = MemoryTool()
    perms = ExecutionPermissions(cache_write=True)

    def ask() -> Any:
        return tool.run(
            root,
            operation="ask",
            subject=SUBJECT,
            query="needle",
            request={"view": "compact", "limit": 1},
            owner_scope=ALICE.as_dict(),
            permissions=perms,
        )

    def expand() -> Any:
        return tool.run(
            root,
            operation="expand",
            request={"id": "row-p0", "version": 1},
            owner_scope=ALICE.as_dict(),
            permissions=perms,
        )

    first = ask()
    assert _raw(first)["code"] == "OK"
    assert len(_items(first)) == 1
    assert _raw(expand())["code"] == "OK"

    held = retrieval.MemoryAccess.resolve(
        root, operation="ask", owner_scope=ALICE, data_root=data_root
    )
    assert held is not None
    _grant(auth, root, BOB, data_root, ops=("ask",))
    assert held.recheck() == "changed"
    restarted = recall_page(
        store, subject=SUBJECT, query="needle", access=held, limit=1
    )
    assert restarted["code"] == "E_RESTART"
    assert restarted["items"] == []

    telemetry_before = TelemetryStore(root).get_memory_event_total()
    entered, release = _pause_first_call(monkeypatch, retrieval, "_measure_page")
    thread, box = _run_in_thread(ask)
    assert entered.wait(10)
    auth.revoke_memory_scope(
        grant_id=grant["grant_id"],
        expected_policy_revision=_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )
    release.set()
    thread.join(10)
    paused = box["result"]
    assert _raw(paused)["code"] == "E_PERMISSION"
    assert _items(paused) == []
    assert "mk-p" not in _dump(_raw(paused))
    assert TelemetryStore(root).get_memory_event_total() == telemetry_before

    revoked = ask()
    assert _raw(revoked)["code"] == "E_PERMISSION"
    assert _items(revoked) == []
    assert _raw(expand())["code"] == "E_NOT_VISIBLE"

    regrant = _grant(auth, root, ALICE, data_root, ops=("ask", "expand"))
    assert _raw(expand())["code"] == "OK"
    telemetry_before = TelemetryStore(root).get_memory_event_total()
    entered, release = _pause_first_call(monkeypatch, retrieval, "_measure_expand")
    thread, box = _run_in_thread(expand)
    assert entered.wait(10)
    auth.revoke_memory_scope(
        grant_id=regrant["grant_id"],
        expected_policy_revision=_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )
    release.set()
    thread.join(10)
    paused_expand = box["result"]
    assert _raw(paused_expand)["code"] == "E_NOT_VISIBLE"
    assert not _raw(paused_expand)["data"].get("content_base64")
    assert TelemetryStore(root).get_memory_event_total() == telemetry_before


# --- 6 ----------------------------------------------------------------------


def test_t01_forged_identity_moved_root_and_missing_policy_create_nothing(
    tmp_path: Path,
) -> None:
    from rush.memory import authorization as auth
    from rush.memory.retrieval import (
        MemoryAccess,
        evaluate_artifact_visibility,
        expand_artifact,
        recall_page,
    )

    data_root = default_data_root()
    root_a = _registered(tmp_path / "a", data_root)
    store_a = TypedArtifactStore(root_a)
    marker = "mk-forged-a1"
    _row(store_a, "row-a1", ALICE, marker)
    tool = MemoryTool()

    def ask(root: Path, owner: OwnerScope, **extra: Any) -> Any:
        return tool.run(
            root,
            operation="ask",
            subject=SUBJECT,
            query="needle",
            request={"view": "compact"},
            owner_scope=owner.as_dict(),
            **extra,
        )

    forged = ask(
        root_a,
        ALICE,
        project_id="forged-project",
        session_id="forged-session",
        agent_id="forged-agent",
    )
    assert _raw(forged)["code"] == "E_PERMISSION"
    assert marker not in _dump(_raw(forged))
    assert not auth.policy_path(data_root=data_root).exists()
    assert not (data_root / "user").exists()
    assert (
        MemoryAccess.resolve(
            root_a, operation="ask", owner_scope=ALICE, data_root=data_root
        )
        is None
    )
    assert not auth.policy_path(data_root=data_root).exists()
    assert not (data_root / "user").exists()

    _grant(auth, root_a, ALICE, data_root)
    assert (
        MemoryAccess.resolve(
            root_a, operation="ask", session_binding="forged", data_root=data_root
        )
        is None
    )
    access_a = MemoryAccess.resolve(root_a, operation="ask", data_root=data_root)
    expand_a = MemoryAccess.resolve(root_a, operation="expand", data_root=data_root)
    assert access_a is not None and expand_a is not None
    assert marker in _dump(_raw(ask(root_a, ALICE)))

    as_bob = ask(root_a, BOB)
    assert _raw(as_bob)["code"] == "E_PERMISSION"
    assert marker not in _dump(_raw(as_bob))
    assert (
        MemoryAccess.resolve(
            root_a, operation="ask", owner_scope=BOB, data_root=data_root
        )
        is None
    )

    root_b = _registered(tmp_path / "b", data_root)
    (root_b / ".rush").mkdir(exist_ok=True)
    shutil.copy2(store_a.db_path, root_b / ".rush" / store_a.db_path.name)
    moved = ask(root_b, ALICE)
    assert _raw(moved)["code"] == "E_PERMISSION"
    assert marker not in _dump(_raw(moved))

    view_b, state = TypedArtifactStore.open_readonly_view(root_b)
    assert view_b is not None, state
    try:
        _assert_not(
            evaluate_artifact_visibility(
                view_b, view_b.get_current("row-a1"), access=access_a
            )
        )
        page = recall_page(view_b, subject=SUBJECT, query="needle", access=access_a)
        assert page["items"] == []
        denied = expand_artifact(
            view_b, artifact_id="row-a1", version=1, access=expand_a
        )
        assert denied["code"] == "E_NOT_VISIBLE"
        assert marker not in _dump([page, denied])
    finally:
        view_b.close()


# --- 7 ----------------------------------------------------------------------


def test_t01_missing_store_and_old_schema_create_nothing(tmp_path: Path) -> None:
    tool = MemoryTool()

    def legacy(root: Path, operation: str) -> Any:
        return tool.run(
            root,
            operation=operation,  # type: ignore[arg-type]
            subject=SUBJECT,
            query="needle",
            session_allowlist=["s"],
        )

    def compact(root: Path, operation: str) -> Any:
        return tool.run(
            root,
            operation=operation,  # type: ignore[arg-type]
            subject=SUBJECT,
            query="needle",
            session_allowlist=["s"],
            request={"view": "compact"},
        )

    def expand(root: Path) -> Any:
        return tool.run(
            root,
            operation="expand",
            session_allowlist=["s"],
            request={"id": "row-1", "version": 1},
        )

    bare = tmp_path / "bare"
    bare.mkdir()
    asked = legacy(bare, "ask")
    assert not (bare / ".rush").exists()
    assert asked["status"] == "ok"
    for operation in ("ask", "recall"):
        result = compact(bare, operation)
        assert _raw(result)["code"] == "OK"
        assert _items(result) == []
    assert _raw(expand(bare))["code"] == "E_NOT_VISIBLE"
    assert legacy(bare, "list")["status"] == "ok"
    assert list(bare.iterdir()) == []

    old = tmp_path / "old"
    old.mkdir()
    store = TypedArtifactStore(old)
    _row(store, "row-1", None, "mk-old", source="s")
    db = store.db_path
    _drop_payload_columns(db)
    _no_sidecars(db)
    before = (
        _sha_file(db),
        db.stat().st_mtime_ns,
        sorted(p.name for p in db.parent.iterdir()),
        _paging_key_rows(db),
    )

    reason = readonly_view_reason("migration_required")
    for operation in ("ask", "list"):
        result = legacy(old, operation)
        assert result["status"] == "error", operation
        assert reason in result["summary"], operation
        assert "mk-old" not in _dump(result.get("raw"))
    for operation in ("ask", "recall"):
        result = compact(old, operation)
        assert _raw(result)["code"] == "E_MIGRATION", operation
        assert "mk-old" not in _dump(_raw(result))
    expanded = expand(old)
    assert _raw(expanded)["code"] != "OK"
    assert not _raw(expanded)["data"].get("content_base64")

    _no_sidecars(db)
    after = (
        _sha_file(db),
        db.stat().st_mtime_ns,
        sorted(p.name for p in db.parent.iterdir()),
        _paging_key_rows(db),
    )
    assert after == before


# --- 8 ----------------------------------------------------------------------


def test_t01_review_citations_and_cache_selection_use_shared_decision(
    tmp_path: Path,
) -> None:
    from rush.memory.expiry import sweep_expired
    from rush.token_economy.memory_cache_gate import (
        check_memory_before_pack,
        write_cache_fill,
    )
    from rush.tools.review import ReviewTool

    root = _git_repo(
        tmp_path / "project",
        {"module.py": KNOWN_SRC, "web/app.js": "function Known() { return 1; }\n"},
    )
    module_hash = _sha_file(root / "module.py")
    js_hash = _sha_file(root / "web/app.js")
    store = TypedArtifactStore(root)

    def failure(artifact_id: str, **extra: Any) -> None:
        params: dict[str, Any] = {
            "symbol_ref": "module.py::Known",
            "content_hash": module_hash,
        }
        params.update(extra)
        _row(
            store,
            artifact_id,
            None,
            artifact_id,
            source="migration:failure_ledger",
            subject="failure",
            content={
                "target_file": "module.py",
                "fix_commit": "abc1234",
                "error_message": f"marker {artifact_id}",
            },
            **params,
        )

    failure("f-current")
    failure("f-archived")
    failure("f-expired", created_at=time.time() - 30 * DAY)
    failure("f-tampered")
    failure("f-js", symbol_ref="web/app.js::Known", content_hash=js_hash)
    store.archive("f-archived", expected_version=1, scope="failure", apply=True)
    assert sweep_expired(root, candidate_ids=["f-expired"]) == 1
    _tamper(store.db_path, "f-tampered")

    def review() -> tuple[list[str], int]:
        result = ReviewTool().run(root / "module.py")
        memory = result.get("metadata", {}).get("memory") or {}
        used = [entry["id"] for entry in memory.get("used", [])]
        citations = [
            f for f in result["findings"] if f.get("rule") == "memory-failure-citation"
        ]
        return used, len(citations)

    assert review() == (["f-current"], 1)

    filled = write_cache_fill(
        root, "module.py", "Known", {"source_content_hash": module_hash, "text": "p"}
    )
    assert filled is not None
    js_fill = write_cache_fill(
        root, "web/app.js", "Known", {"source_content_hash": js_hash, "text": "j"}
    )
    assert js_fill is not None
    hit = check_memory_before_pack("module.py", "Known", project_root=root)
    assert hit.hit is True and hit.artifact_id == filled.id
    js_hit = check_memory_before_pack("web/app.js", "Known", project_root=root)
    assert js_hit.hit is False

    store.archive("f-current", expected_version=1, scope="failure", apply=True)
    assert review() == ([], 0)
    _tamper(store.db_path, filled.id)
    assert (
        check_memory_before_pack("module.py", "Known", project_root=root).hit is False
    )


# --- 9 ----------------------------------------------------------------------


def test_t01_legacy_allowlist_route_retained(tmp_path: Path) -> None:
    from rush.memory import retrieval
    from rush.memory.retrieval import defended_recall, recall_page
    from rush.memory.store import SignatureMismatchError

    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    _row(store, "row-alice", ALICE, "mk-alice", source="s")
    _row(store, "row-bob", BOB, "mk-bob", source="s")

    page = recall_page(store, subject=SUBJECT, query="needle", session_allowlist=["s"])
    assert set(_ids(page)) == {"row-alice", "row-bob"}

    tool = MemoryTool()
    as_bob = tool.run(
        root,
        operation="ask",
        subject=SUBJECT,
        query="needle",
        session_allowlist=["s"],
        request={"view": "compact"},
        owner_scope=BOB.as_dict(),
    )
    assert _raw(as_bob)["code"] == "OK"
    assert [item["id"] for item in _items(as_bob)] == ["row-bob"]

    empty = recall_page(store, subject=SUBJECT, query="needle", session_allowlist=[])
    assert empty["items"] == []
    assert defended_recall(store, SUBJECT, "needle", []) == []

    _row(store, "row-stated", None, "mk-stated", source="t")
    _, promotion = store.promote("row-stated", user_stated=True, expected_version=1)
    assert promotion.promoted is True
    _break_signature(store.db_path, "row-stated")
    with pytest.raises(SignatureMismatchError):
        store.recall(SUBJECT, "needle", ["t"])
    with pytest.raises(SignatureMismatchError):
        defended_recall(store, SUBJECT, "needle", ["t"])

    with pytest.raises(ValueError):
        recall_page(
            store,
            subject=SUBJECT,
            query="needle",
            session_allowlist=["s"],
            access=retrieval.MemoryAccess.legacy(root, ["s"]),
        )


# --- 10 ---------------------------------------------------------------------


def test_t01_baseline_probe_t01_fields(tmp_path: Path) -> None:
    """Plan §2.2 probe, verbatim apart from `tmp_path`; `paging` belongs to T02."""
    from rush.memory.retrieval import expand_artifact, recall_page
    from rush.memory.trust import resolve_symbol_ref

    d = tmp_path
    root = Path(d) / "project"
    root.mkdir()
    outside = Path(d) / "outside.py"
    outside.write_text("def Known():\n    return 1\n", encoding="utf-8")
    source = root / "source.py"
    source.write_text(outside.read_text(encoding="utf-8"), encoding="utf-8")
    for args in (
        ["init", "--initial-branch=main"],
        ["add", "source.py"],
        [
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    store = TypedArtifactStore(root)
    owner = legacy_owner_scope(root)
    for i in range(3):
        store.write(
            MemoryArtifact(
                id=f"p{i}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"text": "needle"},
                source="allowed",
                created_at=time.time(),
                symbol_ref="source.py::Known",
                content_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
                owner_scope=owner,
            )
        )
    store.archive(
        "p2",
        expected_version=1,
        scope="domain_knowledge",
        owner_scope=owner,
        apply=True,
    )
    active = recall_page(
        store,
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
        limit=10,
    )
    archived = store.get_current("p2")
    assert archived is not None
    expansion = expand_artifact(
        store,
        artifact_id="p2",
        version=archived.artifact_version,
        session_allowlist=["allowed"],
    )
    results = {
        "archive_hidden": [item["id"] for item in active["items"]] == ["p0", "p1"],
        "expansion_denied": expansion["code"] == "E_NOT_VISIBLE",
        "outside_denied": resolve_symbol_ref(str(outside) + "::Known", root) is False,
    }
    assert results == dict.fromkeys(results, True), results


# --- 11 ---------------------------------------------------------------------


def test_t01_relations_and_hybrid_never_disclose_excluded_neighbors(
    tmp_path: Path,
) -> None:
    from rush.memory import authorization as auth
    from rush.memory.relations import add_relation
    from rush.memory.retrieval import MemoryAccess, hybrid_page, recall_page

    data_root = tmp_path / "user-data"
    root = _registered(tmp_path / "project", data_root)
    store = TypedArtifactStore(root)
    _row(store, "row-a1", ALICE, "mk-a1-alpha")
    _row(store, "row-a2", ALICE, "mk-a2-bravo")
    _row(store, "row-b1", BOB, "mk-b1-delta")
    _row(store, "row-c1", ALICE, "mk-c1-golf", subject="architectural_decision")
    store.archive(
        "row-a2", expected_version=1, scope=SUBJECT, owner_scope=ALICE, apply=True
    )
    for target in ("row-a2", "row-b1", "row-c1"):
        added = add_relation(
            store,
            source_id="row-a1",
            source_version=1,
            target_id=target,
            target_version=_version(store.db_path, target),
            kind="depends_on",
        )
        assert added["code"] == "OK", added

    _grant(auth, root, ALICE, data_root)
    access = MemoryAccess.resolve(root, operation="ask", data_root=data_root)
    assert access is not None

    page = recall_page(store, subject=SUBJECT, query="needle", access=access)
    assert _ids(page) == ["row-a1"]
    assert [r["id"] for r in page["items"][0]["relations"]] == ["row-c1"]

    calls, embed = _embed_spy()
    hybrid = hybrid_page(
        store,
        subject=SUBJECT,
        query="needle",
        access=access,
        embed_config=_embed_config(),
        embed_fn=embed,
    )
    assert _ids(hybrid) == ["row-a1"]
    assert [r["id"] for r in hybrid["items"][0]["relations"]] == ["row-c1"]
    embedded = [text for batch in calls for text in batch if text != "needle"]
    assert embedded and all("mk-a1-alpha" in text for text in embedded)
    dumped = _dump([page, hybrid, calls])
    for hidden in ("row-a2", "row-b1", "mk-a2-bravo", "mk-b1-delta"):
        assert hidden not in dumped


# --- 12 ---------------------------------------------------------------------


def test_t01_unbound_and_backfilled_integrity_labels(tmp_path: Path) -> None:
    from rush.memory import retrieval

    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    plain = _row(store, "row-plain", None, "mk-plain", source="src")
    _row(store, "row-stated", None, "mk-stated", source="src")
    _row(store, "row-bad-sig", None, "mk-bad", source="src")
    for artifact_id in ("row-stated", "row-bad-sig"):
        _, promotion = store.promote(artifact_id, user_stated=True, expected_version=1)
        assert promotion.promoted is True
    _break_signature(store.db_path, "row-bad-sig")
    _drop_payload_columns(store.db_path)

    reopened = TypedArtifactStore(root)
    db = reopened.db_path
    for table in ("memory_artifacts", "memory_artifact_versions"):
        assert set(PAYLOAD_COLUMNS) <= _columns(db, table), table
    assert _payload_row(db, "row-plain") == (_payload_sha(plain.content), "backfill")
    stated = reopened.get_current("row-stated")
    assert stated is not None
    assert _payload_row(db, "row-stated") == (_payload_sha(stated.content), "backfill")
    assert _payload_row(db, "row-bad-sig")[0] is None

    unbound_content = {"text": "needle mk-unbound"}
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO memory_artifacts "
            "(id, family, subject, trust_tier, content, source, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                "row-unbound",
                "memory",
                SUBJECT,
                "DERIVED",
                json.dumps(unbound_content),
                "src",
                time.time(),
            ),
        )
        conn.execute(
            "INSERT INTO memory_artifact_versions "
            "(artifact_id, artifact_version, content, source, trust_tier, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (
                "row-unbound",
                1,
                json.dumps(unbound_content),
                "src",
                "DERIVED",
                time.time(),
            ),
        )
        conn.commit()
    assert _payload_row(db, "row-unbound") == (None, None)

    access = retrieval.MemoryAccess.legacy(root, ["src"])
    labels = {"row-plain": "backfilled", "row-unbound": "unbound"}
    for artifact_id, label in labels.items():
        decision = retrieval.evaluate_artifact_visibility(
            reopened, reopened.get_current(artifact_id), access=access
        )
        assert decision.visible is True, artifact_id
        assert decision.usable_as_current is True, artifact_id
        assert decision.reference["integrity"] == label, artifact_id
    bad = retrieval.evaluate_artifact_visibility(
        reopened, reopened.get_current("row-bad-sig"), access=access
    )
    assert bad.usable_as_current is False


# --- 14 (OD-3) --------------------------------------------------------------


def test_t01_learned_advice_reads_use_shared_decision(tmp_path: Path) -> None:
    """OD-3: experience.py (359, 550, 581), intent.py:341 and verification.py:207.

    A non-empty `session_allowlist` is the legacy route (no owner filter, so the
    foreign-owner row is only asserted absent on the policy route). An absent
    allowlist resolves the policy at the default data root, as `MemoryTool` does.
    """
    from rush.memory import authorization as auth
    from rush.memory.experience import (
        DEFAULT_BEHAVIOR_NAMESPACE,
        behavior_runtime_digest,
        compare_last_success,
        recall_repair_episodes,
    )
    from rush.memory.expiry import sweep_expired
    from rush.memory.intent import intent_evidence
    from rush.memory.verification import plan_checks

    data_root = default_data_root()
    root = _registered(tmp_path / "project", data_root)
    store = TypedArtifactStore(root)
    now = time.time()
    kinds = ("current", "archived", "expired", "tampered", "foreign")
    excluded = ("archived", "expired", "tampered", "foreign")
    digest = behavior_runtime_digest(runtime=None, platform=None)
    rows: dict[str, list[tuple[str, str]]] = {kind: [] for kind in kinds}

    def add(kind: str, artifact_id: str, subject: str, content: dict[str, Any]) -> None:
        _row(
            store,
            artifact_id,
            BOB if kind == "foreign" else ALICE,
            artifact_id,
            source="s",
            subject=subject,
            content=content,
            created_at=now - 30 * DAY if kind == "expired" else now,
        )
        rows[kind].append((artifact_id, subject))

    def add_pass(kind: str, artifact_id: str, behavior: str) -> None:
        store.write_pass(
            MemoryArtifact(
                id=artifact_id,
                family="experience",
                subject="episodic",
                trust_tier="DERIVED",
                content={
                    "kind": "behavior_success",
                    "behavior_id": behavior,
                    "conditions": {"code_digest": "c"},
                },
                source="s",
                created_at=now - 30 * DAY if kind == "expired" else now,
                owner_scope=BOB if kind == "foreign" else ALICE,
            ),
            namespace=DEFAULT_BEHAVIOR_NAMESPACE,
            behavior_id=behavior,
            runtime_digest=digest,
        )
        rows[kind].append((artifact_id, "episodic"))

    def cause(kind: str, artifact_id: str, behavior: str, baseline: str) -> None:
        add(
            kind,
            artifact_id,
            "episodic",
            {
                "kind": "cause_experiment",
                "behavior_id": behavior,
                "baseline_ref": {"id": baseline, "version": 1},
                "changed_factor": "code",
                "control_receipt_ref": "receipt",
                "outcome_changed": True,
                "cause_state": "reproduced",
            },
        )

    for kind in kinds:
        add(
            kind,
            f"rep-{kind}",
            "failure",
            {
                "kind": "repair_episode",
                "symptom": "symptomalpha",
                "hypothesis": f"hyp-{kind}",
                "patch_hash": "patch",
                "conditions": {},
                "receipt_ref": None,
                "behavior_ids": [],
                "affected_symbols": [],
                "outcome": "failed",
                "commit_message": None,
            },
        )
        add(
            kind,
            f"int-{kind}",
            "architectural_decision",
            {
                "kind": "intent",
                "behavior_id": "behintent",
                "intent_id": f"intent-{kind}",
                "status": "active",
                "statement_ref": None,
                "check_refs": [],
            },
        )
        add(
            kind,
            f"ev-{kind}",
            "episodic",
            {
                "evidence_kind": "source_graph",
                "check_id": "chkone",
                "targets": ["tgtone"],
            },
        )
        add_pass(kind, f"pass-{kind}", f"beh{kind}")
        if kind != "current":
            cause(kind, f"cause-{kind}", "behcurrent", "pass-current")
    add_pass("current", "pass-control", "behcontrol")
    cause("current", "cause-control", "behcontrol", "pass-control")

    for artifact_id, subject in rows["archived"]:
        store.archive(
            artifact_id,
            expected_version=1,
            scope=subject,
            owner_scope=ALICE,
            apply=True,
        )
    expired_ids = [artifact_id for artifact_id, _ in rows["expired"]]
    assert sweep_expired(root, owner_scope=ALICE, candidate_ids=expired_ids) == len(
        expired_ids
    )
    for artifact_id, _ in rows["tampered"]:
        _tamper(store.db_path, artifact_id)
    _grant(auth, root, ALICE, data_root, sources=("s",), ops=("ask", "list"))

    legacy_hidden = {f"rep-{k}" for k in ("archived", "expired", "tampered")}
    legacy = recall_repair_episodes(
        project_root=root,
        symptom="symptomalpha",
        conditions={},
        session_allowlist=["s"],
    )
    legacy_ids = {entry["id"] for entry in legacy["failures"]}
    assert "rep-current" in legacy_ids
    assert not legacy_ids & legacy_hidden
    policy = recall_repair_episodes(
        project_root=root, symptom="symptomalpha", conditions={}, session_allowlist=None
    )
    assert {entry["id"] for entry in policy["failures"]} == {"rep-current"}

    legacy_intents = {
        entry["id"]
        for entry in intent_evidence(
            project_root=root, behavior_ids=["behintent"], session_allowlist=["s"]
        )
    }
    assert "int-current" in legacy_intents
    assert not legacy_intents & {
        f"int-{k}" for k in ("archived", "expired", "tampered")
    }
    policy_intents = {
        entry["id"]
        for entry in intent_evidence(
            project_root=root, behavior_ids=["behintent"], session_allowlist=None
        )
    }
    assert policy_intents == {"int-current"}

    conditions = {"code_digest": "c"}
    current = compare_last_success(
        project_root=root, behavior_id="behcurrent", conditions=conditions
    )
    assert current["baseline_ref"] == {"id": "pass-current", "version": 1}
    assert current["cause_state"] == "candidate"
    for kind in excluded:
        result = compare_last_success(
            project_root=root, behavior_id=f"beh{kind}", conditions=conditions
        )
        assert result["baseline_ref"] is None, kind
    control = compare_last_success(
        project_root=root, behavior_id="behcontrol", conditions=conditions
    )
    assert control["baseline_ref"] == {"id": "pass-control", "version": 1}
    assert control["cause_state"] == "reproduced"

    planned = json.dumps(
        plan_checks(
            project_root=root,
            changed_targets=[{"id": "tgtone"}],
            required_checks=[{"id": "chkone", "argv": ["true"]}],
            environment={},
        )
    )
    assert "ev-current" in planned
    for kind in excluded:
        assert f"ev-{kind}" not in planned, kind

    missing = tmp_path / "missing"
    missing.mkdir()
    recalled = recall_repair_episodes(
        project_root=missing,
        symptom="symptomalpha",
        conditions={},
        session_allowlist=["s"],
    )
    assert recalled["failures"] == []
    assert list(missing.iterdir()) == []


# --- X1 (T008 §4.1) ---------------------------------------------------------


def test_t01_overlay_access_evaluates_user_store_rows(tmp_path: Path) -> None:
    from rush.memory import authorization as auth
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility

    data_root = tmp_path / "user-data"
    root = _registered(tmp_path / "project", data_root)
    overlay = auth.user_overlay_owner_scope(data_root=data_root)
    _grant(
        auth,
        root,
        overlay,
        data_root,
        sources=(OVERLAY_SOURCE,),
        ops=("overlay_read", "write"),
    )
    user_store = TypedArtifactStore(data_root / "user")
    _row(
        user_store,
        "pref-1",
        overlay,
        "mk-pref",
        source=OVERLAY_SOURCE,
        subject="preference",
    )
    access = MemoryAccess.resolve(
        root,
        operation="overlay_read",
        owner_scope=overlay,
        requested_sources=[OVERLAY_SOURCE],
        data_root=data_root,
    )
    assert access is not None
    decision = evaluate_artifact_visibility(
        user_store, user_store.get_current("pref-1"), access=access
    )
    assert decision.visible is True
    assert decision.usable_as_current is True
    assert decision.freshness == "not_applicable"

    # The overlay exemption holds only for a store rooted at `<data_root>/user`.
    elsewhere = TypedArtifactStore(tmp_path / "elsewhere")
    _row(
        elsewhere,
        "pref-1",
        overlay,
        "mk-pref-elsewhere",
        source=OVERLAY_SOURCE,
        subject="preference",
    )
    _assert_not(
        evaluate_artifact_visibility(
            elsewhere, elsewhere.get_current("pref-1"), access=access
        )
    )


# --- X5 (T007; PM gate delta) -----------------------------------------------


@pytest.mark.posix_only
def test_t01_artifact_freshness_matches_visibility_decision(tmp_path: Path) -> None:
    """`retrieval.artifact_freshness` needs no access value, never writes, and agrees
    with the decision's freshness and freshness reasons for every test-2 row."""
    from rush.memory import retrieval

    root, _outside, store, rows, plain_store = _containment_fixture(tmp_path)
    db = store.db_path
    before = (_sha_file(db), db.stat().st_mtime_ns)
    for artifact_id, (_, _, freshness, reasons) in rows.items():
        artifact = store.get_current(artifact_id)
        assert retrieval.artifact_freshness(store, artifact) == (
            freshness,
            reasons,
        ), artifact_id
    legacy = retrieval.MemoryAccess.legacy(root, ["src"])
    for artifact_id, (_, _, freshness, reasons) in rows.items():
        artifact = store.get_current(artifact_id)
        decision = retrieval.evaluate_artifact_visibility(
            store, artifact, access=legacy, mode="historical"
        )
        assert (decision.freshness, tuple(decision.reason_codes)) == (
            freshness,
            reasons,
        ), artifact_id
    assert retrieval.artifact_freshness(store, store.get_current("unanchored")) == (
        "not_applicable",
        (),
    )
    assert retrieval.artifact_freshness(plain_store, plain_store.get_current("g1")) == (
        "unknown",
        ("api_baseline_unknown",),
    )
    assert (_sha_file(db), db.stat().st_mtime_ns) == before


# --- B6 (PM gate delta 2) ---------------------------------------------------


def test_t01_checkpoint_name_symbol_ref_is_not_an_anchor(tmp_path: Path) -> None:
    """A checkpoint-journal row's `symbol_ref` is a checkpoint name, not a code anchor:
    it is `not_applicable` and usable as current. The malformed-ref rule still holds
    for every other source."""
    from rush.memory import retrieval

    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    checkpoint_source = "checkpoint_journal:save_checkpoint"
    _row(store, "cp-row", None, "mk-cp", source=checkpoint_source, symbol_ref="cp-1")
    _row(store, "other-row", None, "mk-other", source="src", symbol_ref="cp-1")

    assert retrieval.artifact_freshness(store, store.get_current("cp-row")) == (
        "not_applicable",
        (),
    )
    decision = retrieval.evaluate_artifact_visibility(
        store,
        store.get_current("cp-row"),
        access=retrieval.MemoryAccess.legacy(root, [checkpoint_source]),
    )
    assert decision.visible is True
    assert decision.usable_as_current is True
    assert decision.freshness == "not_applicable"
    assert tuple(decision.reason_codes) == ()

    control = retrieval.evaluate_artifact_visibility(
        store,
        store.get_current("other-row"),
        access=retrieval.MemoryAccess.legacy(root, ["src"]),
    )
    assert control.visible is True
    assert control.usable_as_current is False
    assert control.freshness == "unknown"
    assert tuple(control.reason_codes) == ("symbol_ref_malformed",)


# --- 72-T01 fix round 1 (T020 findings F1-F5) -------------------------------

CHECKPOINT_SOURCE = "checkpoint_journal:save_checkpoint"


def _fix1_data_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """HOME, XDG_DATA_HOME and LOCALAPPDATA inside `tmp_path`; the resolved default
    data root, asserted to be inside `tmp_path`."""
    for name, sub in (
        ("HOME", "fix1-home"),
        ("XDG_DATA_HOME", "fix1-xdg"),
        ("LOCALAPPDATA", "fix1-appdata"),
    ):
        path = tmp_path / sub
        path.mkdir(exist_ok=True)
        monkeypatch.setenv(name, str(path))
    data_root = default_data_root()
    assert data_root and Path(data_root).resolve().is_relative_to(tmp_path.resolve())
    return Path(data_root)


def _fix1_compact_tamper(db: Path, artifact_id: str, content: dict[str, Any]) -> None:
    """PM repro step 2: rewrite only `memory_artifacts.content`, as compact JSON."""
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = ?",
            (json.dumps(content, separators=(",", ":")), artifact_id),
        )
        conn.commit()


def _fix1_raw_content(db: Path, artifact_id: str) -> str:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        row = conn.execute(
            "SELECT content FROM memory_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
    assert row is not None, artifact_id
    return str(row[0])


def _fix1_assert_quarantined(
    store: TypedArtifactStore, artifact_id: str, subject: str, source: str
) -> None:
    from rush.memory.retrieval import (
        MemoryAccess,
        defended_recall,
        evaluate_artifact_visibility,
    )

    root = store.project_root
    legacy = MemoryAccess.legacy(root, [source])
    assert store.get_current(artifact_id).trust_tier != "STATED"
    ordinary = evaluate_artifact_visibility(
        store, store.get_current_row(artifact_id), access=legacy
    )
    assert ordinary.visible is False
    assert ordinary.usable_as_current is False
    historical = evaluate_artifact_visibility(
        store, store.get_current_row(artifact_id), access=legacy, mode="historical"
    )
    assert historical.usable_as_current is False
    assert "integrity_payload_mismatch" in historical.reason_codes
    assert artifact_id not in {
        a.id for a in defended_recall(store, subject, "needle", [source])
    }


def _fix1_wire_rows(result: Any) -> list[dict[str, Any]]:
    raw = _raw(result)
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return _items(result)
    return []


def _fix1_revoke(auth: Any, grant: dict[str, Any], data_root: Path) -> None:
    auth.revoke_memory_scope(
        grant_id=grant["grant_id"],
        expected_policy_revision=_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )


def _fix1_fire_after(
    monkeypatch: pytest.MonkeyPatch, target: Any, name: str, action: Any
) -> dict[str, int]:
    """Wrap `target.name` so `action()` runs once, right after the first call returns
    its rows (mid-scan: after the fetch, before results are emitted)."""
    original = getattr(target, name)
    fired = {"n": 0}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        if fired["n"] == 0:
            fired["n"] += 1
            action()
        return result

    monkeypatch.setattr(target, name, wrapper)
    return fired


# --- F1 ---------------------------------------------------------------------


def test_t01_fix1_promote_refuses_payload_mismatched_row(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    db = store.db_path

    # Control: an untampered row written by Rush still promotes, `write`-bound.
    store.write(
        MemoryArtifact(
            id="c1",
            family="handoff",
            subject="active_context",
            trust_tier="DERIVED",
            content={"text": "needle control"},
            source="s",
            created_at=1e9,
        )
    )
    _, control = store.promote("c1", user_stated=True)
    assert control.promoted is True
    digest, origin = _payload_row(db, "c1")
    assert origin == "write"
    assert digest == _sha_text(_fix1_raw_content(db, "c1"))

    # PM repro.
    store.write(
        MemoryArtifact(
            id="a1",
            family="handoff",
            subject="active_context",
            trust_tier="DERIVED",
            content={"text": "needle ok"},
            source="s",
            created_at=1e9,
        )
    )
    _fix1_compact_tamper(db, "a1", {"text": "needle EVIL"})
    _fix1_assert_quarantined(store, "a1", "active_context", "s")

    _, result = store.promote("a1", user_stated=True)
    assert result.promoted is False
    _fix1_assert_quarantined(store, "a1", "active_context", "s")


def test_t01_fix1_maintenance_promotion_refuses_payload_mismatched_row(
    tmp_path: Path,
) -> None:
    from rush.memory.maintenance import run_maintenance_cycle

    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    _row(store, "m1", None, "mk-m1", source="s1")
    _row(store, "m2", None, "mk-m2", source="s2")
    _fix1_compact_tamper(store.db_path, "m1", {"text": "needle EVIL"})
    _fix1_assert_quarantined(store, "m1", SUBJECT, "s1")

    run_maintenance_cycle(
        "promotion_sweep",
        project_root=root,
        owner_scope=legacy_owner_scope(root.resolve()),
        candidate_ids=["m1"],
    )
    _fix1_assert_quarantined(store, "m1", SUBJECT, "s1")


# --- F2 ---------------------------------------------------------------------


def _fix1_policy_fixture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[Any, Path, Path, TypedArtifactStore, dict[str, Any]]:
    from rush.memory import authorization as auth

    data_root = _fix1_data_root(monkeypatch, tmp_path)
    root = _registered(tmp_path / "project", data_root)
    store = TypedArtifactStore(root)
    for i in range(3):
        _row(store, f"row-r{i}", ALICE, f"mk-r{i}")
    grant = _grant(auth, root, ALICE, data_root)
    return auth, data_root, root, store, grant


def test_t01_fix1_defended_recall_rechecks_before_emit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.retrieval import MemoryAccess, defended_recall

    auth, data_root, root, store, grant = _fix1_policy_fixture(monkeypatch, tmp_path)
    access = MemoryAccess.resolve(
        root, operation="ask", owner_scope=ALICE, data_root=data_root
    )
    assert access is not None
    assert len(defended_recall(store, SUBJECT, "needle", None, access=access)) == 3

    fired = _fix1_fire_after(
        monkeypatch,
        store,
        "search_candidates",
        lambda: _fix1_revoke(auth, grant, data_root),
    )
    rows = defended_recall(store, SUBJECT, "needle", None, access=access)
    assert fired["n"] == 1
    assert rows == []


def test_t01_fix1_store_recall_rechecks_before_emit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.retrieval import MemoryAccess

    auth, data_root, root, store, grant = _fix1_policy_fixture(monkeypatch, tmp_path)
    access = MemoryAccess.resolve(
        root, operation="ask", owner_scope=ALICE, data_root=data_root
    )
    assert access is not None
    assert len(store.recall(SUBJECT, "needle", access=access, mode="ordinary")) == 3

    fired = _fix1_fire_after(
        monkeypatch,
        TypedArtifactStore,
        "search_rows",
        lambda: _fix1_revoke(auth, grant, data_root),
    )
    rows = store.recall(SUBJECT, "needle", access=access, mode="ordinary")
    assert fired["n"] == 1
    assert rows == []


def test_t01_fix1_memory_tool_legacy_ask_revision_change_restarts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, data_root, root, _store, _grant_a = _fix1_policy_fixture(
        monkeypatch, tmp_path
    )
    tool = MemoryTool()

    def ask() -> Any:
        return tool.run(
            root,
            operation="ask",
            subject=SUBJECT,
            query="needle",
            owner_scope=ALICE.as_dict(),
        )

    baseline = ask()
    assert baseline["status"] == "ok"
    assert len(_fix1_wire_rows(baseline)) == 3

    # A revision change mid-call (a second grant) restarts the read.
    fired = _fix1_fire_after(
        monkeypatch,
        TypedArtifactStore,
        "search_rows",
        lambda: _grant(auth, root, BOB, data_root, ops=("ask",)),
    )
    restarted = ask()
    assert fired["n"] == 1
    assert _fix1_wire_rows(restarted) == []
    assert "mk-r" not in _dump(restarted)
    assert "E_RESTART" in _dump(restarted)


def test_t01_fix1_memory_tool_legacy_ask_revoke_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    auth, data_root, root, _store, grant = _fix1_policy_fixture(monkeypatch, tmp_path)
    tool = MemoryTool()

    def ask() -> Any:
        return tool.run(
            root,
            operation="ask",
            subject=SUBJECT,
            query="needle",
            owner_scope=ALICE.as_dict(),
        )

    baseline = ask()
    assert baseline["status"] == "ok"
    assert len(_fix1_wire_rows(baseline)) == 3

    # A revoke mid-call fails closed.
    fired = _fix1_fire_after(
        monkeypatch,
        TypedArtifactStore,
        "search_rows",
        lambda: _fix1_revoke(auth, grant, data_root),
    )
    revoked = ask()
    assert fired["n"] == 1
    assert revoked["status"] != "ok"
    assert _fix1_wire_rows(revoked) == []
    assert "mk-r" not in _dump(revoked)


def test_t01_fix1_od3_reader_rechecks_before_emit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import authorization as auth
    from rush.memory.intent import intent_evidence

    data_root = _fix1_data_root(monkeypatch, tmp_path)
    root = _registered(tmp_path / "project", data_root)
    store = TypedArtifactStore(root)
    _row(
        store,
        "int-a",
        ALICE,
        "mk-int",
        subject="architectural_decision",
        content={
            "kind": "intent",
            "behavior_id": "behintent",
            "intent_id": "intent-a",
            "status": "active",
            "statement_ref": None,
            "check_refs": [],
        },
    )
    grant = _grant(auth, root, ALICE, data_root)

    def read() -> set[str]:
        return {
            entry["id"]
            for entry in intent_evidence(
                project_root=root, behavior_ids=["behintent"], session_allowlist=None
            )
        }

    assert read() == {"int-a"}
    fired = _fix1_fire_after(
        monkeypatch,
        TypedArtifactStore,
        "search_rows",
        lambda: _fix1_revoke(auth, grant, data_root),
    )
    assert read() == set()
    assert fired["n"] == 1


# --- F3 ---------------------------------------------------------------------


def test_t01_fix1_memory_tool_wire_carries_freshness(tmp_path: Path) -> None:
    from rush.memory.retrieval import SourceValidationMemo

    root = tmp_path / "project"
    root.mkdir()
    root = root.resolve()
    for name in ("gone.py", "moved.py"):
        (root / name).write_text(KNOWN_SRC, encoding="utf-8")
    store = TypedArtifactStore(root)
    memo = SourceValidationMemo()
    _row(
        store,
        "w-gone",
        None,
        "mk-gone",
        source="src",
        symbol_ref="gone.py::",
        content_hash=memo.source_hash(root / "gone.py"),
    )
    _row(
        store,
        "w-moved",
        None,
        "mk-moved",
        source="src",
        symbol_ref="moved.py::",
        content_hash=memo.source_hash(root / "moved.py"),
    )
    _row(store, "w-plain", None, "mk-plain", source="src")
    (root / "gone.py").unlink()
    (root / "moved.py").write_text("def Other():\n    return 2\n", encoding="utf-8")

    tool = MemoryTool()

    def wire(operation: str) -> dict[str, dict[str, Any]]:
        result = tool.run(
            root,
            operation=operation,
            subject=SUBJECT,
            query="needle",
            session_allowlist=["src"],
        )
        assert result["status"] == "ok", _dump(result)
        return {row["id"]: row for row in _fix1_wire_rows(result)}

    listed = wire("list")
    assert listed["w-gone"]["freshness"] == "unknown"
    assert listed["w-gone"]["stale"] is False
    assert listed["w-moved"]["freshness"] == "stale"
    assert listed["w-moved"]["stale"] is True
    assert listed["w-plain"]["freshness"] == "not_applicable"
    assert listed["w-plain"]["stale"] is False
    for operation in ("recall", "ask"):
        rows = wire(operation)
        assert set(rows) == {"w-plain"}, operation
        assert rows["w-plain"]["freshness"] == "not_applicable", operation
        assert rows["w-plain"]["stale"] is False, operation


# --- F4 ---------------------------------------------------------------------


@pytest.mark.parametrize("case", ["anchored", "outside"])
def test_t01_fix1_checkpoint_exemption_covers_names_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    from rush.memory import retrieval

    root = tmp_path / "project"
    root.mkdir()
    root = root.resolve()
    (root / "m.py").write_text("def K():\n    return 1\n", encoding="utf-8")
    store = TypedArtifactStore(root)
    if case == "anchored":
        symbol_ref = "m.py::K"
        content_hash = retrieval.SourceValidationMemo().source_hash(root / "m.py")
    else:
        symbol_ref = "/etc/passwd::x"
        content_hash = "0" * 64
    _row(
        store,
        "cp-row",
        None,
        "mk-cp-row",
        source=CHECKPOINT_SOURCE,
        symbol_ref=symbol_ref,
        content_hash=content_hash,
    )
    (root / "m.py").write_text("def K(changed):\n    return 2\n", encoding="utf-8")
    access = retrieval.MemoryAccess.legacy(root, [CHECKPOINT_SOURCE])

    outside_real = Path(os.path.realpath("/etc/passwd"))
    reads: list[Path] = []
    original_read_text = Path.read_text
    original_read_bytes = Path.read_bytes
    original_open = Path.open

    def spy_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        reads.append(Path(os.path.realpath(self)))
        return original_read_text(self, *args, **kwargs)

    def spy_read_bytes(self: Path) -> bytes:
        reads.append(Path(os.path.realpath(self)))
        return original_read_bytes(self)

    def spy_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        reads.append(Path(os.path.realpath(self)))
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy_read_text)
    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    monkeypatch.setattr(Path, "open", spy_open)

    decision = retrieval.evaluate_artifact_visibility(
        store, store.get_current("cp-row"), access=access, mode="historical"
    )
    freshness = retrieval.artifact_freshness(store, store.get_current("cp-row"))[0]
    if case == "anchored":
        assert decision.freshness == "stale"
        assert "source_hash_mismatch" in decision.reason_codes
        assert freshness == "stale"
    else:
        assert decision.freshness == "unknown"
        assert "source_not_contained" in decision.reason_codes
        assert freshness == "unknown"
    assert decision.usable_as_current is False
    recalled = retrieval.defended_recall(store, SUBJECT, "needle", [CHECKPOINT_SOURCE])
    assert "cp-row" not in {a.id for a in recalled}
    assert outside_real not in reads


# --- F5 ---------------------------------------------------------------------


def test_t01_fix1_mismatched_row_integrity_label(tmp_path: Path) -> None:
    from rush.memory import retrieval

    root = tmp_path / "project"
    root.mkdir()
    store = TypedArtifactStore(root)
    _row(store, "w-tampered", None, "mk-tampered", source="src")
    _tamper(store.db_path, "w-tampered")
    decision = retrieval.evaluate_artifact_visibility(
        store,
        store.get_current("w-tampered"),
        access=retrieval.MemoryAccess.legacy(root, ["src"]),
        mode="historical",
    )
    assert "integrity_payload_mismatch" in decision.reason_codes
    assert decision.reference is not None
    assert decision.reference["integrity"] == "mismatch"


# --- 72-T01 fix round 2 (T065 findings J1-J4) -------------------------------

FIX2_EVIL = {"text": "needle EVIL"}
FIX2_PATHS = ("archive", "expiry", "staleness", "promotion_sweep", "promote_stated")


def _fix2_fixture_row(root: Path, artifact_id: str, path: str) -> MemoryArtifact:
    """One row shaped so `path` reaches its `_write_version` call: an old DERIVED row
    (expiry), a symbol-anchored row (staleness) or a row whose stored corroboration
    count differs from the recount (promotion sweep)."""
    from rush.memory.merkle_invalidator import MerkleInvalidator

    store = TypedArtifactStore(root)
    symbol_ref = content_hash = None
    if path == "staleness":
        target = root / "module.py"
        target.write_text("def hello():\n    return 1\n", encoding="utf-8")
        symbol_ref = "module.py::hello"
        content_hash = MerkleInvalidator(root).hash_content(target.read_text())
    created_at = time.time() - 20 * DAY if path == "expiry" else time.time()
    written = _row(
        store,
        artifact_id,
        None,
        f"café {artifact_id}",
        source=f"src-{artifact_id}",
        created_at=created_at,
        symbol_ref=symbol_ref,
        content_hash=content_hash,
    )
    if path == "promotion_sweep":
        with contextlib.closing(sqlite3.connect(store.db_path)) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET corroboration_count = 5 WHERE id = ?",
                (artifact_id,),
            )
            conn.commit()
    return written


def _fix2_run_path(root: Path, artifact_id: str, path: str) -> None:
    """Drive one lifecycle path over `artifact_id` through its real entry point."""
    from rush.memory.expiry import sweep_expired
    from rush.memory.maintenance import run_maintenance_cycle

    store = TypedArtifactStore(root)
    owner = legacy_owner_scope(root)
    if path == "archive":
        version = _version(store.db_path, artifact_id)
        for step, archived in enumerate((True, False)):
            applied = store.archive(
                artifact_id,
                expected_version=version + step,
                scope=SUBJECT,
                apply=True,
                archived=archived,
            )
            assert applied["applied"] is True
    elif path == "expiry":
        assert sweep_expired(root, candidate_ids=[artifact_id]) == 1
    elif path == "staleness":
        (root / "module.py").write_text("def hello():\n    return 2\n", "utf-8")
        run_maintenance_cycle(
            "staleness_sweep",
            project_root=root,
            owner_scope=owner,
            candidate_ids=[artifact_id],
        )
    elif path == "promotion_sweep":
        run_maintenance_cycle(
            "promotion_sweep",
            project_root=root,
            owner_scope=owner,
            candidate_ids=[artifact_id],
        )
    else:
        store.promote(artifact_id, user_stated=True)


def _fix2_assert_bound(
    store: TypedArtifactStore, artifact_id: str, origin: str, *, visible: bool
) -> None:
    """The live row and its latest version row each match their own bytes, under
    `origin`; `visible` rows are ordinary-visible and recalled."""
    from rush.memory.retrieval import (
        MemoryAccess,
        defended_recall,
        evaluate_artifact_visibility,
    )

    db = store.db_path
    raw = _fix1_raw_content(db, artifact_id)
    assert _payload_row(db, artifact_id) == (_sha_text(raw), origin), artifact_id
    version = _version(db, artifact_id)
    payload = store.get_version_payload(artifact_id, version)
    assert payload is not None
    text, digest = payload
    assert digest == _sha_text(text), (artifact_id, version)
    assert text == raw, (artifact_id, version)
    assert _payload_version_row(db, artifact_id, version)[2] == origin

    row = store.get_current_row(artifact_id)
    access = MemoryAccess.legacy(store.project_root, [row["source"]])
    historical = evaluate_artifact_visibility(
        store, row, access=access, mode="historical"
    )
    assert "integrity_payload_mismatch" not in historical.reason_codes
    assert historical.reference is not None
    assert historical.reference["integrity"] != "mismatch"
    if visible:
        ordinary = evaluate_artifact_visibility(store, row, access=access)
        assert ordinary.visible is True, ordinary.reason_codes
        assert ordinary.usable_as_current is True, ordinary.reason_codes
        recalled = defended_recall(store, row["subject"], "needle", [row["source"]])
        assert artifact_id in {a.id for a in recalled}


@pytest.mark.parametrize("path", FIX2_PATHS)
def test_t01_fix2_j1_noncanonical_backfill_survives_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """J1: an honest backfilled row whose stored text is not `json.dumps` canonical
    keeps a binding that matches its own bytes through every same-content rewrite."""
    _fix1_data_root(monkeypatch, tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    root = root.resolve()
    written = _fix2_fixture_row(root, "j1", path)
    noncanonical = json.dumps(written.content, ensure_ascii=False)
    assert noncanonical != json.dumps(written.content)
    db = TypedArtifactStore(root).db_path
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = ?", (noncanonical, "j1")
        )
        conn.commit()
    _drop_payload_columns(db)

    store = TypedArtifactStore(root)
    assert _fix1_raw_content(db, "j1") == noncanonical
    assert _payload_row(db, "j1") == (_sha_text(noncanonical), "backfill")
    before = _version(db, "j1")

    _fix2_run_path(root, "j1", path)

    assert _version(db, "j1") > before, path
    assert json.loads(_fix1_raw_content(db, "j1")) == written.content
    _fix2_assert_bound(
        store, "j1", "backfill", visible=path not in ("expiry", "staleness")
    )
    if path == "promote_stated":
        assert store.get_current("j1").trust_tier == "STATED"
    if path == "expiry":
        assert store.get_current_row("j1")["expired_at"] is not None


def test_t01_fix2_j1_canonical_write_row_archive_keeps_write_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J1 control: a canonical `store.write` row archived and unarchived stays
    `write`-bound with a matching hash."""
    _fix1_data_root(monkeypatch, tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    root = root.resolve()
    store = TypedArtifactStore(root)
    written = _row(store, "c1", None, "café c1", source="src-c1")
    assert _fix1_raw_content(store.db_path, "c1") == json.dumps(written.content)
    _fix2_run_path(root, "c1", "archive")
    assert _version(store.db_path, "c1") == 3
    _fix2_assert_bound(store, "c1", "write", visible=True)


def test_t01_fix2_j2_promotion_sweep_rereads_row_under_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J2: an edit committed between the sweep's SELECT and its BEGIN IMMEDIATE is
    never overwritten in history by the pre-edit content."""
    from rush.memory import maintenance

    _fix1_data_root(monkeypatch, tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    root = root.resolve()
    store = TypedArtifactStore(root)
    _row(store, "m1", None, "m1", source="s1")
    db = store.db_path
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute("UPDATE memory_artifacts SET corroboration_count = 5")
        conn.commit()

    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        (row,) = maintenance._select_rows(
            "promotion_sweep",
            conn,
            root,
            owner_scope=legacy_owner_scope(root),
            batch_size=500,
            candidate_ids=["m1"],
        )
        assert json.loads(row["content"]) == {"text": "needle m1"}
        store.update_content("m1", {"text": "needle EDITED"})
        edited_version = _version(db, "m1")
        maintenance._mutate_promotion_sweep(conn, row, root)

    raw = _fix1_raw_content(db, "m1")
    assert json.loads(raw) == {"text": "needle EDITED"}
    assert _payload_row(db, "m1")[0] == _sha_text(raw)
    latest = _version(db, "m1")
    payload = store.get_version_payload("m1", latest)
    assert payload is not None
    text, digest = payload
    assert json.loads(text) == {"text": "needle EDITED"}
    assert digest == _sha_text(text)
    for version in range(edited_version, latest + 1):
        assert "needle m1" not in _payload_version_row(db, "m1", version)[0]


@pytest.mark.parametrize("path", ("archive", "expiry", "staleness", "promotion_sweep"))
def test_t01_fix2_j3_tampered_row_never_rebound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    """J3: a compact-JSON tamper never gains a `write`-consistent version row on any
    rewrite path, and the maintenance sweeps never rewrite it at all (guards W2, MP
    and MS)."""
    _fix1_data_root(monkeypatch, tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    root = root.resolve()
    _fix2_fixture_row(root, "t1", path)
    store = TypedArtifactStore(root)
    db = store.db_path
    _fix1_compact_tamper(db, "t1", FIX2_EVIL)
    tampered = _fix1_raw_content(db, "t1")
    before = _version(db, "t1")
    assert _payload_row(db, "t1")[0] != _sha_text(tampered)

    _fix2_run_path(root, "t1", path)

    raw = _fix1_raw_content(db, "t1")
    assert json.loads(raw) == FIX2_EVIL
    assert _payload_row(db, "t1")[0] != _sha_text(raw)
    latest = _version(db, "t1")
    if path in ("staleness", "promotion_sweep"):
        assert latest == before, f"{path} rewrote a payload-mismatched row"
    for version in range(before + 1, latest + 1):
        text, digest, origin = _payload_version_row(db, "t1", version)
        assert not (origin == "write" and digest == _sha_text(text)), version
    payload = store.get_version_payload("t1", latest)
    assert payload is not None
    text, digest = payload
    assert payload != (tampered, _sha_text(tampered))
    assert not (json.loads(text) == FIX2_EVIL and digest == _sha_text(text))
    _fix1_assert_quarantined(store, "t1", SUBJECT, "src-t1")


def test_t01_fix2_j4_compare_last_success_rechecks_before_emit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J4: a revoke committed after the baseline's reads (inside the cause scan) is
    no baseline."""
    from rush.memory import authorization as auth
    from rush.memory import retrieval
    from rush.memory.experience import compare_last_success, record_behavior_success

    data_root = _fix1_data_root(monkeypatch, tmp_path)
    root = _registered(tmp_path / "project", data_root)
    conditions = {"runtime": "py", "platform": "os", "code_digest": "c"}
    passed = record_behavior_success(
        project_root=root, behavior_id="behj4", conditions=conditions, source="src-j4"
    )
    grant = _grant(
        auth,
        root,
        legacy_owner_scope(root),
        data_root,
        sources=("src-j4",),
        ops=("ask",),
    )

    def compare() -> dict[str, Any]:
        return compare_last_success(
            project_root=root, behavior_id="behj4", conditions=conditions
        )

    assert compare()["baseline_ref"] == {"id": passed.id, "version": 1}
    fired = _fix1_fire_after(
        monkeypatch,
        retrieval,
        "visible_artifacts",
        lambda: _fix1_revoke(auth, grant, data_root),
    )
    result = compare()
    assert fired["n"] == 1
    assert result["baseline_ref"] is None


# --- 72-T01 PM post-cap fix (T068 J5-J8) -------------------------------------------


def _pm_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _fix1_data_root(monkeypatch, tmp_path)
    root = tmp_path / "project"
    root.mkdir()
    return root.resolve()


def _pm_set_content(db: Path, artifact_id: str, content: Any) -> None:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = ?",
            (content, artifact_id),
        )
        conn.commit()


def _pm_version_rows(db: Path, artifact_id: str) -> list[tuple[Any, Any, Any]]:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        return conn.execute(
            "SELECT content, payload_hash, payload_hash_origin "
            "FROM memory_artifact_versions WHERE artifact_id = ? "
            "ORDER BY artifact_version",
            (artifact_id,),
        ).fetchall()


def _pm_archive_unarchive(store: TypedArtifactStore, artifact_id: str) -> None:
    version = _version(store.db_path, artifact_id)
    for step, archived in enumerate((True, False)):
        applied = store.archive(
            artifact_id,
            expected_version=version + step,
            scope=SUBJECT,
            apply=True,
            archived=archived,
        )
        assert applied["applied"] is True


def test_t01_fix2_blob_content_never_rebound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J5: BLOB-typed stored content is never canonicalized into a `write`-consistent
    binding, and an honest unbound blob row keeps its `unbound` label."""
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility

    root = _pm_project(tmp_path, monkeypatch)
    store = TypedArtifactStore(root)
    db = store.db_path

    _row(store, "b1", None, "b1", source="sb1")
    before = _payload_row(db, "b1")
    _pm_set_content(db, "b1", json.dumps({"text": "needle EVIL"}).encode())
    _pm_archive_unarchive(store, "b1")
    for text, digest, origin in _pm_version_rows(db, "b1")[1:]:
        as_text = text.decode() if isinstance(text, bytes) else text
        assert not (origin == "write" and digest == _sha_text(as_text)), as_text
    assert _payload_row(db, "b1") == before
    _fix1_assert_quarantined(store, "b1", SUBJECT, "sb1")

    _row(store, "b2", None, "b2", source="sb2")
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET content = ?, payload_hash = NULL, "
            "payload_hash_origin = NULL WHERE id = 'b2'",
            (json.dumps({"text": "needle b2"}).encode(),),
        )
        conn.commit()
    access = MemoryAccess.legacy(root, ["sb2"])
    first = evaluate_artifact_visibility(
        store, store.get_current_row("b2"), access=access
    )
    assert first.usable_as_current is True, first.reason_codes
    assert first.reference["integrity"] == "unbound"
    _pm_archive_unarchive(store, "b2")
    after = evaluate_artifact_visibility(
        store, store.get_current_row("b2"), access=access
    )
    assert after.visible is True and after.usable_as_current is True, after.reason_codes
    assert after.reference["integrity"] == "unbound"
    assert _payload_row(db, "b2") == (None, None)


def test_t01_fix2_deep_nested_content_is_corrupt_not_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J6: content too deeply nested to parse is excluded as corrupt on every read
    route, and archive, expiry, maintenance and delete still complete."""
    from rush.memory.expiry import sweep_expired
    from rush.memory.maintenance import run_maintenance_cycle
    from rush.memory.retrieval import (
        MemoryAccess,
        defended_recall,
        evaluate_artifact_visibility,
        expand_artifact,
        recall_page,
    )

    root = _pm_project(tmp_path, monkeypatch)
    store = TypedArtifactStore(root)
    db = store.db_path
    _row(store, "ok1", None, "ok1", source="sd")
    for artifact_id in ("d1", "d2"):
        _row(
            store,
            artifact_id,
            None,
            artifact_id,
            source="sd",
            created_at=time.time() - 20 * DAY,
        )
        _pm_set_content(
            db,
            artifact_id,
            '{"text":"needle '
            + artifact_id
            + '","x":'
            + "[" * 100000
            + "]" * 100000
            + "}",
        )
    access = MemoryAccess.legacy(root, ["sd"])

    assert [a.id for a in defended_recall(store, SUBJECT, "needle", ["sd"])] == ["ok1"]
    assert [a.id for a in store.recall(SUBJECT, "needle", ["sd"], mode="ordinary")] == [
        "ok1"
    ]
    page = recall_page(store, subject=SUBJECT, query="needle", session_allowlist=["sd"])
    assert "d1" not in _dump(page) and "ok1" in _dump(page)
    denied = expand_artifact(store, artifact_id="d1", version=1, access=access)
    assert denied["code"] == "E_NOT_VISIBLE"
    historical = evaluate_artifact_visibility(
        store, store.get_current_row("d1"), access=access, mode="historical"
    )
    assert "integrity_content_corrupt" in historical.reason_codes

    _pm_archive_unarchive(store, "d1")
    sweep_expired(root, candidate_ids=["d2"])
    run_maintenance_cycle(
        "promotion_sweep",
        project_root=root,
        owner_scope=legacy_owner_scope(root),
        candidate_ids=["d1"],
    )
    result = store.delete_batch(
        ["d1", "d2"],
        expected_revisions={
            "d1": _version(db, "d1"),
            "d2": _version(db, "d2"),
        },
        scope=SUBJECT,
        apply=True,
    )
    assert result.get("applied") is True, result
    assert store.get_current_row("d1") is None
    assert store.get_current_row("d2") is None


@pytest.mark.parametrize("method", ["edit", "update_content"])
def test_t01_fix2_edit_and_update_content_keep_noncanonical_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    """J7: a same-content edit or update keeps an honest non-canonical row's bytes and
    binding; new content is bound with origin `write`."""
    root = _pm_project(tmp_path, monkeypatch)
    written = _fix2_fixture_row(root, "e1", "archive")
    noncanonical = json.dumps(written.content, ensure_ascii=False)
    db = TypedArtifactStore(root).db_path
    _pm_set_content(db, "e1", noncanonical)
    _drop_payload_columns(db)
    store = TypedArtifactStore(root)
    assert _payload_row(db, "e1") == (_sha_text(noncanonical), "backfill")

    def apply(content: dict[str, Any]) -> None:
        if method == "edit":
            store.edit(
                "e1",
                content,
                expected_version=_version(db, "e1"),
                scope=SUBJECT,
                apply=True,
            )
        else:
            store.update_content("e1", content)

    apply(dict(written.content))
    assert _fix1_raw_content(db, "e1") == noncanonical
    _fix2_assert_bound(store, "e1", "backfill", visible=method == "update_content")

    apply({"text": "needle new"})
    raw = _fix1_raw_content(db, "e1")
    assert json.loads(raw) == {"text": "needle new"}
    assert _payload_row(db, "e1") == (_sha_text(raw), "write")


def test_t01_fix2_second_source_scope_never_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J8: a same-owner row in a source outside the access is absent from every
    ordinary route, and expanding it is indistinguishable from a missing id."""
    from rush.memory.retrieval import (
        MemoryAccess,
        defended_recall,
        expand_artifact,
        recall_page,
    )

    root = _pm_project(tmp_path, monkeypatch)
    store = TypedArtifactStore(root)
    _row(store, "sa1", None, "sa1", source="source-a")
    _row(store, "sb1", None, "sb1 secret-b", source="source-b")
    access = MemoryAccess.legacy(root, ["source-a"])

    assert [a.id for a in defended_recall(store, SUBJECT, "needle", ["source-a"])] == [
        "sa1"
    ]
    recalled = store.recall(SUBJECT, "needle", ["source-a"], mode="ordinary")
    assert [a.id for a in recalled] == ["sa1"]
    page = recall_page(
        store, subject=SUBJECT, query="needle", session_allowlist=["source-a"]
    )
    assert "sb1" not in _dump(page) and "secret-b" not in _dump(page)
    denied = expand_artifact(store, artifact_id="sb1", version=1, access=access)
    missing = expand_artifact(store, artifact_id="zz-missing", version=1, access=access)
    assert denied["code"] == missing["code"] == "E_NOT_VISIBLE"
    assert {k: v for k, v in denied.items() if k != "id"} == {
        k: v for k, v in missing.items() if k != "id"
    }
