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
  for (const child of root._children) {
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
    tmp_path: Path, scenario_js: str
) -> tuple[int, str, str]:
    app_src = (
        Path(__file__).parent.parent / "src" / "rush" / "dashboard" / "application.js"
    )
    harness_dir = tmp_path / "restore_project_id_harness"
    harness_dir.mkdir()
    shutil.copyfile(app_src, harness_dir / "application.js")
    (harness_dir / "package.json").write_text(json.dumps({"type": "module"}))
    (harness_dir / "project_map.js").write_text(_PROJECT_MAP_STUB)
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
