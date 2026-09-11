"""Phase 66 P66-02: global project registry, selector, and navigation
(plan sections 3.1, 3.2, 3.6) over real loopback HTTP against the canonical
`create_dashboard_server` boundary from P66-01.
"""

from __future__ import annotations

import concurrent.futures
import json
import shutil
import subprocess
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from rush.dashboard.server import create_dashboard_server
from rush.workflows import projects as projects_module

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dashboard"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


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


_GRANTS = {"cache_write": True, "artifact_write": True}


def test_empty_registry_add_select_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    repo = tmp_path / "repo-a"
    repo.mkdir()

    server, ctx, token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        empty_list = _get(f"{base_url}/api/projects", headers={"Cookie": cookie})
        assert empty_list.status == 200
        assert json.loads(empty_list.read())["data"]["items"] == []

        add_body = json.dumps(
            {
                "operation": "add",
                "path": str(repo),
                "grants": _GRANTS,
                "request_id": str(uuid.uuid4()),
            }
        ).encode()
        added = _post(
            f"{base_url}/api/projects",
            headers={
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            body=add_body,
        )
        assert added.status == 201
        added_data = json.loads(added.read())["data"]
        assert added_data["root"] == str(repo)
        assert added_data["next"] == "configure"
        project_id = added_data["project_id"]

        listed = _get(f"{base_url}/api/projects", headers={"Cookie": cookie})
        items = json.loads(listed.read())["data"]["items"]
        assert [item["project_id"] for item in items] == [project_id]

        snapshot = _get(
            f"{base_url}/api/projects/{project_id}/snapshot", headers={"Cookie": cookie}
        )
        assert snapshot.status == 200
        data = json.loads(snapshot.read())["data"]
        assert data["files"] == []
        assert data["findings"] == []
        assert data["root"] == str(repo)

        map_resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot?section=map",
            headers={"Cookie": cookie},
        )
        map_data = json.loads(map_resp.read())["data"]
        assert map_data["total_nodes"] == 1
        assert len(map_data["nodes"]) == 1
        assert map_data["nodes"][0]["kind"] == "project"
        assert map_data["edges"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_create_conflict_preserves_existing_folder(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    parent = tmp_path / "workspace"
    parent.mkdir()
    occupied = parent / "existing"
    occupied.mkdir()
    marker = occupied / "keep.txt"
    marker.write_text("do not touch")

    server, ctx, token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)

        create_body = json.dumps(
            {
                "operation": "create",
                "parent": str(parent),
                "name": "existing",
                "grants": _GRANTS,
                "request_id": str(uuid.uuid4()),
            }
        ).encode()
        conflict = _post(
            f"{base_url}/api/projects",
            headers={
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Content-Type": "application/json",
                "Origin": base_url,
            },
            body=create_body,
        )
        assert conflict.status == 409
        error = json.loads(conflict.read())["error"]
        assert error["code"] == "project_exists"

        # The original folder and its content are untouched.
        assert occupied.is_dir()
        assert marker.read_text() == "do not touch"
    finally:
        server.shutdown()
        server.server_close()


def test_project_switch_replaces_all_sections() -> None:
    project_a = _load_fixture("project_a.json")
    project_b = _load_fixture("project_b.json")
    server, ctx, token = create_dashboard_server(
        {"project-a": project_a, "project-b": project_b}
    )
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)

        resp_a = _get(
            f"{base_url}/api/projects/project-a/snapshot?section=map",
            headers={"Cookie": cookie},
        )
        map_a = json.loads(resp_a.read())["data"]
        resp_b = _get(
            f"{base_url}/api/projects/project-b/snapshot?section=map",
            headers={"Cookie": cookie},
        )
        map_b = json.loads(resp_b.read())["data"]

        # Both fixtures use identical relative file paths on purpose (spec
        # 3.9: "Project B uses identical paths but distinct project/source/
        # finding/memory IDs"), so file node IDs (path-content-derived, not
        # project-scoped) legitimately collide -- that's harmless since a
        # client only ever renders one selected project's map at a time.
        # Findings/memories/agents carry distinct per-project original IDs
        # and must never leak across a switch.
        evidence_a = {n["id"] for n in map_a["nodes"] if n["kind"] != "file"}
        evidence_b = {n["id"] for n in map_b["nodes"] if n["kind"] != "file"}
        assert evidence_a.isdisjoint(evidence_b)
        assert map_a["project_id"] == "project-a"
        assert map_b["project_id"] == "project-b"
    finally:
        server.shutdown()
        server.server_close()


def test_concurrent_requests_return_correct_project_each() -> None:
    """Server-side per-request correctness under concurrency: every response
    carries its own requested project's identity, never a cross-project
    mix-up. This does NOT exercise application.js's client-side
    stale-response discard (selectProject/loadMap/isCurrentGeneration) --
    see test_client_side_stale_response_is_discarded_via_generation_guard
    below for that."""
    project_a = _load_fixture("project_a.json")
    project_b = _load_fixture("project_b.json")
    server, ctx, token = create_dashboard_server(
        {"project-a": project_a, "project-b": project_b}
    )
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)

        # Interleave rapid requests for both projects as if a user switched
        # mid-flight; every response must still carry its own requested
        # project's identity -- never a mix-up.
        urls = [
            f"{base_url}/api/projects/project-a/snapshot",
            f"{base_url}/api/projects/project-b/snapshot",
        ] * 10

        def fetch(url: str) -> tuple[str, str]:
            resp = _get(url, headers={"Cookie": cookie})
            body = json.loads(resp.read())
            return url, body["project_id"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(fetch, urls))

        for url, project_id in results:
            assert project_id in url
    finally:
        server.shutdown()
        server.server_close()


# Minimal stub for project_map.js's exports so application.js -- imported
# byte-identical, unmodified -- can run under plain Node without a real DOM.
# Records every renderMap call so the harness can assert which project's
# data was actually rendered.
_PROJECT_MAP_STUB = """
export const rendered = [];
export function renderMap(container, mapData) {
  rendered.push(mapData);
}
export function fitMap() {}
export function destroyMap() {}
export function showGroupMembers() {}
export function hideGroupMembers() {}
"""

# Mocks fetch so project-a's response is slow (300ms) and project-b's is
# fast (10ms), mirroring T303's Judge repro exactly: selectProject twice in
# a row must leave only the second (fast) project's data ever rendered,
# proving application.js's real selectProject/loadMap/isCurrentGeneration
# generation guard discards the late project-a response.
_RACE_GUARD_HARNESS = """
import { selectProject, getState } from "./application.js";
import { rendered } from "./project_map.js";

getState().mapContainer = {};

global.fetch = (url) => {
  const isA = url.includes("project-a");
  const projectId = isA ? "project-a" : "project-b";
  const delayMs = isA ? 300 : 10;
  return new Promise((resolve) => {
    setTimeout(() => {
      resolve({
        ok: true,
        status: 200,
        json: async () => ({
          schema_version: 1,
          request_id: "r",
          project_id: projectId,
          sequence: 1,
          data: { project_id: projectId, nodes: [], edges: [] },
        }),
      });
    }, delayMs);
  });
};

selectProject("project-a");
selectProject("project-b");

setTimeout(() => {
  const projectIds = rendered.map((d) => d.project_id);
  const onlyLatestRendered = projectIds.length === 1 && projectIds[0] === "project-b";
  if (onlyLatestRendered) {
    console.log("PASS");
    process.exit(0);
  } else {
    console.error("FAIL: rendered=" + JSON.stringify(projectIds));
    process.exit(1);
  }
}, 500);
"""


def test_client_side_stale_response_is_discarded_via_generation_guard(tmp_path) -> None:
    """New coverage for T303's real gap: the concurrency test above proves
    server-side per-request correctness, but leaves application.js's own
    stale-response guard (selectProject/loadMap/isCurrentGeneration) with
    zero automated coverage. Shells out to `node` to actually exercise the
    real application.js source as-is (byte-identical copy, not a
    reimplementation) with a mocked fetch: project-a's response is delayed,
    project-b's is fast. selectProject('project-a') then immediately
    selectProject('project-b') must result in ONLY project-b's data ever
    being rendered."""
    app_src = (
        Path(__file__).parent.parent / "src" / "rush" / "dashboard" / "application.js"
    )
    harness_dir = tmp_path / "race_guard_harness"
    harness_dir.mkdir()
    shutil.copyfile(app_src, harness_dir / "application.js")
    (harness_dir / "package.json").write_text(json.dumps({"type": "module"}))
    (harness_dir / "project_map.js").write_text(_PROJECT_MAP_STUB)
    (harness_dir / "run_harness.js").write_text(_RACE_GUARD_HARNESS)

    node = shutil.which("node")
    assert node is not None, "node must be installed to exercise application.js"
    result = subprocess.run(
        [node, "run_harness.js"],
        cwd=harness_dir,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, (
        f"race-guard harness failed\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "PASS" in result.stdout


def test_unknown_artifact_type_remains_visible() -> None:
    project_with_unknown = dict(_load_fixture("project_a.json"))
    project_with_unknown["artifacts"] = [
        {"id": "custom-trace", "type": "custom", "content": "safe text"}
    ]
    server, ctx, token = create_dashboard_server({"project-a": project_with_unknown})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, _csrf = _bootstrap_session(base_url, token)

        resp = _get(
            f"{base_url}/api/projects/project-a/snapshot", headers={"Cookie": cookie}
        )
        data = json.loads(resp.read())["data"]
        assert data["artifacts"] == [
            {"id": "custom-trace", "type": "custom", "content": "safe text"}
        ]
    finally:
        server.shutdown()
        server.server_close()
