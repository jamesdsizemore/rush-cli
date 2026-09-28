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

import base64
import hashlib
import io
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
from rush.permissions import ExecutionPermissions
from rush.tui import ProjectState, TuiState, _dispatch_key, default_scan_actions
from rush.workflows import project_run as project_run_module
from rush.workflows import projects as projects_module
from rush.workflows.project_run import ScanCandidate, ScanPlan
from rush.workflows.projects import (
    expand_artifact_reference,
    export_project_data,
    project_git_commit_diff,
    project_git_history,
    project_snapshot,
    register_project,
)

pytestmark = pytest.mark.usefixtures("hermetic_engine_path")

# --- shared HTTP helpers (mirrors tests/test_dashboard_memory_tokens.py) -----


def _serve(server) -> threading.Thread:
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
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


def _commit_files(root: Path, commits: list[tuple[str, str, str]]) -> str:
    """`_commit_file` for each `(rel_path, content, message)` in order, as
    one `git fast-import` stream instead of three git spawns per commit:
    same author/committer, subjects and files, each commit on top of the
    current branch. The work tree and index are then synced to the result.
    Returns the final HEAD."""
    branch = _run_git(root, "symbolic-ref", "HEAD")
    parent = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
        cwd=root,
        env=_GIT_ENV,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    identity = f"{_GIT_ENV['GIT_AUTHOR_NAME']} <{_GIT_ENV['GIT_AUTHOR_EMAIL']}> now"
    stream = io.BytesIO()
    for rel_path, content, message in commits:
        data = content.encode("utf-8")
        subject = message.encode("utf-8")
        stream.write(f"commit {branch}\n".encode())
        stream.write(f"author {identity}\ncommitter {identity}\n".encode())
        stream.write(f"data {len(subject)}\n".encode() + subject + b"\n")
        if parent:
            stream.write(f"from {parent}\n".encode())
            parent = ""
        stream.write(f"M 100644 inline {rel_path}\n".encode())
        stream.write(f"data {len(data)}\n".encode() + data + b"\n")
    subprocess.run(
        ["git", "fast-import", "--quiet", "--date-format=now"],
        cwd=root,
        env=_GIT_ENV,
        input=stream.getvalue(),
        check=True,
        capture_output=True,
    )
    _run_git(root, "reset", "--quiet", "--hard", "HEAD")
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
    project_id: str,
    run_id: str,
    scheduled: list[dict[str, Any]],
    attempt_id: str | None = None,
    git_link: dict[str, Any] | None = None,
) -> None:
    attempt_id = attempt_id or f"{run_id}-attempt-1"
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "git_link": git_link or {},
        "plan_id": f"plan-{run_id}",
        "project_id": project_id,
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
    candidate_id: str,
    category: str,
    *,
    artifacts: list[str] | None = None,
    artifact_snapshots: dict[str, dict[str, Any]] | None = None,
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
        # M12: sibling of "child", matching `CandidateResult.to_dict()`'s
        # real shape -- keyed by the exact declared path string.
        "artifact_snapshots": artifact_snapshots or {},
    }


def _write_artifact_snapshot(
    root: Path,
    run_id: str,
    attempt_id: str,
    candidate_id: str,
    index: int,
    data: bytes,
    *,
    media_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """M12: writes a fixture immutable snapshot file at the same relative
    layout `project_run.py::_capture_artifact_snapshots` uses, and returns
    the matching `artifact_snapshots` entry -- so a test can assert the
    download route reads captured bytes back, without driving a real scan."""
    relative = f".rush/runs/{run_id}/attempts/{attempt_id}/artifacts/{candidate_id}/{index}.bin"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "immutable_path": relative,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "media_type": media_type,
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
            "next_cursor": None,
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


def test_git_scan_link_requires_matching_source_revision_not_just_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07.2b: linking a commit to scan output requires the persisted
    `git_link` to match that exact commit (HEAD, clean tree, per-path
    digests against the commit's tree) -- a merely intersecting recorded
    path is never sufficient on its own (P69-03.2's Git-link predicate,
    reused verbatim)."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "connect-repo")
    head = _commit_file(root, "src/app.py", "print('changed')\n", "touch src/app.py")
    real_digest = hashlib.sha256((root / "src/app.py").read_bytes()).hexdigest()

    # Matches the commit exactly: linked.
    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-connect",
        scheduled=[
            _scheduled_item("matching-tool", "quality", artifacts=["src/app.py"]),
        ],
        git_link={
            "repository": True,
            "head": head,
            "dirty": False,
            "path_digests": {"src/app.py": real_digest},
        },
    )
    # Recorded path intersects the diff, but its own source revision does
    # not match this commit -- must NOT be linked despite the path overlap.
    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-stale",
        scheduled=[
            _scheduled_item("stale-tool", "quality", artifacts=["src/app.py"]),
        ],
        git_link={
            "repository": True,
            "head": "0" * 40,
            "dirty": False,
            "path_digests": {"src/app.py": real_digest},
        },
    )

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        status, _headers, body = _snapshot(
            base_url, project_id, cookie, "git", commit=head
        )
        assert status == 200
        linked = body["data"]["diff"]["linked_scan_outputs"]
        assert linked == ["run:run-connect:run-connect-attempt-1:matching-tool"]
    finally:
        server.shutdown()
        server.server_close()


# --- M13: repository-state evidence never becomes an impossible Git path ---


def _run_real_scan(tmp_path: Path, project_id: str) -> dict[str, Any]:
    """A real `execute_scan` attempt against the registered project's own
    root -- the "real scan route" M13's Fix bullet 4 requires. `git-guard`
    (a real repository-state engine needing only the `git` binary, always
    present here) runs as one of the catalog's own real candidates; no
    fixture/fake tool stands in for it."""
    from rush.workflows.project_run import execute_scan, plan_scan

    plan = plan_scan(project_id, data_root=tmp_path / "rush-data")
    run = execute_scan(
        plan,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
        data_root=tmp_path / "rush-data",
    )
    return json.loads(Path(run.manifest_path).read_text())


def test_no_synthetic_evidence_key_reaches_git_show_commit_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M13 bullets 1-3: `git-guard`'s own synthetic `candidate_id:kind`
    provenance digest is recorded under this candidate's
    `repository_state_evidence`, never under the attempt's
    `git_link.path_digests` -- `projects.git_link_matches_commit` treats
    every `path_digests` key as a literal `git show commit:path` argument,
    so a synthetic key there would be an impossible Git path."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "m13-synthetic-repo")
    _commit_file(root, ".gitignore", ".rush/\n", "add .gitignore")
    _commit_file(root, "src/app.py", "print('hi')\n", "add src/app.py")

    manifest = _run_real_scan(tmp_path, project_id)

    git_guard_entry = next(
        item for item in manifest["scheduled"] if item["candidate_id"] == "git-guard"
    )
    assert git_guard_entry["outcome"] == "executed"
    assert git_guard_entry["consumed_path_digests"] == {}
    repository_state_evidence = git_guard_entry["repository_state_evidence"]
    assert repository_state_evidence
    synthetic_key = next(iter(repository_state_evidence))
    assert synthetic_key == "git-guard:git-status-stdout"

    path_digests = manifest["git_link"]["path_digests"]
    assert synthetic_key not in path_digests
    assert set(path_digests) == {".gitignore", "src/app.py"}


def test_clean_matching_commit_links_correctly_through_gitguard_diffcover_undercover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M13 bullet 4: `git-guard`'s own repository-state evidence (present
    alongside DiffCover/Undercover, which share the identical
    `repository_state_evidence` path per Fix bullet 1, when those binaries
    are installed) never blocks a clean, unmodified commit from linking
    correctly through `projects.git_link_matches_commit`."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "m13-clean-match-repo")
    _commit_file(root, ".gitignore", ".rush/\n", "add .gitignore")
    head = _commit_file(root, "src/app.py", "print('hi')\n", "add src/app.py")

    manifest = _run_real_scan(tmp_path, project_id)

    git_guard_entry = next(
        item for item in manifest["scheduled"] if item["candidate_id"] == "git-guard"
    )
    assert git_guard_entry["outcome"] == "executed"
    assert manifest["git_link"]["dirty"] is False
    assert projects_module.git_link_matches_commit(root, manifest["git_link"], head)


def test_changed_repository_state_evidence_prevents_a_false_git_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M13 bullet 4: the repository state changes (an untracked file
    appears) between two attempts against the same commit -- `git-guard`'s
    own real `repository_state_evidence` digest changes, the persisted
    `git_link.dirty` flag flips to `True`, and
    `projects.git_link_matches_commit` correctly refuses to link this
    attempt's output to the commit despite an identical HEAD, rather than
    falsely matching on HEAD alone."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "m13-changed-evidence-repo")
    _commit_file(root, ".gitignore", ".rush/\n", "add .gitignore")
    head = _commit_file(root, "src/app.py", "print('hi')\n", "add src/app.py")

    clean_manifest = _run_real_scan(tmp_path, project_id)
    assert projects_module.git_link_matches_commit(
        root, clean_manifest["git_link"], head
    )

    (root / "untracked.py").write_text("z = 1\n", encoding="utf-8")
    dirty_manifest = _run_real_scan(tmp_path, project_id)

    clean_evidence = next(
        item["repository_state_evidence"]
        for item in clean_manifest["scheduled"]
        if item["candidate_id"] == "git-guard"
    )
    dirty_evidence = next(
        item["repository_state_evidence"]
        for item in dirty_manifest["scheduled"]
        if item["candidate_id"] == "git-guard"
    )
    assert clean_evidence != dirty_evidence
    assert dirty_manifest["git_link"]["head"] == head
    assert dirty_manifest["git_link"]["dirty"] is True
    assert not projects_module.git_link_matches_commit(
        root, dirty_manifest["git_link"], head
    )


def test_git_history_uses_50_commit_cursor_not_offset_pagination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07.2b/Phase66 §3.1/§3.6: Git history pages by an opaque,
    revision-bound cursor with a 50-commit default page size -- not the old
    default 20-entry `skip`/`limit` offset pagination."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "cursor-repo")
    expected_subjects = [f"commit number {i}" for i in range(25)]
    _commit_files(
        root,
        [
            (f"f{i}.txt", f"{i}\n", subject)
            for i, subject in enumerate(expected_subjects)
        ],
    )

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        # Default page size is 50, not the old 20 -- all 25 real commits fit
        # on one page with no limit specified.
        status, _headers, page1 = _snapshot(base_url, project_id, cookie, "git")
        assert status == 200
        assert len(page1["data"]["history"]) == 25
        assert page1["data"]["next_cursor"] is None
        assert "next_skip" not in page1["data"]

        # Cursor-based pagination: the returned cursor is opaque, not a bare
        # offset integer, and advances correctly across pages.
        status, _headers, small_page1 = _snapshot(
            base_url, project_id, cookie, "git", limit="10"
        )
        assert len(small_page1["data"]["history"]) == 10
        cursor = small_page1["data"]["next_cursor"]
        assert cursor is not None
        assert cursor != "10"

        status, _headers, small_page2 = _snapshot(
            base_url, project_id, cookie, "git", limit="10", cursor=cursor
        )
        assert len(small_page2["data"]["history"]) == 10

        seen = [c["subject"] for c in small_page1["data"]["history"]] + [
            c["subject"] for c in small_page2["data"]["history"]
        ]
        assert seen == list(reversed(expected_subjects))[:20]

        # A cursor issued against a stale revision is rejected -- a new
        # commit landing between page requests invalidates it.
        _commit_file(root, "late.txt", "late\n", "a later commit")
        status, _headers, body = _snapshot(
            base_url, project_id, cookie, "git", limit="10", cursor=cursor
        )
        assert status == 409
        assert body["error"]["code"] == "cursor_rejected"
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
        project_id=project_id,
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
        assert "run:run-1:run-1-attempt-1:tool-a" in seen_refs
        assert "run:run-1:run-1-attempt-1:tool-b" in seen_refs
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
        root,
        project_id=project_id,
        run_id="run-1",
        scheduled=[_scheduled_item("tool-a", "quality")],
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
        project_id=project_id,
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
            expand_ref="run:run-profiler:run-profiler-attempt-1:profiler-tool",
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


def test_artifact_content_route_supports_paged_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07.2b/M12: `GET /api/projects/{id}/artifacts/{ref}` supports real
    paged content download for a scan-output artifact's captured immutable
    snapshot (never the live/staged current-project tree), base64-encoded
    for lossless reassembly (Phase 66 §3.6: artifact reads paginate,
    1MiB/page)."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "download-repo")
    content = ("line\n" * 500).encode("utf-8")
    snapshot = _write_artifact_snapshot(
        root,
        "run-dl",
        "run-dl-attempt-1",
        "dl-tool",
        0,
        content,
        media_type="text/plain",
    )
    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-dl",
        scheduled=[
            _scheduled_item(
                "dl-tool",
                "quality",
                artifacts=["report.txt"],
                artifact_snapshots={"report.txt": snapshot},
            )
        ],
    )
    artifact_ref = "run:run-dl:run-dl-attempt-1:dl-tool"

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        collected = b""
        offset = 0
        pages = 0
        last_page: dict[str, Any] = {}
        while True:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/artifacts/{artifact_ref}"
                f"?limit=1000&offset={offset}",
                headers={"Cookie": cookie},
            )
            assert resp.status == 200
            page = json.loads(resp.read())["data"]["content"]
            last_page = page
            assert page["path"] == "report.txt"
            assert page["offset"] == offset
            chunk = base64.b64decode(page["content_base64"])
            assert len(chunk) <= 1000
            collected += chunk
            pages += 1
            assert pages <= 10  # bounded loop guard, never an infinite paginate
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        assert pages > 1  # actually paginated, not one giant blob
        assert collected == content
        assert last_page["sha256"] == snapshot["sha256"]
        assert last_page["media_type"] == "text/plain"
    finally:
        server.shutdown()
        server.server_close()


# --- M12: historical byte storage overwritten at finalization -------------


def test_two_candidates_in_one_attempt_writing_the_same_logical_filename_retain_different_original_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M12 regression: every scheduled candidate in one attempt shares the
    same private staging tree, so a second candidate declaring the exact
    same absolute artifact path as an earlier one physically overwrites it
    on disk before the attempt finishes. `_capture_artifact_snapshots`
    (`project_run.py`) must copy each candidate's own bytes out immediately
    after it runs -- before that overwrite can happen -- so both retain
    their own original content."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "collision-repo", init_git=False)
    shared_path = tmp_path / "shared-out.bin"

    def _fake_execute_candidate(candidate, **_kwargs):
        payload = f"{candidate.candidate_id}-bytes".encode()
        shared_path.write_bytes(payload)
        return "executed", {
            "tool": candidate.candidate_id,
            "engine": None,
            "status": "ok",
            "duration_ms": 0,
            "summary": "ok",
            "findings": [],
            "artifacts": [str(shared_path)],
        }

    monkeypatch.setattr(
        project_run_module, "_execute_candidate", _fake_execute_candidate
    )

    plan = ScanPlan(
        plan_id="fixture-plan",
        project_id=project_id,
        root=str(root),
        candidates=(
            ScanCandidate("cand-a", "tool", "quality", "applicable", "static"),
            ScanCandidate("cand-b", "tool", "quality", "applicable", "static"),
        ),
        exclude=(),
        targets={},
        severity="warn",
        concurrency=2,
        timeout_seconds=300,
    )
    run = project_run_module.execute_scan(
        plan, run_id="run-collision", attempt_id="attempt-1"
    )

    manifest = json.loads(Path(run.manifest_path).read_text(encoding="utf-8"))
    scheduled_by_id = {item["candidate_id"]: item for item in manifest["scheduled"]}
    snap_a = scheduled_by_id["cand-a"]["artifact_snapshots"][str(shared_path)]
    snap_b = scheduled_by_id["cand-b"]["artifact_snapshots"][str(shared_path)]

    assert snap_a["sha256"] != snap_b["sha256"]
    assert snap_a["immutable_path"] != snap_b["immutable_path"]
    assert (root / snap_a["immutable_path"]).read_bytes() == b"cand-a-bytes"
    assert (root / snap_b["immutable_path"]).read_bytes() == b"cand-b-bytes"
    # The shared physical path really was overwritten -- proving the
    # captured snapshot, not the live path, is what preserved cand-a's bytes.
    assert shared_path.read_bytes() == b"cand-b-bytes"


def test_two_attempts_and_a_resumed_completed_candidate_retain_their_own_artifact_copies_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M12 regression: a candidate retained across a resumed attempt is
    reloaded straight from its persisted evidence file (`_load_completed_
    candidates`, a real "after restart" reload, never carried in memory).
    It must keep pointing at its own attempt-1 bytes even after a fresh
    candidate in attempt 2 declares the exact same physical artifact path."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "resume-collision-repo", init_git=False)
    shared_path = tmp_path / "shared-out.bin"

    def _fake_execute_candidate_1(candidate, **_kwargs):
        payload = f"{candidate.candidate_id}-attempt1-bytes".encode()
        shared_path.write_bytes(payload)
        return "executed", {
            "tool": candidate.candidate_id,
            "engine": None,
            "status": "ok",
            "duration_ms": 0,
            "summary": "ok",
            "findings": [],
            "artifacts": [str(shared_path)],
        }

    monkeypatch.setattr(
        project_run_module, "_execute_candidate", _fake_execute_candidate_1
    )

    candidate_a = ScanCandidate("cand-a", "tool", "quality", "applicable", "static")
    plan_1 = ScanPlan(
        plan_id="fixture-plan",
        project_id=project_id,
        root=str(root),
        candidates=(candidate_a,),
        exclude=(),
        targets={},
        severity="warn",
        concurrency=2,
        timeout_seconds=300,
    )
    run_1 = project_run_module.execute_scan(
        plan_1, run_id="run-resume", attempt_id="attempt-1"
    )
    attempt_1_manifest = json.loads(
        Path(run_1.manifest_path).read_text(encoding="utf-8")
    )
    attempt_1_snap = attempt_1_manifest["scheduled"][0]["artifact_snapshots"][
        str(shared_path)
    ]

    # A real restart: reload the completed candidate straight off disk, the
    # same way `resume_scan_run` does after a process death.
    attempt_1_dir = root / ".rush" / "runs" / "run-resume" / "attempts" / "attempt-1"
    already_completed = project_run_module._load_completed_candidates(attempt_1_dir)
    assert (
        already_completed["cand-a"].artifact_snapshots[str(shared_path)]
        == attempt_1_snap
    )

    def _fake_execute_candidate_2(candidate, **_kwargs):
        payload = f"{candidate.candidate_id}-attempt2-bytes".encode()
        shared_path.write_bytes(payload)
        return "executed", {
            "tool": candidate.candidate_id,
            "engine": None,
            "status": "ok",
            "duration_ms": 0,
            "summary": "ok",
            "findings": [],
            "artifacts": [str(shared_path)],
        }

    monkeypatch.setattr(
        project_run_module, "_execute_candidate", _fake_execute_candidate_2
    )
    candidate_b = ScanCandidate("cand-b", "tool", "quality", "applicable", "static")
    plan_2 = ScanPlan(
        plan_id="fixture-plan",
        project_id=project_id,
        root=str(root),
        candidates=(candidate_a, candidate_b),
        exclude=(),
        targets={},
        severity="warn",
        concurrency=2,
        timeout_seconds=300,
    )
    run_2 = project_run_module._execute_attempt_locked(
        plan_2,
        root=root,
        run_id="run-resume",
        attempt_id="attempt-2",
        permissions=ExecutionPermissions(),
        config=None,
        already_completed=already_completed,
    )
    attempt_2_manifest = json.loads(
        Path(run_2.manifest_path).read_text(encoding="utf-8")
    )
    scheduled_by_id = {
        item["candidate_id"]: item for item in attempt_2_manifest["scheduled"]
    }

    carried = scheduled_by_id["cand-a"]["artifact_snapshots"][str(shared_path)]
    assert carried == attempt_1_snap
    assert (root / carried["immutable_path"]).read_bytes() == b"cand-a-attempt1-bytes"

    fresh = scheduled_by_id["cand-b"]["artifact_snapshots"][str(shared_path)]
    assert (root / fresh["immutable_path"]).read_bytes() == b"cand-b-attempt2-bytes"
    assert fresh["sha256"] != carried["sha256"]


def test_download_more_than_two_pages_containing_split_utf8_nul_and_0xff_bytes_reassembles_exactly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M12 regression: the prior text-decode page reader
    (`chunk.decode("utf-8", errors="replace")`) corrupted a multi-byte UTF-8
    character split across a page boundary, a NUL byte, and 0xFF -- the
    base64 wire contract must reassemble all three losslessly across more
    than two pages."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "binary-download-repo")
    # 'A', the 3-byte UTF-8 encoding of '€' ("euro sign"), 'B', a NUL
    # byte, and 0xFF.
    content = bytes.fromhex("41e282ac4200ff")
    snapshot = _write_artifact_snapshot(
        root, "run-bin", "run-bin-attempt-1", "bin-tool", 0, content
    )
    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-bin",
        scheduled=[
            _scheduled_item(
                "bin-tool",
                "quality",
                artifacts=["out.bin"],
                artifact_snapshots={"out.bin": snapshot},
            )
        ],
    )
    artifact_ref = "run:run-bin:run-bin-attempt-1:bin-tool"

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        collected = b""
        offset = 0
        pages = 0
        while True:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/artifacts/{artifact_ref}"
                f"?limit=2&offset={offset}",
                headers={"Cookie": cookie},
            )
            assert resp.status == 200
            page = json.loads(resp.read())["data"]["content"]
            chunk = base64.b64decode(page["content_base64"])
            assert len(chunk) <= 2
            collected += chunk
            pages += 1
            assert pages <= 10  # bounded loop guard, never an infinite paginate
            if page["next_offset"] is None:
                break
            offset = page["next_offset"]
        assert pages > 2  # more than two pages, per this test's own name
        assert collected == content
        assert hashlib.sha256(collected).hexdigest() == snapshot["sha256"]
    finally:
        server.shutdown()
        server.server_close()


def test_a_reference_and_offset_for_attempt_a_never_selects_attempt_bs_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M12 regression: two attempts (each the sole/latest attempt of its own
    run -- `_iter_run_manifests` only ever surfaces one attempt per run_id,
    a separate, pre-existing constraint this test does not exercise), each
    with a candidate declaring the identical logical artifact filename,
    must never let attempt A's reference resolve attempt B's captured
    bytes (or vice versa) -- even at the same byte offset."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "two-attempt-download-repo")

    content_a = b"attempt-A-bytes"
    content_b = b"attempt-B-different-bytes"
    snapshot_a = _write_artifact_snapshot(
        root, "run-a", "attempt-a", "same-tool", 0, content_a
    )
    snapshot_b = _write_artifact_snapshot(
        root, "run-b", "attempt-b", "same-tool", 0, content_b
    )
    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-a",
        attempt_id="attempt-a",
        scheduled=[
            _scheduled_item(
                "same-tool",
                "quality",
                artifacts=["out.txt"],
                artifact_snapshots={"out.txt": snapshot_a},
            )
        ],
    )
    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-b",
        attempt_id="attempt-b",
        scheduled=[
            _scheduled_item(
                "same-tool",
                "quality",
                artifacts=["out.txt"],
                artifact_snapshots={"out.txt": snapshot_b},
            )
        ],
    )
    ref_a = "run:run-a:attempt-a:same-tool"
    ref_b = "run:run-b:attempt-b:same-tool"

    server, base_url, cookie, _csrf = _start_dashboard(project_id, root)
    try:
        resp_a = _get(
            f"{base_url}/api/projects/{project_id}/artifacts/{ref_a}?offset=0&limit=100",
            headers={"Cookie": cookie},
        )
        assert resp_a.status == 200
        page_a = json.loads(resp_a.read())["data"]["content"]
        assert base64.b64decode(page_a["content_base64"]) == content_a

        resp_b = _get(
            f"{base_url}/api/projects/{project_id}/artifacts/{ref_b}?offset=0&limit=100",
            headers={"Cookie": cookie},
        )
        assert resp_b.status == 200
        page_b = json.loads(resp_b.read())["data"]["content"]
        assert base64.b64decode(page_b["content_base64"]) == content_b

        assert page_a["content_base64"] != page_b["content_base64"]
    finally:
        server.shutdown()
        server.server_close()


def test_two_attempts_of_same_run_produce_distinct_artifact_references(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07.2c: `list_project_artifacts()` built `artifact_ref` as
    `run:{run_id}:{candidate_id}` with no `attempt_id` -- two attempts of the
    same `run_id` produced identical references, so a stale reference minted
    against one attempt silently resolved whichever attempt was currently
    highest-generation instead of the one it was minted for."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "two-attempts-repo")

    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-1",
        attempt_id="run-1-attempt-a",
        scheduled=[_scheduled_item("tool-a", "quality")],
    )
    payload_a = projects_module.list_project_artifacts(project_id)
    ref_a = next(
        item["artifact_ref"]
        for item in payload_a["scan_outputs"]
        if item["tool_id"] == "tool-a"
    )
    assert ref_a == "run:run-1:run-1-attempt-a:tool-a"

    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-1",
        attempt_id="run-1-attempt-b",
        scheduled=[_scheduled_item("tool-a", "quality")],
    )
    payload_b = projects_module.list_project_artifacts(project_id)
    ref_b = next(
        item["artifact_ref"]
        for item in payload_b["scan_outputs"]
        if item["tool_id"] == "tool-a"
    )
    assert ref_b == "run:run-1:run-1-attempt-b:tool-a"
    assert ref_a != ref_b


def test_list_project_artifacts_surfaces_persisted_git_link_provenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """P69-07.2b: the manifest's persisted `git_link` (HEAD/dirty/per-path
    digests, reusing P69-03.2's Git-link metadata) is passed through verbatim
    on every scan-output artifact reference."""
    _isolate_data_roots(tmp_path, monkeypatch)
    project_id, root = _register(tmp_path, "git-link-artifacts-repo")
    git_link = {
        "repository": True,
        "head": "abc123",
        "dirty": False,
        "path_digests": {"app.py": "deadbeef"},
    }
    _write_manifest(
        root,
        project_id=project_id,
        run_id="run-1",
        scheduled=[_scheduled_item("tool-a", "quality")],
        git_link=git_link,
    )

    payload = projects_module.list_project_artifacts(project_id)
    item = next(item for item in payload["scan_outputs"] if item["tool_id"] == "tool-a")
    assert item["git_link"] == git_link


def test_build_manifest_persists_git_link_provenance_reusing_source_identity(
    tmp_path: Path,
) -> None:
    """P69-07.2b: `_build_manifest`'s `git_link` field reuses the exact
    `_git_link()` result already computed for `source_identity` -- one shared
    provenance contract, never a second, independently computed Git read that
    could drift from `source_identity`'s own snapshot."""
    root = tmp_path
    _init_repo(root)
    _commit_file(root, "app.py", "print('x')\n", "init")

    digests = {"app.py": "deadbeef"}
    identity = project_run_module._source_identity(digests, root)
    plan = ScanPlan(
        plan_id="plan-x",
        project_id="proj-x",
        root=str(root),
        candidates=(),
        exclude=(),
        targets={},
        severity="warn",
        concurrency=1,
        timeout_seconds=300,
    )
    manifest = project_run_module._build_manifest(
        run_id="run-x",
        attempt_id="attempt-x",
        plan=plan,
        run_state="completed",
        scheduled=[],
        aggregate={},
        source_identity=identity,
        digests=digests,
    )

    assert manifest["git_link"] == {
        "repository": True,
        "head": identity["git"]["head"],
        "dirty": False,
        "path_digests": digests,
    }


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

    # U01 fix: Tab now cycles panes, not projects. Switching the active
    # project goes through the F2 project-selector overlay (Down highlights
    # the next project, Enter confirms the switch).
    _dispatch_key(state, "f2", actions)
    _dispatch_key(state, "down", actions)
    _dispatch_key(state, "enter", actions)
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
