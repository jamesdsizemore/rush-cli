"""Phase 70 TS: test-suite speed -- the design gate's section 3 matrix.

Each fix here removes redundant work (a capability scan per project view, a
full graph rebuild per group page, a retokenized page per memory candidate,
a second MCP server per inventory) or a slow/unsafe test pattern, without
weakening any behaviour. Cases marked keep-green pin behaviour a fix must
preserve; every other case fails before its fix.
"""

from __future__ import annotations

import ast
import copy
import io
import json
import os
import select
import shutil
import socket
import sys
import time
import tomllib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pytest

from rush.dashboard import project_map
from rush.dashboard import server as server_module
from rush.dashboard.project_map import expand_group
from rush.dashboard.server import MAX_BODY_BYTES, create_dashboard_server
from rush.memory import retrieval
from rush.memory.retrieval import hybrid_page, recall_page
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.runtime.binaries import resolve_binary
from rush.setup import provision as provision_module
from rush.workflows import project_run
from rush.workflows import projects as projects_module
from rush.workflows.projects import register_project

pytest_plugins = ["pytester"]

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFTEST = Path(__file__).resolve().parent / "conftest.py"


# --- shared helpers ---------------------------------------------------------


def _serve(server: Any) -> None:
    import threading

    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()


def _get(url: str, headers: dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        return urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        return exc


def _post(url: str, headers: dict[str, str] | None = None, body: bytes = b"") -> Any:
    req = urllib.request.Request(url, data=body, headers=headers or {}, method="POST")
    try:
        return urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as exc:
        return exc


def _bootstrap_session(base_url: str, token: str) -> str:
    resp = _post(
        f"{base_url}/api/session", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status == 200
    return resp.headers.get("Set-Cookie").split(";")[0]


def _isolate_data_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_root = tmp_path / "rush-data"
    monkeypatch.setattr(projects_module, "default_data_root", lambda: data_root)
    monkeypatch.setattr(provision_module, "default_data_root", lambda: data_root)
    return data_root


def _snapshot(project_id: str, root: Path, files: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "project_id": project_id,
        "source_identity": str(root),
        "root": str(root),
        "files": [{"path": path} for path in files],
        "findings": [],
        "memories": [],
        "agents": [],
    }


def _count_calls(monkeypatch: pytest.MonkeyPatch, owner: Any, name: str) -> list[int]:
    calls: list[int] = []
    real = getattr(owner, name)

    def _spy(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(owner, name, _spy)
    return calls


# --- R3: the project view computes languages without a capability scan ------


def test_r3_project_view_needs_no_capability_scan_or_path_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush import capabilities
    from rush.tools.routing import detect_project_languages

    root = tmp_path / "proj"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "p"\n', encoding="utf-8")
    (root / "package.json").write_text("{}\n", encoding="utf-8")
    data_root = tmp_path / "data"
    record = register_project(root, data_root=data_root)
    expected = detect_project_languages(root)
    assert expected

    def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("project view ran a capability scan / PATH lookup")

    monkeypatch.setattr(capabilities, "inspect_capabilities", _forbidden)
    monkeypatch.setattr(
        projects_module, "inspect_capabilities", _forbidden, raising=False
    )
    monkeypatch.setattr(shutil, "which", _forbidden)

    view = projects_module.resolve_project(record.project_id, data_root=data_root)
    assert view["languages"] == expected
    listed = projects_module.list_projects(data_root=data_root)
    assert [p["languages"] for p in listed] == [expected]


def test_r3_invalid_rush_toml_still_fails_the_view_closed(tmp_path: Path) -> None:
    """keep-green: dropping the capability scan must keep config validation."""
    from rush.config import RushConfigError

    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    data_root = tmp_path / "data"
    record = register_project(root, data_root=data_root)
    (root / "rush.toml").write_text("[tools\nbroken = ", encoding="utf-8")
    with pytest.raises(RushConfigError):
        projects_module.resolve_project(record.project_id, data_root=data_root)


# --- R4: expand_group membership memo ---------------------------------------


def _files_snapshot(project_id: str, count: int, prefix: str = "src") -> dict:
    return _snapshot(
        project_id,
        Path("/fixture") / project_id,
        [f"{prefix}/f{i:03d}.py" for i in range(count)],
    )


def _page_all(snapshot: dict[str, Any], group_id: str, **filters: Any) -> list[str]:
    ids: list[str] = []
    cursor = None
    while True:
        page = expand_group(snapshot, group_id, cursor=cursor, **filters)
        ids.extend(member["path"] for member in page["members"])
        cursor = page["next_cursor"]
        if cursor is None:
            return ids


def test_r4_paging_a_group_builds_the_graph_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _count_calls(monkeypatch, project_map, "_build_full_graph")
    snapshot = _files_snapshot("proj-memo", 450)
    ids = _page_all(snapshot, "group:src")
    assert len(ids) == 450
    assert len(calls) == 1


def test_r4_two_snapshots_with_the_same_identity_tuple_page_their_own_members() -> None:
    first = _files_snapshot("proj-same", 150)
    second = _files_snapshot("proj-same", 150)
    second["files"] = [{"path": f"src/other{i:03d}.py"} for i in range(150)]
    first_ids = _page_all(first, "group:src")
    second_ids = _page_all(second, "group:src")
    assert all(path.startswith("src/f") for path in first_ids)
    assert all(path.startswith("src/other") for path in second_ids)


def test_r4_appending_a_file_invalidates_the_memo() -> None:
    snapshot = _files_snapshot("proj-append", 150)
    assert len(_page_all(snapshot, "group:src")) == 150
    snapshot["files"].append({"path": "src/zz_new.py"})
    ids = _page_all(snapshot, "group:src")
    assert len(ids) == 151
    assert "src/zz_new.py" in ids


def test_r4_mutating_a_returned_member_does_not_change_later_pages() -> None:
    snapshot = _files_snapshot("proj-mutate", 150)
    page = expand_group(snapshot, "group:src")
    original = copy.deepcopy(page["members"][0])
    page["members"][0]["label"] = "mutated"
    page["members"][0]["path"] = "elsewhere"
    again = expand_group(snapshot, "group:src")
    assert again["members"][0] == original


def test_r4_a_different_filter_gives_different_membership() -> None:
    # `g` is not a hex digit, so the query cannot match a hashed node id.
    snapshot = _files_snapshot("proj-filter", 150)
    snapshot["files"] = [{"path": f"src/g{i:03d}.py"} for i in range(150)]
    everything = _page_all(snapshot, "group:src")
    filtered = _page_all(snapshot, "group:src", query="g01")
    assert len(everything) == 150
    assert filtered == [path for path in everything if "g01" in path]
    assert 0 < len(filtered) < len(everything)


# --- R4: the server reuses the published record and historical view ---------


def _start_map_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: list[str]
) -> tuple[Any, Any, str, str, str, Path]:
    data_root = _isolate_data_roots(tmp_path, monkeypatch)
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n", encoding="utf-8")
    project_id = register_project(root).project_id
    server, ctx, token = create_dashboard_server(
        {project_id: _snapshot(project_id, root, files)}, data_root=data_root
    )
    _serve(server)
    base_url = ctx.launch_origin
    cookie = _bootstrap_session(base_url, token)
    return server, ctx, base_url, cookie, project_id, root


def _map_request(base_url: str, project_id: str, cookie: str, query: str) -> Any:
    resp = _get(
        f"{base_url}/api/projects/{project_id}/snapshot?section=map&{query}",
        headers={"Cookie": cookie},
    )
    return resp.status, json.loads(resp.read())


def test_r4_http_group_paging_builds_the_graph_once_and_never_mutates_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, ctx, base_url, cookie, project_id, _root = _start_map_server(
        tmp_path, monkeypatch, [f"src/f{i:03d}.py" for i in range(250)]
    )
    try:
        before = copy.deepcopy(ctx.projects.get(project_id).snapshot)
        calls = _count_calls(monkeypatch, project_map, "_build_full_graph")
        from urllib.parse import quote

        members: list[str] = []
        cursor: str | None = None
        while True:
            query = "group=group:src" + (f"&cursor={quote(cursor)}" if cursor else "")
            status, body = _map_request(base_url, project_id, cookie, query)
            assert status == 200, body
            members.extend(m["id"] for m in body["data"]["members"])
            cursor = body["data"]["next_cursor"]
            if cursor is None:
                break
        assert len(members) == 250
        assert len(calls) == 1
        assert ctx.projects.get(project_id).snapshot == before
    finally:
        server.shutdown()
        server.server_close()


def _write_manifest(
    root: Path,
    run_id: str,
    attempt_id: str,
    finding_id: str,
    *,
    file_inventory: list[dict[str, str]] | None = None,
) -> Path:
    from rush.workflows.project_run import _write_attempt_header

    _write_attempt_header(root, run_id, attempt_id, "plan-x", "project-x")
    attempt_dir = root / ".rush" / "runs" / run_id / "attempts" / attempt_id
    attempt_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "run_state": "completed",
        "aggregate": {
            "findings": [
                {
                    "finding_id": finding_id,
                    "path": "app.py",
                    "line": 1,
                    "severity": "warn",
                    "message": finding_id,
                }
            ]
        },
    }
    if file_inventory is not None:
        manifest["file_inventory"] = file_inventory
    path = attempt_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _historical_findings(base_url: str, project_id: str, cookie: str) -> set[str]:
    status, body = _map_request(
        base_url, project_id, cookie, "run_id=run-a&attempt_id=att-a"
    )
    assert status == 200, body
    return {n["id"] for n in body["data"]["nodes"] if n["kind"] == "finding"}


def test_r4_second_historical_request_reuses_the_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _ctx, base_url, cookie, project_id, root = _start_map_server(
        tmp_path, monkeypatch, []
    )
    try:
        _write_manifest(root, "run-a", "att-a", "finding-a")
        builds = _count_calls(monkeypatch, server_module, "_snapshot_from_scan_result")
        assert _historical_findings(base_url, project_id, cookie) == {
            "finding:finding-a"
        }
        assert _historical_findings(base_url, project_id, cookie) == {
            "finding:finding-a"
        }
        assert len(builds) == 1
    finally:
        server.shutdown()
        server.server_close()


def test_r4_rewriting_the_manifest_invalidates_the_historical_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _ctx, base_url, cookie, project_id, root = _start_map_server(
        tmp_path, monkeypatch, []
    )
    try:
        manifest_path = _write_manifest(root, "run-a", "att-a", "finding-a")
        builds = _count_calls(monkeypatch, server_module, "_snapshot_from_scan_result")
        assert _historical_findings(base_url, project_id, cookie) == {
            "finding:finding-a"
        }
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["aggregate"]["findings"][0]["finding_id"] = "finding-rewritten"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        assert _historical_findings(base_url, project_id, cookie) == {
            "finding:finding-rewritten"
        }
        assert len(builds) == 2
    finally:
        server.shutdown()
        server.server_close()


def test_r4_an_empty_persisted_file_inventory_is_never_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty persisted inventory is rewalked from the live tree on every
    request, so its view can never be cached."""
    server, _ctx, base_url, cookie, project_id, root = _start_map_server(
        tmp_path, monkeypatch, []
    )
    try:
        _write_manifest(root, "run-a", "att-a", "finding-a", file_inventory=[])
        builds = _count_calls(monkeypatch, server_module, "_snapshot_from_scan_result")
        _historical_findings(base_url, project_id, cookie)
        (root / "late.py").write_text("y = 2\n", encoding="utf-8")
        status, body = _map_request(
            base_url, project_id, cookie, "run_id=run-a&attempt_id=att-a"
        )
        assert status == 200
        assert "late.py" in {n["path"] for n in body["data"]["nodes"]}
        assert len(builds) == 2
    finally:
        server.shutdown()
        server.server_close()


# --- R5: page budgets without retokenizing every trial page ------------------


def _write_memory(store: TypedArtifactStore, artifact_id: str, text: str) -> None:
    store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject="domain_knowledge",
            trust_tier="IMPORTED",
            content={"text": text},
            source="allowed",
            created_at=1.0,
        )
    )


def _seed_bulk(store: TypedArtifactStore, count: int) -> None:
    import sqlite3

    with sqlite3.connect(store.db_path) as conn:
        conn.executemany(
            "INSERT INTO memory_artifacts (id, family, subject, trust_tier, content, "
            "source, created_at, artifact_version) VALUES (?, 'memory', "
            "'domain_knowledge', 'IMPORTED', ?, 'allowed', 1.0, 1)",
            [
                (f"c{i:04d}", json.dumps({"text": f"scanme item c{i:04d}"}))
                for i in range(count)
            ],
        )
        conn.commit()


def test_r5_recall_page_does_not_retokenize_each_trial_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = TypedArtifactStore(tmp_path)
    _seed_bulk(store, 512)
    calls = _count_calls(monkeypatch, retrieval, "_count_tokens")
    page = recall_page(
        store,
        subject="domain_knowledge",
        query="scanme",
        session_allowlist=["allowed"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
    )
    assert len(page["items"]) == 512
    assert len(calls) <= 3


def _old_budget_loop(
    candidates: list[dict[str, Any]], *, max_bytes: int, max_tokens: int, limit: int
) -> list[dict[str, Any]]:
    """The pre-TS selection loop, verbatim: every trial page fully measured."""
    items: list[dict[str, Any]] = []
    for item in candidates:
        trial_bytes, trial_tokens = retrieval._measure_page(
            [*items, item], None, True, "cl100k_base"
        )
        if trial_bytes > max_bytes or trial_tokens > max_tokens:
            break
        items.append(item)
        if len(items) >= limit:
            break
    return items


_TEXTS = [
    "plain ascii needle words",
    "needle naïve café résumé ünïcödé",
    "needle 漢字かな交じり文 with CJK",
    'needle emoji-free symbols ∑∫√≈ and quotes " and \\ backslashes',
    "needle " + "long " * 60,
    "needle tab\tand newline\nescaped",
]


def _seed_varied(store: TypedArtifactStore, count: int) -> None:
    for i in range(count):
        _write_memory(store, f"v{i:03d}", f"{_TEXTS[i % len(_TEXTS)]} #{i}")


_BUDGETS = [
    (bytes_, tokens)
    for bytes_ in (120, 400, 900, 2_000, 8_192, 50_000)
    for tokens in (40, 150, 400, 2_048, 50_000)
]


def test_r5_recall_page_matches_the_old_loop_across_budgets(tmp_path: Path) -> None:
    store = TypedArtifactStore(tmp_path)
    _seed_varied(store, 40)
    full = recall_page(
        store,
        subject="domain_knowledge",
        query="needle",
        session_allowlist=["allowed"],
        limit=10_000,
        max_tokens=1_000_000,
        max_bytes=1_000_000,
    )
    assert len(full["items"]) == 40
    for max_bytes, max_tokens in _BUDGETS:
        page = recall_page(
            store,
            subject="domain_knowledge",
            query="needle",
            session_allowlist=["allowed"],
            limit=10_000,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
        )
        if page["code"] == "E_BUDGET":
            continue
        expected = _old_budget_loop(
            full["items"], max_bytes=max_bytes, max_tokens=max_tokens, limit=10_000
        )
        assert page["items"] == expected, (max_bytes, max_tokens)
        assert (page["bytes"], page["tokens"]) == retrieval._measure_page(
            expected, page["next_cursor"], page["complete"], "cl100k_base"
        )


def _any_vector(_config: Any, chunks: Any) -> list[list[float]]:
    return [[1.0, float(len(chunk) % 7) + 1.0] for chunk in chunks]


def test_r5_hybrid_page_matches_the_old_loop_across_budgets(tmp_path: Path) -> None:
    from rush.memory.embeddings import EmbeddingConfig

    config = EmbeddingConfig(
        endpoint="http://fake-embed.invalid", model="fake", model_digest="d1"
    )
    store = TypedArtifactStore(tmp_path)
    _seed_varied(store, 40)

    def _page(max_bytes: int, max_tokens: int) -> dict[str, Any]:
        return hybrid_page(
            store,
            subject="domain_knowledge",
            query="needle",
            session_allowlist=["allowed"],
            embed_config=config,
            embed_fn=_any_vector,
            limit=10_000,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
        )

    full = _page(1_000_000, 1_000_000)
    assert full["retrieval"] == "hybrid"
    assert len(full["items"]) == 40
    for max_bytes, max_tokens in _BUDGETS:
        page = _page(max_bytes, max_tokens)
        expected = _old_budget_loop(
            full["items"], max_bytes=max_bytes, max_tokens=max_tokens, limit=10_000
        )
        assert page["items"] == expected, (max_bytes, max_tokens)


@pytest.mark.parametrize("max_bytes", [150, 1_000_000])
def test_r5_special_token_content_raises_the_same_value_error(
    tmp_path: Path, max_bytes: int
) -> None:
    """keep-green: tiktoken refuses special-token text; the page must raise
    exactly as the fully-tokenizing loop did, even when the byte budget
    alone would have excluded the item."""
    store = TypedArtifactStore(tmp_path)
    _write_memory(store, "s1", "needle " + "<|endoftext|>" + " tail " * 20)
    with pytest.raises(ValueError, match="special token"):
        recall_page(
            store,
            subject="domain_knowledge",
            query="needle",
            session_allowlist=["allowed"],
            limit=10_000,
            max_tokens=1_000_000,
            max_bytes=max_bytes,
        )


# --- R6: the operations inventory reuses the module-level MCP server --------


def test_r6_operations_inventory_does_not_build_a_second_mcp_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rush.mcp as mcp_module
    from rush.governance import public_operations

    def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("build_operations_inventory built another MCP server")

    monkeypatch.setattr(mcp_module, "build_server", _forbidden)
    monkeypatch.setattr(public_operations, "build_server", _forbidden, raising=False)
    inventory = public_operations.build_operations_inventory()
    assert any(op.mcp_tool == "rush_lint" for op in inventory)


# --- R7: the coverage manifest -----------------------------------------------


def test_r7_build_manifest_classifies_this_checkout() -> None:
    from rush.governance.coverage_manifest import build_manifest

    manifest = build_manifest(PROJECT_ROOT, revision="ts")
    paths = {record.path for record in manifest.records}
    assert "pyproject.toml" in paths
    assert not any(path.startswith(".scratch/") for path in paths)


def test_r7_every_checked_in_manifest_record_exists() -> None:
    data = tomllib.loads(
        (PROJECT_ROOT / "governance" / "first-party-coverage.toml").read_text(
            encoding="utf-8"
        )
    )
    missing = [
        record["path"]
        for record in data["records"]
        if not (PROJECT_ROOT / record["path"]).exists()
    ]
    assert missing == []


# --- R1: hermetic engine PATH ------------------------------------------------


def test_r1_hermetic_path_hides_host_engines_and_restores_on_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import _hermetic_engine_path

    host_bin = tmp_path / "host-bin"
    host_bin.mkdir()
    fake = host_bin / "rush-ts-fake-engine"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{host_bin}{os.pathsep}{os.environ['PATH']}")
    original_path = os.environ["PATH"]
    assert resolve_binary("rush-ts-fake-engine") == str(fake)

    with _hermetic_engine_path(tmp_path / "hermetic-bin"):
        assert resolve_binary("rush-ts-fake-engine") is None
        assert resolve_binary("git") is not None
        ruff = resolve_binary("ruff")
        assert ruff is not None
        assert Path(ruff).parent == Path(sys.prefix) / (
            "Scripts" if os.name == "nt" else "bin"
        )

    assert os.environ["PATH"] == original_path
    assert resolve_binary("rush-ts-fake-engine") == str(fake)


# --- R2: a test may not leave an HTTP server serving -------------------------


def test_r2_guard_fails_a_test_that_closes_without_shutdown(
    pytester: pytest.Pytester,
) -> None:
    from conftest import _LEFT_SERVING

    pytester.makeconftest(_CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(
        test_servers="""
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


        def _serve():
            server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            return server


        def test_close_only():
            _serve().server_close()


        def test_shutdown_then_close():
            server = _serve()
            server.shutdown()
            server.server_close()
        """
    )
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    result.assert_outcomes(passed=2, errors=1)
    result.stdout.fnmatch_lines(
        [
            "*ERROR at teardown of test_close_only*",
            f"*{_LEFT_SERVING}*",
        ]
    )


# --- R1b: the staging-failure test proves its property -----------------------


def test_r1b_dropping_staging_failures_fails_the_staging_test(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_project_run_lifecycle import (
        test_staging_failure_never_falls_back_to_a_live_read_and_never_publishes_a_clean_result as _staging_test,
    )

    real = project_run._finalize_attempt

    def _mutant(**kwargs: Any) -> Any:
        return real(**{**kwargs, "staging_failures": None})

    monkeypatch.setattr(project_run, "_finalize_attempt", _mutant)
    with pytest.raises(AssertionError):
        _staging_test(tmp_path, monkeypatch)


# --- C2: lingering close covers every early rejection -------------------------


def _limits_server(tmp_path: Path) -> tuple[Any, str, int]:
    server, ctx, _token = create_dashboard_server(
        {"project-a": _snapshot("project-a", tmp_path, [])},
        data_root=tmp_path / "rush-data",
    )
    _serve(server)
    return server, ctx.launch_origin, ctx.bound_port


def test_c2_oversized_and_chunked_posts_always_get_their_error(
    tmp_path: Path,
) -> None:
    server, base_url, _port = _limits_server(tmp_path)
    url = f"{base_url}/api/projects/project-a/actions"
    headers = {"Origin": base_url, "Content-Type": "application/json"}
    oversized = json.dumps({"padding": "x" * (257 * 1024)}).encode()
    try:
        for _ in range(50):
            assert _post(url, headers=headers, body=oversized).status == 413
            chunked = _post(
                url,
                headers={**headers, "Transfer-Encoding": "chunked"},
                body=b'{"operation": "noop"}',
            )
            assert chunked.status == 400
    finally:
        server.shutdown()
        server.server_close()


def _declare_huge_body(port: int) -> tuple[socket.socket, int]:
    sock = socket.create_connection(("127.0.0.1", port), timeout=5)
    head = (
        "POST /api/projects/project-a/actions HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{port}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {100 * 1024 * 1024}\r\n\r\n"
    ).encode("ascii")
    sock.sendall(head)
    return sock, len(head)


def _status_line(response: bytes) -> bytes:
    return response.split(b"\r\n", 1)[0]


def test_c2_trickled_oversized_body_is_cut_off_by_the_linger_deadline(
    tmp_path: Path,
) -> None:
    server, _base_url, port = _limits_server(tmp_path)
    sock, _head = _declare_huge_body(port)
    response = b""
    cut_off: float | None = None
    start = time.monotonic()
    try:
        while time.monotonic() - start < 8.0:
            try:
                sock.sendall(b"x" * 1024)
                if select.select([sock], [], [], 0)[0]:
                    response += sock.recv(65536)
            except OSError:
                cut_off = time.monotonic() - start
                break
            time.sleep(0.05)
    finally:
        sock.close()
        server.shutdown()
        server.server_close()
    assert b" 413 " in _status_line(response), response[:200]
    assert cut_off is not None, "a trickling client was never cut off"
    assert cut_off <= server_module._LINGER_SECONDS + 1.0


def test_c2_fast_oversized_body_is_discarded_only_up_to_the_byte_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, _base_url, port = _limits_server(tmp_path)
    sock, head = _declare_huge_body(port)
    client_port = sock.getsockname()[1]
    server_read = [0]
    real_recv_into = socket.socket.recv_into

    def _counting_recv_into(self: socket.socket, *args: Any, **kwargs: Any) -> int:
        count = real_recv_into(self, *args, **kwargs)
        try:
            peer_port = self.getpeername()[1]
        except OSError:
            peer_port = None
        if count and peer_port == client_port:
            server_read[0] += count
        return count

    monkeypatch.setattr(socket.socket, "recv_into", _counting_recv_into)
    response = b""
    start = time.monotonic()
    cut_off: float | None = None
    chunk = b"x" * (64 * 1024)
    try:
        for _ in range(20 * 1024 * 1024 // len(chunk)):
            try:
                sock.sendall(chunk)
                if select.select([sock], [], [], 0)[0]:
                    response += sock.recv(65536)
            except OSError:
                cut_off = time.monotonic() - start
                break
    finally:
        sock.close()
        server.shutdown()
        server.server_close()
    assert b" 413 " in _status_line(response), response[:200]
    assert cut_off is not None and cut_off <= server_module._LINGER_SECONDS + 1.0
    assert server_read[0] <= (
        head + server_module._LINGER_MAX_BYTES + io.DEFAULT_BUFFER_SIZE
    )
    assert server_module._LINGER_MAX_BYTES == 4 * MAX_BODY_BYTES


# --- release artifacts are built per session from the current source --------

_ARTIFACT_TEST_FILES = (
    "test_phase52_installed_artifacts.py",
    "test_release_asset_contract.py",
)


def test_artifact_tests_never_read_the_repo_dist_dir() -> None:
    """A stale gitignored `dist/` (e.g. built before T2's agent assets) must
    be unable to make an installed-artifact test pass or fail: those tests
    read only the session-built artifacts, never a `"dist"` path."""
    for name in _ARTIFACT_TEST_FILES:
        module = ast.parse((Path(__file__).parent / name).read_text(encoding="utf-8"))
        uses = [
            node.lineno
            for node in ast.walk(module)
            if isinstance(node, ast.Constant) and node.value == "dist"
        ]
        assert uses == [], f"{name} reads dist/ at lines {uses}"


def test_release_artifacts_are_built_from_current_source(
    distribution_artifacts: tuple[Path, Path], native_release_archive: Path
) -> None:
    import rush
    from scripts.probe_installed_artifacts import (
        AGENT_ASSET_MEMBERS,
        verify_archive_checksum,
    )

    wheel, sdist = distribution_artifacts
    checksums = native_release_archive.parent / "SHA256SUMS"
    repo_dist = PROJECT_ROOT / "dist"
    for artifact in (wheel, sdist, native_release_archive, checksums):
        assert artifact.is_file()
        assert not artifact.resolve().is_relative_to(repo_dist.resolve())
    with zipfile.ZipFile(wheel) as zf:
        members = set(zf.namelist())
        metadata = zf.read(f"rush_cli-{rush.__version__}.dist-info/METADATA")
    assert set(AGENT_ASSET_MEMBERS) <= members
    assert f"Version: {rush.__version__}".encode() in metadata
    assert verify_archive_checksum(native_release_archive, checksums)
