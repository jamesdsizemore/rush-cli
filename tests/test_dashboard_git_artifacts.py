"""Tests for Phase 66 P66-06: Git history and every generated artifact (F38).

Drives the real dashboard HTTP snapshot/action boundary (`server.py`) against
a real registered project with a real on-disk Git repository (`git init`/
`git commit`/`git mv` via `subprocess`, never a fake/mocked history), plus
`rush.tui`'s real key-dispatch functions directly (mirrors
`tests/test_dashboard_memory_tokens.py`'s own pattern) -- never a fabricated
response.

This packet renders untrusted commit-message/scanner-output text in a
browser, so the hostile-HTML tests below are treated with security-review
rigor, not as a formatting nicety: real XSS payloads are committed as actual
Git commit messages, then the real HTTP response bytes are inspected to
confirm the payload only ever travels as an inert JSON string field, and
that the two owned browser rendering modules (`application.js`,
`project_map.js` -- not part of this packet's allowed files) contain zero
`innerHTML` sinks that could turn that JSON into executable markup.

Every Git read here (`log`/`status`/`show`) is argv-based and read-only;
`test_git_read_operations_never_mutate_branch_or_index` and its TUI sibling
assert the repo's HEAD and working-tree status are byte-identical before and
after every code path in this file is exercised.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

import pytest

from rush.dashboard.server import create_dashboard_server
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.tui import ProjectState, TuiState, _dispatch_key, default_scan_actions
from rush.workflows import projects as projects_module
from rush.workflows.projects import (
    expand_artifact_reference,
    export_project_data,
    project_git_commit_diff,
    project_git_history,
    project_snapshot,
    register_project,
)

# --- shared HTTP helpers (mirrors tests/test_dashboard_memory_tokens.py) -----


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
    return resp.status, resp.headers, json.loads(resp.read())


def _snapshot(base_url: str, project_id: str, cookie: str, section: str, **query: str):
    from urllib.parse import urlencode

    qs = urlencode({"section": section, **query})
    resp = _get(
        f"{base_url}/api/projects/{project_id}/snapshot?{qs}",
        headers={"Cookie": cookie},
    )
    return resp.status, resp.headers, json.loads(resp.read())


def _isolate_data_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "rush-data"
    monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)


def _register(
    tmp_path: Path, name: str = "project", *, init_git: bool = True
) -> tuple[str, Path]:
    root = tmp_path / name
    if init_git:
        _init_repo(root)
    else:
        root.mkdir(parents=True, exist_ok=True)
        (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
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


# --- real, on-disk Git repo fixtures ------------------------------------

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _run_git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=_GIT_ENV,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _run_git(root, "init", "--quiet")


def _commit_file(root: Path, rel_path: str, content: str, message: str) -> str:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _run_git(root, "add", rel_path)
    _run_git(root, "commit", "--quiet", "-m", message)
    return _run_git(root, "rev-parse", "HEAD")


def _rename_file(root: Path, old: str, new: str, message: str) -> str:
    _run_git(root, "mv", old, new)
    _run_git(root, "commit", "--quiet", "-m", message)
    return _run_git(root, "rev-parse", "HEAD")


def _repo_state(root: Path) -> tuple[str, str]:
    """(HEAD, porcelain status) snapshot for before/after no-mutation checks."""
    head = _run_git(root, "rev-parse", "HEAD")
    status = _run_git(root, "status", "--porcelain")
    return head, status


# --- run-manifest / handoff / memory fixtures (mirrors test_project_evidence.py) --


def _write_manifest(
    root: Path,
    *,
    run_id: str,
    scheduled: list[dict[str, Any]],
) -> None:
    attempt_id = f"{run_id}-attempt-1"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "plan_id": f"plan-{run_id}",
        "project_id": "unused-by-reader",
        "root": str(root),
        "run_state": "completed",
        "severity": "warn",
        "concurrency": 2,
        "timeout_seconds": 300,
        "created_at": "2026-01-01T00:00:00+00:00",
        "candidates": scheduled,
        "scheduled": scheduled,
        "aggregate": {
            "tool": "scan",
            "engine": None,
            "status": "ok",
            "findings": [],
            "metadata": {"coverage": {"empty": False}},
        },
        "totals": {
            "candidate_count": len(scheduled),
            "scheduled_count": len(scheduled),
            "executed_count": len(scheduled),
            "finding_count": 0,
        },
    }
    manifest_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def _scheduled_item(
    candidate_id: str, category: str, *, artifacts: list[str] | None = None
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "kind": "tool",
        "category": category,
        "disposition": "applicable",
        "reason": "comprehensive_static_analysis",
        "outcome": "executed",
        "child": {
            "tool": candidate_id,
            "engine": None,
            "status": "ok",
            "findings": [],
            "summary": f"{candidate_id} ok",
            "metrics": {},
            "artifacts": artifacts or [],
            "raw": None,
        },
    }


def _write_handoff(root: Path, handoff_id: str) -> None:
    handoffs_dir = root / ".rush" / "handoffs"
    handoffs_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "handoff_id": handoff_id,
        "run_id": "run-handoff",
        "state": "sent",
        "artifact_id": "artifact-handoff",
        "artifact_version": 1,
        "packet": {"tokens": 42},
    }
    (handoffs_dir / f"{handoff_id}.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _seed_memory(store: TypedArtifactStore, note: str) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=str(uuid.uuid4()),
            family="memory",
            subject="domain_knowledge",
            trust_tier="EXTERNAL_WRITE",
            content={"note": note},
            source="test-source",
            created_at=time.time(),
            symbol_ref=None,
            content_hash=None,
            origin_kind=None,
            origin_id=None,
        )
    )


_XSS_PAYLOADS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    '"><svg onload=alert(1)>',
]


# --- P66-06.1 RED / P66-06.2-3 GREEN/CONNECT: HTTP `section=git` ------------


def test_git_section_reports_correct_repo_identity_for_two_separate_repos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_a, root_a = _register(tmp_path, "repo-a")
    head_a = _commit_file(root_a, "a.py", "print('a')\n", "commit in repo A")
    project_b, root_b = _register(tmp_path, "repo-b")
    head_b = _commit_file(root_b, "b.py", "print('b')\n", "commit in repo B")

    server, base_url, cookie, _csrf = _start_dashboard(project_a, root_a)
    try:
        status, headers, body_a = _snapshot(base_url, project_a, cookie, "git")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("application/json")
        assert body_a["data"]["has_git"] is True
        assert body_a["data"]["head"] == head_a
        subjects_a = {c["subject"] for c in body_a["data"]["history"]}
        assert subjects_a == {"commit in repo A"}
    finally:
        server.shutdown()
        server.server_close()

    server, base_url, cookie, _csrf = _start_dashboard(project_b, root_b)
    try:
        status, _headers, body_b = _snapshot(base_url, project_b, cookie, "git")
        assert status == 200
        assert body_b["data"]["head"] == head_b
        subjects_b = {c["subject"] for c in body_b["data"]["history"]}
        assert subjects_b == {"commit in repo B"}
        assert body_b["data"]["head"] != head_a
    finally:
        server.shutdown()
        server.server_close()


def test_git_section_renders_hostile_commit_messages_as_inert_json_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "hostile-repo")
    for idx, payload in enumerate(_XSS_PAYLOADS):
        _commit_file(root, f"file{idx}.txt", f"content {idx}\n", payload)

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, headers, body = _snapshot(base_url, project_id, cookie, "git")
        assert status == 200
        assert headers.get("Content-Type", "").startswith("application/json")
        subjects = {c["subject"] for c in body["data"]["history"]}
        assert subjects == set(_XSS_PAYLOADS)

        # The two owned browser rendering modules must never build HTML by
        # string-interpolating this JSON data -- `innerHTML` is the sink
        # that would turn an inert JSON string into executable markup.
        js_resp = _get(f"{base_url}/assets/application.js", headers={"Cookie": cookie})
        assert b"innerHTML" not in js_resp.read()
        map_resp = _get(f"{base_url}/assets/project_map.js", headers={"Cookie": cookie})
        assert b"innerHTML" not in map_resp.read()
    finally:
        server.shutdown()
        server.server_close()


def test_git_section_reports_dirty_index_and_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "dirty-repo")
    _commit_file(root, "tracked.py", "a = 1\n", "initial commit")
    (root / "tracked.py").write_text("a = 2\n", encoding="utf-8")
    (root / "staged_new.py").write_text("b = 1\n", encoding="utf-8")
    _run_git(root, "add", "staged_new.py")
    (root / "untracked.py").write_text("c = 1\n", encoding="utf-8")

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _snapshot(base_url, project_id, cookie, "git")
        assert status == 200
        assert body["data"]["dirty"] is True
        by_path = {e["path"]: e["status"] for e in body["data"]["dirty_files"]}
        assert by_path["tracked.py"] == "M"
        assert by_path["staged_new.py"] == "A"
        assert by_path["untracked.py"] == "??"
    finally:
        server.shutdown()
        server.server_close()


def test_git_section_non_git_project_returns_has_git_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "no-git-project", init_git=False)

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _snapshot(base_url, project_id, cookie, "git")
        assert status == 200
        assert body["data"] == {
            "has_git": False,
            "head": None,
            "dirty": None,
            "dirty_files": [],
            "history": [],
            "next_skip": None,
        }
    finally:
        server.shutdown()
        server.server_close()


def test_git_commit_diff_detects_renamed_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "rename-repo")
    _commit_file(root, "old_name.py", "value = 1\n", "add old_name.py")
    rename_head = _rename_file(root, "old_name.py", "new_name.py", "rename the file")

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _snapshot(
            base_url, project_id, cookie, "git", commit=rename_head
        )
        assert status == 200
        diff = body["data"]["diff"]
        assert diff["has_git"] is True
        assert set(diff["changed_paths"]) == {"old_name.py", "new_name.py"}
    finally:
        server.shutdown()
        server.server_close()


def test_git_commit_diff_is_bounded_for_a_large_diff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "large-diff-repo")
    big_content = "\n".join(f"line {i}" for i in range(700)) + "\n"
    head = _commit_file(root, "big.txt", big_content, "add a large file")

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _snapshot(
            base_url, project_id, cookie, "git", commit=head
        )
        assert status == 200
        diff = body["data"]["diff"]
        assert diff["truncated"] is True
        assert len(diff["lines"]) == projects_module._GIT_DIFF_MAX_LINES
    finally:
        server.shutdown()
        server.server_close()


def test_git_commit_diff_links_scan_output_only_on_exact_path_identity_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "connect-repo")
    head = _commit_file(root, "src/app.py", "print('changed')\n", "touch src/app.py")
    _write_manifest(
        root,
        run_id="run-connect",
        scheduled=[
            _scheduled_item("matching-tool", "quality", artifacts=["src/app.py"]),
            _scheduled_item("unrelated-tool", "quality", artifacts=["other.py"]),
        ],
    )

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _snapshot(
            base_url, project_id, cookie, "git", commit=head
        )
        assert status == 200
        linked = body["data"]["diff"]["linked_scan_outputs"]
        assert linked == ["run:run-connect:matching-tool"]
    finally:
        server.shutdown()
        server.server_close()


def test_git_section_history_pagination_is_bounded_and_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "paged-repo")
    expected_subjects = []
    for i in range(5):
        subject = f"commit number {i}"
        _commit_file(root, f"f{i}.txt", f"{i}\n", subject)
        expected_subjects.append(subject)

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, page1 = _snapshot(
            base_url, project_id, cookie, "git", limit="2"
        )
        assert status == 200
        assert len(page1["data"]["history"]) == 2
        assert page1["data"]["next_skip"] == 2

        status, _headers, page2 = _snapshot(
            base_url, project_id, cookie, "git", limit="2", skip="2"
        )
        assert len(page2["data"]["history"]) == 2
        assert page2["data"]["next_skip"] == 4

        status, _headers, page3 = _snapshot(
            base_url, project_id, cookie, "git", limit="2", skip="4"
        )
        assert len(page3["data"]["history"]) == 1
        assert page3["data"]["next_skip"] is None

        seen = [
            c["subject"]
            for page in (page1, page2, page3)
            for c in page["data"]["history"]
        ]
        assert seen == list(reversed(expected_subjects))
    finally:
        server.shutdown()
        server.server_close()


# --- P66-06.2-3 GREEN/CONNECT: HTTP `section=artifacts` ---------------------


def test_artifacts_section_lists_every_manifest_entry_with_bounded_pagination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "artifacts-repo")
    _write_manifest(
        root,
        run_id="run-1",
        scheduled=[
            _scheduled_item("tool-a", "quality"),
            _scheduled_item("tool-b", "security"),
        ],
    )
    _write_handoff(root, "handoff-1")
    store = TypedArtifactStore(root)
    for i in range(4):
        _seed_memory(store, f"note {i}")

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        seen_refs: set[str] = set()
        cursor = None
        pages = 0
        while True:
            kwargs = {"limit": "3"}
            if cursor:
                kwargs["cursor"] = cursor
            status, _headers, body = _snapshot(
                base_url, project_id, cookie, "artifacts", **kwargs
            )
            assert status == 200
            assert len(body["data"]["items"]) <= 3
            seen_refs.update(item["artifact_ref"] for item in body["data"]["items"])
            cursor = body["data"]["next_cursor"]
            pages += 1
            assert pages <= 10  # bounded loop guard, never an infinite paginate
            if cursor is None:
                break

        assert len(seen_refs) == 7  # 2 scan_outputs + 1 handoff + 4 memory
        assert "run:run-1:tool-a" in seen_refs
        assert "run:run-1:tool-b" in seen_refs
        assert "handoff:handoff-1" in seen_refs
    finally:
        server.shutdown()
        server.server_close()


def test_artifacts_section_missing_artifact_expand_returns_found_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "missing-artifact-repo")
    _write_manifest(
        root, run_id="run-1", scheduled=[_scheduled_item("tool-a", "quality")]
    )

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _snapshot(
            base_url,
            project_id,
            cookie,
            "artifacts",
            expand_ref="run:does-not-exist:tool-z",
        )
        assert status == 200
        assert body["data"]["expand"] == {
            "found": False,
            "kind": "unknown",
            "entry": None,
            "raw_excerpt": None,
        }
    finally:
        server.shutdown()
        server.server_close()


def test_artifacts_section_unknown_output_type_gets_generic_safe_redacted_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "unknown-type-repo")
    hostile_line = "<script>alert('scanner output')</script>"
    (root / "profile.out").write_text(hostile_line + "\n", encoding="utf-8")
    _write_manifest(
        root,
        run_id="run-profiler",
        scheduled=[
            _scheduled_item(
                "profiler-tool", "profiler_export", artifacts=["profile.out"]
            )
        ],
    )

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, headers, body = _snapshot(
            base_url,
            project_id,
            cookie,
            "artifacts",
            expand_ref="run:run-profiler:profiler-tool",
        )
        assert status == 200
        assert headers.get("Content-Type", "").startswith("application/json")
        expand = body["data"]["expand"]
        assert expand["found"] is True
        assert expand["entry"]["category"] == "profiler_export"
        assert expand["raw_excerpt"]["lines"] == [hostile_line]
        assert "profiler_export" in body["data"]["categories"]
    finally:
        server.shutdown()
        server.server_close()


# --- P66-06.3 CONNECT: per-project data export ------------------------------


def test_data_export_requires_download_grant_and_serializes_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "export-repo")
    _commit_file(root, "app.py", "print('x')\n", "initial commit")

    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _action(
            base_url, project_id, cookie, csrf, operation="data_export", grants={}
        )
        assert status == 403
        assert body["error"]["code"] == "grant_denied"

        status, _headers, body = _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="data_export",
            grants={"download": True},
        )
        assert status == 200
        exported = body["data"]
        assert exported["schema_version"] == 1
        assert exported["project_id"] == project_id
        assert exported["snapshot"]["git"]["has_git"] is True
    finally:
        server.shutdown()
        server.server_close()


# --- P66-06.4 VERIFY: no branch/index mutation from any read here -----------


def test_git_read_operations_never_mutate_branch_or_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "no-mutation-repo")
    _commit_file(root, "a.py", "a = 1\n", "first commit")
    second_head = _commit_file(root, "b.py", "b = 1\n", "second commit")
    (root / "a.py").write_text("a = 2\n", encoding="utf-8")  # leave the tree dirty

    before = _repo_state(root)
    server, base_url, cookie, csrf = _start_dashboard(project_id, root)
    try:
        _snapshot(base_url, project_id, cookie, "git", limit="1")
        _snapshot(base_url, project_id, cookie, "git", commit=second_head)
        _snapshot(base_url, project_id, cookie, "artifacts")
        _action(
            base_url,
            project_id,
            cookie,
            csrf,
            operation="data_export",
            grants={"download": True},
        )
    finally:
        server.shutdown()
        server.server_close()
    after = _repo_state(root)
    assert before == after


# --- P66-06.1-4 workflow-level (registry-free) unit coverage ----------------


def test_expand_artifact_reference_missing_ref_returns_found_false(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wf-repo"
    root.mkdir()
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    result = expand_artifact_reference(
        record.project_id, "memory:does-not-exist", data_root=data_root
    )
    assert result == {"found": False, "kind": "unknown", "entry": None}


def test_export_project_data_matches_project_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "wf-repo"
    root.mkdir()
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    exported = export_project_data(record.project_id, data_root=data_root)
    snapshot = project_snapshot(record.project_id, data_root=data_root)
    assert exported["snapshot"] == snapshot
    assert exported["project_id"] == snapshot["project"]["project_id"]


def test_project_git_commit_diff_rejects_non_hash_ref(tmp_path: Path) -> None:
    root = tmp_path / "wf-repo"
    _init_repo(root)
    _commit_file(root, "a.py", "a = 1\n", "init")
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    diff = project_git_commit_diff(record.project_id, "; rm -rf /", data_root=data_root)
    assert diff["error"] == "invalid_ref"
    assert diff["lines"] == []


def test_project_git_history_reports_has_git_false_without_error(
    tmp_path: Path,
) -> None:
    root = tmp_path / "wf-repo"
    root.mkdir()
    data_root = tmp_path / "rush-data"
    record = register_project(root, data_root=data_root)
    history = project_git_history(record.project_id, data_root=data_root)
    assert history == {"has_git": False, "commits": [], "next_skip": None}


# --- P66-06.4 VERIFY: TUI Git & artifacts view -------------------------------


def _tui_state(root: Path) -> TuiState:
    project = ProjectState(name=root.name, root=root, results=[])
    return TuiState(projects=[project])


def test_tui_git_view_loads_real_history_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "tui-repo")
    head = _commit_file(root, "a.py", "a = 1\n", "tui commit")
    assert project_id  # registered so `default_scan_actions()`'s real
    # `resolve_project`-backed `git_snapshot` can resolve `root`.

    state = _tui_state(root)
    actions = default_scan_actions()
    _dispatch_key(state, "G", actions)

    assert state.mode == "git"
    assert state.git_data["git"]["has_git"] is True
    assert state.git_data["git"]["head"] == head
    subjects = {c["subject"] for c in state.git_data["git"]["history"]}
    assert subjects == {"tui commit"}

    _dispatch_key(state, "escape", actions)
    assert state.mode == "list"


def test_tui_git_view_renders_hostile_and_markup_content_as_literal_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rich.console import Console

    from rush.tui import _render_git_panel

    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "tui-hostile-repo")
    xss_message = "<script>alert(1)</script>"
    markup_message = "[bold red]INJECTED[/bold red]"
    _commit_file(root, "x.py", "x = 1\n", xss_message)
    _commit_file(root, "y.py", "y = 1\n", markup_message)
    assert project_id

    state = _tui_state(root)
    actions = default_scan_actions()
    _dispatch_key(state, "G", actions)
    assert state.git_message == ""

    panel = _render_git_panel(state)
    console = Console(record=True, width=200, force_terminal=False)
    console.print(panel)
    rendered = console.export_text()

    # A hostile commit subject must appear as literal text -- if Rich had
    # ever interpreted `[bold red]...[/bold red]` as real markup, the
    # literal bracketed tag text would be gone from the plain-text export
    # and only the unstyled word "INJECTED" would remain.
    assert xss_message in rendered
    assert markup_message in rendered


def test_tui_git_view_two_project_isolation_no_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_a, root_a = _register(tmp_path, "tui-repo-a")
    _commit_file(root_a, "a.py", "a = 1\n", "commit in A")
    project_b, root_b = _register(tmp_path, "tui-repo-b")
    _commit_file(root_b, "b.py", "b = 1\n", "commit in B")
    assert project_a and project_b

    project_state_a = ProjectState(name=root_a.name, root=root_a, results=[])
    project_state_b = ProjectState(name=root_b.name, root=root_b, results=[])
    state = TuiState(projects=[project_state_a, project_state_b])
    actions = default_scan_actions()

    _dispatch_key(state, "G", actions)
    subjects_a = {c["subject"] for c in state.git_data["git"]["history"]}
    assert subjects_a == {"commit in A"}

    _dispatch_key(state, "tab", actions)
    assert state.git_data is None  # reset -- never leaks project A's data

    _dispatch_key(state, "G", actions)
    subjects_b = {c["subject"] for c in state.git_data["git"]["history"]}
    assert subjects_b == {"commit in B"}


def test_tui_git_read_never_mutates_branch_or_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "tui-no-mutation-repo")
    _commit_file(root, "a.py", "a = 1\n", "first commit")
    (root / "a.py").write_text("a = 2\n", encoding="utf-8")
    assert project_id

    before = _repo_state(root)
    state = _tui_state(root)
    actions = default_scan_actions()
    _dispatch_key(state, "G", actions)
    after = _repo_state(root)
    assert before == after
