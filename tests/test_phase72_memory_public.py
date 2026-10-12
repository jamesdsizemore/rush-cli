"""72-T06: canonical public memory query and administration (G5 test author).

Every symbol an earlier task adds (`MemoryAccess.required_operations`,
`TypedArtifactStore.version_history_readonly`, `apply_import_records`, ...) and every
T06 symbol is imported inside the test that uses it, so this module collects at HEAD
and each test fails on its own until the product code exists. Module-level imports are
existing code and the standard library only.

G10: the autouse fixture below places HOME, XDG_DATA_HOME and LOCALAPPDATA inside the
test's `tmp_path`; no test touches the real data root. Platform cases are
`pytest.param` with `posix_only` / `posix_nonroot` / `windows_only` marks and literal
ids; nothing here skips or xfails.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from rush.memory.store import (
    MemoryArtifact,
    OwnerScope,
    TypedArtifactStore,
    legacy_owner_scope,
)
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.tools.memory import MemoryOperation, MemoryTool
from rush.workflows.projects import register_project

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SUBJECTS = (
    "active_context",
    "episodic",
    "preference",
    "failure",
    "architectural_decision",
    "domain_knowledge",
    "skill_pattern",
)
ALICE = OwnerScope("user", "alice")
BOB = OwnerScope("user", "bob")
SRC = "s1"
OVERLAY_SOURCE = "personal-preferences"
GRANT_OPS = ("ask", "list", "expand", "history", "write")
NO_HISTORY_OPS = ("ask", "list", "expand", "write")
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
V2_NAMED = frozenset(
    {
        "versions",
        "supporting",
        "contrary",
        "attempted",
        "affected",
        "targets",
        "next_action",
    }
)
TOOL_RESULT_KEYS = frozenset(
    {
        "tool",
        "engine",
        "engine_version",
        "status",
        "duration_ms",
        "summary",
        "findings",
        "raw",
        "metadata",
    }
)
REFERENCE_KEYS = frozenset(
    {
        "artifact_id",
        "artifact_version",
        "project_id",
        "worktree_id",
        "owner_scope",
        "source",
        "subject",
        "trust_tier",
        "origin_kind",
        "origin_id",
        "freshness",
        "integrity",
        "payload_hash",
    }
)
COMPACT_KEYS = frozenset(
    {"id", "version", "excerpt", "source", "trust", "freshness", "relations"}
)
ITEM_KEYS = (
    frozenset(
        {"reference", "content_hash", "symbol_ref", "usable_as_current", "reason_codes"}
    )
    | COMPACT_KEYS
)
CODE_STATUS = {
    "OK": "ok",
    "E_INPUT": "error",
    "E_PERMISSION": "fail",
}  # spot checks only; the full map is `tools.memory._CODE_STATUS`

ALICE_IDS = {
    s: ("r1" if s == "domain_knowledge" else "r2" if s == "failure" else f"a-{s}")
    for s in SUBJECTS
}
BOB_IDS = {s: f"b-{s}" for s in SUBJECTS}


@pytest.fixture(autouse=True)
def _t06_isolated_home(tmp_path_factory: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """G10: HOME, XDG_DATA_HOME and LOCALAPPDATA under a per-test temporary tree."""
    home = tmp_path_factory.mktemp("t06home")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    if os.name == "nt":
        monkeypatch.setenv("USERPROFILE", str(home))
    return home


# --- environment ------------------------------------------------------------------


@dataclasses.dataclass
class Env:
    """Fixture F: project P with two grants (Alice, Bob) and a seeded store."""

    root: Path
    data_root: Path
    store: TypedArtifactStore | None
    mode: str  # "policy" | "legacy"
    grants: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)

    @property
    def db(self) -> Path:
        return self.root / ".rush" / "memory.db"


def _auth() -> Any:
    from rush.memory import authorization

    return authorization


def _revision(data_root: Path) -> int:
    return int(
        _auth().load_policy_readonly(data_root=data_root)["policy_revision"] or 0
    )


def grant(
    env_or_root: Any,
    data_root: Path,
    owner: OwnerScope,
    *,
    sources: tuple[str, ...] = (SRC,),
    ops: tuple[str, ...] = GRANT_OPS,
    root: Path | None = None,
) -> dict[str, Any]:
    target = root if root is not None else getattr(env_or_root, "root", env_or_root)
    return _auth().grant_memory_scope(
        project_root=target,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=_revision(data_root),
        consent=True,
        data_root=data_root,
    )


def revoke(env: Env, owner: OwnerScope) -> None:
    _auth().revoke_memory_scope(
        grant_id=env.grants[owner.id]["grant_id"],
        expected_policy_revision=_revision(env.data_root),
        consent=True,
        data_root=env.data_root,
    )


def put(
    store: TypedArtifactStore,
    artifact_id: str,
    owner: OwnerScope | None,
    subject: str = "domain_knowledge",
    *,
    text: str | None = None,
    source: str = SRC,
    content: dict[str, Any] | None = None,
    trust: str = "DERIVED",
    created_at: float | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
) -> MemoryArtifact:
    label = owner.id if owner is not None else "legacy"
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject=subject,  # type: ignore[arg-type]
            trust_tier=trust,  # type: ignore[arg-type]
            content=content
            if content is not None
            else {"text": text or f"needle {subject} {label}"},
            source=source,
            created_at=created_at if created_at is not None else time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
            owner_scope=owner,
        )
    )


def seed(store: TypedArtifactStore, *, bob: bool = True, legacy: bool = False) -> None:
    for subject in SUBJECTS:
        put(store, ALICE_IDS[subject], None if legacy else ALICE, subject)
        if bob:
            put(store, BOB_IDS[subject], None if legacy else BOB, subject)


def make_env(
    tmp_path: Path,
    *,
    mode: str = "policy",
    ops: tuple[str, ...] = GRANT_OPS,
    bob: bool = True,
    seeded: bool = True,
    name: str = "project",
    create_store: bool = True,
) -> Env:
    data_root = default_data_root()
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    _git_init(root)
    root = root.resolve()
    store: TypedArtifactStore | None = None
    env = Env(root=root, data_root=data_root, store=None, mode=mode)
    if mode == "policy":
        register_project(root, data_root=data_root)
        env.grants["alice"] = grant(env, data_root, ALICE, ops=ops)
        if bob:
            env.grants["bob"] = grant(env, data_root, BOB, ops=ops)
    if create_store:
        store = TypedArtifactStore(root)
        env.store = store
        if seeded:
            seed(store, bob=bob, legacy=mode == "legacy")
    return env


def _git_init(root: Path) -> None:
    subprocess.run(
        ["git", "init", "--initial-branch=main", "-q"],
        cwd=root,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_overlay_env(tmp_path: Path) -> tuple[Env, OwnerScope, TypedArtifactStore]:
    """A policy project plus an overlay grant and a seeded overlay store (`p1`)."""
    env = make_env(tmp_path)
    overlay = _auth().user_overlay_owner_scope(data_root=env.data_root)
    env.grants["overlay"] = grant(
        env,
        env.data_root,
        overlay,
        sources=(OVERLAY_SOURCE,),
        ops=("overlay_read", "list", "expand", "history", "write"),
    )
    overlay_root = env.data_root / "user"
    overlay_root.mkdir(parents=True, exist_ok=True)
    store = TypedArtifactStore(overlay_root)
    put(
        store,
        "p1",
        overlay,
        "preference",
        source=OVERLAY_SOURCE,
        text="needle overlay p1",
    )
    return env, overlay, store


# --- snapshots and raw access ------------------------------------------------------


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_tree(base: Path, *, skip: tuple[str, ...] = ()) -> dict[str, str]:
    """Every path under `base` with its kind and content: file bytes (sha256), a
    symlink's link text (never followed) and directories. An unreadable file raises:
    a captured oracle never turns lost bytes into a constant."""
    out: dict[str, str] = {}
    if not base.exists():
        return out
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(base).as_posix()
        if any(rel.startswith(s) for s in skip):
            continue
        if p.is_symlink():
            out[rel] = "link:" + os.readlink(p)
        elif p.is_dir():
            out[rel] = "dir"
        else:
            out[rel] = "file:" + sha_file(p)
    return out


def db_state(db: Path) -> dict[str, Any] | None:
    """Logical state of a store: its schema (tables, indexes, triggers) and every row.
    Read from a private copy so inspecting never creates a -wal/-shm beside the store."""
    import shutil
    import tempfile

    if not db.exists():
        return None
    with tempfile.TemporaryDirectory(prefix="t06-dbstate-") as tmp:
        copy = Path(tmp) / "memory.db"
        shutil.copyfile(db, copy)
        wal = db.with_name(db.name + "-wal")
        if wal.exists():
            shutil.copyfile(wal, Path(tmp) / "memory.db-wal")
        try:
            with contextlib.closing(sqlite3.connect(copy)) as conn:
                schema = sorted(
                    tuple(r)
                    for r in conn.execute("SELECT type, name, sql FROM sqlite_master")
                )
                names = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table' "
                        "AND name NOT LIKE 'sqlite_%'"
                    )
                ]
                tables = {
                    name: sorted(
                        repr(tuple(r)) for r in conn.execute(f'SELECT * FROM "{name}"')
                    )
                    for name in sorted(names)
                }
        except sqlite3.DatabaseError as exc:
            return {"unreadable": str(exc), "bytes": sha_file(db)}
    return {"schema": schema, "tables": tables}


def snapshot(env: Env) -> dict[str, Any]:
    """Everything a refused or read-only call must leave unchanged."""
    return {
        "db": sha_file(env.db) if env.db.exists() else None,
        "state": db_state(env.db),
        "root": digest_tree(env.root, skip=(".git/",)),
        "data": digest_tree(env.data_root, skip=("dashboard/project_locks",)),
    }


def table_rows(
    env: Env, table: str, where: str = "1=1", params: tuple = ()
) -> list[sqlite3.Row]:
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute(f"SELECT * FROM {table} WHERE {where}", params))


def version_numbers(env: Env, artifact_id: str) -> list[int]:
    rows = table_rows(
        env,
        "memory_artifact_versions",
        "artifact_id = ? ORDER BY artifact_version",
        (artifact_id,),
    )
    return [int(r["artifact_version"]) for r in rows]


def current_version(env: Env, artifact_id: str) -> int | None:
    rows = table_rows(env, "memory_artifacts", "id = ?", (artifact_id,))
    return int(rows[0]["artifact_version"]) if rows else None


def v2_receipts(env: Env) -> list[sqlite3.Row]:
    return table_rows(env, "mutation_receipts", "invocation_id IS NOT NULL")


def all_receipts(env: Env) -> list[sqlite3.Row]:
    return table_rows(env, "mutation_receipts")


def row_count(env: Env, table: str = "memory_artifacts") -> int:
    return len(table_rows(env, table))


def raw(result: Any) -> dict[str, Any]:
    value = result["raw"]
    assert isinstance(value, dict), result
    return value


def code(result: Any) -> Any:
    return raw(result).get("code")


def data(result: Any) -> dict[str, Any]:
    value = raw(result).get("data")
    return value if isinstance(value, dict) else {}


def reason(result: Any) -> Any:
    return data(result).get("reason")


def dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def ids(result: Any) -> list[str]:
    return [i["reference"]["artifact_id"] for i in raw(result)["items"]]


def find_key(value: Any, key: str) -> Any:
    """First value stored under `key` anywhere inside `value` (dicts and lists)."""
    if isinstance(value, dict):
        if key in value:
            return value[key]
        for sub in value.values():
            found = find_key(sub, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for sub in value:
            found = find_key(sub, key)
            if found is not None:
                return found
    return None


def payload_of(row: sqlite3.Row) -> dict[str, Any]:
    return json.loads(row["payload"])


def stable(result: Any) -> dict[str, Any]:
    """A ToolResult without its wall-clock field."""
    return {k: v for k, v in dict(result).items() if k != "duration_ms"}


# --- request builders --------------------------------------------------------------


def v2(**fields: Any) -> dict[str, Any]:
    return {"schema_version": 2, **fields}


def owner_of(owner: OwnerScope | None) -> dict[str, str] | None:
    return owner.as_dict() if owner is not None else None


def r_list(owner: OwnerScope | None = ALICE, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"subjects": list(SUBJECTS)}
    if owner is not None:
        body["owner_scope"] = owner.as_dict()
    body.update(extra)
    return v2(**body)


def r_ask(
    owner: OwnerScope | None = ALICE, query: str = "needle", **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"subjects": ["domain_knowledge"], "query": query}
    if owner is not None:
        body["owner_scope"] = owner.as_dict()
    body.update(extra)
    return v2(**body)


def r_expand(
    owner: OwnerScope | None = ALICE, artifact_id: str = "r1", **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"artifact_id": artifact_id, "artifact_version": 1}
    if owner is not None:
        body["owner_scope"] = owner.as_dict()
    body.update(extra)
    return v2(**body)


def r_related(
    owner: OwnerScope | None = ALICE, artifact_id: str = "r1", **extra: Any
) -> dict[str, Any]:
    return r_expand(owner, artifact_id, **{"depth": 1, **extra})


def r_history(
    owner: OwnerScope | None = ALICE, artifact_id: str = "r1", **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {"artifact_id": artifact_id}
    if owner is not None:
        body["owner_scope"] = owner.as_dict()
    body.update(extra)
    return v2(**body)


def r_explain(
    owner: OwnerScope | None = ALICE, artifact_id: str | None = "r1", **extra: Any
) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if artifact_id is not None:
        body["artifact_id"] = artifact_id
    if owner is not None:
        body["owner_scope"] = owner.as_dict()
    body.update(extra)
    return v2(**body)


def _mut(
    owner: OwnerScope | None, apply: bool, inv: str, eff: str, body: dict[str, Any]
) -> dict[str, Any]:
    out = dict(body)
    if owner is not None:
        out["owner_scope"] = owner.as_dict()
    out["apply"] = apply
    if inv:
        out["invocation_id"] = inv
        out["effect_id"] = eff
    return v2(**out)


def m_write(
    owner: OwnerScope | None = ALICE,
    *,
    apply: bool = True,
    inv: str = "inv-w",
    eff: str = "eff-w",
    text: str = "needle written",
    source: str = SRC,
    subject: str = "domain_knowledge",
    content: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _mut(
        owner,
        apply,
        inv if apply else "",
        eff,
        {
            "subject": subject,
            "content": content if content is not None else {"text": text},
            "source": source,
        },
    )


def m_edit(
    owner: OwnerScope | None = ALICE,
    *,
    artifact_id: str = "r1",
    expected_version: int = 1,
    apply: bool = True,
    inv: str = "inv-e",
    eff: str = "eff-e",
    text: str = "needle edited",
    subject: str = "domain_knowledge",
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "subject": subject,
        "artifact_id": artifact_id,
        "expected_version": expected_version,
    }
    if "correction" not in extra:
        body["content"] = {"text": text}
    body.update(extra)
    return _mut(owner, apply, inv if apply else "", eff, body)


def m_archive(
    owner: OwnerScope | None = ALICE,
    *,
    artifact_id: str = "r1",
    expected_version: int = 1,
    archived: bool = True,
    apply: bool = True,
    inv: str = "inv-a",
    eff: str = "eff-a",
    subject: str = "domain_knowledge",
) -> dict[str, Any]:
    return _mut(
        owner,
        apply,
        inv if apply else "",
        eff,
        {
            "subject": subject,
            "artifact_id": artifact_id,
            "expected_version": expected_version,
            "archived": archived,
        },
    )


def m_delete(
    owner: OwnerScope | None = ALICE,
    *,
    revisions: dict[str, int] | None = None,
    apply: bool = True,
    inv: str = "inv-d",
    eff: str = "eff-d",
    subject: str = "domain_knowledge",
) -> dict[str, Any]:
    revs = revisions if revisions is not None else {"r1": 1}
    return _mut(
        owner,
        apply,
        inv if apply else "",
        eff,
        {"subject": subject, "artifact_ids": list(revs), "expected_revisions": revs},
    )


def m_promote(
    owner: OwnerScope | None = ALICE,
    *,
    artifact_id: str = "r1",
    expected_version: int = 1,
    user_stated: bool = True,
    apply: bool = True,
    inv: str = "inv-p",
    eff: str = "eff-p",
    subject: str = "domain_knowledge",
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "subject": subject,
        "artifact_id": artifact_id,
        "expected_version": expected_version,
        "user_stated": user_stated,
    }
    body.update(extra)
    return _mut(owner, apply, inv if apply else "", eff, body)


def m_maintain(
    owner: OwnerScope | None = ALICE,
    *,
    apply: bool = True,
    inv: str = "inv-m",
    eff: str = "eff-m",
    candidate_ids: tuple[str, ...] = ("r1",),
    revisions: dict[str, int] | None = None,
    batch_size: int = 10,
    task: str = "staleness_sweep",
) -> dict[str, Any]:
    revs = revisions if revisions is not None else {i: 1 for i in candidate_ids}
    return _mut(
        owner,
        apply,
        inv if apply else "",
        eff,
        {
            "task": task,
            "batch_size": batch_size,
            "candidate_ids": list(candidate_ids),
            "expected_revisions": revs,
        },
    )


def m_link(
    owner: OwnerScope | None = ALICE,
    *,
    apply: bool = True,
    inv: str = "inv-l",
    eff: str = "eff-l",
    source_id: str = "r1",
    target_id: str = "r2",
    kind: str = "depends_on",
    source_version: int = 1,
    target_version: int = 1,
) -> dict[str, Any]:
    return _mut(
        owner,
        apply,
        inv if apply else "",
        eff,
        {
            "source_id": source_id,
            "source_version": source_version,
            "target_id": target_id,
            "target_version": target_version,
            "kind": kind,
            "origin_ref": "t06-test",
        },
    )


MUTATION_BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "write": m_write,
    "edit": m_edit,
    "archive": m_archive,
    "delete": m_delete,
    "promote": m_promote,
    "maintain": m_maintain,
    "link": m_link,
}
READ_BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "ask": r_ask,
    "recall": r_ask,
    "list": r_list,
    "expand": r_expand,
    "related": r_related,
    "history": r_history,
    "explain": r_explain,
}
V2_OPS = (*READ_BUILDERS, *MUTATION_BUILDERS)

PERM_W = ExecutionPermissions(cache_write=True)
PERM_NONE = ExecutionPermissions()


def call(
    env_or_root: Any,
    operation: str,
    request: dict[str, Any],
    *,
    perms: ExecutionPermissions | None = None,
    **top: Any,
) -> Any:
    """In-process `MemoryTool().run` (the single canonical route)."""
    root = getattr(env_or_root, "root", env_or_root)
    return MemoryTool().run(
        root,
        operation=cast(MemoryOperation, operation),
        request=request,
        permissions=perms,
        **top,
    )


def apply_call(env: Env, operation: str, request: dict[str, Any], **top: Any) -> Any:
    return call(env, operation, request, perms=PERM_W, **top)


def mcp_call(
    env_or_root: Any,
    operation: str,
    request: dict[str, Any],
    *,
    cache_write: bool = False,
    **top: Any,
) -> dict[str, Any]:
    """The MCP route: `validate_and_normalize` (before any dispatch) then the
    `make_tool_wrapper` the server registers for `rush_memory`."""
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.request_models import validate_and_normalize
    from rush.mcp_support.tool_registry import make_tool_wrapper

    root = getattr(env_or_root, "root", env_or_root)
    arguments: dict[str, Any] = {
        "path": str(root),
        "operation": operation,
        "request": request,
        **top,
    }
    if cache_write:
        arguments["allow_cache_write"] = True
    outcome = validate_and_normalize("rush_memory", arguments)
    if outcome.rejected:
        return json.loads(json.dumps(outcome.result, default=str))
    tool = MemoryTool()
    executor = InvocationExecutor()
    executor.register("memory", tool.__call__)
    result = make_tool_wrapper(tool, executor)(**(outcome.arguments or {}))
    return json.loads(json.dumps(dict(result), default=str))


def mcp_server_call(
    env_or_root: Any, operation: str, request: dict[str, Any], **top: Any
) -> dict[str, Any]:
    """The same call through a built `RushFastMCP` server (`call_tool`)."""
    from rush.mcp import build_server

    root = getattr(env_or_root, "root", env_or_root)
    arguments: dict[str, Any] = {
        "path": str(root),
        "operation": operation,
        "request": request,
        **top,
    }
    server = build_server()

    async def _go() -> Any:
        return await server.call_tool("rush_memory", arguments)

    return json.loads(asyncio.run(_go()).content[0].text)


def stdio_call(
    env: Env,
    operation: str,
    request: dict[str, Any],
    *,
    cache_write: bool = False,
    tool: str = "rush_memory",
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One call over a real `python -m rush.cli mcp serve` stdio child."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import TextContent

    payload: dict[str, Any] = (
        dict(arguments)
        if arguments is not None
        else {"path": str(env.root), "operation": operation, "request": request}
    )
    if cache_write:
        payload["allow_cache_write"] = True
    child_env = {**os.environ}
    for key in ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA", "USERPROFILE"):
        if key in os.environ:
            child_env[key] = os.environ[key]

    async def _run() -> dict[str, Any]:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rush.cli", "mcp", "serve"],
            cwd=str(PROJECT_ROOT),
            env=child_env,
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            response = await session.call_tool(tool, payload)
            block = response.content[0]
            assert isinstance(block, TextContent), block
            return json.loads(block.text)

    return asyncio.run(_run())


def cli_json(root: Path, args: list[str]) -> tuple[int, Any]:
    """`rush memory ...` through Click from `root`; `(exit_code, parsed --json output)`."""
    from click.testing import CliRunner

    from rush.cli import cli

    old = os.getcwd()
    os.chdir(root)
    try:
        result = CliRunner().invoke(cli, args)
    finally:
        os.chdir(old)
    try:
        parsed = json.loads(result.output)
    except ValueError:
        parsed = result.output
    return result.exit_code, parsed


def write_input(root: Path, name: str, request: dict[str, Any]) -> Path:
    path = root.parent / f"{name}.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    return path


def assert_v2_envelope(
    result: Any, operation: str, expected_code: str | None = None
) -> dict[str, Any]:
    assert set(result) == TOOL_RESULT_KEYS, sorted(result)
    body = raw(result)
    extras = set(body) - {"next_action"}
    assert V2_KEYS <= extras, sorted(body)
    assert extras - V2_KEYS <= V2_NAMED, sorted(extras - V2_KEYS)
    assert body["schema_version"] == 2
    assert body["operation"] == operation
    assert isinstance(body["items"], list)
    assert isinstance(body["complete"], bool)
    assert body["next_cursor"] is None or isinstance(body["next_cursor"], str)
    assert body["unknowns"] == sorted(set(body["unknowns"]))
    assert result["status"] == _status_of(body["code"]), (
        result["status"],
        body["code"],
    )
    if expected_code is not None:
        assert body["code"] == expected_code, dump(body)
    return body


def _status_of(code_value: str) -> str:
    from rush.tools.memory import _CODE_STATUS

    return _CODE_STATUS[code_value]


def only_zero_effects(env: Env, before: dict[str, Any], label: str = "") -> None:
    assert snapshot(env) == before, (
        f"{label}: a refused or read-only call changed state"
    )


# =============================================================================
# R1: query and administration, permissions and versions
# =============================================================================


def _alice_ids() -> set[str]:
    return set(ALICE_IDS.values())


def _bob_ids() -> set[str]:
    return set(BOB_IDS.values())


def test_t06_query_admin_permissions_and_versions(tmp_path: Path) -> None:
    env = make_env(tmp_path / "a")
    bob = _bob_ids()

    # Seven subjects, one Alice row each, no Bob id anywhere.
    listed = call(env, "list", r_list())
    body = assert_v2_envelope(listed, "list", "OK")
    assert len(body["items"]) == 7
    assert sorted(i["reference"]["subject"] for i in body["items"]) == sorted(SUBJECTS)
    assert {i["reference"]["artifact_id"] for i in body["items"]} == _alice_ids()
    assert all(
        i["reference"]["owner_scope"] == {"kind": "user", "id": "alice"}
        for i in body["items"]
    )
    assert body["complete"] is True and body["next_cursor"] is None
    assert not any(b in dump(body) for b in bob)

    # Result names: reference + compact keys on every item.
    for item in body["items"]:
        assert ITEM_KEYS <= set(item), sorted(set(ITEM_KEYS) - set(item))
        assert set(item["reference"]) == REFERENCE_KEYS, sorted(item["reference"])
        assert isinstance(item["reason_codes"], list)
        assert item["id"] == item["reference"]["artifact_id"]
        assert item["version"] == item["reference"]["artifact_version"]

    # Empty query browses in artifact_id order; omitted and "" agree.
    omitted = ids(call(env, "list", r_list()))
    blank = ids(call(env, "list", r_list(query="")))
    assert omitted == blank == sorted(_alice_ids())

    # Nonempty query searches; the owner filter never grants Bob.
    needle = call(env, "list", r_list(query="needle"))
    assert set(ids(needle)) == _alice_ids()
    assert not any(b in dump(raw(needle)) for b in bob)
    targeted = ids(
        call(
            env,
            "list",
            r_list(query="needle domain_knowledge", subjects=["domain_knowledge"]),
        )
    )
    assert targeted == ["r1"]
    asked = call(env, "ask", r_ask())
    assert ids(asked) == ["r1"]
    assert assert_v2_envelope(asked, "ask", "OK")["items"][0]["reason_codes"] == []

    # Request fields: exactly the declared set.
    before = snapshot(env)
    unknown = call(env, "list", r_list(not_a_field=1))
    assert_v2_envelope(unknown, "list", "E_INPUT")
    only_zero_effects(env, before, "unknown request key")

    # Historical view and `history` need the `history` grant.
    nohist = make_env(tmp_path / "b", ops=NO_HISTORY_OPS)
    before_nh = snapshot(nohist)
    for operation, req in (
        ("history", r_history()),
        ("list", r_list(archive_mode="historical")),
        ("ask", r_ask(archive_mode="historical")),
        ("expand", r_expand(archive_mode="historical")),
    ):
        denied = call(nohist, operation, req)
        assert_v2_envelope(denied, operation, "E_PERMISSION")
        assert reason(denied) == "operation_not_granted", operation
    only_zero_effects(nohist, before_nh, "no history grant")

    # Mutations: edit r1@1 -> r1@2, old version retained.
    first = apply_call(env, "edit", m_edit())
    first_body = assert_v2_envelope(first, "edit", "OK")
    assert version_numbers(env, "r1") == [1, 2]
    assert current_version(env, "r1") == 2
    assert len(v2_receipts(env)) == 1
    assert any(
        i["reference"]["artifact_id"] == "r1"
        and i["reference"]["artifact_version"] == 2
        for i in first_body["items"]
    )

    # History: versions oldest first, decided per version.
    hist = call(env, "history", r_history())
    hist_body = assert_v2_envelope(hist, "history", "OK")
    assert hist_body["items"] == []
    assert [v["reference"]["artifact_version"] for v in hist_body["versions"]] == [1, 2]
    assert hist_body["versions"][0]["usable_as_current"] is False
    assert isinstance(hist_body["versions"][1]["usable_as_current"], bool)
    assert all(
        v["reference"]["owner_scope"] == {"kind": "user", "id": "alice"}
        for v in hist_body["versions"]
    )

    # Retry of the identical effect: byte-identical raw, no r1@3, no new receipt row.
    receipts_before = len(all_receipts(env))
    again = apply_call(env, "edit", m_edit())
    assert dump(raw(again)) == dump(raw(first))
    assert version_numbers(env, "r1") == [1, 2]
    assert len(all_receipts(env)) == receipts_before
    # Same effect ids, different request digest: conflict, nothing changes.
    conflict = apply_call(env, "edit", m_edit(text="needle other bytes"))
    assert_v2_envelope(conflict, "edit", "E_VERSION")
    assert reason(conflict) == "effect_digest_conflict"
    assert version_numbers(env, "r1") == [1, 2]

    # Matching content alone never dedupes independent writes.
    rows_before = row_count(env)
    w1 = apply_call(env, "write", m_write(inv="inv-w1", eff="eff-w1"))
    w2 = apply_call(env, "write", m_write(inv="inv-w2", eff="eff-w2"))
    assert code(w1) == code(w2) == "OK"
    assert row_count(env) == rows_before + 2
    assert ids(w1) != ids(w2)

    # Restore uses archive archived=false.
    assert env.store is not None
    put(env.store, "dk2", ALICE, text="needle dk2")
    gone = apply_call(env, "archive", m_archive(artifact_id="dk2", expected_version=1))
    assert code(gone) == "OK"
    assert "dk2" not in ids(call(env, "list", r_list()))
    back = apply_call(
        env,
        "archive",
        m_archive(
            artifact_id="dk2",
            expected_version=current_version(env, "dk2") or 0,
            archived=False,
            inv="inv-a2",
            eff="eff-a2",
        ),
    )
    assert code(back) == "OK"
    assert "dk2" in ids(call(env, "list", r_list()))

    # Delete {r1:2, dk2:1}: dk2 is stale (archive and restore advanced it), so both roll back.
    rows_now = row_count(env)
    stale = apply_call(
        env,
        "delete",
        m_delete(revisions={"r1": 2, "dk2": 1}, inv="inv-d1", eff="eff-d1"),
    )
    assert_v2_envelope(stale, "delete", "E_VERSION")
    assert row_count(env) == rows_now
    assert current_version(env, "r1") == 2 and current_version(env, "dk2") == 3

    # Promotion: a new candidate C (id != r1) at version 1, its decision as C@2.
    pro = make_env(tmp_path / "c")
    existing = {r["id"] for r in table_rows(pro, "memory_artifacts")}
    receipts_pre = len(all_receipts(pro))
    promoted = apply_call(pro, "promote", m_promote())
    assert_v2_envelope(promoted, "promote", "OK")
    created = {r["id"] for r in table_rows(pro, "memory_artifacts")} - existing
    assert len(created) == 1
    cand = next(iter(created))
    assert cand != "r1"
    assert version_numbers(pro, cand) == [1, 2]
    new_receipts = all_receipts(pro)[receipts_pre:]
    promote_receipts = [r for r in v2_receipts(pro) if r["kind"] == "promote"]
    assert len(promote_receipts) == 1 and len(new_receipts) == 1
    pay = payload_of(promote_receipts[0])
    assert find_key(pay, "candidate_ref") == {
        "artifact_id": cand,
        "artifact_version": 1,
    }
    decision = find_key(pay, "decision_ref")
    assert decision["artifact_id"] == cand and decision["artifact_version"] == 2
    assert decision["promoted"] is True
    assert current_version(pro, "r1") == 1
    r1_row = table_rows(pro, "memory_artifacts", "id = 'r1'")[0]
    assert r1_row["trust_tier"] == "DERIVED"
    assert json.loads(r1_row["content"]) == {"text": "needle domain_knowledge alice"}

    # Explain with no relations returns unknowns, never invented text; no model call.
    ex = call(pro, "explain", r_explain())
    ex_body = assert_v2_envelope(ex, "explain", "OK")
    for bucket in ("supporting", "contrary", "attempted", "affected"):
        assert ex_body[bucket] == [], bucket
    assert ex_body["unknowns"] == ["no_recorded_rationale"]
    assert set(ex_body) <= V2_KEYS | V2_NAMED

    # Mutation preconditions: each missing one leaves the store untouched and returns
    # the reviewed form unchanged.
    gate = make_env(tmp_path / "d")
    nowrite = make_env(tmp_path / "e", ops=("ask", "list", "expand", "history"))
    cases: list[
        tuple[str, Env, str, dict[str, Any], ExecutionPermissions, str, str | None]
    ] = [
        ("no_invocation_id", gate, "edit", m_edit(inv=""), PERM_W, "E_INPUT", None),
        (
            "owner_omitted",
            gate,
            "edit",
            m_edit(owner=None),
            PERM_W,
            "E_INPUT",
            "owner_required",
        ),
        (
            "no_cache_write",
            gate,
            "edit",
            m_edit(),
            PERM_NONE,
            "E_PERMISSION",
            "cache_write_required",
        ),
        (
            "no_write_grant",
            nowrite,
            "edit",
            m_edit(),
            PERM_W,
            "E_PERMISSION",
            "operation_not_granted",
        ),
    ]
    for label, target, operation, request, perms, want_code, want_reason in cases:
        snap = snapshot(target)
        result = call(target, operation, request, perms=perms)
        assert_v2_envelope(result, operation, want_code)
        if want_reason is not None:
            assert reason(result) == want_reason, label
        only_zero_effects(target, snap, label)
        if want_code != "E_INPUT" or want_reason is not None:
            echoed = data(result)["request"]
            for key, value in request.items():
                assert echoed[key] == value, (label, key)
    missing_version = {k: v for k, v in m_edit().items() if k != "expected_version"}
    snap = snapshot(gate)
    result = call(gate, "edit", missing_version, perms=PERM_W)
    assert_v2_envelope(result, "edit", "E_INPUT")
    only_zero_effects(gate, snap, "no expected_version")

    # Correction downstream: link r1 -> r2, reject r1; `affected` names the linked row
    # and the rejected row is absent from the next ask.
    cor = make_env(tmp_path / "f")
    assert code(apply_call(cor, "link", m_link())) == "OK"
    rejected = apply_call(
        cor,
        "edit",
        m_edit(
            inv="inv-c", eff="eff-c", correction={"kind": "reject", "reason": "wrong"}
        ),
    )
    rej_body = assert_v2_envelope(rejected, "edit", "OK")
    explained = call(cor, "explain", r_explain())
    assert rej_body["data"]["affected"] == raw(explained)["affected"]
    assert any(
        a["reference"]["artifact_id"] == "r2" for a in rej_body["data"]["affected"]
    )
    assert "r1" not in ids(call(cor, "ask", r_ask()))


# =============================================================================
# R2: strict v2 request rejections
# =============================================================================


def _huge() -> int:
    return 10**400


def _base_cases() -> list[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    """`(label, operation, request, top-level kwargs)` -- every one is `E_INPUT`."""
    cases: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []

    def add(label: str, op: str, req: dict[str, Any], **top: Any) -> None:
        cases.append((label, op, req, top))

    add("unknown_key", "list", r_list(bogus=1))
    value: Any
    for name in ("limit", "max_tokens", "max_bytes"):
        for label, value in (
            ("true", True),
            ("float", 1.5),
            ("str", "20"),
            ("zero", 0),
            ("neg", -1),
            ("null", None),
            ("huge", _huge()),
        ):
            if name != "limit" and label == "huge":
                continue  # an oversized budget is type-valid and admitted
            add(f"{name}_{label}", "list", r_list(**{name: value}))
    add("limit_101", "list", r_list(limit=101))
    add("top_level_limit_beside_v2", "list", r_list(), limit=5)
    add("top_level_max_bytes_beside_v2", "list", r_list(), max_bytes=4096)
    for field, value in (
        ("subject", "domain_knowledge"),
        ("session_allowlist", [SRC]),
        ("source", SRC),
        ("content", {"text": "x"}),
        ("symbol_ref", "a.py::b"),
        ("source_kind", "local_tool"),
        ("owner_scope", ALICE.as_dict()),
        ("include_archived", True),
        ("user_stated", True),
        ("candidate_sources", [SRC]),
        ("task", "staleness_sweep"),
        ("batch_size", 10),
    ):
        add(f"mixed_legacy_{field}", "list", r_list(), **{field: value})
    add("mixed_legacy_query", "list", r_list(), query="x")
    add("subjects_string", "list", r_list(subjects="episodic"))
    add("subjects_empty", "list", r_list(subjects=[]))
    add("subjects_duplicate", "list", r_list(subjects=["episodic", "episodic"]))
    add("subjects_unknown", "list", r_list(subjects=["nope"]))
    add("owner_string", "list", r_list(owner_scope="user:alice"))
    add("owner_null", "list", r_list(owner_scope=None))
    add(
        "owner_unhashable_kind",
        "list",
        r_list(owner_scope={"kind": ["user"], "id": "x"}),
    )
    add("owner_id_nul", "list", r_list(owner_scope={"kind": "user", "id": "a\x00b"}))
    add("sources_empty", "list", r_list(sources=[]))
    add("sources_star", "list", r_list(sources=["*"]))
    add("sources_nul", "list", r_list(sources=["a\x00b"]))
    add("sources_cc", "list", r_list(sources=["a\x07b"]))
    add("sources_cf", "list", r_list(sources=["a\u200bb"]))
    add("sources_surrogate", "list", r_list(sources=["a\ud800b"]))
    add("sources_duplicate", "list", r_list(sources=[SRC, SRC]))
    add("trust_bad", "list", r_list(trust_tiers=["BOGUS"]))
    add("trust_empty", "list", r_list(trust_tiers=[]))
    add("freshness_bad", "list", r_list(freshness=["fresh"]))
    add("archive_mode_bad", "list", r_list(archive_mode="all"))
    add("cursor_empty", "list", r_list(cursor=""))
    add("cursor_nul", "list", r_list(cursor="a\x00b"))
    add("cursor_int", "list", r_list(cursor=5))
    add("query_nul", "list", r_list(query="a\x00b"))
    add("query_surrogate", "list", r_list(query="a\ud800b"))
    add("query_int", "list", r_list(query=5))
    add("ask_query_empty", "ask", r_ask(query=""))
    add("ask_query_missing", "ask", {k: v for k, v in r_ask().items() if k != "query"})
    add("retrieval_bad", "list", r_list(retrieval="vector"))
    add("embedding_model_int", "list", r_list(retrieval="hybrid", embedding_model=5))
    add("encoding_int", "list", r_list(encoding=5))
    add("data_root_key", "list", r_list(data_root="/tmp/x"))
    add("expand_version_true", "expand", r_expand(artifact_version=True))
    add("expand_version_zero", "expand", r_expand(artifact_version=0))
    add("expand_version_huge", "expand", r_expand(artifact_version=_huge()))
    add("expand_offset_neg", "expand", r_expand(offset=-1))
    add("expand_offset_huge", "expand", r_expand(offset=_huge()))
    add("expand_representation", "expand", r_expand(representation="hex"))
    add("expand_id_empty", "expand", r_expand(artifact_id=""))
    add("expand_id_nul", "expand", r_expand(artifact_id="a\x00b"))
    add("expand_id_cc", "expand", r_expand(artifact_id="a\x07b"))
    add("expand_id_cf", "expand", r_expand(artifact_id="a\u200bb"))
    add("expand_id_surrogate", "expand", r_expand(artifact_id="a\ud800b"))
    add("expand_id_slash", "expand", r_expand(artifact_id="a/b"))
    add("expand_limit_key", "expand", r_expand(limit=5))
    add("related_depth_3", "related", r_related(depth=3))
    add("related_depth_huge", "related", r_related(depth=_huge()))
    add("related_max_nodes_33", "related", r_related(max_nodes=33))
    add("related_max_nodes_huge", "related", r_related(max_nodes=_huge()))
    add("history_representation", "history", r_history(representation="hex"))
    add("history_both_forms", "history", r_history(query="x"))
    add("history_id_missing", "history", v2(owner_scope=ALICE.as_dict()))
    add("explain_both", "explain", r_explain(query="x"))
    add("explain_neither", "explain", r_explain(artifact_id=None))
    add("explain_query_empty", "explain", r_explain(artifact_id=None, query=""))
    add("write_content_nan", "write", m_write(content={"text": "x", "n": float("nan")}))
    add("write_content_inf", "write", m_write(content={"text": "x", "n": float("inf")}))
    add(
        "write_content_ninf",
        "write",
        m_write(content={"text": "x", "n": float("-inf")}),
    )
    add("write_source_star", "write", m_write(source="*"))
    add("write_source_nul", "write", m_write(source="a\x00b"))
    add("write_source_empty", "write", m_write(source=""))
    add("write_subject_bad", "write", m_write(subject="nope"))
    add("write_no_ids", "write", m_write(inv=""))
    add("write_invocation_only", "write", {**m_write(), "effect_id": None})
    add("write_invocation_nul", "write", m_write(inv="a\x00b"))
    add("write_effect_cc", "write", m_write(eff="a\x07b"))
    add("write_effect_cf", "write", m_write(eff="a\u200bb"))
    add("write_effect_surrogate", "write", m_write(eff="a\ud800b"))
    add("write_apply_str", "write", {**m_write(), "apply": "true"})
    add("write_apply_int", "write", {**m_write(), "apply": 1})
    add("write_symbol_ref_int", "write", {**m_write(), "symbol_ref": 5})
    add("edit_version_true", "edit", m_edit(expected_version=True))
    add("edit_version_huge", "edit", m_edit(expected_version=_huge()))
    add(
        "edit_content_and_correction",
        "edit",
        m_edit(correction={"kind": "correct", "reason": "r"}, content={"text": "x"})
        | {"content": {"text": "x"}, "correction": {"kind": "reject", "reason": "r"}},
    )
    add(
        "edit_correction_reject_with_content",
        "edit",
        {**m_edit(), "correction": {"kind": "reject", "reason": "r"}},
    )
    add(
        "edit_correction_kind",
        "edit",
        m_edit(correction={"kind": "erase", "reason": "r"}),
    )
    add(
        "edit_correction_reason_empty",
        "edit",
        m_edit(correction={"kind": "reject", "reason": ""}),
    )
    add(
        "edit_correction_reason_cc",
        "edit",
        m_edit(correction={"kind": "reject", "reason": "a\x07b"}),
    )
    add(
        "edit_correction_reason_cf",
        "edit",
        m_edit(correction={"kind": "reject", "reason": "a\u200bb"}),
    )
    add(
        "edit_correction_reason_surrogate",
        "edit",
        m_edit(correction={"kind": "reject", "reason": "a\ud800b"}),
    )
    add(
        "edit_correction_supersedes_empty",
        "edit",
        m_edit(correction={"kind": "supersede", "reason": "r", "supersedes": []}),
    )
    add(
        "edit_correction_supersedes_65",
        "edit",
        m_edit(
            correction={
                "kind": "supersede",
                "reason": "r",
                "supersedes": [
                    {"artifact_id": f"x{i}", "artifact_version": 1} for i in range(65)
                ],
            }
        ),
    )
    add(
        "edit_correction_supersedes_duplicate",
        "edit",
        m_edit(
            correction={
                "kind": "supersede",
                "reason": "r",
                "supersedes": [
                    {"artifact_id": "r2", "artifact_version": 1},
                    {"artifact_id": "r2", "artifact_version": 1},
                ],
            }
        ),
    )
    add(
        "edit_correction_supersedes_version_zero",
        "edit",
        m_edit(
            correction={
                "kind": "supersede",
                "reason": "r",
                "supersedes": [{"artifact_id": "r2", "artifact_version": 0}],
            }
        ),
    )
    add(
        "edit_correction_supersedes_version_huge",
        "edit",
        m_edit(
            correction={
                "kind": "supersede",
                "reason": "r",
                "supersedes": [{"artifact_id": "r2", "artifact_version": _huge()}],
            }
        ),
    )
    add(
        "edit_correction_supersedes_version_true",
        "edit",
        m_edit(
            correction={
                "kind": "supersede",
                "reason": "r",
                "supersedes": [{"artifact_id": "r2", "artifact_version": True}],
            }
        ),
    )
    add(
        "edit_correction_nan",
        "edit",
        {
            **m_edit(correction={"kind": "correct", "reason": "r"}),
            "content": {"n": float("nan")},
        },
    )
    add("archive_archived_str", "archive", {**m_archive(), "archived": "yes"})
    add(
        "delete_keys_mismatch",
        "delete",
        {**m_delete(revisions={"r1": 1}), "artifact_ids": ["r1", "r2"]},
    )
    add(
        "delete_ids_empty",
        "delete",
        {**m_delete(), "artifact_ids": [], "expected_revisions": {}},
    )
    add("delete_ids_duplicate", "delete", {**m_delete(), "artifact_ids": ["r1", "r1"]})
    add(
        "delete_ids_101", "delete", m_delete(revisions={f"x{i}": 1 for i in range(101)})
    )
    add("delete_revision_bool", "delete", m_delete(revisions={"r1": True}))
    add("delete_revision_huge", "delete", m_delete(revisions={"r1": _huge()}))
    add("promote_user_stated_str", "promote", {**m_promote(), "user_stated": "yes"})
    add("promote_refs_empty", "promote", m_promote(candidate_refs=[]))
    add(
        "promote_refs_65",
        "promote",
        m_promote(
            candidate_refs=[
                {"id": f"x{i}", "version": 1, "source": SRC} for i in range(65)
            ]
        ),
    )
    add("maintain_batch_zero", "maintain", m_maintain(batch_size=0))
    add("maintain_batch_1001", "maintain", m_maintain(batch_size=1001))
    add("maintain_batch_true", "maintain", {**m_maintain(), "batch_size": True})
    add("maintain_batch_huge", "maintain", m_maintain(batch_size=_huge()))
    add(
        "maintain_revisions_missing_key",
        "maintain",
        m_maintain(candidate_ids=("r1", "r2"), revisions={"r1": 1}),
    )
    add(
        "maintain_revisions_extra_key",
        "maintain",
        m_maintain(candidate_ids=("r1",), revisions={"r1": 1, "r2": 1}),
    )
    add("maintain_revisions_bool", "maintain", m_maintain(revisions={"r1": True}))
    add("maintain_revisions_huge", "maintain", m_maintain(revisions={"r1": _huge()}))
    add("maintain_revisions_zero", "maintain", m_maintain(revisions={"r1": 0}))
    add("link_preview", "link", m_link(apply=False))
    add("link_kind_bad", "link", m_link(kind="loves"))
    add("link_version_huge", "link", m_link(source_version=_huge()))
    return cases


_BASE_CASES = _base_cases()


@pytest.mark.parametrize(
    ("label", "operation", "body", "top"),
    [pytest.param(*c, id=c[0]) for c in _BASE_CASES],
)
def test_t06_v2_strict_request_rejections(
    label: str,
    operation: str,
    body: dict[str, Any],
    top: dict[str, Any],
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    before = snapshot(env)
    # In-process: legacy kwargs (`top`) are `run` parameters except MCP-only ones.
    mcp_only = {"limit", "max_bytes"}
    run_top = {k: v for k, v in top.items() if k not in mcp_only}
    if mcp_only & set(top):
        inproc = None
    else:
        inproc = call(env, operation, body, perms=PERM_W, **run_top)
    over_mcp = mcp_call(env, operation, body, cache_write=True, **top)
    for result in (r for r in (inproc, over_mcp) if r is not None):
        body = assert_v2_envelope(result, operation, "E_INPUT")
        assert result["status"] == "error"
        assert body["items"] == [] and body["next_cursor"] is None
        assert body["complete"] is False
        assert body["data"].get("details") or body["data"].get("message"), label
    if inproc is not None:
        assert dump(raw(inproc)) == dump(raw(over_mcp)), label
    only_zero_effects(env, before, label)


def test_t06_v2_strict_admits_type_valid_huge_budgets(tmp_path: Path) -> None:
    """`max_bytes`/`max_tokens` = 10**400 is type-valid: admitted, and the response fits."""
    env = make_env(tmp_path)
    for field in ("max_bytes", "max_tokens"):
        result = call(env, "list", r_list(**cast(dict[str, Any], {field: _huge()})))
        assert_v2_envelope(result, "list", "OK")


def test_t06_v2_null_cursor_is_a_first_page(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    plain = call(env, "list", r_list())
    explicit = call(env, "list", {**r_list(), "cursor": None})
    assert_v2_envelope(plain, "list", "OK")
    assert_v2_envelope(explicit, "list", "OK")
    assert dump(raw(explicit)) == dump(raw(plain))


def test_t06_v2_budget_admission_precedes_effects(tmp_path: Path) -> None:
    """C05: a cap below the complete `E_BUDGET` raw is `E_INPUT` with the cap named,
    counted as an admission failure, and nothing is created (also on an absent store)."""
    env = make_env(tmp_path / "present")
    absent = make_env(tmp_path / "absent", seeded=False, create_store=False)
    for target in (env, absent):
        before = snapshot(target)
        for field in ("max_bytes", "max_tokens"):
            result = call(
                target, "list", r_list(**cast(dict[str, Any], {field: 1})), perms=PERM_W
            )
            body = assert_v2_envelope(result, "list", "E_INPUT")
            assert body["data"].get("field") == field, dump(body)
        assert not (absent.root / ".rush" / "memory.db").exists()
        only_zero_effects(target, before, "admission")
    fits = call(env, "list", r_list(), perms=PERM_W)
    assert code(fits) == "OK"


# =============================================================================
# R3: receipts (D29)
# =============================================================================


def _op_id(invocation_id: str, effect_id: str) -> str:
    return (
        "v2:"
        + hashlib.sha256(
            json.dumps([invocation_id, effect_id]).encode("utf-8")
        ).hexdigest()
    )


def _inject_after(
    monkeypatch: pytest.MonkeyPatch, owner: Any, name: str
) -> dict[str, bool]:
    """Make `owner.name` fail once it has completed; `state["fired"]` proves it ran."""
    original = getattr(owner, name)
    state = {"fired": False}

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        original(*args, **kwargs)
        state["fired"] = True
        raise RuntimeError(f"injected failure after {name}")

    monkeypatch.setattr(owner, name, wrapper)
    return state


def _legacy_receipt_requests(receipt_id: str) -> dict[str, dict[str, Any]]:
    """Legacy (no `schema_version`) delete/edit/archive requests carrying a receipt id."""
    scope = {"scope": "domain_knowledge", "owner_scope": ALICE.as_dict(), "apply": True}
    return {
        "delete": {
            "artifact_ids": ["r1"],
            "expected_revisions": {"r1": 1},
            "receipt_operation_ids": {"r1": receipt_id},
            **scope,
        },
        "edit": {
            "id": "r1",
            "expected_version": 1,
            "content": {"text": "x"},
            "receipt_operation_id": receipt_id,
            **scope,
        },
        "archive": {
            "id": "r1",
            "expected_version": 1,
            "receipt_operation_id": receipt_id,
            **scope,
        },
    }


_RECEIPT_CASES = [
    "same_digest_replay",
    "different_digest_conflict",
    "partial_unique_index",
    "plain_insert",
    "operation_id_derivation",
    "one_id_alone",
    "legacy_v2_prefix_input",
    "legacy_receipt_insert_or_replace",
    "promote_one_receipt_both_refs",
    "promote_failure_after_receipt",
    "promote_failure_after_promotion",
]


@pytest.mark.parametrize("case", [pytest.param(c, id=c) for c in _RECEIPT_CASES])
def test_t06_receipt_identity(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    if case == "same_digest_replay":
        first = apply_call(env, "edit", m_edit())
        assert code(first) == "OK"
        receipts = all_receipts(env)
        second = apply_call(env, "edit", m_edit())
        assert dump(raw(second)) == dump(raw(first))
        assert version_numbers(env, "r1") == [1, 2]
        assert len(all_receipts(env)) == len(receipts)
    elif case == "different_digest_conflict":
        assert code(apply_call(env, "edit", m_edit())) == "OK"
        conflict = apply_call(env, "edit", m_edit(text="needle different"))
        assert (
            code(conflict) == "E_VERSION"
            and reason(conflict) == "effect_digest_conflict"
        )
        assert version_numbers(env, "r1") == [1, 2]
    elif case == "partial_unique_index":
        cols = {
            r["name"] for r in table_rows(env, "pragma_table_info('mutation_receipts')")
        }
        assert {"invocation_id", "effect_id", "request_digest"} <= cols
        rows = table_rows(
            env, "sqlite_master", "type = 'index' AND name = 'idx_mutation_receipts_v2'"
        )
        assert len(rows) == 1
        sql = re.sub(r"\s+", " ", rows[0]["sql"]).upper()
        assert (
            "UNIQUE" in sql
            and "INVOCATION_ID" in sql
            and "EFFECT_ID" in sql
            and "WHERE" in sql
        )
    elif case == "plain_insert":
        store = env.store
        assert store is not None
        kwargs: dict[str, Any] = {
            "invocation_id": "i1",
            "effect_id": "e1",
            "request_digest": "d" * 64,
            "artifact_id": None,
            "kind": "write",
            "revision": None,
            "payload": {"x": 1},
        }
        with store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            store._write_v2_receipt(conn, **kwargs)
            with pytest.raises(sqlite3.IntegrityError):
                store._write_v2_receipt(conn, **kwargs)
            conn.rollback()
    elif case == "operation_id_derivation":
        assert code(apply_call(env, "edit", m_edit(inv="inv-x", eff="eff-x"))) == "OK"
        rows = v2_receipts(env)
        assert [r["operation_id"] for r in rows] == [_op_id("inv-x", "eff-x")]
        assert rows[0]["invocation_id"] == "inv-x" and rows[0]["effect_id"] == "eff-x"
        assert re.fullmatch(r"[0-9a-f]{64}", rows[0]["request_digest"])
        assert (
            rows[0]["kind"] == "edit"
            and rows[0]["artifact_id"] == "r1"
            and rows[0]["revision"] == 2
        )
    elif case == "one_id_alone":
        snap = snapshot(env)
        for body in (
            {k: v for k, v in m_edit().items() if k != "effect_id"},
            {k: v for k, v in m_edit().items() if k != "invocation_id"},
        ):
            result = apply_call(env, "edit", body)
            assert_v2_envelope(result, "edit", "E_INPUT")
        only_zero_effects(env, snap, "one id alone")
    elif case == "legacy_v2_prefix_input":
        snap = snapshot(env)
        for operation, request in _legacy_receipt_requests("v2:forged").items():
            result = mcp_call(env, operation, request, cache_write=True)
            assert code(result) == "E_INPUT", (operation, dump(raw(result)))
            fields = {tuple(d["loc"])[-1] for d in data(result).get("details", [])}
            assert fields & {"receipt_operation_id", "receipt_operation_ids"}, dump(
                raw(result)
            )
        only_zero_effects(env, snap, "v2 prefix on a legacy receipt id")
        # Control: the same requests with an ordinary id are valid.
        # Each operation gets its own project: delete removes r1, so the edit and
        # archive that follow it on one store would fail with an unknown artifact_id.
        for operation, request in _legacy_receipt_requests("ordinary-id").items():
            control = make_env(tmp_path / f"control_{operation}")
            ok = mcp_call(control, operation, request, cache_write=True)
            assert code(ok) == "OK", (operation, dump(raw(ok)))
    elif case == "legacy_receipt_insert_or_replace":
        store = env.store
        assert store is not None
        with store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            store._write_receipt(conn, "legacy-op", None, "write", 1, {"v": 1})
            conn.commit()
        with store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            store._write_receipt(conn, "legacy-op", None, "write", 2, {"v": 2})
            conn.commit()
        receipt = store.get_receipt("legacy-op")
        assert receipt is not None
        assert receipt["payload"] == {"v": 2} and receipt["revision"] == 2
    else:
        _promote_receipt_case(env, case, monkeypatch)


def _promote_receipt_case(env: Env, case: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import rush.memory.store as store_module

    before_ids = {r["id"] for r in table_rows(env, "memory_artifacts")}
    before_versions = row_count(env, "memory_artifact_versions")
    before_receipts = len(all_receipts(env))
    if case == "promote_one_receipt_both_refs":
        first = apply_call(env, "promote", m_promote())
        assert code(first) == "OK"
        created = {r["id"] for r in table_rows(env, "memory_artifacts")} - before_ids
        assert len(created) == 1
        cand = next(iter(created))
        assert len(all_receipts(env)) == before_receipts + 1
        pay = payload_of(v2_receipts(env)[0])
        assert find_key(pay, "candidate_ref")["artifact_id"] == cand
        assert find_key(pay, "decision_ref")["artifact_id"] == cand
        replay = apply_call(env, "promote", m_promote())
        assert dump(raw(replay)) == dump(raw(first))
        assert cand in dump(raw(replay))
        assert {
            r["id"] for r in table_rows(env, "memory_artifacts")
        } == before_ids | created
        return
    if case == "promote_failure_after_receipt":
        state = _inject_after(
            monkeypatch, store_module.TypedArtifactStore, "_write_v2_receipt"
        )
    else:
        state = _inject_after(monkeypatch, store_module, "promote_stored_artifact")
    with contextlib.suppress(Exception):
        apply_call(env, "promote", m_promote())
    assert state["fired"], "the v2 promote never reached the injected step"
    assert {r["id"] for r in table_rows(env, "memory_artifacts")} == before_ids
    assert row_count(env, "memory_artifact_versions") == before_versions
    assert len(all_receipts(env)) == before_receipts
    assert current_version(env, "r1") == 1


def test_t06_receipt_replay_rechecks_access(tmp_path: Path) -> None:
    # Source narrowing, including a two-source delete (binding.sources).
    env = make_env(tmp_path / "n", ops=GRANT_OPS)
    env.grants["alice"] = grant(env, env.data_root, ALICE, sources=(SRC, "s2"))
    assert env.store is not None
    put(env.store, "two-a", ALICE, source=SRC, text="needle two a")
    put(env.store, "two-b", ALICE, source="s2", text="needle two b")
    deleted = apply_call(
        env,
        "delete",
        m_delete(revisions={"two-a": 1, "two-b": 1}, inv="inv-two", eff="eff-two"),
    )
    assert code(deleted) == "OK"
    digest = v2_receipts(env)[-1]["request_digest"]
    payload_text = v2_receipts(env)[-1]["payload"]
    env.grants["alice"] = grant(env, env.data_root, ALICE, sources=(SRC,))
    snap = snapshot(env)
    replay = apply_call(
        env,
        "delete",
        m_delete(revisions={"two-a": 1, "two-b": 1}, inv="inv-two", eff="eff-two"),
    )
    assert_v2_envelope(replay, "delete", "E_NOT_VISIBLE")
    text = dump(raw(replay))
    assert digest not in text and payload_text not in text
    only_zero_effects(env, snap, "source narrowing")

    # Owner change: Bob replays Alice's effect.
    own = make_env(tmp_path / "o")
    assert code(apply_call(own, "write", m_write(inv="inv-o", eff="eff-o"))) == "OK"
    snap = snapshot(own)
    by_bob = apply_call(own, "write", m_write(owner=BOB, inv="inv-o", eff="eff-o"))
    assert_v2_envelope(by_bob, "write", "E_NOT_VISIBLE")
    only_zero_effects(own, snap, "owner change")

    # Revocation: the replaying access can no longer resolve.
    rev = make_env(tmp_path / "r")
    assert code(apply_call(rev, "write", m_write(inv="inv-r", eff="eff-r"))) == "OK"
    revoke(rev, ALICE)
    snap = snapshot(rev)
    gone = apply_call(rev, "write", m_write(inv="inv-r", eff="eff-r"))
    assert_v2_envelope(gone, "write", "E_PERMISSION")
    assert reason(gone) == "revoked"
    only_zero_effects(rev, snap, "revocation")

    # A reviewed delete of the result: the replay is not visible.
    rd = make_env(tmp_path / "d")
    first = apply_call(rd, "write", m_write(inv="inv-w", eff="eff-w"))
    new_id = ids(first)[0]
    assert (
        code(
            apply_call(
                rd,
                "delete",
                m_delete(revisions={new_id: 1}, inv="inv-del", eff="eff-del"),
            )
        )
        == "OK"
    )
    snap = snapshot(rd)
    after_delete = apply_call(rd, "write", m_write(inv="inv-w", eff="eff-w"))
    assert_v2_envelope(after_delete, "write", "E_NOT_VISIBLE")
    assert new_id not in dump(raw(after_delete))
    only_zero_effects(rd, snap, "reviewed delete")

    # An archive effect replayed by the same access returns the original result.
    arc = make_env(tmp_path / "a")
    original = apply_call(arc, "archive", m_archive())
    assert code(original) == "OK"
    again = apply_call(arc, "archive", m_archive())
    assert dump(raw(again)) == dump(raw(original))
    assert current_version(arc, "r1") == 2


def test_t06_v2_namespace_reserved(tmp_path: Path) -> None:
    from rush.memory.authorization import MemoryPolicyError

    env = make_env(tmp_path)
    assert code(apply_call(env, "write", m_write(inv="inv-ns", eff="eff-ns"))) == "OK"
    op_id = _op_id("inv-ns", "eff-ns")
    row_before = table_rows(env, "mutation_receipts", "operation_id = ?", (op_id,))[0]
    versions_before = row_count(env, "memory_artifact_versions")
    store = env.store
    assert store is not None
    with store._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(MemoryPolicyError) as direct:
            store._write_receipt(conn, op_id, None, "write", 1, {"forged": True})
        assert (direct.value.code, direct.value.reason) == (
            "E_INPUT",
            "reserved_receipt_namespace",
        )
        with pytest.raises(MemoryPolicyError) as fresh:
            store._write_receipt(conn, "v2:never-issued", None, "write", 1, {})
        assert (fresh.value.code, fresh.value.reason) == (
            "E_INPUT",
            "reserved_receipt_namespace",
        )
        conn.rollback()
    with pytest.raises(MemoryPolicyError) as handoff:
        store.write_handoff_delivery_receipt(
            op_id, artifact_id="r1", payload={"forged": True}
        )
    assert (handoff.value.code, handoff.value.reason) == (
        "E_INPUT",
        "reserved_receipt_namespace",
    )
    row_after = table_rows(env, "mutation_receipts", "operation_id = ?", (op_id,))[0]
    assert dict(row_after) == dict(row_before)
    assert row_count(env, "memory_artifact_versions") == versions_before
    replay = apply_call(env, "write", m_write(inv="inv-ns", eff="eff-ns"))
    assert code(replay) == "OK" and ids(replay)  # replay identity unchanged


@pytest.mark.parametrize(
    "operation",
    [pytest.param(o, id=o) for o in ("delete", "edit", "archive", "promote")],
)
def test_t06_reserved_receipt_prefix_rejected(operation: str, tmp_path: Path) -> None:
    from rush.memory.authorization import MemoryPolicyError

    env = make_env(tmp_path)
    snap = snapshot(env)
    if operation == "promote":
        # The MCP promote model has no receipt field: the in-process keys are rejected
        # at the store (`_write_receipt` -> `reserved_receipt_namespace`) before effects.
        result = MemoryTool().run(
            env.root,
            operation="promote",
            subject="domain_knowledge",
            content={"text": "needle promote reserved"},
            source=SRC,
            user_stated=True,
            owner_scope=ALICE,
            receipt_operation_ids={"candidate_create": "v2:x", "promotion": "v2:y"},
            permissions=ExecutionPermissions(cache_write=True),
        )
        assert code(result) == "E_INPUT", dump(raw(result))
        assert "reserved_receipt_namespace" in dump(raw(result))
        only_zero_effects(env, snap, "promote")
        return
    body = _legacy_receipt_requests("v2:forged")[operation]
    over_mcp = mcp_call(env, operation, body, cache_write=True)
    in_process = MemoryTool().run(
        env.root,
        operation=cast(MemoryOperation, operation),
        request=body,
        permissions=ExecutionPermissions(cache_write=True),
    )
    for each in (over_mcp, in_process):
        assert code(each) == "E_INPUT", (operation, dump(raw(each)))
        assert "receipt_operation_id" in dump(raw(each)), dump(raw(each))
    only_zero_effects(env, snap, operation)
    with pytest.raises(MemoryPolicyError):
        assert env.store is not None
        env.store.write_handoff_delivery_receipt(
            "v2:forged", artifact_id="r1", payload={}
        )


# =============================================================================
# R4: event identity (D30)
# =============================================================================


def _ids_of(env: Env, owner: OwnerScope = ALICE) -> tuple[str, str]:
    scope = _auth().resolve_memory_scope(
        project_root=env.root,
        operation="write",
        owner_scope=owner,
        requested_sources=[],
        data_root=env.data_root,
    )
    return scope["project_id"], scope["worktree_id"]


def _event(
    env: Env,
    event_id: str = "e1",
    task_id: str = "t1",
    text: str = "event body",
    **over: Any,
) -> dict[str, Any]:
    project_id, worktree_id = _ids_of(env)
    body: dict[str, Any] = {
        "project_id": project_id,
        "worktree_id": worktree_id,
        "task_id": task_id,
        "event_id": event_id,
        "text": text,
    }
    body.update(over)
    return body


def _drop_event_guards(env: Env) -> None:
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute("DROP TRIGGER IF EXISTS memory_event_identity_immutable")
        conn.execute("DROP INDEX IF EXISTS idx_memory_event_identity")
        conn.commit()


def _set_content(env: Env, artifact_id: str, content: Any) -> None:
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        text = content if isinstance(content, str) else json.dumps(content)
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = ?", (text, artifact_id)
        )
        conn.commit()


def _index_sql(env: Env) -> str | None:
    rows = table_rows(
        env, "sqlite_master", "type = 'index' AND name = 'idx_memory_event_identity'"
    )
    return rows[0]["sql"] if rows else None


def test_t06_event_identity_unique(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    first = apply_call(env, "write", m_write(inv="i1", eff="e1", content=_event(env)))
    assert code(first) == "OK"
    original = ids(first)[0]
    rows = row_count(env)
    same = apply_call(env, "write", m_write(inv="i2", eff="e2", content=_event(env)))
    assert code(same) == "OK" and ids(same) == [original]
    assert row_count(env) == rows

    changed = apply_call(
        env,
        "write",
        m_write(inv="i3", eff="e3", content=_event(env, text="a different payload")),
    )
    assert code(changed) == "E_VERSION" and reason(changed) == "event_digest_conflict"
    assert row_count(env) == rows

    # Wrong project/worktree ids in policy mode, empty or non-string identity fields.
    for label, content in (
        ("project", _event(env, event_id="e9", project_id="other-project")),
        ("worktree", _event(env, event_id="e9", worktree_id="other-worktree")),
        ("task_empty", _event(env, event_id="e9", task_id="")),
        ("event_empty", _event(env, event_id="")),
        ("event_int", _event(env, event_id=5)),  # type: ignore[arg-type]  # deliberate non-str id
        ("project_int", _event(env, event_id="e9", project_id=5)),
    ):
        snap = snapshot(env)
        bad = apply_call(
            env, "write", m_write(inv=f"ib-{label}", eff=f"eb-{label}", content=content)
        )
        assert code(bad) == "E_INPUT", (label, dump(raw(bad)))
        only_zero_effects(env, snap, label)

    # A replayed original that is no longer visible.
    assert (
        code(
            apply_call(
                env,
                "archive",
                m_archive(artifact_id=original, expected_version=1, inv="ia", eff="ea"),
            )
        )
        == "OK"
    )
    gone = apply_call(env, "write", m_write(inv="i4", eff="e4", content=_event(env)))
    assert code(gone) == "E_NOT_VISIBLE"
    assert original not in dump(raw(gone).get("items"))


def test_t06_event_identity_integer_event_id_does_not_collide(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    assert env.store is not None
    put(env.store, "legacy-ev", ALICE, text="pre-T06 row")
    _drop_event_guards(env)
    project_id, worktree_id = _ids_of(env)
    _set_content(
        env,
        "legacy-ev",
        {
            "project_id": project_id,
            "worktree_id": worktree_id,
            "task_id": "t1",
            "event_id": 5,
            "text": "raw sql",
        },
    )
    rows = row_count(env)
    fresh = TypedArtifactStore(env.root)  # constructor recreates trigger and index
    assert fresh is not None
    created = apply_call(
        env, "write", m_write(inv="i5", eff="e5", content=_event(env, event_id="5"))
    )
    assert code(created) == "OK"
    assert row_count(env) == rows + 1


def test_t06_event_index_over_corrupt_content(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    assert env.store is not None
    put(env.store, "corrupt-1", ALICE, text="to be corrupted")
    _drop_event_guards(env)
    _set_content(env, "corrupt-1", "not json at all")
    assert _index_sql(env) is None
    TypedArtifactStore(env.root)
    sql = _index_sql(env)
    assert sql is not None and "json_valid" in sql.lower()
    fresh = apply_call(env, "write", m_write(inv="ic", eff="ec", content=_event(env)))
    assert code(fresh) == "OK"


def _dup_events(env: Env, rows: list[tuple[str, OwnerScope]]) -> None:
    assert env.store is not None
    for artifact_id, owner in rows:
        put(env.store, artifact_id, owner, text=f"dup {artifact_id}")
    _drop_event_guards(env)
    project_id, worktree_id = _ids_of(env)
    for artifact_id, owner in rows:
        _set_content(
            env,
            artifact_id,
            {
                "project_id": project_id,
                "worktree_id": worktree_id,
                "task_id": "t",
                "event_id": f"dup-{owner.id}",
                "text": artifact_id,
            },
        )


def _alice_write_access(env: Env) -> Any:
    from rush.memory.retrieval import MemoryAccess

    access = MemoryAccess.resolve(
        env.root,
        operation="write",
        apply=True,
        owner_scope=ALICE,
        data_root=env.data_root,
    )
    assert access is not None
    return access


def test_t06_upgrade_duplicate_error_access_filtered(tmp_path: Path) -> None:
    from rush.memory.store import MemoryMigrationRequiredError

    env = make_env(tmp_path / "bob-only", seeded=False)
    _dup_events(env, [("bob-d1", BOB), ("bob-d2", BOB)])
    before = sha_file(env.db)
    with pytest.raises(MemoryMigrationRequiredError) as caught:
        TypedArtifactStore.upgrade(
            env.root, cache_write=True, access=_alice_write_access(env)
        )
    err = caught.value
    assert err.reason == "duplicate_event_identity"
    shown = f"{err} {err!r} {dump(list(err.refs))}"
    assert "bob-d1" not in shown and "bob-d2" not in shown and "bob" not in shown
    assert list(err.refs) == []
    assert sha_file(env.db) == before

    own = make_env(tmp_path / "alice", seeded=False)
    _dup_events(
        own,
        [("alice-d1", ALICE), ("alice-d2", ALICE), ("bob-x1", BOB), ("bob-x2", BOB)],
    )
    before = sha_file(own.db)
    with pytest.raises(MemoryMigrationRequiredError) as listed:
        TypedArtifactStore.upgrade(
            own.root, cache_write=True, access=_alice_write_access(own)
        )
    refs = list(listed.value.refs)
    assert sorted(r["artifact_id"] for r in refs) == ["alice-d1", "alice-d2"]
    assert all(set(r) == {"artifact_id", "artifact_version"} for r in refs)
    assert "bob-x" not in f"{listed.value} {dump(refs)}"
    assert sha_file(own.db) == before


def test_t06_event_identity_legacy_and_import(tmp_path: Path) -> None:
    legacy = make_env(tmp_path / "legacy", mode="legacy", seeded=False)
    assert legacy.store is not None
    # Legacy callers (no policy ids): nonempty strings are accepted as given.
    stored = legacy.store.write(
        MemoryArtifact(
            id="leg-1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={
                "project_id": "any-p",
                "worktree_id": "any-w",
                "task_id": "t",
                "event_id": "e",
                "text": "legacy",
            },
            source=SRC,
            created_at=time.time(),
        )
    )
    assert stored.id == "leg-1"
    via_v2 = call(
        legacy,
        "write",
        m_write(
            owner=None,
            inv="il",
            eff="el",
            content={
                "project_id": "p2",
                "worktree_id": "w2",
                "task_id": "t",
                "event_id": "e2",
                "text": "x",
            },
        ),
        perms=PERM_W,
    )
    assert code(via_v2) == "OK", dump(raw(via_v2))

    imp = _import_env(tmp_path / "import")
    foreign = {
        "project_id": "foreign-p",
        "worktree_id": "foreign-w",
        "task_id": "ft",
        "event_id": "fe1",
        "text": "foreign event",
    }
    first = _run_import(
        imp, [_rec("f1", content=foreign)], inv="ii1", eff="ie1", digest="1" * 64
    )
    second = _run_import(
        imp, [_rec("f1", content=foreign)], inv="ii2", eff="ie2", digest="2" * 64
    )
    mapped = [
        m["artifact_id"] for res in (first, second) for m in find_key(res, "mappings")
    ]
    assert len(set(mapped)) == 2
    for artifact_id in mapped:
        stored_row = table_rows(imp, "memory_artifacts", "id = ?", (artifact_id,))[0]
        content = json.loads(stored_row["content"])
        assert stored_row["trust_tier"] == "IMPORTED"
        assert (
            "event_id" not in content and content["origin_event"]["event_id"] == "fe1"
        )
    # No row carries a top-level identity, so the index holds none of them.
    with contextlib.closing(sqlite3.connect(imp.db)) as conn:
        indexed = conn.execute(
            "SELECT COUNT(*) FROM memory_artifacts WHERE json_extract(content, '$.event_id') IS NOT NULL"
        ).fetchone()[0]
    assert indexed == 0


def test_t06_event_identity_scoped_by_owner_no_cross_owner_conflict(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    alice = apply_call(
        env,
        "write",
        m_write(
            owner=ALICE, inv="ia", eff="ea", content=_event(env, text="same event")
        ),
    )
    bob = apply_call(
        env,
        "write",
        m_write(owner=BOB, inv="ib", eff="eb", content=_event(env, text="same event")),
    )
    assert code(alice) == "OK" and code(bob) == "OK"
    assert ids(alice) != ids(bob)
    assert ids(alice)[0] not in dump(raw(bob)) and ids(bob)[0] not in dump(raw(alice))
    rows = [
        r for r in table_rows(env, "memory_artifacts") if '"event_id"' in r["content"]
    ]
    assert len(rows) == 2
    assert {(r["owner_scope_kind"], r["owner_scope_id"]) for r in rows} == {
        ("user", "alice"),
        ("user", "bob"),
    }


def test_t06_event_index_null_owner_backfill(tmp_path: Path) -> None:
    from rush.memory.store import MemoryMigrationRequiredError

    env = make_env(tmp_path, seeded=False)
    assert env.store is not None
    project_id, worktree_id = _ids_of(env)
    event = {
        "project_id": project_id,
        "worktree_id": worktree_id,
        "task_id": "t",
        "event_id": "dupe",
        "text": "x",
    }
    owner = legacy_owner_scope(env.root)
    put(env.store, "legacy-owned", owner, content=dict(event))
    # Identity is owner-scoped (brief 3.10, D30): a second row with the same owner
    # would already conflict at write time, so it starts under another owner and is
    # NULLed after the guards are dropped.
    put(env.store, "null-owned", BOB, content={**event, "text": "y"})
    _drop_event_guards(env)
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET owner_scope_kind = NULL, owner_scope_id = NULL WHERE id = 'null-owned'"
        )
        conn.commit()
    # Constructor: NULL owners exist, so the index stays absent.
    TypedArtifactStore(env.root)
    assert _index_sql(env) is None
    blocked = apply_call(
        env, "write", m_write(inv="in", eff="en", content=_event(env, event_id="fresh"))
    )
    assert code(blocked) == "E_MIGRATION" and reason(blocked) == "upgrade_required"
    # `upgrade` backfills the owner, finds the duplicate and refuses without changes.
    before = sha_file(env.db)
    with pytest.raises(MemoryMigrationRequiredError) as dup:
        TypedArtifactStore.upgrade(
            env.root, cache_write=True, access=_alice_write_access(env)
        )
    assert dup.value.reason == "duplicate_event_identity"
    assert sha_file(env.db) == before


def test_t06_import_foreign_event_identity(tmp_path: Path) -> None:
    imp = _import_env(tmp_path)
    foreign = {
        "project_id": "fp",
        "worktree_id": "fw",
        "task_id": "ft",
        "event_id": "fe",
        "text": "foreign",
    }
    res = _run_import(
        imp,
        [_rec("g1", content=foreign), _rec("g2", content={**foreign, "text": "other"})],
        inv="ij",
        eff="ej",
        digest="3" * 64,
    )
    mapped = find_key(res, "mappings")
    assert len(mapped) == 2
    for m in mapped:
        row = table_rows(imp, "memory_artifacts", "id = ?", (m["artifact_id"],))[0]
        content = json.loads(row["content"])
        assert set(content["origin_event"]) >= {
            "project_id",
            "worktree_id",
            "task_id",
            "event_id",
        }
        for key in ("project_id", "worktree_id", "task_id", "event_id"):
            assert key not in content


# =============================================================================
# R5: history and explain (D31, D32, D38)
# =============================================================================


def _link_rows(env: Env, edges: list[tuple[str, str, str]]) -> None:
    from rush.memory.relations import add_relation

    assert env.store is not None
    for source, kind, target in edges:
        out = add_relation(
            env.store,
            source_id=source,
            source_version=1,
            target_id=target,
            target_version=1,
            kind=kind,
            origin_ref="t06-test",
        )
        assert out["code"] == "OK", (source, kind, target, out)


def _bucket_ids(body: dict[str, Any], bucket: str) -> list[str]:
    return [e["reference"]["artifact_id"] for e in body[bucket]]


def test_t06_history_and_explain(tmp_path: Path) -> None:
    env = make_env(tmp_path / "h")
    assert code(apply_call(env, "edit", m_edit())) == "OK"

    hist = call(env, "history", r_history())
    body = assert_v2_envelope(hist, "history", "OK")
    versions = body["versions"]
    assert [v["reference"]["artifact_version"] for v in versions] == [1, 2]
    assert body["items"] == []
    first, second = versions
    assert json.loads(first["content_utf8"]) == {
        "text": "needle domain_knowledge alice"
    }
    assert json.loads(second["content_utf8"]) == {"text": "needle edited"}
    assert first["reference"]["integrity"] == "verified"
    assert first["freshness"] == "unknown"
    assert first["usable_as_current"] is False
    assert set(first["lifecycle"]) == {"archived", "expired"}
    assert first["lifecycle"] == {"archived": False, "expired": False}
    assert "store_binding" in first
    assert first["reference"]["payload_hash"] != second["reference"]["payload_hash"]

    as_bytes = call(env, "history", r_history(representation="base64"))
    b64 = raw(as_bytes)["versions"][0]
    assert "content_base64" in b64 and "content_utf8" not in b64
    import base64

    assert json.loads(base64.b64decode(b64["content_base64"])) == {
        "text": "needle domain_knowledge alice"
    }

    # Non-UTF-8 version bytes: utf8 is refused with the base64 alternative.
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(
            "UPDATE memory_artifact_versions SET content = ? WHERE artifact_id = 'r1' AND artifact_version = 1",
            (b"\xff\xfe",),
        )
        conn.commit()
    refused = call(env, "history", r_history())
    assert_v2_envelope(refused, "history", "E_INPUT")
    assert reason(refused) == "representation_unavailable"
    assert data(refused)["alternatives"] == ["base64"]
    ok64 = call(env, "history", r_history(representation="base64"))
    assert code(ok64) == "OK"
    assert base64.b64decode(raw(ok64)["versions"][0]["content_base64"]) == b"\xff\xfe"
    assert raw(ok64)["versions"][0]["reference"]["integrity"] == "mismatch"

    # Per-version source filtering: a hidden version is neither listed nor counted.
    src = make_env(tmp_path / "src")
    assert code(apply_call(src, "edit", m_edit())) == "OK"
    with contextlib.closing(sqlite3.connect(src.db)) as conn:
        conn.execute(
            "UPDATE memory_artifact_versions SET source = 'hidden-src' WHERE artifact_id = 'r1' AND artifact_version = 1"
        )
        conn.commit()
    filtered = assert_v2_envelope(call(src, "history", r_history()), "history", "OK")
    assert [v["reference"]["artifact_version"] for v in filtered["versions"]] == [2]
    assert "hidden-src" not in dump(filtered)

    # Archive: active history is `E_NOT_VISIBLE`, historical history lists the versions.
    arc = make_env(tmp_path / "arc")
    assert code(apply_call(arc, "archive", m_archive())) == "OK"
    hidden = call(arc, "history", r_history())
    assert code(hidden) == "E_NOT_VISIBLE"
    shown = assert_v2_envelope(
        call(arc, "history", r_history(archive_mode="historical")), "history", "OK"
    )
    assert all(v["lifecycle"]["archived"] is True for v in shown["versions"])

    # Budget: one version larger than the cap -> E_BUDGET with the required sizes.
    big = make_env(tmp_path / "big", seeded=False)
    assert big.store is not None
    put(big.store, "r1", ALICE, content={"text": "needle " + "x" * 60000})
    over = call(big, "history", r_history(max_bytes=4096))
    assert_v2_envelope(over, "history", "E_BUDGET")
    assert set(data(over)["required"]) == {"max_bytes", "max_tokens"}

    # Explain: one hop, sorted, deduped D38 buckets with `via`.
    gx = make_env(tmp_path / "x")
    _link_rows(
        gx,
        [
            ("r1", "depends_on", "a-skill_pattern"),
            ("r1", "validated_by", "r2"),
            ("r1", "contradicts", "a-preference"),
            ("a-active_context", "contradicts", "r1"),
            ("a-architectural_decision", "supersedes", "r1"),
            ("a-episodic", "depends_on", "r1"),
            ("r1", "implements", "a-skill_pattern"),
        ],
    )
    ex = assert_v2_envelope(call(gx, "explain", r_explain()), "explain", "OK")
    assert _bucket_ids(ex, "supporting") == ["a-skill_pattern", "r2"]
    skill = next(
        e
        for e in ex["supporting"]
        if e["reference"]["artifact_id"] == "a-skill_pattern"
    )
    assert [v["kind"] for v in skill["via"]] == ["depends_on", "implements"]
    assert all(set(v) == {"kind", "direction"} for v in skill["via"])
    assert skill["via"] == sorted(
        skill["via"], key=lambda v: (v["kind"], v["direction"])
    )
    by_id = {e["reference"]["artifact_id"]: e for e in ex["contrary"]}
    assert (
        by_id["a-active_context"]["via"][0]["direction"]
        != by_id["a-preference"]["via"][0]["direction"]
    ), "an incoming and an outgoing contradiction carry different directions"
    assert _bucket_ids(ex, "contrary") == [
        "a-active_context",
        "a-architectural_decision",
        "a-preference",
    ]
    assert set(_bucket_ids(ex, "attempted")) == {"a-episodic", "r2"}
    assert set(_bucket_ids(ex, "affected")) == {
        "a-active_context",
        "a-architectural_decision",
        "a-episodic",
        "a-preference",
        "a-skill_pattern",
        "r2",
    }
    for bucket in ("supporting", "contrary", "attempted", "affected"):
        keys = [
            (e["reference"]["artifact_id"], e["reference"]["artifact_version"])
            for e in ex[bucket]
        ]
        assert keys == sorted(set(keys)), bucket
    assert "no_recorded_rationale" not in ex["unknowns"]
    assert not any(b in dump(ex) for b in _bob_ids())

    # Query mode: matched rows, `targets`, no generated text.
    q = assert_v2_envelope(
        call(
            gx,
            "explain",
            r_explain(
                artifact_id=None,
                query="needle domain_knowledge",
                subjects=["domain_knowledge"],
            ),
        ),
        "explain",
        "OK",
    )
    assert [
        t["artifact_id"] if "artifact_id" in t else t["reference"]["artifact_id"]
        for t in q["targets"]
    ] == ["r1"]
    none = assert_v2_envelope(
        call(gx, "explain", r_explain(artifact_id=None, query="zzzznomatchzzzz")),
        "explain",
        "OK",
    )
    assert "no_matches" in none["unknowns"] and none["targets"] == []
    assert set(q) <= V2_KEYS | V2_NAMED


def test_t06_explain_affected_requires_edge(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    shared: dict[str, Any] = {"task_id": "task-shared"}
    rows: dict[str, str] = {}
    for name in ("target", "linked", "unlinked"):
        res = apply_call(
            env,
            "write",
            m_write(inv=f"i-{name}", eff=f"e-{name}", text=f"needle {name}"),
            **shared,
        )
        assert code(res) == "OK", dump(raw(res))
        rows[name] = ids(res)[0]
    from rush.memory.relations import add_relation

    assert env.store is not None
    assert (
        add_relation(
            env.store,
            source_id=rows["linked"],
            source_version=1,
            target_id=rows["target"],
            target_version=1,
            kind="depends_on",
        )["code"]
        == "OK"
    )
    # An edge from an invisible (Bob-owned) row adds nothing to any bucket.
    assert (
        add_relation(
            env.store,
            source_id=BOB_IDS["domain_knowledge"],
            source_version=1,
            target_id=rows["target"],
            target_version=1,
            kind="contradicts",
        )["code"]
        == "OK"
    )
    ex = assert_v2_envelope(
        call(env, "explain", r_explain(artifact_id=rows["target"]), **shared),
        "explain",
        "OK",
    )
    assert _bucket_ids(ex, "affected") == [rows["linked"]]
    assert rows["unlinked"] not in dump(ex)
    assert BOB_IDS["domain_knowledge"] not in dump(ex)
    assert ex["contrary"] == []


def test_t06_history_version_context(tmp_path: Path) -> None:
    env = make_env(tmp_path / "ctx")
    assert (
        code(
            apply_call(
                env,
                "write",
                m_write(inv="i1", eff="e1", text="needle first"),
                task_id="task-a",
            )
        )
        == "OK"
    )
    created = [
        r["id"]
        for r in table_rows(env, "memory_artifacts")
        if "needle first" in r["content"]
    ]
    assert len(created) == 1
    rid = created[0]
    assert (
        code(
            apply_call(
                env,
                "edit",
                m_edit(artifact_id=rid, inv="i2", eff="e2", text="needle second"),
                task_id="task-b",
            )
        )
        == "OK"
    )
    project_id, worktree_id = _ids_of(env)
    versions = assert_v2_envelope(
        call(env, "history", r_history(artifact_id=rid), task_id="task-b"),
        "history",
        "OK",
    )["versions"]
    assert [v["task_binding"] for v in versions] == [
        [project_id, worktree_id, "task-a"],
        [project_id, worktree_id, "task-b"],
    ]
    assert all("version_context_unbound" not in v["reason_codes"] for v in versions)

    # A pre-T05 version (no recorded binding) reports `version_context_unbound` and
    # never inherits the current row's context.
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(
            "UPDATE memory_artifact_versions SET binding_recorded = NULL WHERE artifact_id = ? AND artifact_version = 1",
            (rid,),
        )
        conn.commit()
    unbound = raw(call(env, "history", r_history(artifact_id=rid), task_id="task-b"))[
        "versions"
    ]
    assert "version_context_unbound" in unbound[0]["reason_codes"]
    assert unbound[0]["task_binding"] is None and unbound[0]["applicability"] is None
    assert unbound[1]["task_binding"] is not None

    # Correction, archive/restore, promotion and expiry each keep a coherent history.
    cor = make_env(tmp_path / "cor")
    assert (
        code(
            apply_call(
                cor,
                "edit",
                m_edit(
                    inv="ic", eff="ec", correction={"kind": "correct", "reason": "fix"}
                ),
            )
        )
        == "OK"
    )
    assert (
        code(
            apply_call(
                cor,
                "archive",
                m_archive(
                    expected_version=current_version(cor, "r1") or 0, inv="ia", eff="ea"
                ),
            )
        )
        == "OK"
    )
    assert (
        code(
            apply_call(
                cor,
                "archive",
                m_archive(
                    expected_version=current_version(cor, "r1") or 0,
                    archived=False,
                    inv="ir",
                    eff="er",
                ),
            )
        )
        == "OK"
    )
    full = raw(call(cor, "history", r_history()))["versions"]
    assert [v["reference"]["artifact_version"] for v in full] == list(
        range(1, len(full) + 1)
    )
    assert len(full) >= 4

    pro = make_env(tmp_path / "pro")
    existing = {r["id"] for r in table_rows(pro, "memory_artifacts")}
    assert code(apply_call(pro, "promote", m_promote())) == "OK"
    cand = next(iter({r["id"] for r in table_rows(pro, "memory_artifacts")} - existing))
    chain = raw(call(pro, "history", r_history(artifact_id=cand)))["versions"]
    assert [v["reference"]["artifact_version"] for v in chain] == [1, 2]
    assert [v["reference"]["trust_tier"] for v in chain] == ["DERIVED", "STATED"]

    exp = make_env(tmp_path / "exp")
    with contextlib.closing(sqlite3.connect(exp.db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET expires_at = ?, expired_at = ?, expired_by = 'test' WHERE id = 'r1'",
            (time.time() - 100, time.time() - 50),
        )
        conn.commit()
    assert code(call(exp, "history", r_history())) == "E_NOT_VISIBLE"
    expired = raw(call(exp, "history", r_history(archive_mode="historical")))[
        "versions"
    ]
    assert expired[0]["lifecycle"]["expired"] is True


# =============================================================================
# R6: error mapping (§3.3)
# =============================================================================


def _force(monkeypatch: pytest.MonkeyPatch, name: str, exc: BaseException) -> None:
    def raiser(*args: Any, **kwargs: Any) -> Any:
        raise exc

    monkeypatch.setattr(TypedArtifactStore, name, raiser)


def _expired_grant_env(tmp_path: Path) -> Env:
    env = make_env(tmp_path, bob=False)
    soon = time.time() + 1.0
    _auth().grant_memory_scope(
        project_root=env.root,
        owner_scope=ALICE,
        approved_sources=[SRC],
        allowed_operations=list(GRANT_OPS),
        expected_policy_revision=_revision(env.data_root),
        consent=True,
        expires_at=soon,
        data_root=env.data_root,
    )
    time.sleep(1.2)
    return env


def _error_cases() -> list[Any]:
    cases: list[Any] = []

    def add(name: str, expected: str, **kw: Any) -> None:
        cases.append(pytest.param(name, expected, kw, id=name))

    add("owner_required", "E_INPUT", field="owner_scope", reason="owner_required")
    add("owner_not_granted", "E_OWNER", reason="owner_not_granted")
    add("source_not_granted", "E_SCOPE", reason="source_not_granted")
    for reason_name in (
        "policy_missing",
        "policy_invalid",
        "no_grant",
        "revoked",
        "expired",
        "operation_not_granted",
        "project_missing",
        "overlay_storage_root",
    ):
        add(f"permission-{reason_name}", "E_PERMISSION", reason=reason_name)
    add("memory_policy_error", "E_INPUT", reason="x_reason")
    add("migration_required", "E_MIGRATION", reason=None)
    add("store_corrupt", "E_STORE_CORRUPT", reason=None)
    add("store_busy", "E_STORE_BUSY", reason=None)
    add("owner_scope_error", "E_OWNER", reason=None)
    add("memory_scope_error", "E_SCOPE", reason=None)
    add("version_conflict", "E_VERSION", reason=None)
    add("key_error", "E_NOT_VISIBLE", reason=None)
    add("recheck_changed", "E_RESTART", reason="access_changed")
    return cases


@pytest.mark.parametrize(("name", "expected", "want"), _error_cases())
def test_t06_error_mapping(
    name: str,
    expected: str,
    want: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rush.memory.authorization import MemoryPolicyError
    from rush.memory.store import (
        MemoryScopeError,
        MemoryStoreUnreadableError,
        OwnerScopeError,
        VersionConflictError,
    )

    env = make_env(tmp_path)
    operation, request, perms = "list", r_list(), PERM_NONE
    if name == "owner_required":
        request = r_list(owner=None)
    elif name == "owner_not_granted":
        request = r_list(owner=OwnerScope("user", "carol"))
    elif name == "source_not_granted":
        request = r_list(sources=["not-granted"])
    elif name == "permission-policy_missing":
        _auth().policy_path(data_root=env.data_root).unlink()
    elif name == "permission-policy_invalid":
        _auth().policy_path(data_root=env.data_root).write_bytes(b"{")
    elif name == "permission-no_grant":
        # A marked project with no grant of its own while the policy holds others.
        from rush.memory.authorization import REGISTRATION_MARKER

        other = tmp_path / "marked-without-grant"
        (other / ".rush").mkdir(parents=True)
        (other / ".rush" / REGISTRATION_MARKER).write_text("", encoding="utf-8")
        env = dataclasses.replace(env, root=other.resolve())
    elif name == "permission-revoked":
        revoke(env, ALICE)
    elif name == "permission-expired":
        env = _expired_grant_env(tmp_path / "expired")
    elif name == "permission-operation_not_granted":
        env = make_env(tmp_path / "nolist", ops=("ask", "expand", "write"))
    elif name == "permission-project_missing":
        import shutil

        shutil.rmtree(env.root)
    elif name == "permission-overlay_storage_root":
        env = dataclasses.replace(env, root=env.data_root / "user")
        (env.data_root / "user").mkdir(parents=True, exist_ok=True)
    elif name in {
        "memory_policy_error",
        "owner_scope_error",
        "memory_scope_error",
        "version_conflict",
        "key_error",
        "recheck_changed",
    }:
        operation, request, perms = "edit", m_edit(), PERM_W
        if name == "memory_policy_error":
            _force(monkeypatch, "edit", MemoryPolicyError("E_INPUT", "x_reason"))
        elif name == "owner_scope_error":
            _force(monkeypatch, "edit", OwnerScopeError("owner mismatch"))
        elif name == "memory_scope_error":
            _force(monkeypatch, "edit", MemoryScopeError("scope mismatch"))
        elif name == "version_conflict":
            _force(monkeypatch, "edit", VersionConflictError("stale", code="E_VERSION"))
        elif name == "key_error":
            _force(monkeypatch, "edit", KeyError("r1"))
        else:
            original = TypedArtifactStore.edit

            def changing(self: Any, *args: Any, **kwargs: Any) -> Any:
                grant(
                    env, env.data_root, ALICE, sources=(SRC, "s2")
                )  # new revision mid-call
                return original(self, *args, **kwargs)

            monkeypatch.setattr(TypedArtifactStore, "edit", changing)
    elif name == "migration_required":
        with contextlib.closing(sqlite3.connect(env.db)) as conn:
            for table in ("memory_artifacts", "memory_artifact_versions"):
                for column in ("payload_hash", "payload_hash_origin"):
                    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()
    elif name == "store_corrupt":
        env.db.write_bytes(b"this is not a sqlite database" * 64)
    elif name == "store_busy":
        monkeypatch.setattr(
            TypedArtifactStore,
            "open_readonly_view",
            classmethod(
                lambda cls, root: (_ for _ in ()).throw(
                    MemoryStoreUnreadableError("busy", code="E_STORE_BUSY")
                )
            ),
        )
    snap = snapshot(env) if env.root.exists() else None
    result = call(env, operation, request, perms=perms)
    body = assert_v2_envelope(result, operation, expected)
    assert body["items"] == []
    if want.get("reason") is not None:
        assert reason(result) == want["reason"], dump(body)
    if "field" in want:
        assert data(result).get("field") == want["field"]
    if name == "migration_required":
        assert reason(result) == "migration_required", dump(body)
    if name.startswith("store_"):
        assert "message" in data(result)
    if name in {
        "memory_policy_error",
        "owner_scope_error",
        "memory_scope_error",
        "version_conflict",
        "key_error",
    }:
        assert "message" in data(result)
        assert current_version(env, "r1") == 1
    if snap is not None and name not in {
        "memory_policy_error",
        "owner_scope_error",
        "memory_scope_error",
        "version_conflict",
        "key_error",
        "recheck_changed",
    }:
        assert snapshot(env) == snap, name
    # Migration errors never carry hidden refs; an `E_MIGRATION` body has no Bob id.
    assert not any(b in dump(body) for b in _bob_ids())
    # The same mapping reaches MCP unchanged for a pure read.
    if operation == "list" and name not in {
        "permission-project_missing",
        "permission-overlay_storage_root",
        "store_busy",
    }:
        assert dump(raw(mcp_call(env, operation, request))) == dump(raw(result))


def test_t06_migration_required_error_carries_reason_and_refs() -> None:
    from rush.memory.store import MemoryMigrationRequiredError

    plain = MemoryMigrationRequiredError("needs upgrade")
    assert plain.reason is None and tuple(plain.refs) == ()
    rich = MemoryMigrationRequiredError(
        "dup",
        reason="duplicate_event_identity",
        refs=({"artifact_id": "a", "artifact_version": 1},),
    )
    assert rich.reason == "duplicate_event_identity"
    assert rich.refs == ({"artifact_id": "a", "artifact_version": 1},)


# =============================================================================
# R7: restricted bridge (D22)
# =============================================================================

DENIAL_DATA = {"message": "Unknown or revoked handoff session."}
ADMIN_OPS = (
    "edit",
    "history",
    "explain",
    "write",
    "archive",
    "delete",
    "promote",
    "maintain",
    "link",
    "ask",
    "list",
    "recall",
)


def _bridge(
    tmp_path: Path,
    *,
    selected: tuple[str, ...] = ("a1",),
    edges: bool = True,
    name: str = "bridge",
) -> tuple[Path, TypedArtifactStore, Any, str]:
    from rush.memory.handoff import prepare_handoff
    from rush.memory.relations import add_relation

    root = tmp_path / name
    root.mkdir()
    store = TypedArtifactStore(root)
    for rid in ("a1", "b1", "c1"):
        put(store, rid, None, text=f"needle {rid}")
    if edges:
        for src, dst in (("a1", "b1"), ("b1", "c1")):
            assert (
                add_relation(
                    store,
                    source_id=src,
                    source_version=1,
                    target_id=dst,
                    target_version=1,
                    kind="depends_on",
                )["code"]
                == "OK"
            )
    session, capability, _delta = prepare_handoff(
        store,
        root=root,
        audience="codex_cli",
        granted_ids=list(selected),
        session_allowlist=[SRC],
    )
    return root, store, session, capability


def _set_session_ids(db: Path, session_id: str, granted: list[str]) -> None:
    """Empty (or replace) a stored handoff session's selection behind the store's back."""
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_handoff_sessions SET granted_ids = ? WHERE session_id = ?",
            (json.dumps(granted), session_id),
        )
        conn.commit()


def _handler(root: Path, session_id: str, capability: str) -> Any:
    from rush.mcp_support.tool_registry import build_memory_bridge_handler

    return build_memory_bridge_handler(
        root=root, session_id=session_id, capability=capability
    )


def _bridge_cases() -> list[Any]:
    cases = [
        pytest.param(
            "admin_op_denied_before_store", "edit", id="admin_op_denied_before_store"
        )
    ]
    cases += [
        pytest.param(
            f"admin_op_denied_before_store-{op}",
            op,
            id=f"admin_op_denied_before_store-{op}",
        )
        for op in ADMIN_OPS
        if op != "edit"
    ]
    cases += [
        pytest.param(
            f"schema_version_denied_before_store-{op}",
            op,
            id=f"schema_version_denied_before_store-{op}",
        )
        for op in ("receive", "expand", "related", "resume")
    ]
    cases += [
        pytest.param("selected_ids_only", "", id="selected_ids_only"),
        pytest.param(
            "empty_selection_grants_nothing", "", id="empty_selection_grants_nothing"
        ),
        pytest.param(
            "related_equals_graph_without_unselected_edges",
            "",
            id="related_equals_graph_without_unselected_edges",
        ),
        pytest.param(
            "no_writable_store_for_reads", "", id="no_writable_store_for_reads"
        ),
        pytest.param(
            "invalid_capability_missing_store_creates_no_db",
            "",
            id="invalid_capability_missing_store_creates_no_db",
        ),
    ]
    return cases


@pytest.mark.parametrize(("case", "operation"), _bridge_cases())
def test_t06_restricted_bridge_readonly(
    case: str, operation: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if case.startswith("admin_op_denied_before_store"):
        bare = tmp_path / "bare"
        bare.mkdir()
        handler = _handler(bare, "s" * 32, "cap")
        request = (
            {"id": "a1", "version": 1, "schema_version": 2, "artifact_id": "a1"}
            if operation in {"history", "explain"}
            else {"id": "a1", "version": 1}
        )
        out = handler(operation, request)
        assert out["code"] == "E_PERMISSION"
        assert (
            "receive/expand/related/resume" in dump(out)
            or "('receive', 'expand', 'related', 'resume')" in dump(out)
            or "restricted" in dump(out).lower()
        )
        assert list(bare.iterdir()) == []
        assert not (bare / ".rush").exists()
        # A real session gets the same denial and no store byte moves.
        root, _store, session, capability = _bridge(tmp_path, name="real")
        before = digest_tree(root)
        real = _handler(root, session.session_id, capability)(operation, request)
        assert real["code"] == "E_PERMISSION" and dump(real) == dump(out)
        assert digest_tree(root) == before
        return
    if case.startswith("schema_version_denied_before_store"):
        opened: list[Any] = []
        original = TypedArtifactStore.open_readonly_view.__func__  # type: ignore[attr-defined]

        def spy(cls: Any, root_arg: Path) -> Any:
            opened.append(root_arg)
            return original(cls, root_arg)

        monkeypatch.setattr(TypedArtifactStore, "open_readonly_view", classmethod(spy))
        bare = tmp_path / "bare"
        bare.mkdir()
        request = {"schema_version": 2, "artifact_id": "a1", "artifact_version": 1}
        out = _handler(bare, "s" * 32, "cap")(operation, request)
        assert out["code"] == "E_INPUT" and out["data"].get("field") == "schema_version"
        assert list(bare.iterdir()) == [] and opened == []
        root, _store, session, capability = _bridge(tmp_path, name="real")
        before = digest_tree(root)
        opened.clear()
        real = _handler(root, session.session_id, capability)(operation, request)
        assert (
            real["code"] == "E_INPUT" and real["data"].get("field") == "schema_version"
        )
        assert opened == [] and digest_tree(root) == before
        return
    if case == "invalid_capability_missing_store_creates_no_db":
        bare = tmp_path / "bare"
        bare.mkdir()
        for op, req in (
            ("receive", {}),
            ("expand", {"id": "a1", "version": 1}),
            ("related", {"id": "a1", "version": 1}),
            ("resume", {"task": "t", "conditions": {}}),
        ):
            out = _handler(bare, "0" * 32, "wrong")(op, req)
            assert out["code"] == "E_PERMISSION" and out["data"] == DENIAL_DATA
        assert list(bare.iterdir()) == []
        return
    if case == "selected_ids_only":
        root, _store, session, capability = _bridge(tmp_path)
        handler = _handler(root, session.session_id, capability)
        before = digest_tree(root)
        assert handler("expand", {"id": "a1", "version": 1})["code"] == "OK"
        denied = handler("expand", {"id": "b1", "version": 1})
        assert denied["code"] == "E_PERMISSION"
        assert "needle b1" not in dump(denied)
        related = handler("related", {"id": "a1", "version": 1, "depth": 2})
        assert "b1" not in dump(related) and "c1" not in dump(related)
        missing = handler("related", {"id": "zz-none", "version": 1})
        unselected_seed = handler("related", {"id": "b1", "version": 1})
        assert unselected_seed["code"] == missing["code"]
        assert "needle b1" not in dump(unselected_seed)
        for op, req in (("resume", {"task": "t", "conditions": {}}), ("receive", {})):
            out = handler(op, req)
            assert out["code"] == "OK", (op, dump(out))
            assert "b1" not in dump(out) and "c1" not in dump(out), op
            assert "needle b1" not in dump(out) and "needle c1" not in dump(out)
        assert digest_tree(root) == before
        return
    if case == "empty_selection_grants_nothing":
        root, store, session, capability = _bridge(tmp_path)
        _set_session_ids(store.db_path, session.session_id, [])
        handler = _handler(root, session.session_id, capability)
        assert handler("expand", {"id": "a1", "version": 1})["code"] == "E_PERMISSION"
        for op, req in (
            ("resume", {"task": "t", "conditions": {}}),
            ("receive", {}),
            ("related", {"id": "a1", "version": 1}),
        ):
            out = handler(op, req)
            assert "needle a1" not in dump(out) and "needle b1" not in dump(out), op
        return
    if case == "related_equals_graph_without_unselected_edges":
        with_edges, _s, sess_a, cap_a = _bridge(tmp_path, edges=True, name="with")
        without, _s2, sess_b, cap_b = _bridge(tmp_path, edges=False, name="without")
        a = _handler(with_edges, sess_a.session_id, cap_a)(
            "related", {"id": "a1", "version": 1, "depth": 2, "max_nodes": 32}
        )
        b = _handler(without, sess_b.session_id, cap_b)(
            "related", {"id": "a1", "version": 1, "depth": 2, "max_nodes": 32}
        )
        assert a["code"] == b["code"]
        assert dump(a["data"]) == dump(b["data"])
        return
    assert case == "no_writable_store_for_reads"
    root, _store, session, capability = _bridge(tmp_path)
    constructed: list[Any] = []
    real_init = TypedArtifactStore.__init__

    def counting(self: Any, *args: Any, **kwargs: Any) -> None:
        constructed.append(args)
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(TypedArtifactStore, "__init__", counting)
    handler = _handler(root, session.session_id, capability)
    for op, req in (
        ("expand", {"id": "a1", "version": 1}),
        ("related", {"id": "a1", "version": 1}),
        ("resume", {"task": "t", "conditions": {}}),
    ):
        assert handler(op, req)["code"] in {"OK", "E_NOT_VISIBLE"}
    assert constructed == [], "a read through the bridge constructed a writable store"


# =============================================================================
# R8: one MemoryTool for CLI, full MCP (in-process and stdio) and direct calls
# =============================================================================

_VOLATILE = frozenset(
    {"created_at", "updated_at", "expires_at", "timestamp", "duration_ms", "elapsed_ms"}
)


def _normalize(env: Env, value: Any) -> str:
    def scrub(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: scrub(v) for k, v in obj.items() if k not in _VOLATILE}
        if isinstance(obj, list):
            return [scrub(v) for v in obj]
        return obj

    project_id, worktree_id = _ids_of(env) if env.mode == "policy" else ("", "")
    text = json.dumps(scrub(value), sort_keys=True, default=str)
    for needle, token in (
        (str(env.root), "<root>"),
        (project_id, "<pid>"),
        (worktree_id, "<wid>"),
    ):
        if needle:
            text = text.replace(needle, token)
    return text


def test_t06_cli_mcp_parity(tmp_path: Path) -> None:
    solo = make_env(tmp_path / "solo", bob=False)
    # history / explain leaves: positional CLI vs in-process vs full MCP vs real stdio.
    code_h, cli_h = cli_json(solo.root, ["memory", "history", "r1", "--json"])
    direct_h = call(solo, "history", v2(artifact_id="r1"))
    over_mcp = mcp_call(solo, "history", v2(artifact_id="r1"))
    over_stdio = stdio_call(solo, "history", v2(artifact_id="r1"))
    over_server = mcp_server_call(solo, "history", v2(artifact_id="r1"))
    assert code_h == 0 and cli_h["raw"]["code"] == "OK"
    expected = _normalize(solo, raw(direct_h))
    for other in (cli_h, over_mcp, over_stdio, over_server):
        assert _normalize(solo, raw(other)) == expected

    _c, cli_hh = cli_json(
        solo.root, ["memory", "history", "r1", "--historical", "--json"]
    )
    assert _normalize(solo, raw(cli_hh)) == _normalize(
        solo,
        raw(call(solo, "history", v2(artifact_id="r1", archive_mode="historical"))),
    )

    _c, cli_e = cli_json(solo.root, ["memory", "explain", "r1", "--json"])
    assert _normalize(solo, raw(cli_e)) == _normalize(
        solo, raw(call(solo, "explain", v2(artifact_id="r1")))
    )
    _c, cli_q = cli_json(
        solo.root, ["memory", "explain", "--query", "needle", "--json"]
    )
    assert _normalize(solo, raw(cli_q)) == _normalize(
        solo, raw(call(solo, "explain", v2(query="needle")))
    )
    assert _normalize(
        solo, raw(stdio_call(solo, "explain", v2(query="needle")))
    ) == _normalize(solo, raw(cli_q))

    # Exactly one of the argument or `--query`.
    for argv in (
        ["memory", "explain", "r1", "--query", "x", "--json"],
        ["memory", "explain", "--json"],
    ):
        status, _out = cli_json(solo.root, argv)
        assert status == 2, argv
    status, _out = cli_json(solo.root, ["memory", "history"])
    assert status == 2

    # Task context forwards as the top-level `task_id` only when given.
    _c, cli_t = cli_json(
        solo.root, ["memory", "history", "r1", "--task-id", "task-1", "--json"]
    )
    assert _normalize(solo, raw(cli_t)) == _normalize(
        solo, raw(call(solo, "history", v2(artifact_id="r1"), task_id="task-1"))
    )

    # Equal error bodies for one invalid v2 request across transports.
    bad = v2(artifact_id="r1", bogus=True)
    assert (
        _normalize(solo, raw(call(solo, "history", bad)))
        == _normalize(solo, raw(mcp_call(solo, "history", bad)))
        == _normalize(solo, raw(stdio_call(solo, "history", bad)))
    )

    # `--input` leaves: read operations against the same store.
    for cli_name, operation, request in (
        ("expand", "expand", v2(artifact_id="r1", artifact_version=1)),
        ("related", "related", v2(artifact_id="r1", artifact_version=1, depth=1)),
    ):
        path = write_input(solo.root, f"{cli_name}-in", request)
        _c, via_cli = cli_json(
            solo.root, ["memory", cli_name, "--input", str(path), "--json"]
        )
        assert _normalize(solo, raw(via_cli)) == _normalize(
            solo, raw(call(solo, operation, request))
        ), cli_name

    # `--input` mutations: identical fresh stores per transport.
    for cli_name, operation, request in (
        ("edit", "edit", m_edit(owner=None)),
        ("archive", "archive", m_archive(owner=None)),
        ("delete", "delete", m_delete(owner=None)),
        ("link", "link", m_link(owner=None)),
    ):
        a = make_env(tmp_path / f"cli-{cli_name}", bob=False)
        b = make_env(tmp_path / f"mcp-{cli_name}", bob=False)
        path = write_input(a.root, f"{cli_name}-mut", request)
        _c, via_cli = cli_json(
            a.root,
            ["memory", cli_name, "--input", str(path), "--allow-cache-write", "--json"],
        )
        via_mcp = mcp_call(b, operation, request, cache_write=True)
        assert raw(via_cli)["code"] == "OK", (cli_name, dump(raw(via_cli)))
        assert _normalize(a, raw(via_cli)) == _normalize(b, raw(via_mcp)), cli_name
        assert len(v2_receipts(a)) == len(v2_receipts(b)) == 1


# =============================================================================
# R9: cursor binds filters and archive mode
# =============================================================================


def test_t06_cursor_binds_filters_and_archive_mode(tmp_path: Path) -> None:
    env = make_env(tmp_path, ops=GRANT_OPS)
    env.grants["alice"] = grant(env, env.data_root, ALICE, sources=(SRC, "s2"))
    assert env.store is not None
    put(env.store, "s2-row", ALICE, source="s2", text="needle s2")

    def page(**extra: Any) -> Any:
        return call(env, "list", r_list(limit=3, **extra))

    first = page()
    body = assert_v2_envelope(first, "list", "OK")
    assert len(body["items"]) == 3 and body["complete"] is False and body["next_cursor"]
    seen = ids(first)
    cursor = body["next_cursor"]
    while cursor:
        nxt = page(cursor=cursor)
        nbody = assert_v2_envelope(nxt, "list", "OK")
        seen += ids(nxt)
        cursor = nbody["next_cursor"]
    assert nbody["complete"] is True
    assert len(seen) == len(set(seen)) == 8
    assert seen == sorted(seen)

    # Changing any bound field between pages is `E_RESTART` with no items.
    changes: dict[str, dict[str, Any]] = {
        "subjects": {"subjects": ["failure"]},
        "trust_tiers": {"trust_tiers": ["DERIVED"]},
        "freshness": {"freshness": ["current", "unknown"]},
        "archive_mode": {"archive_mode": "historical"},
        "sources": {"sources": [SRC]},
        "query": {"query": "needle"},
    }
    for label, extra in changes.items():
        issued = raw(page())["next_cursor"]
        moved = call(env, "list", r_list(limit=3, cursor=issued, **extra))
        assert_v2_envelope(moved, "list", "E_RESTART")
        assert raw(moved)["items"] == [], label
    issued = raw(page())["next_cursor"]
    other_owner = call(env, "list", r_list(owner=BOB, limit=3, cursor=issued))
    assert code(other_owner) == "E_RESTART" and not ids(other_owner)

    # A cursor issued for filter set X works with X again, and an unrelated project's
    # grant between pages does not invalidate it (T02 binding excludes policy_revision).
    issued = raw(page(trust_tiers=["DERIVED"]))["next_cursor"]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    register_project(elsewhere, data_root=env.data_root)
    grant(env, env.data_root, ALICE, root=elsewhere.resolve())
    resumed = call(env, "list", r_list(limit=3, trust_tiers=["DERIVED"], cursor=issued))
    assert code(resumed) == "OK" and not set(ids(resumed)) & set(seen[:3])

    # Hybrid retrieval never accepts a cursor.
    hybrid = call(
        env,
        "list",
        r_list(limit=3, retrieval="hybrid", cursor=issued),
        perms=ExecutionPermissions(network=True),
    )
    assert code(hybrid) == "E_INPUT"

    # A v1 compact cursor is untouched by T06: it still pages.
    v1 = MemoryTool().run(
        env.root,
        operation="list",
        subject="domain_knowledge",
        query="needle",
        owner_scope=ALICE,
        request={"view": "compact", "limit": 1},
    )
    assert raw(v1)["code"] == "OK"
    v1_cursor = raw(v1)["data"]["next_cursor"]
    assert v1_cursor
    again = MemoryTool().run(
        env.root,
        operation="list",
        subject="domain_knowledge",
        query="needle",
        owner_scope=ALICE,
        request={"view": "compact", "limit": 1, "cursor": v1_cursor},
    )
    assert raw(again)["code"] == "OK"


# =============================================================================
# R10 / R15: import seam (D18)
# =============================================================================

IMPORT_SOURCE = "capsule:import"
CAPSULE = "c" * 64


def _import_env(
    tmp_path: Path, *, mode: str = "policy", store: bool = True, name: str = "import"
) -> Env:
    """A project whose Alice grant allows the `capsule:import` writer source."""
    data_root = default_data_root()
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    _git_init(root)
    root = root.resolve()
    env = Env(root=root, data_root=data_root, store=None, mode=mode)
    if mode == "policy":
        register_project(root, data_root=data_root)
        env.grants["alice"] = grant(
            env, data_root, ALICE, sources=(SRC, IMPORT_SOURCE), ops=GRANT_OPS
        )
        env.grants["bob"] = grant(
            env, data_root, BOB, sources=(SRC, IMPORT_SOURCE), ops=GRANT_OPS
        )
    if store:
        env.store = TypedArtifactStore(root)
    return env


def _write_access(
    env: Env, owner: OwnerScope = ALICE, sources: tuple[str, ...] = (IMPORT_SOURCE,)
) -> Any:
    from rush.memory.retrieval import MemoryAccess

    if env.mode == "legacy":
        return MemoryAccess.legacy(
            env.root,
            list(sources),
            owner_scope=legacy_owner_scope(env.root),
            operation="write",
            data_root=env.data_root,
        )
    access = MemoryAccess.resolve(
        env.root,
        operation="write",
        apply=True,
        owner_scope=owner,
        requested_sources=sources,
        data_root=env.data_root,
    )
    assert access is not None
    return access


def _rec(
    fid: str,
    *,
    subject: str = "domain_knowledge",
    content: dict[str, Any] | None = None,
    family: str = "memory",
    source: str = "foreign-src",
    owner: dict[str, str] | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
) -> dict[str, Any]:
    return {
        "foreign_origin_id": fid,
        "family": family,
        "subject": subject,
        "content": content if content is not None else {"text": f"imported {fid}"},
        "foreign_source": source,
        "foreign_owner": owner,
        "foreign_symbol_ref": symbol_ref,
        "foreign_content_hash": content_hash,
    }


def _constraint(
    fid: str, constraint_id: str, text: str = "constraint text"
) -> dict[str, Any]:
    return _rec(
        fid,
        content={"kind": "constraint", "constraint_id": constraint_id, "text": text},
    )


def _preview(
    env: Env,
    records: list[dict[str, Any]],
    *,
    constraints: tuple[str, ...] = (),
    mapping_id: str | None = None,
    access: Any = None,
    capsule: str = CAPSULE,
) -> dict[str, Any]:
    return TypedArtifactStore.preview_import_records(
        records=tuple(records),
        capsule_digest=capsule,
        confirm_constraint_ids=tuple(constraints),
        mapping_id=mapping_id,
        access=access if access is not None else _write_access(env),
    )


def _apply(
    env: Env,
    records: list[dict[str, Any]],
    preview: dict[str, Any],
    *,
    inv: str,
    eff: str,
    digest: str,
    constraints: tuple[str, ...] = (),
    confirm_foreign: tuple[str, ...] | None = None,
    access: Any = None,
    binding: Any = None,
    revision: Any = None,
    versions: Any = None,
) -> Any:
    return TypedArtifactStore.apply_import_records(
        records=tuple(records),
        preview_binding=preview["preview_binding"] if binding is None else binding,
        expected_store_revision=preview["store_revision"]
        if revision is None
        else revision,
        expected_versions=preview["expected_versions"]
        if versions is None
        else versions,
        confirm_foreign_ids=tuple(
            r["foreign_origin_id"] for r in records if "foreign_origin_id" in r
        )
        if confirm_foreign is None
        else confirm_foreign,
        confirm_constraint_ids=tuple(constraints),
        invocation_id=inv,
        effect_id=eff,
        request_digest=digest,
        access=access if access is not None else _write_access(env),
    )


def _run_import(
    env: Env,
    records: list[dict[str, Any]],
    *,
    inv: str,
    eff: str,
    digest: str,
    constraints: tuple[str, ...] = (),
) -> Any:
    preview = _preview(env, records, constraints=constraints)
    return _apply(
        env, records, preview, inv=inv, eff=eff, digest=digest, constraints=constraints
    )


def _hex(n: int) -> str:
    return f"{n:064x}"


def _expect_policy_error(code_value: str, reason_value: str | None, fn: Any) -> Any:
    from rush.memory.authorization import MemoryPolicyError

    with pytest.raises(MemoryPolicyError) as caught:
        fn()
    assert caught.value.code == code_value, (caught.value.code, caught.value.reason)
    if reason_value is not None:
        assert caught.value.reason == reason_value, (
            caught.value.code,
            caught.value.reason,
        )
    return caught.value


def _imported_rows(env: Env) -> list[sqlite3.Row]:
    return table_rows(env, "memory_artifacts", "trust_tier = 'IMPORTED'")


def test_t06_apply_import_records_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recs = [_rec("f1"), _constraint("f2", "c-one")]

    # Forged or omitted binding, wrong foreign confirmation, malformed records: E_INPUT.
    env = _import_env(tmp_path / "bind")
    pre = _preview(env, recs, constraints=("c-one",))
    snap = snapshot(env)
    forged = dict(pre["preview_binding"], preview_digest="0" * 64)
    wrong_ids = dict(pre["preview_binding"], selected_ids=["f2", "f1"])
    other_dest = dict(
        pre["preview_binding"],
        destination=dict(pre["preview_binding"]["destination"], root="/elsewhere"),
    )
    for label, kw in (
        ("omitted", {"binding": None}),
        ("forged_digest", {"binding": forged}),
        ("selected_ids_changed", {"binding": wrong_ids}),
        ("destination_changed", {"binding": other_dest}),
        ("confirm_foreign_subset", {"confirm_foreign": ("f1",)}),
        ("confirm_foreign_extra", {"confirm_foreign": ("f1", "f2", "f3")}),
    ):
        if label == "omitted":
            _expect_policy_error(
                "E_INPUT",
                None,
                lambda: TypedArtifactStore.apply_import_records(
                    records=tuple(recs),
                    preview_binding=None,  # type: ignore[arg-type]  # deliberately omitted
                    expected_store_revision=pre["store_revision"],
                    expected_versions=pre["expected_versions"],
                    confirm_foreign_ids=("f1", "f2"),
                    confirm_constraint_ids=("c-one",),
                    invocation_id="i",
                    effect_id="e",
                    request_digest=_hex(1),
                    access=_write_access(env),
                ),
            )
            continue
        _expect_policy_error(
            "E_INPUT",
            None,
            lambda kw=kw: _apply(
                env,
                recs,
                pre,
                inv="i",
                eff="e",
                digest=_hex(1),
                constraints=("c-one",),
                **kw,
            ),
        )
    bad_records = [dict(recs[0], extra_key=1)]
    _expect_policy_error(
        "E_INPUT",
        "import_record_invalid",
        lambda: _apply(env, bad_records, pre, inv="i", eff="e", digest=_hex(1)),
    )
    only_zero_effects(env, snap, "rejected applies")

    # Revision drift, a local row after preview, a store created after an absent preview.
    drift = _import_env(tmp_path / "drift")
    pre = _preview(drift, [_rec("f1")])
    assert drift.store is not None
    put(drift.store, "local-after", ALICE, text="added after preview")
    _expect_policy_error(
        "E_VERSION",
        "store_changed",
        lambda: _apply(drift, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(2)),
    )
    assert not _imported_rows(drift)

    cons = _import_env(tmp_path / "existing")
    assert cons.store is not None
    put(
        cons.store,
        "local-c",
        ALICE,
        content={"kind": "constraint", "constraint_id": "cx", "text": "local"},
    )
    pre = _preview(cons, [_constraint("f9", "cx")], constraints=("cx",))
    assert (
        pre["expected_versions"]
        == {"local-c": 1}
        == pre["preview_binding"]["existing_versions"]
    )
    put(
        cons.store,
        "local-c2",
        ALICE,
        content={"kind": "constraint", "constraint_id": "cx", "text": "second"},
    )
    _expect_policy_error(
        "E_VERSION",
        "store_changed",
        lambda: _apply(
            cons,
            [_constraint("f9", "cx")],
            pre,
            inv="i",
            eff="e",
            digest=_hex(3),
            constraints=("cx",),
        ),
    )

    absent = _import_env(tmp_path / "absent", store=False)
    pre_absent = _preview(absent, [_rec("f1")])
    assert pre_absent["store_state"] == "absent"
    TypedArtifactStore(absent.root)  # a store appears after the absent preview
    _expect_policy_error(
        "E_VERSION",
        "store_changed",
        lambda: _apply(
            absent, [_rec("f1")], pre_absent, inv="i", eff="e", digest=_hex(4)
        ),
    )

    # policy_revision or grant_id differing from the live resolve: recovery_required.
    rev = _import_env(tmp_path / "rev")
    pre = _preview(rev, [_rec("f1")])
    rev.grants["alice"] = grant(
        rev, rev.data_root, ALICE, sources=(SRC, IMPORT_SOURCE, "extra")
    )
    _expect_policy_error(
        "E_VERSION",
        "recovery_required",
        lambda: _apply(rev, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(5)),
    )

    # Preview and find on a corrupt or busy store: the store error code, zero effects.
    from rush.memory.store import MemoryStoreUnreadableError

    bad = _import_env(tmp_path / "corrupt")
    bad.db.write_bytes(b"garbage" * 200)
    before = sha_file(bad.db)
    with pytest.raises(MemoryStoreUnreadableError) as corrupt:
        _preview(bad, [_rec("f1")])
    assert corrupt.value.code == "E_STORE_CORRUPT"
    with pytest.raises(MemoryStoreUnreadableError) as found:
        TypedArtifactStore.find_import_effect_readonly(
            invocation_id="i",
            effect_id="e",
            request_digest=_hex(6),
            access=_write_access(bad),
        )
    assert found.value.code == "E_STORE_CORRUPT"
    assert sha_file(bad.db) == before
    busy = _import_env(tmp_path / "busy")
    with monkeypatch.context() as patch:
        patch.setattr(
            TypedArtifactStore,
            "open_readonly_view",
            classmethod(lambda cls, root: (None, "busy")),
        )
        with pytest.raises(MemoryStoreUnreadableError) as is_busy:
            _preview(busy, [_rec("f1")])
        assert is_busy.value.code == "E_STORE_BUSY"

    # The committed effect: replay after drift, digest conflict, narrowed scope.
    ok = _import_env(tmp_path / "ok")
    recs_ok = [_rec("f1"), _constraint("f2", "c-one")]
    pre = _preview(ok, recs_ok, constraints=("c-one",))
    first = _apply(
        ok,
        recs_ok,
        pre,
        inv="inv-i",
        eff="eff-i",
        digest=_hex(7),
        constraints=("c-one",),
    )
    mappings = find_key(first, "mappings")
    assert [m["foreign_origin_id"] for m in mappings] == ["f1", "f2"]
    assert [m["applicability"] for m in mappings] == ["pending", "active"]
    assert all(m["artifact_version"] == 1 for m in mappings)
    rows_before = row_count(ok)
    assert ok.store is not None
    put(ok.store, "drift-row", ALICE, text="store revision moves")
    replay = _apply(
        ok,
        recs_ok,
        pre,
        inv="inv-i",
        eff="eff-i",
        digest=_hex(7),
        constraints=("c-one",),
    )
    assert find_key(replay, "mappings") == mappings
    assert row_count(ok) == rows_before + 1  # only the drift row; no second import
    assert len(v2_receipts(ok)) == 1
    _expect_policy_error(
        "E_VERSION",
        "effect_digest_conflict",
        lambda: _apply(
            ok,
            recs_ok,
            pre,
            inv="inv-i",
            eff="eff-i",
            digest=_hex(8),
            constraints=("c-one",),
        ),
    )
    ok.grants["alice"] = grant(ok, ok.data_root, ALICE, sources=(IMPORT_SOURCE,))
    narrowed = _write_access(ok)
    # Result refs now live in a source the narrowed access also covers; revoke to make them invisible.
    with contextlib.closing(sqlite3.connect(ok.db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET source = 'elsewhere' WHERE trust_tier = 'IMPORTED'"
        )
        conn.commit()
    _expect_policy_error(
        "E_NOT_VISIBLE",
        None,
        lambda: _apply(
            ok,
            recs_ok,
            pre,
            inv="inv-i",
            eff="eff-i",
            digest=_hex(9),
            constraints=("c-one",),
            access=narrowed,
        ),
    )
    found_state = TypedArtifactStore.find_import_effect_readonly
    with pytest.raises(Exception) as hidden:
        found_state(
            invocation_id="inv-i",
            effect_id="eff-i",
            request_digest=_hex(7),
            access=narrowed,
        )
    assert getattr(hidden.value, "code", None) == "E_NOT_VISIBLE"

    # Reviewed confirm_constraint_ids: empty, selected, unknown, duplicate, changed, omitted.
    cc = _import_env(tmp_path / "constraints")
    two = [_constraint("k1", "ca"), _constraint("k2", "cb"), _rec("k3")]
    for label, confirm, expect in (
        ("empty", (), {"k1": "pending", "k2": "pending", "k3": "pending"}),
        ("selected", ("ca",), {"k1": "active", "k2": "pending", "k3": "pending"}),
        ("both", ("ca", "cb"), {"k1": "active", "k2": "active", "k3": "pending"}),
    ):
        env_c = _import_env(tmp_path / f"c-{label}")
        res = _run_import(
            env_c,
            two,
            inv=f"i-{label}",
            eff=f"e-{label}",
            digest=_hex(20),
            constraints=confirm,
        )
        got = {
            m["foreign_origin_id"]: m["applicability"]
            for m in find_key(res, "mappings")
        }
        assert got == expect, label
        assert all(
            json.loads(r["content"])["authority"] == "imported_unverified"
            for r in _imported_rows(env_c)
        )
    pre_c = _preview(cc, two, constraints=("ca",))
    for label, confirm in (
        ("unknown", ("zz",)),
        ("duplicate", ("ca", "ca")),
        ("changed", ("cb",)),
        ("non_constraint", ("k3",)),
    ):
        _expect_policy_error(
            "E_INPUT",
            None,
            lambda confirm=confirm: _apply(
                cc, two, pre_c, inv="i", eff="e", digest=_hex(21), constraints=confirm
            ),
        )
    _expect_policy_error(
        "E_INPUT",
        None,
        lambda: _apply(
            cc, two, pre_c, inv="i", eff="e", digest=_hex(21), constraints=()
        ),
    )
    assert not _imported_rows(cc)

    # Request digest shape: exactly 64 lowercase hexadecimal characters.
    dg = _import_env(tmp_path / "digest")
    pre_d = _preview(dg, [_rec("f1")])
    for bad_digest in (
        "ABC",
        "g" * 64,
        "A" * 64,
        "a" * 63,
        "a" * 65,
        "",
        None,
        5,
        b"a" * 64,
    ):
        _expect_policy_error(
            "E_INPUT",
            None,
            lambda d=bad_digest: _apply(
                dg, [_rec("f1")], pre_d, inv="i", eff="e", digest=d
            ),
        )
        with pytest.raises(Exception) as bad_find:
            TypedArtifactStore.find_import_effect_readonly(
                invocation_id="i",
                effect_id="e",
                request_digest=bad_digest,  # type: ignore[arg-type]  # deliberate bad digest
                access=_write_access(dg),
            )
        assert getattr(bad_find.value, "code", "E_INPUT") == "E_INPUT"
    assert not _imported_rows(dg)

    # A contradictory imported record leaves the local explicit choice unchanged (D34).
    d34 = _import_env(tmp_path / "d34")
    assert d34.store is not None
    put(
        d34.store,
        "local-choice",
        ALICE,
        content={"kind": "constraint", "constraint_id": "same", "text": "local choice"},
    )
    local_before = dict(table_rows(d34, "memory_artifacts", "id = 'local-choice'")[0])
    res = _run_import(
        d34,
        [_constraint("fz", "same", "foreign contradiction")],
        inv="i-d34",
        eff="e-d34",
        digest=_hex(22),
        constraints=("same",),
    )
    assert find_key(res, "mappings")[0]["applicability"] == "active"
    assert (
        dict(table_rows(d34, "memory_artifacts", "id = 'local-choice'")[0])
        == local_before
    )

    # Injected failure after the applicability write and after the receipt: everything rolls back.
    for stage, owner_obj, attr in (
        ("receipt", TypedArtifactStore, "_write_v2_receipt"),
        ("insert", TypedArtifactStore, "_insert_row"),
    ):
        inj = _import_env(tmp_path / f"inj-{stage}")
        pre_i = _preview(
            inj, [_rec("f1"), _constraint("f2", "c1")], constraints=("c1",)
        )
        counts = (
            row_count(inj),
            row_count(inj, "memory_artifact_versions"),
            len(all_receipts(inj)),
        )
        with monkeypatch.context() as patch:
            injected = _inject_after(patch, owner_obj, attr)
            with pytest.raises(RuntimeError, match="injected failure"):
                _apply(
                    inj,
                    [_rec("f1"), _constraint("f2", "c1")],
                    pre_i,
                    inv="i",
                    eff="e",
                    digest=_hex(23),
                    constraints=("c1",),
                )
        assert (
            row_count(inj),
            row_count(inj, "memory_artifact_versions"),
            len(all_receipts(inj)),
        ) == counts, stage
        assert injected["fired"], f"the {stage} step never ran"


def test_t06_import_record_schema(tmp_path: Path) -> None:
    from rush.delivery import compact
    from rush.safety.redactor import sanitize_value

    env = _import_env(tmp_path / "schema")
    assert env.store is not None
    # Foreign-equal constraint ids in a Bob-owned row and in an ungranted source do not
    # appear in `existing_versions`; Alice's own equal id does.
    put(
        env.store,
        "bob-c",
        BOB,
        content={"kind": "constraint", "constraint_id": "c1", "text": "bob"},
    )
    put(
        env.store,
        "ungranted-c",
        ALICE,
        source="not-granted",
        content={"kind": "constraint", "constraint_id": "c1", "text": "other source"},
    )
    put(
        env.store,
        "alice-c",
        ALICE,
        content={"kind": "constraint", "constraint_id": "c1", "text": "alice"},
    )
    recs = [
        _rec(
            "fa",
            content={"text": "a domain record", "authority": "explicit"},
            symbol_ref=None,
        ),
        _constraint("fb", "c1"),
    ]
    preview = _preview(env, recs, constraints=("c1",), mapping_id="map-1")
    assert set(preview) == {
        "preview_binding",
        "store_state",
        "store_revision",
        "expected_versions",
        "records",
        "redactions",
    }
    binding = preview["preview_binding"]
    assert preview["store_state"] == "current" and isinstance(
        preview["store_revision"], int
    )
    assert (
        preview["expected_versions"] == binding["existing_versions"] == {"alice-c": 1}
    )
    assert (
        binding["selected_ids"] == ["fa", "fb"] and binding["capsule_digest"] == CAPSULE
    )
    assert binding["mapping_id"] == "map-1" and binding["confirm_constraint_ids"] == [
        "c1"
    ]
    assert binding["destination"]["root"] == str(env.root)
    assert binding["destination"]["owner_scope"] == {"kind": "user", "id": "alice"}
    without = {k: v for k, v in binding.items() if k != "preview_digest"}
    assert (
        binding["preview_digest"]
        == hashlib.sha256(compact.canonical_json(without)).hexdigest()
    )
    assert [r["applicability"] for r in preview["records"]] == ["pending", "active"]

    result = _apply(
        env, recs, preview, inv="i", eff="e", digest=_hex(30), constraints=("c1",)
    )
    mappings = find_key(result, "mappings")
    assert [m["foreign_origin_id"] for m in mappings] == ["fa", "fb"]
    assert len({m["artifact_id"] for m in mappings}) == 2
    assert not {m["artifact_id"] for m in mappings} & {"fa", "fb"}
    assert [m["applicability"] for m in mappings] == ["pending", "active"]
    for mapping, foreign in zip(mappings, recs, strict=True):
        row = table_rows(env, "memory_artifacts", "id = ?", (mapping["artifact_id"],))[
            0
        ]
        content = json.loads(row["content"])
        assert row["artifact_version"] == 1 and row["trust_tier"] == "IMPORTED"
        assert row["source"] == IMPORT_SOURCE
        assert (row["owner_scope_kind"], row["owner_scope_id"]) == ("user", "alice")
        for column in ("signature", "promoted_at", "symbol_ref", "content_hash"):
            assert row[column] is None, column
        assert content["authority"] == "imported_unverified"
        assert content["import_provenance"] == {
            "capsule_digest": CAPSULE,
            "foreign_origin_id": foreign["foreign_origin_id"],
            "foreign_source": "foreign-src",
            "foreign_owner": None,
            "foreign_symbol_ref": None,
            "foreign_content_hash": None,
        }
    # Without `write` on `capsule:import` the apply is refused with E_SCOPE.
    narrow = _import_env(tmp_path / "narrow")
    narrow.grants["alice"] = grant(
        narrow, narrow.data_root, ALICE, sources=(SRC,), ops=GRANT_OPS
    )
    from rush.memory.retrieval import MemoryAccess

    plain = MemoryAccess.resolve(
        narrow.root,
        operation="write",
        apply=True,
        owner_scope=ALICE,
        data_root=narrow.data_root,
    )
    assert plain is not None
    pre_n = _preview(narrow, [_rec("fx")], access=plain)
    _expect_policy_error(
        "E_SCOPE",
        None,
        lambda: _apply(
            narrow, [_rec("fx")], pre_n, inv="i", eff="e", digest=_hex(31), access=plain
        ),
    )
    assert not _imported_rows(narrow)

    # Record shape: every deviation is `import_record_invalid` from preview and from apply.
    good = _rec("ok")
    mutations: dict[str, Any] = {}
    for key in good:
        mutations[f"missing_{key}"] = {k: v for k, v in good.items() if k != key}
    for extra in (
        "id",
        "trust_tier",
        "signature",
        "owner_scope",
        "source",
        "origin_kind",
        "origin_id",
        "surplus",
    ):
        mutations[f"unknown_{extra}"] = {**good, extra: "x"}
    mutations.update(
        {
            "empty_id": {**good, "foreign_origin_id": ""},
            "id_int": {**good, "foreign_origin_id": 5},
            "family_bad": {**good, "family": "nope"},
            "subject_bad": {**good, "subject": "nope"},
            "content_list": {**good, "content": ["x"]},
            "source_empty": {**good, "foreign_source": ""},
            "owner_bad": {**good, "foreign_owner": {"kind": "", "id": "x"}},
            "owner_str": {**good, "foreign_owner": "user:x"},
            "symbol_int": {**good, "foreign_symbol_ref": 5},
            "hash_short": {**good, "foreign_content_hash": "ab"},
            "hash_upper": {**good, "foreign_content_hash": "A" * 64},
        }
    )
    snap = snapshot(env)
    for bad_record in mutations.values():
        _expect_policy_error(
            "E_INPUT", "import_record_invalid", lambda b=bad_record: _preview(env, [b])
        )
        _expect_policy_error(
            "E_INPUT",
            "import_record_invalid",
            lambda b=bad_record: _apply(
                env, [b], preview, inv="i2", eff="e2", digest=_hex(32)
            ),
        )
    _expect_policy_error(
        "E_INPUT",
        "import_record_invalid",
        lambda: _preview(env, [_rec("dup"), _rec("dup")]),
    )
    only_zero_effects(env, snap, "invalid records")

    # Redaction: the preview content is the stored sanitized content; a changed redaction
    # set between preview and apply is recovery_required.
    secret = {"text": "key AKIAIOSFODNN7EXAMPLE end"}
    sanitized = sanitize_value(secret)
    assert sanitized.redaction_count >= 1
    red = _import_env(tmp_path / "redact")
    pre = _preview(red, [_rec("sec", content=secret)])
    assert pre["records"][0]["content"] == sanitized.value
    assert pre["redactions"] == [
        {"foreign_origin_id": "sec", "count": sanitized.redaction_count}
    ]
    _expect_policy_error(
        "E_VERSION",
        "recovery_required",
        lambda: _apply(
            red,
            [_rec("sec", content={"text": "key removed"})],
            pre,
            inv="i",
            eff="e",
            digest=_hex(33),
        ),
    )
    done = _apply(
        red, [_rec("sec", content=secret)], pre, inv="i", eff="e", digest=_hex(33)
    )
    stored = table_rows(
        red,
        "memory_artifacts",
        "id = ?",
        (find_key(done, "mappings")[0]["artifact_id"],),
    )[0]
    assert json.loads(stored["content"])["text"] == sanitized.value["text"]
    assert "AKIAIOSFODNN7EXAMPLE" not in stored["content"]

    # find_import_effect_readonly: absent, present with exact mappings, unavailable.
    fnd = _import_env(tmp_path / "find")
    access = _write_access(fnd)
    assert TypedArtifactStore.find_import_effect_readonly(
        invocation_id="i", effect_id="e", request_digest=_hex(34), access=access
    ) == {"state": "absent"}
    out = _run_import(fnd, [_rec("fm")], inv="i", eff="e", digest=_hex(34))
    present = TypedArtifactStore.find_import_effect_readonly(
        invocation_id="i",
        effect_id="e",
        request_digest=_hex(34),
        access=_write_access(fnd),
    )
    assert present["state"] == "present"
    assert find_key(present["result"], "mappings") == find_key(out, "mappings")
    gone = _import_env(tmp_path / "gone", store=False)
    assert TypedArtifactStore.find_import_effect_readonly(
        invocation_id="i",
        effect_id="e",
        request_digest=_hex(34),
        access=_write_access(gone),
    ) == {"state": "unavailable", "store_state": "absent"}


# =============================================================================
# R15: store creation, atomicity, containment and crash recovery
# =============================================================================


def _tree(base: Path) -> list[str]:
    return (
        sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))
        if base.exists()
        else []
    )


def test_t06_import_creates_store_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Previews report the store state and create nothing.
    absent = _import_env(tmp_path / "absent", store=False)
    snap = snapshot(absent)
    pre = _preview(absent, [_rec("f1")])
    assert (
        pre["store_state"] == "absent"
        and pre["store_revision"] == 0
        and pre["expected_versions"] == {}
    )
    only_zero_effects(absent, snap, "absent preview")

    old = _import_env(tmp_path / "old")
    with contextlib.closing(sqlite3.connect(old.db)) as conn:
        for table in ("memory_artifacts", "memory_artifact_versions"):
            for column in ("payload_hash", "payload_hash_origin"):
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()
    snap_old = snapshot(old)
    pre_old = _preview(old, [_rec("f1")])
    assert (
        pre_old["store_state"] == "migration_required"
        and pre_old["store_revision"] == 0
    )
    only_zero_effects(old, snap_old, "migration_required preview")
    from rush.memory.store import MemoryMigrationRequiredError

    with pytest.raises(MemoryMigrationRequiredError):
        _apply(old, [_rec("f1")], pre_old, inv="i", eff="e", digest=_hex(40))
    only_zero_effects(old, snap_old, "migration_required apply")

    current = _import_env(tmp_path / "current")
    assert _preview(current, [_rec("f1")])["store_state"] == "current"

    # Absent apply: only ":memory:" is connected before the link; then a real store.
    events: list[str] = []
    real_connect, real_link = sqlite3.connect, os.link

    def spy_connect(database: Any, *args: Any, **kwargs: Any) -> Any:
        events.append(f"connect:{database}")
        return real_connect(database, *args, **kwargs)

    def spy_link(*args: Any, **kwargs: Any) -> Any:
        events.append("LINK")
        return real_link(*args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", spy_connect)
        patch.setattr(os, "link", spy_link)
        res = _run_import(absent, [_rec("f1")], inv="i", eff="e", digest=_hex(41))
    assert "LINK" in events
    before_link = events[: events.index("LINK")]
    assert before_link and all(e == "connect::memory:" for e in before_link), (
        before_link
    )
    assert absent.db.exists() and not list(
        (absent.root / ".rush").glob("memory.db.import-*")
    )
    assert find_key(res, "mappings")
    reference = TypedArtifactStore(tmp_path / "reference")
    assert reference is not None

    def shape(db: Path) -> tuple[Any, ...]:
        with contextlib.closing(sqlite3.connect(db)) as conn:
            names = sorted(
                r[:2]
                for r in conn.execute(
                    "SELECT type, name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            )
            return (conn.execute("PRAGMA user_version").fetchone()[0], names)

    assert shape(absent.db) == shape(tmp_path / "reference" / ".rush" / "memory.db")
    TypedArtifactStore(absent.root)
    with contextlib.closing(sqlite3.connect(absent.db)) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    # An existing memory.db at link time -> store_changed; other link errors -> publication_unsupported.
    for label, exc, want in (
        ("exists", None, ("E_VERSION", "store_changed")),
        (
            "unsupported",
            OSError(1, "Operation not permitted"),
            ("E_UNAVAILABLE", "publication_unsupported"),
        ),
    ):
        env = _import_env(tmp_path / f"link-{label}", store=False)
        pre_l = _preview(env, [_rec("f1")])
        original = os.link

        def failing_link(
            *args: Any,
            exc: Any = exc,
            env: Env = env,
            original: Any = original,
            **kwargs: Any,
        ) -> Any:
            if exc is not None:
                raise exc
            (env.root / ".rush" / "memory.db").write_bytes(
                b"planted by a racing writer"
            )
            return original(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(os, "link", failing_link)
            _expect_policy_error(
                want[0],
                want[1],
                lambda env=env, pre_l=pre_l: _apply(
                    env, [_rec("f1")], pre_l, inv="i", eff="e", digest=_hex(42)
                ),
            )
        assert not list((env.root / ".rush").glob("memory.db.import-*")), label
        if label == "exists":
            assert (
                env.root / ".rush" / "memory.db"
            ).read_bytes() == b"planted by a racing writer"
        else:
            assert not (env.root / ".rush" / "memory.db").exists()

    # Orphan temp: preview and reads leave it; the apply removes it under the lock.
    orphan_env = _import_env(tmp_path / "orphan", store=False)
    (orphan_env.root / ".rush").mkdir(exist_ok=True)
    orphan = orphan_env.root / ".rush" / "memory.db.import-deadbeef"
    orphan.write_bytes(b"left by a crashed apply")
    pre_o = _preview(orphan_env, [_rec("f1")])
    TypedArtifactStore.open_readonly_view(orphan_env.root)
    assert orphan.exists()
    _apply(orphan_env, [_rec("f1")], pre_o, inv="i", eff="e", digest=_hex(43))
    assert not orphan.exists() and orphan_env.db.exists()


def _failure_stages() -> list[Any]:
    return [
        pytest.param(s, id=s)
        for s in ("constructor", "schema", "rows", "receipt", "serialize", "temp_write")
    ]


class _SerializeFails:
    """A `sqlite3.Connection` proxy whose `serialize` completes and then fails."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._conn, name, value)

    def __enter__(self) -> Any:
        self._conn.__enter__()
        return self

    def __exit__(self, *exc: object) -> Any:
        return self._conn.__exit__(*exc)

    def serialize(self, *args: Any, **kwargs: Any) -> Any:
        self._conn.serialize(*args, **kwargs)
        raise RuntimeError("injected failure after serialize")


@pytest.mark.parametrize(
    "mode", [pytest.param("policy", id="policy"), pytest.param("legacy", id="legacy")]
)
@pytest.mark.parametrize("stage", _failure_stages())
def test_t06_import_failure_leaves_tree_unchanged(
    stage: str, mode: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _import_env(tmp_path, mode=mode, store=False)
    pre = _preview(env, [_rec("f1"), _rec("f2")])
    tree_before = _tree(env.root)
    snap = snapshot(env)
    fired: dict[str, bool] | None = None
    with monkeypatch.context() as patch:
        if stage == "constructor":
            fired = _inject_after(patch, TypedArtifactStore, "_init_db")
        elif stage == "schema":
            fired = _inject_after(
                patch, TypedArtifactStore, "_migrate_owner_scope_columns"
            )
        elif stage == "rows":
            fired = _inject_after(patch, TypedArtifactStore, "_insert_row")
        elif stage == "receipt":
            fired = _inject_after(patch, TypedArtifactStore, "_write_v2_receipt")
        elif stage == "serialize":
            real_connect = sqlite3.connect

            def proxied(database: Any, *args: Any, **kwargs: Any) -> Any:
                conn = real_connect(database, *args, **kwargs)
                return _SerializeFails(conn) if database == ":memory:" else conn

            patch.setattr(sqlite3, "connect", proxied)
        else:
            real_fsync = os.fsync

            def failing_fsync(fd: int) -> None:
                import stat as stat_module

                if stat_module.S_ISREG(os.fstat(fd).st_mode):
                    real_fsync(fd)
                    raise OSError(5, "injected failure after the temp write")
                real_fsync(fd)

            patch.setattr(os, "fsync", failing_fsync)
        with pytest.raises(Exception) as caught:
            _apply(
                env, [_rec("f1"), _rec("f2")], pre, inv="i", eff="e", digest=_hex(50)
            )
    assert "injected failure" in str(caught.value), repr(caught.value)
    if fired is not None:
        assert fired["fired"], f"the {stage} step never ran"
    assert _tree(env.root) == tree_before, (
        "a failed import changed the destination tree"
    )
    assert snapshot(env) == snap
    assert not env.db.exists()
    assert not (env.root / ".rush" / "cache").exists()
    if mode == "legacy":
        assert not (env.root / ".rush").exists(), (
            "a .rush this call created must be removed"
        )


class _Swap:
    """Install a one-shot swap of `<root>/.rush` for a symlink at a named point."""

    def __init__(self, tmp_path: Path, root: Path) -> None:
        self.root = root
        self.moved = tmp_path / "moved-rush"
        self.elsewhere = tmp_path / "elsewhere"
        self.elsewhere.mkdir()
        (self.elsewhere / "sentinel.txt").write_text(
            "outside the root", encoding="utf-8"
        )
        self.fired = False

    def swap(self) -> None:
        if self.fired:
            return
        self.fired = True
        os.rename(self.root / ".rush", self.moved)
        os.symlink(self.elsewhere, self.root / ".rush")

    def install(self, patch: pytest.MonkeyPatch, point: str) -> None:
        import stat as stat_module

        real_open, real_fsync, real_link = os.open, os.fsync, os.link
        o_dir = getattr(os, "O_DIRECTORY", 0)

        def open_(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
            fd = real_open(path, flags, *args, **kwargs)
            if (
                point == "after_dir_open"
                and flags & o_dir
                and os.path.basename(os.fspath(path)) == ".rush"
            ):
                self.swap()
            return fd

        def fsync(fd: int) -> None:
            real_fsync(fd)
            if point == "after_temp_written" and stat_module.S_ISREG(
                os.fstat(fd).st_mode
            ):
                self.swap()

        def link(*args: Any, **kwargs: Any) -> Any:
            if point == "before_link":
                self.swap()
            result = real_link(*args, **kwargs)
            if point == "after_link":
                self.swap()
            return result

        patch.setattr(os, "open", open_)
        patch.setattr(os, "fsync", fsync)
        patch.setattr(os, "link", link)


def _assert_clean_after_swap(swap: _Swap, env: Env) -> None:
    assert not (swap.moved / "memory.db").exists()
    assert not list(swap.moved.glob("memory.db.import-*")), (
        "temp left in the moved directory"
    )
    assert sorted(p.name for p in swap.elsewhere.iterdir()) == ["sentinel.txt"]
    assert (swap.elsewhere / "sentinel.txt").read_text(
        encoding="utf-8"
    ) == "outside the root"
    assert not os.path.lexists(env.root / ".rush" / "memory.db")


def _containment_cases() -> list[Any]:
    posix = pytest.mark.posix_only
    windows = pytest.mark.windows_only
    cases: list[Any] = [
        pytest.param("rush_symlink", id="posix_rush_symlink", marks=posix),
        pytest.param("after_dir_open", id="posix_swap_after_dir_open", marks=posix),
        pytest.param(
            "after_temp_written", id="posix_swap_after_temp_written", marks=posix
        ),
        pytest.param("before_link", id="posix_swap_before_link", marks=posix),
        pytest.param("after_link", id="posix_swap_after_link", marks=posix),
        pytest.param(
            "orphan_symlink", id="posix_orphan_symlink_never_followed", marks=posix
        ),
        pytest.param("windows_junction", id="windows_junction_rush", marks=windows),
    ]
    for index, point in enumerate(
        ("after_dir_open", "after_temp_written", "before_link", "after_link"), start=1
    ):
        cases.append(
            pytest.param(
                f"windows_rename_rush:{point}",
                id=f"windows_rename_rush_injection_{index}",
                marks=windows,
            )
        )
        cases.append(
            pytest.param(
                f"windows_rename_root:{point}",
                id=f"windows_rename_root_injection_{index}",
                marks=windows,
            )
        )
    return cases


@pytest.mark.parametrize("case", _containment_cases())
def test_t06_import_path_containment(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = _import_env(tmp_path / "proj", store=False)
    pre = _preview(env, [_rec("f1")])
    if case == "rush_symlink":
        swap = _Swap(tmp_path, env.root)
        os.rename(env.root / ".rush", swap.moved)
        os.symlink(swap.elsewhere, env.root / ".rush")
        error = _expect_policy_error(
            "E_PERMISSION",
            "symlink",
            lambda: _apply(env, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(60)),
        )
        assert error is not None
        _assert_clean_after_swap(swap, env)
        return
    if case in {"after_dir_open", "after_temp_written", "before_link", "after_link"}:
        swap = _Swap(tmp_path, env.root)
        with monkeypatch.context() as patch:
            swap.install(patch, case)
            _expect_policy_error(
                "E_PERMISSION",
                "symlink",
                lambda: _apply(
                    env, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(61)
                ),
            )
        assert swap.fired, f"the swap point {case} was never reached"
        _assert_clean_after_swap(swap, env)
        return
    if case == "orphan_symlink":
        from rush.memory.authorization import MemoryPolicyError

        outside = tmp_path / "outside-target"
        outside.write_text("must survive", encoding="utf-8")
        (env.root / ".rush").mkdir(exist_ok=True)
        evil = env.root / ".rush" / "memory.db.import-evil"
        os.symlink(outside, evil)
        try:
            _apply(env, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(62))
        except (
            MemoryPolicyError
        ) as exc:  # a refusal is acceptable; following the link is not
            assert exc.code in {"E_PERMISSION", "E_UNAVAILABLE"}
        assert outside.read_text(encoding="utf-8") == "must survive"
        return
    _windows_containment(case, env, pre, tmp_path, monkeypatch)


def _windows_containment(
    case: str,
    env: Env,
    pre: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Native Windows cells (deselected elsewhere; recorded native-pending until 72-T09)."""
    import shutil

    if case == "windows_junction":
        target = tmp_path / "junction-target"
        target.mkdir()
        shutil.rmtree(env.root / ".rush", ignore_errors=True)
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(env.root / ".rush"), str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        _expect_policy_error(
            "E_PERMISSION",
            "symlink",
            lambda: _apply(env, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(63)),
        )
        assert list(target.iterdir()) == []
        return
    kind, point = case.split(":")
    target_path = env.root / ".rush" if kind == "windows_rename_rush" else env.root
    renamed: list[BaseException] = []
    real_open, real_fsync, real_link = os.open, os.fsync, os.link

    def attempt() -> None:
        if renamed:
            return
        try:
            os.rename(target_path, tmp_path / "renamed-away")
        except PermissionError as exc:
            renamed.append(exc)
        else:  # pragma: no cover - a pinned directory must refuse the rename
            renamed.append(AssertionError("rename of a pinned directory succeeded"))

    def open_(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        # The pin loop has completed when the publication temp is first created.
        if point == "after_dir_open" and os.path.basename(os.fspath(path)).startswith(
            "memory.db.import-"
        ):
            attempt()
        return real_open(path, flags, *args, **kwargs)

    def fsync(fd: int) -> None:
        real_fsync(fd)
        if point == "after_temp_written":
            attempt()

    def link(*args: Any, **kwargs: Any) -> Any:
        if point == "before_link":
            attempt()
        out = real_link(*args, **kwargs)
        if point == "after_link":
            attempt()
        return out

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", open_)
        patch.setattr(os, "fsync", fsync)
        patch.setattr(os, "link", link)
        result = _apply(env, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(64))
    assert find_key(result, "mappings")
    assert all(isinstance(e, PermissionError) for e in renamed), renamed
    assert env.db.exists() and not list((env.root / ".rush").glob("memory.db.import-*"))
    os.rename(env.root / ".rush", tmp_path / "after-return")  # every handle is closed


_CRASH_CHILD = r"""
import json, os, sys
from pathlib import Path
from rush.memory.retrieval import MemoryAccess
from rush.memory.store import OwnerScope, TypedArtifactStore

params = json.loads(Path(sys.argv[1]).read_text())
access = MemoryAccess.resolve(Path(params["root"]), operation="write", apply=True,
    owner_scope=OwnerScope("user", "alice"), requested_sources=("capsule:import",),
    data_root=Path(params["data_root"]))
real_link = os.link
def link(*a, **k):
    out = real_link(*a, **k)
    os._exit(9)
os.link = link
TypedArtifactStore.apply_import_records(
    records=tuple(params["records"]), preview_binding=params["binding"],
    expected_store_revision=params["revision"], expected_versions=params["versions"],
    confirm_foreign_ids=tuple(params["confirm"]), confirm_constraint_ids=(),
    invocation_id="i", effect_id="e", request_digest=params["digest"], access=access)
os._exit(3)
"""


def test_t06_import_crash_after_link(tmp_path: Path) -> None:
    env = _import_env(tmp_path / "crash", store=False)
    recs = [_rec("f1"), _rec("f2")]
    pre = _preview(env, recs)
    params = tmp_path / "params.json"
    params.write_text(
        json.dumps(
            {
                "root": str(env.root),
                "data_root": str(env.data_root),
                "records": recs,
                "binding": pre["preview_binding"],
                "revision": pre["store_revision"],
                "versions": pre["expected_versions"],
                "confirm": ["f1", "f2"],
                "digest": _hex(70),
            }
        ),
        encoding="utf-8",
    )
    child = subprocess.run(  # noqa: PLW1510 - the exit code is asserted below
        [sys.executable, "-c", _CRASH_CHILD, str(params)],
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert child.returncode == 9, child.stderr
    assert env.db.exists(), "the link had completed before the crash"
    assert list((env.root / ".rush").glob("memory.db.import-*")), (
        "the crash left the temp orphan"
    )
    access = _write_access(env)
    state = TypedArtifactStore.find_import_effect_readonly(
        invocation_id="i", effect_id="e", request_digest=_hex(70), access=access
    )
    assert state["state"] == "present"
    mappings = find_key(state["result"], "mappings")
    assert [m["foreign_origin_id"] for m in mappings] == ["f1", "f2"]
    rows = row_count(env)
    # Restart: the same reviewed request replays the committed mapping; nothing duplicates.
    retry = _apply(env, recs, pre, inv="i", eff="e", digest=_hex(70))
    assert find_key(retry, "mappings") == mappings
    assert row_count(env) == rows and len(v2_receipts(env)) == 1
    assert not list((env.root / ".rush").glob("memory.db.import-*")), (
        "orphan removed under the lock"
    )


def test_t06_import_windows_publication_fake_kernel32(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Locally runnable sibling of the Windows pin/publication branch: a fake kernel32
    records the exact CreateFileW arguments; it certifies the call shape, the error
    mapping, the reparse refusal and handle closure -- not native rename behavior."""
    import ctypes
    import stat as stat_module
    import types

    # Envs, previews and access objects are built before the store module is switched
    # to "nt", on the real platform. Every env grants into the shared policy, which
    # bumps its revision, so all envs come first and the previews and access last.
    env = _import_env(tmp_path / "win", store=False)
    err_cases = [
        (
            code_number,
            reason_value,
            code_value,
            _import_env(tmp_path / f"win-err-{code_number}", store=False),
        )
        for code_number, reason_value, code_value in (
            (2, "path_escape", "E_PERMISSION"),
            (3, "path_escape", "E_PERMISSION"),
            (5, "publication_unsupported", "E_UNAVAILABLE"),
        )
    ]
    rp = _import_env(tmp_path / "win-reparse", store=False)
    pre = _preview(env, [_rec("f1")])
    access = _write_access(env)
    bound_err_cases = [
        (*case, _preview(case[3], [_rec("f1")]), _write_access(case[3]))
        for case in err_cases
    ]
    pre_r = _preview(rp, [_rec("f1")])
    access_r = _write_access(rp)
    calls: list[tuple[str, int, int, int, int]] = []
    opened: dict[int, int] = {}
    closed: list[int] = []
    outcome = {
        "error": 0,
        "attributes": stat_module.FILE_ATTRIBUTE_DIRECTORY
        if hasattr(stat_module, "FILE_ATTRIBUTE_DIRECTORY")
        else 0x10,
        "invalid": False,
    }

    class FakeKernel32:
        def __init__(self) -> None:
            # A plain function (not a bound method) so the product may set `.restype`.
            def create_file(*args: Any) -> Any:
                return self._create(*args)

            self.CreateFileW = create_file

        def _create(
            self,
            path: str,
            access: int,
            share: int,
            security: Any,
            disposition: int,
            flags: int,
            template: Any,
        ) -> Any:
            calls.append((str(path), access, share, disposition, flags))
            if outcome["invalid"]:
                return ctypes.c_void_p(-1).value
            handle = 1000 + len(calls)
            opened[handle] = os.open(str(path), os.O_RDONLY)
            return handle

    fake_msvcrt = types.SimpleNamespace(
        open_osfhandle=lambda handle, flags: opened[handle]
    )
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    monkeypatch.setattr(
        ctypes,
        "WinDLL",
        lambda name, use_last_error=False: FakeKernel32(),
        raising=False,
    )
    monkeypatch.setattr(
        ctypes, "get_last_error", lambda: outcome["error"], raising=False
    )
    real_close = os.close

    def closing(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(os, "close", closing)
    real_fstat = os.fstat

    def fstat(fd: int) -> Any:
        base = real_fstat(fd)
        return types.SimpleNamespace(
            **{k: getattr(base, k) for k in dir(base) if k.startswith("st_")},
            st_file_attributes=outcome["attributes"],
        )

    monkeypatch.setattr(os, "fstat", fstat)
    # Only the store module sees "nt": patching the real os.name would make pathlib
    # instantiate WindowsPath, which cannot exist on this platform.
    import rush.memory.store as store_module

    class NtOs:
        name = "nt"

        def __getattr__(self, attribute: str) -> Any:
            return getattr(os, attribute)

    monkeypatch.setattr(store_module, "os", NtOs())
    result = _apply(
        env, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(80), access=access
    )
    assert find_key(result, "mappings")
    assert calls, "no directory was pinned through CreateFileW"
    for _path, access, share, disposition, flags in calls:
        assert (access, share, disposition, flags) == (0x81, 0x3, 3, 0x02200000)
    assert Path(calls[-1][0]).name == ".rush"
    assert sorted(opened.values()) == sorted(set(opened.values())) and set(
        opened.values()
    ) <= set(closed), "a pinned handle was not closed"

    # Error mapping: file/path not found -> path_escape; any other error -> publication_unsupported.
    for error_code, reason_value, code_value, bad, pre_b, access_b in bound_err_cases:
        outcome.update(invalid=True, error=error_code)
        _expect_policy_error(
            code_value,
            reason_value,
            lambda bad=bad, pre_b=pre_b, access_b=access_b: _apply(
                bad,
                [_rec("f1")],
                pre_b,
                inv="i",
                eff="e",
                digest=_hex(81),
                access=access_b,
            ),
        )
        assert not bad.db.exists()
    outcome.update(invalid=False, error=0)
    # A reparse point in the pinned chain is refused as a symlink; no store is published.
    outcome["attributes"] = 0x400 | 0x10
    before_closed = len(closed)
    _expect_policy_error(
        "E_PERMISSION",
        "symlink",
        lambda: _apply(
            rp, [_rec("f1")], pre_r, inv="i", eff="e", digest=_hex(82), access=access_r
        ),
    )
    assert not rp.db.exists() and len(closed) > before_closed


# =============================================================================
# R11: route x mode matrix (G2)
# =============================================================================

READ_ROUTES = ("ask", "recall", "list", "expand", "related", "history", "explain")
MUT_ROUTES = ("write", "edit", "archive", "delete", "promote", "maintain", "link")
PRIMARY_GRANT = {
    "ask": "ask",
    "recall": "ask",
    "related": "ask",
    "explain": "ask",
    "list": "list",
    "expand": "expand",
    "history": "history",
    **{m: "write" for m in MUT_ROUTES},
}
MUT_KIND = {
    "write": "write",
    "edit": "edit",
    "archive": "archive",
    "delete": "delete",
    "promote": "promote",
    "maintain": "maintain",
    "link": "link",
}


@dataclasses.dataclass
class Plan:
    env: Env
    operation: str
    request: dict[str, Any]
    perms: ExecutionPermissions
    top: dict[str, Any]
    code: str
    reason: str | None = None
    effects: str = "none"  # "none" | "commit"
    check: str = "ok"
    overlay: OwnerScope | None = None
    note: str = ""


def _request_for(
    route: str, *, owner: OwnerScope | None = ALICE, apply: bool = True, **extra: Any
) -> dict[str, Any]:
    if route in READ_BUILDERS:
        builder = READ_BUILDERS[route]
        return builder(owner, **extra)
    request = MUTATION_BUILDERS[route](owner, apply=apply)
    request.update(extra)
    return request


def _env_for_route(
    tmp_path: Path, route: str, *, ops: tuple[str, ...] = GRANT_OPS, bob: bool = True
) -> Env:
    return make_env(tmp_path, ops=ops, bob=bob)


def _set_sql(env: Env, sql: str, params: tuple = ()) -> None:
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(sql, params)
        conn.commit()


def _read_ids_for(route: str, result: Any) -> list[str]:
    body = raw(result)
    if route in {"ask", "recall", "list"}:
        return ids(result)
    return [i["reference"]["artifact_id"] for i in body.get("items", [])]


def _plan(route: str, dim: str, value: str, tmp_path: Path, transport: str) -> Plan:
    is_read = route in READ_BUILDERS
    primary = PRIMARY_GRANT[route]
    perms = PERM_NONE if is_read else PERM_W
    top: dict[str, Any] = {}
    env = _env_for_route(tmp_path, route, bob=transport != "cli")

    def base(owner: OwnerScope | None = ALICE, **extra: Any) -> dict[str, Any]:
        return _request_for(route, owner=owner, **extra)

    expected_ok = Plan(
        env, route, base(), perms, top, "OK", effects="none" if is_read else "commit"
    )

    if dim == "access":
        if value == "policy":
            return expected_ok
        if value.startswith("legacy_allowlist"):
            # legacy rows carry no owner, so Bob's rows cannot be told apart from
            # Alice's in a legacy read; seed only the rows the read may return.
            env = make_env(tmp_path / "legacy", mode="legacy", bob=not is_read)
            if value == "legacy_allowlist":
                req = base(
                    None, **({"sources": [SRC]} if is_read or route != "write" else {})
                )
                return Plan(
                    env,
                    route,
                    req,
                    perms,
                    top,
                    "OK",
                    effects="none" if is_read else "commit",
                )
            if value == "legacy_allowlist_nosources":
                if is_read or route != "write":
                    return Plan(
                        env,
                        route,
                        base(None),
                        perms,
                        top,
                        "E_PERMISSION",
                        "policy_missing",
                    )
                return Plan(env, route, base(None), perms, top, "OK", effects="commit")
            assert value == "legacy_allowlist_owner_other"
            assert not is_read
            other = {"sources": [SRC]} if route != "write" else {}
            return Plan(
                env,
                route,
                base(BOB, **other),
                perms,
                top,
                "E_OWNER",
                "owner_not_granted",
            )
        assert value == "overlay"
        oenv, overlay, _store = make_overlay_env(tmp_path / "overlay")
        okw = {"artifact_id": "p1"}
        if route in {"ask", "recall"}:
            req = r_ask(overlay, subjects=["preference"])
        elif route == "list":
            req = r_list(overlay, subjects=["preference"])
        elif route in {"expand", "related", "history", "explain"}:
            req = (
                READ_BUILDERS[route](overlay, **okw)
                if route in {"history", "explain"}
                else READ_BUILDERS[route](overlay, "p1")
            )
        elif route == "write":
            req = m_write(overlay, source=OVERLAY_SOURCE, subject="preference")
        elif route in {"archive", "edit", "promote"}:
            req = MUTATION_BUILDERS[route](
                overlay, artifact_id="p1", subject="preference"
            )
        elif route == "delete":
            req = m_delete(overlay, revisions={"p1": 1}, subject="preference")
        elif route == "link":
            req = m_link(overlay, source_id="p1", target_id="p1")
        else:
            req = m_maintain(overlay, candidate_ids=("p1",))
        if is_read:
            return Plan(
                oenv,
                route,
                req,
                perms,
                top,
                "OK",
                check="overlay_read",
                overlay=overlay,
            )
        if route in {"archive", "delete"}:
            return Plan(
                oenv,
                route,
                req,
                perms,
                top,
                "OK",
                effects="commit",
                check="overlay_commit",
                overlay=overlay,
            )
        return Plan(
            oenv,
            route,
            req,
            perms,
            top,
            "E_OWNER",
            "overlay_requires_preference_route",
            overlay=overlay,
        )

    if dim == "policy_state":
        if value == "ok":
            return expected_ok
        if value == "missing_no_marker":
            env = make_env(tmp_path / "nomarker", mode="legacy")
            if route == "write":
                return Plan(env, route, base(None), perms, top, "OK", effects="commit")
            return Plan(
                env, route, base(None), perms, top, "E_PERMISSION", "policy_missing"
            )
        if value == "missing_marker":
            _auth().policy_path(data_root=env.data_root).unlink()
            return Plan(
                env, route, base(), perms, top, "E_PERMISSION", "policy_missing"
            )
        assert value == "invalid"
        _auth().policy_path(data_root=env.data_root).write_bytes(b"{")
        return Plan(env, route, base(), perms, top, "E_PERMISSION", "policy_invalid")

    if dim == "mode":
        archived_target = "r2" if route in {"ask", "recall", "list"} else "r1"
        if value == "ordinary" or value == "inspect":
            return expected_ok
        if value == "historical_with_grant":
            assert is_read
            _set_sql(
                env,
                "UPDATE memory_artifacts SET archived_at = ? WHERE id = ?",
                (time.time(), archived_target),
            )
            extra: dict[str, Any] = {"archive_mode": "historical"}
            if route in {"ask", "recall"}:
                req = r_ask(ALICE, subjects=["failure"], **extra)
            elif route == "list":
                req = r_list(ALICE, subjects=["failure"], **extra)
            else:
                req = (
                    READ_BUILDERS[route](ALICE, **extra)
                    if route in {"expand", "related"}
                    else READ_BUILDERS[route](ALICE, "r1", **extra)
                )
            return Plan(env, route, req, perms, top, "OK", check="historical_present")
        if value == "historical_without_grant":
            assert is_read
            env = make_env(tmp_path / "nohist", ops=NO_HISTORY_OPS)
            extra = {"archive_mode": "historical"}
            if route in {"ask", "recall"}:
                req = r_ask(ALICE, **extra)
            elif route == "list":
                req = r_list(ALICE, **extra)
            else:
                req = (
                    READ_BUILDERS[route](ALICE, **extra)
                    if route in {"expand", "related"}
                    else READ_BUILDERS[route](ALICE, "r1", **extra)
                )
            if route == "history":
                req = r_history(ALICE)
            return Plan(
                env, route, req, perms, top, "E_PERMISSION", "operation_not_granted"
            )
        assert value == "archive_mode_on_mutation" and not is_read
        return Plan(env, route, base(archive_mode="historical"), perms, top, "E_INPUT")

    if dim == "representation":
        if is_read and route in {"expand", "history"}:
            return Plan(
                env,
                route,
                base(representation="base64" if value == "base64" else "utf8"),
                perms,
                top,
                "OK",
                check=f"repr_{value}",
            )
        return Plan(env, route, base(representation="base64"), perms, top, "E_INPUT")

    if dim == "retrieval":
        if is_read and route in {"ask", "recall", "list"}:
            if value == "lexical":
                return Plan(env, route, base(retrieval="lexical"), perms, top, "OK")
            if value == "hybrid_no_network":
                return Plan(
                    env, route, base(retrieval="hybrid"), PERM_NONE, top, "E_PERMISSION"
                )
            assert value == "hybrid_network_no_engine"
            return Plan(
                env,
                route,
                base(retrieval="hybrid"),
                ExecutionPermissions(network=True),
                top,
                "OK",
                check="hybrid_lexical",
            )
        return Plan(env, route, base(retrieval="hybrid"), perms, top, "E_INPUT")

    if dim == "store":
        if value == "present":
            return expected_ok
        if value == "absent":
            env = make_env(tmp_path / "absent", seeded=False, create_store=False)
            if is_read:
                if route in {"ask", "recall", "list"}:
                    return Plan(
                        env, route, base(), perms, top, "OK", check="empty_page"
                    )
                if route == "explain":
                    return Plan(
                        env,
                        route,
                        r_explain(ALICE, artifact_id=None, query="needle"),
                        perms,
                        top,
                        "OK",
                        check="explain_no_matches",
                    )
                return Plan(env, route, base(), perms, top, "E_NOT_VISIBLE")
            if route == "write":
                return Plan(
                    env,
                    route,
                    base(),
                    perms,
                    top,
                    "OK",
                    effects="commit",
                    check="store_created",
                )
            return Plan(env, route, base(), perms, top, "E_NOT_VISIBLE")
        assert value == "old_schema"
        with contextlib.closing(sqlite3.connect(env.db)) as conn:
            for table in ("memory_artifacts", "memory_artifact_versions"):
                for column in ("payload_hash", "payload_hash_origin"):
                    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()
        if is_read:
            return Plan(
                env, route, base(), perms, top, "E_MIGRATION", "migration_required"
            )
        return Plan(
            env, route, base(), perms, top, "OK", effects="commit", check="migrated"
        )

    if dim == "apply":
        if not is_read:
            if value == "preview":
                if route == "link":
                    # brief 72-T06 3.2 (D2): link has no preview, apply not True is E_INPUT
                    return Plan(
                        env, route, base(apply=False), PERM_NONE, top, "E_INPUT"
                    )
                return Plan(
                    env, route, base(apply=False), PERM_NONE, top, "OK", check="preview"
                )
            return expected_ok
        # brief 72-T06 5.1 apply rows: a read carrying `apply` is E_INPUT (unknown key)
        request = base()
        request["apply"] = value == "apply"
        return Plan(env, route, request, perms, top, "E_INPUT")

    if dim == "cache_write":
        if is_read:
            if value == "on":
                return Plan(
                    env, route, base(), PERM_W, top, "OK", check="telemetry_written"
                )
            return Plan(env, route, base(), PERM_NONE, top, "OK", check="no_telemetry")
        if value == "on":
            return expected_ok
        return Plan(
            env, route, base(), PERM_NONE, top, "E_PERMISSION", "cache_write_required"
        )

    if dim == "grant_ops":
        if value == "exact":
            return expected_ok
        reduced = tuple(o for o in GRANT_OPS if o != primary)
        env = make_env(tmp_path / "reduced", ops=reduced)
        return Plan(
            env, route, base(), perms, top, "E_PERMISSION", "operation_not_granted"
        )

    if dim == "row_state":
        return _row_state_plan(route, value, env, perms, top)

    if dim == "ack":
        return Plan(env, route, base(ack=True), perms, top, "E_INPUT")

    if dim == "capability_ids":
        return Plan(env, route, base(granted_ids=["r1"]), perms, top, "E_INPUT")
    raise AssertionError((route, dim, value))


def _row_state_plan(
    route: str, value: str, env: Env, perms: ExecutionPermissions, top: dict[str, Any]
) -> Plan:
    is_read = route in READ_BUILDERS
    historical = value.endswith("_historical")
    state = value.removesuffix("_historical")
    if state == "archived":
        _set_sql(
            env,
            "UPDATE memory_artifacts SET archived_at = ? WHERE id = 'r1'",
            (time.time(),),
        )
    elif state == "expired":
        _set_sql(
            env,
            "UPDATE memory_artifacts SET expires_at = ?, expired_at = ?, expired_by = 'test' WHERE id = 'r1'",
            (time.time() - 100, time.time() - 50),
        )
    elif state in {"rejected", "pending"}:
        _set_sql(
            env,
            "UPDATE memory_artifacts SET applicability = ? WHERE id = 'r1'",
            (state,),
        )
    elif state == "tampered":
        _set_sql(
            env,
            "UPDATE memory_artifacts SET content = ? WHERE id = 'r1'",
            (json.dumps({"text": "needle tampered bytes"}),),
        )
    extra: dict[str, Any] = {"archive_mode": "historical"} if historical else {}
    if is_read:
        if route in {"ask", "recall"}:
            req = r_ask(ALICE, **extra)
        elif route == "list":
            req = r_list(ALICE, subjects=["domain_knowledge"], **extra)
        else:
            req = READ_BUILDERS[route](ALICE, "r1", **extra)
        if historical:
            return Plan(
                env, route, req, perms, top, "OK", check=f"state_historical:{state}"
            )
        if state in {"rejected", "pending"}:
            if route == "list":
                return Plan(
                    env, route, req, perms, top, "OK", check=f"state_listed:{state}"
                )
            return Plan(env, route, req, perms, top, "OK", check="state_absent")
        if route in {"ask", "recall", "list"}:
            return Plan(env, route, req, perms, top, "OK", check="state_absent")
        return Plan(env, route, req, perms, top, "E_NOT_VISIBLE")
    # mutations
    if state in {"archived", "expired"}:
        if route == "archive":
            req = m_archive(archived=False)
            return (
                Plan(env, route, req, perms, top, "OK", effects="commit")
                if state == "archived"
                else Plan(env, route, req, perms, top, "E_NOT_VISIBLE")
            )
        if route in {"edit", "promote"}:
            return Plan(
                env,
                route,
                _request_for(route),
                perms,
                top,
                "E_NOT_VISIBLE",
                check="either_visibility_or_version",
            )
    if state in {"rejected", "pending"} and route == "edit":
        req = m_edit(correction={"kind": "correct", "reason": "re-review"})
        return Plan(env, route, req, perms, top, "OK", effects="commit")
    if state == "tampered" and route == "promote":
        # brief 72-T06 3.9: promote requires the row visible in ordinary mode, and an
        # integrity-failed row is not visible, so the denial is E_NOT_VISIBLE.
        return Plan(env, route, _request_for(route), perms, top, "E_NOT_VISIBLE")
    raise AssertionError(f"no row-state cell for {route} {value}")


def _row_states_for(route: str) -> tuple[str, ...]:
    """The `row_state` values the brief defines for each route."""
    if route in {"ask", "recall", "list"}:
        return (
            "archived",
            "archived_historical",
            "expired",
            "expired_historical",
            "rejected",
            "pending",
            "tampered",
            "tampered_historical",
        )
    if route in {"expand", "history"}:
        return (
            "archived",
            "archived_historical",
            "expired",
            "expired_historical",
            "tampered",
            "tampered_historical",
        )
    if route in {"related", "explain"}:
        return (
            "archived",
            "archived_historical",
            "expired",
            "expired_historical",
            "tampered",
        )
    if route == "edit":
        return ("archived", "expired", "rejected", "pending")
    if route == "archive":
        return ("archived",)
    if route == "promote":
        return ("archived", "expired", "tampered")
    return ()


def _matrix_cells() -> list[Any]:
    cells: list[Any] = []

    def add(transport: str, route: str, dim: str, value: str) -> None:
        cells.append(
            pytest.param(
                transport, route, dim, value, id=f"{transport}.{route}-{dim}-{value}"
            )
        )

    for transport in ("inproc", "mcp"):
        for route in (*READ_ROUTES, *MUT_ROUTES):
            is_read = route in READ_ROUTES
            for value in (
                "policy",
                "legacy_allowlist",
                "legacy_allowlist_nosources",
                "overlay",
            ):
                add(transport, route, "access", value)
            if not is_read:
                add(transport, route, "access", "legacy_allowlist_owner_other")
            for value in ("ok", "missing_no_marker", "missing_marker", "invalid"):
                add(transport, route, "policy_state", value)
            if is_read:
                add(
                    transport,
                    route,
                    "mode",
                    "ordinary" if route != "list" else "inspect",
                )
                add(transport, route, "mode", "historical_with_grant")
                add(transport, route, "mode", "historical_without_grant")
            else:
                add(transport, route, "mode", "archive_mode_on_mutation")
            for value in ("base64", "utf8"):
                add(transport, route, "representation", value)
            for value in ("lexical", "hybrid_no_network", "hybrid_network_no_engine"):
                add(transport, route, "retrieval", value)
            for value in ("present", "absent", "old_schema"):
                add(transport, route, "store", value)
            for value in ("preview", "apply"):
                add(transport, route, "apply", value)
            for value in ("on", "off"):
                add(transport, route, "cache_write", value)
            for value in ("exact", "missing_one"):
                add(transport, route, "grant_ops", value)
            for value in _row_states_for(route):
                add(transport, route, "row_state", value)
            add(transport, route, "ack", "ack")
            add(transport, route, "capability_ids", "granted_ids")
    return cells


def _invoke(transport: str, plan: Plan) -> Any:
    if transport == "inproc":
        return call(
            plan.env, plan.operation, plan.request, perms=plan.perms, **plan.top
        )
    cache = plan.perms.cache_write
    top = dict(plan.top)
    if plan.perms.network:
        top["allow_network"] = True
    return mcp_call(plan.env, plan.operation, plan.request, cache_write=cache, **top)


def _telemetry(env: Env) -> Path:
    return env.root / ".rush" / "telemetry" / "tokens.db"


def _engine_cell(
    transport: str, route: str, dim: str, value: str, tmp_path: Path
) -> None:
    plan = _plan(route, dim, value, tmp_path, transport)
    env = plan.env
    before = snapshot(env) if env.root.exists() else None
    receipts_before = len(all_receipts(env)) if env.db.exists() else 0
    result = _invoke(transport, plan)
    body = (
        assert_v2_envelope(result, route, plan.code)
        if plan.check != "either_visibility_or_version"
        else assert_v2_envelope(result, route)
    )
    if plan.check == "either_visibility_or_version":
        assert body["code"] in {"E_NOT_VISIBLE", "E_VERSION"}, dump(body)
    if plan.reason is not None:
        assert reason(result) == plan.reason, dump(body)
    if plan.code != "OK":
        assert (
            body["items"] == []
            and body["complete"] is False
            and body["next_cursor"] is None
        )
        if before is not None:
            assert snapshot(env) == before, (
                f"{dim}={value}: a refused call changed state"
            )
        return
    _check_success(plan, route, dim, value, result, before, receipts_before)


def _check_success(
    plan: Plan,
    route: str,
    dim: str,
    value: str,
    result: Any,
    before: dict[str, Any] | None,
    receipts_before: int,
) -> None:
    env, body, check = plan.env, raw(result), plan.check
    is_read = route in READ_BUILDERS
    owner_dump = dump(body)
    if check == "ok" and is_read:
        assert not any(b in owner_dump for b in _bob_ids())
        if route in {"ask", "recall", "list"}:
            assert set(ids(result)) <= _alice_ids() and ids(result)
        if dim != "cache_write":
            assert snapshot(env) == before
        return
    if check == "overlay_read":
        assert dump(body).count("p1") >= 1 or route in {"history", "explain"}
        assert plan.overlay is not None
        assert all(
            i["reference"]["owner_scope"]["id"] == plan.overlay.id
            for i in body["items"]
        )  # type: ignore[union-attr]
        return
    if check == "overlay_commit":
        overlay_db = env.data_root / "user" / ".rush" / "memory.db"
        assert overlay_db.exists()
        with contextlib.closing(sqlite3.connect(overlay_db)) as conn:
            kinds = {
                r[0]
                for r in conn.execute(
                    "SELECT kind FROM mutation_receipts WHERE invocation_id IS NOT NULL"
                )
            }
        assert kinds == {route}
        assert len(v2_receipts(env)) == 0  # nothing leaked into the project store
        return
    if check in {"state_absent"}:
        assert "r1" not in ids(result)
        return
    if check.startswith("state_listed"):
        assert "r1" in ids(result)
        item = next(i for i in body["items"] if i["reference"]["artifact_id"] == "r1")
        assert item["reason_codes"] and item["usable_as_current"] is False
        return
    if check.startswith("state_historical"):
        state = check.split(":", 1)[1]
        if route in {"ask", "recall", "list"}:
            assert "r1" in ids(result)
            item = next(
                i for i in body["items"] if i["reference"]["artifact_id"] == "r1"
            )
            if state in {"archived", "expired"}:
                assert state in item["reason_codes"]
            if state == "tampered":
                assert item["reference"]["integrity"] == "mismatch"
        elif route == "history":
            assert body["versions"] and body["versions"][0]["reference"][
                "integrity"
            ] == ("mismatch" if state == "tampered" else "verified")
        return
    if check == "historical_present":
        return
    if check in {"repr_base64", "repr_utf8"}:
        item = body["versions"][0] if route == "history" else body["items"][0]
        key = "content_base64" if check == "repr_base64" else "content_utf8"
        other = "content_utf8" if check == "repr_base64" else "content_base64"
        assert key in item or key in dump(item), dump(item)
        assert other not in item
        return
    if check == "hybrid_lexical":
        assert body["items"], (
            "hybrid without an engine falls back to a lexical-labelled result"
        )
        return
    if check == "empty_page":
        assert body["items"] == [] and body["complete"] is True
        assert not env.db.exists()
        return
    if check == "explain_no_matches":
        assert "no_matches" in body["unknowns"] and not env.db.exists()
        return
    if check == "preview":
        assert "preview" in body["data"] and snapshot(env) == before
        return
    if check == "telemetry_written":
        assert _telemetry(env).exists()
        return
    if check == "no_telemetry":
        assert not _telemetry(env).exists()
        return
    if check == "store_created":
        assert env.db.exists() and len(v2_receipts(env)) == 1
        return
    if check == "migrated":
        assert len(v2_receipts(env)) == 1
        return
    if not is_read and plan.effects == "commit":
        receipts = all_receipts(env)[receipts_before:]
        v2 = [r for r in v2_receipts(env)]
        assert len(v2) >= 1 and v2[-1]["kind"] == MUT_KIND[route], dump(body)
        assert len(receipts) >= 1
        return


# --- B: operations that are not v2 operations ------------------------------------

NON_V2_OPERATIONS = (
    "consolidate",
    "verify_attempt",
    "prepare",
    "resume",
    "intent",
    "recipe",
    "plan_checks",
    "last_success_diagnose",
    "handoff",
    "receive",
    "preference",
)


def _cell_non_v2(operation: str, transport: str, tmp_path: Path) -> None:
    env = make_env(tmp_path)
    before = snapshot(env)
    request = {"schema_version": 2}
    result = (
        call(env, operation, request, perms=PERM_W)
        if transport == "inproc"
        else mcp_call(env, operation, request, cache_write=True)
    )
    body = assert_v2_envelope(result, operation, "E_INPUT")
    assert body["data"]["details"][0]["loc"] == ["request", "schema_version"], dump(
        body
    )
    only_zero_effects(env, before, operation)


def _cell_capsule(transport: str, tmp_path: Path) -> None:
    """73-T09/CODEC owns `capsule`; until it lands the operation name itself is rejected."""
    env = make_env(tmp_path)
    before = snapshot(env)
    if transport == "inproc":
        result = call(env, "capsule", {"schema_version": 2}, perms=PERM_W)
        assert result["status"] == "error"
        assert "capsule" in result["summary"]
    else:
        result = mcp_call(env, "capsule", {"schema_version": 2}, cache_write=True)
        assert code(result) == "E_INPUT"
        assert raw(result)["data"]["details"][0]["loc"][-1] == "operation"
    only_zero_effects(env, before, "capsule")


# --- C: restricted bridge cells in the matrix grammar ------------------------------


def _cell_bridge(operation: str, tmp_path: Path) -> None:
    root, _store, session, capability = _bridge(tmp_path)
    before = digest_tree(root)
    handler = _handler(root, session.session_id, capability)
    request: dict[str, Any] = {
        "schema_version": 2,
        "artifact_id": "a1",
        "artifact_version": 1,
    }
    out = handler(operation, request)
    if operation in {"receive", "expand", "related", "resume"}:
        assert out["code"] == "E_INPUT" and out["data"].get("field") == "schema_version"
    else:
        assert out["code"] == "E_PERMISSION"
    assert digest_tree(root) == before


# --- D: no-field routes: output unchanged by Bob's v2 write ------------------------


def _read_visible_rows(env: Env) -> Any:
    """`retrieval.read_visible` for Alice's `ask` access over the fixture subject."""
    from rush.memory.retrieval import MemoryAccess, read_visible

    if env.mode == "legacy":
        access: MemoryAccess | None = MemoryAccess.legacy(
            env.root,
            [SRC],
            owner_scope=legacy_owner_scope(env.root),
            operation="ask",
            data_root=env.data_root,
        )
    else:
        access = MemoryAccess.resolve(
            env.root,
            operation="ask",
            owner_scope=ALICE,
            requested_sources=(SRC,),
            data_root=env.data_root,
        )
    assert access is not None
    return read_visible(env.root, [("domain_knowledge", "needle")], access=access)


def _no_field_routes() -> dict[str, Any]:
    def tool(**kw: Any) -> Any:
        return lambda env: stable(
            MemoryTool().run(env.root, owner_scope=ALICE, permissions=PERM_NONE, **kw)
        )

    def store_read(fn: Any) -> Any:
        return lambda env: fn(TypedArtifactStore(env.root))

    def cli_ask(env: Env) -> Any:
        parsed = cli_json(
            env.root,
            ["memory", "ask", "domain_knowledge", "needle", "--session", SRC, "--json"],
        )[1]
        # duration_ms is wall-clock and differs between two runs.
        return stable(parsed) if isinstance(parsed, dict) else parsed

    return {
        "v1_ask": tool(
            operation="ask",
            subject="domain_knowledge",
            query="needle",
            request={"view": "compact"},
        ),
        "v1_recall": tool(
            operation="recall",
            subject="domain_knowledge",
            query="needle",
            request={"view": "compact"},
        ),
        "v1_list": tool(
            operation="list",
            subject="domain_knowledge",
            query="needle",
            request={"view": "compact"},
        ),
        "v1_expand": tool(operation="expand", request={"id": "r1", "version": 1}),
        "v1_related": tool(operation="related", request={"id": "r1", "version": 1}),
        "v1_prepare": tool(
            operation="prepare",
            request={"task": "t", "conditions": {}, "query": "needle"},
        ),
        "v1_plan_checks": tool(
            operation="plan_checks",
            request={
                "changed_targets": [{"id": "t1"}],
                "required_checks": [{"id": "c1"}],
                "environment": {},
            },
        ),
        "v1_intent_check": tool(
            operation="intent", request={"action": "check", "intent_id": "none"}
        ),
        "v1_recipe_resolve": tool(
            operation="recipe", request={"action": "resolve", "recipe_id": "none"}
        ),
        "v1_last_success": tool(
            operation="last_success_diagnose",
            request={"behavior_id": "b1", "conditions": {}},
        ),
        "store_get_current": store_read(
            lambda s: dump(dataclasses.asdict(s.get_current("r1")))
        ),
        "store_search_candidates": store_read(
            lambda s: [
                r["id"]
                for r in s.search_candidates(
                    "domain_knowledge",
                    "needle",
                    source_allowlist=(SRC,),
                    owner_scope=ALICE,
                )
            ]
        ),
        "read_visible": lambda env: dump(
            [[row.id for row in rows] for rows in _read_visible_rows(env)]
        ),
        "cli_ask": cli_ask,
    }


NO_FIELD = _no_field_routes()


def _cell_no_field(route: str, tmp_path: Path) -> None:
    env = make_env(tmp_path)
    first = NO_FIELD[route](env)
    written = apply_call(
        env,
        "write",
        m_write(owner=BOB, inv="inv-bob", eff="eff-bob", text="needle bob extra"),
    )
    assert code(written) == "OK"
    second = NO_FIELD[route](env)
    assert dump(second) == dump(first), (
        f"{route}: Bob's v2 write changed Alice's output"
    )


def _shape(value: Any) -> Any:
    """A value reduced to its structure (keys and scalar types), for outputs that carry
    fresh ids or timestamps on every run."""
    if isinstance(value, dict):
        return {k: _shape(v) for k, v in sorted(value.items()) if k != "duration_ms"}
    if isinstance(value, list):
        return [_shape(value[0])] if value else []
    return type(value).__name__


def _cell_cli_positional(leaf: str, tmp_path: Path) -> None:
    """CLI positional leaves have no `request` field: their output is unchanged by Bob's
    v2 `write` apply (byte-identical for the reads; same structure for the leaves that
    mint a fresh id or timestamp on every call)."""
    env = make_env(tmp_path)
    content = '{"text": "needle cli leaf"}'
    args = {
        "ask": [
            "memory",
            "ask",
            "domain_knowledge",
            "needle",
            "--session",
            SRC,
            "--json",
        ],
        "recall": [
            "memory",
            "recall",
            "domain_knowledge",
            "needle",
            "--session",
            SRC,
            "--json",
        ],
        "list": [
            "memory",
            "list",
            "domain_knowledge",
            "needle",
            "--session",
            SRC,
            "--json",
        ],
        "write": [
            "memory",
            "write",
            "domain_knowledge",
            SRC,
            "--content",
            content,
            "--json",
        ],
        "promote": [
            "memory",
            "promote",
            "domain_knowledge",
            SRC,
            "--content",
            content,
            "--json",
        ],
        "maintain": ["memory", "maintain", "--task", "staleness_sweep", "--json"],
    }[leaf]
    status_a, first = cli_json(env.root, args)
    assert isinstance(first, dict), (leaf, first)
    written = apply_call(env, "write", m_write(owner=BOB, inv="inv-bob", eff="eff-bob"))
    assert code(written) == "OK", dump(raw(written))
    status_b, second = cli_json(env.root, args)
    assert status_a == status_b
    if leaf in {"ask", "recall", "list"}:
        assert _normalize(env, stable(first)) == _normalize(env, stable(second))
    else:
        assert _shape(first) == _shape(second)


# --- G2a intersections -------------------------------------------------------------


def test_t06_g2a_intersections(tmp_path: Path) -> None:
    # legacy-with-policy: a top-level session_allowlist beside v2 is E_INPUT.
    env = make_env(tmp_path / "a")
    snap = snapshot(env)
    mixed = call(env, "list", r_list(), session_allowlist=[SRC])
    assert_v2_envelope(mixed, "list", "E_INPUT")
    only_zero_effects(env, snap, "legacy+policy")

    # historical + compound grant: {list, history} -> OK; {list} -> operation_not_granted.
    both = make_env(tmp_path / "b", ops=("list", "history"))
    assert code(call(both, "list", r_list(archive_mode="historical"))) == "OK"
    only_list = make_env(tmp_path / "c", ops=("list",))
    denied = call(only_list, "list", r_list(archive_mode="historical"))
    assert code(denied) == "E_PERMISSION" and reason(denied) == "operation_not_granted"

    # no-store + denial/admission: nothing is created.
    nostore = make_env(tmp_path / "d", seeded=False, create_store=False)
    revoke(nostore, ALICE)
    snap = snapshot(nostore)
    gone = call(nostore, "list", r_list())
    assert code(gone) == "E_PERMISSION" and reason(gone) == "revoked"
    only_zero_effects(nostore, snap, "revoked absent store")
    tiny = make_env(tmp_path / "e", seeded=False, create_store=False)
    snap = snapshot(tiny)
    assert code(call(tiny, "list", r_list(max_bytes=1))) == "E_INPUT"
    only_zero_effects(tiny, snap, "admission on absent store")

    # overlay + revocation.
    oenv, overlay, _store = make_overlay_env(tmp_path / "f")
    _auth().revoke_memory_scope(
        grant_id=oenv.grants["overlay"]["grant_id"],
        expected_policy_revision=_revision(oenv.data_root),
        consent=True,
        data_root=oenv.data_root,
    )
    revoked = call(oenv, "list", r_list(overlay, subjects=["preference"]))
    assert code(revoked) == "E_PERMISSION" and reason(revoked) == "revoked"

    # cache-write + ask-only: a hybrid read never opens a writable store or embeds.
    ask_only = make_env(tmp_path / "g", ops=("ask",))
    snap = snapshot(ask_only)
    result = call(
        ask_only,
        "ask",
        r_ask(retrieval="hybrid"),
        perms=ExecutionPermissions(cache_write=True, network=True),
    )
    assert code(result) in {"OK", "E_PERMISSION"}
    with contextlib.closing(sqlite3.connect(ask_only.db)) as conn:
        tables = {
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        if "memory_embeddings" in tables:
            assert (
                conn.execute("SELECT COUNT(*) FROM memory_embeddings").fetchone()[0]
                == 0
            )


# --- E: store seams x store state x access form ------------------------------------

SEAMS = (
    "version_history_readonly",
    "preview_import_records",
    "apply_import_records",
    "find_import_effect_readonly",
    "write_v2_receipt",
    "upgrade",
)
STORE_STATES = ("present", "absent", "old_schema")
ACCESS_FORMS = ("policy", "legacy_allowlist", "overlay")


def _seam_env(tmp_path: Path, state: str, form: str) -> tuple[Env, Path]:
    """`(env, storage_root)` for a seam cell: the store is present, absent or old-schema."""
    import shutil

    if form == "overlay":
        env, overlay, _store = make_overlay_env(tmp_path / "ov")
        storage = env.data_root / "user"
        # An import into the overlay store needs a writer grant for its literal source.
        env.grants["overlay"] = grant(
            env,
            env.data_root,
            overlay,
            sources=(OVERLAY_SOURCE, IMPORT_SOURCE),
            ops=("overlay_read", "list", "expand", "history", "write"),
        )
        if state == "absent":
            # The policy file lives in the same `.rush`: remove only the store files.
            for name in ("memory.db", "memory.db-wal", "memory.db-shm"):
                (storage / ".rush" / name).unlink(missing_ok=True)
            shutil.rmtree(storage / ".rush" / "cache", ignore_errors=True)
    elif form == "legacy_allowlist":
        env = _import_env(tmp_path / "lg", mode="legacy", store=state != "absent")
        storage = env.root
        if env.store is not None:
            seed(env.store, bob=False, legacy=True)
    else:
        env = _import_env(tmp_path / "po", store=state != "absent")
        storage = env.root
        if env.store is not None:
            seed(env.store)
    if state == "old_schema":
        db = storage / ".rush" / "memory.db"
        with contextlib.closing(sqlite3.connect(db)) as conn:
            for table in ("memory_artifacts", "memory_artifact_versions"):
                for column in ("payload_hash", "payload_hash_origin"):
                    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()
    return env, storage


def _seam_access(env: Env, form: str, kind: str) -> Any:
    """The access one seam is called with: `history` (read) or `import` (writer)."""
    from rush.memory.retrieval import MemoryAccess

    overlay = _auth().user_overlay_owner_scope(data_root=env.data_root)
    if kind == "import":
        return (
            _import_access(env, form, None) if form == "overlay" else _write_access(env)
        )
    if form == "overlay":
        got = MemoryAccess.resolve(
            env.root,
            operation="history",
            overlay=True,
            owner_scope=overlay,
            requested_sources=(OVERLAY_SOURCE,),
            data_root=env.data_root,
        )
    elif form == "legacy_allowlist":
        got = MemoryAccess.legacy(
            env.root,
            [SRC],
            owner_scope=legacy_owner_scope(env.root),
            operation="history",
            data_root=env.data_root,
        )
    else:
        got = MemoryAccess.resolve(
            env.root,
            operation="history",
            owner_scope=ALICE,
            requested_sources=(SRC,),
            data_root=env.data_root,
        )
    assert got is not None
    return got


def _seam_cells() -> list[Any]:
    return [
        pytest.param(s, st, f, id=f"seam.{s}-store-{st}-access-{f}")
        for s in SEAMS
        for st in STORE_STATES
        for f in ACCESS_FORMS
    ]


def _cell_seam(seam: str, state: str, form: str, tmp_path: Path) -> None:
    env, storage = _seam_env(tmp_path, state, form)
    db = storage / ".rush" / "memory.db"
    before_db = sha_file(db) if db.exists() else None
    tree_before = _tree(storage)
    probe_id = "p1" if form == "overlay" else "r1"
    if seam == "version_history_readonly":
        assert hasattr(TypedArtifactStore, "version_history_readonly")
        view, view_state = TypedArtifactStore.open_readonly_view(storage)
        if state == "present":
            assert view is not None and view_state is None
            try:
                access = _seam_access(env, form, "history")
                versions = view.version_history_readonly(probe_id, access=access)
                assert [v["reference"]["artifact_version"] for v in versions] == [1]
            finally:
                view.close()
            writable = TypedArtifactStore(storage)
            with pytest.raises(TypeError):
                writable.version_history_readonly(probe_id, access=access)
        else:
            assert view is None and view_state == (
                None if state == "absent" else "migration_required"
            )
        if state != "present":
            assert _tree(storage) == tree_before
    elif seam == "preview_import_records":
        preview = _preview(env, [_rec("f1")], access=_seam_access(env, form, "import"))
        assert (
            preview["store_state"]
            == {
                "present": "current",
                "absent": "absent",
                "old_schema": "migration_required",
            }[state]
        )
        if state != "present":
            assert preview["store_revision"] == 0 and preview["expected_versions"] == {}
        assert _tree(storage) == tree_before
        assert sha_file(db) == before_db if db.exists() else not db.exists()
    elif seam == "apply_import_records":
        acc = _seam_access(env, form, "import")
        pre = _preview(env, [_rec("f1")], access=acc)
        if state == "old_schema":
            from rush.memory.store import MemoryMigrationRequiredError

            with pytest.raises(MemoryMigrationRequiredError):
                _apply(
                    env,
                    [_rec("f1")],
                    pre,
                    inv="i",
                    eff="e",
                    digest=_hex(90),
                    access=acc,
                )
            assert sha_file(db) == before_db
        else:
            res = _apply(
                env, [_rec("f1")], pre, inv="i", eff="e", digest=_hex(90), access=acc
            )
            assert find_key(res, "mappings")
            assert db.exists()
            with contextlib.closing(sqlite3.connect(db)) as conn:
                assert (
                    conn.execute(
                        "SELECT COUNT(*) FROM memory_artifacts WHERE trust_tier = 'IMPORTED'"
                    ).fetchone()[0]
                    == 1
                )
    elif seam == "find_import_effect_readonly":
        acc = _seam_access(env, form, "import")
        found = TypedArtifactStore.find_import_effect_readonly(
            invocation_id="i", effect_id="e", request_digest=_hex(91), access=acc
        )
        assert found == (
            {"state": "absent"}
            if state == "present"
            else {
                "state": "unavailable",
                "store_state": "absent" if state == "absent" else "migration_required",
            }
        )
        assert _tree(storage) == tree_before
    elif seam == "write_v2_receipt":
        # The writable constructor creates an absent store and migrates an old one.
        store = TypedArtifactStore(storage)
        with store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            store._write_v2_receipt(
                conn,
                invocation_id="i",
                effect_id="e",
                request_digest=_hex(92),
                artifact_id=None,
                kind="write",
                revision=None,
                payload={"x": 1},
            )
            conn.commit()
        with contextlib.closing(sqlite3.connect(db)) as conn:
            assert (
                conn.execute(
                    "SELECT COUNT(*) FROM mutation_receipts WHERE invocation_id = 'i'"
                ).fetchone()[0]
                == 1
            )
    else:
        access = _seam_access(env, form, "import")
        migrated = TypedArtifactStore.upgrade(storage, cache_write=True, access=access)
        assert isinstance(migrated, int)
        if state == "absent":
            assert migrated == 0 and not db.exists()
        else:
            cols = {
                r[1]
                for r in sqlite3.connect(db).execute(
                    "PRAGMA table_info(mutation_receipts)"
                )
            }
            assert {"invocation_id", "effect_id", "request_digest"} <= cols
        with pytest.raises(ValueError):
            TypedArtifactStore.upgrade(storage, cache_write=False, access=access)


def _import_access(env: Env, form: str, default: Any) -> Any:
    if form != "overlay":
        return default
    from rush.memory.retrieval import MemoryAccess

    overlay = _auth().user_overlay_owner_scope(data_root=env.data_root)
    got = MemoryAccess.resolve(
        env.root,
        operation="write",
        apply=True,
        overlay=True,
        owner_scope=overlay,
        requested_sources=(OVERLAY_SOURCE,),
        data_root=env.data_root,
    )
    assert got is not None
    return got


# =============================================================================
# R4 (cont.): content-update sites keep event identity immutable
# =============================================================================


def _event_row_env(tmp_path: Path) -> Env:
    env = make_env(tmp_path, seeded=False)
    assert env.store is not None
    project_id, worktree_id = _ids_of(env)
    put(
        env.store,
        "ev",
        ALICE,
        content={
            "project_id": project_id,
            "worktree_id": worktree_id,
            "task_id": "t1",
            "event_id": "e1",
            "text": "original",
        },
    )
    return env


_IMMUTABLE_SITES = [
    pytest.param("edit", id="store.py:1737"),
    pytest.param("update_content", id="store.py:2817"),
    pytest.param("promote", id="store.py:3091"),
    pytest.param("migration", id="migration.py:131"),
    pytest.param("unrelated", id="unrelated_content_edit"),
]


@pytest.mark.parametrize("site", _IMMUTABLE_SITES)
def test_t06_event_identity_immutable_every_site(site: str, tmp_path: Path) -> None:
    from rush.memory.authorization import MemoryPolicyError

    env = _event_row_env(tmp_path)
    store = env.store
    assert store is not None
    original = json.loads(
        table_rows(env, "memory_artifacts", "id = 'ev'")[0]["content"]
    )
    changed = {**original, "event_id": "e-changed"}
    before_versions = version_numbers(env, "ev")
    if site == "edit":
        result = apply_call(env, "edit", m_edit(artifact_id="ev", content=changed))
        assert (
            code(result) == "E_INPUT" and reason(result) == "event_identity_immutable"
        ), dump(raw(result))
    elif site == "update_content":
        with pytest.raises(MemoryPolicyError) as caught:
            store.update_content("ev", changed, expected_version=1)
        assert (caught.value.code, caught.value.reason) == (
            "E_INPUT",
            "event_identity_immutable",
        )
    elif site == "promote":
        # Promotion re-sanitizes persisted content: a secret-shaped event id would be
        # redacted, which would change the event identity -- refused instead.
        secret_event = {**original, "event_id": "AKIAIOSFODNN7EXAMPLE"}
        with contextlib.closing(sqlite3.connect(env.db)) as conn:
            conn.execute("DROP TRIGGER IF EXISTS memory_event_identity_immutable")
            conn.execute("DROP INDEX IF EXISTS idx_memory_event_identity")
            conn.execute(
                "UPDATE memory_artifacts SET content = ? WHERE id = 'ev'",
                (json.dumps(secret_event),),
            )
            conn.commit()
        TypedArtifactStore(env.root)  # the constructor recreates trigger and index
        before_content = table_rows(env, "memory_artifacts", "id = 'ev'")[0]["content"]
        with pytest.raises(MemoryPolicyError) as caught:
            store.promote("ev", user_stated=True, owner_scope=ALICE)
        assert (caught.value.code, caught.value.reason) == (
            "E_INPUT",
            "event_identity_immutable",
        )
        assert (
            table_rows(env, "memory_artifacts", "id = 'ev'")[0]["content"]
            == before_content
        )
        assert version_numbers(env, "ev") == before_versions
        return
    elif site == "migration":
        from rush.memory import migration

        lg = make_env(tmp_path / "legacy", mode="legacy", seeded=False)
        assert lg.store is not None
        store, env = lg.store, lg
        created = migration.write_if_new(
            store,
            family="memory",
            subject="domain_knowledge",
            content={
                "project_id": "p",
                "worktree_id": "w",
                "task_id": "t",
                "event_id": "origin-e",
                "text": "origin",
            },
            source=SRC,
            origin_kind="t06-test",
            origin_id="o1",
        )
        assert created is not None
        with pytest.raises(MemoryPolicyError) as caught:
            migration.replace_origin_content(
                store,
                "t06-test",
                "o1",
                {
                    "project_id": "p",
                    "worktree_id": "w",
                    "task_id": "t",
                    "event_id": "origin-changed",
                    "text": "origin",
                },
            )
        assert (caught.value.code, caught.value.reason) == (
            "E_INPUT",
            "event_identity_immutable",
        )
        assert (
            json.loads(
                table_rows(env, "memory_artifacts", "id = ?", (created.id,))[0][
                    "content"
                ]
            )["event_id"]
            == "origin-e"
        )
        return
    else:
        # Guard G-e: existing store seam only, so the case passes at HEAD and fails
        # when `edit` keeps the old row content.
        edited = store.edit(
            "ev",
            {**original, "text": "only the text changed"},
            expected_version=1,
            scope="domain_knowledge",
            owner_scope=ALICE,
            apply=True,
        )
        assert edited["revision"] == 2, edited
        after = json.loads(
            table_rows(env, "memory_artifacts", "id = 'ev'")[0]["content"]
        )
        assert after["text"] == "only the text changed" and after["event_id"] == "e1"
        assert version_numbers(env, "ev") == [1, 2]
        return
    assert (
        json.loads(table_rows(env, "memory_artifacts", "id = 'ev'")[0]["content"])
        == original
    )
    assert version_numbers(env, "ev") == before_versions


# =============================================================================
# R12: identity invariants
# =============================================================================

_FILE_HASH = "f" * 64


def _identity(env: Env, artifact_id: str) -> tuple[Any, ...]:
    row = table_rows(env, "memory_artifacts", "id = ?", (artifact_id,))[0]
    return (
        row["owner_scope_kind"],
        row["owner_scope_id"],
        row["source"],
        row["symbol_ref"],
        row["content_hash"],
    )


def _identity_env(tmp_path: Path, **row: Any) -> tuple[Env, str]:
    env = make_env(tmp_path, seeded=False)
    assert env.store is not None
    (env.root / "mod.py").write_text("def Fn():\n    return 1\n", encoding="utf-8")
    put(
        env.store, "idr", ALICE, symbol_ref="mod.py::Fn", content_hash=_FILE_HASH, **row
    )
    assert _identity(env, "idr") == ("user", "alice", SRC, "mod.py::Fn", _FILE_HASH)
    return env, "idr"


_IDENTITY_CASES = [
    "edit",
    "update_content",
    "archive",
    "promote",
    "maintenance_corroboration",
    "maintenance_stale",
    "expiry",
    "upgrade_backfill",
    "migration_replace",
]


@pytest.mark.parametrize("case", [pytest.param(c, id=c) for c in _IDENTITY_CASES])
def test_t06_identity_invariants(case: str, tmp_path: Path) -> None:
    if case == "upgrade_backfill":
        env = make_env(tmp_path, seeded=False)
        assert env.store is not None
        put(
            env.store,
            "null-owned",
            ALICE,
            symbol_ref="mod.py::Fn",
            content_hash=_FILE_HASH,
        )
        put(
            env.store, "bob-keep", BOB, symbol_ref="mod.py::Fn", content_hash=_FILE_HASH
        )
        before_bob = _identity(env, "bob-keep")
        with contextlib.closing(sqlite3.connect(env.db)) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET owner_scope_kind = NULL, owner_scope_id = NULL WHERE id = 'null-owned'"
            )
            conn.commit()
        TypedArtifactStore.upgrade(env.root, cache_write=True)
        legacy = legacy_owner_scope(env.root)
        assert _identity(env, "null-owned") == (
            legacy.kind,
            legacy.id,
            SRC,
            "mod.py::Fn",
            _FILE_HASH,
        )
        assert _identity(env, "bob-keep") == before_bob
        return
    if case == "migration_replace":
        from rush.memory import migration

        # The origin writer authorizes a literal D4 source: use the legacy-mode project.
        env = make_env(tmp_path, mode="legacy", seeded=False)
        assert env.store is not None
        created = migration.write_if_new(
            env.store,
            family="memory",
            subject="domain_knowledge",
            content={"text": "origin v1"},
            source=SRC,
            origin_kind="t06-test",
            origin_id="o1",
            symbol_ref="mod.py::Fn",
        )
        assert created is not None
        _set_sql(
            env,
            "UPDATE memory_artifacts SET content_hash = ? WHERE id = ?",
            (_FILE_HASH, created.id),
        )
        before = _identity(env, created.id)
        assert (
            migration.replace_origin_content(
                env.store, "t06-test", "o1", {"text": "origin v2"}
            )
            is True
        )
        assert _identity(env, created.id) == before
        assert current_version(env, created.id) == 2
        return
    row_kw: dict[str, Any] = {}
    if case == "expiry":
        row_kw["created_at"] = time.time() - 400 * 86400
    env, rid = _identity_env(tmp_path, **row_kw)
    before = _identity(env, rid)
    assert env.store is not None
    if case == "edit":
        env.store.edit(
            rid,
            {"text": "edited bytes"},
            expected_version=1,
            scope="domain_knowledge",
            owner_scope=ALICE,
            apply=True,
        )
        assert current_version(env, rid) == 2
    elif case == "update_content":
        env.store.update_content(rid, {"text": "updated content"}, expected_version=1)
        assert current_version(env, rid) == 2
    elif case == "archive":
        env.store.archive(
            rid,
            expected_version=1,
            scope="domain_knowledge",
            owner_scope=ALICE,
            apply=True,
        )
        assert current_version(env, rid) == 2
    elif case == "promote":
        env.store.promote(rid, user_stated=True, owner_scope=ALICE)
        assert (
            table_rows(env, "memory_artifacts", "id = ?", (rid,))[0]["trust_tier"]
            == "STATED"
        )
    elif case in {"maintenance_corroboration", "maintenance_stale"}:
        from rush.memory.maintenance import run_maintenance_cycle
        from rush.memory.retrieval import MemoryAccess

        if case == "maintenance_corroboration":
            _set_sql(
                env,
                "UPDATE memory_artifacts SET corroboration_count = 7 WHERE id = ?",
                (rid,),
            )
        run_maintenance_cycle(
            "promotion_sweep"
            if case == "maintenance_corroboration"
            else "staleness_sweep",
            access=MemoryAccess.legacy(
                env.root, [SRC], owner_scope=ALICE, operation="write"
            ),
            project_root=env.root,
            candidate_ids=[rid],
            expected_revisions={rid: 1},
        )
        row = table_rows(env, "memory_artifacts", "id = ?", (rid,))[0]
        if case == "maintenance_corroboration":
            assert row["corroboration_count"] != 7
        else:
            assert row["stale"] == 1
    else:
        from rush.memory.maintenance import run_maintenance_cycle
        from rush.memory.retrieval import MemoryAccess

        swept = run_maintenance_cycle(
            "expiry_sweep",
            access=MemoryAccess.legacy(
                env.root, [SRC], owner_scope=ALICE, operation="write"
            ),
            project_root=env.root,
            candidate_ids=[rid],
        )
        assert swept.changed == 1
        assert (
            table_rows(env, "memory_artifacts", "id = ?", (rid,))[0]["expired_at"]
            is not None
        )
    assert _identity(env, rid) == before, (
        f"{case} changed owner/source/symbol_ref/content_hash"
    )


# =============================================================================
# R13: receipts schema migration (D29)
# =============================================================================

_V2_RECEIPT_COLUMNS = ("invocation_id", "effect_id", "request_digest")


def _pre72_receipts_env(tmp_path: Path) -> tuple[Env, str]:
    """A store that predates the D29 columns, holding one legacy receipt."""
    env = make_env(tmp_path)
    store = env.store
    assert store is not None
    with store._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        store._write_receipt(conn, "legacy-op-1", "r1", "edit", 2, {"legacy": True})
        conn.commit()
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute("DROP INDEX IF EXISTS idx_mutation_receipts_v2")
        conn.execute("DROP TRIGGER IF EXISTS memory_event_identity_immutable")
        conn.execute("DROP INDEX IF EXISTS idx_memory_event_identity")
        present = {r[1] for r in conn.execute("PRAGMA table_info(mutation_receipts)")}
        for column in _V2_RECEIPT_COLUMNS:
            if column in present:
                conn.execute(f"ALTER TABLE mutation_receipts DROP COLUMN {column}")
        conn.commit()
    return env, "legacy-op-1"


def _receipt_columns(env: Env) -> set[str]:
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        return {r[1] for r in conn.execute("PRAGMA table_info(mutation_receipts)")}


def _check_migrated(env: Env, legacy_id: str) -> None:
    assert set(_V2_RECEIPT_COLUMNS) <= _receipt_columns(env)
    index = table_rows(
        env, "sqlite_master", "type = 'index' AND name = 'idx_mutation_receipts_v2'"
    )
    assert (
        len(index) == 1
        and "UNIQUE" in index[0]["sql"].upper()
        and "WHERE" in index[0]["sql"].upper()
    )
    assert table_rows(
        env,
        "sqlite_master",
        "type = 'trigger' AND name = 'memory_event_identity_immutable'",
    )
    receipt = TypedArtifactStore(env.root).get_receipt(legacy_id)
    assert receipt is not None and receipt["payload"] == {"legacy": True}


def test_t06_get_receipt_readonly_creates_and_changes_nothing(tmp_path: Path) -> None:
    env, legacy_id = _pre72_receipts_env(tmp_path)
    before = (sha_file(env.db), _tree(env.root / ".rush"))
    status, receipt = TypedArtifactStore.get_receipt_readonly(env.root, legacy_id)
    assert status == "present"
    assert receipt is not None and receipt["payload"] == {"legacy": True}
    assert TypedArtifactStore.get_receipt_readonly(env.root, "missing-op") == (
        "absent",
        None,
    )
    assert (sha_file(env.db), _tree(env.root / ".rush")) == before
    assert not set(_V2_RECEIPT_COLUMNS) & _receipt_columns(env)
    no_store = tmp_path / "no-store"
    no_store.mkdir()
    assert TypedArtifactStore.get_receipt_readonly(no_store, "x") == ("absent", None)
    assert not (no_store / ".rush").exists()


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(c, id=c)
        for c in ("upgrade", "constructor", "readonly_v2_replay", "legacy_get_receipt")
    ],
)
def test_t06_receipts_migrate_existing_db(case: str, tmp_path: Path) -> None:
    env, legacy_id = _pre72_receipts_env(tmp_path)
    assert not set(_V2_RECEIPT_COLUMNS) & _receipt_columns(env)
    if case == "upgrade":
        TypedArtifactStore.upgrade(env.root, cache_write=True)
        _check_migrated(env, legacy_id)
    elif case == "constructor":
        TypedArtifactStore(env.root)
        _check_migrated(env, legacy_id)
    elif case == "readonly_v2_replay":
        before = sha_file(env.db)
        found = TypedArtifactStore.find_import_effect_readonly(
            invocation_id="i",
            effect_id="e",
            request_digest=_hex(1),
            access=_write_access(_import_env_like(env)),
        )
        assert found == {"state": "unavailable", "store_state": "migration_required"}
        status, receipt = TypedArtifactStore.get_receipt_readonly(env.root, legacy_id)
        assert (
            status == "present"
            and receipt is not None
            and receipt["payload"] == {"legacy": True}
        )
        assert sha_file(env.db) == before
    else:
        receipt = TypedArtifactStore(env.root).get_receipt(legacy_id)
        assert receipt is not None and receipt["payload"] == {"legacy": True}
        assert isinstance(receipt["payload"], dict)
        TypedArtifactStore.upgrade(env.root, cache_write=True)
        again = TypedArtifactStore(env.root).get_receipt(legacy_id)
        assert again is not None and again["payload"] == {"legacy": True}

    # An absent receipts table gains the v2 table.
    absent = make_env(tmp_path / "absent-table")
    with contextlib.closing(sqlite3.connect(absent.db)) as conn:
        conn.execute("DROP INDEX IF EXISTS idx_mutation_receipts_v2")
        conn.execute("DROP TABLE mutation_receipts")
        conn.commit()
    if case == "upgrade":
        TypedArtifactStore.upgrade(absent.root, cache_write=True)
        assert set(_V2_RECEIPT_COLUMNS) <= _receipt_columns(absent)


def _import_env_like(env: Env) -> Env:
    """The same project, granted for the `capsule:import` writer source."""
    grant(env, env.data_root, ALICE, sources=(SRC, IMPORT_SOURCE), ops=GRANT_OPS)
    return env


class _FailAfter:
    """A `sqlite3.Connection` proxy that raises once after executing SQL containing `needle`."""

    def __init__(
        self, conn: sqlite3.Connection, needle: str, state: dict[str, bool]
    ) -> None:
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "_needle", needle)
        object.__setattr__(self, "_state", state)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._conn, name, value)

    def _maybe_fail(self, sql: str) -> None:
        if self._needle in sql and not self._state["fired"]:
            self._state["fired"] = True
            raise RuntimeError(f"injected failure after {self._needle}")

    def execute(self, sql: str, *args: Any) -> Any:
        out = self._conn.execute(sql, *args)
        self._maybe_fail(sql)
        return out

    def executescript(self, sql: str) -> Any:
        out = self._conn.executescript(sql)
        self._maybe_fail(sql)
        return out


@pytest.mark.parametrize(
    "needle",
    [
        pytest.param("ADD COLUMN invocation_id", id="after_alter_invocation_id"),
        pytest.param("ADD COLUMN effect_id", id="after_alter_effect_id"),
        pytest.param("ADD COLUMN request_digest", id="after_alter_request_digest"),
        pytest.param("idx_mutation_receipts_v2", id="after_receipt_index"),
        pytest.param("memory_event_identity_immutable", id="after_event_trigger"),
        pytest.param("idx_memory_event_identity", id="after_event_index"),
    ],
)
def test_t06_upgrade_receipt_failure_rolls_back(
    needle: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env, _legacy_id = _pre72_receipts_env(tmp_path)
    original = env.db.read_bytes()
    state = {"fired": False}
    real_connect = sqlite3.connect

    def proxied(database: Any, *args: Any, **kwargs: Any) -> Any:
        conn = real_connect(database, *args, **kwargs)
        return (
            _FailAfter(conn, needle, state)
            if str(database).endswith("memory.db")
            else conn
        )

    with monkeypatch.context() as patch:
        patch.setattr(sqlite3, "connect", proxied)
        with pytest.raises(RuntimeError, match="injected failure"):
            TypedArtifactStore.upgrade(env.root, cache_write=True)
    assert state["fired"], f"upgrade never executed SQL containing {needle!r}"
    assert env.db.read_bytes() == original, (
        "a failed upgrade must leave the file bytes unchanged"
    )
    assert not set(_V2_RECEIPT_COLUMNS) & _receipt_columns(env)


_UPGRADE_CHILD = r"""
import sys
import threading
from pathlib import Path
from rush.memory.store import TypedArtifactStore
TypedArtifactStore.upgrade(Path(sys.argv[1]), cache_write=True)
"""


def test_t06_concurrent_upgrades(tmp_path: Path) -> None:
    env, legacy_id = _pre72_receipts_env(tmp_path)
    assert env.store is not None
    for index in range(300):
        put(env.store, f"bulk-{index}", ALICE, text=f"needle bulk {index}")
    environment = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")}
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _UPGRADE_CHILD, str(env.root)],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    outputs = [p.communicate(timeout=180) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], outputs
    _check_migrated(env, legacy_id)
    names = [
        r["name"]
        for r in table_rows(
            env, "sqlite_master", "type = 'index' AND name = 'idx_mutation_receipts_v2'"
        )
    ]
    assert names == ["idx_mutation_receipts_v2"]
    assert (
        len(table_rows(env, "mutation_receipts", "operation_id = 'legacy-op-1'")) == 1
    )


# =============================================================================
# R14: reviewed-deleted rows leave no history
# =============================================================================

_DELETED_CASES = [
    pytest.param("history", False, id="history_active"),
    pytest.param("history", True, id="history_historical"),
    pytest.param("expand", False, id="expand_ordinary"),
    pytest.param("expand", True, id="expand_historical"),
]


@pytest.mark.parametrize(("operation", "historical"), _DELETED_CASES)
def test_t06_deleted_history_absent(
    operation: str, historical: bool, tmp_path: Path
) -> None:
    env = make_env(tmp_path)
    if operation == "expand":
        _deleted_expand_halves(env, historical)
        return
    assert code(apply_call(env, "edit", m_edit())) == "OK"  # r1 has two versions
    assert code(apply_call(env, "delete", m_delete(revisions={"r1": 2}))) == "OK"
    extra: dict[str, Any] = {"archive_mode": "historical"} if historical else {}
    gone = call(env, "history", r_history(artifact_id="r1", **extra))
    never = call(env, "history", r_history(artifact_id="never-existed", **extra))
    assert code(gone) == "E_NOT_VISIBLE" and code(never) == "E_NOT_VISIBLE"
    assert dump(raw(gone)).replace("r1", "ID") == dump(raw(never)).replace(
        "never-existed", "ID"
    )
    assert "needle" not in dump(raw(gone))
    # The deleted id leaves no trace in any read under the same access.
    assert "r1" not in dump(raw(call(env, "list", r_list(archive_mode="historical"))))
    assert "r1" not in dump(raw(call(env, "ask", r_ask(archive_mode="historical"))))


def _deleted_expand_halves(env: Env, historical: bool) -> None:
    """Guard G-a: set up and read through existing store/retrieval seams only, so the
    two expand cases pass at HEAD and fail when `delete_batch` keeps the current row."""
    from rush.memory.retrieval import MemoryAccess, expand_artifact

    store = env.store
    assert store is not None
    store.edit(
        "r1",
        {"text": "needle revised"},
        expected_version=1,
        scope="domain_knowledge",
        owner_scope=ALICE,
        apply=True,
    )
    store.delete_batch(
        ["r1"],
        expected_revisions={"r1": 2},
        scope="domain_knowledge",
        owner_scope=ALICE,
        apply=True,
    )
    access = MemoryAccess.resolve(
        env.root,
        operation="expand",
        historical=historical,
        owner_scope=ALICE,
        data_root=env.data_root,
    )
    assert access is not None
    mode: Literal["ordinary", "historical"] = "historical" if historical else "ordinary"
    gone = expand_artifact(store, artifact_id="r1", version=2, access=access, mode=mode)
    never = expand_artifact(
        store, artifact_id="never-existed", version=2, access=access, mode=mode
    )
    assert gone["code"] == "E_NOT_VISIBLE" and never["code"] == "E_NOT_VISIBLE", (
        gone,
        never,
    )
    assert dump(gone).replace("r1", "ID") == dump(never).replace("never-existed", "ID")
    assert "needle" not in dump(gone)


def test_t06_deleted_expand_v2_surface(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    assert code(apply_call(env, "edit", m_edit())) == "OK"
    assert code(apply_call(env, "delete", m_delete(revisions={"r1": 2}))) == "OK"
    for extra in cast(tuple[dict[str, Any], ...], ({}, {"archive_mode": "historical"})):
        gone = call(env, "expand", r_expand(artifact_id="r1", **extra))
        never = call(env, "expand", r_expand(artifact_id="never-existed", **extra))
        assert code(gone) == "E_NOT_VISIBLE" and code(never) == "E_NOT_VISIBLE"
        assert dump(raw(gone)).replace("r1", "ID") == dump(raw(never)).replace(
            "never-existed", "ID"
        )
        assert "needle" not in dump(raw(gone))


# =============================================================================
# Producer flips, schema-only additions, G3/G4 rows and maintenance locking
# =============================================================================

_MATRIX_FILES = (
    "tests/test_phase72_memory_correctness.py",
    "tests/test_phase72_preferences.py",
)


def test_t06_earlier_matrices_have_no_t06_producer_cells() -> None:
    """72-T06 flips every producer-staged cell it owns (`schema_version`, `history`,
    `explain`, `archive_mode`) in the 72-T01..72-T05 route matrices into a real cell: no
    collected test id of those files keeps a `producer-72-T06` suffix."""
    present = [f for f in _MATRIX_FILES if (PROJECT_ROOT / f).exists()]
    assert present, "no earlier matrix file exists"
    collected = subprocess.run(  # noqa: PLW1510 - the return code is asserted below
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *present,
        ],
        cwd=PROJECT_ROOT,
        env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert collected.returncode == 0, (
        collected.stdout[-2000:] + collected.stderr[-2000:]
    )
    staged = [
        line
        for line in collected.stdout.splitlines()
        if "producer-72-T06" in line or "-72-T06]" in line
    ]
    assert staged == [], staged[:5]


def test_t06_hybrid_read_on_store_missing_only_t06_additions_leaves_bytes_unchanged(
    tmp_path: Path,
) -> None:
    """A store missing only the T06 schema additions (three receipt columns, the partial
    receipt index, the event trigger and index) is read through the read-only view by a
    hybrid read: no constructor migration runs on a read route."""
    env, _legacy = _pre72_receipts_env(tmp_path)
    before = sha_file(env.db)
    result = call(
        env,
        "ask",
        r_ask(retrieval="hybrid"),
        perms=ExecutionPermissions(cache_write=True, network=True),
    )
    assert code(result) in {"OK", "E_PERMISSION"}, dump(raw(result))
    assert sha_file(env.db) == before
    assert not set(_V2_RECEIPT_COLUMNS) & _receipt_columns(env)
    lex = call(env, "list", r_list(), perms=ExecutionPermissions(cache_write=True))
    assert code(lex) == "OK" and sha_file(env.db) == before


def test_t06_telemetry_only_after_admission_and_access(tmp_path: Path) -> None:
    env = make_env(tmp_path / "ok")
    assert code(call(env, "list", r_list(), perms=PERM_W)) == "OK"
    assert (env.root / ".rush" / "telemetry" / "tokens.db").exists()

    denied = make_env(tmp_path / "revoked")
    revoke(denied, ALICE)
    assert code(call(denied, "list", r_list(), perms=PERM_W)) == "E_PERMISSION"
    assert not (denied.root / ".rush" / "telemetry").exists()

    admitted = make_env(tmp_path / "admission")
    assert code(call(admitted, "list", r_list(max_bytes=1), perms=PERM_W)) == "E_INPUT"
    assert not (admitted.root / ".rush" / "telemetry").exists()


def test_t06_legacy_forms_keep_their_v1_envelope(tmp_path: Path) -> None:
    """Compatibility: a call without `schema_version` keeps the pre-T06 result shape."""
    env = make_env(tmp_path)
    compact = MemoryTool().run(
        env.root,
        operation="ask",
        subject="domain_knowledge",
        query="needle",
        owner_scope=ALICE,
        request={"view": "compact"},
    )
    assert raw(compact)["code"] == "OK" and raw(compact)["schema_version"] == 1
    assert [i["id"] for i in raw(compact)["data"]["items"]] == ["r1"]
    listed = MemoryTool().run(
        env.root,
        operation="list",
        subject="domain_knowledge",
        query="needle",
        owner_scope=ALICE,
    )
    assert isinstance(listed["raw"], list) and [i["id"] for i in listed["raw"]] == [
        "r1"
    ]
    unsupported = call(env, "capsule", {})
    assert unsupported["status"] == "error"


def test_t06_g4_path_and_input_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path / "p")

    # A symlink loop or unresolvable path: in-process E_INPUT field path; MCP rejects.
    if os.name != "nt":
        loop = tmp_path / "loop"
        loop.symlink_to(loop)
        looped = MemoryTool().run(
            loop, operation="list", request=r_list(), permissions=PERM_NONE
        )
        assert code(looped) == "E_INPUT" and data(looped)["field"] == "path"
    raising = MemoryTool().run(
        "\x00bad",  # type: ignore[arg-type]  # deliberate NUL path
        operation="list",
        request=r_list(),
        permissions=PERM_NONE,
    )
    assert code(raising) == "E_INPUT" and data(raising)["field"] == "path"

    # A missing path: policy mode denies, legacy mode reads an empty page.
    import shutil

    gone = tmp_path / "gone"
    gone.mkdir()
    register_project(gone, data_root=env.data_root)
    grant(gone, env.data_root, ALICE, root=gone.resolve())
    shutil.rmtree(gone)
    missing = MemoryTool().run(
        gone, operation="list", request=r_list(), permissions=PERM_NONE
    )
    assert code(missing) == "E_PERMISSION" and reason(missing) == "project_missing"
    legacy_missing = MemoryTool().run(
        tmp_path / "never-existed",
        operation="list",
        request=r_list(None, sources=[SRC]),
        permissions=PERM_NONE,
    )
    assert code(legacy_missing) == "OK" and raw(legacy_missing)["items"] == []
    assert not (tmp_path / "never-existed").exists()

    # A moved root: the registered grant no longer matches the relocated worktree.
    moved = tmp_path / "moved-away"
    env.root.rename(moved)
    relocated = MemoryTool().run(
        moved, operation="list", request=r_list(), permissions=PERM_NONE
    )
    assert code(relocated) == "E_PERMISSION"
    assert reason(relocated) in {
        "relinked",
        "project_missing",
        "worktree_mismatch",
        "no_grant",
        "project_not_registered",
    }
    moved.rename(env.root)

    # A case-variant spelling of the root is never the registered root.
    variant = env.root.parent / env.root.name.swapcase()
    assert variant != env.root
    respelled = MemoryTool().run(
        variant, operation="list", request=r_list(), permissions=PERM_NONE
    )
    assert code(respelled) == "E_PERMISSION"
    assert reason(respelled) in {"relinked", "project_missing", "worktree_mismatch"}

    # A lone surrogate inside stored content is the JSON escape and returned identically.
    sur = apply_call(
        env,
        "write",
        m_write(inv="i-s", eff="e-s", content={"text": "needle \ud800 lone"}),
    )
    assert code(sur) == "OK", dump(raw(sur))
    new_id = ids(sur)[0]
    stored = table_rows(env, "memory_artifacts", "id = ?", (new_id,))[0]["content"]
    assert "\\ud800" in stored
    again = call(env, "expand", r_expand(artifact_id=new_id))
    assert code(again) == "OK"
    assert "\\ud800" in dump(raw(again))

    # CLI `--input`: a BOM or non-UTF-8 file is a ClickException (exit 1); MemoryTool is never called.
    calls: list[Any] = []
    real_run = MemoryTool.run

    def spy_run(self: Any, *a: Any, **k: Any) -> Any:
        calls.append(k)
        return real_run(self, *a, **k)

    monkeypatch.setattr(MemoryTool, "run", spy_run)
    bad_utf8 = env.root.parent / "bad-utf8.json"
    bad_utf8.write_bytes(b"\xff\xfe{}")
    bom = env.root.parent / "bom.json"
    bom.write_bytes(b"\xef\xbb\xbf{}")
    status, out = cli_json(
        env.root, ["memory", "expand", "--input", str(bad_utf8), "--json"]
    )
    assert status == 1 and "must be UTF-8 JSON" in str(out)
    status, out = cli_json(
        env.root, ["memory", "expand", "--input", str(bom), "--json"]
    )
    assert status == 1 and "must be valid JSON" in str(out)
    assert calls == []


def test_t06_explain_over_cap_is_budget_error(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    assert env.store is not None
    from rush.memory.relations import add_relation

    for index in range(60):
        rid = f"n{index:02d}"
        put(env.store, rid, ALICE, text=f"needle neighbour {index} " + "padding " * 20)
        assert (
            add_relation(
                env.store,
                source_id="r1",
                source_version=1,
                target_id=rid,
                target_version=1,
                kind="depends_on",
            )["code"]
            == "OK"
        )
    over = call(env, "explain", r_explain(max_bytes=4096))
    assert_v2_envelope(over, "explain", "E_BUDGET")
    assert set(data(over)["required"]) == {"max_bytes", "max_tokens"}
    assert (
        data(over)["required"]["max_bytes"] > 4096
        or data(over)["required"]["max_tokens"] > 0
    )


def test_t06_maintain_cycle_runs_outside_the_policy_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T04 R19(a) through v2: replay lookup and the receipt hold the policy lock; the
    maintenance cycle itself does not (another thread can take it while the cycle runs)."""
    from rush.memory import authorization, maintenance

    env = make_env(tmp_path)
    free = {"ok": False}
    original = maintenance.run_maintenance_cycle

    def probe(*args: Any, **kwargs: Any) -> Any:
        done = threading.Event()

        def attempt() -> None:
            with authorization.hold_policy_lock(data_root=env.data_root):
                done.set()

        worker = threading.Thread(target=attempt)
        worker.start()
        worker.join(10)
        free["ok"] = done.is_set()
        return original(*args, **kwargs)

    monkeypatch.setattr(maintenance, "run_maintenance_cycle", probe)
    import rush.tools.memory as memory_tool

    monkeypatch.setattr(memory_tool, "run_maintenance_cycle", probe, raising=False)
    result = apply_call(env, "maintain", m_maintain(batch_size=1000))
    assert code(result) == "OK", dump(raw(result))
    assert free["ok"], "the maintenance cycle ran while the route held the policy lock"
    assert len(v2_receipts(env)) == 1 and v2_receipts(env)[0]["kind"] == "maintain"
    # A reviewed revision that no longer matches is never swept.
    stale = apply_call(
        env, "maintain", m_maintain(inv="inv-m2", eff="eff-m2", revisions={"r1": 99})
    )
    assert code(stale) in {"OK", "E_VERSION"}
    assert table_rows(env, "memory_artifacts", "id = 'r1'")[0]["stale"] == 0


def test_t06_maintain_replay_and_revocation_before_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import maintenance

    env = make_env(tmp_path)
    first = apply_call(env, "maintain", m_maintain())
    assert code(first) == "OK"
    receipts = len(v2_receipts(env))
    again = apply_call(env, "maintain", m_maintain())
    assert dump(raw(again)) == dump(raw(first))
    assert len(v2_receipts(env)) == receipts

    # Revocation between the cycle and the receipt: denial, no new receipt.
    late = make_env(tmp_path / "late")
    original = maintenance.run_maintenance_cycle

    def revoke_after(*args: Any, **kwargs: Any) -> Any:
        out = original(*args, **kwargs)
        revoke(late, ALICE)
        return out

    monkeypatch.setattr(maintenance, "run_maintenance_cycle", revoke_after)
    import rush.tools.memory as memory_tool

    monkeypatch.setattr(
        memory_tool, "run_maintenance_cycle", revoke_after, raising=False
    )
    denied = apply_call(late, "maintain", m_maintain(inv="inv-late", eff="eff-late"))
    assert code(denied) == "E_PERMISSION" and reason(denied) == "revoked"
    assert not v2_receipts(late)


def test_t06_v2_read_request_accepts_exactly_the_declared_fields(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    full = r_list(
        sources=[SRC],
        trust_tiers=["IMPORTED", "EXTERNAL_WRITE", "DERIVED", "STATED"],
        freshness=["current", "stale", "unknown", "not_applicable"],
        archive_mode="active",
        limit=5,
        max_tokens=4000,
        max_bytes=20000,
        retrieval="lexical",
        query="",
    )
    body = assert_v2_envelope(call(env, "list", full), "list", "OK")
    assert len(body["items"]) == 5 and body["next_cursor"] and body["complete"] is False
    declared = {
        "schema_version",
        "subjects",
        "query",
        "owner_scope",
        "sources",
        "trust_tiers",
        "freshness",
        "archive_mode",
        "limit",
        "max_tokens",
        "max_bytes",
        "encoding",
        "cursor",
        "retrieval",
        "embedding_endpoint",
        "embedding_model",
        "embedding_model_digest",
        "embedding_chunking_version",
    }
    assert set(full) <= declared
    # A page of the same request resumes through its own cursor.
    nxt = call(env, "list", {**full, "cursor": body["next_cursor"]})
    assert code(nxt) == "OK" and not set(ids(nxt)) & {
        i["reference"]["artifact_id"] for i in body["items"]
    }


# --- stdio and CLI baseline cells of the matrix ------------------------------------


def _cell_stdio(route: str, tmp_path: Path) -> None:
    """One real `python -m rush.cli mcp serve` child per operation at the baseline."""
    solo = make_env(tmp_path, bob=False)
    if route in READ_BUILDERS:
        request = READ_BUILDERS[route](None)
        expected = call(solo, route, request)
        over_stdio = stdio_call(solo, route, request)
        assert code(over_stdio) == "OK", dump(raw(over_stdio))
        assert _normalize(solo, raw(over_stdio)) == _normalize(solo, raw(expected))
        return
    request = MUTATION_BUILDERS[route](None)
    before = len(all_receipts(solo))
    over_stdio = stdio_call(solo, route, request, cache_write=True)
    assert code(over_stdio) == "OK", dump(raw(over_stdio))
    assert len(all_receipts(solo)) == before + 1
    assert v2_receipts(solo)[-1]["kind"] == MUT_KIND[route]


_CLI_LEAVES: dict[str, list[str] | dict[str, Any]] = {
    "history": ["memory", "history", "r1", "--json"],
    "explain": ["memory", "explain", "r1", "--json"],
    "expand": r_expand(None),
    "related": r_related(None),
    "link": m_link(None),
    "delete": m_delete(None),
    "edit": m_edit(None),
    "archive": m_archive(None),
}


def _cell_cli_baseline(leaf: str, tmp_path: Path) -> None:
    solo = make_env(tmp_path, bob=False)
    spec = _CLI_LEAVES[leaf]
    if isinstance(spec, list):
        status, out = cli_json(solo.root, spec)
    else:
        path = write_input(solo.root, f"{leaf}-in", spec)
        flags = ["--allow-cache-write"] if leaf in MUT_ROUTES else []
        status, out = cli_json(
            solo.root, ["memory", leaf, "--input", str(path), *flags, "--json"]
        )
    assert status == 0 and raw(out)["code"] == "OK", dump(out)
    assert raw(out)["schema_version"] == 2 and raw(out)["operation"] == leaf
    if leaf in MUT_ROUTES:
        assert v2_receipts(solo)[-1]["kind"] == MUT_KIND[leaf]


# --- the single matrix test: every group is a cell of `test_t06_route_mode_matrix` ----


def _dashboard_cell(tmp_path: Path) -> None:
    """A dashboard `memory_promote` action carrying `schema_version` is refused at the
    allowlist (HTTP 400 `unsupported_argument`) before any dispatch: the dashboard is not a
    v2 transport (72-T07 adopts it)."""
    from rush.dashboard.server import create_dashboard_server
    from tests.test_dashboard_http_contract import (
        _bootstrap_session,
        _load_fixture,
        _post,
        _serve,
    )

    project_a = _load_fixture("project_a.json")
    server, ctx, token = create_dashboard_server({"project-a": project_a})
    _serve(server)
    try:
        base_url = ctx.launch_origin
        cookie, csrf = _bootstrap_session(base_url, token)
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        }
        response = _post(
            f"{base_url}/api/projects/project-a/actions",
            headers=headers,
            body=json.dumps(
                {
                    "schema_version": 1,
                    "operation": "memory_promote",
                    "request_id": "req-t06-schema-version",
                    "arguments": {
                        "subject": "domain_knowledge",
                        "content": {"text": "x"},
                        "source": SRC,
                        "schema_version": 2,
                    },
                }
            ).encode(),
        )
        assert response.status == 400
        assert json.loads(response.read())["error"]["code"] == "unsupported_argument"
    finally:
        server.shutdown()
        server.server_close()


def _all_cells() -> list[Any]:
    cells: list[Any] = list(_matrix_cells())

    def add(transport: str, route: str, dim: str, value: str) -> None:
        cells.append(
            pytest.param(
                transport, route, dim, value, id=f"{transport}.{route}-{dim}-{value}"
            )
        )

    for transport in ("inproc", "mcp"):
        for operation in NON_V2_OPERATIONS:
            add(transport, operation, "schema_version", "2")
        add(transport, "capsule", "operation", "producer_73_T09")
    for operation in ("receive", "expand", "related", "resume", *ADMIN_OPS):
        add("bridge", operation, "access", "restricted")
    for name in NO_FIELD:
        add("inproc", name, "access", "policy_no_field")
    for leaf in ("ask", "recall", "list", "write", "promote", "maintain"):
        add("cli", leaf, "access", "policy_no_field")
    for seam in SEAMS:
        for state in STORE_STATES:
            for form in ACCESS_FORMS:
                add("seam", seam, "store", f"{state}-access-{form}")
    for route in V2_OPS:
        add("stdio", route, "access", "policy")
    for leaf in _CLI_LEAVES:
        add("cli", leaf, "access", "policy")
    add("dashboard", "promote", "schema_version", "present")
    return cells


@pytest.mark.parametrize(("transport", "route", "dim", "value"), _all_cells())
def test_t06_route_mode_matrix(
    transport: str,
    route: str,
    dim: str,
    value: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if transport == "bridge":
        _cell_bridge(route, tmp_path)
    elif transport == "dashboard":
        _dashboard_cell(tmp_path)
    elif transport == "stdio":
        _cell_stdio(route, tmp_path)
    elif transport == "seam":
        state, form = value.split("-access-")
        _cell_seam(route, state, form, tmp_path)
    elif transport == "cli":
        if dim == "access" and value == "policy_no_field":
            _cell_cli_positional(route, tmp_path)
        else:
            _cell_cli_baseline(route, tmp_path)
    elif dim == "schema_version":
        _cell_non_v2(route, transport, tmp_path)
    elif dim == "operation":
        _cell_capsule(transport, tmp_path)
    elif dim == "access" and value == "policy_no_field":
        _cell_no_field(route, tmp_path)
    else:
        _engine_cell(transport, route, dim, value, tmp_path)


def test_t06_single_granted_owner_resolves_when_omitted(tmp_path: Path) -> None:
    solo = make_env(tmp_path / "solo", bob=False)
    listed = call(solo, "list", r_list(owner=None))
    assert_v2_envelope(listed, "list", "OK")
    assert set(ids(listed)) == _alice_ids()
    written = apply_call(solo, "write", m_write(owner=None, inv="i-solo", eff="e-solo"))
    assert code(written) == "OK"
    new_id = ids(written)[0]
    row = table_rows(solo, "memory_artifacts", "id = ?", (new_id,))[0]
    assert (row["owner_scope_kind"], row["owner_scope_id"]) == ("user", "alice")
    # Two granted owners make an omitted owner ambiguous, never a silent default.
    pair = make_env(tmp_path / "pair")
    ambiguous = call(pair, "list", r_list(owner=None))
    assert code(ambiguous) == "E_INPUT"
    assert data(ambiguous).get("field") == "owner_scope"
    assert data(ambiguous).get("reason") == "owner_required"


def test_t06_omitted_sources_resolve_every_approved_source(tmp_path: Path) -> None:
    env = make_env(tmp_path, bob=False)
    env.grants["alice"] = grant(env, env.data_root, ALICE, sources=(SRC, "s2"))
    assert env.store is not None
    put(env.store, "from-s2", ALICE, source="s2", text="needle s2 row")
    everything = ids(call(env, "list", r_list(subjects=["domain_knowledge"])))
    assert {"r1", "from-s2"} <= set(everything)
    only_s2 = ids(
        call(env, "list", r_list(subjects=["domain_knowledge"], sources=["s2"]))
    )
    assert only_s2 == ["from-s2"]
    denied = call(env, "list", r_list(sources=["s3"]))
    assert code(denied) == "E_SCOPE" and reason(denied) == "source_not_granted"
    assert "from-s2" not in ids(
        call(env, "list", r_list(subjects=["domain_knowledge"], sources=[SRC]))
    )


# =============================================================================
# Re-gate additions: correction model, maintenance contract, transport frames,
# type-aware event identity, G15 failure classes, preservation oracle
# =============================================================================


def _cli_result(root: Path, args: list[str]) -> Any:
    """The Click `Result` of `rush ...` from `root` (exit code, output, exception)."""
    from click.testing import CliRunner

    from rush.cli import cli

    old = os.getcwd()
    os.chdir(root)
    try:
        return CliRunner().invoke(cli, args)
    finally:
        os.chdir(old)


# --- R2: explicit legacy defaults beside schema_version (presence is preserved) -----

_LEGACY_DEFAULT_FIELDS = [
    pytest.param("query", "", id="query_blank"),
    pytest.param("source", "", id="source_blank"),
    pytest.param("user_stated", False, id="user_stated_false"),
    pytest.param("batch_size", 500, id="batch_size_default"),
    pytest.param("include_archived", False, id="include_archived_false"),
    pytest.param("source_kind", "local_tool", id="source_kind_default"),
]


@pytest.mark.parametrize(
    "boundary", [pytest.param("run", id="run"), pytest.param("call", id="call")]
)
@pytest.mark.parametrize(("field", "value"), _LEGACY_DEFAULT_FIELDS)
def test_t06_v2_mixed_fields_preserve_presence(
    field: str, value: Any, boundary: str, tmp_path: Path
) -> None:
    """A legacy field supplied beside `schema_version` is a mixed form even when its
    value equals the legacy default, at `run` and at `__call__` (which forwards every
    parameter); in-process and MCP agree, nothing is created, and the same v2 request
    with the field omitted is not mistaken for a mixed form."""
    env = make_env(tmp_path)
    before = snapshot(env)
    tool = MemoryTool()
    if boundary == "run":
        supplied = tool.run(
            env.root,
            operation="list",
            request=r_list(),
            permissions=PERM_W,
            **{field: value},
        )
    else:
        supplied = tool(
            env.root,
            "list",
            request=r_list(),
            allow_cache_write=True,
            **{field: value},
        )
    over_mcp = mcp_call(env, "list", r_list(), cache_write=True, **{field: value})
    body = assert_v2_envelope(supplied, "list", "E_INPUT")
    assert supplied["status"] == "error"
    assert body["items"] == [] and body["complete"] is False
    assert dump(raw(supplied)) == dump(raw(over_mcp))
    only_zero_effects(env, before, f"{boundary}:{field}")
    if boundary == "run":
        omitted = tool.run(env.root, operation="list", request=r_list())
    else:
        omitted = tool(env.root, "list", request=r_list())
    assert_v2_envelope(omitted, "list", "OK")


@pytest.mark.parametrize(
    "boundary", [pytest.param("run", id="run"), pytest.param("call", id="call")]
)
@pytest.mark.parametrize(
    ("field", "value"),
    [p for p in _LEGACY_DEFAULT_FIELDS if p.id != "query_blank"],
)
def test_t06_legacy_explicit_defaults_match_omitted(
    field: str, value: Any, boundary: str, tmp_path: Path
) -> None:
    """Compatibility: on a legacy call an explicit default is byte-identical to omitting
    the parameter (the sentinel substitutes the existing defaults only on this branch)."""
    env = make_env(tmp_path)
    tool = MemoryTool()
    base: dict[str, Any] = {
        "operation": "ask",
        "subject": "domain_knowledge",
        "query": "needle",
        "session_allowlist": [SRC],
        "owner_scope": ALICE,
        "request": {"view": "compact"},
    }

    def go(extra: dict[str, Any]) -> Any:
        if boundary == "run":
            return tool.run(env.root, **base, **extra)
        args = {k: v for k, v in base.items() if k != "operation"}
        return tool(env.root, base["operation"], **args, **extra)

    omitted = go({})
    explicit = go({field: value})
    assert omitted["raw"]["code"] == "OK" and omitted["raw"]["schema_version"] == 1
    assert stable(explicit) == stable(omitted)


# --- R2 / 72-T05 handoff: the edit correction request model --------------------------


def _citation(
    artifact_id: str = "r2", version: Any = 1, **extra: Any
) -> dict[str, Any]:
    return {"artifact_id": artifact_id, "artifact_version": version, **extra}


def _no_content(body: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in body.items() if k != "content"}


def _correction_rejections() -> list[Any]:
    cases: list[tuple[str, dict[str, Any]]] = []

    def add(label: str, correction: Any, *, content: Any = None) -> None:
        body = m_edit(correction=correction)
        if content is not None:
            body = {**body, "content": content}
        cases.append((label, body))

    add("kind_unknown", {"kind": "retract", "reason": "r"})
    add("kind_list", {"kind": ["correct"], "reason": "r"})
    add("kind_dict", {"kind": {"a": 1}, "reason": "r"})
    add("kind_missing", {"reason": "r"})
    add("reason_missing", {"kind": "correct"})
    add("reason_empty", {"kind": "correct", "reason": ""})
    add("reason_nul", {"kind": "correct", "reason": "bad\x00reason"})
    add("reason_cc", {"kind": "correct", "reason": "bad\x07reason"})
    add("reason_cf", {"kind": "correct", "reason": "bad\u200breason"})
    add("reason_lone_surrogate", {"kind": "correct", "reason": "bad\ud800reason"})
    add("reason_not_str", {"kind": "correct", "reason": 5})
    add("extra_key", {"kind": "correct", "reason": "r", "note": "x"})
    add("correction_not_object", ["correct"])
    add("correction_null", None)
    add(
        "supersedes_not_list",
        {"kind": "supersede", "reason": "r", "supersedes": "r2"},
    )
    add("supersedes_empty", {"kind": "supersede", "reason": "r", "supersedes": []})
    add(
        "supersedes_65",
        {
            "kind": "supersede",
            "reason": "r",
            "supersedes": [_citation(f"c{i}") for i in range(65)],
        },
    )
    add(
        "supersedes_duplicate",
        {
            "kind": "supersede",
            "reason": "r",
            "supersedes": [_citation(), _citation()],
        },
    )
    for label, version in (
        ("version_zero", 0),
        ("version_negative", -1),
        ("version_true", True),
        ("version_str", "1"),
        ("version_float", 1.0),
        ("version_huge", 10**400),
        ("version_none", None),
    ):
        add(
            f"supersedes_{label}",
            {
                "kind": "supersede",
                "reason": "r",
                "supersedes": [_citation(version=version)],
            },
        )
    add(
        "supersedes_id_nul",
        {"kind": "supersede", "reason": "r", "supersedes": [_citation("r\x002")]},
    )
    add(
        "supersedes_id_not_str",
        {"kind": "supersede", "reason": "r", "supersedes": [_citation(5)]},  # type: ignore[arg-type]  # deliberate non-str id
    )
    add(
        "supersedes_entry_extra_key",
        {"kind": "supersede", "reason": "r", "supersedes": [_citation(note="x")]},
    )
    add(
        "supersedes_entry_missing_version",
        {"kind": "supersede", "reason": "r", "supersedes": [{"artifact_id": "r2"}]},
    )
    # Content rules: an ordinary edit needs content, `reject` forbids it.
    cases.append(("no_correction_no_content", _no_content(m_edit())))
    add(
        "reject_with_content",
        {"kind": "reject", "reason": "wrong"},
        content={"text": "must not be here"},
    )
    return [pytest.param(label, body, id=label) for label, body in cases]


@pytest.mark.parametrize(("label", "body"), _correction_rejections())
def test_t06_edit_correction_request_contract(
    label: str, body: dict[str, Any], tmp_path: Path
) -> None:
    """MemoryEditCorrection and the content rules are strict: every violation is an
    `E_INPUT` with zero effects, identical in-process and over MCP."""
    env = make_env(tmp_path)
    before = snapshot(env)
    inproc = call(env, "edit", body, perms=PERM_W)
    over_mcp = mcp_call(env, "edit", body, cache_write=True)
    for result in (inproc, over_mcp):
        envelope = assert_v2_envelope(result, "edit", "E_INPUT")
        assert envelope["items"] == [] and envelope["complete"] is False
        assert envelope["data"].get("details") or envelope["data"].get("message"), label
    assert dump(raw(inproc)) == dump(raw(over_mcp)), label
    only_zero_effects(env, before, label)


def _cite_set(items: Any) -> set[tuple[Any, Any]]:
    return {
        (i["artifact_id"], i["artifact_version"])
        if isinstance(i, dict)
        else (i[0], i[1])
        for i in items or ()
    }


_CORRECTION_DISPATCH = [
    pytest.param(
        {"kind": "correct", "reason": "fix"}, None, set(), id="correct_omitted_content"
    ),
    pytest.param(
        {"kind": "correct", "reason": "fix"},
        {"text": "needle corrected"},
        set(),
        id="correct_replacement",
    ),
    pytest.param({"kind": "reject", "reason": "wrong"}, None, set(), id="reject"),
    pytest.param(
        {"kind": "supersede", "reason": "newer", "supersedes": [_citation()]},
        None,
        {("r2", 1)},
        id="supersede_one_citation_omitted_content",
    ),
    pytest.param(
        {
            "kind": "supersede",
            "reason": "newer",
            "supersedes": [
                _citation("r2"),
                _citation("a-episodic"),
                _citation("r2", 2),
            ],
        },
        {"text": "needle newer"},
        {("r2", 1), ("a-episodic", 1), ("r2", 2)},
        id="supersede_three_citations_with_content",
    ),
]


@pytest.mark.parametrize(("correction", "content", "cited"), _CORRECTION_DISPATCH)
def test_t06_edit_correction_dispatch_passes_every_citation(
    correction: dict[str, Any],
    content: dict[str, Any] | None,
    cited: set[tuple[str, int]],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Schema-2 `edit` with `correction` calls the 72-T05 `apply_correction` once with
    the resolved access, the target's current content, the replacement content (or None),
    every normalized citation and a `receipt_writer` bound to the v2 receipt; a replay
    returns the stored result without calling it again."""
    env = make_env(tmp_path)
    calls: list[dict[str, Any]] = []

    def fake_apply_correction(self: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        ref = {"artifact_id": kwargs["artifact_id"], "artifact_version": 1}
        with contextlib.closing(sqlite3.connect(env.db, isolation_level=None)) as conn:
            conn.execute("BEGIN IMMEDIATE")
            kwargs["receipt_writer"](
                conn,
                {
                    **ref,
                    "result_refs": [ref],
                    "result": {"code": "OK", **ref, "replacement": None, "edge": None},
                },
            )
            conn.execute("COMMIT")
        return {"code": "OK", **ref, "replacement": None, "edge": None}

    monkeypatch.setattr(
        TypedArtifactStore, "apply_correction", fake_apply_correction, raising=False
    )
    request = m_edit(correction=correction)
    if content is not None:
        request = {**request, "content": content}
    first = apply_call(env, "edit", request)
    assert_v2_envelope(first, "edit", "OK")
    assert len(calls) == 1, calls
    seen = calls[0]
    assert seen["kind"] == correction["kind"]
    assert seen["artifact_id"] == "r1" and seen["expected_version"] == 1
    assert isinstance(seen["target_content"], dict)
    if correction["kind"] == "supersede":
        assert isinstance(seen["replacement_content"], dict)
        if content is not None:
            assert seen["replacement_content"] == content
    elif correction["kind"] == "reject":
        assert seen.get("replacement_content") is None
    if content is not None:
        shown = dump(
            {"t": seen["target_content"], "r": seen.get("replacement_content")}
        )
        assert content["text"] in shown
    assert _cite_set(seen.get("supersedes")) == cited
    assert seen["access"].owner_scope == ALICE
    assert seen["binding"] is not None and callable(seen["receipt_writer"])
    receipts = v2_receipts(env)
    assert len(receipts) == 1 and receipts[0]["kind"] == "edit"
    assert receipts[0]["artifact_id"] == "r1"
    replay = apply_call(env, "edit", request)
    assert dump(raw(replay)) == dump(raw(first))
    assert len(calls) == 1 and len(v2_receipts(env)) == 1


# --- R3 / 72-T04: v2 maintain, lock sequencing and reviewed revisions -----------------


def test_t06_v2_maintenance_lock_and_revision_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Replay lookup and the receipt each hold the policy lock for a short span; the
    maintenance cycle runs with no route-level lock; `batch_size` is 1-1000;
    `expected_revisions` is required for apply and keyed exactly by `candidate_ids`; a
    stale reviewed revision is never swept; a replay does not run the cycle again."""
    import rush.tools.memory as memory_tool
    from rush.memory import authorization, maintenance

    env = make_env(tmp_path)
    assert env.store is not None
    bulk = tuple(f"m{index:04d}" for index in range(1000))
    for artifact_id in bulk:
        put(env.store, artifact_id, ALICE, text=f"needle bulk {artifact_id}")

    events: list[str] = []
    depth = {"n": 0}
    real_lock = authorization.hold_policy_lock

    @contextlib.contextmanager
    def tracked(*args: Any, **kwargs: Any) -> Any:
        depth["n"] += 1
        events.append("lock+")
        try:
            with real_lock(*args, **kwargs):
                yield
        finally:
            depth["n"] -= 1
            events.append("lock-")

    real_cycle = maintenance.run_maintenance_cycle

    def cycle(*args: Any, **kwargs: Any) -> Any:
        events.append(f"cycle@{depth['n']}")
        try:
            return real_cycle(*args, **kwargs)
        finally:
            events.append(f"cycle-end@{depth['n']}")

    monkeypatch.setattr(authorization, "hold_policy_lock", tracked)
    monkeypatch.setattr(memory_tool, "hold_policy_lock", tracked, raising=False)
    monkeypatch.setattr(maintenance, "run_maintenance_cycle", cycle)
    monkeypatch.setattr(memory_tool, "run_maintenance_cycle", cycle, raising=False)

    full = m_maintain(candidate_ids=bulk, batch_size=1000)
    first = apply_call(env, "maintain", full)
    assert_v2_envelope(first, "maintain", "OK")
    assert "cycle@0" in events and "cycle-end@0" in events, events
    start, end = events.index("cycle@0"), events.index("cycle-end@0")
    before_cycle, after_cycle = events[:start], events[end + 1 :]
    assert before_cycle.count("lock+") >= 1, events
    assert before_cycle.count("lock+") == before_cycle.count("lock-"), events
    assert after_cycle.count("lock+") >= 1, events
    assert [r["kind"] for r in v2_receipts(env)] == ["maintain"]

    runs = sum(1 for e in events if e.startswith("cycle@"))
    replay = apply_call(env, "maintain", full)
    assert dump(raw(replay)) == dump(raw(first))
    assert sum(1 for e in events if e.startswith("cycle@")) == runs
    assert len(v2_receipts(env)) == 1

    # Strict revision maps and batch bounds, all before any effect.
    before = snapshot(env)
    for label, request in (
        ("batch_1001", m_maintain(batch_size=1001, inv="i-b1", eff="e-b1")),
        ("batch_0", m_maintain(batch_size=0, inv="i-b2", eff="e-b2")),
        (
            "revisions_missing_for_apply",
            {
                k: v
                for k, v in m_maintain(inv="i-b3", eff="e-b3").items()
                if k != "expected_revisions"
            },
        ),
        (
            "revisions_not_a_mapping",
            {**m_maintain(inv="i-b4", eff="e-b4"), "expected_revisions": ["r1"]},
        ),
        (
            "revisions_string",
            {**m_maintain(inv="i-b5", eff="e-b5"), "expected_revisions": "r1"},
        ),
        (
            "revision_null_value",
            m_maintain(revisions={"r1": None}, inv="i-b6", eff="e-b6"),  # type: ignore[dict-item]
        ),
    ):
        refused = apply_call(env, "maintain", request)
        assert_v2_envelope(refused, "maintain", "E_INPUT")
        assert dump(raw(refused)) == dump(
            mcp_call(env, "maintain", request, cache_write=True)
        ), label
    only_zero_effects(env, before, "maintain validation")

    # A reviewed revision that no longer matches is refused and the row is not swept.
    assert (
        code(apply_call(env, "edit", m_edit(artifact_id="r1", expected_version=1)))
        == "OK"
    )
    changed_version = current_version(env, "r1")
    assert changed_version == 2
    stale = apply_call(
        env,
        "maintain",
        m_maintain(candidate_ids=("r1",), revisions={"r1": 1}, inv="i-s", eff="e-s"),
    )
    assert code(stale) == "OK", dump(raw(stale))
    assert find_key(raw(stale), "changed") == 0
    assert [c["id"] for c in find_key(raw(stale), "refused")] == ["r1"]
    assert current_version(env, "r1") == changed_version
    assert table_rows(env, "memory_artifacts", "id = 'r1'")[0]["stale"] == 0


# --- D35: the measured frame of each transport ---------------------------------------


def _bisect_min_cap(admitted: Any) -> int:
    """The smallest cap `admitted(cap)` accepts (1 is refused; admission is monotone)."""
    assert not admitted(1), "a cap of 1 must be refused before any effect"
    hi = 2
    while not admitted(hi):
        hi *= 2
        assert hi < 2**24, "no cap up to 16 MiB was admitted"
    lo = hi // 2
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if admitted(mid):
            hi = mid
        else:
            lo = mid
    return hi


def _frame_tokens(frame: bytes) -> int:
    from rush.memory.retrieval import DEFAULT_ENCODING, _count_tokens

    return _count_tokens(frame.decode("utf-8"), DEFAULT_ENCODING)


def _check_frame(
    parsed: dict[str, Any], frame: bytes, max_bytes: int, max_tokens: int, label: str
) -> None:
    body = parsed["raw"]
    assert body["code"] in {"OK", "E_BUDGET"}, (label, dump(body))
    assert len(frame) <= max_bytes, (label, len(frame), max_bytes)
    assert _frame_tokens(frame) <= max_tokens, (label, max_tokens)


def _frame_server(
    env: Env, operation: str, request: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    from rush.delivery.compact import canonical_json

    parsed = mcp_server_call(env, operation, request)
    return parsed, canonical_json(parsed)


def _frame_cli(
    env: Env, operation: str, request: dict[str, Any]
) -> tuple[dict[str, Any], bytes]:
    path = write_input(env.root, f"frame-{operation}", request)
    outcome = _cli_result(
        env.root, ["memory", operation, "--input", str(path), "--json"]
    )
    return json.loads(outcome.output), outcome.output.encode("utf-8")


def _frame_stdio(
    env: Env, calls: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], bytes]]:
    """One real stdio server; per call the parsed ToolResult and the JSON-RPC frame."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from mcp.types import JSONRPCResponse, TextContent

    child_env = {**os.environ}
    for key in ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA", "USERPROFILE"):
        if key in os.environ:
            child_env[key] = os.environ[key]

    async def _run() -> list[tuple[dict[str, Any], bytes]]:
        out: list[tuple[dict[str, Any], bytes]] = []
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "rush.cli", "mcp", "serve"],
            cwd=str(PROJECT_ROOT),
            env=child_env,
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            for arguments in calls:
                response = await session.call_tool("rush_memory", arguments)
                block = response.content[0]
                assert isinstance(block, TextContent), block
                # Request ids 1..9 serialize to one digit, so the frame length does not
                # depend on how many requests the SDK issued before this call.
                rpc = JSONRPCResponse(
                    jsonrpc="2.0",
                    id=1,
                    result=response.model_dump(
                        mode="json", by_alias=True, exclude_none=True
                    ),
                )
                frame = (
                    rpc.model_dump_json(by_alias=True, exclude_none=True) + os.linesep
                ).encode("utf-8")
                out.append((json.loads(block.text), frame))
        return out

    return asyncio.run(_run())


def _frame_env(tmp_path: Path) -> Env:
    env = make_env(tmp_path)
    assert env.store is not None
    for index in range(6):
        put(
            env.store,
            f"fr{index}",
            ALICE,
            text="needle frame row " + "x" * 160 + f" {index}",
        )
    return env


FRAME_IDS = {"r1", "fr0", "fr1", "fr2", "fr3", "fr4", "fr5"}
HUGE_CAP = 10**6


def _page_through(
    fetch: Any, request: dict[str, Any], max_bytes: int, max_tokens: int, label: str
) -> set[str]:
    seen: list[str] = []
    cursor: str | None = None
    for page in range(30):
        body = {**request, "max_bytes": max_bytes, "max_tokens": max_tokens}
        if cursor is not None:
            body["cursor"] = cursor
        parsed, frame = fetch(body)
        _check_frame(parsed, frame, max_bytes, max_tokens, f"{label}:page{page}")
        raw_body = parsed["raw"]
        if raw_body["code"] == "E_BUDGET":
            return set(seen)
        seen.extend(i["reference"]["artifact_id"] for i in raw_body["items"])
        cursor = raw_body["next_cursor"]
        if raw_body["complete"]:
            assert cursor is None, label
            break
        assert cursor, label
    assert len(seen) == len(set(seen)), (label, seen)
    return set(seen)


@pytest.mark.parametrize(
    "transport",
    [
        pytest.param("server_in_process", id="server_in_process"),
        pytest.param("cli_json", id="cli_json"),
        pytest.param("mcp_stdio", id="mcp_stdio"),
    ],
)
def test_t06_transport_frame_admission_and_measurement(
    transport: str, tmp_path: Path
) -> None:
    """C05 / D35: admission measures the frame the caller's transport emits; a cap
    below the admitted minimum is `E_INPUT` before any effect; every admitted success
    or `E_BUDGET` frame (envelope, cursor and framing included) fits both caps."""
    env = _frame_env(tmp_path)
    before = snapshot(env)

    if transport == "mcp_stdio":
        base = {"path": str(env.root), "operation": "list"}
        request = r_list(subjects=["domain_knowledge"])
        refused = _frame_stdio(env, [{**base, "request": {**request, "max_bytes": 1}}])[
            0
        ][0]
        assert refused["raw"]["code"] == "E_INPUT"
        assert data_of(refused).get("field") == "max_bytes"
        max_bytes, max_tokens = 6000, 1500
        pages = _frame_stdio(
            env,
            [
                {
                    **base,
                    "request": {
                        **request,
                        "max_bytes": max_bytes,
                        "max_tokens": max_tokens,
                    },
                }
            ],
        )
        first_parsed, first_frame = pages[0]
        _check_frame(first_parsed, first_frame, max_bytes, max_tokens, "stdio:page0")
        first = first_parsed["raw"]
        assert first["code"] == "OK" and first["items"], dump(first)
        assert first["complete"] is False and first["next_cursor"]
        follow = _frame_stdio(
            env,
            [
                {
                    **base,
                    "request": {
                        **request,
                        "max_bytes": max_bytes,
                        "max_tokens": max_tokens,
                        "cursor": first["next_cursor"],
                    },
                }
            ],
        )[0]
        _check_frame(follow[0], follow[1], max_bytes, max_tokens, "stdio:page1")
        second_ids = [i["reference"]["artifact_id"] for i in follow[0]["raw"]["items"]]
        first_ids = [i["reference"]["artifact_id"] for i in first["items"]]
        assert second_ids and not set(first_ids) & set(second_ids)
        only_zero_effects(env, before, "stdio")
        return

    if transport == "server_in_process":
        operation = "list"
        fetch_one = lambda caps: _frame_server(
            env, "list", r_list(subjects=["domain_knowledge"], **caps)
        )
    else:
        operation = "expand"
        fetch_one = lambda caps: _frame_cli(env, "expand", r_expand(**caps))

    def admitted_bytes(cap: int) -> bool:
        parsed, _ = fetch_one({"max_bytes": cap, "max_tokens": HUGE_CAP})
        if parsed["raw"]["code"] == "E_INPUT":
            assert data_of(parsed).get("field") == "max_bytes", dump(parsed["raw"])
            return False
        return True

    def admitted_tokens(cap: int) -> bool:
        parsed, _ = fetch_one({"max_bytes": HUGE_CAP, "max_tokens": cap})
        if parsed["raw"]["code"] == "E_INPUT":
            assert data_of(parsed).get("field") == "max_tokens", dump(parsed["raw"])
            return False
        return True

    min_bytes = _bisect_min_cap(admitted_bytes)
    min_tokens = _bisect_min_cap(admitted_tokens)
    only_zero_effects(env, before, f"{transport} admission")

    for cap in sorted({min_bytes, min_bytes + 1, min_bytes * 2, min_bytes * 4}):
        parsed, frame = fetch_one({"max_bytes": cap, "max_tokens": HUGE_CAP})
        _check_frame(parsed, frame, cap, HUGE_CAP, f"{transport}:bytes={cap}")
    for cap in sorted({min_tokens, min_tokens + 1, min_tokens * 2, min_tokens * 4}):
        parsed, frame = fetch_one({"max_bytes": HUGE_CAP, "max_tokens": cap})
        _check_frame(parsed, frame, HUGE_CAP, cap, f"{transport}:tokens={cap}")

    if operation == "list":
        ids_seen = _page_through(
            lambda body: _frame_server(env, "list", body),
            r_list(subjects=["domain_knowledge"]),
            min_bytes * 4,
            HUGE_CAP,
            "pages",
        )
        assert ids_seen == FRAME_IDS, ids_seen
    only_zero_effects(env, before, f"{transport} measurement")


def data_of(parsed: dict[str, Any]) -> dict[str, Any]:
    value = parsed["raw"].get("data")
    return value if isinstance(value, dict) else {}


# --- R4: type-aware event identity (re-gate SQL correction) --------------------------


def _legacy_event_row(env: Env, artifact_id: str, event_id: Any) -> None:
    assert env.store is not None
    put(env.store, artifact_id, ALICE, text="legacy event row")
    _drop_event_guards(env)
    project_id, worktree_id = _ids_of(env)
    _set_content(
        env,
        artifact_id,
        {
            "project_id": project_id,
            "worktree_id": worktree_id,
            "task_id": "t1",
            "event_id": event_id,
            "text": "raw sql",
        },
    )


@pytest.mark.parametrize(
    ("legacy_value", "label"),
    [
        pytest.param(["5"], "array", id="array"),
        pytest.param({"a": 1}, "object", id="object"),
        pytest.param(5, "integer", id="integer"),
        pytest.param("", "empty", id="empty"),
        pytest.param(None, "null", id="null"),
        pytest.param(True, "boolean", id="boolean"),
    ],
)
def test_t06_event_identity_type_aware_expressions(
    legacy_value: Any, label: str, tmp_path: Path
) -> None:
    """A legacy non-string `event_id` never collides with a string event whose text
    equals its JSON form, and the immutability trigger refuses turning one into the
    other (the SQL compares `json_type` as well as the extracted value)."""
    env = make_env(tmp_path)
    _legacy_event_row(env, "legacy-ev", legacy_value)
    TypedArtifactStore(env.root)  # the constructor recreates the guards
    rows = row_count(env)
    as_text = json.dumps(legacy_value)
    created = apply_call(
        env,
        "write",
        m_write(inv="i-ev", eff="e-ev", content=_event(env, event_id=as_text)),
    )
    assert code(created) == "OK", (label, dump(raw(created)))
    assert row_count(env) == rows + 1
    project_id, worktree_id = _ids_of(env)
    retyped = json.dumps(
        {
            "project_id": project_id,
            "worktree_id": worktree_id,
            "task_id": "t1",
            "event_id": "now-a-string",
            "text": "retyped",
        }
    )
    with (
        contextlib.closing(sqlite3.connect(env.db)) as conn,
        pytest.raises(sqlite3.IntegrityError, match="event_identity_immutable"),
    ):
        conn.execute(
            "UPDATE memory_artifacts SET content = ? WHERE id = 'legacy-ev'",
            (retyped,),
        )


# --- G15 failure classes ---------------------------------------------------------------

_OPAQUE_NAMES = (
    "C:\\Windows\\system32\\x",
    "..\\..\\escape",
    "/etc/passwd",
    "a\\b",
    "\\\\server\\share\\x",
    "x/../../y",
    "CON",
    "a:b",
    "..",
)


def _changed_outside(
    before: dict[str, str], after: dict[str, str], prefix: str
) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key) and not key.startswith(prefix)
    )


def _g15_opaque_import_provenance(tmp_path: Path) -> None:
    """Foreign provenance is opaque text: Windows drive and backslash traversal forms and
    POSIX literal-backslash names are recorded verbatim and never become a path."""
    env = _import_env(tmp_path)
    records = [_rec(name, source=name) for name in _OPAQUE_NAMES]
    before = digest_tree(tmp_path, skip=(".git/",))
    preview = _preview(env, records)
    result = _apply(env, records, preview, inv="i-g15", eff="e-g15", digest=_hex(900))
    mappings = find_key(result, "mappings")
    assert {m["foreign_origin_id"] for m in mappings} == set(_OPAQUE_NAMES)
    after = digest_tree(tmp_path, skip=(".git/",))
    assert _changed_outside(before, after, f"{env.root.name}/.rush/") == []


def _g15_opaque_selectors(tmp_path: Path) -> None:
    """`sources`, `invocation_id`, `effect_id` and `artifact_id` that look like paths are
    opaque labels on every OS: they are stored and filtered verbatim and touch nothing
    outside the store."""
    data_root = default_data_root()
    label = "C:\\data\\..\\x"
    root = tmp_path / "opaque"
    root.mkdir()
    _git_init(root)
    root = root.resolve()
    env = Env(root=root, data_root=data_root, store=None, mode="policy")
    register_project(root, data_root=data_root)
    env.grants["alice"] = grant(env, data_root, ALICE, sources=(label,))
    env.store = TypedArtifactStore(root)
    before = digest_tree(tmp_path, skip=(".git/",))
    wrote = apply_call(
        env,
        "write",
        m_write(inv="..\\..\\inv", eff="C:\\eff", source=label, text="needle opaque"),
    )
    assert code(wrote) == "OK", dump(raw(wrote))
    new_id = ids(wrote)[0]
    listed = call(env, "list", r_list(sources=[label]))
    assert ids(listed) == [new_id]
    assert raw(listed)["items"][0]["reference"]["source"] == label
    receipt = v2_receipts(env)[0]
    assert (
        receipt["invocation_id"] == "..\\..\\inv" and receipt["effect_id"] == "C:\\eff"
    )
    after = digest_tree(tmp_path, skip=(".git/",))
    assert _changed_outside(before, after, f"{env.root.name}/.rush/") == []


def _g15_posix_literal_backslash(tmp_path: Path) -> None:
    """On POSIX a backslash in the project path is a literal filename character, not a
    separator: the call neither splits it into `a/b` nor creates anything."""
    literal = tmp_path / "a\\b"
    literal.mkdir()
    _git_init(literal)
    result = MemoryTool().run(
        literal, operation="list", request=r_list(None, sources=[SRC])
    )
    assert code(result) == "OK" and raw(result)["items"] == []
    assert not (tmp_path / "a").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a\\b"]
    assert not (literal / ".rush").exists()


def _g15_windows_backslash_separator(tmp_path: Path) -> None:
    """On Windows a backslash is a separator: a dotted alias of the project root reads the
    same store as its canonical spelling and creates nothing."""
    env = make_env(tmp_path)
    alias = str(env.root.parent) + "\\." + "\\" + env.root.name
    canonical = call(env, "list", r_list())
    before = snapshot(env)
    aliased = MemoryTool().run(Path(alias), operation="list", request=r_list())
    assert ids(aliased) == ids(canonical) and code(aliased) == "OK"
    only_zero_effects(env, before, "windows alias")


def _g15_discriminator_types(tmp_path: Path) -> None:
    """A list or dict where an enum or discriminator belongs is a controlled `E_INPUT`
    (in-process and MCP agree), never a `TypeError` from an unhashable membership test."""
    env = make_env(tmp_path)
    before = snapshot(env)
    bad_values: tuple[Any, ...] = (["x"], {"a": 1})
    cases: list[tuple[str, str, Any]] = [
        ("schema_version", "list", lambda v: {**r_list(), "schema_version": v}),
        ("subjects_entry", "list", lambda v: r_list(subjects=[v])),
        (
            "owner_kind",
            "list",
            lambda v: {**r_list(), "owner_scope": {"kind": v, "id": "alice"}},
        ),
        ("archive_mode", "list", lambda v: r_list(archive_mode=v)),
        ("retrieval", "list", lambda v: r_list(retrieval=v)),
        ("trust_tiers_entry", "list", lambda v: r_list(trust_tiers=[v])),
        ("freshness_entry", "list", lambda v: r_list(freshness=[v])),
        ("expand_representation", "expand", lambda v: r_expand(representation=v)),
        ("history_representation", "history", lambda v: r_history(representation=v)),
        ("explain_subjects_entry", "explain", lambda v: r_explain(subjects=[v])),
        ("link_kind", "link", lambda v: m_link(kind=v)),
        ("maintain_task", "maintain", lambda v: m_maintain(task=v)),
        ("write_subject", "write", lambda v: m_write(subject=v)),
        (
            "correction_kind",
            "edit",
            lambda v: m_edit(correction={"kind": v, "reason": "r"}),
        ),
    ]
    for field, operation, build in cases:
        for value in bad_values:
            body = build(value)
            inproc = call(env, operation, body, perms=PERM_W)
            over_mcp = mcp_call(env, operation, body, cache_write=True)
            assert_v2_envelope(inproc, operation, "E_INPUT")
            assert dump(raw(inproc)) == dump(raw(over_mcp)), (field, value)
    # The top-level operation itself: a controlled error result, never an exception.
    for value in bad_values:
        outcome = MemoryTool().run(env.root, operation=value)  # type: ignore[arg-type]
        assert outcome["status"] == "error", value
        from rush.mcp_support.request_models import validate_and_normalize

        rejected = validate_and_normalize(
            "rush_memory", {"path": str(env.root), "operation": value}
        )
        assert rejected.rejected, value
    only_zero_effects(env, before, "discriminator types")


_SURROGATE = "\ud800"


def _g15_unencodable_os_input(tmp_path: Path) -> None:
    """A lone surrogate in a path, id, cursor, source, owner id or label is `E_INPUT`
    before any OS or SQLite call; a lone surrogate inside stored content stays valid."""
    env = make_env(tmp_path)
    before = snapshot(env)
    sur = _SURROGATE
    cases: list[tuple[str, str, dict[str, Any]]] = [
        ("expand_artifact_id", "expand", r_expand(artifact_id="r1" + sur)),
        ("write_invocation_id", "write", m_write(inv="i" + sur)),
        ("write_effect_id", "write", m_write(eff="e" + sur)),
        ("list_cursor", "list", {**r_list(), "cursor": "m2." + sur}),
        ("list_sources_entry", "list", r_list(sources=["s" + sur])),
        (
            "list_owner_id",
            "list",
            {**r_list(), "owner_scope": {"kind": "user", "id": "a" + sur}},
        ),
        ("write_source", "write", m_write(source="s" + sur)),
        ("ask_query", "ask", r_ask(query="needle" + sur)),
        (
            "edit_correction_reason",
            "edit",
            m_edit(correction={"kind": "correct", "reason": "r" + sur}),
        ),
        ("link_origin_ref", "link", {**m_link(), "origin_ref": "o" + sur}),
    ]
    for label, operation, body in cases:
        inproc = call(env, operation, body, perms=PERM_W)
        over_mcp = mcp_call(env, operation, body, cache_write=True)
        assert_v2_envelope(inproc, operation, "E_INPUT")
        assert dump(raw(inproc)) == dump(raw(over_mcp)), label
    only_zero_effects(env, before, "unencodable input")
    bad_path = MemoryTool().run(
        "proj" + sur,  # type: ignore[arg-type]  # deliberate unencodable path
        operation="list",
        request=r_list(None, sources=[SRC]),
    )
    assert code(bad_path) == "E_INPUT" and data(bad_path)["field"] == "path"
    stored = apply_call(
        env,
        "write",
        m_write(inv="i-ok", eff="e-ok", content={"text": "needle " + sur + " kept"}),
    )
    assert code(stored) == "OK"
    assert "\\ud800" in dump(
        raw(call(env, "expand", r_expand(artifact_id=ids(stored)[0])))
    )


def _deep(depth: int) -> Any:
    node: Any = []
    for _ in range(depth):
        node = [node]
    return node


def _g15_recursive_untrusted_data(tmp_path: Path) -> None:
    """Deeply nested or cyclic request, import and JSON-file data is a controlled
    `E_INPUT` / `ClickException` before any effect, never an uncaught `RecursionError`.
    The validation boundary and the CLI parse boundary are exercised separately."""
    env = make_env(tmp_path / "v")
    before = snapshot(env)
    deep = _deep(100_000)
    cyclic: dict[str, Any] = {"text": "cycle"}
    cyclic["self"] = cyclic
    for label, content in (("deep", {"text": "x", "deep": deep}), ("cyclic", cyclic)):
        result = call(
            env,
            "write",
            m_write(inv=f"i-{label}", eff=f"e-{label}", content=content),
            perms=PERM_W,
        )
        assert_v2_envelope(result, "write", "E_INPUT")
    over_mcp = mcp_call(
        env,
        "write",
        m_write(inv="i-mcp", eff="e-mcp", content={"text": "x", "deep": deep}),
        cache_write=True,
    )
    assert_v2_envelope(over_mcp, "write", "E_INPUT")
    only_zero_effects(env, before, "deep request")

    imp = _import_env(tmp_path / "imp")
    snap = snapshot(imp)
    deep_record = _rec("deep", content={"text": "x", "deep": deep})
    _expect_policy_error("E_INPUT", None, lambda: _preview(imp, [deep_record]))
    good = _preview(imp, [_rec("ok")])
    _expect_policy_error(
        "E_INPUT",
        None,
        lambda: _apply(imp, [deep_record], good, inv="i", eff="e", digest=_hex(901)),
    )
    only_zero_effects(imp, snap, "deep import")

    calls: list[Any] = []
    real_run = MemoryTool.run
    patch = pytest.MonkeyPatch()
    try:

        def spy_run(self: Any, *a: Any, **k: Any) -> Any:
            calls.append(k)
            return real_run(self, *a, **k)

        patch.setattr(MemoryTool, "run", spy_run)
        nested = tmp_path / "nested.json"
        nested.write_text("[" * 200_000 + "]" * 200_000, encoding="utf-8")
        outcome = _cli_result(
            env.root, ["memory", "expand", "--input", str(nested), "--json"]
        )
    finally:
        patch.undo()
    assert outcome.exit_code == 1, outcome.output
    assert "Error" in outcome.output and "Traceback" not in outcome.output
    assert not isinstance(outcome.exception, RecursionError)
    assert calls == []


def _g15_cleanup_masking(
    cleanup: str, primary: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cleanup failure (temp unlink, directory fsync, handle close, rmdir) never masks
    the primary outcome of an absent-store import: the primary code and reason survive,
    a post-commit cleanup failure still succeeds, a post-link durability failure is
    `publication_unconfirmed`, and a validated committed database is never unlinked."""
    import shutil

    from rush.memory.authorization import MemoryPolicyError

    env = _import_env(tmp_path, store=False)
    records = [_rec("f1")]
    preview = _preview(env, records)
    access = _write_access(env)
    if cleanup == "rmdir":
        # The only rmdir cleanup is of a `.rush` the import itself created, so the
        # directory that registration made must not exist when the apply starts.
        shutil.rmtree(env.root / ".rush")
    real = {
        name: getattr(os, name)
        for name in ("unlink", "remove", "rmdir", "fsync", "close", "open", "link")
    }
    dir_fds: set[int] = set()
    state: dict[str, Any] = {"linked": False, "hits": []}

    def fake_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        fd = real["open"](path, flags, *args, **kwargs)
        if flags & getattr(os, "O_DIRECTORY", 0):
            dir_fds.add(fd)
        return fd

    def fake_link(src: Any, dst: Any, *args: Any, **kwargs: Any) -> Any:
        if primary == "unsupported":
            raise OSError(1, "Operation not permitted")
        if primary == "exists":
            (env.root / ".rush" / "memory.db").write_bytes(
                b"planted by a racing writer"
            )
        out = real["link"](src, dst, *args, **kwargs)
        state["linked"] = True
        return out

    def is_temp(path: Any) -> bool:
        try:
            return "memory.db.import-" in os.fsdecode(path)
        except TypeError:
            return False

    def failing_remove(name: str) -> Any:
        def inner(path: Any, *args: Any, **kwargs: Any) -> Any:
            if cleanup == "unlink" and is_temp(path):
                state["hits"].append("unlink")
                raise OSError(5, "injected unlink failure")
            return real[name](path, *args, **kwargs)

        return inner

    def fake_rmdir(path: Any, *args: Any, **kwargs: Any) -> Any:
        if cleanup == "rmdir":
            state["hits"].append("rmdir")
            raise OSError(39, "injected rmdir failure")
        return real["rmdir"](path, *args, **kwargs)

    def fake_fsync(fd: int) -> Any:
        if cleanup == "fsync" and state["linked"] and fd in dir_fds:
            state["hits"].append("fsync")
            raise OSError(5, "injected fsync failure")
        return real["fsync"](fd)

    def fake_close(fd: int) -> Any:
        was_dir = fd in dir_fds
        real["close"](fd)
        dir_fds.discard(fd)
        if cleanup == "close" and was_dir and state["linked"]:
            state["hits"].append("close")
            raise OSError(9, "injected close failure")

    outcome: Any = None
    with monkeypatch.context() as patch:
        patch.setattr(os, "open", fake_open)
        patch.setattr(os, "link", fake_link)
        patch.setattr(os, "unlink", failing_remove("unlink"))
        patch.setattr(os, "remove", failing_remove("remove"))
        patch.setattr(os, "rmdir", fake_rmdir)
        patch.setattr(os, "fsync", fake_fsync)
        patch.setattr(os, "close", fake_close)

        def run() -> Any:
            return _apply(
                env,
                records,
                preview,
                inv="i-cm",
                eff="e-cm",
                digest=_hex(910),
                access=access,
            )

        if primary == "none" and cleanup == "fsync":
            with pytest.raises(MemoryPolicyError) as caught:
                run()
            assert caught.value.reason == "publication_unconfirmed"
        elif primary == "none":
            outcome = run()
            assert find_key(outcome, "mappings"), cleanup
        else:
            want = (
                ("E_UNAVAILABLE", "publication_unsupported")
                if primary == "unsupported"
                else ("E_VERSION", "store_changed")
            )
            with pytest.raises(MemoryPolicyError) as caught:
                run()
            assert (caught.value.code, caught.value.reason) == want
    required_hits = {
        ("unlink", "none"),
        ("unlink", "unsupported"),
        ("unlink", "exists"),
        ("rmdir", "unsupported"),
        ("rmdir", "exists"),
        ("fsync", "none"),
        ("close", "none"),
    }
    if (cleanup, primary) in required_hits:
        assert state["hits"], f"the {cleanup} fault was never reached ({primary})"
    if primary == "exists":
        assert env.db.read_bytes() == b"planted by a racing writer"
    elif primary == "unsupported":
        assert not env.db.exists()
    else:
        assert env.db.exists()
        reopened = TypedArtifactStore(env.root)
        assert reopened is not None


def _g15_two_artifact_views(tmp_path: Path) -> None:
    """The scope gate sees a protected guard change in the staged blob and in the
    worktree file independently: changed assert, removed, duplicated, symlinked and
    unparseable protected source are all refused, the real T06 edits pass in both
    views, and the real worktree's index is never touched."""
    gate = PROJECT_ROOT / "scripts" / "scope_gate.py"
    modules = (
        "tests/test_memory_authorization.py",
        "tests/test_phase72_memory_correctness.py",
    )
    git_env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_AUTHOR_NAME": "t06",
        "GIT_AUTHOR_EMAIL": "t06@example.invalid",
        "GIT_COMMITTER_NAME": "t06",
        "GIT_COMMITTER_EMAIL": "t06@example.invalid",
    }

    def git(
        cwd: Path, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            ["git", *args], cwd=cwd, env=git_env, check=check, capture_output=True
        )

    def index_state() -> tuple[bytes, bytes]:
        path = (
            git(PROJECT_ROOT, "rev-parse", "--git-path", "index")
            .stdout.decode()
            .strip()
        )
        index = Path(path) if Path(path).is_absolute() else PROJECT_ROOT / path
        status = git(PROJECT_ROOT, "status", "--porcelain=v1", "-z").stdout
        return (index.read_bytes() if index.exists() else b"", status)

    real_before = index_state()
    head = {m: git(PROJECT_ROOT, "show", f"HEAD:{m}").stdout for m in modules}
    current = {m: (PROJECT_ROOT / m).read_bytes() for m in modules}

    repo = tmp_path / "gate-repo"
    repo.mkdir()
    git(repo, "init", "--initial-branch=main", "-q")
    for module, data_bytes in head.items():
        (repo / module).parent.mkdir(parents=True, exist_ok=True)
        (repo / module).write_bytes(data_bytes)
    git(repo, "add", "--", *modules)
    git(repo, "commit", "-q", "-m", "head")
    baseline = tmp_path / "baseline.json"

    def gate_run(*args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(
            [sys.executable, str(gate), *args],
            cwd=repo,
            env=git_env,
            capture_output=True,
            check=False,
        )

    recorded = gate_run("record", "--task", "72-T06:g15", "--out", str(baseline))
    assert recorded.returncode == 0, recorded.stderr.decode()

    def reset() -> None:
        git(repo, "reset", "-q", "--hard", "HEAD")
        git(repo, "clean", "-q", "-fd")

    def check(*extra: str) -> subprocess.CompletedProcess[bytes]:
        return gate_run(
            "check", "--baseline", str(baseline), "--allowed", *modules, *extra
        )

    def place(
        module: str, data_bytes: bytes, *, view: str, symlink: bool = False
    ) -> None:
        target = repo / module
        if symlink:
            target.unlink()
            target.symlink_to(Path(module).name + ".real")
            (repo / (module + ".real")).write_bytes(data_bytes)
        else:
            target.write_bytes(data_bytes)
        if view == "staged":
            git(
                repo,
                "add",
                "-f",
                "--",
                module,
                *([module + ".real"] if symlink else []),
            )
            target.unlink()
            target.write_bytes(current[module])

    # The real T06 edits keep every guard list, in the worktree and in the index.
    for view in ("worktree", "staged"):
        reset()
        for module in modules:
            place(module, current[module], view=view)
        passed = check()
        assert passed.returncode == 0, (view, passed.stderr.decode())

    guard = "test_t01_fix1_promote_refuses_payload_mismatched_row"
    module = "tests/test_phase72_memory_correctness.py"

    def span(data_bytes: bytes) -> tuple[int, int]:
        import ast

        tree = ast.parse(data_bytes)
        node = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == guard
        )
        assert node.end_lineno is not None
        return node.lineno - 1, node.end_lineno

    def mutate(kind: str) -> bytes:
        lines = current[module].decode("utf-8").split("\n")
        start, end = span(current[module])
        body = lines[start:end]
        if kind == "assert_changed":
            index = next(
                i for i, line in enumerate(body) if line.lstrip().startswith("assert ")
            )
            body[index] = body[index].replace("assert ", "assert True or ", 1)
            lines[start:end] = body
        elif kind == "removed":
            lines[start:end] = []
        elif kind == "duplicated":
            lines[end:end] = ["", ""] + body
        elif kind == "unparseable":
            lines.append("def broken(:")
        return "\n".join(lines).encode("utf-8")

    for kind, expected in (
        ("assert_changed", 1),
        ("removed", 1),
        ("duplicated", 1),
        ("unparseable", 2),
        ("symlinked", 1),
    ):
        for view in ("worktree", "staged"):
            reset()
            if kind == "symlinked":
                place(module, current[module], view=view, symlink=True)
            else:
                place(module, mutate(kind), view=view)
            refused = check(module + ".real") if kind == "symlinked" else check()
            assert refused.returncode == expected, (
                kind,
                view,
                refused.returncode,
                refused.stderr.decode(),
            )
            assert module.encode() in refused.stderr or kind == "unparseable", (
                kind,
                view,
            )
    reset()
    assert index_state() == real_before


_G15_CLEANUPS = ("unlink", "rmdir", "fsync", "close")
_G15_PRIMARIES = ("none", "unsupported", "exists")
_G15_CASES = [
    pytest.param(
        "opaque_import_provenance", id="cross_os_paths-opaque_import_provenance"
    ),
    pytest.param("opaque_selectors", id="cross_os_paths-opaque_selectors"),
    pytest.param(
        "posix_literal_backslash",
        id="cross_os_paths-posix_literal_backslash",
        marks=pytest.mark.posix_only,
    ),
    pytest.param(
        "windows_backslash_separator",
        id="cross_os_paths-windows_backslash_separator",
        marks=pytest.mark.windows_only,
    ),
    pytest.param("discriminator_types", id="discriminator_types"),
    pytest.param("unencodable_os_input", id="unencodable_os_input"),
    pytest.param("recursive_untrusted_data", id="recursive_untrusted_data"),
    pytest.param("two_artifact_views", id="two_artifact_views"),
    *[
        pytest.param(
            f"cleanup:{cleanup}:{primary}",
            id=f"cleanup_masking-{cleanup}-{primary}",
            marks=pytest.mark.posix_only,
        )
        for cleanup in _G15_CLEANUPS
        for primary in _G15_PRIMARIES
    ],
]


@pytest.mark.parametrize("failure_class", _G15_CASES)
def test_t06_g15_failure_classes(
    failure_class: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if failure_class.startswith("cleanup:"):
        _, cleanup, primary = failure_class.split(":")
        _g15_cleanup_masking(cleanup, primary, tmp_path, monkeypatch)
        return
    {
        "opaque_import_provenance": _g15_opaque_import_provenance,
        "opaque_selectors": _g15_opaque_selectors,
        "posix_literal_backslash": _g15_posix_literal_backslash,
        "windows_backslash_separator": _g15_windows_backslash_separator,
        "discriminator_types": _g15_discriminator_types,
        "unencodable_os_input": _g15_unencodable_os_input,
        "recursive_untrusted_data": _g15_recursive_untrusted_data,
        "two_artifact_views": _g15_two_artifact_views,
    }[failure_class](tmp_path)


# --- G15 class 7: the preservation oracle is sensitive to every captured component -----


def _oracle_mutations() -> list[Any]:
    """(id, mutate(env), marks): each mutates exactly one component the oracle captures
    and returns the snapshot to compare against (None: the pristine baseline)."""

    def file_added(env: Env) -> dict[str, Any] | None:
        (env.root / "notes.txt").write_bytes(b"aaaa")
        return None

    def file_bytes(env: Env) -> dict[str, Any] | None:
        (env.root / "README.local").write_bytes(b"aaaa")
        reference = snapshot(env)
        (env.root / "README.local").write_bytes(b"aaab")
        return reference

    def file_removed(env: Env) -> dict[str, Any] | None:
        (env.root / "gone.txt").write_bytes(b"x")
        reference = snapshot(env)
        (env.root / "gone.txt").unlink()
        return reference

    def dir_added(env: Env) -> dict[str, Any] | None:
        (env.root / "emptydir").mkdir()
        return None

    def symlink_retargeted(env: Env) -> dict[str, Any] | None:
        (env.root / "link").symlink_to("target-one")
        reference = snapshot(env)
        (env.root / "link").unlink()
        (env.root / "link").symlink_to("target-two")
        return reference

    def data_root_bytes(env: Env) -> dict[str, Any] | None:
        marker = env.data_root / "marker.bin"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_bytes(b"\x00\x01")
        reference = snapshot(env)
        marker.write_bytes(b"\x00\x02")
        return reference

    def sql(env: Env, statement: str) -> None:
        with contextlib.closing(sqlite3.connect(env.db)) as conn:
            conn.execute(statement)
            conn.commit()

    def db_row(env: Env) -> dict[str, Any] | None:
        sql(env, "UPDATE memory_artifacts SET stale = 1 WHERE id = 'r1'")
        return None

    def db_version(env: Env) -> dict[str, Any] | None:
        sql(
            env,
            "UPDATE memory_artifact_versions SET content = content || ' ' "
            "WHERE artifact_id = 'r1'",
        )
        return None

    def db_receipt(env: Env) -> dict[str, Any] | None:
        sql(
            env,
            "INSERT INTO mutation_receipts (operation_id, artifact_id, kind, "
            "revision, payload, created_at) VALUES ('oracle', NULL, 'write', NULL, "
            "'{}', 0)",
        )
        return None

    def db_index(env: Env) -> dict[str, Any] | None:
        sql(env, "CREATE INDEX t06_oracle_probe ON memory_artifacts(created_at)")
        reference = snapshot(env)
        sql(env, "DROP INDEX t06_oracle_probe")
        sql(env, "CREATE INDEX t06_oracle_probe ON memory_artifacts(source)")
        return reference

    def db_trigger(env: Env) -> dict[str, Any] | None:
        sql(
            env,
            "CREATE TRIGGER t06_oracle_probe BEFORE UPDATE ON memory_artifacts "
            "BEGIN SELECT 1; END",
        )
        return None

    rows = [
        ("file_added", file_added, ()),
        ("file_bytes", file_bytes, ()),
        ("file_removed", file_removed, ()),
        ("dir_added", dir_added, ()),
        ("symlink_retargeted", symlink_retargeted, (pytest.mark.posix_only,)),
        ("data_root_bytes", data_root_bytes, ()),
        ("db_row", db_row, ()),
        ("db_version", db_version, ()),
        ("db_receipt", db_receipt, ()),
        ("db_index", db_index, ()),
        ("db_trigger", db_trigger, ()),
    ]
    return [pytest.param(name, fn, id=name, marks=marks) for name, fn, marks in rows]


@pytest.mark.parametrize(("component", "mutate"), _oracle_mutations())
def test_t06_preservation_oracle_self_check(
    component: str, mutate: Any, tmp_path: Path
) -> None:
    """The zero-effect oracle (`snapshot`) differs after a change to each component it
    captures -- file bytes, symlink target, file-list membership, rows, versions,
    receipts and index or trigger definitions -- so a green "unchanged" assertion cannot
    hide that component changing."""
    env = make_env(tmp_path)
    baseline = snapshot(env)
    assert snapshot(env) == baseline, "the oracle is stable when nothing changes"
    reference = mutate(env) or baseline
    after = snapshot(env)
    assert after != reference, f"{component}: the oracle did not see the change"
    if component.startswith("db_"):
        assert after["state"] != reference["state"], component
    if component == "file_removed":
        assert after == baseline, "removing the file restores the original snapshot"


def test_t06_preservation_oracle_keeps_captured_bytes(tmp_path: Path) -> None:
    """An inventory never turns file content into a constant: two files of different
    bytes have different digests, and the digest is of the bytes."""
    (tmp_path / "a.bin").write_bytes(b"one")
    (tmp_path / "b.bin").write_bytes(b"two")
    tree = digest_tree(tmp_path)
    assert tree["a.bin"] != tree["b.bin"]
    assert tree["a.bin"] == "file:" + hashlib.sha256(b"one").hexdigest()


@pytest.mark.posix_nonroot
def test_t06_preservation_oracle_unreadable_file_raises(tmp_path: Path) -> None:
    """A file the oracle cannot read is an error, not a masked constant."""
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"bytes the oracle must capture")
    secret.chmod(0)
    try:
        with pytest.raises(OSError):
            digest_tree(tmp_path)
    finally:
        secret.chmod(0o600)
