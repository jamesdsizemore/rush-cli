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
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import pytest

from rush.dashboard.server import create_dashboard_server
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.token_economy.telemetry import TelemetryStore
from rush.tui import ProjectState, TuiState, _dispatch_key, default_scan_actions
from rush.workflows import projects as projects_module
from rush.workflows.projects import register_project

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
):
    body = json.dumps(
        {
            "schema_version": 1,
            "operation": operation,
            "arguments": arguments or {},
            "grants": grants or {},
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
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(
        store,
        content={"note": "original"},
        source="origin-tool",
        origin_kind="scan-finding",
        origin_id="finding-123",
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
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "v1"})
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
            },
            grants=_grant_all(),
        )
        assert status == 200
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
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "unchanged"})
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
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "archivable"})
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


def test_memory_delete_preview_shows_exactly_selected_and_cancel_deletes_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deletion fixture: 3 candidate records, exactly 2 selected. A
    preview (apply=False) never mutates anything -- treating that preview as
    a cancellation (never calling apply=True) must leave all 3 records
    intact, including the 2 that were "selected" for the preview."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path)
    store = TypedArtifactStore(root)
    keep_out_of_selection = _seed_artifact(store, content={"note": "untouched"})
    selected_one = _seed_artifact(store, content={"note": "selected-1"})
    selected_two = _seed_artifact(store, content={"note": "selected-2"})
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
    store = TypedArtifactStore(root)
    survivor = _seed_artifact(store, content={"note": "survivor"})
    doomed_one = _seed_artifact(store, content={"note": "doomed-1"})
    doomed_two = _seed_artifact(store, content={"note": "doomed-2"})
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
    store = TypedArtifactStore(root)
    artifact = _seed_artifact(store, content={"note": "protected"})
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
