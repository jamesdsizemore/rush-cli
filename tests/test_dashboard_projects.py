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

import pytest

from rush.dashboard.server import create_dashboard_server, stop_all_dashboard_contexts
from rush.workflows import projects as projects_module

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dashboard"


@pytest.fixture(autouse=True)
def _stop_leaked_dashboard_recovery_threads():
    """T027: every `create_dashboard_server(...)` call in this file leaves
    its `DashboardContext`'s recovery/outcome-retry background threads
    running -- `server.shutdown()` below only stops the HTTP server, never
    these. Left alone, they keep firing at their own interval for the rest
    of this pytest process's life, accumulating across the full suite."""
    yield
    stop_all_dashboard_contexts()


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


def test_overview_and_setup_sections_return_dedicated_content_not_full_snapshot(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    repo = tmp_path / "repo-overview-setup"
    repo.mkdir()

    server, ctx, token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
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
        project_id = json.loads(added.read())["data"]["project_id"]

        overview_resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot?section=overview",
            headers={"Cookie": cookie},
        )
        assert overview_resp.status == 200
        overview = json.loads(overview_resp.read())["data"]
        assert overview["project_id"] == project_id
        assert overview["finding_count"] == 0
        assert "findings" not in overview
        assert "agents" not in overview

        setup_resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot?section=setup",
            headers={"Cookie": cookie},
        )
        assert setup_resp.status == 200
        setup = json.loads(setup_resp.read())["data"]
        assert setup["project_id"] == project_id
        assert "readiness" in setup
        assert "findings" not in setup
    finally:
        server.shutdown()
        server.server_close()


def test_add_project_rejects_non_boolean_grants_and_git_init(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(
        projects_module, "default_data_root", lambda: tmp_path / "rush-data"
    )
    repo = tmp_path / "repo-strict-bool"
    repo.mkdir()

    server, ctx, token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Content-Type": "application/json",
            "Origin": base_url,
        }

        truthy_string_grants = _post(
            f"{base_url}/api/projects",
            headers=headers,
            body=json.dumps(
                {
                    "operation": "add",
                    "path": str(repo),
                    "grants": {"cache_write": "true", "artifact_write": True},
                    "request_id": str(uuid.uuid4()),
                }
            ).encode(),
        )
        assert truthy_string_grants.status == 400

        non_bool_git_init = _post(
            f"{base_url}/api/projects",
            headers=headers,
            body=json.dumps(
                {
                    "operation": "create",
                    "parent": str(tmp_path),
                    "name": "repo-strict-bool-create",
                    "git_init": 1,
                    "grants": _GRANTS,
                    "request_id": str(uuid.uuid4()),
                }
            ).encode(),
        )
        assert non_bool_git_init.status == 400

        real_bools = _post(
            f"{base_url}/api/projects",
            headers=headers,
            body=json.dumps(
                {
                    "operation": "add",
                    "path": str(repo),
                    "grants": _GRANTS,
                    "request_id": str(uuid.uuid4()),
                }
            ).encode(),
        )
        assert real_bools.status == 201
    finally:
        server.shutdown()
        server.server_close()


# --- P69-04.1 RED: browser application wiring (Phase 66 Sec 0 row 4) --------
#
# Structural assertions only (real HTTP responses, real served source) --
# these prove markup/wiring exists, never that a click handler actually
# fires in a real browser; the live browser session is a separate,
# named verification step (P69-04.4) alongside this pytest run.

_NAV_SECTIONS = (
    "map",
    "overview",
    "scans",
    "memory",
    "tokens",
    "git",
    "artifacts",
    "setup",
)


def test_topbar_navigation_controls_exist_and_are_wired() -> None:
    server, ctx, _token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        shell = _get(f"{base_url}/")
        assert shell.status == 200
        shell_body = shell.read()
        assert b'data-role="topbar"' in shell_body
        assert b'data-role="nav"' in shell_body
        assert b'data-role="inspector"' in shell_body
        assert b'data-role="project-select"' in shell_body
        for section in _NAV_SECTIONS:
            assert f'data-section="{section}"'.encode() in shell_body

        app_js = _get(f"{base_url}/assets/application.js")
        assert app_js.status == 200
        app_body = app_js.read()
        assert b"function wireTopbar" in app_body
        assert b"function wireNav" in app_body
        assert b"function switchSection" in app_body
        assert b"SECTION_RENDERERS" in app_body
        assert b"dispatchAction" in app_body
        assert b"addOrCreateProject" in app_body
    finally:
        server.shutdown()
        server.server_close()


def test_select_add_create_choose_later_all_reachable_from_shell() -> None:
    server, ctx, _token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        shell = _get(f"{base_url}/")
        shell_body = shell.read()
        assert b'data-role="project-select"' in shell_body
        assert b'data-role="project-add"' in shell_body
        assert b'data-role="project-create"' in shell_body
        assert b'data-role="project-choose-later"' in shell_body
        assert b'data-role="project-add-form"' in shell_body
        assert b'data-role="project-create-form"' in shell_body

        app_js = _get(f"{base_url}/assets/application.js")
        app_body = app_js.read()
        assert b"function wireTopbar" in app_body
        assert b'"project-add"' in app_body
        assert b'"project-create"' in app_body
        assert b'"project-choose-later"' in app_body
        assert b"addOrCreateProject({" in app_body
    finally:
        server.shutdown()
        server.server_close()


def test_group_member_row_opens_its_evidence() -> None:
    server, ctx, _token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        map_js = _get(f"{base_url}/assets/project_map.js")
        assert map_js.status == 200
        body = map_js.read()
        # Real actionable element (a <button>), not a plain <li> with no
        # action -- and wired to the same selection mechanism a direct map
        # node click already uses (opens its evidence via selectNodeInternal).
        assert b'"member-row"' in body
        assert b'createElement("button")' in body
        assert b"selectNodeInternal(member.id)" in body
        assert b'addEventListener("click"' in body
        assert b'addEventListener("keydown"' in body
    finally:
        server.shutdown()
        server.server_close()


def test_every_workflow_from_configure_through_artifact_export_has_a_visible_control() -> (
    None
):
    server, ctx, _token = create_dashboard_server({})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        app_js = _get(f"{base_url}/assets/application.js")
        assert app_js.status == 200
        body = app_js.read()
        for operation in (
            "configure",
            "provision_plan",
            "provision_apply",
            "scan_start",
            "scan_cancel",
            "scan_resume",
            "rescan",
            "handoff_preview",
            "handoff_send",
            "artifact_export",
        ):
            assert f'"{operation}"'.encode() in body, f"missing control for {operation}"
        # Every visible control's own <form> carries data-operation so a
        # live browser session can find it; the memory forms this packet
        # owns building (write/promote/edit/archive/delete) and the
        # agent-connect control (a distinct, non-project-scoped endpoint).
        assert b"data-operation" in body
        assert b"function buildActionForm" in body
        assert b'"memory_propose"' in body
        assert b'"memory_promote"' in body
        assert b'"memory_edit"' in body
        assert b'"memory_archive"' in body
        assert b'"memory_delete"' in body
        assert b"function connectAgent" in body
        assert b"/api/agents/actions" in body
        assert b"function buildAgentConnectControl" in body
    finally:
        server.shutdown()
        server.server_close()


# Shared minimal DOM shim (global.document.createElement + a `[attr="value"]`/
# `[attr]` query-selector engine) so the real, unmodified application.js --
# which this packet extends to build topbar/nav/section DOM via
# `document.createElement` -- can run under plain Node without jsdom. Builds
# a tree mirroring static_assets.py's real shell markup so `startApplication`
# finds every element it queries for.
_MINI_DOM_PRELUDE = """
function makeElement(tag, attrs) {
  attrs = attrs || {};
  const el = {
    tagName: tag.toUpperCase(),
    _attrs: {},
    _children: [],
    _listeners: {},
    dataset: {},
    hidden: false,
    checked: false,
    value: "",
    textContent: "",
    setAttribute(name, value) {
      this._attrs[name] = String(value);
    },
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this._attrs, name)
        ? this._attrs[name]
        : null;
    },
    appendChild(child) {
      this._children.push(child);
      return child;
    },
    addEventListener(type, handler) {
      (this._listeners[type] = this._listeners[type] || []).push(handler);
    },
    dispatchEvent(evt) {
      for (const handler of this._listeners[evt.type] || []) handler(evt);
    },
    click() {
      this.dispatchEvent({ type: "click", preventDefault() {}, target: this });
    },
    querySelector(sel) {
      return findFirst(this, sel);
    },
    querySelectorAll(sel) {
      return findAll(this, sel);
    },
  };
  for (const name of Object.keys(attrs)) el.setAttribute(name, attrs[name]);
  return el;
}

function matchesSelector(el, sel) {
  if (typeof el.getAttribute !== "function") return false; // a text node, never a match
  const m = sel.match(/^\\[([a-zA-Z0-9-]+)(?:="([^"]*)")?\\]$/);
  if (!m) return false;
  const attr = m[1];
  const value = m[2];
  const actual = el.getAttribute(attr);
  if (actual === null) return false;
  return value === undefined || actual === value;
}

function findAll(root, sel) {
  const out = [];
  for (const child of root._children || []) {
    if (matchesSelector(child, sel)) out.push(child);
    out.push.apply(out, findAll(child, sel));
  }
  return out;
}

function findFirst(root, sel) {
  const all = findAll(root, sel);
  return all.length ? all[0] : null;
}

global.document = {
  createElement: function (tag) {
    return makeElement(tag);
  },
  createTextNode: function (text) {
    return { nodeType: 3, textContent: text };
  },
};

const projectSelect = makeElement("select", { "data-role": "project-select" });
const addBtn = makeElement("button", { "data-role": "project-add" });
const addForm = makeElement("form", { "data-role": "project-add-form" });
addForm.appendChild(makeElement("input", { name: "path" }));
const createBtn = makeElement("button", { "data-role": "project-create" });
const createForm = makeElement("form", { "data-role": "project-create-form" });
createForm.appendChild(makeElement("input", { name: "parent" }));
createForm.appendChild(makeElement("input", { name: "name" }));
createForm.appendChild(makeElement("input", { name: "git_init" }));
const chooseLaterBtn = makeElement("button", { "data-role": "project-choose-later" });
const topbar = makeElement("div", { "data-role": "topbar" });
[projectSelect, addBtn, addForm, createBtn, createForm, chooseLaterBtn].forEach(function (c) {
  topbar.appendChild(c);
});

const nav = makeElement("div", { "data-role": "nav" });
["map", "overview", "scans", "memory", "tokens", "git", "artifacts", "setup"].forEach(
  function (section) {
    nav.appendChild(makeElement("button", { "data-section": section }));
  }
);

const mapEl = makeElement("div", { "data-role": "map" });
const inspector = makeElement("div", { "data-role": "inspector" });
const errorBanner = makeElement("div", { "data-role": "error-banner" });

const rootEl = makeElement("div", {});
[topbar, nav, mapEl, inspector, errorBanner].forEach(function (c) {
  rootEl.appendChild(c);
});
"""


def _run_restore_project_id_harness(
    tmp_path: Path, scenario_js: str, *, project_map_stub: str = _PROJECT_MAP_STUB
) -> tuple[int, str, str]:
    app_src = (
        Path(__file__).parent.parent / "src" / "rush" / "dashboard" / "application.js"
    )
    harness_dir = tmp_path / "restore_project_id_harness"
    harness_dir.mkdir()
    shutil.copyfile(app_src, harness_dir / "application.js")
    (harness_dir / "package.json").write_text(json.dumps({"type": "module"}))
    (harness_dir / "project_map.js").write_text(project_map_stub)
    (harness_dir / "run_harness.js").write_text(_MINI_DOM_PRELUDE + scenario_js)

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
    return result.returncode, result.stdout, result.stderr


_RESTORE_LANDS_ON_PROJECT_SCENARIO = """
import { startApplication, getState } from "./application.js";

global.fetch = (url) => {
  const u = String(url);
  let ok = true;
  let data;
  let extra = {};
  if (u === "/api/session") {
    extra = { csrf_token: "csrf-token" };
  } else if (u === "/api/theme") {
    data = { theme: {}, motion: {} };
  } else if (u === "/api/projects") {
    data = {
      items: [
        { project_id: "project-a", root: "/a" },
        { project_id: "project-b", root: "/b" },
      ],
    };
  } else if (u.indexOf("/api/projects/project-b/snapshot") === 0) {
    data = { project_id: "project-b", nodes: [], edges: [] };
  } else {
    ok = false;
  }
  return Promise.resolve({
    ok,
    status: ok ? 200 : 404,
    json: async () => Object.assign({ schema_version: 1, request_id: "r", data }, extra),
  });
};

startApplication(rootEl, { restoreProjectId: "project-b", mapContainer: {} }).then(() => {
  const selected = getState().selectedProjectId;
  if (selected === "project-b") {
    console.log("PASS");
    process.exit(0);
  } else {
    console.error("FAIL: selectedProjectId=" + selected);
    process.exit(1);
  }
});
"""


def test_restore_project_id_option_lands_on_that_project_not_the_chooser(
    tmp_path: Path,
) -> None:
    """Phase 68's P68-04 browser-handoff step depends on this: a supplied
    `restoreProjectId` lands the shell directly on that project, never the
    chooser."""
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _RESTORE_LANDS_ON_PROJECT_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_RESTORE_BEYOND_FIRST_PAGE_SCENARIO = """
import { startApplication, getState } from "./application.js";

global.fetch = (url) => {
  const u = String(url);
  let ok = true;
  let data;
  let extra = {};
  if (u === "/api/session") {
    extra = { csrf_token: "csrf-token" };
  } else if (u === "/api/theme") {
    data = { theme: {}, motion: {} };
  } else if (u === "/api/projects") {
    // project-b is NOT on this (simulated) first page of 50 -- the fix must
    // resolve restoreProjectId via a direct existence check, never
    // single-page `items` membership.
    data = { items: [{ project_id: "project-a", root: "/a" }] };
  } else if (u.indexOf("/api/projects/project-b/snapshot") === 0) {
    data = { project_id: "project-b", nodes: [], edges: [] };
  } else {
    ok = false;
  }
  return Promise.resolve({
    ok,
    status: ok ? 200 : 404,
    json: async () => Object.assign({ schema_version: 1, request_id: "r", data }, extra),
  });
};

startApplication(rootEl, { restoreProjectId: "project-b", mapContainer: {} }).then(() => {
  const selected = getState().selectedProjectId;
  if (selected === "project-b") {
    console.log("PASS");
    process.exit(0);
  } else {
    console.error("FAIL: selectedProjectId=" + selected);
    process.exit(1);
  }
});
"""


def test_restore_project_id_beyond_first_page_of_projects_still_resolves(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _RESTORE_BEYOND_FIRST_PAGE_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_INVALID_RESTORE_WITH_LONE_PROJECT_SCENARIO = """
import { startApplication, getState } from "./application.js";

global.fetch = (url) => {
  const u = String(url);
  let ok = true;
  let data;
  let extra = {};
  if (u === "/api/session") {
    extra = { csrf_token: "csrf-token" };
  } else if (u === "/api/theme") {
    data = { theme: {}, motion: {} };
  } else if (u === "/api/projects") {
    data = { items: [{ project_id: "project-a", root: "/a" }] };
  } else if (u.indexOf("/api/projects/project-x/snapshot") === 0) {
    // Unknown/invalid restoreProjectId -- real _handle_snapshot 404s this.
    ok = false;
  } else {
    ok = false;
  }
  return Promise.resolve({
    ok,
    status: ok ? 200 : 404,
    json: async () => Object.assign({ schema_version: 1, request_id: "r", data }, extra),
  });
};

startApplication(rootEl, { restoreProjectId: "project-x", mapContainer: {} }).then(() => {
  const selected = getState().selectedProjectId;
  // Must show the chooser (no selection) -- must NEVER silently auto-select
  // the one other registered project instead.
  if (selected === null) {
    console.log("PASS");
    process.exit(0);
  } else {
    console.error("FAIL: selectedProjectId=" + selected);
    process.exit(1);
  }
});
"""


def test_invalid_restore_project_id_with_exactly_one_registered_project_shows_chooser_not_that_project(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _INVALID_RESTORE_WITH_LONE_PROJECT_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


# --- Phase 69 codex-review remediation T013: U05/U06/U07/U08/U10/U11 ------
#
# These extend the same real-`application.js`-over-Node harness above rather
# than a second mechanism. Shared mock-fetch/DOM-interaction helpers below
# (envelope/jsonOk/goto/etc) are plain JS text prepended to each scenario --
# `_run_restore_project_id_harness` is generic despite its name (any scenario
# JS), reused here rather than duplicating the harness runner/DOM shim.
# Real 480ms/reduced-motion/full-browser-timing observation for these same
# findings happens separately in a live browser session (never substituted
# by this pytest surrogate) -- U05/U06/U07/U08/U10/U11 are all named
# browser-acceptance findings per the review doc's own §9/§12.

_ACTION_HARNESS_HELPERS_JS = """
function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
function jsonOk(body) {
  return Promise.resolve({ ok: true, status: 200, json: async () => body });
}
function jsonStatus(status, body) {
  return Promise.resolve({ ok: status >= 200 && status < 300, status, json: async () => body });
}
function envelope(projectId, sequence, data) {
  return { schema_version: 1, request_id: "r", project_id: projectId, sequence, data };
}
function sessionBody() {
  return {
    schema_version: 1,
    request_id: "r",
    csrf_token: "csrf-token",
    owner_scope_id: "owner-session-1",
  };
}
function themeBody() {
  return envelope(null, 0, { theme: {}, motion: {} });
}
function projectsBody(items) {
  return envelope(null, 0, { items });
}
function findForm(operation) {
  return inspector.querySelector('[data-operation="' + operation + '"]');
}
async function goto(section) {
  const order = ["map", "overview", "scans", "memory", "tokens", "git", "artifacts", "setup"];
  nav._children[order.indexOf(section)].click();
  await wait(30);
}
"""


# --- U05: lossless artifact-download pagination ----------------------------

_ARTIFACT_EXPORT_MULTI_PAGE_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + """
import { startApplication } from "./application.js";

const fullBytes = Buffer.concat([
  Buffer.from("h\\u00e9", "utf-8"), // 0x68 0xC3 0xA9 -- multi-byte char split below
  Buffer.from([0x00, 0xff]),
  Buffer.from("w\\u00f6rld", "utf-8"),
]);
const splitAt = 2; // right inside the 2-byte 0xC3 0xA9 sequence
const page1 = fullBytes.subarray(0, splitAt);
const page2 = fullBytes.subarray(splitAt);
const ARTIFACT_REF = "run:r1:a1:c1";

const realBlob = global.Blob;
let lastChunks = null;
global.Blob = class extends realBlob {
  constructor(parts, opts) {
    lastChunks = parts;
    super(parts, opts);
  }
};

global.fetch = (url, options) => {
  const u = String(url);
  if (u === "/api/session") return jsonOk(sessionBody());
  if (u === "/api/theme") return jsonOk(themeBody());
  if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
  if (u.indexOf("/api/projects/project-a/snapshot") === 0) return jsonOk(envelope("project-a", 1, { nodes: [], edges: [] }));
  if (u === "/api/projects/project-a/actions") {
    return jsonOk(
      envelope("project-a", 1, {
        found: true,
        kind: "scan_output",
        entry: { artifact_ref: ARTIFACT_REF, run_id: "r1", attempt_id: "a1", tool_id: "c1", paths: ["out.bin"] },
      })
    );
  }
  if (u.indexOf("/api/projects/project-a/artifacts/") === 0) {
    const offset = Number(new URL(u, "http://x").searchParams.get("offset"));
    const page = offset === 0 ? page1 : page2;
    const nextOffset = offset === 0 ? splitAt : null;
    return jsonOk(
      envelope("project-a", 1, {
        found: true,
        kind: "scan_output",
        entry: { artifact_ref: ARTIFACT_REF, paths: ["out.bin"] },
        content: {
          path: "out.bin",
          offset,
          size: fullBytes.length,
          content_base64: page.toString("base64"),
          next_offset: nextOffset,
          sha256: "digest-1",
          media_type: "application/octet-stream",
        },
      })
    );
  }
  return jsonOk(envelope(null, 0, {}));
};

await startApplication(rootEl, { mapContainer: {} });
await goto("artifacts");
const form = findForm("artifact_export");
form.querySelector('[name="artifact_id"]').value = ARTIFACT_REF;
form.querySelector('[data-grant="download"]').checked = true;
form.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(100);

const result = form.querySelector('[data-role="action-result"]');
const assembled = Buffer.concat((lastChunks || []).map((c) => Buffer.from(c)));
if (assembled.equals(fullBytes) && result.textContent.indexOf("downloaded " + fullBytes.length) === 0) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error(
    "FAIL result=" + result.textContent + " assembledLen=" + assembled.length + " expectedLen=" + fullBytes.length
  );
  process.exit(1);
}
"""
)


def test_artifact_export_control_follows_next_offset_until_null_and_assembles_full_byte_content(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _ARTIFACT_EXPORT_MULTI_PAGE_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_ARTIFACT_EXPORT_INCONSISTENT_PAGE_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + """
import { startApplication } from "./application.js";

const ARTIFACT_REF = "run:r1:a1:c1";

global.fetch = (url) => {
  const u = String(url);
  if (u === "/api/session") return jsonOk(sessionBody());
  if (u === "/api/theme") return jsonOk(themeBody());
  if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
  if (u.indexOf("/api/projects/project-a/snapshot") === 0) return jsonOk(envelope("project-a", 1, { nodes: [], edges: [] }));
  if (u === "/api/projects/project-a/actions") {
    return jsonOk(
      envelope("project-a", 1, {
        found: true,
        kind: "scan_output",
        entry: { artifact_ref: ARTIFACT_REF, run_id: "r1", attempt_id: "a1", tool_id: "c1", paths: ["out.bin"] },
      })
    );
  }
  if (u.indexOf("/api/projects/project-a/artifacts/") === 0) {
    const offset = Number(new URL(u, "http://x").searchParams.get("offset"));
    if (offset === 0) {
      return jsonOk(
        envelope("project-a", 1, {
          found: true,
          entry: { artifact_ref: ARTIFACT_REF, paths: ["out.bin"] },
          content: {
            path: "out.bin",
            offset: 0,
            size: 10,
            content_base64: Buffer.from("hello").toString("base64"),
            next_offset: 5,
            sha256: "digest-1",
            media_type: "application/octet-stream",
          },
        })
      );
    }
    // Second page: digest silently changed mid-download -- a truncated or
    // tampered sequence must be rejected, never assembled as complete.
    return jsonOk(
      envelope("project-a", 1, {
        found: true,
        entry: { artifact_ref: ARTIFACT_REF, paths: ["out.bin"] },
        content: {
          path: "out.bin",
          offset: 5,
          size: 10,
          content_base64: Buffer.from("world").toString("base64"),
          next_offset: null,
          sha256: "digest-DIFFERENT",
          media_type: "application/octet-stream",
        },
      })
    );
  }
  return jsonOk(envelope(null, 0, {}));
};

await startApplication(rootEl, { mapContainer: {} });
await goto("artifacts");
const form = findForm("artifact_export");
form.querySelector('[name="artifact_id"]').value = ARTIFACT_REF;
form.querySelector('[data-grant="download"]').checked = true;
form.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(100);

const result = form.querySelector('[data-role="action-result"]');
const anchor = form.querySelector('[data-role="artifact-download-link"]');
if (result.textContent.indexOf("download failed") === 0 && !anchor) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL result=" + result.textContent + " anchor=" + !!anchor);
  process.exit(1);
}
"""
)


def test_artifact_export_control_rejects_a_truncated_or_inconsistent_page_sequence(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _ARTIFACT_EXPORT_INCONSISTENT_PAGE_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_ARTIFACT_EXPORT_CANCELLATION_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + """
import { startApplication } from "./application.js";

const ARTIFACT_REF = "run:r1:a1:c1";
let secondPageFetches = 0;

global.fetch = (url, options) => {
  const u = String(url);
  if (u === "/api/session") return jsonOk(sessionBody());
  if (u === "/api/theme") return jsonOk(themeBody());
  if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
  if (u.indexOf("/api/projects/project-a/snapshot") === 0) return jsonOk(envelope("project-a", 1, { nodes: [], edges: [] }));
  if (u === "/api/projects/project-a/actions") {
    return jsonOk(
      envelope("project-a", 1, {
        found: true,
        entry: { artifact_ref: ARTIFACT_REF, run_id: "r1", attempt_id: "a1", tool_id: "c1", paths: ["out.bin"] },
      })
    );
  }
  if (u.indexOf("/api/projects/project-a/artifacts/") === 0) {
    const offset = Number(new URL(u, "http://x").searchParams.get("offset"));
    if (offset === 0) {
      return jsonOk(
        envelope("project-a", 1, {
          found: true,
          entry: { artifact_ref: ARTIFACT_REF, paths: ["out.bin"] },
          content: {
            path: "out.bin",
            offset: 0,
            size: 10,
            content_base64: Buffer.from("hello").toString("base64"),
            next_offset: 5,
            sha256: "digest-1",
            media_type: "application/octet-stream",
          },
        })
      );
    }
    secondPageFetches += 1;
    // Never resolves on its own -- only the AbortController's signal ends it.
    return new Promise((_resolve, reject) => {
      const signal = options && options.signal;
      if (signal) {
        signal.addEventListener("abort", () => {
          const err = new Error("aborted");
          err.name = "AbortError";
          reject(err);
        });
      }
    });
  }
  return jsonOk(envelope(null, 0, {}));
};

await startApplication(rootEl, { mapContainer: {} });
await goto("artifacts");
const form = findForm("artifact_export");
form.querySelector('[name="artifact_id"]').value = ARTIFACT_REF;
form.querySelector('[data-grant="download"]').checked = true;
form.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(50); // let page 1 resolve, page 2 fetch start (and hang)
form.querySelector('[data-role="artifact-export-cancel"]').click();
await wait(50);

const result = form.querySelector('[data-role="action-result"]');
if (result.textContent === "download cancelled" && secondPageFetches === 1) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL result=" + result.textContent + " secondPageFetches=" + secondPageFetches);
  process.exit(1);
}
"""
)


def test_artifact_export_control_supports_cancellation_via_abortcontroller(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _ARTIFACT_EXPORT_CANCELLATION_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


# --- U06: visible handoff Preview -> Send -------------------------------

_HANDOFF_ACTIONS_MOCK_JS = """
function handoffActionsFetch(capturedActions, opts) {
  return (url, options) => {
    const u = String(url);
    if (u === "/api/session") return jsonOk(sessionBody());
    if (u === "/api/theme") return jsonOk(themeBody());
    if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
    if (u.indexOf("/api/projects/project-a/snapshot") === 0) return jsonOk(envelope("project-a", 1, { nodes: [], edges: [] }));
    if (u === "/api/projects/project-a/actions") {
      const body = JSON.parse(options.body);
      capturedActions.push(body);
      if (body.operation === "handoff_preview") {
        return jsonOk(
          envelope("project-a", 1, { run_id: body.arguments.run_id, agent_id: body.arguments.agent_id, handoff_id: opts.handoffId })
        );
      }
      if (body.operation === "handoff_send") {
        if (opts.sendStatus === 409) {
          return jsonStatus(409, envelope("project-a", 1, { error: "conflict" }));
        }
        return jsonStatus(202, envelope("project-a", 1, { operation_id: "op-1" }));
      }
    }
    if (u.indexOf("/api/projects/project-a/operations/op-1") === 0) {
      return jsonOk(envelope("project-a", 1, { terminal_at: "now", status: "delivered" }));
    }
    return jsonOk(envelope(null, 0, {}));
  };
}
"""

_HANDOFF_PREVIEW_THEN_SEND_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + _HANDOFF_ACTIONS_MOCK_JS
    + """
import { startApplication } from "./application.js";

const capturedActions = [];
global.fetch = handoffActionsFetch(capturedActions, { handoffId: "hash-1" });

await startApplication(rootEl, { mapContainer: {} });
await goto("scans");
const form = findForm("handoff_preview");
form.querySelector('[name="run_id"]').value = "run-1";
form.querySelector('[name="attempt_id"]').value = "attempt-1";
form.querySelector('[name="agent_id"]').value = "codex-cli";
form.querySelector('[data-role="handoff-preview"]').click();
await wait(50);

const sendBtn = form.querySelector('[data-role="handoff-send"]');
if (sendBtn.disabled) {
  console.error("FAIL: Send still disabled after a successful Preview");
  process.exit(1);
}
sendBtn.click();
await wait(50);

const result = form.querySelector('[data-role="action-result"]');
const sendCall = capturedActions.find((a) => a.operation === "handoff_send");
const inputsMatch =
  sendCall &&
  sendCall.arguments.run_id === "run-1" &&
  sendCall.arguments.attempt_id === "attempt-1" &&
  sendCall.arguments.agent_id === "codex-cli" &&
  sendCall.arguments.handoff_id === "hash-1";
if (inputsMatch && result.textContent.indexOf("delivered") !== -1) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL capturedActions=" + JSON.stringify(capturedActions) + " result=" + result.textContent);
  process.exit(1);
}
"""
)


def test_visible_handoff_preview_then_send_completes_using_stored_preview_inputs(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _HANDOFF_PREVIEW_THEN_SEND_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_HANDOFF_409_ZERO_EFFECTS_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + _HANDOFF_ACTIONS_MOCK_JS
    + """
import { startApplication } from "./application.js";

const capturedActions = [];
let operationPolls = 0;
const baseFetch = handoffActionsFetch(capturedActions, { handoffId: "hash-1", sendStatus: 409 });
global.fetch = (url, options) => {
  if (String(url).indexOf("/operations/") !== -1) operationPolls += 1;
  return baseFetch(url, options);
};

await startApplication(rootEl, { mapContainer: {} });
await goto("scans");
const form = findForm("handoff_preview");
form.querySelector('[name="run_id"]').value = "run-1";
form.querySelector('[name="attempt_id"]').value = "attempt-1";
form.querySelector('[name="agent_id"]').value = "codex-cli";
form.querySelector('[data-role="handoff-preview"]').click();
await wait(50);
form.querySelector('[data-role="handoff-send"]').click();
await wait(50);

const result = form.querySelector('[data-role="action-result"]');
const sendBtn = form.querySelector('[data-role="handoff-send"]');
const sendCalls = capturedActions.filter((a) => a.operation === "handoff_send");
if (
  sendCalls.length === 1 &&
  operationPolls === 0 &&
  sendBtn.disabled &&
  result.textContent.toLowerCase().indexOf("stale") !== -1
) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error(
    "FAIL sendCalls=" + sendCalls.length + " operationPolls=" + operationPolls + " disabled=" + sendBtn.disabled + " result=" + result.textContent
  );
  process.exit(1);
}
"""
)


def test_source_or_attempt_change_between_preview_and_send_yields_409_and_zero_effects(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _HANDOFF_409_ZERO_EFFECTS_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_HANDOFF_STALE_REQUIRES_FRESH_PREVIEW_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + _HANDOFF_ACTIONS_MOCK_JS
    + """
import { startApplication } from "./application.js";

const capturedActions = [];
const opts = { handoffId: "hash-1", sendStatus: 409 };
global.fetch = handoffActionsFetch(capturedActions, opts);

await startApplication(rootEl, { mapContainer: {} });
await goto("scans");
const form = findForm("handoff_preview");
form.querySelector('[name="run_id"]').value = "run-1";
form.querySelector('[name="attempt_id"]').value = "attempt-1";
form.querySelector('[name="agent_id"]').value = "codex-cli";
const sendBtn = form.querySelector('[data-role="handoff-send"]');

form.querySelector('[data-role="handoff-preview"]').click();
await wait(50);
sendBtn.click(); // this send 409s (opts.sendStatus === 409) -> stale, Send disabled
await wait(50);
const actionsAfterStaleSend = capturedActions.length;

sendBtn.click(); // disabled -- must be a no-op, no new network call at all
await wait(30);
if (capturedActions.length !== actionsAfterStaleSend) {
  console.error("FAIL: clicking a disabled Send dispatched a new action");
  process.exit(1);
}

opts.sendStatus = 200; // a fresh preview should now succeed normally
form.querySelector('[data-role="handoff-preview"]').click();
await wait(50);
if (sendBtn.disabled) {
  console.error("FAIL: Send still disabled after an explicit fresh Preview");
  process.exit(1);
}
console.log("PASS");
process.exit(0);
"""
)


def test_stale_preview_disables_send_until_explicit_fresh_preview(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _HANDOFF_STALE_REQUIRES_FRESH_PREVIEW_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_HANDOFF_REQUIRES_RUN_AND_ATTEMPT_ID_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + _HANDOFF_ACTIONS_MOCK_JS
    + """
import { startApplication } from "./application.js";

const capturedActions = [];
global.fetch = handoffActionsFetch(capturedActions, { handoffId: "hash-1" });

await startApplication(rootEl, { mapContainer: {} });
await goto("scans");
const form = findForm("handoff_preview");
// run_id supplied, attempt_id left blank -- S06 requires both.
form.querySelector('[name="run_id"]').value = "run-1";
form.querySelector('[data-role="handoff-preview"]').click();
await wait(30);

const result = form.querySelector('[data-role="action-result"]');
if (capturedActions.length === 0 && result.textContent.indexOf("attempt_id") !== -1) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL capturedActions=" + capturedActions.length + " result=" + result.textContent);
  process.exit(1);
}
"""
)


def test_handoff_preview_and_send_both_require_run_id_and_attempt_id_per_s06(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _HANDOFF_REQUIRES_RUN_AND_ATTEMPT_ID_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


# --- U07: shell interactivity is independent of a slow map fetch -----------

_SHELL_INTERACTIVE_INDEPENDENT_OF_MAP_FETCH_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + """
import { startApplication, getState } from "./application.js";

let mapResolved = false;
global.fetch = (url) => {
  const u = String(url);
  if (u === "/api/session") return jsonOk(sessionBody());
  if (u === "/api/theme") return jsonOk(themeBody());
  if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
  if (u.indexOf("/api/projects/project-a/snapshot") === 0) {
    if (u.indexOf("section=overview") !== -1) return jsonOk(envelope("project-a", 1, { source_identity: null }));
    // The map fetch (section=map): deliberately delayed ~2s, mirroring the
    // finding's own native-browser repro (map response at ~2015ms).
    return new Promise((resolve) => {
      setTimeout(() => {
        mapResolved = true;
        resolve({ ok: true, status: 200, json: async () => envelope("project-a", 1, { nodes: [], edges: [] }) });
      }, 2000);
    });
  }
  return jsonOk(envelope(null, 0, {}));
};

const navStart = Date.now();
await startApplication(rootEl, { mapContainer: {} });
// Selection/section-switch must work well within the ~1s warm-local bound
// while the map fetch above is still pending -- never blocked on it.
nav._children[1].click(); // "overview" -- a real section switch, not map
await wait(30);
const elapsed = Date.now() - navStart;

if (getState().activeSection === "overview" && !mapResolved && elapsed < 1000) {
  console.log("PASS elapsed=" + elapsed);
  process.exit(0);
} else {
  console.error(
    "FAIL activeSection=" + getState().activeSection + " mapResolved=" + mapResolved + " elapsed=" + elapsed
  );
  process.exit(1);
}
"""
)


def test_shell_interactive_signal_independent_of_map_fetch_completion(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _SHELL_INTERACTIVE_INDEPENDENT_OF_MAP_FETCH_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


# --- U08: terminal-event pulse fires through real ledger polling -----------

_PULSE_SPY_PROJECT_MAP_STUB = """
export const pulseCalls = [];
export function renderMap(_container, _mapData) {}
export function fitMap() {}
export function destroyMap() {}
export function showGroupMembers() {}
export function hideGroupMembers() {}
export function setReducedMotion(_value) {}
export function pulseEvidence(nodeId) {
  pulseCalls.push(nodeId);
}
"""

_TERMINAL_EVENT_PULSE_VIA_POLLING_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + """
import { startApplication } from "./application.js";
import { pulseCalls } from "./project_map.js";

let eventsCall = 0;
global.fetch = (url) => {
  const u = String(url);
  if (u === "/api/session") return jsonOk(sessionBody());
  if (u === "/api/theme") return jsonOk(themeBody());
  if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
  if (u.indexOf("/api/projects/project-a/snapshot") === 0) return jsonOk(envelope("project-a", 1, { nodes: [], edges: [] }));
  if (u.indexOf("/api/projects/project-a/events") === 0) {
    eventsCall += 1;
    // The first normal ledger-poll tick observes a real terminal scan
    // event -- never a synthetic direct call to the pulse helper itself.
    if (eventsCall === 1) return jsonOk(envelope("project-a", 2, { events: [{ status: "terminal" }] }));
    return jsonOk(envelope("project-a", 2, { events: [] }));
  }
  return jsonOk(envelope(null, 0, {}));
};

await startApplication(rootEl, { mapContainer: {} });
await wait(900); // first poll tick fires after the 750ms active interval

if (pulseCalls.length === 1 && pulseCalls[0] === "project:project-a") {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL pulseCalls=" + JSON.stringify(pulseCalls));
  process.exit(1);
}
"""
)


def test_terminal_event_pulse_plays_once_480ms_on_real_scan_completion_via_normal_ledger_polling(
    tmp_path: Path,
) -> None:
    """The 480ms duration / single-iteration / reduced-motion-gating token
    contract itself is asserted structurally in
    `tests/test_dashboard_motion_contract.py::
    test_terminal_pulse_has_exactly_one_iteration_and_no_animation_under_reduced_motion`
    (real `project_map.js` source, real animation call); this test is the
    other half -- proving `application.js`'s own polling `tick` actually
    reaches `pulseEvidence` on a genuine terminal ledger event, not merely
    that the two happen to share code elsewhere. Real full-browser 480ms
    timing observation is a separate live-browser acceptance step (this
    finding is browser-acceptance, per the review doc's own §12)."""
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path,
        _TERMINAL_EVENT_PULSE_VIA_POLLING_SCENARIO,
        project_map_stub=_PULSE_SPY_PROJECT_MAP_STUB,
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


# --- U10: owner-scope controls on every memory mutation form ---------------

_MEMORY_OWNER_SCOPE_BASE_FETCH_JS = """
function memoryOwnerFetch(capturedActions, opts) {
  opts = opts || {};
  return (url, options) => {
    const u = String(url);
    if (u === "/api/session") return jsonOk(sessionBody());
    if (u === "/api/theme") return jsonOk(themeBody());
    if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
    if (u.indexOf("/api/projects/project-a/snapshot") === 0) return jsonOk(envelope("project-a", 1, { nodes: [], edges: [] }));
    if (u === "/api/projects/project-a/actions") {
      const body = JSON.parse(options.body);
      capturedActions.push(body);
      const owner = body.arguments.owner_scope || {};
      const rejected =
        !owner.id ||
        (owner.kind === "project" && owner.id !== "project-a") ||
        (owner.kind === "session" && owner.id !== "owner-session-1");
      if (rejected) {
        return jsonStatus(400, envelope("project-a", 1, { error: "malformed_request", message: "invalid owner_scope" }));
      }
      return jsonOk(envelope("project-a", 2, { id: "mem-1", version: 1 }));
    }
    return jsonOk(envelope(null, 0, {}));
  };
}
"""


def _memory_form_field(scenario_extra: str) -> str:
    return (
        _ACTION_HARNESS_HELPERS_JS
        + _MEMORY_OWNER_SCOPE_BASE_FETCH_JS
        + """
import { startApplication } from "./application.js";

const capturedActions = [];
global.fetch = memoryOwnerFetch(capturedActions);

await startApplication(rootEl, { mapContainer: {} });
await goto("memory");
"""
        + scenario_extra
    )


_ALL_FIVE_MEMORY_OPS = (
    "memory_propose",
    "memory_promote",
    "memory_edit",
    "memory_archive",
    "memory_delete",
)

_ALL_FIVE_EXPOSE_OWNER_CONTROL_SCENARIO = _memory_form_field(
    """
const ops = ["memory_propose", "memory_promote", "memory_edit", "memory_archive", "memory_delete"];
const missing = ops.filter((op) => {
  const form = findForm(op);
  return !form || !form.querySelector('[data-role="owner-kind"]') || !form.querySelector('[data-role="owner-id"]');
});
if (missing.length === 0) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL missing owner control for: " + missing.join(","));
  process.exit(1);
}
"""
)


def test_all_five_memory_actions_expose_owner_kind_and_id_control(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _ALL_FIVE_EXPOSE_OWNER_CONTROL_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_PROJECT_OWNER_USES_SELECTED_UUID_SCENARIO = _memory_form_field(
    """
const form = findForm("memory_propose");
const ownerId = form.querySelector('[data-role="owner-id"]');
const ownerKind = form.querySelector('[data-role="owner-kind"]');
if (ownerKind.value === "project" && ownerId.value === "project-a" && ownerId.readOnly === true) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL kind=" + ownerKind.value + " id=" + ownerId.value + " readOnly=" + ownerId.readOnly);
  process.exit(1);
}
"""
)


def test_project_owner_uses_selected_registered_uuid(tmp_path: Path) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _PROJECT_OWNER_USES_SELECTED_UUID_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_USER_AGENT_OWNER_ACCEPTS_LABEL_SCENARIO = _memory_form_field(
    """
const form = findForm("memory_propose");
const ownerKind = form.querySelector('[data-role="owner-kind"]');
const ownerId = form.querySelector('[data-role="owner-id"]');
ownerKind.value = "user";
ownerKind.dispatchEvent({ type: "change" });
if (ownerId.readOnly) {
  console.error("FAIL: owner id stayed read-only for a user-kind owner");
  process.exit(1);
}
ownerId.value = "alice";
form.querySelector('[name="subject"]').value = "subj-1";
form.querySelector('[name="content"]').value = '{"text":"hi"}';
form.querySelector('[name="source"]').value = "src-1";
form.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(50);

const sent = capturedActions.find((a) => a.operation === "memory_propose");
if (sent && sent.arguments.owner_scope && sent.arguments.owner_scope.kind === "user" && sent.arguments.owner_scope.id === "alice") {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL captured=" + JSON.stringify(capturedActions));
  process.exit(1);
}
"""
)


def test_user_agent_owner_accepts_opaque_nonblank_label(tmp_path: Path) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _USER_AGENT_OWNER_ACCEPTS_LABEL_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_SESSION_OWNER_USES_STATE_ID_SCENARIO = _memory_form_field(
    """
const form = findForm("memory_propose");
const ownerKind = form.querySelector('[data-role="owner-kind"]');
const ownerId = form.querySelector('[data-role="owner-id"]');
ownerKind.value = "session";
ownerKind.dispatchEvent({ type: "change" });
if (ownerId.value === "owner-session-1" && ownerId.readOnly === true) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL id=" + ownerId.value + " readOnly=" + ownerId.readOnly);
  process.exit(1);
}
"""
)


def test_session_owner_uses_non_secret_owner_scope_id_from_session_state(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _SESSION_OWNER_USES_STATE_ID_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_MISSING_FOREIGN_MISMATCHED_OWNER_SCENARIO = _memory_form_field(
    """
const form = findForm("memory_propose");
const ownerKind = form.querySelector('[data-role="owner-kind"]');
const ownerId = form.querySelector('[data-role="owner-id"]');
const subject = form.querySelector('[name="subject"]');
subject.value = "keep-me";
form.querySelector('[name="content"]').value = '{"text":"hi"}';
form.querySelector('[name="source"]').value = "src-1";

async function attempt(kind, id) {
  ownerKind.value = kind;
  ownerKind.dispatchEvent({ type: "change" });
  // The control auto-derives project/session ids and marks them read-only
  // (never a free-typed value through the honest UI) -- force the id here
  // anyway to simulate a value that reached the wire some other way, so
  // this test can prove the mocked server (M08, real elsewhere) is what
  // actually stops it, not just the client's own UI convenience.
  ownerId.value = id;
  form.dispatchEvent({ type: "submit", preventDefault() {} });
  await wait(30);
}

// missing (blank user id)
await attempt("user", "");
const afterMissing = form.querySelector('[data-role="action-result"]').textContent;
// foreign project id (never the selected project's own id)
await attempt("project", "some-other-project");
const afterForeign = form.querySelector('[data-role="action-result"]').textContent;
// mismatched session id (never the real session's own owner_scope_id)
await attempt("session", "not-the-real-session-id");
const afterMismatch = form.querySelector('[data-role="action-result"]').textContent;

const allRejected = [afterMissing, afterForeign, afterMismatch].every(
  (t) => t.indexOf("malformed_request") !== -1
);
if (allRejected && subject.value === "keep-me") {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL afterMissing=" + afterMissing + " afterForeign=" + afterForeign + " afterMismatch=" + afterMismatch);
  process.exit(1);
}
"""
)


def test_missing_or_foreign_or_mismatched_owner_leaves_storage_unchanged(
    tmp_path: Path,
) -> None:
    """The client-side half: each rejected submission's server response is
    shown verbatim and the form's other input (`subject`) is preserved, never
    optimistically cleared as if the mutation had committed. `owner_scope`
    reservation/rejection *before any row change* is M08's own server-side
    contract, already covered by that finding's own tests (not re-verified
    here, per this finding's own client-side Fix scope)."""
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _MISSING_FOREIGN_MISMATCHED_OWNER_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


def test_session_renewal_supplies_new_non_secret_id_without_transferring_old_rows_ownership() -> (
    None
):
    """Server-side half of U10 point 2 -- a fresh session (a renewed
    bootstrap exchange, exactly what happens on reconnect) always mints its
    own distinct, non-secret `owner_scope_id`; nothing in `DashboardAuth`
    ever copies one session's id onto another, which is what would let a
    renewal silently inherit an old session's already-owned rows."""
    from rush.dashboard.auth import DashboardAuth

    auth = DashboardAuth()
    first_token = auth.issue_bootstrap()
    first_session, _cookie = auth.exchange_bootstrap(first_token)

    second_token = auth.issue_bootstrap()
    second_session, _cookie2 = auth.exchange_bootstrap(second_token)

    assert first_session.owner_scope_id != second_session.owner_scope_id
    assert first_session.owner_scope_id and second_session.owner_scope_id


# --- U11: memory content/source-kind form contract --------------------------

_CONTENT_JSON_OBJECT_SCENARIO = _memory_form_field(
    """
const form = findForm("memory_propose");
const contentInput = form.querySelector('[name="content"]');
const subject = form.querySelector('[name="subject"]');
subject.value = "subj-1";
form.querySelector('[name="source"]').value = "src-1";

if (contentInput.getAttribute("placeholder") !== '{"text":"..."}') {
  console.error("FAIL: missing illustrative JSON-object placeholder");
  process.exit(1);
}

contentInput.value = "not json at all";
form.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(30);
const afterInvalidJson = form.querySelector('[data-role="action-result"]').textContent;

contentInput.value = "[1,2,3]"; // valid JSON, but an array, not an object
form.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(30);
const afterArray = form.querySelector('[data-role="action-result"]').textContent;

if (
  afterInvalidJson.indexOf("valid JSON") !== -1 &&
  afterArray.indexOf("JSON object") !== -1 &&
  capturedActions.length === 0
) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL afterInvalidJson=" + afterInvalidJson + " afterArray=" + afterArray + " captured=" + capturedActions.length);
  process.exit(1);
}
"""
)


def test_content_field_shows_json_object_example_and_rejects_non_object_input_client_side(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _CONTENT_JSON_OBJECT_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_MALFORMED_CONTENT_SENDS_NO_POST_SCENARIO = _memory_form_field(
    """
const form = findForm("memory_propose");
form.querySelector('[name="subject"]').value = "subj-1";
form.querySelector('[name="source"]').value = "src-1";
form.querySelector('[name="content"]').value = "{not valid json";
form.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(30);

if (capturedActions.length === 0) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL: a POST was sent for malformed content: " + JSON.stringify(capturedActions));
  process.exit(1);
}
"""
)


def test_malformed_or_non_object_content_sends_no_post_request(tmp_path: Path) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _MALFORMED_CONTENT_SENDS_NO_POST_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_SOURCE_KIND_SELECT_OPTIONS_SCENARIO = _memory_form_field(
    """
const expected = ["local_tool", "cross_tool_handoff", "human_derived"];
const proposeSelect = findForm("memory_propose").querySelector('[name="source_kind"]');
const promoteSelect = findForm("memory_promote").querySelector('[name="source_kind"]');
const proposeValues = proposeSelect._children.map((o) => o.value);
const promoteValues = promoteSelect._children.map((o) => o.value);
const matches = (values) => values.length === expected.length && values.every((v, i) => v === expected[i]);
if (matches(proposeValues) && matches(promoteValues)) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL propose=" + JSON.stringify(proposeValues) + " promote=" + JSON.stringify(promoteValues));
  process.exit(1);
}
"""
)


def test_source_kind_select_offers_exactly_local_tool_cross_tool_handoff_human_derived_for_write_and_promote(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _SOURCE_KIND_SELECT_OPTIONS_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_EDIT_HAS_NO_SOURCE_KIND_SCENARIO = _memory_form_field(
    """
const editForm = findForm("memory_edit");
if (!editForm.querySelector('[name="source_kind"]')) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL: memory_edit unexpectedly exposes a source_kind field");
  process.exit(1);
}
"""
)


def test_edit_does_not_require_source_kind(tmp_path: Path) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _EDIT_HAS_NO_SOURCE_KIND_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout


_WRITE_EDIT_ARCHIVE_SEQUENCE_JS = """
function writeEditArchiveFetch(capturedActions) {
  let mem = null;
  return (url, options) => {
    const u = String(url);
    if (u === "/api/session") return jsonOk(sessionBody());
    if (u === "/api/theme") return jsonOk(themeBody());
    if (u === "/api/projects") return jsonOk(projectsBody([{ project_id: "project-a", root: "/a" }]));
    if (u.indexOf("/api/projects/project-a/snapshot") === 0) return jsonOk(envelope("project-a", 1, { nodes: [], edges: [] }));
    if (u === "/api/projects/project-a/actions") {
      const body = JSON.parse(options.body);
      capturedActions.push(body);
      if (body.operation === "memory_propose") {
        mem = { id: "mem-1", version: 1 };
        return jsonOk(envelope("project-a", 2, { id: mem.id, version: mem.version }));
      }
      if (body.operation === "memory_edit" || body.operation === "memory_archive") {
        if (!mem || body.arguments.id !== mem.id || body.arguments.expected_version !== mem.version) {
          return jsonStatus(409, envelope("project-a", 2, { error: "version_conflict" }));
        }
        mem.version += 1;
        return jsonOk(
          envelope("project-a", mem.version + 1, {
            id: mem.id,
            version: mem.version,
            archived: body.operation === "memory_archive",
          })
        );
      }
    }
    return jsonOk(envelope(null, 0, {}));
  };
}
"""

_WRITE_EDIT_ARCHIVE_SEQUENCE_SCENARIO = (
    _ACTION_HARNESS_HELPERS_JS
    + _WRITE_EDIT_ARCHIVE_SEQUENCE_JS
    + """
import { startApplication } from "./application.js";

const capturedActions = [];
global.fetch = writeEditArchiveFetch(capturedActions);

await startApplication(rootEl, { mapContainer: {} });
await goto("memory");

const proposeForm = findForm("memory_propose");
proposeForm.querySelector('[name="subject"]').value = "subj-1";
proposeForm.querySelector('[name="content"]').value = '{"text":"hi"}';
proposeForm.querySelector('[name="source"]').value = "src-1";
proposeForm.dispatchEvent({ type: "submit", preventDefault() {} });
await wait(50);

const editForm = findForm("memory_edit");
editForm.querySelector('[name="scope"]').value = "project";
editForm.querySelector('[name="id"]').value = "mem-1";
editForm.querySelector('[name="expected_version"]').value = "1";
editForm.querySelector('[name="content"]').value = '{"text":"edited"}';
editForm.querySelector('[data-role="apply"]').click();
await wait(50);

const archiveForm = findForm("memory_archive");
archiveForm.querySelector('[name="scope"]').value = "project";
archiveForm.querySelector('[name="id"]').value = "mem-1";
archiveForm.querySelector('[name="expected_version"]').value = "2";
archiveForm.querySelector('[name="archived"]').checked = true;
archiveForm.querySelector('[data-role="apply"]').click();
await wait(50);

const finalResult = archiveForm.querySelector('[data-role="action-result"]').textContent;
const parsedFinal = JSON.parse(finalResult).data;
if (parsedFinal.version === 3 && parsedFinal.archived === true) {
  console.log("PASS");
  process.exit(0);
} else {
  console.error("FAIL finalResult=" + finalResult + " captured=" + JSON.stringify(capturedActions));
  process.exit(1);
}
"""
)


def test_valid_write_edit_archive_sequence_produces_correct_revisions(
    tmp_path: Path,
) -> None:
    returncode, stdout, stderr = _run_restore_project_id_harness(
        tmp_path, _WRITE_EDIT_ARCHIVE_SEQUENCE_SCENARIO
    )
    assert returncode == 0, f"harness failed\\nstdout={stdout}\\nstderr={stderr}"
    assert "PASS" in stdout
