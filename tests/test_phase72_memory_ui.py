"""72-T07: complete user memory search, correction and explanation (CLI, TUI, server).

Design gate: `phase72-gates/72-T07.md` (brief, Pre-gate addendum, G1 re-gate addendum).
Every test imports the symbols a task adds (`memory_ui_state`, `memory_view_authority`,
T05/T06/CODEC/BOOTSTRAP producers) inside its own body, so this module collects at HEAD
and each test fails on its own until its producer lands. The module-level imports below
are existing code only.

Real keys, real stores, real grants: nothing here fabricates a result. A fake
`memory_run` is used only to record the calls the real `MemoryTool` still serves, or (R6)
to hold one request in flight.
"""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import hashlib
import io
import itertools
import json
import os
import re
import select
import sqlite3
import struct
import threading
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast, get_args
from urllib.parse import urlencode

import pytest
from click.testing import CliRunner
from rich.console import Console

from rush.cli import cli
from rush.memory import authorization as auth
from rush.memory.store import (
    MemoryArtifact,
    MemorySubject,
    OwnerScope,
    TypedArtifactStore,
    readonly_view_reason,
)
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.tools.memory import MemoryTool
from rush.tui import (
    ProjectState,
    TuiState,
    _dispatch_key,
    _pump,
    default_scan_actions,
    project_key,
    render_app,
)
from rush.workflows.projects import register_project

SUBJECTS = tuple(get_args(MemorySubject))
SUBJECT = "domain_knowledge"
SOURCE = "t07-src"
ALICE = OwnerScope("user", "alice")
BOB = OwnerScope("user", "bob")
GRANT_OPS = ("ask", "expand", "list", "history", "write")
FAMILY = {
    "active_context": "handoff",
    "episodic": "experience",
    "preference": "memory",
    "failure": "memory",
    "architectural_decision": "memory",
    "domain_knowledge": "memory",
    "skill_pattern": "skill",
}
# The terminal-hostile payload of R15/R16: erase-line, a lone CR, BEL and a bidi override.
HOSTILE = "\x1b[2K\r\x07\u202e"
HOSTILE_ESCAPES = ("\\x1b[2K", "\\x0d", "\\x07", "\\u202e")
SGR = re.compile(r"\x1b\[[0-9;]*m")
V2_KEYS = frozenset(
    {
        "schema_version",
        "operation",
        "code",
        "items",
        "next_cursor",
        "complete",
        "unknowns",
        "data",
    }
)


# --- world: a registered project, two owners, seven subjects, an optional grant ----


@dataclasses.dataclass
class World:
    root: Path
    data_root: Path
    project_id: str
    store: TypedArtifactStore
    grant: dict[str, Any] | None = None
    ids: dict[tuple[str, str], str] = dataclasses.field(default_factory=dict)

    def db_sha(self) -> str:
        return hashlib.sha256(
            (self.root / ".rush" / "memory.db").read_bytes()
        ).hexdigest()

    def alice(self, subject: str = SUBJECT) -> str:
        return self.ids[("alice", subject)]

    def bob(self, subject: str = SUBJECT) -> str:
        return self.ids[("bob", subject)]


def _write(
    store: TypedArtifactStore,
    artifact_id: str,
    owner: OwnerScope,
    subject: str,
    text: str,
    *,
    source: str = SOURCE,
    trust: str = "EXTERNAL_WRITE",
    content: dict[str, Any] | None = None,
) -> MemoryArtifact:
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family=FAMILY[subject],  # type: ignore[arg-type]
            subject=subject,  # type: ignore[arg-type]
            trust_tier=trust,  # type: ignore[arg-type]
            content=content if content is not None else {"text": text},
            source=source,
            created_at=time.time(),
            owner_scope=owner,
        )
    )


def _revision() -> int:
    return int(
        auth.load_policy_readonly(data_root=default_data_root())["policy_revision"] or 0
    )


def _grant(
    root: Path,
    owner: OwnerScope = ALICE,
    *,
    sources: tuple[str, ...] = (SOURCE,),
    ops: tuple[str, ...] = GRANT_OPS,
    expires_at: float | None = None,
) -> dict[str, Any]:
    data_root = default_data_root()
    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=_revision(),
        consent=True,
        expires_at=expires_at,
        data_root=data_root,
    )


def _revoke(world: World) -> None:
    assert world.grant is not None
    auth.revoke_memory_scope(
        grant_id=world.grant["grant_id"],
        expected_policy_revision=_revision(),
        consent=True,
        data_root=world.data_root,
    )


def _world(
    tmp_path: Path,
    *,
    grant: bool = True,
    ops: tuple[str, ...] = GRANT_OPS,
    extra_domain: int = 0,
    hostile: bool = False,
    expires_at: float | None = None,
    name: str = "project",
) -> World:
    """One registered project: for each of the seven subjects one Alice and one Bob row
    (source `t07-src`, content `{"text": "needle <subject> <owner>"}`), `extra_domain`
    more Alice `domain_knowledge` rows (`alice-dk-NN`), an optional hostile Alice row and,
    with `grant`, an Alice grant over `t07-src`."""
    data_root = default_data_root()
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    record = register_project(root, data_root=data_root)
    store = TypedArtifactStore(root)
    world = World(root, data_root, record.project_id, store)
    for subject in SUBJECTS:
        for label, owner in (("alice", ALICE), ("bob", BOB)):
            artifact_id = f"{label}-{subject}"
            # 72-T01 D33: an unanchored `episodic` row with no `kind` is `unknown`, not
            # usable as current (so not expandable); `observation` is `not_applicable`.
            _write(
                store,
                artifact_id,
                owner,
                subject,
                f"needle {subject} {label}",
                content={"kind": "observation", "text": f"needle {subject} {label}"}
                if subject == "episodic"
                else None,
            )
            world.ids[(label, subject)] = artifact_id
    for index in range(extra_domain):
        _write(store, f"alice-dk-{index:02d}", ALICE, SUBJECT, f"needle extra {index}")
    if hostile:
        _write(
            store,
            "alice-hostile",
            ALICE,
            SUBJECT,
            "",
            content={"text": f"{HOSTILE} hostilemarker"},
        )
        world.ids[("alice", "hostile")] = "alice-hostile"
    if grant:
        world.grant = _grant(root, ops=ops, expires_at=expires_at)
    return world


def _tree(
    base: Path, skip: tuple[str, ...] = ("dashboard", "owners")
) -> dict[str, str]:
    """Every file under `base` (relative path -> sha256); `{}` when it does not exist.
    A dashboard server keeps its own mutation ledger under `<data root>/dashboard`, which
    is not memory state, and `owners/` holds the empty owner locks any server or UI
    takes, so those subtrees are skipped by default."""
    if not base.exists():
        return {}
    return {
        str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(base.rglob("*"))
        if p.is_file()
        and not p.is_symlink()
        and p.relative_to(base).parts[0] not in skip
    }


def _scrub(value: Any) -> Any:
    """`value` without the volatile `duration_ms` keys, for equality against MemoryTool."""
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items() if k != "duration_ms"}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _raw(result: Any) -> dict[str, Any]:
    raw = result.get("raw") if hasattr(result, "get") else None
    return raw if isinstance(raw, dict) else {}


def _code(result: Any) -> Any:
    return _raw(result).get("code")


def _reason(result: Any) -> Any:
    raw = _raw(result)
    data: dict[str, Any] = raw["data"] if isinstance(raw.get("data"), dict) else {}
    return raw.get("reason") or data.get("reason")


def _identity(item: dict[str, Any]) -> tuple[str, int]:
    """(artifact id, version) of one list row, read from the canonical `reference` and
    falling back to the flat keys a TUI row may keep."""
    ref = item.get("reference")
    if isinstance(ref, dict) and "artifact_id" in ref:
        return ref["artifact_id"], ref["artifact_version"]
    return item["id"], cast(int, item.get("artifact_version", item.get("version")))


def _pairs(items: list[dict[str, Any]]) -> list[tuple[str, int]]:
    return [_identity(item) for item in items]


def _oracle(
    world: World,
    operation: str,
    request: dict[str, Any],
    *,
    permissions: ExecutionPermissions | None = None,
) -> Any:
    """What `MemoryTool` itself returns for the same request: the contract every
    transport must equal."""
    kwargs: dict[str, Any] = {"operation": operation, "request": request}
    if permissions is not None:
        kwargs["permissions"] = permissions
    return MemoryTool().run(world.root, **kwargs)


def _list_request(
    subjects: list[str] | None = None, query: str = "", **extra: Any
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "subjects": list(subjects if subjects is not None else SUBJECTS),
        "query": query,
        **extra,
    }


def _oracle_list(
    world: World, subjects: list[str] | None = None, query: str = "", **extra: Any
) -> Any:
    return _oracle(world, "list", _list_request(subjects, query, **extra))


def _all_pages(world: World, subject: str, query: str = "") -> list[tuple[str, int]]:
    """Every (id, version) MemoryTool lists for one subject, following `next_cursor`."""
    out: list[tuple[str, int]] = []
    cursor: str | None = None
    for _ in range(50):
        extra = {} if cursor is None else {"cursor": cursor}
        raw = _raw(_oracle_list(world, [subject], query, **extra))
        assert raw.get("code") == "OK", raw
        out.extend(_pairs(raw["items"]))
        cursor = raw.get("next_cursor")
        if cursor is None:
            return out
    raise AssertionError("list never completed")


# --- CLI harness --------------------------------------------------------------


@dataclasses.dataclass
class Cli:
    exit_code: int
    stdout: str
    output: str
    json: dict[str, Any] | None
    exception: BaseException | None = None


def _cli(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    *args: str,
    json_mode: bool = False,
) -> Cli:
    monkeypatch.chdir(world.root)
    argv = [*args, *(["--json"] if json_mode else [])]
    result = CliRunner().invoke(cli, argv)
    payload = None
    if json_mode:
        with contextlib.suppress(ValueError):
            payload = json.loads(result.stdout)
    return Cli(
        result.exit_code, result.stdout, result.output, payload, result.exception
    )


def _input_file(tmp_path: Path, name: str, body: dict[str, Any]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _spy_memory_tool(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every `MemoryTool.run` call (kwargs only) while still serving it."""
    calls: list[dict[str, Any]] = []
    real = MemoryTool.run

    def _run(self: MemoryTool, root: Path, *args: Any, **kwargs: Any) -> Any:
        calls.append({"root": root, **kwargs})
        return real(self, root, *args, **kwargs)

    monkeypatch.setattr(MemoryTool, "run", _run)
    return calls


# --- TUI harness ---------------------------------------------------------------


class Recorder:
    """`actions.memory_run` that records each call and serves it with the real tool."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, root: Path, **kwargs: Any) -> Any:
        self.calls.append({"root": root, **kwargs})
        return MemoryTool().run(root, **kwargs)

    def applies(self) -> list[dict[str, Any]]:
        return [
            c
            for c in self.calls
            if isinstance(c.get("request"), dict) and c["request"].get("apply") is True
        ]

    def of(self, operation: str) -> list[dict[str, Any]]:
        return [c for c in self.calls if c.get("operation") == operation]


def _actions(run: Callable[..., Any]) -> Any:
    return dataclasses.replace(default_scan_actions(), memory_run=run)


def _tui(
    world: World,
    run: Callable[..., Any] | None = None,
    *,
    owner: tuple[str, str] = ("user", "alice"),
) -> tuple[TuiState, Any, Recorder]:
    recorder = run if isinstance(run, Recorder) else Recorder()
    actions = _actions(run if run is not None else recorder)
    state = TuiState(
        projects=[
            ProjectState(name="t07", root=world.root, project_id=world.project_id)
        ],
        data_root=world.data_root,
    )
    state.memory_owner_scope_kind, state.memory_owner_scope_id = owner
    state.terminal_size = (160, 50)
    return state, actions, recorder  # type: ignore[return-value]


def _settle(state: TuiState, actions: Any, seconds: float = 5.0) -> None:
    deadline = time.monotonic() + seconds
    _pump(state, actions)
    while state.memory_request is not None:
        assert time.monotonic() < deadline, f"still in flight: {state.memory_request}"
        time.sleep(0.005)
        _pump(state, actions)


def _keys(state: TuiState, actions: Any, *keys: str) -> None:
    for key in keys:
        _dispatch_key(state, key, actions)
        _settle(state, actions)


def _type(state: TuiState, actions: Any, text: str) -> None:
    _keys(state, actions, *list(text))


def _render(state: TuiState, width: int = 160, height: int = 50) -> str:
    state.terminal_size = (width, height)
    console = Console(record=True, width=width, height=height, file=io.StringIO())
    console.print(render_app(state))
    return console.export_text()


def _open_memory(state: TuiState, actions: Any) -> None:
    _keys(state, actions, "f3", "4")
    assert state.mode == "memory", state.mode


def _tui_ids(state: TuiState) -> list[tuple[str, int]]:
    return _pairs(state.memory_items)


def _to_subject(state: TuiState, actions: Any, subject: str) -> None:
    for _ in range(len(SUBJECTS)):
        if state.memory_subject == subject:
            return
        _keys(state, actions, "S")
    raise AssertionError(f"S never reached {subject}")


# --- dashboard harness ---------------------------------------------------------


def _serve(server: Any) -> threading.Thread:
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    return thread


def _http(
    method: str, url: str, headers: dict[str, str] | None = None, body: bytes = b""
) -> Any:
    request = urllib.request.Request(
        url,
        data=body if method == "POST" else None,
        headers=headers or {},
        method=method,
    )
    try:
        return urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as exc:
        return exc


@dataclasses.dataclass
class Dash:
    server: Any
    ctx: Any
    base: str
    cookie: str
    csrf: str
    project_id: str

    def snapshot(self, section: str, **query: str) -> tuple[int, dict[str, Any]]:
        qs = urlencode({"section": section, **query})
        resp = _http(
            "GET",
            f"{self.base}/api/projects/{self.project_id}/snapshot?{qs}",
            {"Cookie": self.cookie},
        )
        return resp.status, json.loads(resp.read())

    def action(
        self,
        operation: str,
        arguments: dict[str, Any] | None = None,
        *,
        grants: dict[str, Any] | None = None,
        project_id: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body = json.dumps(
            {
                "schema_version": 1,
                "operation": operation,
                "arguments": arguments or {},
                "grants": grants or {},
                "expected": {},
                "request_id": str(uuid.uuid4()),
            }
        ).encode("utf-8")
        resp = _http(
            "POST",
            f"{self.base}/api/projects/{project_id or self.project_id}/actions",
            {
                "Cookie": self.cookie,
                "X-Rush-CSRF": self.csrf,
                "Origin": self.base,
                "Content-Type": "application/json",
            },
            body,
        )
        return resp.status, json.loads(resp.read())

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _dashboard(*worlds: World) -> Dash:
    from rush.dashboard.server import create_dashboard_server

    first = worlds[0]
    snapshots = {
        w.project_id: {
            "schema_version": 1,
            "project_id": w.project_id,
            "source_identity": str(w.root),
            "root": str(w.root),
            "files": [],
            "findings": [],
            "memories": [],
            "agents": [],
        }
        for w in worlds
    }
    server, ctx, token = create_dashboard_server(snapshots, data_root=first.data_root)
    _serve(server)
    base = ctx.launch_origin
    resp = _http("POST", f"{base}/api/session", {"Authorization": f"Bearer {token}"})
    assert resp.status == 200
    payload = json.loads(resp.read())
    cookie = resp.headers.get("Set-Cookie").split(";")[0]
    return Dash(server, ctx, base, cookie, payload["csrf_token"], first.project_id)


WRITE = {"cache_write": True, "artifact_write": True}


# =============================================================================
# R1 -- CLI `rush memory list`
# =============================================================================

_FIXTURE_ROWS = Path(__file__).parent / "fixtures" / "phase70" / "cli-outcomes.json"


def test_t07_cli_list_optional_subject_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(tmp_path, extra_domain=24)
    calls = _spy_memory_tool(monkeypatch)

    # (a) usage: SUBJECT and QUERY are optional positionals, every option is declared.
    helped = _cli(world, monkeypatch, "memory", "list", "--help")
    assert helped.exit_code == 0, helped.output
    usage = re.sub(r"\s+", "", helped.stdout.split("Options:")[0])
    assert "[{active_context|" in usage and "[QUERY]" in usage, helped.stdout
    for option in (
        "--subject",
        "--query",
        "--owner",
        "--source",
        "--session",
        "--cursor",
        "--include-archived",
        "--json",
    ):
        assert option in helped.stdout, (option, helped.stdout)
    assert calls == []

    # (c) every accepted form calls MemoryTool().run(root, operation="list", request=R)
    # exactly once with the schema-2 request R and no legacy argument.
    base = {"schema_version": 2, "subjects": list(SUBJECTS), "query": ""}
    forms: list[tuple[tuple[str, ...], dict[str, Any]]] = [
        ((), {}),
        (("domain_knowledge",), {"subjects": ["domain_knowledge"]}),
        (
            ("domain_knowledge", "needle"),
            {"subjects": ["domain_knowledge"], "query": "needle"},
        ),
        (("--query", "needle"), {"query": "needle"}),
        (
            ("--subject", "failure", "--subject", "episodic", "--query", "q"),
            {"subjects": ["failure", "episodic"], "query": "q"},
        ),
        (("--subject", "failure", "--subject", "failure"), {"subjects": ["failure"]}),
        (
            ("--owner", "user:alice"),
            {"owner_scope": {"kind": "user", "id": "alice"}},
        ),
        (
            ("--owner", "agent:a:b"),
            {"owner_scope": {"kind": "agent", "id": "a:b"}},
        ),
        (("--source", "s1", "--session", "s2"), {"sources": ["s1", "s2"]}),
        (("--source", "s1", "--source", "s1"), {"sources": ["s1"]}),
        (("--cursor", "abc"), {"cursor": "abc"}),
        (("--include-archived",), {"archive_mode": "historical"}),
    ]
    for args, delta in forms:
        calls.clear()
        _cli(world, monkeypatch, "memory", "list", *args, json_mode=True)
        assert len(calls) == 1, (args, calls)
        call = calls[0]
        assert call["operation"] == "list", args
        assert call["request"] == {**base, **delta}, (args, call["request"])
        for legacy in (
            "subject",
            "query",
            "session_allowlist",
            "include_archived",
            "owner_scope",
            "task_id",
        ):
            assert legacy not in call, (args, legacy)

    # (a) a positional plus its option for the same field is a usage error (exit 2),
    # before MemoryTool is touched.
    for args, message in (
        (("domain_knowledge", "--subject", "failure"), "give the subject once"),
        (
            ("domain_knowledge", "needle", "--subject", "failure"),
            "give the subject once",
        ),
        (("domain_knowledge", "needle", "--query", "x"), "give the query once"),
    ):
        calls.clear()
        result = _cli(world, monkeypatch, "memory", "list", *args)
        assert result.exit_code == 2, (args, result.output)
        assert message in result.output, (args, result.output)
        assert calls == [], args
    # (b) a malformed owner is a BadParameter naming --owner.
    for owner in ("robot:x", "user", "user:", "user: ", ":x", "session:   "):
        calls.clear()
        result = _cli(world, monkeypatch, "memory", "list", "--owner", owner)
        assert result.exit_code == 2, (owner, result.output)
        assert "--owner" in result.output and "KIND:ID" in result.output, result.output
        assert calls == [], owner
    for args in (("nonsense",), ("--subject", "nonsense")):
        calls.clear()
        result = _cli(world, monkeypatch, "memory", "list", *args)
        assert result.exit_code == 2, (args, result.output)
        assert calls == [], args

    # (d) policy mode, no arguments: the seven subjects are browsed (a project holding
    # one row per subject and owner, so one page holds them all); the JSON items equal
    # MemoryTool's for the same request; every item carries `reference`; the page names
    # next_cursor and complete.
    seven = _world(tmp_path, name="seven")
    calls.clear()
    listed = _cli(seven, monkeypatch, "memory", "list", json_mode=True)
    assert listed.exit_code == 0, listed.output
    assert listed.json is not None
    oracle = _raw(_oracle_list(seven))
    assert _scrub(listed.json["raw"]["items"]) == _scrub(oracle["items"])
    assert {"next_cursor", "complete"} <= set(listed.json["raw"])
    assert listed.json["raw"]["code"] == "OK"
    assert listed.json["raw"]["complete"] is True
    assert all("reference" in item for item in listed.json["raw"]["items"])
    shown = {_identity(i)[0] for i in listed.json["raw"]["items"]}
    assert shown == {seven.alice(s) for s in SUBJECTS}, shown
    assert not any(seven.bob(s) in listed.stdout for s in SUBJECTS), "Bob's rows leaked"
    # With more rows than one page, the same call names its next page.
    paged = _cli(world, monkeypatch, "memory", "list", json_mode=True)
    assert paged.json is not None and paged.json["raw"]["complete"] is False
    assert isinstance(paged.json["raw"]["next_cursor"], str)

    # Page / inspect / history / related / correction hints in the human output, and a
    # second page by --cursor that continues without repeats.
    first = _cli(
        world, monkeypatch, "memory", "list", "--subject", SUBJECT, json_mode=True
    )
    assert first.json is not None
    page1 = first.json["raw"]
    assert page1["complete"] is False and isinstance(page1["next_cursor"], str)
    human = _cli(world, monkeypatch, "memory", "list", "--subject", SUBJECT)
    assert f"next page: rerun with --cursor {page1['next_cursor']}" in human.stdout
    for hint in (
        "inspect: rush memory expand --input FILE",
        "history: rush memory history",
        "related: rush memory related --input FILE",
        "explain: rush memory explain",
        "correct: rush memory edit --input FILE",
    ):
        assert hint in human.stdout, (hint, human.stdout)
    assert re.search(
        r"alice-\S+@v1\s+subject domain_knowledge\s+owner user:alice\s+"
        r"source t07-src\s+trust EXTERNAL_WRITE\s+freshness \S+",
        human.stdout,
    ), human.stdout
    assert re.search(r"cite alice-\S+@v1 sha256:[0-9a-f]{64}", human.stdout), (
        human.stdout
    )
    second = _cli(
        world,
        monkeypatch,
        "memory",
        "list",
        "--subject",
        SUBJECT,
        "--cursor",
        page1["next_cursor"],
        json_mode=True,
    )
    assert second.json is not None and second.json["raw"]["code"] == "OK"
    seen = [_identity(i) for i in page1["items"] + second.json["raw"]["items"]]
    assert len(seen) == len(set(seen)), "a page repeated a row"
    assert seen == _all_pages(world, SUBJECT)[: len(seen)]

    # (e) legacy mode (no policy, no D1 marker): v2 list without a source is the D1
    # fail-closed denial, fail/exit 1, with a concrete next step; a named source lists.
    legacy_world = _world(tmp_path, grant=False, name="legacy_world")
    denied = _cli(legacy_world, monkeypatch, "memory", "list", json_mode=True)
    assert denied.exit_code == 1, denied.output
    assert denied.json is not None
    assert denied.json["status"] == "fail", denied.json
    assert denied.json["raw"]["code"] == "E_PERMISSION"
    assert denied.json["raw"]["data"]["reason"] == "policy_missing"
    human_denied = _cli(legacy_world, monkeypatch, "memory", "list")
    for text in ("memory fail", "state: denied", "action:"):
        assert text in human_denied.output, (text, human_denied.output)
    sourced = _cli(
        legacy_world, monkeypatch, "memory", "list", "--source", SOURCE, json_mode=True
    )
    assert sourced.json is not None and sourced.json["raw"]["code"] == "OK"
    assert _scrub(sourced.json["raw"]["items"]) == _scrub(
        _raw(_oracle_list(legacy_world, sources=[SOURCE]))["items"]
    )

    # (f) the Phase 70 CLI outcome row becomes the no-argument browse.
    rows = json.loads(_FIXTURE_ROWS.read_text(encoding="utf-8"))
    row = next(r for r in rows if r["id"] == "memory.list")
    assert row["empty"]["argv"] == ["memory", "list"], row["empty"]
    for kind in ("expect", "empty"):
        spec = row[kind]
        assert spec["json_paths"]["tool"] == "memory", kind
        assert spec["json_paths"]["status"] == "fail", kind
        assert spec["json_paths"]["raw.code"] == "E_PERMISSION", kind
        assert spec["json_paths"]["raw.data.reason"] == "policy_missing", kind
        assert spec["exit"] == 1, kind
        for text in ("memory fail", "state: denied", "action:"):
            assert text in spec["human_contains"], (kind, text)
    assert row["failure"]["argv"][:3] == ["memory", "list", "nonsense"]
    assert row["failure"]["exit"] == 2


# =============================================================================
# R2 -- the UI-state classifier
# =============================================================================

STATE_ACTIONS: dict[str, str] = {
    "server_error": "retry the request; if it fails again run rush doctor",
    "absent": (
        "no memory store yet: record one with rush memory write SUBJECT SOURCE "
        "--content JSON --allow-cache-write"
    ),
    "migration_required": (
        "run any rush memory write command to migrate the store, then refresh"
    ),
    "corrupt": "move .rush/memory.db aside or restore it from a backup, then refresh",
    "busy": "a writer holds the store; retry in a moment",
    "conflict": (
        "the record changed since you reviewed it; refresh, review the current "
        "version, then apply again"
    ),
    "restart": "access changed during the request; refresh to restart from the first page",
    "partial": "more results exist: open the next page",
    "not_visible": (
        "the record is not visible to your grant (deleted, archived, expired or "
        "another owner); refresh the list"
    ),
    "invalid": "fix the field named in the reason and retry",
    "revoked": (
        "the grant was revoked; ask the project owner to grant memory access again "
        "(rush memory grant)"
    ),
    "expired": "the grant expired; renew it with rush memory grant --expires-at TIME",
    "denied": "request access with rush memory grant",
    "digest_mismatch": (
        "content bytes do not match the recorded payload hash; content withheld; "
        "refresh and expand again"
    ),
    "empty": "no records match; change the subject, query or filters",
    "ok": "select a record to inspect, see history or correct it",
}
SKIPPED_ACTION = "name a source: rerun with --source SOURCE"
BUDGET_ACTION = (
    "raise --max-bytes/--max-tokens to the reported minimum or request a smaller page"
)


def _result(
    code: str | None,
    *,
    reason: str | None = None,
    status: str | None = None,
    operation: str = "list",
    items: list[dict[str, Any]] | None = None,
    complete: bool | None = True,
    data: dict[str, Any] | None = None,
    next_action: dict[str, Any] | None = None,
    **named: Any,
) -> dict[str, Any]:
    """A ToolResult shaped like the v2 envelope MemoryTool emits."""
    body: dict[str, Any] = dict(data or {})
    if reason is not None:
        body["reason"] = reason
    raw: dict[str, Any] = {
        "schema_version": 2,
        "operation": operation,
        "code": code,
        "items": items or [],
        "next_cursor": None,
        "unknowns": [],
        "data": body,
        **named,
    }
    if complete is not None:
        raw["complete"] = complete
    if next_action is not None:
        raw["next_action"] = next_action
    if status is None:
        status = "ok" if code == "OK" else "fail"
    return {
        "tool": "memory",
        "status": status,
        "summary": f"memory {operation}",
        "raw": raw,
    }


def _item(artifact_id: str = "a1", version: int = 1, **ref: Any) -> dict[str, Any]:
    reference = {
        "artifact_id": artifact_id,
        "artifact_version": version,
        "trust_tier": "EXTERNAL_WRITE",
        "freshness": "current",
        "integrity": "verified",
        "payload_hash": "0" * 64,
        **ref,
    }
    return {"reference": reference, "id": artifact_id, "version": version}


def test_t07_ui_state_classifier(tmp_path: Path) -> None:
    from rush.tools.memory import MEMORY_UI_STATES, memory_ui_state

    assert MEMORY_UI_STATES == tuple(STATE_ACTIONS), MEMORY_UI_STATES

    def classify(*args: Any, **kwargs: Any) -> dict[str, Any]:
        ui = memory_ui_state(*args, **kwargs)
        assert set(ui) == {"state", "reason", "action", "next_action", "rows"}, ui
        assert ui["state"] in MEMORY_UI_STATES
        assert isinstance(ui["action"], str) and ui["action"], ui
        return ui

    perm = lambda reason: _result("E_PERMISSION", reason=reason)
    rows: list[tuple[str, dict[str, Any], str]] = []
    # Rows 4-18 of the predicate table: every code, every D19 reason, every HTTP status.
    for code, state in (
        ("E_MIGRATION", "migration_required"),
        ("E_SCHEMA_UNSUPPORTED", "migration_required"),
        ("E_STORE_CORRUPT", "corrupt"),
        ("E_STORE_BUSY", "busy"),
        ("E_VERSION", "conflict"),
        ("E_RESTART", "restart"),
        ("E_BUDGET", "partial"),
        ("E_EMBEDDING_UNAVAILABLE", "partial"),
        ("UNRESOLVED", "partial"),
        ("E_NOT_VISIBLE", "not_visible"),
        ("E_INPUT", "invalid"),
        ("E_OFFSET", "invalid"),
        ("E_OWNER", "denied"),
        ("E_SCOPE", "denied"),
        ("E_UNAVAILABLE", "server_error"),
        ("E_SOMETHING_NEW", "server_error"),
    ):
        rows.append((code, _result(code), state))
    rows.append(
        (
            "E_INPUT/owner_scope",
            _result("E_INPUT", data={"field": "owner_scope"}),
            "invalid",
        )
    )
    rows.append(("revoked", perm("revoked"), "revoked"))
    rows.append(("expired", perm("expired"), "expired"))
    for reason in (
        "policy_missing",
        "no_grant",
        "project_not_registered",
        "operation_not_granted",
        "policy_invalid",
        "lock_unavailable",
        "a_reason_no_one_has_named_yet",
    ):
        rows.append((f"E_PERMISSION/{reason}", perm(reason), "denied"))
    rows.append(("OK", _result("OK", items=[_item()]), "ok"))
    for label, result, expected in rows:
        ui = classify(result)
        assert ui["state"] == expected, (label, ui)
        if label != "E_BUDGET":
            assert ui["action"] == STATE_ACTIONS[expected], (label, ui)
    budget = classify(
        _result("E_BUDGET", data={"required": {"max_bytes": 52113, "max_tokens": 917}})
    )
    assert budget["state"] == "partial"
    assert budget["action"].startswith(BUDGET_ACTION), budget
    assert "52113" in budget["action"] and "917" in budget["action"], budget
    assert classify(_result("E_BUDGET"))["action"] == BUDGET_ACTION

    # HTTP statuses without a body code (rows 6, 9, 10, 13, 14).
    for http, state in (
        (400, "invalid"),
        (401, "denied"),
        (403, "denied"),
        (404, "not_visible"),
        (409, "conflict"),
        (500, "server_error"),
        (503, "server_error"),
    ):
        ui = classify(
            {"status": "error", "summary": "x", "raw": None}, http_status=http
        )
        assert ui["state"] == state, (http, ui)
    # Without a code the outer status decides (rows 15-18).
    assert (
        classify({"status": "skipped", "summary": "skipped", "raw": None})["state"]
        == "denied"
    )
    assert (
        classify({"status": "skipped", "summary": "skipped", "raw": None})["action"]
        == SKIPPED_ACTION
    )
    assert (
        classify({"status": "error", "summary": "x", "raw": None})["state"] == "invalid"
    )
    assert (
        classify({"status": "warn", "summary": "x", "raw": None})["state"] == "partial"
    )
    assert (
        classify({"status": "fail", "summary": "x", "raw": None})["state"] == "denied"
    )

    # Rows 1-3: an exception, no result, each store state.
    err = classify(None, error=RuntimeError("boom"))
    assert err["state"] == "server_error" and err["reason"] == "RuntimeError: boom"
    none = classify(None)
    assert none["state"] == "server_error" and none["reason"] == "no result"
    absent = classify(None, store_state="absent")
    assert absent["state"] == "absent"
    assert absent["reason"] == "no memory store exists for this project"
    for store_state in ("migration_required", "corrupt", "busy"):
        ui = classify(None, store_state=store_state)
        assert ui["state"] == store_state, ui
        assert ui["reason"] == readonly_view_reason(store_state), ui  # type: ignore[arg-type]
        assert ui["action"] == STATE_ACTIONS[store_state]
    # A denial wins over a store state: the denied result is never reported as absent.
    assert classify(perm("revoked"), store_state="absent")["state"] == "revoked"

    # D16: the BOOTSTRAP-CONSENT next_action text is the action for revoked/expired/denied.
    guided = {
        "text": "run: rush memory grant --operation list",
        "command": "rush memory grant --operation list",
    }
    for reason, state in (
        ("revoked", "revoked"),
        ("expired", "expired"),
        ("no_grant", "denied"),
    ):
        ui = classify(_result("E_PERMISSION", reason=reason, next_action=guided))
        assert ui["state"] == state and ui["action"] == guided["text"], ui
        assert ui["next_action"] == guided, ui
    assert classify(perm("revoked"))["next_action"] is None

    # Collections: empty, an incomplete page, a mutation receipt, history versions.
    empty = classify(_result("OK", items=[]))
    assert empty["state"] == "empty" and empty["action"] == STATE_ACTIONS["empty"]
    assert (
        classify(_result("OK", items=[_item()], complete=False))["state"] == "partial"
    )
    assert (
        classify(_result("OK", items=[_item()], complete=False))["action"]
        == STATE_ACTIONS["partial"]
    )
    committed = _result("OK", operation="edit", items=[_item("a1", 2)], complete=False)
    assert classify(committed)["state"] == "ok", (
        "complete:false is not partial for a receipt"
    )
    history = _result(
        "OK", operation="history", items=[], versions=[_item("a1", 1), _item("a1", 2)]
    )
    assert classify(history)["state"] == "ok", (
        "history lists raw.versions, not raw.items"
    )
    assert (
        classify(_result("OK", operation="history", items=[], versions=[]))["state"]
        == "empty"
    )
    # Absent complete (a non-page read) is not partial.
    assert classify(_result("OK", items=[_item()], complete=None))["state"] == "ok"

    # Digest: v2 expand compares against raw.items[0].reference.payload_hash; legacy
    # expand against data.payload_hash; data.integrity == "mismatch" always wins.
    recorded = hashlib.sha256(b"exact bytes").hexdigest()
    expand = _result("OK", operation="expand", items=[_item(payload_hash=recorded)])
    assert classify(expand, observed_payload_sha256=recorded)["state"] == "ok"
    mismatch = classify(
        expand, observed_payload_sha256=hashlib.sha256(b"other").hexdigest()
    )
    assert (
        mismatch["state"] == "digest_mismatch"
        and mismatch["action"] == STATE_ACTIONS["digest_mismatch"]
    )
    legacy = _result("OK", operation="expand", data={"payload_hash": recorded})
    assert (
        classify(legacy, observed_payload_sha256=hashlib.sha256(b"other").hexdigest())[
            "state"
        ]
        == "digest_mismatch"
    )
    assert classify(legacy, observed_payload_sha256=recorded)["state"] == "ok"
    flagged = _result("OK", operation="expand", data={"integrity": "mismatch"})
    assert classify(flagged)["state"] == "digest_mismatch"

    # Per-row badges.
    badge_rows = classify(
        _result(
            "OK",
            items=[
                _item("s", 1, freshness="stale"),
                _item("u", 2, freshness="unknown"),
                _item("b", 1, integrity="backfilled"),
                _item("n", 3, integrity="unbound"),
                _item("m", 1, integrity="mismatch"),
                {**_item("p", 1), "applicability": "pending"},
                {**_item("r", 1), "applicability": "rejected"},
                {**_item("x", 1), "applicability": "superseded"},
                {**_item("e", 1), "reason_codes": ["expired"]},
                {**_item("v", 1), "archived": True},
                _item("clean", 1),
            ],
        )
    )
    by_id = {row["artifact_id"]: row for row in badge_rows["rows"]}
    assert by_id["s"]["badges"] == ["stale"]
    assert by_id["u"]["badges"] == ["unknown"]
    assert by_id["b"]["badges"] == ["integrity:backfilled"]
    assert by_id["n"]["badges"] == ["integrity:unbound"]
    assert by_id["m"]["badges"] == ["integrity:mismatch"]
    assert by_id["p"]["badges"] == ["pending"]
    assert by_id["r"]["badges"] == ["rejected"]
    assert by_id["x"]["badges"] == ["superseded"]
    assert by_id["e"]["badges"] == ["expired"]
    assert by_id["v"]["badges"] == ["archived"]
    assert by_id["clean"]["badges"] == []
    assert by_id["n"]["artifact_version"] == 3

    # Odd shapes never raise: raw as a bare list (legacy), a non-mapping result, no raw.
    assert (
        classify({"status": "ok", "raw": [{"id": "a1", "artifact_version": 1}]})[
            "state"
        ]
        == "ok"
    )
    assert classify({"status": "ok", "raw": []})["state"] == "empty"
    assert classify({"status": "ok", "raw": None})["state"] == "ok"

    # The shapes the producers really emit, not only hand-built dictionaries: a v2
    # history (versions listed, `items` deliberately empty), a v2 utf8 expansion whose
    # recorded digest is `items[0].reference.payload_hash`, and a real revoked grant.
    world = _world(tmp_path)
    artifact = world.alice()
    real_history = _oracle(
        world, "history", {"schema_version": 2, "artifact_id": artifact}
    )
    assert _code(real_history) == "OK", real_history
    assert _raw(real_history)["items"] == [] and _raw(real_history)["versions"]
    assert classify(real_history)["state"] == "ok", "history lists raw.versions"
    real_expand = _oracle(
        world,
        "expand",
        {
            "schema_version": 2,
            "artifact_id": artifact,
            "artifact_version": 1,
            "representation": "utf8",
        },
    )
    assert _code(real_expand) == "OK", real_expand
    page = _raw(real_expand)["items"][0]
    assert page["complete"] is True, page
    page_sha = hashlib.sha256(page["content_utf8"].encode("utf-8")).hexdigest()
    assert page_sha == page["reference"]["payload_hash"], page
    assert classify(real_expand, observed_payload_sha256=page_sha)["state"] == "ok"
    assert (
        classify(
            real_expand, observed_payload_sha256=hashlib.sha256(b"other").hexdigest()
        )["state"]
        == "digest_mismatch"
    )
    _revoke(world)
    revoked = classify(_oracle_list(world))
    assert revoked["state"] == "revoked", revoked
    assert classify(_oracle_list(world), store_state="absent")["state"] == "revoked"


# =============================================================================
# R3 -- the dashboard memory routes serve the 72-T06 contract under D1
# =============================================================================


def _ids() -> dict[str, str]:
    return {"invocation_id": uuid.uuid4().hex, "effect_id": uuid.uuid4().hex}


def _mutation_requests(world: World) -> list[tuple[str, str, dict[str, Any], bool]]:
    """(dashboard action, MemoryTool operation, schema-2 request without `apply`,
    whether an applied replay is byte-identical)."""
    owner = ALICE.as_dict()
    return [
        (
            "memory_edit",
            "edit",
            {
                "schema_version": 2,
                "subject": "failure",
                "artifact_id": world.alice("failure"),
                "expected_version": 1,
                "owner_scope": owner,
                "content": {"text": "needle edited by the dashboard"},
            },
            True,
        ),
        (
            "memory_archive",
            "archive",
            {
                "schema_version": 2,
                "subject": "episodic",
                "artifact_id": world.alice("episodic"),
                "expected_version": 1,
                "archived": True,
                "owner_scope": owner,
            },
            True,
        ),
        (
            "memory_delete",
            "delete",
            {
                "schema_version": 2,
                "subject": "skill_pattern",
                "artifact_ids": [world.alice("skill_pattern")],
                "expected_revisions": {world.alice("skill_pattern"): 1},
                "owner_scope": owner,
            },
            True,
        ),
        (
            "memory_promote",
            "promote",
            {
                "schema_version": 2,
                "subject": "architectural_decision",
                "artifact_id": world.alice("architectural_decision"),
                "expected_version": 1,
                "user_stated": True,
                "owner_scope": owner,
            },
            True,
        ),
        (
            "memory_propose",
            "write",
            {
                "schema_version": 2,
                "subject": SUBJECT,
                "content": {"text": "needle proposed by the dashboard"},
                "source": SOURCE,
                "owner_scope": owner,
            },
            True,
        ),
        (
            "memory_maintain",
            "maintain",
            {
                "schema_version": 2,
                "task": "expiry_sweep",
                "batch_size": 10,
                "owner_scope": owner,
            },
            False,
        ),
    ]


def test_t07_dashboard_memory_routes_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.tools.memory import memory_ui_state

    world = _world(tmp_path, extra_domain=24)
    dash = _dashboard(world)
    try:
        # --- GET section=memory: browse, second page, query, expand_id, related_id ---
        status, body = dash.snapshot("memory")
        assert status == 200, body
        data = body["data"]
        oracle = _raw(_oracle_list(world))
        assert _scrub(data["list"]["raw"]) == _scrub(oracle)
        assert _scrub(data["items"]) == _scrub(oracle["items"])
        assert data["next_cursor"] == oracle["next_cursor"]
        assert data["complete"] == oracle["complete"]
        assert data["subjects"] == list(SUBJECTS)
        assert data["known_sources"] == [SOURCE]
        assert all("reference" in item for item in data["items"])
        assert data["ui_state"] == memory_ui_state(data["list"])
        assert "bob-" not in json.dumps(data), "another owner's rows are never listed"

        status, body = dash.snapshot("memory", subject=SUBJECT)
        first = body["data"]
        assert first["complete"] is False and isinstance(first["next_cursor"], str)
        assert first["ui_state"]["state"] == "partial"
        status, body = dash.snapshot(
            "memory", subject=SUBJECT, cursor=first["next_cursor"]
        )
        second = body["data"]
        assert status == 200
        expected_second = _raw(
            _oracle_list(world, [SUBJECT], cursor=first["next_cursor"])
        )
        assert _scrub(second["list"]["raw"]) == _scrub(expected_second)
        paged = [_identity(i) for i in first["items"] + second["items"]]
        assert paged == _all_pages(world, SUBJECT)[: len(paged)]
        assert len(paged) == len(set(paged))

        status, body = dash.snapshot("memory", subject=SUBJECT, limit="5")
        assert _scrub(body["data"]["list"]["raw"]) == _scrub(
            _raw(_oracle_list(world, [SUBJECT], limit=5))
        )

        status, body = dash.snapshot("memory", subject=SUBJECT, query="needle")
        assert _scrub(body["data"]["list"]["raw"]) == _scrub(
            _raw(_oracle_list(world, [SUBJECT], "needle"))
        )

        target = world.alice("failure")
        status, body = dash.snapshot("memory", expand_id=target, expand_version="1")
        assert _scrub(body["data"]["expand"]["raw"]) == _scrub(
            _raw(_oracle(world, "expand", {"id": target, "version": 1}))
        )
        status, body = dash.snapshot("memory", related_id=target, related_version="1")
        assert _scrub(body["data"]["related"]["raw"]) == _scrub(
            _raw(_oracle(world, "related", {"id": target, "version": 1}))
        )

        # --- POST memory_query / memory_expand: v2 requests equal MemoryTool's ---
        for mode in ("list", "ask", "recall"):
            request = {"schema_version": 2, "subjects": [SUBJECT], "query": "needle"}
            status, body = dash.action("memory_query", {**request, "mode": mode})
            assert status == 200, (mode, body)
            assert _scrub(body["data"]["raw"]) == _scrub(
                _raw(_oracle(world, mode, request))
            ), mode
            assert body["data"]["raw"]["items"], mode
            assert all("reference" in i for i in body["data"]["raw"]["items"]), mode
        expand_args = {
            "schema_version": 2,
            "artifact_id": target,
            "artifact_version": 1,
            "representation": "utf8",
        }
        status, body = dash.action("memory_expand", expand_args)
        assert status == 200, body
        assert _scrub(body["data"]["raw"]) == _scrub(
            _raw(_oracle(world, "expand", expand_args))
        )
        assert body["data"]["raw"]["items"][0]["reference"]["artifact_id"] == target

        # --- POST edit/archive/delete/promote/propose/maintain: preview and apply ---
        before_all = world.db_sha()
        for action, operation, request, replayable in _mutation_requests(world):
            preview_args = {**request, "apply": False}
            status, body = dash.action(action, preview_args)
            assert status == 200, (action, body)
            assert body["data"]["raw"]["code"] == "OK", (action, body)
            assert _scrub(body["data"]["raw"]) == _scrub(
                _raw(_oracle(world, operation, preview_args))
            ), action
            assert world.db_sha() == before_all, f"{action}: a preview wrote"
            assert body["data"]["memory_view_key"]["request_identity"] == {
                "operation": action
            }, action
            assert body["data"]["ui_state"]["state"] in ("ok", "empty"), action

            apply_args = {**request, "apply": True, **_ids()}
            status, body = dash.action(action, apply_args, grants=WRITE)
            assert status == 200, (action, body)
            applied = body["data"]["raw"]
            assert applied["code"] == "OK", (action, applied)
            assert world.db_sha() != before_all, f"{action}: apply wrote nothing"
            before_all = world.db_sha()
            if replayable:
                replay = _oracle(
                    world,
                    operation,
                    apply_args,
                    permissions=ExecutionPermissions(cache_write=True),
                )
                assert _scrub(applied) == _scrub(_raw(replay)), action
                assert world.db_sha() == before_all, f"{action}: a replay wrote"
        current = world.store.get_current_row(world.alice("failure"))
        assert current is not None and current["artifact_version"] == 2

        # apply without a cache_write grant writes nothing; a legacy shape without
        # `apply` keeps the HEAD write-immediately behavior and needs the grant.
        status, body = dash.action(
            "memory_propose",
            {
                "schema_version": 2,
                "subject": SUBJECT,
                "content": {"text": "x"},
                "source": SOURCE,
                "owner_scope": ALICE.as_dict(),
                "apply": True,
                **_ids(),
            },
        )
        assert status == 403, (status, body)
        assert world.db_sha() == before_all
        status, body = dash.action(
            "memory_propose",
            {
                "subject": SUBJECT,
                "content": {"text": "legacy shape"},
                "source": SOURCE,
                "owner_scope": ALICE.as_dict(),
            },
        )
        assert status == 403, (
            "legacy apply-absent propose still writes, so needs cache_write"
        )
        status, body = dash.action(
            "memory_propose",
            {
                "schema_version": 2,
                "subject": SUBJECT,
                "content": {"text": "schema 2 default is a preview"},
                "source": SOURCE,
                "owner_scope": ALICE.as_dict(),
            },
        )
        assert status == 200 and body["data"]["raw"]["code"] == "OK", body
        assert world.db_sha() == before_all
    finally:
        dash.stop()

    # --- the client is Phase 71 P07's: no dashboard client file is touched (D12) ---
    import subprocess

    repo = Path(__file__).resolve().parent.parent
    for client in ("application.js", "static_assets.py"):
        assert (repo / "src" / "rush" / "dashboard" / client).is_file(), client
    assert not (repo / "src" / "rush" / "dashboard" / "panels.js").exists()
    assert not (repo / "tests" / "test_phase71_dashboard_integration.py").exists()
    diff = subprocess.run(
        [
            "git",
            "diff",
            "--quiet",
            "HEAD",
            "--",
            "src/rush/dashboard/application.js",
            "src/rush/dashboard/static_assets.py",
        ],
        cwd=repo,
        capture_output=True,
        check=False,
    )
    assert diff.returncode == 0, "a dashboard client file differs from HEAD"

    _check_dashboard_denials(tmp_path, monkeypatch)


def _check_dashboard_denials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A denied grant answers with the D19 state and the BOOTSTRAP-CONSENT next action
    on every memory route; nothing of the project is disclosed."""
    cases = {
        "revoked": lambda w: _revoke(w),
        "expired": lambda w: monkeypatch.setattr(
            auth, "_now", lambda: time.time() + 10**7
        ),
        "denied": lambda w: None,
    }
    for label, break_it in cases.items():
        world = _world(
            tmp_path,
            ops=("ask", "expand", "list") if label == "denied" else GRANT_OPS,
            expires_at=time.time() + 3600 if label == "expired" else None,
            name=f"project-{label}",
        )
        dash = _dashboard(world)
        try:
            break_it(world)
            historical = label == "denied"
            query = {
                "subject": SUBJECT,
                **({"include_archived": "true"} if historical else {}),
            }
            _status, body = dash.snapshot("memory", **query)
            ui = body["data"]["ui_state"]
            assert ui["state"] == label, (label, ui)
            assert isinstance(ui["next_action"], dict), (label, ui)
            assert str(ui["next_action"]["command"]).startswith("rush memory grant"), ui
            assert body["data"]["items"] == []
            request = {"schema_version": 2, "subjects": [SUBJECT], "query": "needle"}
            if historical:
                request["archive_mode"] = "historical"
            _status, body = dash.action("memory_query", {**request, "mode": "list"})
            raw = body["data"]["raw"]
            assert body["data"]["ui_state"]["state"] == label, (label, body)
            assert raw["items"] == [] and raw["code"] == "E_PERMISSION", raw
            # 73-T02 H3: `memory_next_action` has a command only for the grant
            # reasons, so a revoked or expired grant keeps `command: None` in
            # `raw.next_action` (equal to `MemoryTool.run`'s raw, 72-T07 R3); the
            # `ui_state` action is the one that names the `rush memory grant` preview.
            if label == "denied":
                assert str(raw["next_action"]["command"]).startswith(
                    "rush memory grant"
                ), raw
            else:
                assert raw["next_action"]["command"] is None, raw
                assert raw["next_action"]["text"] == (
                    f"memory access denied ({label})"
                ), raw
            action = body["data"]["ui_state"]["next_action"]
            assert str(action["command"]).startswith("rush memory grant"), body["data"]
            assert "alice-" not in json.dumps(body["data"]), "a denial disclosed a row"
            assert _reason(body["data"]) == (
                "operation_not_granted" if label == "denied" else label
            )
        finally:
            dash.stop()
        monkeypatch.setattr(auth, "_now", time.time)


# =============================================================================
# R11 -- request-bound revalidation and the `memory_view_key` stamp (server only)
# =============================================================================


class _Hook:
    """Fires one event right after the real wrapped call returns (before the server
    builds its response)."""

    def __init__(self) -> None:
        self.event: Callable[[], object] | None = None

    def fire(self) -> None:
        event, self.event = self.event, None
        if event is not None:
            event()


def _authority_expected(world: World, access_op: str = "list") -> dict[str, Any]:
    from rush.memory.retrieval import MemoryAccess, route_access
    from rush.tools.memory import memory_view_authority

    access = route_access(world.root, access_op, data_root=world.data_root)
    assert isinstance(access, MemoryAccess), access
    return memory_view_authority(access, world.store.current_generation())


def _make_target(
    world: World, name: str
) -> Callable[[Dash], tuple[int, dict[str, Any]]]:
    victim = world.alice("failure")
    reads = {
        "browse": lambda d: d.snapshot("memory", subject=SUBJECT),
        "query": lambda d: d.snapshot("memory", subject=SUBJECT, query="needle"),
        "section_expand": lambda d: d.snapshot(
            "memory", expand_id=victim, expand_version="1"
        ),
        "memory_query": lambda d: d.action(
            "memory_query",
            {
                "schema_version": 2,
                "mode": "list",
                "subjects": [SUBJECT],
                "query": "needle",
            },
        ),
        "memory_expand": lambda d: d.action(
            "memory_expand",
            {"schema_version": 2, "artifact_id": victim, "artifact_version": 1},
        ),
        "memory_edit_preview": lambda d: d.action(
            "memory_edit",
            {
                "schema_version": 2,
                "subject": "failure",
                "artifact_id": victim,
                "expected_version": 1,
                "owner_scope": ALICE.as_dict(),
                "content": {"text": "needle preview only"},
                "apply": False,
            },
        ),
    }
    return reads[name]


_R11_TARGETS = (
    "browse",
    "query",
    "section_expand",
    "memory_query",
    "memory_expand",
    "memory_edit_preview",
)


def _payload(body: dict[str, Any]) -> dict[str, Any]:
    return body["data"]


def test_t07_dashboard_authority_revalidated_and_stamped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.dashboard import server as server_module

    hook = _Hook()
    real_fetch = server_module._fetch_memory_browse_items
    real_run = MemoryTool.run

    def fetch(*args: Any, **kwargs: Any) -> Any:
        result = real_fetch(*args, **kwargs)
        hook.fire()
        return result

    def run(self: MemoryTool, root: Path, *args: Any, **kwargs: Any) -> Any:
        result = real_run(self, root, *args, **kwargs)
        hook.fire()
        return result

    monkeypatch.setattr(server_module, "_fetch_memory_browse_items", fetch)
    monkeypatch.setattr(MemoryTool, "run", run)

    for target in _R11_TARGETS:
        # (4) nothing changes during the computation: the stamp names the authority.
        world = _world(tmp_path, expires_at=time.time() + 3600, name=f"stamp-{target}")
        dash = _dashboard(world)
        try:
            server_module._MEMORY_BROWSE_CACHE.clear()
            _status, body = _make_target(world, target)(dash)
            data = _payload(body)
            key = data["memory_view_key"]
            assert key["authority"] == _authority_expected(world), (target, key)
            assert key["authority"]["grant_id"] == world.grant["grant_id"]  # type: ignore[index]
            assert key["authority"]["project_id"] == world.project_id
            assert key["authority"]["owner_scope"] == {"kind": "user", "id": "alice"}
            assert key["authority"]["sources"] == [SOURCE]
            assert (
                key["authority"]["store_generation"] == world.store.current_generation()
            )
            assert data["ui_state"]["state"] in ("ok", "partial", "empty"), (
                target,
                data["ui_state"],
            )
            identity = key["request_identity"]
            if target in ("browse", "query", "section_expand"):
                assert list(identity) == sorted(identity), identity
                if target == "section_expand":
                    # The request names the exact record, not a subject.
                    assert identity["expand_id"] == [world.alice("failure")]
                    assert identity["expand_version"] == ["1"]
                else:
                    assert identity["subject"] == [SUBJECT]
                if target == "query":
                    assert identity["query"] == ["needle"]
            else:
                operation = "memory_edit" if target == "memory_edit_preview" else target
                assert identity == {"operation": operation}, (target, identity)
        finally:
            dash.stop()

        for event in ("revoke", "expire", "replace"):
            world = _world(
                tmp_path,
                expires_at=time.time() + 3600,
                name=f"{event}-{target}",
            )
            dash = _dashboard(world)
            try:
                server_module._MEMORY_BROWSE_CACHE.clear()
                if event == "revoke":
                    hook.event = lambda w=world: _revoke(w)
                elif event == "expire":
                    hook.event = lambda: monkeypatch.setattr(
                        auth, "_now", lambda: time.time() + 10**7
                    )
                else:
                    hook.event = lambda w=world: _grant(
                        w.root, ALICE, sources=(SOURCE, "other-src")
                    )
                _status, body = _make_target(world, target)(dash)
                hook.event = None
                data = _payload(body)
                # A refusal echoes the request: the id the caller itself named
                # (`expand_id`, `artifact_id`) is not a row the store disclosed.
                text = json.dumps(
                    {k: v for k, v in data.items() if k != "memory_view_key"}
                ).replace(world.alice("failure"), "")
                state = data["ui_state"]["state"]
                want = {"revoke": "revoked", "expire": "expired", "replace": "restart"}[
                    event
                ]
                assert state == want, (target, event, data["ui_state"])
                assert "alice-" not in text, (
                    target,
                    event,
                    "an item survived the race",
                )
                if event != "replace":
                    action = data["ui_state"]["next_action"]
                    assert isinstance(action, dict), (target, event, data["ui_state"])
                    assert str(action["command"]).startswith("rush memory grant")
                else:
                    raw = data.get("raw") or {}
                    if raw:
                        assert raw["code"] == "E_RESTART", (target, raw)
                        assert raw["data"]["reason"] == "access_changed", (target, raw)
                assert len(server_module._MEMORY_BROWSE_CACHE) == 0, (
                    target,
                    event,
                    "a raced page entered the browse cache",
                )
                monkeypatch.setattr(auth, "_now", time.time)
                if event == "replace":
                    # (4) a request after the replacement carries the new grant id.
                    new_grant = auth.load_policy_readonly(data_root=world.data_root)
                    active = [
                        g
                        for g in new_grant["grants"].values()
                        if g.get("project_id") == world.project_id
                        and not g.get("revoked")
                        and not g.get("superseded_by")
                    ]
                    assert len(active) == 1
                    _status, body = _make_target(world, target)(dash)
                    key = _payload(body)["memory_view_key"]
                    assert key["authority"]["grant_id"] == active[0]["grant_id"]
                    assert key["authority"]["grant_id"] != world.grant["grant_id"]  # type: ignore[index]
                    assert key["authority"]["sources"] == sorted([SOURCE, "other-src"])
            finally:
                hook.event = None
                dash.stop()

    # (5) an applied edit whose wrapped call revokes after its commit returns the
    # committed result stamped with the pre-revoke authority; the next read is revoked.
    world = _world(tmp_path, name="apply-race")
    dash = _dashboard(world)
    try:
        before = _authority_expected(world, "write")
        victim = world.alice("failure")
        hook.event = lambda: _revoke(world)
        _status, body = dash.action(
            "memory_edit",
            {
                "schema_version": 2,
                "subject": "failure",
                "artifact_id": victim,
                "expected_version": 1,
                "owner_scope": ALICE.as_dict(),
                "content": {"text": "needle committed before the revoke"},
                "apply": True,
                **_ids(),
            },
            grants=WRITE,
        )
        hook.event = None
        data = _payload(body)
        assert data["raw"]["code"] == "OK", data
        stamp = data["memory_view_key"]["authority"]
        assert stamp["grant_id"] == world.grant["grant_id"]  # type: ignore[index]
        assert stamp["policy_revision"] == before["policy_revision"]
        row = world.store.get_current_row(victim)
        assert row is not None and row["artifact_version"] == 2
        _status, body = dash.snapshot("memory", subject=SUBJECT)
        assert _payload(body)["ui_state"]["state"] == "revoked"
        assert _payload(body)["items"] == []
    finally:
        hook.event = None
        dash.stop()


# =============================================================================
# R6 -- a project switch during a request discards the foreign late response
# =============================================================================


def _virgin(tmp_path: Path, *, grant: bool = True, name: str = "virgin") -> World:
    """A registered project with no memory store at all (and optionally a grant)."""
    data_root = default_data_root()
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    root = root.resolve()
    record = register_project(root, data_root=data_root)
    world = World(root, data_root, record.project_id, None)  # type: ignore[arg-type]
    for subject in SUBJECTS:
        for label in ("alice", "bob"):
            world.ids[(label, subject)] = f"{label}-{subject}"
    if grant:
        world.grant = _grant(root)
    return world


def test_t07_project_switch_discards_late_response(tmp_path: Path) -> None:
    a = _world(tmp_path, grant=False, name="proj-a")
    b = _world(tmp_path, grant=False, name="proj-b")
    _write(a.store, "a-only-row", ALICE, SUBJECT, "needle only project a")
    _write(b.store, "b-only-row", ALICE, SUBJECT, "needle only project b")
    gate = threading.Event()
    entered = threading.Event()
    finished = threading.Event()

    def blocking(root: Path, **kwargs: Any) -> Any:
        if root == a.root and kwargs.get("operation") == "list":
            entered.set()
            gate.wait(10)
        try:
            return MemoryTool().run(root, **kwargs)
        finally:
            if root == a.root and kwargs.get("operation") == "list":
                finished.set()

    actions = _actions(blocking)
    state = TuiState(
        projects=[
            ProjectState(name="proj-a", root=a.root, project_id=a.project_id),
            ProjectState(name="proj-b", root=b.root, project_id=b.project_id),
        ],
        data_root=a.data_root,
    )
    state.memory_owner_scope_kind, state.memory_owner_scope_id = ("user", "alice")
    state.terminal_size = (160, 50)
    try:
        _dispatch_key(state, "f3", actions)
        _dispatch_key(state, "4", actions)
        assert entered.wait(10), "project A's list request never reached the worker"
        assert (
            state.memory_request is not None and state.active_project.name == "proj-a"
        )
        # Project A's held T07 state (history, explanation, cursors, import and
        # correction buffers, view state, authority, map snapshot) when the switch lands.
        outgoing = state.active_project
        outgoing.map_snapshot, outgoing.map_snapshot_key = {"available": True}, ("k",)
        state.memory_history = {
            "id": "a-only-row",
            "project_key": project_key(outgoing),
        }
        state.memory_explained = {
            "id": "a-only-row",
            "project_key": project_key(outgoing),
        }
        state.memory_cursor, state.memory_cursor_next = "cursor-a", "cursor-a2"
        state.memory_cursor_stack = [None, "cursor-a"]
        state.memory_import_buffer = "a-only-row"
        state.memory_import_preview = {"records": ["a-only-row"]}
        state.memory_import_selected = {"a-only-row"}
        state.memory_correction_buffer = {"kind": "correct", "reason": "a-only-row"}
        state.memory_view_state = {"state": "ok", "reason": "a-only-row"}
        state.memory_authority = ("a-only-row",)
        # Leave Memory (its list keys never take F2), F2 -> select B, while A's
        # request is still blocked in the worker.
        for key in ("f3", "1", "f2", "down", "enter"):
            _dispatch_key(state, key, actions)
        assert state.active_project.name == "proj-b"
        # The switch itself drops every piece of A's held state (R6/R10, section 3.6).
        assert state.memory_history is None and state.memory_explained is None
        assert state.memory_cursor is None and state.memory_cursor_next is None
        assert state.memory_cursor_stack == []
        assert state.memory_import_buffer is None
        assert state.memory_import_preview is None and not state.memory_import_selected
        assert state.memory_correction_buffer is None
        assert state.memory_view_state is None and state.memory_authority is None
        assert outgoing.map_snapshot is None and outgoing.map_snapshot_key is None
        gate.set()
        assert finished.wait(10)
        for _ in range(20):
            _pump(state, actions)
            time.sleep(0.01)
        assert state.memory_request is None or state.memory_request.get(
            "project_key"
        ) == project_key(state.active_project)
        listed = json.dumps(state.memory_items, default=str)
        assert "a-only-row" not in listed, "A's late page filled B"
        assert "a-only-row" not in state.memory_message
        assert state.memory_view_state is None and state.memory_authority is None
        assert state.memory_history is None and state.memory_cursor_stack == []
        assert "a-only-row" not in _render(state)
        # Project B then lists its own record through the real schema-2 MemoryTool, and
        # still nothing of A: a discarded late page leaves B's own browse working.
        _keys(state, actions, "f3", "4")
        assert state.mode == "memory" and state.active_project.name == "proj-b"
        listed_b = json.dumps(state.memory_items, default=str)
        assert "b-only-row" in listed_b, (state.memory_message, listed_b)
        assert "a-only-row" not in listed_b and "a-only-row" not in state.memory_message
    finally:
        gate.set()


# =============================================================================
# R9 / R10 / R12 -- D37 cache keys, revocation and request identity
# =============================================================================

_AUTHORITY_FIELDS = (
    "policy_revision",
    "grant_id",
    "project_id",
    "worktree_id",
    "owner_scope",
    "sources",
    "store_generation",
)


def _key_tuple(d: dict[str, Any]) -> tuple[Any, ...]:
    owner = d["owner_scope"]
    return (
        d["policy_revision"],
        d["grant_id"],
        d["project_id"],
        d["worktree_id"],
        None if owner is None else (owner["kind"], owner["id"]),
        tuple(d["sources"] or ()),
        d["store_generation"],
    )


def _regrant(
    world: World, *, ops: tuple[str, ...] = (*GRANT_OPS, "bootstrap")
) -> dict[str, Any]:
    """A replacement grant (new grant id and policy revision) for the same owner."""
    world.grant = _grant(world.root, ALICE, ops=ops)
    return world.grant


def _counting_fetch(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from rush.dashboard import server as server_module

    calls: list[dict[str, Any]] = []
    real = server_module._fetch_memory_browse_items

    def fetch(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(server_module, "_fetch_memory_browse_items", fetch)
    server_module._MEMORY_BROWSE_CACHE.clear()
    return calls


def _map_ids(body: dict[str, Any]) -> set[str]:
    return set(re.findall(r"memory:([A-Za-z0-9_.-]+)", json.dumps(body["data"])))


def _historical_fixture(
    dash: Dash, world: World, monkeypatch: pytest.MonkeyPatch
) -> tuple[Callable[[str, str], Any], list[int]]:
    """Drive `_historical_map_snapshot_reused` directly over a real manifest file, with
    the attempt build replaced by a counting stub holding one memory entry."""
    from rush.dashboard import server as server_module

    builds: list[int] = []

    def build(
        root: Path, project_id: str, record: Any, run_id: str, attempt_id: Any
    ) -> Any:
        builds.append(1)
        return {"memories": [{"id": "alice-domain_knowledge"}], "root": str(root)}, True

    monkeypatch.setattr(server_module, "_build_historical_map_snapshot", build)
    record = dash.ctx.projects.get(world.project_id)

    def reuse(run_id: str, attempt_id: str) -> Any:
        manifest = world.root / server_module._MANIFEST_RELATIVE.format(
            run_id=run_id, attempt_id=attempt_id
        )
        manifest.parent.mkdir(parents=True, exist_ok=True)
        if not manifest.exists():
            manifest.write_text("{}", encoding="utf-8")
        return server_module._historical_map_snapshot_reused(
            dash.ctx, world.root, world.project_id, record, run_id, attempt_id
        )

    return reuse, builds


def test_t07_cache_keyed_by_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.retrieval import MemoryAccess, route_access
    from rush.tools.memory import memory_view_authority
    from rush.workflows import projects as wp

    world = _world(tmp_path)
    access = route_access(world.root, "list", data_root=world.data_root)
    assert isinstance(access, MemoryAccess), access

    # The authority projection: wire names, sorted sources, the given generation.
    stamp = memory_view_authority(access, 7)
    assert stamp == {
        "policy_revision": access.policy_revision,
        "grant_id": world.grant["grant_id"],  # type: ignore[index]
        "project_id": world.project_id,
        "worktree_id": access.worktree_id,
        "owner_scope": {"kind": "user", "id": "alice"},
        "sources": [SOURCE],
        "store_generation": 7,
    }
    # legacy_allowlist: no grant fields; the declared owner and the allowlist, sorted.
    legacy = MemoryAccess.legacy(world.root, ["b-src", SOURCE], owner_scope=ALICE)
    assert memory_view_authority(legacy, 5) == {
        "policy_revision": None,
        "grant_id": None,
        "project_id": None,
        "worktree_id": None,
        "owner_scope": {"kind": "user", "id": "alice"},
        "sources": ["b-src", SOURCE],  # sorted: "b-src" < "t07-src"
        "store_generation": 5,
    }
    assert (
        memory_view_authority(MemoryAccess.legacy(world.root, [SOURCE]), 1)[
            "owner_scope"
        ]
        is None
    )
    # overlay: the personal layer's own grant; the owner is the overlay owner. (A
    # project of its own: a second owner's grant on `world` would make its reads
    # ambiguous.)
    ow = _world(tmp_path, grant=False, name="overlay-authority")
    overlay_owner = auth.user_overlay_owner_scope(data_root=ow.data_root)
    overlay_grant = auth.grant_memory_scope(
        project_root=ow.root,
        owner_scope=overlay_owner,
        approved_sources=["personal-preferences"],
        allowed_operations=["overlay_read", "list"],
        expected_policy_revision=_revision(),
        consent=True,
        data_root=ow.data_root,
    )
    overlay = MemoryAccess.resolve(
        ow.root,
        operation="list",
        overlay=True,
        owner_scope=overlay_owner,
        data_root=ow.data_root,
    )
    assert isinstance(overlay, MemoryAccess), overlay
    overlay_stamp = memory_view_authority(overlay, 9)
    assert overlay_stamp["grant_id"] == overlay_grant["grant_id"]
    assert overlay_stamp["owner_scope"] == overlay_owner.as_dict()
    assert overlay_stamp["sources"] == ["personal-preferences"]
    assert overlay_stamp["store_generation"] == 9
    # unavailable / denied: every field null.
    assert memory_view_authority(None, None) == dict.fromkeys(_AUTHORITY_FIELDS)
    assert list(memory_view_authority(None, None)) == list(_AUTHORITY_FIELDS) or set(
        memory_view_authority(None, None)
    ) == set(_AUTHORITY_FIELDS)

    # Site 1: the dashboard browse cache stores and serves under (authority, request).
    fetches = _counting_fetch(monkeypatch)
    dash = _dashboard(world)
    try:
        dash.snapshot("memory", subject=SUBJECT)
        dash.snapshot("memory", subject=SUBJECT)
        assert len(fetches) == 1, "an unchanged authority and request is served cached"
        _write(world.store, "alice-fresh", ALICE, SUBJECT, "needle fresh row")
        _status, body = dash.snapshot("memory", subject=SUBJECT)
        assert len(fetches) == 2, "a store write changes the generation, so the key"
        assert "alice-fresh" in json.dumps(body["data"]["items"])
        old_grant = world.grant["grant_id"]  # type: ignore[index]
        new_grant = _regrant(world)["grant_id"]
        assert new_grant != old_grant
        _status, body = dash.snapshot("memory", subject=SUBJECT)
        assert len(fetches) == 3, "a replacement grant must not be served the old page"
        assert body["data"]["memory_view_key"]["authority"]["grant_id"] == new_grant
        dash.snapshot("memory", subject=SUBJECT)
        assert len(fetches) == 3, "the new key is cached in turn"

        # Site 2: `_refresh_project_memories` records the authority its snapshot ran under.
        from rush.dashboard import server as server_module

        server_module._refresh_project_memories(dash.ctx, world.project_id, world.root)
        recorded = dash.ctx.memory_authority[world.project_id]
        assert recorded == _key_tuple(_authority_expected(world))

        # Site 3: `_historical_map_snapshot_reused` keys on the authority too.
        reuse, builds = _historical_fixture(dash, world, monkeypatch)
        first = reuse("run-1", "att-1")
        assert reuse("run-1", "att-1") is first and len(builds) == 1
        _regrant(world, ops=GRANT_OPS)
        again = reuse("run-1", "att-1")
        assert len(builds) == 2, "a new authority rebuilds the memoized historical view"
        assert again is not first
    finally:
        dash.stop()

    # Site 4: the TUI expansion is keyed by the authority it was fetched under.
    state, actions, recorder = _tui(world)
    _open_memory(state, actions)
    _to_subject(state, actions, "failure")
    _keys(state, actions, "x")
    expected_key = _key_tuple(_authority_expected(world, "expand"))
    assert state.memory_expanded is not None
    assert state.memory_expanded["authority"] == expected_key
    expands = len(recorder.of("expand"))
    _keys(state, actions, "x")
    assert len(recorder.of("expand")) == expands, "same authority: the page is reused"
    _regrant(world)
    _keys(state, actions, "x")
    assert len(recorder.of("expand")) > expands, "a new grant refetches the page"
    assert state.memory_expanded is not None
    assert state.memory_expanded["authority"] == _key_tuple(
        _authority_expected(world, "expand")
    )
    assert state.memory_expanded["authority"] != expected_key

    # Site 5: the TUI map snapshot is keyed by the authority tuple.
    calls: list[int] = []

    def _counting_snapshot(record: Any, run_id: Any, attempt_id: Any) -> dict[str, Any]:
        calls.append(1)
        return {"available": True}

    monkeypatch.setattr(wp, "project_map_snapshot", _counting_snapshot)
    from rush import tui as tui_mod

    project = ProjectState(name="t07", root=world.root, project_id=world.project_id)
    tui_mod._load_map_snapshot(project, world.data_root)
    tui_mod._load_map_snapshot(project, world.data_root)
    assert len(calls) == 1, "unchanged state is served from the cache"
    # An identical grant is returned unchanged (no new authority), so the replacement
    # must differ from Site 4's: the default `_regrant` adds "bootstrap".
    _regrant(world, ops=GRANT_OPS)
    tui_mod._load_map_snapshot(project, world.data_root)
    assert len(calls) == 2, "a new authority reloads the map snapshot"


def test_t07_cache_cleared_on_revoke_expire_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush import tui as tui_mod
    from rush.dashboard import server as server_module
    from rush.workflows import projects as wp

    for event in ("revoke", "expire"):
        world = _world(tmp_path, expires_at=time.time() + 3600, name=f"proj-{event}")

        def trip(w: World = world, e: str = event) -> None:
            if e == "revoke":
                _revoke(w)
            else:
                monkeypatch.setattr(auth, "_now", lambda: time.time() + 10**7)

        want = "revoked" if event == "revoke" else "expired"
        fetches = _counting_fetch(monkeypatch)
        calls: list[int] = []

        def counted_snapshot(
            record: Any, run_id: Any, attempt_id: Any, _calls: list[int] = calls
        ) -> dict[str, Any]:
            _calls.append(1)
            return {"available": True}

        monkeypatch.setattr(wp, "project_map_snapshot", counted_snapshot)
        state, actions, _recorder = _tui(world)
        _open_memory(state, actions)
        _to_subject(state, actions, "failure")
        _keys(state, actions, "x")
        assert state.memory_expanded is not None
        project = state.active_project
        tui_mod._load_map_snapshot(project, world.data_root)
        dash = _dashboard(world)
        try:
            server_module._refresh_project_memories(
                dash.ctx, world.project_id, world.root
            )
            _, body = dash.snapshot("memory", subject=SUBJECT)
            assert len(fetches) == 1 and body["data"]["items"]
            _, mapped = dash.snapshot("map")
            assert any(i.startswith("alice-") for i in _map_ids(mapped)), (
                "map has memories"
            )
            reuse, _builds = _historical_fixture(dash, world, monkeypatch)
            reuse("run-9", "att-9")
            memo = dash.ctx.historical_map_memo

            trip()

            # Dashboard browse: the D19 state, never the cached page.
            _, body = dash.snapshot("memory", subject=SUBJECT)
            assert body["data"]["ui_state"]["state"] == want, body["data"]["ui_state"]
            assert body["data"]["items"] == [] and "alice-" not in json.dumps(
                body["data"]
            )
            assert len(fetches) == 1, "a denied request fetched nothing"
            # Dashboard map: no memory entry of the project is served.
            _, mapped = dash.snapshot("map")
            assert not any(i.startswith("alice-") for i in _map_ids(mapped)), event
            # Historical memo: a denial serves no memories and never replaces the memo.
            denied = reuse("run-9", "att-9")
            assert denied is not None and denied["memories"] == [], event
            assert denied["memory_state"]["state"] == want, event
            assert dash.ctx.historical_map_memo is memo
            # TUI: the next refresh shows the state; the expansion and the map cache go.
            _keys(state, actions, "/", "enter")
            assert state.memory_view_state is not None
            assert state.memory_view_state["state"] == want, state.memory_view_state
            assert state.memory_items == [] and state.memory_expanded is None
            assert want in state.memory_message
            rendered = _render(state)
            assert "alice-failure" not in rendered
            tui_mod._load_map_snapshot(project, world.data_root)
            assert len(calls) == 1, (
                "a denied map load must not call the snapshot reader"
            )
            assert project.map_snapshot is not None
            assert project.map_snapshot["available"] is False
            assert f"E_PERMISSION: {want}" in project.map_snapshot["reason"]
        finally:
            dash.stop()
            monkeypatch.setattr(auth, "_now", time.time)

    # A project switch clears every held page; the next render shows nothing of A.
    a = _world(tmp_path, name="switch-a")
    b = _world(tmp_path, name="switch-b")
    _write(a.store, "a-only-row", ALICE, "failure", "needle a only")
    _write(b.store, "b-only-row", ALICE, "failure", "needle b only")
    state, actions, _ = _tui(a)
    state.projects.append(
        ProjectState(name="t07-b", root=b.root, project_id=b.project_id)
    )
    _open_memory(state, actions)
    _to_subject(state, actions, "failure")
    _keys(state, actions, "x", "v", "E")
    outgoing = state.active_project
    outgoing.map_snapshot, outgoing.map_snapshot_key = {"available": True}, ("k",)
    assert state.memory_expanded is not None
    assert state.memory_history is not None and state.memory_explained is not None
    _keys(state, actions, "f3", "1", "f2", "down", "enter")
    assert state.active_project.name == "t07-b"
    assert state.memory_expanded is None
    assert state.memory_history is None and state.memory_explained is None
    assert outgoing.map_snapshot is None and outgoing.map_snapshot_key is None
    assert state.memory_cursor is None and state.memory_cursor_stack == []
    assert state.memory_view_state is None and state.memory_authority is None
    assert (
        state.memory_correction_buffer is None and state.memory_import_preview is None
    )
    assert "a-only-row" not in _render(state)
    _open_memory(state, actions)
    _to_subject(state, actions, "failure")
    assert "a-only-row" not in json.dumps(state.memory_items, default=str)
    assert "a-only-row" not in _render(state)

    # Dashboard: a request for B after one for A serves nothing cached under A, with no
    # switch signal sent to the server.
    server_module._MEMORY_BROWSE_CACHE.clear()
    dash = _dashboard(a, b)
    try:
        _, first = dash.snapshot("memory", subject="failure")
        assert "a-only-row" in json.dumps(first["data"]["items"])
        dash.project_id = b.project_id
        _, second = dash.snapshot("memory", subject="failure")
        assert "b-only-row" in json.dumps(second["data"]["items"])
        assert "a-only-row" not in json.dumps(second["data"]), (
            "A's cached page leaked to B"
        )
    finally:
        dash.stop()


def test_t07_cache_key_request_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --- dashboard: every filter is part of the request identity ---------------
    world = _world(tmp_path, extra_domain=3)
    fetches = _counting_fetch(monkeypatch)
    dash = _dashboard(world)
    try:
        variants: list[dict[str, str]] = [
            {"subject": "failure"},
            {"subject": "episodic"},
            {"subject": "failure", "trust": "EXTERNAL_WRITE"},
            {"subject": "failure", "trust": "DERIVED"},
            {"subject": "failure", "include_archived": "true"},
            {"subject": "failure", "freshness": "current"},
            {"subject": "failure", "freshness": "stale"},
            {"subject": "failure", "source": SOURCE},
            {"subject": "failure", "limit": "1"},
            {"subject": "failure", "owner": "user:alice"},
        ]
        keys: list[str] = []
        pages: list[Any] = []
        for variant in variants:
            before = len(fetches)
            _, body = dash.snapshot("memory", **variant)
            data = body["data"]
            assert len(fetches) == before + 1, (
                "served from another request's page",
                variant,
            )
            keys.append(
                json.dumps(data["memory_view_key"]["request_identity"], sort_keys=True)
            )
            pages.append(_pairs(data["items"]))
        assert len(set(keys)) == len(variants), "two requests shared one identity"
        assert pages[0] != pages[1], "subject changes the page"
        assert pages[2] != pages[3], "trust changes the page"
        for variant in variants:
            before = len(fetches)
            dash.snapshot("memory", **variant)
            assert len(fetches) == before, (
                "an identical request must be cached",
                variant,
            )
        # Historical -> current map switch: two historical views and the current one
        # never share a memo slot.
        reuse, builds = _historical_fixture(dash, world, monkeypatch)
        run_a = reuse("run-1", "att-1")
        run_b = reuse("run-2", "att-1")
        assert len(builds) == 2 and run_a is not run_b
        assert reuse("run-2", "att-1") is run_b and len(builds) == 2
        assert dash.ctx.historical_map_memo[0][1:3] == ("run-2", "att-1")
    finally:
        dash.stop()

    # --- TUI: expand A then B; A's late page never fills B -----------------------
    world = _world(tmp_path, name="tui-identity")
    _write(world.store, "alice-failure-2", ALICE, "failure", "needle second failure")
    victim_a = world.alice("failure")
    gate = threading.Event()
    entered = threading.Event()
    first_expand = {"seen": False}

    def run(root: Path, **kwargs: Any) -> Any:
        request = kwargs.get("request") or {}
        target = request.get("artifact_id") or request.get("id")
        if (
            kwargs.get("operation") == "expand"
            and target == victim_a
            and not first_expand["seen"]
        ):
            first_expand["seen"] = True
            entered.set()
            gate.wait(10)
        return MemoryTool().run(root, **kwargs)

    state, actions, _ = _tui(world, run)  # type: ignore[arg-type]
    _open_memory(state, actions)
    _to_subject(state, actions, "failure")
    assert [i for i, _v in _tui_ids(state)] == [victim_a, "alice-failure-2"]
    try:
        _dispatch_key(state, "x", actions)
        assert entered.wait(10), "A's expand never reached the worker"
        _dispatch_key(state, "down", actions)
        _dispatch_key(state, "x", actions)  # B supersedes A's in-flight read
        _settle(state, actions)
        assert state.memory_expanded is not None
        assert state.memory_expanded["id"] == "alice-failure-2"
        gate.set()
        time.sleep(0.2)
        for _ in range(10):
            _pump(state, actions)
            time.sleep(0.01)
        assert state.memory_expanded["id"] == "alice-failure-2", (
            "A's late page filled B"
        )
        assert "second failure" in json.dumps(state.memory_expanded)
        assert "needle failure alice" not in state.memory_expanded.get("content", "")
    finally:
        gate.set()

    # --- TUI: representation base64 -> utf8 re-requests and keys differ -------------
    recorder = Recorder()
    state, actions, recorder = _tui(world, recorder)
    _open_memory(state, actions)
    _to_subject(state, actions, "failure")
    _keys(state, actions, "x")
    base64_calls = recorder.of("expand")
    assert base64_calls and "representation" not in base64_calls[-1]["request"]
    assert state.memory_expanded is not None
    before_key = (
        state.memory_expanded["authority"],
        state.memory_expanded["representation"],
    )
    _keys(state, actions, "b")
    assert state.memory_representation == "utf8" and "utf8" in state.memory_message
    assert len(recorder.of("expand")) == len(base64_calls), "b sends no request"
    _keys(state, actions, "x")
    assert len(recorder.of("expand")) > len(base64_calls), (
        "utf8 must not reuse base64 pages"
    )
    assert recorder.of("expand")[-1]["request"]["representation"] == "utf8"
    assert state.memory_expanded is not None
    after_key = (
        state.memory_expanded["authority"],
        state.memory_expanded["representation"],
    )
    assert before_key[0] == after_key[0] and before_key[1] != after_key[1]
    assert after_key[1] == "utf8"


# =============================================================================
# R14 -- one store, two owners, seven subjects: CLI == TUI == MemoryTool
# =============================================================================


def _expand_text(raw: dict[str, Any]) -> str:
    item = raw["items"][0]
    if "content_base64" in item:
        return base64.b64decode(item["content_base64"]).decode("utf-8")
    return str(item["content_utf8"])


def test_t07_shared_user_journey(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(tmp_path)
    state, actions, recorder = _tui(world)
    _open_memory(state, actions)
    bob_ids = {world.bob(s) for s in SUBJECTS}
    outputs: list[str] = []

    for subject in SUBJECTS:
        oracle_pairs = _all_pages(world, subject)
        assert [p[0] for p in oracle_pairs] == [world.alice(subject)], subject
        listed = _cli(
            world, monkeypatch, "memory", "list", "--subject", subject, json_mode=True
        )
        assert listed.json is not None and listed.json["raw"]["code"] == "OK"
        outputs.append(listed.stdout)
        cli_pairs = _pairs(listed.json["raw"]["items"])
        _to_subject(state, actions, subject)
        tui_pairs = _tui_ids(state)
        assert cli_pairs == tui_pairs == oracle_pairs, subject
        assert (
            state.memory_view_state is not None
            and state.memory_view_state["state"] == "ok"
        )

        # The same selection expands to the same bytes on every surface.
        artifact_id, version = oracle_pairs[0]
        request = {
            "schema_version": 2,
            "artifact_id": artifact_id,
            "artifact_version": version,
        }
        oracle_expand = _raw(_oracle(world, "expand", request))
        assert oracle_expand["code"] == "OK", oracle_expand
        form = _input_file(tmp_path, f"expand-{subject}.json", request)
        via_cli = _cli(
            world, monkeypatch, "memory", "expand", "--input", str(form), json_mode=True
        )
        outputs.append(via_cli.stdout)
        assert via_cli.json is not None
        assert _scrub(via_cli.json["raw"]) == _scrub(oracle_expand), subject
        _keys(state, actions, "x")
        assert state.memory_expanded is not None, subject
        assert state.memory_expanded["id"] == artifact_id
        assert state.memory_expanded["version"] == version
        assert _expand_text(oracle_expand) in state.memory_expanded["content"], subject
        outputs.append(_render(state))

    # A CLI edit moves the row n -> n+1; a TUI refresh shows n+1 and never n.
    victim = world.alice("failure")
    edit = _input_file(
        tmp_path,
        "edit.json",
        {
            "schema_version": 2,
            "subject": "failure",
            "artifact_id": victim,
            "expected_version": 1,
            "owner_scope": ALICE.as_dict(),
            "content": {"text": "needle failure alice, second version"},
            "apply": True,
            **_ids(),
        },
    )
    edited = _cli(
        world,
        monkeypatch,
        "memory",
        "edit",
        "--input",
        str(edit),
        "--allow-cache-write",
        json_mode=True,
    )
    assert edited.json is not None and edited.json["raw"]["code"] == "OK", edited.output
    _to_subject(state, actions, "failure")
    _keys(state, actions, "/", "enter")
    assert (victim, 2) in _tui_ids(state)
    assert (victim, 1) not in _tui_ids(state)
    after_cli = _cli(
        world, monkeypatch, "memory", "list", "--subject", "failure", json_mode=True
    )
    assert after_cli.json is not None
    assert _pairs(after_cli.json["raw"]["items"]) == _tui_ids(state) == [(victim, 2)]
    outputs += [after_cli.stdout, _render(state)]

    # The dashboard memory API reports the same rows.
    dash = _dashboard(world)
    try:
        _, body = dash.snapshot("memory", subject="failure")
        outputs.append(json.dumps(body["data"]))
        assert _pairs(body["data"]["items"]) == [(victim, 2)]
    finally:
        dash.stop()

    for text in outputs:
        assert not any(bob in text for bob in bob_ids), "Bob's rows reached a surface"
    del recorder


# =============================================================================
# R15 / R16 -- hostile terminal text in the CLI and the TUI
# =============================================================================


def _expected_escape(text: str, index: int) -> str:
    """The §3.1 predicate for the character at `index` of `text`."""
    c = text[index]
    o = ord(c)
    nxt = text[index + 1] if index + 1 < len(text) else ""
    escaped = (
        o <= 0x08
        or o in (0x0B, 0x0C)
        or 0x0E <= o <= 0x1F
        or 0x7F <= o <= 0x9F
        or o in (0x061C, 0x200E, 0x200F)
        or 0x202A <= o <= 0x202E
        or 0x2066 <= o <= 0x2069
        or (o == 0x0D and nxt != "\n")
    )
    if not escaped:
        return c
    return f"\\x{o:02x}" if o <= 0xFF else f"\\u{o:04x}"


def _assert_clean(text: str, *, where: str) -> None:
    assert "\x1b" not in text, where
    assert "\x07" not in text, where
    assert "\u202e" not in text, where
    assert re.search(r"\r(?!\n)", text) is None, where


def test_t07_cli_human_hostile_terminal_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.theme import safe_terminal_text

    # The §3.1 predicate over every code point that could matter: C0, DEL, C1, the
    # bidi controls; TAB, LF and a CRLF's CR stay.
    for o in range(0x2200):
        c = chr(o)
        assert safe_terminal_text(c) == _expected_escape(c, 0), hex(o)
    assert safe_terminal_text("a\r\nb\tc") == "a\r\nb\tc"
    assert safe_terminal_text("a\rb") == "a\\x0db"
    assert safe_terminal_text(HOSTILE) == "\\x1b[2K\\x0d\\x07\\u202e"
    for o in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)):
        assert safe_terminal_text(chr(o)) == f"\\u{o:04x}", hex(o)
    assert safe_terminal_text(None) == ""

    world = _world(tmp_path, hostile=True)
    hostile = world.ids[("alice", "hostile")]
    # 72-T01: a row holding a bidi override is integrity-blocked from ordinary and
    # inspect reads; the historical view is where it is visible, and where it must
    # be shown as text.
    listed = _cli(
        world, monkeypatch, "memory", "list", "--subject", SUBJECT, "--include-archived"
    )
    assert listed.exit_code == 0, listed.output
    expand_form = _input_file(
        tmp_path,
        "expand.json",
        {
            "schema_version": 2,
            "artifact_id": hostile,
            "artifact_version": 1,
            "representation": "utf8",
            "archive_mode": "historical",
        },
    )
    expanded = _cli(world, monkeypatch, "memory", "expand", "--input", str(expand_form))
    assert expanded.exit_code == 0, expanded.output
    history = _cli(world, monkeypatch, "memory", "history", hostile, "--historical")
    assert history.exit_code == 0, history.output
    for label, result in (("list", listed), ("expand", expanded), ("history", history)):
        _assert_clean(result.output, where=label)
        for literal in HOSTILE_ESCAPES:
            assert literal in result.output, (label, literal, result.output)
        assert "hostilemarker" in result.output, label
    # The real trust label is shown once per row, from the projector's own field.
    assert listed.output.count("trust EXTERNAL_WRITE") == 2, listed.output
    assert listed.output.count("EXTERNAL_WRITE") == 2, listed.output
    assert history.output.count("trust EXTERNAL_WRITE") == 1, history.output
    # --json is the exact ToolResult: the raw bytes survive as JSON text, untouched.
    machine = _cli(
        world,
        monkeypatch,
        "memory",
        "list",
        "--subject",
        SUBJECT,
        "--include-archived",
        json_mode=True,
    )
    assert machine.json is not None
    texts = json.dumps(machine.json["raw"]["items"], ensure_ascii=False)
    assert "hostilemarker" in texts


def test_t07_tui_hostile_terminal_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    world = _world(tmp_path, hostile=True)
    hostile = world.ids[("alice", "hostile")]
    state, actions, _ = _tui(world)
    _open_memory(state, actions)
    # 72-T01: a row holding a bidi override is integrity-blocked from ordinary and
    # inspect reads; it is visible only in the historical view (`f`, tab to the
    # `archived` field, `true`, Enter), where the screen must show it as text.
    _keys(state, actions, "f", "tab", "tab", "tab", *"true", "enter")
    ids = [i for i, _v in _tui_ids(state)]
    state.memory_selected_index = ids.index(hostile)

    def terminal() -> tuple[str, str]:
        state.terminal_size = (200, 60)
        buffer = io.StringIO()
        console = Console(
            file=buffer,
            width=200,
            height=60,
            force_terminal=True,
            color_system="standard",
            record=True,
        )
        console.print(render_app(state))
        return buffer.getvalue(), console.export_text(styles=False)

    stages = {"list": None, "expand": "x", "history": "v"}
    for stage, key in stages.items():
        if key is not None:
            _keys(state, actions, key)
        stream, text = terminal()
        assert SGR.search(stream), (stage, "Rich's own styling must reach the stream")
        stripped = SGR.sub("", stream)
        _assert_clean(stripped, where=f"{stage} stream")
        _assert_clean(text, where=f"{stage} export")
        for literal in HOSTILE_ESCAPES:
            assert literal in text, (stage, literal)
        assert "hostilemarker" in text, stage
    assert "Memory history" in text
    _keys(state, actions, "E")
    stream, text = terminal()
    _assert_clean(SGR.sub("", stream), where="explain stream")
    _assert_clean(text, where="explain export")
    assert "Memory explain" in text


def test_t07_tui_table_marks_not_current_rows(tmp_path: Path) -> None:
    """72-T05 D3 (plan L849): the TUI memory table lists v2 inspect items; a row that
    is not usable as current carries its state (the applicability or `task_mismatch`
    reason) in the `state` column, where `freshness` alone reads `current`."""
    from rich.text import Text

    from rush.tui import _memory_list_layout

    state = TuiState(
        projects=[ProjectState(name="t07", root=tmp_path, project_id="t07")],
        data_root=tmp_path,
    )
    state.terminal_size = (200, 60)
    state.memory_items = [
        {
            **_item(artifact_id, 1, freshness="current"),
            "usable_as_current": not reasons,
            "reason_codes": reasons,
        }
        for artifact_id, reasons in (
            ("act", []),
            ("rej", ["applicability_rejected"]),
            ("pen", ["applicability_pending"]),
            ("tsk", ["task_mismatch"]),
        )
    ]
    console = Console(width=200, file=io.StringIO(), record=True)
    console.print(*_memory_list_layout(state, [], [Text("")]))
    text = console.export_text(styles=False)
    rows = {
        artifact_id: next(line for line in text.splitlines() if artifact_id in line)
        for artifact_id in ("act", "rej", "pen", "tsk")
    }
    assert "state" in text, text
    assert re.search(r"\brejected\b", rows["rej"]), text
    assert re.search(r"\bpending\b", rows["pen"]), text
    assert re.search(r"\btask_mismatch\b", rows["tsk"]), text
    assert not re.search(r"rejected|pending|task_mismatch", rows["act"]), text


# =============================================================================
# FAMILIES, projectors, explain and the no-auto-approval contract
# =============================================================================

_FAMILY_EXPECTED: dict[str, str] = {
    "overview": "collection",
    **dict.fromkeys(("ask", "list", "recall", "related"), "memory_collection"),
    **dict.fromkeys(
        (
            "expand",
            "prepare",
            "resume",
            "intent",
            "recipe",
            "plan_checks",
            "last_success_diagnose",
            "preference",
            "capsule",
        ),
        "memory_inspection",
    ),
    "history": "memory_history",
    "explain": "memory_explain",
    **dict.fromkeys(
        (
            "write",
            "promote",
            "maintain",
            "link",
            "consolidate",
            "handoff",
            "receive",
            "delete",
            "edit",
            "archive",
            "verify_attempt",
        ),
        "memory_mutation",
    ),
}


def _captured_render(monkeypatch: pytest.MonkeyPatch, result: dict[str, Any]) -> str:
    from rush import theme

    buffer = io.StringIO()
    monkeypatch.setattr(
        theme,
        "_shared_console",
        Console(file=buffer, width=200, theme=theme.RUSH_THEME, force_terminal=False),
    )
    theme.render_result(result)
    return buffer.getvalue()


def test_t07_memory_families_cover_every_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rush import theme
    from rush.tools.memory import VALID_OPERATIONS

    assert len(_FAMILY_EXPECTED) == 27
    actual = {
        op: family
        for (tool, op), family in theme.FAMILIES.items()
        if tool == "memory" and op is not None
    }
    assert actual == _FAMILY_EXPECTED
    assert set(VALID_OPERATIONS) | {"overview"} <= set(actual), (
        "an operation is unmapped"
    )
    # The 26 operations at T07 start (22 at HEAD plus preference from T05, history and
    # explain from T06, capsule from CODEC) are exactly the mapped ones: a producer
    # operation missing from VALID_OPERATIONS, or a mapping with no operation behind
    # it, is a drifted family table.
    assert set(VALID_OPERATIONS) == set(_FAMILY_EXPECTED) - {"overview"}, sorted(
        set(VALID_OPERATIONS) ^ (set(_FAMILY_EXPECTED) - {"overview"})
    )
    for family in (
        "memory_collection",
        "memory_inspection",
        "memory_history",
        "memory_explain",
        "memory_mutation",
    ):
        assert family in theme._PROJECTORS, family
    for operation, family in _FAMILY_EXPECTED.items():
        projector = theme._projection("memory", operation)
        assert projector is theme.FAMILY_PROJECTIONS[("memory", operation)], operation
        if family != "memory_inspection":
            assert projector is not theme._inspection, f"{operation} fell back"
    # The shapes the projectors render: a v2 collection, an expansion page, history
    # versions, an explain bucket set and a mutation receipt.
    ref = _item(
        "a1",
        2,
        source="s1",
        subject="failure",
        owner_scope={"kind": "user", "id": "alice"},
    )
    collection = _result("OK", items=[{**ref, "excerpt": "an excerpt"}], complete=False)
    collection["raw"]["next_cursor"] = "CURSOR1"
    text = _captured_render(monkeypatch, collection)
    assert re.search(
        r"a1@v2\s+subject failure\s+owner user:alice\s+source s1\s+trust EXTERNAL_WRITE\s+freshness current",
        text,
    ), text
    assert "next page: rerun with --cursor CURSOR1" in text
    assert f"cite a1@v2 sha256:{'0' * 64}" in text
    assert "an excerpt" in text

    body = b"exact page bytes"
    expansion = _result(
        "OK",
        operation="expand",
        items=[
            {
                **_item("a1", 1, payload_hash=hashlib.sha256(body).hexdigest()),
                "content_base64": base64.b64encode(body).decode(),
                "offset": 0,
                "next_offset": 5,
                "complete": False,
                "total_bytes": len(body),
            }
        ],
    )
    text = _captured_render(monkeypatch, expansion)
    assert re.search(r"a1@v1\s+bytes 0\.\.5 of 16\s+representation base64", text), text
    assert "exact page bytes" in text
    assert "next page: rush memory expand --input FILE" in text

    versions = _result(
        "OK",
        operation="history",
        items=[],
        versions=[
            {
                **_item("a1", 1),
                "integrity": "verified",
                "freshness": "current",
                "reason_codes": [],
                "content_utf8": "first",
            },
            {
                # The version's own labels win over the current row's (reference).
                **_item("a1", 2, integrity="verified", freshness="current"),
                "integrity": "backfilled",
                "freshness": "stale",
                "reason_codes": ["stale"],
                "content_utf8": "second",
            },
        ],
    )
    text = _captured_render(monkeypatch, versions)
    assert text.index("a1@v1") < text.index("a1@v2"), "history is oldest first"
    line = next(row for row in text.splitlines() if "a1@v2" in row)
    assert "integrity backfilled" in line and "freshness stale" in line, line
    assert "integrity verified" not in line, line
    assert "trust EXTERNAL_WRITE" in line, line
    assert "first" in text and "second" in text

    receipt = _result("OK", operation="edit", items=[_item("a1", 3)], complete=False)
    receipt["raw"]["data"] = {"receipt": {"invocation_id": "i", "effect_id": "e"}}
    text = _captured_render(monkeypatch, receipt)
    assert "committed: a1@v3" in text and "next: rush memory history a1" in text

    denied = _result("E_PERMISSION", reason="revoked", operation="list")
    text = _captured_render(monkeypatch, denied)
    assert "state: revoked" in text and "action:" in text, text


def test_t07_explain_buckets_cli_and_tui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world(tmp_path)
    target = world.alice("architectural_decision")
    support = world.alice("domain_knowledge")
    tried = world.alice("failure")
    contra = "alice-contra"
    _write(world.store, contra, ALICE, SUBJECT, "needle contradicting evidence")
    edges = (
        (target, support, "depends_on"),
        (target, tried, "caused_by"),
        (contra, target, "contradicts"),
    )
    for source, dest, kind in edges:
        linked = _oracle(
            world,
            "link",
            {
                "schema_version": 2,
                "source_id": source,
                "source_version": 1,
                "target_id": dest,
                "target_version": 1,
                "kind": kind,
                "owner_scope": ALICE.as_dict(),
                "apply": True,
                **_ids(),
            },
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert _code(linked) == "OK", linked

    oracle = _raw(
        _oracle(world, "explain", {"schema_version": 2, "artifact_id": target})
    )
    assert oracle["code"] == "OK", oracle

    def refs(bucket: str) -> set[str]:
        return {e["reference"]["artifact_id"] for e in oracle[bucket]}

    assert refs("supporting") == {support, tried}
    assert refs("contrary") == {contra}
    assert refs("attempted") == {tried}
    assert refs("affected") == {support, tried, contra}
    assert "no_recorded_rationale" not in oracle["unknowns"]

    # CLI: JSON equals MemoryTool; human output names every bucket and cited record.
    machine = _cli(world, monkeypatch, "memory", "explain", target, json_mode=True)
    assert machine.json is not None and _scrub(machine.json["raw"]) == _scrub(oracle)
    human = _cli(world, monkeypatch, "memory", "explain", target)
    out = human.output
    order = [
        out.index(h)
        for h in (
            "why (supporting)",
            "contrary",
            "what tried (attempted)",
            "affected code refs",
            "unknowns",
        )
    ]
    assert order == sorted(order), out
    for ident in (support, tried, contra):
        assert ident in out, (ident, out)
    assert re.search(rf"{support}@v1\s+source {SOURCE}\s+freshness \S+", out), out
    assert "stale:" in out
    assert "why: unknown" not in out

    # An absent rationale is `unknown`, never invented text.
    lonely = world.alice("skill_pattern")
    bare = _cli(world, monkeypatch, "memory", "explain", lonely, json_mode=True)
    assert bare.json is not None
    assert bare.json["raw"]["supporting"] == [] and bare.json["raw"]["unknowns"] == [
        "no_recorded_rationale"
    ]
    bare_human = _cli(world, monkeypatch, "memory", "explain", lonely)
    assert "why: unknown (no recorded rationale)" in bare_human.output
    assert bare_human.output.count("none recorded") >= 3, bare_human.output

    # TUI: `E` explains the selected row; a row with no relations says unknown.
    state, actions, recorder = _tui(world)
    _open_memory(state, actions)
    _to_subject(state, actions, "architectural_decision")
    _keys(state, actions, "E")
    explain_calls = recorder.of("explain")
    assert explain_calls and explain_calls[-1]["request"] == {
        "schema_version": 2,
        "artifact_id": target,
    }
    assert state.memory_explained is not None
    rendered = _render(state)
    assert "Memory explain" in rendered
    for heading in ("supporting", "contrary", "attempted", "affected"):
        assert heading in rendered, (heading, rendered)
    for ident in (support, tried, contra):
        assert ident in rendered, (ident, rendered)
    _to_subject(state, actions, "skill_pattern")
    _keys(state, actions, "E")
    assert "unknown" in _render(state)
    # No row and an empty query: a message, no request.
    state.memory_items = []
    count = len(recorder.of("explain"))
    _keys(state, actions, "E")
    assert state.memory_message == "select a row or search first"
    assert len(recorder.of("explain")) == count
    # No row but a typed query: query mode.
    state.memory_query_buffer = "needle"
    _keys(state, actions, "E")
    assert recorder.of("explain")[-1]["request"] == {
        "schema_version": 2,
        "query": "needle",
    }


def test_t07_no_auto_approval_or_read_side_init(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    grant_calls: list[str] = []
    for name in ("grant_memory_scope", "revoke_memory_scope"):
        real = getattr(auth, name)

        def spy(*args: Any, _real: Any = real, _name: str = name, **kwargs: Any) -> Any:
            grant_calls.append(_name)
            return _real(*args, **kwargs)

        monkeypatch.setattr(auth, name, spy)

    for grant in (False, True):
        world = _virgin(tmp_path, grant=grant, name=f"virgin-{grant}")
        grant_calls.clear()
        policy = auth.policy_path(data_root=world.data_root)
        policy_existed = policy.exists()
        data_before = _tree(world.data_root)
        rush_dir = world.root / ".rush"
        rush_existed = rush_dir.exists()
        root_before = _tree(world.root)

        def untouched(
            where: str,
            world: World = world,
            rush_dir: Path = rush_dir,
            rush_existed: bool = rush_existed,
            root_before: dict[str, str] = root_before,
        ) -> None:
            assert rush_dir.exists() == rush_existed, where
            assert _tree(world.root) == root_before, where
            assert not (rush_dir / "memory.db").exists(), where

        forms = tmp_path / f"forms-{grant}"
        forms.mkdir()
        form = _input_file(
            forms,
            "f.json",
            {"schema_version": 2, "artifact_id": "nope", "artifact_version": 1},
        )

        # CLI reads on a project with no store: no `.rush`, no data-root file.
        for args in (
            ("memory", "list", "--source", SOURCE),
            ("memory", "history", "nope"),
            ("memory", "explain", "nope"),
            ("memory", "expand", "--input", str(form)),
            ("memory", "related", "--input", str(form)),
        ):
            _cli(world, monkeypatch, *args)
        browse = _cli(world, monkeypatch, "memory", "list", json_mode=True)
        assert browse.json is not None, browse.output
        if grant:
            # An authorized browse of a project with no store is an empty page.
            assert browse.json["raw"]["code"] == "OK", browse.json
            assert browse.json["raw"]["items"] == []
        else:
            # No policy: the D1 denial with a concrete next step, never a silent grant.
            assert browse.json["raw"]["code"] == "E_PERMISSION", browse.json
            assert browse.json["raw"]["data"]["reason"] == "policy_missing"
        untouched("a CLI read initialized the project")

        # TUI reads: browse, expand, history, explain, page, search.
        state, actions, recorder = _tui(world)
        _open_memory(state, actions)
        _keys(state, actions, "x", "v", "E", "S", "/", "enter", "I", "escape")
        untouched("a TUI read initialized the project")

        # Dashboard reads and a v2 preview.
        dash = _dashboard(world)
        try:
            dash.snapshot("memory")
            dash.snapshot("map")
            dash.action(
                "memory_query",
                {
                    "schema_version": 2,
                    "mode": "list",
                    "subjects": [SUBJECT],
                    "query": "",
                },
            )
            status, body = dash.action(
                "memory_propose",
                {
                    "schema_version": 2,
                    "subject": SUBJECT,
                    "content": {"text": "preview only"},
                    "source": SOURCE,
                    "owner_scope": ALICE.as_dict(),
                    "apply": False,
                },
            )
            # An explicit `apply: false` is a preview: no cache_write grant needed.
            assert status == 200, body
            assert body["data"]["raw"]["code"] in ("OK", "E_PERMISSION", "E_OWNER"), (
                body
            )
            if grant:
                assert body["data"]["raw"]["code"] == "OK", body
        finally:
            dash.stop()
        untouched("a dashboard read initialized the project")
        assert _tree(world.data_root) == data_before, "a read route wrote the data root"

        # Nothing approved anything: no grant writer ran, the grant set is the test's.
        assert grant_calls == [], f"a read route wrote a grant: {grant_calls}"
        assert policy.exists() == policy_existed
        grants = auth.load_policy_readonly(data_root=world.data_root)["grants"]
        assert len(grants) == (1 if grant else 0), grants
        for key in ("y", "enter", "y"):  # stray confirm keys approve nothing
            _keys(state, actions, key)
        assert recorder.applies() == []
        assert len(
            auth.load_policy_readonly(data_root=world.data_root)["grants"]
        ) == len(grants)


# =============================================================================
# G3 -- first filesystem effect of every T07 route
# =============================================================================


def _inventory(world: World) -> tuple[dict[str, str], dict[str, str], bool]:
    return _tree(world.root), _tree(world.data_root), (world.root / ".rush").exists()


def _spy_route_access(
    monkeypatch: pytest.MonkeyPatch, world: World
) -> list[dict[str, Any]]:
    """Record, per `route_access` call, whether it granted and whether the project's
    memory.db already existed at that moment."""
    import importlib

    from rush.memory import retrieval

    real = retrieval.route_access
    db = world.root / ".rush" / "memory.db"
    events: list[dict[str, Any]] = []

    def spy(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        events.append(
            {
                "granted": not isinstance(result, retrieval.RouteDenial),
                "db_exists": db.exists(),
            }
        )
        return result

    monkeypatch.setattr(retrieval, "route_access", spy)
    for name in ("rush.tools.memory", "rush.tui", "rush.dashboard.server"):
        module = importlib.import_module(name)
        if hasattr(module, "route_access"):
            monkeypatch.setattr(module, "route_access", spy)
    return events


def _every_read_route(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, label: str
) -> None:
    forms = tmp_path / f"reads-{label}"
    forms.mkdir()
    form = _input_file(
        forms,
        "read.json",
        {"schema_version": 2, "artifact_id": "nope", "artifact_version": 1},
    )
    for args in (
        ("memory", "list"),
        ("memory", "list", "--subject", SUBJECT, "--query", "needle"),
        ("memory", "expand", "--input", str(form)),
        ("memory", "related", "--input", str(form)),
        ("memory", "history", "nope"),
        ("memory", "explain", "nope"),
    ):
        _cli(world, monkeypatch, *args)
    state, actions, _ = _tui(world)
    _open_memory(state, actions)
    _keys(
        state,
        actions,
        "x",
        "v",
        "E",
        "S",
        "]",
        "[",
        "/",
        "enter",
        "f",
        "escape",
        "I",
        "escape",
    )
    from rush import tui as tui_mod

    tui_mod._load_map_snapshot(state.active_project, world.data_root)
    dash = _dashboard(world)
    try:
        dash.snapshot("memory")
        dash.snapshot("memory", subject=SUBJECT, query="needle")
        dash.snapshot("memory", expand_id="nope", expand_version="1")
        dash.snapshot("memory", related_id="nope", related_version="1")
        dash.snapshot("map")
        for act_name, act_args in (
            (
                "memory_query",
                {
                    "schema_version": 2,
                    "mode": "list",
                    "subjects": [SUBJECT],
                    "query": "",
                },
            ),
            (
                "memory_expand",
                {"schema_version": 2, "artifact_id": "nope", "artifact_version": 1},
            ),
            (
                "memory_edit",
                {
                    "schema_version": 2,
                    "subject": SUBJECT,
                    "artifact_id": "nope",
                    "expected_version": 1,
                    "owner_scope": ALICE.as_dict(),
                    "content": {"text": "x"},
                    "apply": False,
                },
            ),
            (
                "memory_maintain",
                {
                    "schema_version": 2,
                    "task": "expiry_sweep",
                    "owner_scope": ALICE.as_dict(),
                    "apply": False,
                },
            ),
        ):
            dash.action(act_name, act_args)
    finally:
        dash.stop()


def test_t07_first_effect_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Reads and previews: no constructor with a filesystem effect runs on a virgin
    # project, whether the grant is absent, present or revoked (a denial opens nothing).
    for label in ("legacy", "granted", "revoked"):
        world = _virgin(tmp_path, grant=label != "legacy", name=f"g3-{label}")
        if label == "revoked":
            _revoke(world)
        before = _inventory(world)
        _every_read_route(world, tmp_path, monkeypatch, label)
        assert _inventory(world) == before, f"{label}: a read or preview wrote a file"
        assert not (world.root / ".rush" / "memory.db").exists(), label
        assert not (world.root / ".rush" / "telemetry").exists(), label
        if label == "revoked":
            # A denial wins over the absent store: never reported as absent or empty.
            listed = _cli(world, monkeypatch, "memory", "list", json_mode=True)
            assert listed.json is not None
            assert listed.json["raw"]["code"] == "E_PERMISSION", listed.json
            assert listed.json["raw"]["data"]["reason"] == "revoked"
            denied_dash = _dashboard(world)
            try:
                _, body = denied_dash.snapshot("memory")
                assert body["data"]["ui_state"]["state"] == "revoked", body["data"]
            finally:
                denied_dash.stop()
            denied_tui, denied_actions, _ = _tui(world)
            _open_memory(denied_tui, denied_actions)
            view = getattr(denied_tui, "memory_view_state", None) or {}
            assert view.get("state") == "revoked", view

    # TUI apply: the writer runs only after route_access granted, and the store did
    # not exist at that moment.
    world = _virgin(tmp_path, grant=True, name="g3-tui-apply")
    db = world.root / ".rush" / "memory.db"
    events = _spy_route_access(monkeypatch, world)
    state, actions, recorder = _tui(world)
    _open_memory(state, actions)
    _keys(state, actions, "n")
    assert state.mode == "memory_create", state.mode
    state.memory_create_buffer = {
        "subject": SUBJECT,
        "source": SOURCE,
        "content": "created by the tui",
    }
    _keys(state, actions, "enter")
    assert state.memory_pending_mutation is not None, state.memory_message
    assert not db.exists(), "the preview created the store"
    seen = len(events)
    _keys(state, actions, "y")
    assert db.exists(), state.memory_message
    applied = events[seen:]
    assert applied, "the apply never resolved access"
    assert any(e["granted"] and not e["db_exists"] for e in applied), applied
    assert len(recorder.applies()) == 1

    # Dashboard apply:true: the same order.
    world = _virgin(tmp_path, grant=True, name="g3-dash-apply")
    db = world.root / ".rush" / "memory.db"
    events = _spy_route_access(monkeypatch, world)
    dash = _dashboard(world)
    try:
        status, body = dash.action(
            "memory_propose",
            {
                "schema_version": 2,
                "subject": SUBJECT,
                "content": {"text": "created by the dashboard"},
                "source": SOURCE,
                "owner_scope": ALICE.as_dict(),
                "apply": True,
                **_ids(),
            },
            grants=WRITE,
        )
        assert status == 200 and body["data"]["raw"]["code"] == "OK", body
    finally:
        dash.stop()
    assert db.exists()
    assert any(e["granted"] and not e["db_exists"] for e in events), events

    # An apply that route_access denies creates nothing.
    world = _virgin(tmp_path, grant=True, name="g3-denied-apply")
    _revoke(world)
    before = _inventory(world)
    dash = _dashboard(world)
    try:
        status, body = dash.action(
            "memory_propose",
            {
                "schema_version": 2,
                "subject": SUBJECT,
                "content": {"text": "never written"},
                "source": SOURCE,
                "owner_scope": ALICE.as_dict(),
                "apply": True,
                **_ids(),
            },
            grants=WRITE,
        )
        assert body["data"]["ui_state"]["state"] == "revoked", body
    finally:
        dash.stop()
    assert _inventory(world) == before


# =============================================================================
# G4 -- trust-boundary inputs: exact outcomes, only declared exceptions escape
# =============================================================================

_BAD_IDENTS = ("a\x00b", "\ud800", "a\u202eb", "a\x07b")  # NUL, lone surrogate, Cf, Cc


def _no_traceback(result: Any, where: str) -> None:
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        where,
        repr(result.exception),
    )


def _body_error(body: dict[str, Any]) -> str | None:
    error = body.get("error")
    return error.get("code") if isinstance(error, dict) else None


@pytest.mark.parametrize(
    "platform_case",
    [
        pytest.param("common", id="common"),
        pytest.param("symlink_loop", marks=pytest.mark.posix_only, id="symlink_loop"),
    ],
)
def test_t07_g4_trust_boundary_inputs(
    platform_case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if platform_case == "symlink_loop":
        # POSIX only: a capsule path that is a symlink to itself is refused by name.
        world = _world(tmp_path)
        state, actions, _ = _tui(world)
        _open_memory(state, actions)
        pristine_db = world.db_sha()
        loop = tmp_path / "loop.json"
        loop.symlink_to(loop)
        _keys(state, actions, "I")
        assert state.mode == "memory_import", state.mode
        _type(state, actions, str(loop))
        _keys(state, actions, "enter")
        assert state.memory_import_preview is None
        assert re.search(r"invalid|denied|refused|unreadable", state.memory_message), (
            state.memory_message
        )
        _keys(state, actions, "escape")
        assert state.mode == "memory" and state.memory_focus == "list"
        assert world.db_sha() == pristine_db
        return
    world = _world(tmp_path, extra_domain=24)
    calls = _spy_memory_tool(monkeypatch)
    pristine = (_tree(world.root), world.db_sha(), _tree(world.data_root))

    # ---------------- CLI ----------------
    for owner in ("robot:x", "user", "user:", "user: "):
        calls.clear()
        result = _cli(world, monkeypatch, "memory", "list", "--owner", owner)
        assert result.exit_code == 2 and "--owner" in result.output, (
            owner,
            result.output,
        )
        assert calls == [], owner
    for ident in _BAD_IDENTS:
        calls.clear()
        result = _cli(world, monkeypatch, "memory", "list", "--owner", f"user:{ident}")
        _no_traceback(result, f"owner {ident!r}")
        assert result.exit_code == 2, (ident, result.exit_code, result.output)
        assert "state: invalid" in result.output, (ident, result.output)
    for subject in ("nonsense",):
        for args in ((subject,), ("--subject", subject)):
            result = _cli(world, monkeypatch, "memory", "list", *args)
            assert result.exit_code == 2, args
    for source in ("", "a*b", "x\x00", "\ud800"):
        calls.clear()
        result = _cli(
            world, monkeypatch, "memory", "list", "--source", source, json_mode=True
        )
        _no_traceback(result, f"source {source!r}")
        assert result.exit_code == 2, (source, result.exit_code, result.output)
        assert result.json is not None and result.json["raw"]["code"] == "E_INPUT", (
            source
        )
    first = _cli(
        world, monkeypatch, "memory", "list", "--subject", SUBJECT, json_mode=True
    )
    assert first.json is not None
    cursor = first.json["raw"]["next_cursor"]
    assert isinstance(cursor, str)
    for value in ("", "not-a-cursor", "\x00"):
        result = _cli(
            world, monkeypatch, "memory", "list", "--cursor", value, json_mode=True
        )
        _no_traceback(result, f"cursor {value!r}")
        assert result.exit_code == 2, (value, result.output)
        assert result.json is not None and result.json["raw"]["code"] == "E_INPUT", (
            value
        )
    # A cursor from another subject or query is a changed binding: E_RESTART.
    for bound_args in (
        ("--subject", "failure"),
        ("--subject", SUBJECT, "--query", "needle"),
    ):
        result = _cli(
            world,
            monkeypatch,
            "memory",
            "list",
            *bound_args,
            "--cursor",
            cursor,
            json_mode=True,
        )
        assert result.json is not None and result.json["raw"]["code"] == "E_RESTART", (
            bound_args
        )
        assert result.exit_code == 1
    for query in ("\x00", "\ud800", "x" * 10**6):
        result = _cli(
            world, monkeypatch, "memory", "list", "--query", query, json_mode=True
        )
        _no_traceback(result, f"query {query[:8]!r}")
    assert (_tree(world.root), world.db_sha(), _tree(world.data_root)) == pristine, (
        "a refused CLI input changed state"
    )

    # ---------------- TUI ----------------
    state, actions, recorder = _tui(world)
    _open_memory(state, actions)
    victim_ids = _tui_ids(state)
    assert victim_ids, "the TUI listed nothing"
    for ident in _BAD_IDENTS:
        state.memory_filter_owner = f"user:{ident}"
        _keys(state, actions, "/", "enter")
        assert state.memory_view_state is not None
        assert state.memory_view_state["state"] == "invalid", (
            ident,
            state.memory_view_state,
        )
        assert state.memory_items == []
        assert state.memory_filter_owner == f"user:{ident}", "the owner filter was lost"
    state.memory_filter_owner = "no-colon-owner"
    _keys(state, actions, "/", "enter")
    assert (
        state.memory_view_state is not None
        and state.memory_view_state["state"] == "invalid"
    )
    state.memory_filter_owner = None
    for ident in _BAD_IDENTS:
        state.mode = "memory_search"
        state.memory_query_buffer = f"needle{ident}"
        _keys(state, actions, "enter")
        assert state.memory_query_buffer == f"needle{ident}", (
            "the typed search was lost"
        )
        assert state.memory_view_state is not None
        assert state.memory_view_state["state"] in (
            "invalid",
            "empty",
            "ok",
            "partial",
            "server_error",
        ), (ident, state.memory_view_state)
        assert isinstance(state.memory_message, str) and state.memory_message
    state.memory_query_buffer = ""
    _keys(state, actions, "/", "enter")
    assert _tui_ids(state) == victim_ids
    _to_subject(state, actions, SUBJECT)
    state.memory_selected_index = 0
    for ident in _BAD_IDENTS:
        _keys(state, actions, "c")
        assert state.mode == "memory_correct", state.mode
        buffer = {"kind": "correct", "reason": f"why{ident}", "content": "changed text"}
        state.memory_correction_buffer = dict(buffer)
        _keys(state, actions, "enter")
        assert state.memory_correction_buffer == buffer, "the typed correction was lost"
        assert state.memory_pending_mutation is None
        assert "invalid" in state.memory_message.lower(), (ident, state.memory_message)
        _keys(state, actions, "escape")
        assert state.mode == "memory"
    assert recorder.applies() == []
    assert world.db_sha() == pristine[1], "a refused TUI input wrote"

    capsule_dir = tmp_path / "capsules"
    capsule_dir.mkdir()
    (capsule_dir / "dir").mkdir()
    (capsule_dir / "non-utf8.json").write_bytes(b"\xff\xfe\x00junk")
    (capsule_dir / "bom.json").write_bytes(b"\xef\xbb\xbf{}")
    for name in ["missing.json", "dir", "non-utf8.json", "bom.json"]:
        _keys(state, actions, "I")
        assert state.mode == "memory_import", state.mode
        _type(state, actions, str(capsule_dir / name))
        _keys(state, actions, "enter")
        assert state.memory_import_preview is None, name
        assert state.memory_import_buffer == str(capsule_dir / name), (
            "the typed path was lost"
        )
        assert re.search(r"invalid|denied|refused|unreadable", state.memory_message), (
            name,
            state.memory_message,
        )
        _keys(state, actions, "escape")
        assert state.mode == "memory" and state.memory_focus == "list"
    assert world.db_sha() == pristine[1]

    # Moved root / non-path data root: D1 `unavailable`, `denied`, nothing created.
    moved = _world(tmp_path, name="to-move")
    state, actions, _ = _tui(moved)
    new_root = moved.root.parent / "moved-away"
    moved.root.rename(new_root)
    _open_memory(state, actions)
    assert state.memory_view_state is not None
    assert state.memory_view_state["state"] == "denied", state.memory_view_state
    assert "project_missing" in state.memory_view_state["reason"]
    assert not moved.root.exists(), "a TUI read recreated the moved root"
    broken, actions, _ = _tui(_world(tmp_path, name="bad-data-root"))
    broken.data_root = 12345  # type: ignore[assignment]
    _open_memory(broken, actions)
    assert broken.memory_view_state is not None
    assert broken.memory_view_state["state"] == "denied", broken.memory_view_state
    assert "data_root_unavailable" in broken.memory_view_state["reason"]
    variant = _world(tmp_path, name="CaseVariant")
    state, actions, _ = _tui(variant)
    state.projects[0].root = Path(str(variant.root).swapcase())
    before_variant = _inventory(variant)
    _open_memory(state, actions)
    assert state.memory_view_state is not None
    assert state.memory_view_state["state"] == "denied", state.memory_view_state
    assert _inventory(variant) == before_variant

    # ---------------- dashboard GET ----------------
    dash = _dashboard(world)
    try:
        for limit in ("1e3", "NaN", "inf", "-1", "0", "101", "9" * 400):
            _, body = dash.snapshot("memory", subject=SUBJECT, limit=limit)
            data = body["data"]
            assert data["ui_state"]["state"] == "invalid", (limit, data["ui_state"])
            assert data["list"]["raw"]["code"] == "E_INPUT", limit
            assert data["items"] == []
        for bad_query in (
            {"owner": "robot:x"},
            {"owner": "user:"},
            {"subject": "nonsense"},
            {"cursor": "AAAA"},
            {"cursor": "!!!not-base64!!!"},
        ):
            _, body = dash.snapshot("memory", **{"subject": SUBJECT, **bad_query})
            assert body["data"]["ui_state"]["state"] == "invalid", (
                bad_query,
                body["data"]["ui_state"],
            )
            assert body["data"]["list"]["raw"]["code"] == "E_INPUT", bad_query
        # The mutation id strings and the booleans.
        target = world.alice("failure")
        edit = {
            "schema_version": 2,
            "subject": "failure",
            "artifact_id": target,
            "expected_version": 1,
            "owner_scope": ALICE.as_dict(),
            "content": {"text": "never applied"},
            "apply": False,
        }
        for name, action, base in (
            ("apply", "memory_edit", edit),
            (
                "archived",
                "memory_archive",
                {
                    "schema_version": 2,
                    "subject": "failure",
                    "artifact_id": target,
                    "expected_version": 1,
                    "owner_scope": ALICE.as_dict(),
                    "apply": False,
                },
            ),
            (
                "user_stated",
                "memory_promote",
                {
                    "schema_version": 2,
                    "subject": "failure",
                    "artifact_id": target,
                    "expected_version": 1,
                    "owner_scope": ALICE.as_dict(),
                    "apply": False,
                },
            ),
        ):
            for bad in (1, "false", None):
                status, body = dash.action(action, {**base, name: bad}, grants=WRITE)
                assert status == 400 and _body_error(body) == "malformed_request", (
                    action,
                    name,
                    bad,
                    status,
                    body,
                )
        for field in ("limit", "max_bytes", "max_tokens"):
            for bad_value in (True, 1.5, "2048", None, float("inf")):
                status, body = dash.action(
                    "memory_query",
                    {
                        "schema_version": 2,
                        "mode": "list",
                        "subjects": [SUBJECT],
                        "query": "",
                        field: bad_value,
                    },
                )
                assert status == 200, (field, bad_value, status, body)
                assert body["data"]["raw"]["code"] == "E_INPUT", (
                    field,
                    bad_value,
                    body,
                )
        for bad_owner in ({"kind": ["user"], "id": "a"}, {"kind": "user"}):
            status, body = dash.action(
                "memory_edit", {**edit, "owner_scope": bad_owner}
            )
            assert status == 400, (bad_owner, status, body)
            status, body = dash.action(
                "memory_query",
                {
                    "schema_version": 2,
                    "mode": "list",
                    "subjects": [SUBJECT],
                    "query": "",
                    "owner_scope": bad_owner,
                },
            )
            assert body["data"]["raw"]["code"] == "E_INPUT", (bad_owner, body)
        for ident in ("\ud800", "a\x00b"):
            status, body = dash.action(
                "memory_expand",
                {"schema_version": 2, "artifact_id": ident, "artifact_version": 1},
            )
            assert body["data"]["raw"]["code"] == "E_INPUT", (ident, body)
        # Correction cardinality, version range, mixed forms and kinds: the strict model
        # refuses each with E_INPUT and nothing is written.
        ref = {"artifact_id": target, "artifact_version": 1}
        correction_base = {
            "schema_version": 2,
            "subject": "failure",
            "artifact_id": target,
            "expected_version": 1,
            "owner_scope": ALICE.as_dict(),
            "apply": False,
        }

        def corrected(kind: str = "correct", **overrides: Any) -> dict[str, Any]:
            body = {"kind": kind, "reason": "a reason", "supersedes": [ref]}
            body.update(overrides)
            return {"correction": body}

        refused_corrections = {
            "reject_with_content": {**corrected("reject"), "content": {"text": "x"}},
            "no_supersedes": corrected(supersedes=[]),
            "duplicate_refs": corrected(supersedes=[ref, dict(ref)]),
            "too_many_refs": corrected(
                supersedes=[
                    {"artifact_id": f"x{i}", "artifact_version": 1} for i in range(65)
                ]
            ),
            "version_zero": corrected(
                supersedes=[{"artifact_id": target, "artifact_version": 0}]
            ),
            "version_beyond_sqlite": corrected(
                supersedes=[{"artifact_id": target, "artifact_version": 2**63}]
            ),
            "reason_with_format_char": corrected(reason="a\u202eb"),
            "empty_reason": corrected(reason=""),
            "unknown_kind": corrected("erase"),
            "mixed_legacy_keys": {
                "scope": "failure",
                "id": target,
                "content": {"text": "x"},
            },
        }
        guarded = world.db_sha()
        for label, extra in refused_corrections.items():
            status, body = dash.action("memory_edit", {**correction_base, **extra})
            assert status == 200, (label, status, body)
            assert body["data"]["raw"]["code"] == "E_INPUT", (
                label,
                body["data"]["raw"],
            )
        status, body = dash.action(
            "memory_edit", {**correction_base, **corrected(reason="fine")}
        )
        assert body["data"]["raw"]["code"] == "OK", ("correct without content", body)
        # An apply names its invocation and effect together.
        for label, ids_given in (
            ("neither", {}),
            ("invocation only", {"invocation_id": uuid.uuid4().hex}),
            ("effect only", {"effect_id": uuid.uuid4().hex}),
        ):
            status, body = dash.action(
                "memory_edit",
                {
                    **correction_base,
                    "content": {"text": "never applied"},
                    "apply": True,
                    **ids_given,
                },
                grants=WRITE,
            )
            assert body["data"]["raw"]["code"] == "E_INPUT", (
                label,
                body["data"]["raw"],
            )
        assert world.db_sha() == guarded, "a refused correction or identity wrote"
        # The smallest admitted frame still carries the stamps: one byte is refused with
        # the minimum, and exactly that minimum succeeds.
        small = {
            "schema_version": 2,
            "mode": "list",
            "subjects": [SUBJECT],
            "query": "",
            "max_bytes": 1,
            "max_tokens": 1,
        }
        status, body = dash.action("memory_query", small)
        # 72-T02 D35: caps below the smallest response are `E_INPUT` naming the floor.
        assert status == 200 and body["data"]["raw"]["code"] == "E_INPUT", body
        required = body["data"]["raw"]["data"]["required"]
        smallest_bytes = required.get("max_bytes", required.get("bytes"))
        smallest_tokens = required.get("max_tokens", required.get("tokens"))
        assert isinstance(smallest_bytes, int) and isinstance(smallest_tokens, int)
        status, body = dash.action(
            "memory_query",
            {**small, "max_bytes": smallest_bytes, "max_tokens": smallest_tokens},
        )
        # Exactly the floor admits the smallest frame (the stamped `E_BUDGET` refusal:
        # no row fits yet), and that frame carries the stamps.
        assert body["data"]["raw"]["code"] == "E_BUDGET", body["data"]["raw"]
        assert "ui_state" in body["data"] and "memory_view_key" in body["data"]
        # Ample caps return the page with the same stamps.
        status, body = dash.action(
            "memory_query", {**small, "max_bytes": 65536, "max_tokens": 16384}
        )
        assert body["data"]["raw"]["code"] == "OK", body["data"]["raw"]
        assert "ui_state" in body["data"] and "memory_view_key" in body["data"]
        # A non-UTF-8 body is a 400 before any dispatch.
        resp = _http(
            "POST",
            f"{dash.base}/api/projects/{dash.project_id}/actions",
            {
                "Cookie": dash.cookie,
                "X-Rush-CSRF": dash.csrf,
                "Origin": dash.base,
                "Content-Type": "application/json",
            },
            b"\xff\xfe\x00not utf-8",
        )
        assert resp.status == 400
        # A moved project root: the registry still names the old path.
        gone = _world(tmp_path, name="dash-moved")
        gone_dash = _dashboard(gone)
        try:
            gone.root.rename(gone.root.parent / "dash-moved-away")
            _, body = gone_dash.snapshot("memory")
            assert body["data"]["ui_state"]["state"] == "denied", body["data"][
                "ui_state"
            ]
            assert body["data"]["items"] == []
            assert not gone.root.exists()
        finally:
            gone_dash.stop()
    finally:
        dash.stop()
    assert world.db_sha() == pristine[1], "a refused dashboard input wrote"


# =============================================================================
# R7 / G2 -- the route x mode matrix
# =============================================================================
#
# Cell id grammar (T09 section 3.6): `<transport>.<route>[-<dim>-<value>...]-<dim>-<value>`,
# tokens joined by `-`, `_` inside a token. The T07 rows are the entry points of plan
# section 2.3 that this task owns: CLI `list` (three forms), `expand`, `related`,
# `history`, `explain`, `edit`, `archive`, `delete`; the TUI actions; the dashboard GET
# readers (`dashboard_readers`) and the dashboard POST actions (`dashboard`).
#
# Every cell builds its own world, runs the row's real transport once, and asserts the
# G2 outcome for its (dimension, value): a healthy result equal to what `MemoryTool`
# returns for the same request, a D19 denial with its next action, the distinct
# store state, the strict-model/allowlist refusal for a field the route does not
# accept, or byte-identical output where the transport has no such field. Nothing is a
# producer-staged `E_INPUT`.

DIMENSIONS: dict[str, tuple[str, ...]] = {
    "access": ("policy", "legacy_allowlist", "overlay"),
    "policy_state": ("missing_no_marker", "missing_marker", "ok", "invalid"),
    "mode": ("ordinary", "inspect", "historical"),
    "representation": ("base64", "utf8"),
    "retrieval": ("lexical", "hybrid"),
    "store": ("present", "absent", "old_schema"),
    "apply": ("preview", "apply"),
    "cache_write": ("on", "off"),
    "grant_ops": ("exact", "missing_one"),
    "row_state": ("active", "archived", "expired", "rejected", "pending", "tampered"),
    "ack": ("ack", "no_ack"),
    "capability_ids": ("selected", "unselected"),
}
OK_STATES = ("ok", "partial", "empty")
PRODUCT_STATES = (
    "server_error",
    "absent",
    "migration_required",
    "corrupt",
    "busy",
    "conflict",
    "restart",
    "partial",
    "not_visible",
    "invalid",
    "revoked",
    "expired",
    "denied",
    "digest_mismatch",
    "empty",
    "ok",
)


@dataclasses.dataclass
class Obs:
    state: str | None = None
    code: str | None = None
    reason: str | None = None
    ids: list[tuple[str, int]] | None = None
    next_action: dict[str, Any] | None = None
    http: int | None = None
    error: str | None = None
    exit_code: int | None = None
    wrote: bool = False
    traceback: bool = False
    content: bytes | None = None
    payload_hash: str | None = None
    note: str = ""


def _mini_state(raw: dict[str, Any], *, http: int | None = None) -> str:
    """The section 3.2 mapping for the codes this matrix meets, independent of
    `memory_ui_state`."""
    code = raw.get("code") if isinstance(raw, dict) else None
    reason = _reason({"raw": raw}) if isinstance(raw, dict) else None
    if code in (None, "OK") and not raw:
        return "server_error" if http and http >= 500 else "ok"
    table = {
        "E_MIGRATION": "migration_required",
        "E_SCHEMA_UNSUPPORTED": "migration_required",
        "E_STORE_CORRUPT": "corrupt",
        "E_STORE_BUSY": "busy",
        "E_VERSION": "conflict",
        "E_RESTART": "restart",
        "E_BUDGET": "partial",
        "E_NOT_VISIBLE": "not_visible",
        "E_INPUT": "invalid",
        "E_OFFSET": "invalid",
        "E_OWNER": "denied",
        "E_SCOPE": "denied",
    }
    if code in table:
        return table[code]
    if code == "E_PERMISSION":
        return reason if reason in ("revoked", "expired") else "denied"
    if code == "OK":
        items = raw.get("items") or raw.get("versions") or []
        if not items and raw.get("operation") in ("list", "ask", "recall", "history"):
            return "empty"
        if raw.get("complete") is False and raw.get("operation") in (
            "list",
            "ask",
            "recall",
        ):
            return "partial"
        return "ok"
    return "server_error"


@dataclasses.dataclass
class Plan:
    policy: str = "ok"  # ok | legacy | marker | invalid
    store: str = "present"  # present | absent | old_schema
    drop_ops: tuple[str, ...] = ()
    fields: dict[str, Any] = dataclasses.field(default_factory=dict)
    overlay: bool = False
    apply: bool | None = None  # None: the row's own default (a mutation applies)
    cache_write: bool = True
    row_state: str = "active"
    # healthy | denied | absent | migration | boundary | identical | stateful | historical
    expect: str = "healthy"
    reason: str | None = None
    action: bool = False  # the denial must carry a next action


@dataclasses.dataclass
class Env:
    world: World
    monkeypatch: pytest.MonkeyPatch
    tmp_path: Path
    plan: Plan
    owner: OwnerScope | None = None

    @property
    def fields(self) -> dict[str, Any]:
        return self.plan.fields

    subject: str = SUBJECT

    @property
    def target(self) -> str:
        return self.world.alice(self.subject)


@dataclasses.dataclass(frozen=True)
class MRow:
    transport: str
    route: str
    extra: tuple[tuple[str, str], ...]
    kind: str  # read | mutation | map
    surface: str  # flags | request
    fields: frozenset[str]
    grant_op: str
    drive: Callable[[Env], Obs]
    legacy: str  # healthy | denied | stateful: the outcome in D1 legacy mode
    absent: tuple[str, ...] = ("absent", "empty", "not_visible")
    subject: str = SUBJECT
    t08_owned: bool = False  # list/query reads: their hybrid cell is 72-T08's
    extra_domain: int = 0  # more rows, so a second page exists

    def ident(self) -> str:
        extra = "".join(f"-{k}-{v}" for k, v in self.extra)
        return f"{self.transport}.{self.route}{extra}"


# --- world construction for one cell ------------------------------------------


def _build_world(
    tmp_path: Path, plan: Plan, extra_domain: int = 0, name: str = "project"
) -> World:
    ops = tuple(op for op in GRANT_OPS if op not in plan.drop_ops)
    has_grant = plan.policy != "legacy"
    if plan.store == "absent":
        world = _virgin(tmp_path, grant=False, name=name)
        if has_grant:
            world.grant = _grant(world.root, ALICE, ops=ops)
    else:
        world = _world(
            tmp_path, grant=has_grant, ops=ops, extra_domain=extra_domain, name=name
        )
    if plan.policy == "marker":
        auth.policy_path(data_root=world.data_root).unlink()
    elif plan.policy == "invalid":
        auth.policy_path(data_root=world.data_root).write_bytes(b"{")
    if plan.store == "old_schema":
        db = world.root / ".rush" / "memory.db"
        with contextlib.closing(sqlite3.connect(db)) as conn:
            for table in ("memory_artifacts", "memory_artifact_versions"):
                for column in ("payload_hash", "payload_hash_origin"):
                    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()
    return world


def _apply_row_state(world: World, target: str, state: str) -> None:
    store = world.store
    if state == "active":
        return
    row = store.get_current_row(target)
    assert row is not None, target
    if state == "archived":
        store.archive(
            target,
            expected_version=1,
            scope=row["subject"],
            owner_scope=ALICE,
            apply=True,
        )
        return
    db = world.root / ".rush" / "memory.db"
    if state == "expired":
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET expired_at = ? WHERE id = ?", (1.0, target)
            )
            conn.commit()
    elif state == "tampered":
        with contextlib.closing(sqlite3.connect(db)) as conn:
            (raw,) = conn.execute(
                "SELECT content FROM memory_artifacts WHERE id = ?", (target,)
            ).fetchone()
            content = json.loads(raw)
            content["tampered"] = True
            conn.execute(
                "UPDATE memory_artifacts SET content = ? WHERE id = ?",
                (json.dumps(content), target),
            )
            conn.commit()
    elif state == "rejected":
        result = _oracle(
            world,
            "edit",
            {
                "schema_version": 2,
                "subject": row["subject"],
                "artifact_id": target,
                "expected_version": 1,
                "owner_scope": ALICE.as_dict(),
                "correction": {
                    "kind": "reject",
                    "reason": "matrix: rejected",
                    "supersedes": [{"artifact_id": target, "artifact_version": 1}],
                },
                "apply": True,
                **_ids(),
            },
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert _code(result) == "OK", _raw(result)
    elif state == "pending":
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET applicability = 'pending' WHERE id = ?",
                (target,),
            )
            conn.commit()


# --- observation helpers ----------------------------------------------------------


def _wrote(world: World, before: tuple[Any, ...]) -> bool:
    return _footprint(world) != before


def _footprint(world: World) -> tuple[Any, ...]:
    db = world.root / ".rush" / "memory.db"
    sha = hashlib.sha256(db.read_bytes()).hexdigest() if db.exists() else None
    return (sha, _tree(world.root))


def _cli_obs(
    env: Env,
    args: list[str],
    before: tuple[Any, ...],
    *,
    on_raw: Callable[[dict[str, Any], Obs], None] | None = None,
) -> Obs:
    result = _cli(env.world, env.monkeypatch, *args, json_mode=True)
    obs = Obs(exit_code=result.exit_code)
    obs.traceback = not (
        result.exception is None or isinstance(result.exception, SystemExit)
    )
    payload = result.json
    if payload is None:
        obs.state = "server_error"
        obs.note = result.output[-300:]
    else:
        raw: dict[str, Any] = (
            payload["raw"] if isinstance(payload.get("raw"), dict) else {}
        )
        obs.code = raw.get("code")
        obs.reason = _reason({"raw": raw})
        if raw:
            obs.state = _mini_state(raw)
        else:
            obs.state = (
                "denied" if payload.get("status") == "skipped" else "server_error"
            )
        action = raw.get("next_action")
        obs.next_action = action if isinstance(action, dict) else None
        if on_raw is not None:
            on_raw(raw, obs)
    obs.wrote = _wrote(env.world, before)
    return obs


def _list_ids(raw: dict[str, Any], obs: Obs) -> None:
    obs.ids = [_identity(item) for item in raw.get("items", [])]


def _version_ids(raw: dict[str, Any], obs: Obs) -> None:
    obs.ids = [
        (v["reference"]["artifact_id"], v["reference"]["artifact_version"])
        for v in raw.get("versions", [])
    ]


def _expand_raw(raw: dict[str, Any], obs: Obs) -> None:
    items = raw.get("items") or []
    data = raw.get("data")
    legacy: dict[str, Any] = data if isinstance(data, dict) else {}
    if raw.get("code") == "OK" and not items and "id" in legacy and "version" in legacy:
        # The dashboard section reads the exact version with the legacy request
        # (`{"id", "version"}`), whose page names the same record and bytes.
        if "content_base64" in legacy:
            obs.content = base64.b64decode(legacy["content_base64"])
        obs.ids = [(legacy["id"], legacy["version"])]
        return
    if items:
        item = items[0]
        if "content_base64" in item:
            obs.content = base64.b64decode(item["content_base64"])
        elif "content_utf8" in item:
            obs.content = str(item["content_utf8"]).encode("utf-8")
        obs.payload_hash = (item.get("reference") or {}).get("payload_hash")
        obs.ids = [_identity(item)]


def _owner_dict(env: Env) -> dict[str, str]:
    owner = env.owner or ALICE
    return owner.as_dict()


# --- drivers: one per T07-owned entry point ------------------------------------------


def _owner_field(env: Env) -> dict[str, Any]:
    return {"owner_scope": env.owner.as_dict()} if env.owner is not None else {}


def _owner_arg(env: Env) -> list[str]:
    return ["--owner", f"{env.owner.kind}:{env.owner.id}"] if env.owner else []


def _does_apply(env: Env) -> bool:
    return True if env.plan.apply is None else env.plan.apply


# ---- CLI


def _cli_list(form: str) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        before = _footprint(env.world)
        args = ["memory", "list"]
        if form == "positional":
            args += [SUBJECT, "needle"]
        elif form == "options":
            args += ["--subject", SUBJECT, "--query", "needle"]
        if env.fields.get("archive_mode") == "historical":
            args.append("--include-archived")
        args += _owner_arg(env)
        return _cli_obs(env, args, before, on_raw=_list_ids)

    return drive


def _cli_history(env: Env) -> Obs:
    before = _footprint(env.world)
    args = ["memory", "history", env.target]
    if env.fields.get("archive_mode") == "historical":
        args.append("--historical")
    return _cli_obs(env, args, before, on_raw=_version_ids)


def _cli_explain(env: Env) -> Obs:
    before = _footprint(env.world)
    return _cli_obs(env, ["memory", "explain", env.target], before)


def _cli_read_leaf(leaf: str) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        before = _footprint(env.world)
        version = 1
        if leaf == "related":
            # A traversal starts from the seed's current version; an archived seed
            # is already at its archive version (72-T03: a stale seed is not visible).
            store = env.world.store
            row = store.get_current_row(env.target) if store is not None else None
            version = int(row["artifact_version"]) if row is not None else 1
        request = {
            "schema_version": 2,
            "artifact_id": env.target,
            "artifact_version": version,
            **_owner_field(env),
            **env.fields,
        }
        form = _input_file(env.tmp_path, f"{leaf}.json", request)
        return _cli_obs(
            env,
            ["memory", leaf, "--input", str(form)],
            before,
            on_raw=_expand_raw if leaf == "expand" else _list_ids,
        )

    return drive


def _mutation_body(action: str, env: Env) -> dict[str, Any]:
    """The schema-2 request each mutation row sends (without `apply`/ids)."""
    target = env.world.alice("failure")
    owner = _owner_dict(env)
    bodies: dict[str, dict[str, Any]] = {
        "edit": {
            "schema_version": 2,
            "subject": "failure",
            "artifact_id": target,
            "expected_version": 1,
            "owner_scope": owner,
            "content": {"text": "needle matrix edit"},
        },
        "archive": {
            "schema_version": 2,
            "subject": "failure",
            "artifact_id": target,
            "expected_version": 1,
            "archived": True,
            "owner_scope": owner,
        },
        "delete": {
            "schema_version": 2,
            "subject": "failure",
            "artifact_ids": [target],
            "expected_revisions": {target: 1},
            "owner_scope": owner,
        },
        "promote": {
            "schema_version": 2,
            "subject": "failure",
            "artifact_id": target,
            "expected_version": 1,
            "user_stated": True,
            "owner_scope": owner,
        },
        "write": {
            "schema_version": 2,
            "subject": SUBJECT,
            "content": {"text": "needle matrix write"},
            "source": SOURCE,
            "owner_scope": owner,
        },
        "maintain": {
            "schema_version": 2,
            "task": "expiry_sweep",
            "batch_size": 10,
            "owner_scope": owner,
        },
    }
    return dict(bodies[action])


def _full_request(action: str, env: Env) -> dict[str, Any]:
    request = _mutation_body(action, env)
    for key, value in env.fields.items():
        if key != "apply":
            request[key] = value
    if env.owner is not None:
        request["owner_scope"] = env.owner.as_dict()
    request["apply"] = _does_apply(env)
    if request["apply"]:
        request.update(_ids())
    return request


def _cli_mutation(leaf: str, action: str) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        before = _footprint(env.world)
        request = _full_request(action, env)
        if "apply" in env.fields:
            request["apply"] = env.fields["apply"]
        form = _input_file(env.tmp_path, f"{leaf}.json", request)
        args = ["memory", leaf, "--input", str(form)]
        if _does_apply(env) and env.plan.cache_write:
            args.append("--allow-cache-write")
        return _cli_obs(env, args, before)

    return drive


# ---- TUI


def _tui_open(env: Env, *, pages: bool = False) -> tuple[TuiState, Any, Recorder]:
    owner = (env.owner.kind, env.owner.id) if env.owner else ("user", "alice")
    state, actions, recorder = _tui(env.world, owner=owner)
    if (
        env.fields.get("archive_mode") == "historical"
        and env.plan.expect != "identical"
    ):
        # Only a route that takes `archive_mode` views the archived rows (its plan
        # expects the historical view or, without the grant, a denial); for any
        # other the field is refused input (`identical`) and the view stays ordinary.
        state.memory_filter_archived = True
    if env.owner is not None:
        state.memory_filter_owner = f"{env.owner.kind}:{env.owner.id}"
    _keys(state, actions, "f3", "4")
    return state, actions, recorder


def _tui_select(state: TuiState, actions: Any, subject: str, target: str) -> bool:
    if state.memory_subject != subject:
        _to_subject(state, actions, subject)
    ids = [i for i, _v in _tui_ids(state)]
    if target in ids:
        state.memory_selected_index = ids.index(target)
        return True
    return False


def _message_state(message: str) -> str:
    """The state a TUI status line names, for an outcome that has no list refresh of
    its own (an expansion, a panel or an apply refused after the list loaded)."""
    text = message.lower()
    if "promotion denied: insufficient_corroboration" in text:
        # 72-T04: the corroboration rule declining a candidate is the promotion's
        # own answer (a candidate is written), not an access denial.
        return "server_error"
    for needle, state in (
        ("revoked", "revoked"),
        ("expired", "expired"),
        ("operation_not_granted", "denied"),
        ("denied", "denied"),
        ("not granted", "denied"),
        ("e_permission", "denied"),
        ("not_visible", "not_visible"),
        ("migration", "migration_required"),
        ("invalid", "invalid"),
        ("e_input", "invalid"),
        ("conflict", "conflict"),
        ("e_version", "conflict"),
    ):
        if needle in text:
            return state
    return "server_error"


def _tui_obs(env: Env, state: TuiState, before: tuple[Any, ...]) -> Obs:
    ui = getattr(state, "memory_view_state", None) or {}
    action = ui.get("next_action")
    return Obs(
        state=ui.get("state"),
        reason=ui.get("reason"),
        next_action=action if isinstance(action, dict) else None,
        ids=_tui_ids(state),
        wrote=_wrote(env.world, before),
    )


def _tui_outcome(obs: Obs, state: TuiState, shown: bool) -> None:
    """Fold the outcome of the key just pressed into `obs`: shown content is `ok`; a
    refusal after a healthy list is classified from the status line."""
    if shown:
        obs.state = "ok" if obs.state in (None, *OK_STATES) else obs.state
        return
    if obs.state in (None, *OK_STATES):
        message = state.memory_message or ""
        obs.state = _message_state(message)
        obs.reason = message
        obs.ids = []
        if "rush memory grant" in message:
            obs.next_action = {"command": "rush memory grant"}


def _tui_refresh(env: Env) -> Obs:
    before = _footprint(env.world)
    state, _actions, _ = _tui_open(env)
    return _tui_obs(env, state, before)


def _tui_paging(env: Env) -> Obs:
    before = _footprint(env.world)
    state, actions, _ = _tui_open(env)
    first = _tui_ids(state)
    obs = _tui_obs(env, state, before)
    if getattr(state, "memory_cursor_next", None) is not None:
        _keys(state, actions, "]")
        second = _tui_ids(state)
        assert not set(first) & set(second), "a page repeated a row"
        _keys(state, actions, "[")
        assert _tui_ids(state) == first, "[ must return to the first page"
        obs = _tui_obs(env, state, before)
    return obs


def _tui_expand(env: Env) -> Obs:
    before = _footprint(env.world)
    state, actions, _ = _tui_open(env)
    if env.fields.get("representation") == "utf8":
        _keys(state, actions, "b")
    _tui_select(state, actions, SUBJECT, env.target)
    _keys(state, actions, "x")
    obs = _tui_obs(env, state, before)
    expanded = state.memory_expanded
    if expanded is not None:
        obs.content = base64.b64decode(expanded["content_bytes_base64"])
        obs.ids = [(expanded["id"], expanded["version"])]
    _tui_outcome(obs, state, expanded is not None)
    return obs


def _tui_panel(key: str, attr: str) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        before = _footprint(env.world)
        state, actions, _ = _tui_open(env)
        _tui_select(state, actions, SUBJECT, env.target)
        _keys(state, actions, key)
        obs = _tui_obs(env, state, before)
        panel = getattr(state, attr, None)
        if panel is not None:
            raw = _raw(panel["result"])
            if attr == "memory_history":
                _version_ids(raw, obs)
            if raw.get("code") not in (None, "OK"):
                obs.state = _mini_state(raw)
                obs.reason = _reason({"raw": raw})
                obs.ids = []
                action = raw.get("next_action")
                obs.next_action = action if isinstance(action, dict) else None
                return obs
        _tui_outcome(obs, state, panel is not None)
        return obs

    return drive


def _tui_mutation(action: str) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        before = _footprint(env.world)
        state, actions, recorder = _tui_open(env)
        subject = SUBJECT if action == "propose" else "failure"
        target = env.world.alice("failure")
        selected = _tui_select(state, actions, subject, target)
        if action == "propose":
            _keys(state, actions, "n")
            state.memory_create_buffer = {
                "subject": SUBJECT,
                "source": SOURCE,
                "content": "needle matrix create",
            }
            _keys(state, actions, "enter")
        elif action == "correction":
            _keys(state, actions, "c")
            if state.mode == "memory_correct":
                state.memory_correction_buffer = {
                    "kind": "correct",
                    "reason": "matrix correction",
                    "content": "needle matrix corrected",
                }
                _keys(state, actions, "enter")
        elif action == "import":
            _keys(state, actions, "I")
            _type(state, actions, str(env.tmp_path / "no-such-capsule.json"))
            _keys(state, actions, "enter", "escape")
        else:
            keys = {
                "edit": ["e", *"matrix edit", "enter"],
                "archive": ["a"],
                "delete": ["d"],
                "promote": ["p"],
                "maintain": ["w"],
            }[action]
            if selected or action == "maintain":
                _keys(state, actions, *keys)
        pending = (
            state.memory_pending_mutation is not None
            or bool(state.memory_pending_maintain)
            or state.memory_pending_delete is not None
        )
        if _does_apply(env) and pending:
            _keys(state, actions, "y")
        elif pending:
            _keys(state, actions, "escape")
        obs = _tui_obs(env, state, before)
        obs.note = "applied" if recorder.applies() else ("pending" if pending else "")
        if recorder.applies() and obs.state in (None, *OK_STATES):
            message = state.memory_message or ""
            failed = _message_state(message)
            if failed != "server_error":
                obs.state, obs.reason, obs.ids = failed, message, []
                if "rush memory grant" in message:
                    obs.next_action = {"command": "rush memory grant"}
        return obs

    return drive


def _tui_map(env: Env) -> Obs:
    from rush import tui as tui_mod
    from rush.workflows import projects as wp

    before = _footprint(env.world)
    env.monkeypatch.setattr(
        wp,
        "project_map_snapshot",
        lambda record, run_id, attempt_id: {"available": True},
    )
    project = ProjectState(
        name="t07", root=env.world.root, project_id=env.world.project_id
    )
    snapshot = tui_mod._load_map_snapshot(project, env.world.data_root)
    obs = Obs(wrote=_wrote(env.world, before))
    obs.state = "ok" if snapshot and snapshot.get("available") else "denied"
    obs.reason = (snapshot or {}).get("reason")
    return obs


# ---- dashboard


def _dash_obs(
    env: Env, dash: Dash, status: int, body: dict[str, Any], before: tuple[Any, ...]
) -> Obs:
    obs = Obs(http=status, wrote=_wrote(env.world, before))
    error = body.get("error")
    if isinstance(error, dict):
        obs.error = error.get("code")
        obs.state = "invalid" if status == 400 else "denied"
        return obs
    data = body.get("data") or {}
    ui = data.get("ui_state") or {}
    obs.state = ui.get("state")
    obs.reason = ui.get("reason")
    action = ui.get("next_action")
    obs.next_action = action if isinstance(action, dict) else None
    raw: dict[str, Any] = data["raw"] if isinstance(data.get("raw"), dict) else {}
    obs.code = raw.get("code") or (data.get("list") or {}).get("raw", {}).get("code")
    return obs


def _dash_reader(surface: str) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        before = _footprint(env.world)
        dash = _dashboard(env.world)
        try:
            params: dict[str, str] = {"subject": SUBJECT}
            if surface == "memory_query":
                params["query"] = "needle"
            if env.fields.get("archive_mode") == "historical":
                params["include_archived"] = "true"
            if env.owner is not None:
                params["owner"] = f"{env.owner.kind}:{env.owner.id}"
            if surface == "expand_id":
                params.update({"expand_id": env.target, "expand_version": "1"})
            elif surface == "related_id":
                params.update({"related_id": env.target, "related_version": "1"})
            status, body = dash.snapshot("memory", **params)
            obs = _dash_obs(env, dash, status, body, before)
            data = body.get("data") or {}
            if surface in ("memory_browse", "memory_query"):
                obs.ids = [_identity(i) for i in data.get("items", [])]
                return obs
            inner = data.get("expand" if surface == "expand_id" else "related") or {}
            raw = _raw(inner)
            obs.code = raw.get("code")
            if surface == "expand_id":
                _expand_raw(raw, obs)
            if (
                raw
                and raw.get("code") not in (None, "OK")
                and obs.state in (None, *OK_STATES)
            ):
                obs.state = _mini_state(raw)
                obs.reason = _reason({"raw": raw})
                obs.ids = []
                action = raw.get("next_action")
                obs.next_action = action if isinstance(action, dict) else None
            return obs
        finally:
            dash.stop()

    return drive


def _dash_map(historical: bool) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        from rush.dashboard import server as server_module

        before = _footprint(env.world)
        dash = _dashboard(env.world)
        try:
            if historical:
                builds: list[int] = []
                memories = [{"id": env.world.alice(s)} for s in SUBJECTS]

                def build(
                    root: Path, pid: str, record: Any, run_id: str, attempt: Any
                ) -> Any:
                    builds.append(1)
                    return {"memories": memories, "root": str(root)}, True

                env.monkeypatch.setattr(
                    server_module, "_build_historical_map_snapshot", build
                )
                record = dash.ctx.projects.get(env.world.project_id)
                manifest = env.world.root / server_module._MANIFEST_RELATIVE.format(
                    run_id="run-1", attempt_id="att-1"
                )
                manifest.parent.mkdir(parents=True, exist_ok=True)
                manifest.write_text("{}", encoding="utf-8")
                before = _footprint(env.world)
                snapshot = server_module._historical_map_snapshot_reused(
                    dash.ctx,
                    env.world.root,
                    env.world.project_id,
                    record,
                    "run-1",
                    "att-1",
                )
                mapped = {m["id"] for m in (snapshot or {}).get("memories", [])}
            else:
                with contextlib.suppress(Exception):
                    server_module._refresh_project_memories(
                        dash.ctx, env.world.project_id, env.world.root
                    )
                _, body = dash.snapshot("map")
                mapped = _map_ids(body)
            obs = Obs(wrote=_wrote(env.world, before))
            obs.ids = sorted((i, 0) for i in mapped if i.startswith("alice-"))
            obs.state = "ok" if obs.ids else "denied"
            return obs
        finally:
            dash.stop()

    return drive


def _dash_post(
    action: str, build: Callable[[Env], dict[str, Any]], *, mutation: bool
) -> Callable[[Env], Obs]:
    def drive(env: Env) -> Obs:
        before = _footprint(env.world)
        dash = _dashboard(env.world)
        try:
            args = build(env)
            applying = mutation and _does_apply(env)
            grants = WRITE if (applying and env.plan.cache_write) else {}
            status, body = dash.action(action, args, grants=grants)
            obs = _dash_obs(env, dash, status, body, before)
            data = body.get("data") or {}
            raw = _raw(data)
            if raw.get("items"):
                if action == "memory_expand":
                    _expand_raw(raw, obs)
                else:
                    obs.ids = [_identity(i) for i in raw["items"]]
            elif action == "memory_query" and raw.get("code") == "OK":
                obs.ids = []  # a page with no rows is an empty page, not an unread one
            if "versions" in raw:
                _version_ids(raw, obs)
            return obs
        finally:
            dash.stop()

    return drive


def _post_query(env: Env) -> dict[str, Any]:
    args: dict[str, Any] = {
        "schema_version": 2,
        "mode": "list",
        "subjects": [SUBJECT],
        "query": "needle",
        **_owner_field(env),
    }
    args.update(env.fields)
    return args


def _post_expand(env: Env) -> dict[str, Any]:
    args: dict[str, Any] = {
        "schema_version": 2,
        "artifact_id": env.target,
        "artifact_version": 1,
        **_owner_field(env),
    }
    args.update(env.fields)
    return args


def _post_mutation(action: str) -> Callable[[Env], dict[str, Any]]:
    def build(env: Env) -> dict[str, Any]:
        request = _full_request(action, env)
        if "apply" in env.fields:
            request["apply"] = env.fields["apply"]
        return request

    return build


# --- the rows ---------------------------------------------------------------------------


def _mk(
    transport: str,
    route: str,
    extra: tuple[tuple[str, str], ...],
    kind: str,
    surface: str,
    fields: set[str],
    grant_op: str,
    drive: Callable[[Env], Obs],
    legacy: str,
    **more: Any,
) -> MRow:
    return MRow(
        transport,
        route,
        extra,
        kind,
        surface,
        frozenset(fields),
        grant_op,
        drive,
        legacy,
        **more,
    )


ROWS: list[MRow] = [
    _mk(
        "cli",
        "list",
        (("form", "no_args"),),
        "read",
        "flags",
        {"archive_mode"},
        "list",
        _cli_list("no_args"),
        "denied",
        absent=("empty",),
        t08_owned=True,
    ),
    _mk(
        "cli",
        "list",
        (("form", "positional"),),
        "read",
        "flags",
        {"archive_mode"},
        "list",
        _cli_list("positional"),
        "denied",
        absent=("empty",),
        t08_owned=True,
    ),
    _mk(
        "cli",
        "list",
        (("form", "options"),),
        "read",
        "flags",
        {"archive_mode"},
        "list",
        _cli_list("options"),
        "denied",
        absent=("empty",),
        t08_owned=True,
    ),
    _mk(
        "cli",
        "expand",
        (),
        "read",
        "request",
        {"archive_mode", "representation"},
        "expand",
        _cli_read_leaf("expand"),
        "denied",
    ),
    _mk(
        "cli",
        "related",
        (),
        "read",
        "request",
        {"archive_mode"},
        "ask",
        _cli_read_leaf("related"),
        "denied",
    ),
    _mk(
        "cli",
        "history",
        (),
        "read",
        "flags",
        {"archive_mode"},
        "history",
        _cli_history,
        "denied",
    ),
    _mk("cli", "explain", (), "read", "flags", set(), "ask", _cli_explain, "denied"),
    _mk(
        "cli",
        "edit",
        (),
        "mutation",
        "request",
        {"apply"},
        "write",
        _cli_mutation("edit", "edit"),
        "denied",
    ),
    _mk(
        "cli",
        "archive",
        (),
        "mutation",
        "request",
        {"apply"},
        "write",
        _cli_mutation("archive", "archive"),
        "denied",
    ),
    _mk(
        "cli",
        "delete",
        (),
        "mutation",
        "request",
        {"apply"},
        "write",
        _cli_mutation("delete", "delete"),
        "denied",
    ),
    _mk(
        "tui",
        "tui",
        (("action", "refresh"),),
        "read",
        "flags",
        {"archive_mode"},
        "list",
        _tui_refresh,
        "healthy",
        absent=("absent",),
        t08_owned=True,
    ),
    _mk(
        "tui",
        "tui",
        (("action", "paging"),),
        "read",
        "flags",
        set(),
        "list",
        _tui_paging,
        "healthy",
        absent=("absent",),
        t08_owned=True,
        extra_domain=24,
    ),
    _mk(
        "tui",
        "tui",
        (("action", "expand"),),
        "read",
        "flags",
        {"representation"},
        "expand",
        _tui_expand,
        "healthy",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "history"),),
        "read",
        "flags",
        {"archive_mode"},
        "history",
        _tui_panel("v", "memory_history"),
        "healthy",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "explain"),),
        "read",
        "flags",
        set(),
        "ask",
        _tui_panel("E", "memory_explained"),
        "healthy",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "correction"),),
        "mutation",
        "flags",
        {"apply"},
        "write",
        _tui_mutation("correction"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "edit"),),
        "mutation",
        "flags",
        {"apply"},
        "write",
        _tui_mutation("edit"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "archive"),),
        "mutation",
        "flags",
        {"apply"},
        "write",
        _tui_mutation("archive"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "delete"),),
        "mutation",
        "flags",
        {"apply"},
        "write",
        _tui_mutation("delete"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "promote"),),
        "mutation",
        "flags",
        {"apply"},
        "write",
        _tui_mutation("promote"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "maintain"),),
        "mutation",
        "flags",
        {"apply"},
        "write",
        _tui_mutation("maintain"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "propose"),),
        "mutation",
        "flags",
        {"apply"},
        "write",
        _tui_mutation("propose"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "import"),),
        "mutation",
        "flags",
        set(),
        "list",
        _tui_mutation("import"),
        "stateful",
        absent=("absent",),
    ),
    _mk(
        "tui",
        "tui",
        (("action", "map"),),
        "map",
        "flags",
        set(),
        "list",
        _tui_map,
        "healthy",
    ),
    _mk(
        "dashboard",
        "dashboard_readers",
        (("surface", "memory_browse"),),
        "read",
        "flags",
        {"archive_mode"},
        "list",
        _dash_reader("memory_browse"),
        "healthy",
        absent=("absent",),
        t08_owned=True,
    ),
    _mk(
        "dashboard",
        "dashboard_readers",
        (("surface", "memory_query"),),
        "read",
        "flags",
        {"archive_mode"},
        "list",
        _dash_reader("memory_query"),
        "healthy",
        absent=("absent",),
        t08_owned=True,
    ),
    _mk(
        "dashboard",
        "dashboard_readers",
        (("surface", "expand_id"),),
        "read",
        "flags",
        set(),
        "expand",
        _dash_reader("expand_id"),
        "healthy",
        absent=("absent", "not_visible"),
    ),
    _mk(
        "dashboard",
        "dashboard_readers",
        (("surface", "related_id"),),
        "read",
        "flags",
        set(),
        "ask",
        _dash_reader("related_id"),
        "healthy",
        absent=("absent", "not_visible"),
    ),
    _mk(
        "dashboard",
        "dashboard_readers",
        (("surface", "map_current"),),
        "map",
        "flags",
        set(),
        "list",
        _dash_map(False),
        "healthy",
    ),
    _mk(
        "dashboard",
        "dashboard_readers",
        (("surface", "map_historical"),),
        "map",
        "flags",
        set(),
        "list",
        _dash_map(True),
        "healthy",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_query"), ("op", "list")),
        "read",
        "request",
        {"archive_mode", "retrieval"},
        "list",
        _dash_post("memory_query", _post_query, mutation=False),
        "denied",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_expand"), ("op", "expand")),
        "read",
        "request",
        {"archive_mode", "representation"},
        "expand",
        _dash_post("memory_expand", _post_expand, mutation=False),
        "denied",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_edit"), ("op", "edit")),
        "mutation",
        "request",
        {"apply"},
        "write",
        _dash_post("memory_edit", _post_mutation("edit"), mutation=True),
        "denied",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_archive"), ("op", "archive")),
        "mutation",
        "request",
        {"apply"},
        "write",
        _dash_post("memory_archive", _post_mutation("archive"), mutation=True),
        "denied",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_delete"), ("op", "delete")),
        "mutation",
        "request",
        {"apply"},
        "write",
        _dash_post("memory_delete", _post_mutation("delete"), mutation=True),
        "denied",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_promote"), ("op", "promote")),
        "mutation",
        "request",
        {"apply"},
        "write",
        _dash_post("memory_promote", _post_mutation("promote"), mutation=True),
        "denied",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_propose"), ("op", "write")),
        "mutation",
        "request",
        {"apply"},
        "write",
        _dash_post("memory_propose", _post_mutation("write"), mutation=True),
        "denied",
    ),
    _mk(
        "dashboard",
        "dashboard",
        (("action", "memory_maintain"), ("op", "maintain")),
        "mutation",
        "request",
        {"apply"},
        "write",
        _dash_post("memory_maintain", _post_mutation("maintain"), mutation=True),
        "denied",
    ),
]


# --- the plan for one cell and its assertions -------------------------------------------


def _legacy_plan(row: MRow) -> Plan:
    if row.legacy == "denied":
        # A `write` names its own source, so in D1 `legacy` mode (no grant to name an
        # owner) the owner it names is what is refused; every other route has no source
        # to read with and is refused for the missing policy (72-T06 §3.3).
        reason = (
            "owner_not_granted"
            if row.transport == "dashboard" and _action_of(row) == "write"
            else "policy_missing"
        )
        return Plan(policy="legacy", expect="denied", reason=reason)
    if row.legacy == "stateful":
        return Plan(policy="legacy", expect="stateful")
    return Plan(policy="legacy", expect="healthy")


def _plan_for(row: MRow, dim: str, val: str) -> Plan | None:
    """The G2 outcome of one (row, dimension, value), or `None` for a cell that belongs
    to another task's matrix (the hybrid cell of a list/query read is 72-T08's)."""
    refuse = "boundary" if row.surface == "request" else "identical"
    mutation = row.kind == "mutation"
    if dim == "access":
        if val == "policy":
            return Plan()
        if val == "legacy_allowlist":
            return _legacy_plan(row)
        if row.transport == "cli" and row.route in ("history", "explain"):
            # These leaves take no owner: the transport has no overlay field, so the
            # request is byte-identical to the non-overlay one.
            return Plan(overlay=True, expect="identical")
        refused = (
            mutation
            and row.transport != "tui"
            and _action_of(row) in ("edit", "promote", "write", "maintain")
        )
        return Plan(
            overlay=True,
            expect="stateful" if row.kind == "map" else "denied",
            # D25: the personal layer is written only through the preference route.
            reason="overlay_requires_preference_route" if refused else None,
        )
    if dim == "policy_state":
        if val == "missing_no_marker":
            return _legacy_plan(row)
        if val == "ok":
            return Plan()
        if val == "missing_marker":
            return Plan(
                policy="marker",
                expect="denied",
                reason="policy_missing",
                action=row.kind != "map",
            )
        return Plan(policy="invalid", expect="denied", reason="policy_invalid")
    if dim == "mode":
        if val in ("ordinary", "inspect"):
            return Plan()
        if "archive_mode" in row.fields:
            return Plan(
                fields={"archive_mode": "historical"},
                expect="historical",
                row_state="archived",
            )
        return Plan(fields={"archive_mode": "historical"}, expect=refuse)
    if dim == "representation":
        if "representation" in row.fields:
            return Plan(fields={"representation": val})
        return Plan(fields={"representation": val}, expect=refuse)
    if dim == "retrieval":
        if val == "lexical":
            if "retrieval" in row.fields:
                return Plan(fields={"retrieval": "lexical"})
            return (
                Plan()
                if row.t08_owned
                else Plan(fields={"retrieval": "lexical"}, expect=refuse)
            )
        if row.t08_owned:
            return None
        if "retrieval" in row.fields:
            return Plan(fields={"retrieval": "hybrid"}, expect="hybrid_denied")
        return Plan(fields={"retrieval": "hybrid"}, expect=refuse)
    if dim == "store":
        if val == "present":
            return Plan()
        if val == "absent":
            return Plan(
                store="absent",
                expect="stateful" if mutation or row.kind == "map" else "absent",
            )
        return Plan(
            store="old_schema",
            expect="stateful" if mutation or row.kind == "map" else "migration",
        )
    if dim == "apply":
        if mutation:
            return Plan(apply=(val == "apply"))
        return Plan(fields={"apply": val == "apply"}, expect=refuse)
    if dim == "cache_write":
        if mutation and val == "off" and row.transport != "tui":
            return Plan(cache_write=False, expect="refused")
        return Plan()
    if dim == "grant_ops":
        if val == "exact":
            return Plan()
        return Plan(
            drop_ops=(row.grant_op,),
            expect="denied",
            reason="operation_not_granted",
            action=row.kind != "map",
        )
    if dim == "row_state":
        return Plan() if val == "active" else Plan(row_state=val, expect="stateful")
    if dim == "ack":
        return Plan(fields={"ack": True}, expect=refuse) if val == "ack" else Plan()
    if dim == "capability_ids":
        if val == "selected":
            return Plan(fields={"capability_ids": ["x"]}, expect=refuse)
        return Plan()
    raise AssertionError((dim, val))


def _matrix_cells() -> list[Any]:
    cells = []
    for row in ROWS:
        for dim, values in DIMENSIONS.items():
            for val in values:
                if _plan_for(row, dim, val) is None:
                    continue
                cells.append(
                    pytest.param(row, dim, val, id=f"{row.ident()}-{dim}-{val}")
                )
    return cells


def _action_of(row: MRow) -> str:
    extra = dict(row.extra)
    if row.transport == "cli":
        return row.route
    if row.transport == "dashboard":
        return extra["op"]
    return extra["action"]


def _target_of(row: MRow, world: World) -> str:
    return world.alice("failure" if row.kind == "mutation" else row.subject)


def _read_kind(row: MRow) -> str:
    extra = dict(row.extra)
    if row.transport == "cli":
        return {
            "list": "list_all" if extra.get("form") == "no_args" else "list_query",
            "expand": "expand",
            "related": "related",
            "history": "history",
            "explain": "explain",
        }[row.route]
    if row.transport == "tui":
        return {
            "refresh": "list_plain",
            "paging": "list_plain",
            "expand": "expand",
            "history": "history",
            "explain": "explain",
        }.get(extra["action"], "other")
    if row.route == "dashboard_readers":
        return {
            "memory_browse": "list_plain",
            "memory_query": "list_query",
            "expand_id": "expand",
            "related_id": "related",
        }.get(extra["surface"], "other")
    return {"memory_query": "list_query", "memory_expand": "expand"}.get(
        extra["action"], "other"
    )


def _oracle_ids(row: MRow, env: Env) -> list[tuple[str, int]] | None:
    """What MemoryTool returns for the request this row sends, as (id, version)."""
    if row.kind != "read":
        return None
    world = env.world
    extras: dict[str, Any] = _owner_field(env)
    if env.fields.get("archive_mode") == "historical":
        extras["archive_mode"] = "historical"
    kind = _read_kind(row)
    if kind in ("list_all", "list_query", "list_plain"):
        subjects = list(SUBJECTS) if kind == "list_all" else [SUBJECT]
        query = "needle" if kind == "list_query" else ""
        if row.transport == "tui":
            # The terminal asks for a screenful: its own page size and byte/token budget.
            from rush import tui as tui_mod

            extras.update(
                limit=tui_mod._MEMORY_PAGE_ROWS,
                max_bytes=tui_mod._MEMORY_PAGE_MAX_BYTES,
                max_tokens=tui_mod._MEMORY_PAGE_MAX_TOKENS,
            )
        raw = _raw(_oracle_list(world, subjects, query, **extras))
        return _pairs(raw["items"]) if raw.get("code") == "OK" else None
    if kind == "expand":
        raw = _raw(
            _oracle(
                world,
                "expand",
                {
                    "schema_version": 2,
                    "artifact_id": env.target,
                    "artifact_version": 1,
                    **extras,
                },
            )
        )
        if raw.get("code") == "OK" and raw.get("items"):
            return [_identity(raw["items"][0])]
        return None
    if kind == "history":
        raw = _raw(
            _oracle(
                world,
                "history",
                {"schema_version": 2, "artifact_id": env.target, **extras},
            )
        )
        if raw.get("code") != "OK":
            return None
        return [
            (v["reference"]["artifact_id"], v["reference"]["artifact_version"])
            for v in raw["versions"]
        ]
    return None


def _count_rows(world: World, marker: str) -> int:
    with contextlib.closing(
        sqlite3.connect(world.root / ".rush" / "memory.db")
    ) as conn:
        (n,) = conn.execute(
            "SELECT COUNT(*) FROM memory_artifacts WHERE content LIKE ?",
            (f"%{marker}%",),
        ).fetchone()
    return int(n)


def _check_effect(row: MRow, env: Env, obs: Obs) -> None:
    world = env.world
    action = _action_of(row)
    target = world.alice("failure")
    current = world.store.get_current_row(target)
    tui = row.transport == "tui"
    if action in ("edit",):
        assert current is not None and current["artifact_version"] == 2, (
            row.ident(),
            obs,
        )
    elif action == "correction":
        assert current is not None and current["artifact_version"] > 1, (
            row.ident(),
            obs,
        )
    elif action == "archive":
        assert current is not None and current["archived_at"] is not None, (
            row.ident(),
            obs,
        )
    elif action == "delete":
        assert current is None, (row.ident(), obs)
    elif action in ("write", "propose"):
        marker = "needle matrix create" if tui else "needle matrix write"
        assert _count_rows(world, marker) >= 1, (row.ident(), obs)
    elif action == "promote" and not tui:
        # 72-T04: a promotion writes a STATED candidate beside the reviewed row; the
        # reviewed row itself keeps its tier.
        db = world.root / ".rush" / "memory.db"
        with contextlib.closing(sqlite3.connect(db)) as conn:
            (stated,) = conn.execute(
                "SELECT COUNT(*) FROM memory_artifacts "
                "WHERE subject = ? AND trust_tier = 'STATED'",
                (current["subject"] if current is not None else "failure",),
            ).fetchone()
        assert current is not None and stated >= 1, (row.ident(), obs)


def _healthy(
    row: MRow, env: Env, obs: Obs, oracle_ids: list[tuple[str, int]] | None
) -> None:
    where = (row.ident(), obs)
    if row.kind == "map":
        assert obs.state == "ok", where
        return
    if row.kind == "read":
        assert obs.state in OK_STATES, where
        if oracle_ids is not None:
            assert obs.ids == oracle_ids, (where, oracle_ids)
        if _read_kind(row) == "expand" and obs.content is not None:
            expected = _raw(
                _oracle(
                    env.world,
                    "expand",
                    {
                        "schema_version": 2,
                        "artifact_id": env.target,
                        "artifact_version": 1,
                        "representation": env.fields.get("representation", "base64"),
                    },
                )
            )
            if expected.get("code") == "OK":
                item = expected["items"][0]
                recorded = (item.get("reference") or {}).get("payload_hash")
                assert hashlib.sha256(obs.content).hexdigest() == recorded, where
                if "content_utf8" in item:
                    assert obs.content == item["content_utf8"].encode("utf-8"), where
        return
    action = _action_of(row)
    applying = _does_apply(env)
    # The interface names the state it is in (list refresh, receipt or apply outcome).
    assert obs.state in OK_STATES, where
    if action == "import":
        return
    held = action in ("edit", "archive", "delete", "propose", "correction")
    if not applying:
        assert obs.wrote is False, ("a preview wrote", where)
        if row.transport != "tui":
            assert obs.code == "OK", where
        elif held:
            assert obs.note == "pending", ("no reviewed preview was held", where)
        return
    if row.transport == "tui":
        if held:
            assert obs.note == "applied", ("the reviewed apply never ran", where)
        if obs.note == "applied" and action not in ("promote", "maintain"):
            assert obs.wrote is True, where
            _check_effect(row, env, obs)
        return
    assert obs.code == "OK", where
    assert obs.wrote is True, ("an apply wrote nothing", where)
    _check_effect(row, env, obs)


def _denied(row: MRow, env: Env, obs: Obs) -> None:
    plan = env.plan
    where = (row.ident(), plan.expect, obs)
    assert obs.state in ("denied", "revoked", "expired"), where
    assert obs.wrote is False, where
    assert not obs.ids, ("a denial disclosed rows", where)
    if plan.reason is not None and row.kind != "map":
        reason = obs.reason or ""
        assert plan.reason in reason, where
    if plan.action:
        assert obs.next_action is not None, ("a denial without a next action", where)
        assert str(obs.next_action.get("command", "")).startswith(
            "rush memory grant"
        ), where


def _check(
    row: MRow,
    env: Env,
    obs: Obs,
    base: Obs | None,
    oracle_ids: list[tuple[str, int]] | None,
) -> None:
    plan = env.plan
    where = (row.ident(), plan.expect, obs)
    assert not obs.traceback, where
    if obs.state is not None:
        assert obs.state in PRODUCT_STATES, where
    expect = plan.expect
    if expect == "healthy":
        _healthy(row, env, obs, oracle_ids)
    elif expect == "denied":
        _denied(row, env, obs)
    elif expect == "absent":
        assert obs.state in row.absent, where
        assert obs.wrote is False, where
        assert not (env.world.root / ".rush" / "memory.db").exists(), where
    elif expect == "migration":
        assert obs.state == "migration_required", where
        assert obs.wrote is False, where
    elif expect == "boundary":
        assert obs.wrote is False, where
        if row.transport == "dashboard":
            # An allowlist refusal is `unsupported_argument` today; a malformed value
            # is `malformed_request`. Both are the HTTP 400 boundary.
            assert obs.http == 400, where
            assert obs.error in ("malformed_request", "unsupported_argument"), where
        else:
            assert obs.code == "E_INPUT", where
            assert obs.exit_code == 2, where
    elif expect == "identical":
        assert base is not None
        assert (obs.state, obs.code, obs.ids, obs.content) == (
            base.state,
            base.code,
            base.ids,
            base.content,
        ), (where, base)
    elif expect == "hybrid_denied":
        assert obs.http == 403 and obs.error == "grant_denied", where
        assert obs.wrote is False, where
    elif expect == "refused":
        assert obs.wrote is False, where
        if row.transport == "dashboard":
            assert obs.http == 403 and obs.error == "grant_denied", where
        else:
            assert obs.state == "denied", where
    elif expect == "historical":
        assert obs.state in OK_STATES, where
        if oracle_ids is not None:
            assert obs.ids == oracle_ids, (where, oracle_ids)
            if _read_kind(row).startswith("list"):
                assert any(i == env.target for i, _v in obs.ids), (
                    "the archived row must be listed in historical mode",
                    where,
                )
    elif expect == "stateful":
        assert obs.state in (*PRODUCT_STATES, None), where
        if row.kind == "read":
            assert obs.wrote is False, where
            if oracle_ids is not None:
                assert obs.ids == oracle_ids, (where, oracle_ids)
        if row.kind != "map" and obs.state in ("denied", "revoked", "expired"):
            assert not obs.ids, ("a denial disclosed rows", where)
    else:  # pragma: no cover - a typo in a plan
        raise AssertionError(expect)


@pytest.mark.parametrize(("row", "dim", "val"), _matrix_cells())
def test_t07_route_mode_matrix(
    row: MRow,
    dim: str,
    val: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan_for(row, dim, val)
    assert plan is not None
    world = _build_world(tmp_path, plan, row.extra_domain)
    if plan.row_state != "active" and plan.store != "absent":
        _apply_row_state(world, _target_of(row, world), plan.row_state)
    owner = (
        auth.user_overlay_owner_scope(data_root=world.data_root)
        if plan.overlay
        else None
    )
    env = Env(world, monkeypatch, tmp_path, plan, owner)
    oracle_ids = (
        _oracle_ids(row, env)
        if plan.expect in ("healthy", "historical", "stateful")
        else None
    )
    if plan.store != "present":
        oracle_ids = None
    base: Obs | None = None
    issued = [0]
    if plan.expect == "identical":
        # Two runs that must be identical cannot differ by the random id a write
        # mints: pin new ids to a counter restarted for each run.
        original = MemoryTool._build_artifact

        def pinned(*args: Any, **kwargs: Any) -> Any:
            issued[0] += 1
            return dataclasses.replace(
                original(*args, **kwargs), id=f"minted-{issued[0]:04d}"
            )

        monkeypatch.setattr(MemoryTool, "_build_artifact", staticmethod(pinned))
        base_plan = Plan()
        base_world = _build_world(
            tmp_path, base_plan, row.extra_domain, name="baseline"
        )
        base = row.drive(Env(base_world, monkeypatch, tmp_path, base_plan))
        issued[0] = 0
    obs = row.drive(env)
    _check(row, env, obs, base, oracle_ids)

    if plan.expect == "historical":
        # Without the `history` grant the same request is a D19 denial, zero effects.
        denied_plan = Plan(
            drop_ops=("history",),
            fields=plan.fields,
            row_state="archived",
            expect="denied",
            reason="operation_not_granted",
            action=True,
        )
        second = _build_world(
            tmp_path, denied_plan, row.extra_domain, name="no-history"
        )
        _apply_row_state(second, _target_of(row, second), "archived")
        env2 = Env(second, monkeypatch, tmp_path, denied_plan, None)
        denied = row.drive(env2)
        _check(row, env2, denied, None, None)


# =============================================================================
# R8 -- the live PTY keyboard walkthrough on the current app
# =============================================================================

_CSI = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-Za-z]|\x1b[=>78]"
)
_FORBIDDEN_IN_REPORT = (
    re.compile(r"\b[0-9a-f]{32}\b"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{43}(?![A-Za-z0-9_-])"),
    re.compile(r"/Users/[^/\s]+"),
    re.compile(r"/home/[^/\s]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"Bearer\s"),
)


def _t07_child_rush_ui(root: str) -> None:
    """The child of the PTY: the real `rush ui <root>` entry (`rush.cli.cli`)."""
    from rush.cli import cli as rush_cli

    rush_cli(["ui", root], standalone_mode=False)


def _visible(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace")
    return _CSI.sub("", text).replace("\r\n", "\n")


class _Pty:
    """A pty master with a reader thread; `send` returns the bytes one key produced."""

    def __init__(self, pid: int, master: int) -> None:
        self.pid, self.master = pid, master
        self.buffer = bytearray()
        self._lock = threading.Lock()
        self._stop = False
        self._thread = threading.Thread(target=self._read, daemon=True)
        self._thread.start()

    def _read(self) -> None:
        while not self._stop:
            try:
                ready, _, _ = select.select([self.master], [], [], 0.05)
            except (OSError, ValueError):
                return
            if not ready:
                continue
            try:
                chunk = os.read(self.master, 65536)
            except OSError:
                return
            if not chunk:
                return
            with self._lock:
                self.buffer.extend(chunk)

    def _size(self) -> int:
        with self._lock:
            return len(self.buffer)

    def send(self, data: bytes, *, wait: float = 0.4) -> bytes:
        """Write `data`, give the app `wait` seconds, return what it printed meanwhile.
        (A live TUI never goes quiet, so the caller polls for the content it expects.)"""
        start = self._size()
        if data:
            os.write(self.master, data)
        time.sleep(wait)
        with self._lock:
            return bytes(self.buffer[start:])

    def close(self) -> None:
        self._stop = True
        self._thread.join(timeout=2)
        with contextlib.suppress(OSError):
            os.close(self.master)


KEY_BYTES = {
    "f3": b"\x1bOR",
    "tab": b"\t",
    "enter": b"\r",
    "escape": b"\x1b",
}


def _redact(text: str, world: World, tmp_path: Path) -> str:
    """The report form of a transcript excerpt: ids as eight characters plus an
    ellipsis, no home or temp path, no token-shaped string."""
    home = os.environ.get("HOME", "")
    for prefix in sorted({str(tmp_path), home, str(world.root)}, key=len, reverse=True):
        if prefix:
            text = text.replace(prefix, "~")
    identifiers = {v for v in world.ids.values()} | {world.project_id}
    if world.grant:
        identifiers.add(str(world.grant["grant_id"]))
    for ident in sorted(identifiers, key=len, reverse=True):
        if len(ident) > 8:
            text = text.replace(ident, ident[:8] + "…")
    text = re.sub(r"\b[0-9a-f]{32}\b", lambda m: m.group()[:8] + "…", text)
    text = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        lambda m: m.group()[:8] + "…",
        text,
    )
    return text


def _t07_walkthrough_section(
    receipts: list[dict[str, Any]], identity: dict[str, str]
) -> str:
    lines = [
        "## 72-T07 walkthrough",
        "",
        (
            "Machine-generated by `tests/test_phase72_memory_ui.py::test_t07_pty_walkthrough`: "
            "keys written to a pty master, transcript bytes read back per step."
        ),
        "",
        f"- installed entry sha256: `{identity['rush_entry_sha256']}`",
        f"- source tree sha256: `{identity['source_tree_sha256']}`",
        "",
        "| Step | Keys (hex) | Transcript sha256 | Observed |",
        "|---|---|---|---|",
    ]
    for receipt in receipts:
        observed = str(receipt["observed"]).replace("|", "/").replace("\n", " ")
        lines.append(
            f"| {receipt['step']} | {receipt['keys_hex']} | `{receipt['transcript_sha256']}` | {observed} |"
        )
    lines.append("")
    return "\n".join(lines)


@pytest.mark.posix_only
def test_t07_pty_walkthrough(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fcntl
    import termios

    from _process_children import spawn_pty_child

    from rush.theme import safe_terminal_text

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setenv("TERM", "xterm-256color")
    world = _world(tmp_path, hostile=True, extra_domain=24)
    env = dict(os.environ)
    pid, master = spawn_pty_child(
        "test_phase72_memory_ui", "_t07_child_rush_ui", [str(world.root)], env=env
    )
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 50, 200, 0, 0))
    pty = _Pty(pid, master)
    receipts: list[dict[str, Any]] = []

    def step(
        name: str, *keys: str, expect: Callable[[str, bytes], str] | None = None
    ) -> bytes:
        chunks: list[bytes] = []
        sent = bytearray()
        for key in keys:
            data = KEY_BYTES.get(key, key.encode("utf-8"))
            sent.extend(data)
            chunks.append(pty.send(data))
        deadline = time.monotonic() + 12
        while True:
            raw = b"".join(chunks)
            text = _visible(raw)
            try:
                observed = expect(text, raw) if expect is not None else "keys sent"
                break
            except AssertionError:
                if time.monotonic() > deadline:
                    raise
                chunks.append(pty.send(b"", wait=0.4))
        receipts.append(
            {
                "step": name,
                "keys_hex": sent.hex() or "-",
                "transcript_sha256": hashlib.sha256(raw).hexdigest(),
                "observed": _redact(safe_terminal_text(observed), world, tmp_path),
            }
        )
        return raw

    try:
        launch = b""
        for _ in range(60):
            launch += pty.send(b"", wait=0.5)
            if SGR.search(launch.decode("utf-8", "replace")):
                break
        assert launch, "the TUI never drew"
        assert SGR.search(launch.decode("utf-8", "replace")), (
            "no styled output reached the pty"
        )
        time.sleep(1.0)

        def memory_open(text: str, raw: bytes) -> str:
            assert "Memory" in text, text[-600:]
            assert "alice-" in text, text[-600:]
            assert "bob-" not in text
            return "Memory section drew the owner's rows"

        step("memory section", "f3", "4", expect=memory_open)

        def subject_shown(subject: str) -> Callable[[str, bytes], str]:
            def check(text: str, raw: bytes) -> str:
                needle = "alice-dk-00" if subject == SUBJECT else f"alice-{subject}"
                assert needle in text, (subject, text[-800:])
                oracle = _all_pages(world, subject)[0][0]
                assert oracle in text or subject == SUBJECT, (subject, oracle)
                assert "bob-" not in text
                return f"{subject}: listed {needle}"

            return check

        order = list(SUBJECTS)
        position = order.index("domain_knowledge")
        for offset in range(1, len(order) + 1):
            subject = order[(position + offset) % len(order)]
            step(f"subject {subject}", "S", expect=subject_shown(subject))

        first_hit = _pairs(_raw(_oracle_list(world, [SUBJECT], "needle"))["items"])[0][
            0
        ]

        def searched(text: str, raw: bytes) -> str:
            assert first_hit in text, (first_hit, text[-800:])
            return f"search needle: first hit {first_hit}"

        step("search", "/", *"needle", "enter", expect=searched)

        def cleared(text: str, raw: bytes) -> str:
            # The clear reruns the list on a worker thread; "]" sent before its
            # result lands pages the old search rows, so wait for the count line.
            assert "working: " in text, text[-800:]
            assert "result(s)" in text.rpartition("working: ")[2], text[-800:]
            return "search cleared: list reloaded"

        step("clear search", "/", "enter", expect=cleared)

        def page_two(text: str, raw: bytes) -> str:
            assert "alice-dk-20" in text, text[-800:]
            return "page 2 starts at alice-dk-20"

        step("next page", "]", expect=page_two)

        def page_one(text: str, raw: bytes) -> str:
            assert "alice-dk-00" in text, text[-800:]
            return "page 1 again at alice-dk-00"

        step("previous page", "[", expect=page_one)

        def expanded(text: str, raw: bytes) -> str:
            assert "alice-dk-00" in text and "needle extra 0" in text, text[-800:]
            return "exact version expanded: alice-dk-00 v1"

        step("expand", "x", expect=expanded)

        def panel(title: str) -> Callable[[str, bytes], str]:
            def check(text: str, raw: bytes) -> str:
                assert title in text, text[-800:]
                return f"{title} panel drew"

            return check

        step("history", "v", expect=panel("Memory history"))
        step("explain", "E", expect=panel("Memory explain"))
        step("collapse", "-")

        target = "alice-dk-00"
        before = world.store.get_current_row(target)
        assert before is not None
        v0 = before["artifact_version"]
        step(
            "correction preview",
            "c",
            "tab",
            *"pty correction",
            "tab",
            *"needle corrected by the pty walkthrough",
            "enter",
        )
        step("correction apply", "y")
        after = world.store.get_current_row(target)
        assert after is not None and after["artifact_version"] > v0, (v0, after)
        readback = dict(_pairs(_raw(_oracle_list(world, [SUBJECT]))["items"]))
        assert readback[target] == after["artifact_version"], (
            "the TUI and MemoryTool disagree"
        )

        guarded = world.db_sha()
        step("correction cancel", "c", *"never saved", "escape")
        assert world.db_sha() == guarded, "escape wrote"

        def focus_cycle(text: str, raw: bytes) -> str:
            wanted = ["inspect", "edit", "search", "filter", "list"]
            # The header repeats on every redraw: collapse repeats, then the five
            # focus names must appear in order.
            seen = [
                name for name, _ in itertools.groupby(re.findall(r"focus=(\w+)", text))
            ]
            position = 0
            for name in seen:
                if position < len(wanted) and name == wanted[position]:
                    position += 1
            assert position == len(wanted), seen
            return "focus: " + ">".join(wanted)

        step("focus cycle", "tab", "tab", "tab", "tab", "tab", expect=focus_cycle)

        def hostile(text: str, raw: bytes) -> str:
            assert b"\x07" not in raw, "a BEL reached the terminal"
            assert "\u202e" not in raw.decode("utf-8", "replace")
            assert b"\x1b[2K\r\x07" not in raw, "an injected erase-line sequence"
            for literal in HOSTILE_ESCAPES:
                assert literal in text, (literal, text[-800:])
            return "hostile row rendered as escaped text"

        # 72-T01: a row holding a bidi override is integrity-blocked from ordinary and
        # inspect reads; it is visible only in the historical view (`f`, tab to the
        # `archived` field, `true`, Enter), where the screen must show it as text.
        step("historical view", "f", "tab", "tab", "tab", *"true", "enter")
        # (Two steps: one step's 16 key bytes would print as a 32-hex run, which the
        # report check below rejects as a secret-shaped token.)
        step("hostile search", "/", *"hostilemarker", "enter")
        step("hostile row", "x", expect=hostile)
        _revoke(world)

        def revoked(text: str, raw: bytes) -> str:
            assert "revoked" in text, text[-800:]
            return "revoked grant: state shown"

        step("revoked grant", "S", expect=revoked)
        step("quit", "q")
        deadline = time.monotonic() + 15
        exited = False
        while time.monotonic() < deadline:
            done, _status = os.waitpid(pid, os.WNOHANG)
            if done:
                exited = True
                break
            time.sleep(0.1)
        assert exited, "the TUI did not exit on q"
    finally:
        pty.close()
        with contextlib.suppress(ProcessLookupError, ChildProcessError, OSError):
            os.kill(pid, 9)
            os.waitpid(pid, 0)

    # --- the receipts are machine generated and pin the entry and the source tree ---
    repo = Path(__file__).resolve().parent.parent
    entry = repo / ".venv" / "bin" / "rush"
    tree = hashlib.sha256()
    for path in sorted((repo / "src" / "rush").rglob("*.py")):
        tree.update(str(path.relative_to(repo)).encode())
        tree.update(hashlib.sha256(path.read_bytes()).digest())
    identity = {
        "rush_entry_sha256": hashlib.sha256(entry.read_bytes()).hexdigest()
        if entry.is_file()
        else "absent",
        "source_tree_sha256": tree.hexdigest(),
    }
    assert [r["step"] for r in receipts][:2] == [
        "memory section",
        "subject skill_pattern",
    ]
    assert len(receipts) >= 18
    section = _t07_walkthrough_section(receipts, identity)
    assert section.startswith("## 72-T07 walkthrough")
    for pattern in _FORBIDDEN_IN_REPORT:
        assert pattern.search(section) is None, (
            pattern.pattern,
            pattern.search(section),
        )
    for ch in section:
        assert ch in "\n\t" or ord(ch) >= 0x20 and ord(ch) not in range(0x7F, 0xA0), (
            repr(ch)
        )
    from test_phase70_t25 import _CURSOR_RE

    assert _CURSOR_RE.search(section) is None, _CURSOR_RE.search(section)
    for receipt in receipts:
        assert re.fullmatch(r"[0-9a-f]{64}", receipt["transcript_sha256"])
    target_path = os.environ.get("RUSH_T07_WALKTHROUGH_REPORT")
    if target_path:
        Path(target_path).write_text(
            "# Phase 72 memory acceptance\n\n" + section, encoding="utf-8"
        )
