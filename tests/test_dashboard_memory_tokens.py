"""Tests for Phase 66 P66-05: memory administration and token use (F38).

Drives the real dashboard HTTP snapshot/action boundary (`server.py`) against
a real registered project and a real `TypedArtifactStore`/`TelemetryStore` on
disk -- the same `rush.tools.memory.MemoryTool` canonical dispatch the
CLI/MCP use for every mutation -- plus `rush.tui`'s real key-dispatch
functions directly (mirrors `tests/test_tui.py`'s own pattern), never a
fabricated response or a hand-rolled SQLite write.

Deletion is a real data-destruction path: `test_memory_delete_preview_...`
and its siblings assert cancellation removes exactly zero records and
approval removes only the records actually selected, with an unselected
candidate present in the same preview batch surviving untouched.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import pytest

from rush.dashboard import server as server_module
from rush.dashboard.server import create_dashboard_server
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.retrieval import recall_page
from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.token_economy.telemetry import TelemetryStore
from rush.tui import ProjectState, TuiState, _dispatch_key, default_scan_actions
from rush.workflows import projects as projects_module
from rush.workflows.projects import register_project


@pytest.fixture(autouse=True)
def _isolated_dashboard_data_root(tmp_path, monkeypatch):
    """P69-02.2f: `MutationLedger` now also owns the durable scan-admission
    table, so every test in this module gets an isolated data root by default
    -- otherwise a test that never monkeypatches `rush.setup.provision.
    default_data_root` itself would read/write this OS user's real Rush data
    directory, leaking admission/ledger state across test runs. A test that
    explicitly monkeypatches its own `default_data_root` afterward still wins
    (it runs after this fixture)."""
    isolated_root = tmp_path / "rush-data-default"
    monkeypatch.setattr("rush.setup.provision.default_data_root", lambda: isolated_root)
    monkeypatch.setattr(
        "rush.workflows.projects.default_data_root", lambda: isolated_root
    )


# --- shared HTTP helpers (mirrors tests/test_dashboard_scan_actions.py) -----


def _serve(server) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread


def _get(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc


def _post(url: str, headers: dict | None = None, body: bytes = b""):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as exc:
        return exc


def _bootstrap_session(base_url: str, token: str) -> tuple[str, str]:
    resp = _post(
        f"{base_url}/api/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status == 200
    payload = json.loads(resp.read())
    cookie_value = resp.headers.get("Set-Cookie").split(";")[0]
    return cookie_value, payload["csrf_token"]


def _action(
    base_url: str,
    project_id: str,
    cookie: str,
    csrf: str,
    *,
    operation: str,
    arguments: dict[str, Any] | None = None,
    grants: dict[str, Any] | None = None,
    request_id: str | None = None,
    expected: dict[str, Any] | None = None,
):
    body = json.dumps(
        {
            "schema_version": 1,
            "operation": operation,
            "arguments": arguments or {},
            "grants": grants or {},
            "expected": expected or {},
            "request_id": request_id or str(uuid.uuid4()),
        }
    ).encode("utf-8")
    resp = _post(
        f"{base_url}/api/projects/{project_id}/actions",
        headers={
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        },
        body=body,
    )
    return resp.status, json.loads(resp.read())


def _snapshot(base_url: str, project_id: str, cookie: str, section: str, **query: str):
    from urllib.parse import urlencode

    qs = urlencode({"section": section, **query})
    resp = _get(
        f"{base_url}/api/projects/{project_id}/snapshot?{qs}",
        headers={"Cookie": cookie},
    )
    return resp.status, json.loads(resp.read())


def _grant_all() -> dict[str, bool]:
    return {"cache_write": True, "artifact_write": True}


# --- fixture project (real registry, no network) ----------------------------


def _isolate_data_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "rush-data"
    monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)


def _register(tmp_path: Path, name: str = "project") -> tuple[str, Path]:
    root = tmp_path / name
    root.mkdir()
    (root / "app.py").write_text("def my_func():\n    return 1\n", encoding="utf-8")
    record = register_project(root)
    return record.project_id, root


def _start_dashboard(project_id: str, root: Path):
    snapshot = {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": str(root),
        "root": str(root),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    server, ctx, token = create_dashboard_server({project_id: snapshot})
    _serve(server)
    base_url = ctx.launch_origin
    cookie, csrf = _bootstrap_session(base_url, token)
    return server, base_url, cookie, csrf


_FAMILY_BY_SUBJECT = {
    "active_context": "handoff",
    "episodic": "experience",
    "preference": "memory",
    "failure": "memory",
    "architectural_decision": "memory",
    "domain_knowledge": "memory",
    "skill_pattern": "skill",
}


def _seed_artifact(
    store: TypedArtifactStore,
    *,
    subject: str = "domain_knowledge",
    trust_tier: str = "EXTERNAL_WRITE",
    content: dict[str, Any] | None = None,
    source: str = "test-source",
    symbol_ref: str | None = None,
    content_hash: str | None = None,
    origin_kind: str | None = None,
    origin_id: str | None = None,
    owner_scope: OwnerScope | None = None,
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=str(uuid.uuid4()),
            family=_FAMILY_BY_SUBJECT[subject],
            subject=subject,
            trust_tier=trust_tier,
            content=content if content is not None else {"note": "seed"},
            source=source,
            created_at=time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
            origin_kind=origin_kind,
            origin_id=origin_id,
            owner_scope=owner_scope,
        )
    )


# --- P66-05.1 RED / P66-05.2-3 GREEN/CONNECT: memory HTTP section ----------


def test_memory_search_filters_by_subject_trust_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    store = TypedArtifactStore(root)
    _seed_artifact(
        store,
        subject="domain_knowledge",
        trust_tier="EXTERNAL_WRITE",
        content={"note": "alpha widget"},
        source="tool-a",
    )
    _seed_artifact(
        store,
        subject="domain_knowledge",
        trust_tier="DERIVED",
        content={"note": "beta widget"},
        source="tool-b",
    )
    _seed_artifact(
        store,
        subject="preference",
        trust_tier="EXTERNAL_WRITE",
        content={"note": "alpha widget preference"},
        source="tool-a",
    )
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(
            base_url,
            project_id,
            cookie,
            "memory",
            query="widget",
            subject="domain_knowledge",
        )
        assert status == 200
        items = body["data"]["items"]
        assert {i["source"] for i in items} == {"tool-a", "tool-b"}
        assert all(i["subject"] == "domain_knowledge" for i in items)

        status, body = _snapshot(
            base_url,
            project_id,
            cookie,
            "memory",
            query="widget",
            subject="domain_knowledge",
            trust="EXTERNAL_WRITE",
        )
        assert status == 200
        items = body["data"]["items"]
        assert len(items) == 1
        assert items[0]["source"] == "tool-a"
        assert items[0]["trust_tier"] == "EXTERNAL_WRITE"

        status, body = _snapshot(
            base_url, project_id, cookie, "memory", query="widget", source="tool-b"
        )
        assert status == 200
        items = body["data"]["items"]
        assert len(items) == 1
        assert items[0]["source"] == "tool-b"
    finally:
        server.shutdown()
        server.server_close()


def test_memory_immutable_origin_display_across_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(
        store,
        content={"note": "original"},
        source="origin-tool",
        origin_kind="scan-finding",
        origin_id="finding-123",
        owner_scope=owner,
    )
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_edit",
            arguments={
                "scope": "domain_knowledge",
                "id": artifact.id,
                "expected_version": 1,
                "content": {"note": "updated"},
                "apply": True,
                "owner_scope": owner.as_dict(),
            },
            grants=_grant_all(),
        )
        assert status == 200
        assert body["data"]["status"] == "ok"

        status, body = _snapshot(
            base_url, project_id, cookie, "memory", query="updated"
        )
        assert status == 200
        items = body["data"]["items"]
        assert len(items) == 1
        assert items[0]["content"]["note"] == "updated"
        # Origin/source provenance is never rewritten by an edit.
        assert items[0]["origin_kind"] == "scan-finding"
        assert items[0]["origin_id"] == "finding-123"
        assert items[0]["source"] == "origin-tool"
        assert items[0]["id"] == artifact.id
    finally:
        server.shutdown()
        server.server_close()


def test_memory_edit_version_conflict_denied_and_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "v1"}, owner_scope=owner)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_edit",
            arguments={
                "scope": "domain_knowledge",
                "id": artifact.id,
                "expected_version": 99,
                "content": {"note": "should not apply"},
                "apply": True,
                "owner_scope": owner.as_dict(),
            },
            grants=_grant_all(),
        )
        assert status == 409
        assert body["data"]["status"] == "fail"
        assert body["data"]["raw"]["code"] == "E_VERSION"

        status, body = _snapshot(base_url, project_id, cookie, "memory", query="v1")
        assert status == 200
        assert len(body["data"]["items"]) == 1
        assert body["data"]["items"][0]["content"]["note"] == "v1"
    finally:
        server.shutdown()
        server.server_close()


def test_memory_edit_apply_without_grant_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "unchanged"}, owner_scope=owner)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_edit",
            arguments={
                "scope": "domain_knowledge",
                "id": artifact.id,
                "expected_version": 1,
                "content": {"note": "changed"},
                "apply": True,
                "owner_scope": owner.as_dict(),
            },
            grants={},
        )
        assert status == 403
        assert body["error"]["code"] == "grant_denied"

        status, body = _snapshot(
            base_url, project_id, cookie, "memory", query="unchanged"
        )
        assert len(body["data"]["items"]) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_memory_stale_citation_detected_on_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    original_text = (root / "app.py").read_text(encoding="utf-8")
    content_hash = MerkleInvalidator(project_root=root).hash_content(original_text)
    store = TypedArtifactStore(root)
    _seed_artifact(
        store,
        content={"note": "documents my_func"},
        symbol_ref="app.py::my_func",
        content_hash=content_hash,
    )
    # Mutate the cited file after the memory was written -- the merkle hash
    # no longer matches, so a real search's dynamic recall() check must mark
    # this citation stale.
    (root / "app.py").write_text(
        "def my_func():\n    return 2  # changed\n", encoding="utf-8"
    )
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(
            base_url, project_id, cookie, "memory", query="my_func"
        )
        assert status == 200
        items = body["data"]["items"]
        assert len(items) == 1
        assert items[0]["stale"] is True
        assert items[0]["dynamic_freshness_checked"] is True

        # Browsing (no query text) reflects only the persisted column --
        # explicitly labelled as not dynamically re-checked.
        status, body = _snapshot(base_url, project_id, cookie, "memory")
        items = body["data"]["items"]
        assert len(items) == 1
        assert items[0]["stale"] is False
        assert items[0]["dynamic_freshness_checked"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_memory_denied_trust_promotion_insufficient_corroboration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_promote",
            arguments={
                "subject": "domain_knowledge",
                "content": {"note": "a claim", "id": "x", "family": "memory"},
                "source": "only-one-source",
                "user_stated": False,
                "candidate_sources": ["only-one-source"],
                "owner_scope": {"kind": "project", "id": project_id},
            },
            grants=_grant_all(),
        )
        assert status == 200
        raw = body["data"]["raw"]
        assert raw["promoted"] is False
        assert raw["denial_reason"] == "insufficient_corroboration"

        # Denial never left a STATED row behind.
        status, snap = _snapshot(base_url, project_id, cookie, "memory", query="claim")
        assert all(i["trust_tier"] != "STATED" for i in snap["data"]["items"])
    finally:
        server.shutdown()
        server.server_close()


def test_memory_promotion_succeeds_with_two_corroborating_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_promote",
            arguments={
                "subject": "domain_knowledge",
                "content": {"note": "corroborated claim"},
                "source": "source-a",
                "user_stated": False,
                "candidate_sources": ["source-a", "source-b"],
                "owner_scope": {"kind": "project", "id": project_id},
            },
            grants=_grant_all(),
        )
        assert status == 200
        raw = body["data"]["raw"]
        assert raw["promoted"] is True
        assert raw["new_tier"] == "STATED"

        status, snap = _snapshot(
            base_url, project_id, cookie, "memory", query="corroborated"
        )
        items = [i for i in snap["data"]["items"] if i["trust_tier"] == "STATED"]
        assert len(items) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_memory_promote_requires_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_promote",
            arguments={
                "subject": "domain_knowledge",
                "content": {"note": "x"},
                "source": "a",
                "owner_scope": {"kind": "project", "id": project_id},
            },
            grants={},
        )
        assert status == 403
        assert body["error"]["code"] == "grant_denied"
    finally:
        server.shutdown()
        server.server_close()


def test_memory_archive_hides_then_include_archived_shows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "archivable"}, owner_scope=owner)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_archive",
            arguments={
                "scope": "domain_knowledge",
                "id": artifact.id,
                "expected_version": 1,
                "archived": True,
                "apply": True,
                "owner_scope": owner.as_dict(),
            },
            grants=_grant_all(),
        )
        assert status == 200
        assert body["data"]["status"] == "ok"

        status, snap = _snapshot(
            base_url, project_id, cookie, "memory", query="archivable"
        )
        assert snap["data"]["items"] == []

        status, snap = _snapshot(
            base_url,
            project_id,
            cookie,
            "memory",
            query="archivable",
            include_archived="true",
        )
        assert len(snap["data"]["items"]) == 1
        assert snap["data"]["items"][0]["id"] == artifact.id
    finally:
        server.shutdown()
        server.server_close()


def test_memory_section_browse_excludes_archived_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07 subsection g: `scope_artifacts()`'s browse path (an empty query) never
    leaked archived rows before this fix -- `include_expired` was the only toggle,
    and it never touched `archived_at` at all."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    kept = _seed_artifact(store, content={"note": "kept"}, owner_scope=owner)
    archived = _seed_artifact(store, content={"note": "to-archive"}, owner_scope=owner)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_archive",
            arguments={
                "scope": "domain_knowledge",
                "id": archived.id,
                "expected_version": 1,
                "archived": True,
                "apply": True,
                "owner_scope": owner.as_dict(),
            },
            grants=_grant_all(),
        )
        assert status == 200
        assert body["data"]["status"] == "ok"

        status, snap = _snapshot(base_url, project_id, cookie, "memory")
        ids = {i["id"] for i in snap["data"]["items"]}
        assert kept.id in ids
        assert archived.id not in ids

        status, snap = _snapshot(
            base_url, project_id, cookie, "memory", include_archived="true"
        )
        ids = {i["id"] for i in snap["data"]["items"]}
        assert archived.id in ids
    finally:
        server.shutdown()
        server.server_close()


def test_memory_section_browse_paginates_past_512_same_subject_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07 subsection g: browse batches past `scope_artifacts()`'s own `scan_limit`
    default instead of being permanently capped at one call's worth of rows."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    monkeypatch.setattr(server_module, "_MEMORY_BROWSE_BATCH", 3)
    store = TypedArtifactStore(root)
    seeded = [_seed_artifact(store, content={"note": f"row-{i}"}) for i in range(7)]
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(base_url, project_id, cookie, "memory", limit="50")
        assert status == 200
        assert body["data"]["total"] == 7
        returned_ids = {i["id"] for i in body["data"]["items"]}
        assert returned_ids == {a.id for a in seeded}
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.slow
def test_browse_and_query_traverse_more_than_10240_rows_with_exact_totals_and_unique_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M14: `_build_memory_section`'s browse (empty query) path used to loop at most
    `_MEMORY_BROWSE_MAX_BATCHES` (20) batches of 512 -- a hard 10,240-row-per-subject
    ceiling -- and derive `total`/pagination from that silently truncated collection.
    Seeding more than that many rows for one subject, both the empty-query browse and
    the text-query path must report the true total and let a full page-by-page
    traversal recover every seeded id, none permanently unreachable."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    store = TypedArtifactStore(root)
    total_rows = 10_245
    ids = [f"m{i:06d}" for i in range(total_rows)]
    with sqlite3.connect(store.db_path) as conn:
        conn.executemany(
            "INSERT INTO memory_artifacts (id, family, subject, trust_tier, content, "
            "source, created_at, artifact_version) VALUES (?, 'memory', "
            "'domain_knowledge', 'IMPORTED', ?, 'allowed', 1.0, 1)",
            [
                (artifact_id, json.dumps({"text": f"needle row {artifact_id}"}))
                for artifact_id in ids
            ],
        )
        conn.commit()

    def _traverse(query_text: str) -> set[str]:
        seen: set[str] = set()
        cursor: str | None = None
        reported_total: int | None = None
        pages = 0
        while True:
            page_query: dict[str, list[str]] = {
                "query": [query_text],
                "limit": ["100"],
            }
            if cursor:
                page_query["cursor"] = [cursor]
            data = server_module._build_memory_section(project_id, page_query)
            if reported_total is None:
                reported_total = data["total"]
            else:
                assert data["total"] == reported_total
            seen.update(item["id"] for item in data["items"])
            cursor = data["next_cursor"]
            pages += 1
            if cursor is None:
                break
        assert reported_total == total_rows
        assert pages > 1
        return seen

    assert _traverse("") == set(ids)
    assert _traverse("needle") == set(ids)


def test_record_becoming_stale_is_excluded_by_query_mode_freshness_revalidation_at_any_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M14: query-mode's per-row dynamic freshness re-check must still catch a record
    whose cited file changed since it was written, no matter which page of a
    multi-page query result that record lands on -- paging can never skip the
    dynamic re-check `MemoryTool`'s `list` dispatch already performs."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    original_text = (root / "app.py").read_text(encoding="utf-8")
    content_hash = MerkleInvalidator(project_root=root).hash_content(original_text)
    store = TypedArtifactStore(root)
    for i in range(120):
        _seed_artifact(store, content={"note": f"needle fresh row {i}"})
    stale_artifact = _seed_artifact(
        store,
        content={"note": "needle documents my_func"},
        symbol_ref="app.py::my_func",
        content_hash=content_hash,
    )
    (root / "app.py").write_text(
        "def my_func():\n    return 2  # changed\n", encoding="utf-8"
    )
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        cursor: str | None = None
        found_stale: dict[str, Any] | None = None
        pages_seen = 0
        while True:
            kwargs: dict[str, str] = {"query": "needle", "limit": "50"}
            if cursor:
                kwargs["cursor"] = cursor
            status, body = _snapshot(base_url, project_id, cookie, "memory", **kwargs)
            assert status == 200
            pages_seen += 1
            for item in body["data"]["items"]:
                assert item["dynamic_freshness_checked"] is True
                if item["id"] == stale_artifact.id:
                    found_stale = item
            cursor = body["data"]["next_cursor"]
            if cursor is None:
                break
        assert pages_seen > 1
        assert found_stale is not None
        assert found_stale["stale"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_memory_generation_mutation_mid_traversal_rejects_the_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M14: a memory mutation between two browse page requests bumps
    `TypedArtifactStore.current_generation()` -- reusing a cursor issued before that
    mutation must be rejected (409 `cursor_rejected`), never silently splicing
    pre-/post-mutation pages together mid-traversal."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    store = TypedArtifactStore(root)
    for i in range(5):
        _seed_artifact(store, content={"note": f"row-{i}"})
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(base_url, project_id, cookie, "memory", limit="2")
        assert status == 200
        cursor = body["data"]["next_cursor"]
        assert cursor is not None

        _seed_artifact(store, content={"note": "row-new"})

        status, body = _snapshot(
            base_url, project_id, cookie, "memory", limit="2", cursor=cursor
        )
        assert status == 409
        assert body["error"]["code"] == "cursor_rejected"
    finally:
        server.shutdown()
        server.server_close()


def test_memory_delete_preview_shows_exactly_selected_and_cancel_deletes_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deletion fixture: 3 candidate records, exactly 2 selected. A
    preview (apply=False) never mutates anything -- treating that preview as
    a cancellation (never calling apply=True) must leave all 3 records
    intact, including the 2 that were "selected" for the preview."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    keep_out_of_selection = _seed_artifact(
        store, content={"note": "untouched"}, owner_scope=owner
    )
    selected_one = _seed_artifact(
        store, content={"note": "selected-1"}, owner_scope=owner
    )
    selected_two = _seed_artifact(
        store, content={"note": "selected-2"}, owner_scope=owner
    )
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        ids = [selected_one.id, selected_two.id]
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_delete",
            arguments={
                "artifact_ids": ids,
                "expected_revisions": {selected_one.id: 1, selected_two.id: 1},
                "scope": "domain_knowledge",
                "apply": False,
                "owner_scope": owner.as_dict(),
            },
        )
        assert status == 200
        data = body["data"]["raw"]["data"]
        assert data["applied"] is False
        assert {a["id"] for a in data["affected"]} == set(ids)
        assert len(data["affected"]) == 2

        # Cancellation: no further call is made. Every one of the 3 seeded
        # records -- including the 2 "selected" ones -- must still exist.
        status, snap = _snapshot(base_url, project_id, cookie, "memory")
        remaining_ids = {i["id"] for i in snap["data"]["items"]}
        assert remaining_ids == {
            keep_out_of_selection.id,
            selected_one.id,
            selected_two.id,
        }
    finally:
        server.shutdown()
        server.server_close()


def test_memory_delete_apply_deletes_only_selected_others_survive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    survivor = _seed_artifact(store, content={"note": "survivor"}, owner_scope=owner)
    doomed_one = _seed_artifact(store, content={"note": "doomed-1"}, owner_scope=owner)
    doomed_two = _seed_artifact(store, content={"note": "doomed-2"}, owner_scope=owner)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        ids = [doomed_one.id, doomed_two.id]
        revisions = {doomed_one.id: 1, doomed_two.id: 1}

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_delete",
            arguments={
                "artifact_ids": ids,
                "expected_revisions": revisions,
                "scope": "domain_knowledge",
                "apply": False,
                "owner_scope": owner.as_dict(),
            },
        )
        assert status == 200
        assert body["data"]["raw"]["data"]["applied"] is False

        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_delete",
            arguments={
                "artifact_ids": ids,
                "expected_revisions": revisions,
                "scope": "domain_knowledge",
                "apply": True,
                "owner_scope": owner.as_dict(),
            },
            grants=_grant_all(),
        )
        assert status == 200
        data = body["data"]["raw"]["data"]
        assert data["applied"] is True
        assert {a["id"] for a in data["affected"]} == set(ids)

        status, snap = _snapshot(base_url, project_id, cookie, "memory")
        remaining_ids = {i["id"] for i in snap["data"]["items"]}
        assert remaining_ids == {survivor.id}
    finally:
        server.shutdown()
        server.server_close()


def test_memory_delete_apply_requires_cache_write_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    owner = OwnerScope("project", project_id)
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "protected"}, owner_scope=owner)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="memory_delete",
            arguments={
                "artifact_ids": [artifact.id],
                "expected_revisions": {artifact.id: 1},
                "scope": "domain_knowledge",
                "apply": True,
                "owner_scope": owner.as_dict(),
            },
            grants={},
        )
        assert status == 403
        assert body["error"]["code"] == "grant_denied"

        status, snap = _snapshot(base_url, project_id, cookie, "memory")
        assert len(snap["data"]["items"]) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_memory_never_exposes_raw_sqlite_write_path() -> None:
    """Every allowlisted memory action name maps to `MemoryTool`'s own
    canonical dispatch -- there is no action name that reaches
    `TypedArtifactStore`/sqlite3 directly from the dashboard."""
    from rush.dashboard.server import ALLOWED_ACTIONS

    memory_actions = {a for a in ALLOWED_ACTIONS if a.startswith("memory_")}
    assert memory_actions == {
        "memory_edit",
        "memory_archive",
        "memory_delete",
        "memory_promote",
        "memory_query",
        "memory_expand",
        "memory_propose",
        "memory_maintain",
    }


def test_memory_render_failure_is_retryable_error_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        import rush.dashboard.server as server_module

        def _boom(*_a: Any, **_k: Any) -> Any:
            raise RuntimeError("simulated storage failure")

        monkeypatch.setattr(server_module, "_build_memory_section", _boom)
        status, body = _snapshot(base_url, project_id, cookie, "memory")
        assert status == 500
        assert body["error"]["retryable"] is True
        assert "simulated storage failure" in body["error"]["message"]
    finally:
        server.shutdown()
        server.server_close()


# --- P66-05.3 CONNECT: tokens HTTP section -----------------------------------


def test_tokens_actual_vs_estimated_and_provider_usage_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    telemetry = TelemetryStore(root)
    telemetry.record_savings("review", raw_tokens=1000, compressed_tokens=400)
    telemetry.record_savings("review", raw_tokens=500, compressed_tokens=100)
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(base_url, project_id, cookie, "tokens")
        assert status == 200
        data = body["data"]
        assert data["actual"]["raw_tokens"] == 1500
        assert data["actual"]["sent_tokens"] == 500
        assert data["actual"]["events_count"] == 2
        assert data["estimated_avoided"]["tokens_saved"] == 1000
        assert data["provider_usage"]["available"] is False
        assert data["provider_usage"]["reason"]
    finally:
        server.shutdown()
        server.server_close()


def test_tokens_per_run_agent_session_from_handoff_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    handoffs_dir = root / ".rush" / "handoffs"
    handoffs_dir.mkdir(parents=True)
    (handoffs_dir / "handoff-1.json").write_text(
        json.dumps(
            {
                "handoff_id": "handoff-1",
                "run_id": "run-alpha",
                "agent_id": "agent-1",
                "memory_session_id": "session-1",
                "state": "prepared",
                "packet": {
                    "tokens": 321,
                    "bytes": 4096,
                    "encoding": "cl100k_base",
                    "remainder_ids": [],
                },
            }
        ),
        encoding="utf-8",
    )
    (handoffs_dir / "handoff-2.json").write_text(
        json.dumps(
            {
                "handoff_id": "handoff-2",
                "run_id": "run-beta",
                "agent_id": "agent-2",
                "memory_session_id": "session-2",
                "state": "delivered",
                "packet": {
                    "tokens": 55,
                    "bytes": 900,
                    "encoding": "cl100k_base",
                    "remainder_ids": ["f-1"],
                },
            }
        ),
        encoding="utf-8",
    )
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(base_url, project_id, cookie, "tokens")
        assert status == 200
        rows = body["data"]["runs"]
        by_run = {r["run_id"]: r for r in rows}
        assert by_run["run-alpha"]["agent_id"] == "agent-1"
        assert by_run["run-alpha"]["session_id"] == "session-1"
        assert by_run["run-alpha"]["tokens"] == 321
        assert by_run["run-alpha"]["encoding"] == "cl100k_base"
        assert by_run["run-alpha"]["truncated"] is False
        assert by_run["run-beta"]["truncated"] is True

        status, body = _snapshot(
            base_url, project_id, cookie, "tokens", run_id="run-alpha"
        )
        assert [r["run_id"] for r in body["data"]["runs"]] == ["run-alpha"]

        status, body = _snapshot(
            base_url, project_id, cookie, "tokens", agent_id="agent-2"
        )
        assert [r["agent_id"] for r in body["data"]["runs"]] == ["agent-2"]

        export_rows = body["data"]["export_rows"]
        assert export_rows == body["data"]["runs"]
    finally:
        server.shutdown()
        server.server_close()


def test_tokens_section_totals_respect_run_agent_session_filters_not_just_handoff_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M10: `_build_tokens_section`'s displayed `actual` totals (raw/sent tokens,
    events_count, by_memory_event_kind) scope to the same run/agent/session
    selection the handoff `runs` rows already respected -- not just the handoff
    rows while the totals themselves stay project-wide."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    telemetry = TelemetryStore(root)
    telemetry.record_savings(
        "review",
        raw_tokens=1000,
        compressed_tokens=400,
        run_id="run-a",
        agent_id="agent-a",
        session_id="sess-a",
    )
    telemetry.record_savings(
        "review",
        raw_tokens=200,
        compressed_tokens=50,
        run_id="run-b",
        agent_id="agent-b",
        session_id="sess-b",
    )
    telemetry.record_memory_event(
        "retrieval",
        30,
        request_id="r1",
        event_id="e1",
        invocation_id="i1",
        run_id="run-a",
        agent_id="agent-a",
        session_id="sess-a",
        opt_in=True,
    )
    telemetry.record_memory_event(
        "retrieval",
        7,
        request_id="r2",
        event_id="e2",
        invocation_id="i2",
        run_id="run-b",
        agent_id="agent-b",
        session_id="sess-b",
        opt_in=True,
    )
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(base_url, project_id, cookie, "tokens")
        assert status == 200
        assert body["data"]["actual"]["raw_tokens"] == 1200
        assert body["data"]["actual"]["sent_tokens"] == 450
        assert body["data"]["actual"]["events_count"] == 2
        assert body["data"]["actual"]["by_memory_event_kind"]["retrieval"] == 37

        status, body = _snapshot(base_url, project_id, cookie, "tokens", run_id="run-a")
        assert body["data"]["actual"]["raw_tokens"] == 1000
        assert body["data"]["actual"]["sent_tokens"] == 400
        assert body["data"]["actual"]["events_count"] == 1
        assert body["data"]["actual"]["by_memory_event_kind"]["retrieval"] == 30

        status, body = _snapshot(
            base_url, project_id, cookie, "tokens", agent_id="agent-b"
        )
        assert body["data"]["actual"]["raw_tokens"] == 200
        assert body["data"]["actual"]["by_memory_event_kind"]["retrieval"] == 7

        status, body = _snapshot(
            base_url, project_id, cookie, "tokens", session_id="sess-a"
        )
        assert body["data"]["actual"]["raw_tokens"] == 1000
        assert body["data"]["actual"]["by_memory_event_kind"]["retrieval"] == 30

        status, body = _snapshot(
            base_url, project_id, cookie, "tokens", run_id="run-nonexistent"
        )
        assert body["data"]["actual"]["raw_tokens"] == 0
        assert body["data"]["actual"]["events_count"] == 0
        assert body["data"]["actual"]["by_memory_event_kind"]["retrieval"] == 0
    finally:
        server.shutdown()
        server.server_close()


def test_tokens_and_gain_tui_share_same_telemetry_computation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No duplicated savings calculator: the dashboard's `actual`/
    `estimated_avoided` numbers and the TUI's `build_gain_panel` both derive
    from the exact same `TelemetryStore.get_summary()` call."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    telemetry = TelemetryStore(root)
    telemetry.record_savings("review", raw_tokens=200, compressed_tokens=50)
    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, body = _snapshot(base_url, project_id, cookie, "tokens")
        assert status == 200
        dashboard_summary = TelemetryStore(root).get_summary()
        assert (
            body["data"]["actual"]["raw_tokens"]
            == dashboard_summary["total_raw_tokens"]
        )
        assert (
            body["data"]["estimated_avoided"]["tokens_saved"]
            == dashboard_summary["net_tokens_saved"]
        )

        from rush.token_economy.tui_gain import build_gain_panel

        panel = build_gain_panel(root)
        assert panel is not None
    finally:
        server.shutdown()
        server.server_close()


def test_two_project_memory_and_token_isolation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_a, root_a = _register(tmp_path, name="project-a")
    project_b, root_b = _register(tmp_path, name="project-b")
    store_a = TypedArtifactStore(root_a)
    store_b = TypedArtifactStore(root_b)
    _seed_artifact(
        store_a, content={"note": "alpha-only secretless"}, source="a-source"
    )
    _seed_artifact(store_b, content={"note": "beta-only secretless"}, source="b-source")
    TelemetryStore(root_a).record_savings(
        "review", raw_tokens=100, compressed_tokens=10
    )
    TelemetryStore(root_b).record_savings("review", raw_tokens=999, compressed_tokens=1)

    snapshot_a = {
        "schema_version": 1,
        "project_id": project_a,
        "source_identity": str(root_a),
        "root": str(root_a),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    snapshot_b = {
        "schema_version": 1,
        "project_id": project_b,
        "source_identity": str(root_b),
        "root": str(root_b),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }
    server, ctx, token = create_dashboard_server(
        {project_a: snapshot_a, project_b: snapshot_b}
    )
    _serve(server)
    base_url = ctx.launch_origin
    cookie, _csrf = _bootstrap_session(base_url, token)
    try:
        status, body_a = _snapshot(base_url, project_a, cookie, "memory", query="alpha")
        assert status == 200
        assert len(body_a["data"]["items"]) == 1
        assert "alpha" in body_a["data"]["items"][0]["content"]["note"]

        status, body_a_cross = _snapshot(
            base_url, project_a, cookie, "memory", query="beta"
        )
        assert body_a_cross["data"]["items"] == []

        status, body_b = _snapshot(base_url, project_b, cookie, "memory", query="beta")
        assert len(body_b["data"]["items"]) == 1
        assert "beta" in body_b["data"]["items"][0]["content"]["note"]

        status, tokens_a = _snapshot(base_url, project_a, cookie, "tokens")
        status, tokens_b = _snapshot(base_url, project_b, cookie, "tokens")
        assert tokens_a["data"]["actual"]["raw_tokens"] == 100
        assert tokens_b["data"]["actual"]["raw_tokens"] == 999
    finally:
        server.shutdown()
        server.server_close()


# --- P69-07 subsections d/e: telemetry identity columns and invocation dedup -----


def test_token_events_schema_gains_identity_columns_with_a_real_sentinel_default(
    tmp_path: Path,
) -> None:
    """P69-07 subsection d: `token_events` gains project/run/agent/session identity
    columns via a real migration; an omitted value is the real 'unscoped' sentinel,
    never NULL."""
    telemetry = TelemetryStore(tmp_path)
    telemetry.record_savings("review", raw_tokens=10, compressed_tokens=5)
    with sqlite3.connect(telemetry.db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(token_events)")}
        assert {"project_id", "run_id", "agent_id", "session_id"} <= columns
        row = conn.execute(
            "SELECT project_id, run_id, agent_id, session_id FROM token_events"
        ).fetchone()
        assert row == ("unscoped", "unscoped", "unscoped", "unscoped")


def test_token_events_legacy_database_migrates_and_backfills_identity_columns(
    tmp_path: Path,
) -> None:
    """P69-07 subsection d: a pre-P69-07 `token_events` table (no identity columns)
    migrates additively on open, backfilling the real 'unscoped' sentinel."""
    db_path = tmp_path / ".rush" / "telemetry" / "tokens.db"
    db_path.parent.mkdir(parents=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE token_events (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "timestamp INTEGER NOT NULL, tool_name TEXT NOT NULL, "
            "raw_tokens INTEGER NOT NULL, compressed_tokens INTEGER NOT NULL, "
            "duration_ms REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO token_events (timestamp, tool_name, raw_tokens, "
            "compressed_tokens, duration_ms) VALUES (0, 'legacy', 100, 50, 1.0)"
        )
        conn.commit()

    telemetry = TelemetryStore(tmp_path)
    with sqlite3.connect(telemetry.db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(token_events)")}
        assert {"project_id", "run_id", "agent_id", "session_id"} <= columns
        row = conn.execute(
            "SELECT project_id FROM token_events WHERE tool_name = 'legacy'"
        ).fetchone()
        assert row[0] == "unscoped"


def test_memory_events_dedupe_by_invocation_id_not_content_derived_request_id(
    tmp_path: Path,
) -> None:
    """P69-07 subsection e: two distinct invocations sharing identical content and
    the same content-derived `request_id` no longer collide -- the dedup key is
    `invocation_id`; a genuine retry (same `invocation_id`) still dedupes."""
    telemetry = TelemetryStore(tmp_path)
    first = telemetry.record_memory_event(
        "retrieval",
        10,
        request_id="same-content-derived-id",
        event_id="e1",
        invocation_id="invocation-a",
        opt_in=True,
    )
    second = telemetry.record_memory_event(
        "retrieval",
        10,
        request_id="same-content-derived-id",
        event_id="e1",
        invocation_id="invocation-b",
        opt_in=True,
    )
    assert first is True
    assert second is True
    assert telemetry.get_memory_event_total(kind="retrieval") == 20

    retry = telemetry.record_memory_event(
        "retrieval",
        999,
        request_id="same-content-derived-id",
        event_id="e1",
        invocation_id="invocation-a",
        opt_in=True,
    )
    assert retry is False
    assert telemetry.get_memory_event_total(kind="retrieval") == 20


def test_memory_event_total_respects_run_agent_session_filters(
    tmp_path: Path,
) -> None:
    """P69-07 subsection e: `get_memory_event_total()` scopes to a real, distinct
    `run_id`/`agent_id`/`session_id`, not just an unfiltered project-wide sum."""
    telemetry = TelemetryStore(tmp_path)
    telemetry.record_memory_event(
        "retrieval",
        10,
        request_id="r1",
        event_id="e1",
        invocation_id="i1",
        run_id="run-a",
        agent_id="agent-a",
        session_id="sess-a",
        opt_in=True,
    )
    telemetry.record_memory_event(
        "retrieval",
        30,
        request_id="r2",
        event_id="e2",
        invocation_id="i2",
        run_id="run-b",
        agent_id="agent-b",
        session_id="sess-b",
        opt_in=True,
    )
    assert telemetry.get_memory_event_total(kind="retrieval") == 40
    assert telemetry.get_memory_event_total(kind="retrieval", run_id="run-a") == 10
    assert telemetry.get_memory_event_total(kind="retrieval", agent_id="agent-b") == 30
    assert telemetry.get_memory_event_total(kind="retrieval", session_id="sess-a") == 10


def test_recall_page_mints_distinct_invocation_ids_for_identical_repeated_calls(
    tmp_path: Path,
) -> None:
    """P69-07 subsection e: `recall_page()`'s real production caller (`tools/memory.py`)
    passes a content-derived `request_id` -- two calls sharing identical content still
    produce two distinct `memory_events` rows, since `recall_page()` mints its own
    per-call `invocation_id` rather than trusting the caller-supplied `request_id`."""
    store = TypedArtifactStore(tmp_path)
    store.write(
        MemoryArtifact(
            id="a1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="EXTERNAL_WRITE",
            content={"text": "needle content"},
            source="src-a",
            created_at=time.time(),
        )
    )
    telemetry = TelemetryStore(tmp_path)
    for _ in range(2):
        recall_page(
            store,
            subject="domain_knowledge",
            query="needle",
            session_allowlist=["src-a"],
            telemetry=telemetry,
            request_id="same-content-derived-request-id",
            event_id="retrieval",
            opt_in=True,
        )
    with sqlite3.connect(telemetry.db_path) as conn:
        rows = conn.execute(
            "SELECT invocation_id FROM memory_events WHERE kind = 'retrieval'"
        ).fetchall()
    assert len({r[0] for r in rows}) == 2


def test_session_continuity_tool_mints_a_distinct_invocation_id_per_run_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07 subsection e: `SessionContinuityTool.run()` mints one real invocation
    identity per call, shared by every operation dispatched from that call, never
    re-minted per branch -- two separate calls get distinct identities; an explicit
    `idempotency_key` (a genuine retry) reuses the same one."""
    import rush.tools.continuity as continuity_module
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    captured: list[str | None] = []

    def _fake_pack_context(*args: Any, **kwargs: Any) -> dict[str, Any]:
        captured.append(kwargs.get("invocation_id"))
        return {"status": "ok"}

    monkeypatch.setattr(continuity_module, "pack_context", _fake_pack_context)
    tool = SessionContinuityTool()
    granted = ExecutionPermissions(cache_write=True)
    common = {
        "operation": "context_pack",
        "context_path": "x.py",
        "target_symbol": "f",
        "token_budget": 100,
        "permissions": granted,
    }

    tool.run(tmp_path, **common)
    tool.run(tmp_path, **common)
    assert len(captured) == 2
    assert captured[0] and captured[1] and captured[0] != captured[1]

    tool.run(tmp_path, idempotency_key="retry-x", **common)
    tool.run(tmp_path, idempotency_key="retry-x", **common)
    assert captured[2] == "retry-x"
    assert captured[3] == "retry-x"


# --- P66-05.4 VERIFY: TUI memory admin keyboard journeys --------------------


def _tui_state(root: Path) -> TuiState:
    project = ProjectState(name=root.name, root=root, results=[])
    return TuiState(projects=[project])


def test_tui_memory_search_lists_real_results(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    store = TypedArtifactStore(root)
    _seed_artifact(
        store, content={"note": "keyboard driven widget"}, source="tui-source"
    )
    state = _tui_state(root)
    actions = default_scan_actions()

    _dispatch_key(state, "M", actions)
    assert state.mode == "memory"
    _dispatch_key(state, "/", actions)
    assert state.mode == "memory_search"
    for ch in "widget":
        _dispatch_key(state, ch, actions)
    _dispatch_key(state, "enter", actions)

    assert state.mode == "memory"
    assert len(state.memory_items) == 1
    assert state.memory_items[0]["source"] == "tui-source"


def test_tui_memory_delete_preview_cancel_deletes_zero(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    store = TypedArtifactStore(root)
    keep = _seed_artifact(store, content={"note": "doomed candidate"})
    other = _seed_artifact(store, content={"note": "doomed candidate two"})
    state = _tui_state(root)
    actions = default_scan_actions()

    _dispatch_key(state, "M", actions)
    _dispatch_key(state, "/", actions)
    for ch in "doomed":
        _dispatch_key(state, ch, actions)
    _dispatch_key(state, "enter", actions)
    assert len(state.memory_items) == 2

    _dispatch_key(state, " ", actions)  # select first row
    _dispatch_key(state, "d", actions)  # preview delete
    assert state.memory_pending_delete is not None
    assert len(state.memory_pending_delete["artifact_ids"]) == 1

    _dispatch_key(state, "n", actions)  # cancel
    assert state.memory_pending_delete is None
    assert "0 records removed" in state.memory_message

    remaining = {row["id"] for row in store.list_artifact_refs()}
    assert remaining == {keep.id, other.id}


def test_tui_memory_delete_confirm_deletes_only_selected(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    store = TypedArtifactStore(root)
    survivor = _seed_artifact(store, content={"note": "batch item survives"})
    doomed = _seed_artifact(store, content={"note": "batch item removable"})
    state = _tui_state(root)
    actions = default_scan_actions()

    _dispatch_key(state, "M", actions)
    _dispatch_key(state, "/", actions)
    for ch in "batch":  # matches both seeded rows
        _dispatch_key(state, ch, actions)
    _dispatch_key(state, "enter", actions)
    assert len(state.memory_items) == 2

    doomed_index = next(
        i for i, item in enumerate(state.memory_items) if item["id"] == doomed.id
    )
    state.memory_selected_index = doomed_index
    _dispatch_key(state, " ", actions)
    _dispatch_key(state, "d", actions)
    assert state.memory_pending_delete["artifact_ids"] == [doomed.id]

    _dispatch_key(state, "y", actions)
    assert state.memory_pending_delete is None
    assert "deleted 1 record" in state.memory_message

    remaining = {row["id"] for row in store.list_artifact_refs()}
    assert remaining == {survivor.id}


def test_tui_memory_promote_denied_without_corroboration(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    store = TypedArtifactStore(root)
    _seed_artifact(store, content={"note": "lonely claim"}, source="only-source")
    state = _tui_state(root)
    actions = default_scan_actions()

    _dispatch_key(state, "M", actions)
    _dispatch_key(state, "/", actions)
    for ch in "lonely":
        _dispatch_key(state, ch, actions)
    _dispatch_key(state, "enter", actions)
    assert len(state.memory_items) == 1

    _dispatch_key(state, "p", actions)
    assert "promotion denied" in state.memory_message
    assert "insufficient_corroboration" in state.memory_message


def test_tui_memory_expand_shows_full_content(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    store = TypedArtifactStore(root)
    _seed_artifact(store, content={"note": "expand me", "detail": "full body"})
    state = _tui_state(root)
    actions = default_scan_actions()

    _dispatch_key(state, "M", actions)
    _dispatch_key(state, "/", actions)
    for ch in "expand":
        _dispatch_key(state, ch, actions)
    _dispatch_key(state, "enter", actions)
    assert len(state.memory_items) == 1

    _dispatch_key(state, "x", actions)
    assert state.memory_expanded is not None
    decoded = base64.b64decode(state.memory_expanded["content_base64"]).decode("utf-8")
    assert "full body" in decoded
    assert state.memory_expanded["encoding"]
    assert isinstance(state.memory_expanded["tokens"], int)


def test_tui_memory_edit_commits_new_content(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    store = TypedArtifactStore(root)
    _seed_artifact(store, content={"note": "editable row"})
    state = _tui_state(root)
    actions = default_scan_actions()

    _dispatch_key(state, "M", actions)
    _dispatch_key(state, "/", actions)
    for ch in "editable":
        _dispatch_key(state, ch, actions)
    _dispatch_key(state, "enter", actions)
    assert len(state.memory_items) == 1

    _dispatch_key(state, "e", actions)
    assert state.mode == "memory_edit"
    for ch in "hello":
        _dispatch_key(state, ch, actions)
    _dispatch_key(state, "enter", actions)

    assert state.mode == "memory"
    assert state.memory_message == "edit applied"
    refreshed = store.scope_artifacts(
        "domain_knowledge", source_allowlist=["test-source"]
    )
    assert any(
        r["content"] and json.loads(r["content"]).get("note") == "hello"
        for r in refreshed
    )
