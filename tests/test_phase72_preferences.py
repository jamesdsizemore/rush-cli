"""72-T05: consented layered preferences and reversible migration (G5 tests).

Written from the 72-T05 design brief (sections 1-5 and the pre-gate addendum) and the
plan packet. Every T05 symbol (`PreferenceStore.resolve`/`record`/`correct`/`end_task`/
`migrate`, `PreferenceError`, `VersionBinding`, `insert_relation_tx`, `apply_correction`,
the `preference` operation, the `task_id` keyword) is imported or used inside the test
body, so this file collects at any HEAD and each test fails on its own until T05 lands.

Result shapes these tests pin (the brief states them only in prose):

* `preference` over MCP, `MemoryTool.run` and the CLI answers
  `raw == {"schema_version": 1, "operation": "preference", "code": <code>, "data": <d>}`;
  the in-process dict minus `code` is `d` (brief 3.13).
* `resolve` data: `project_id`, `worktree_id`, `task_id`, `preferences`, `layers`
  (brief 3.4 item 10). `record`/`correct`/`end_task` apply data: `applied` plus the
  brief 3.5 / 3.6.2 / 3.7 fields; their previews carry `applied: False`.
* `migrate` preview data: `applied: False`, the brief 3.8 preview keys at top level
  (`source`, `receipt`, `inserts`, `conflicts`, `publication`, `backups`) and
  `preview_digest`; apply data: `applied`, `inserted`, `inserted_count`, `receipt`,
  `publication`.
* A `PreferenceError` and its transport form carry `reason` (and `message`).
"""

from __future__ import annotations

import ast
import contextlib
import dataclasses
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.invocation import InvocationExecutor
from rush.mcp_support.tool_registry import make_tool_wrapper
from rush.memory.preference_store import PreferenceStore
from rush.memory.store import (
    MemoryArtifact,
    OwnerScope,
    TypedArtifactStore,
    legacy_owner_scope,
)
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.tools.memory import MemoryTool
from rush.workflows.projects import register_project

REPO = Path(__file__).resolve().parents[1]
REPO_SRC = REPO / "src"
PREFS = "prefs"
MIG = "migration:preference_store"
PERSONAL = "personal-preferences"
PROJECT_OPS = ("ask", "expand", "list", "write")
OVERLAY_OPS = ("overlay_read", "list", "expand", "write")
LOCKS = ("dashboard/project_locks",)
SCOPE_RANK = {"task": 0, "project": 1, "personal": 2}
TRANSPORTS = ("tool", "mcp", "cli")


# --- file and database helpers ------------------------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_tree(base: Path, *, skip: tuple[str, ...] = ()) -> dict[str, str]:
    """relative path -> sha256 of every file (and `<dir>`/`<link>` marks) under `base`."""
    out: dict[str, str] = {}
    if not base.exists():
        return out
    for path in sorted(base.rglob("*")):
        rel = path.relative_to(base).as_posix()
        if any(rel == s or rel.startswith(s + "/") for s in skip):
            continue
        if path.is_symlink():
            out[rel] = "<link>"
        elif path.is_file():
            try:
                out[rel] = _sha(path)
            except OSError:
                out[rel] = "<unreadable>"
        else:
            out[rel] = "<dir>"
    return out


def _tree(base: Path) -> list[str]:
    if not base.exists():
        return []
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*"))


def _db(root: Path) -> Path:
    return root / ".rush" / "memory.db"


def _counts(db: Path) -> dict[str, int]:
    if not db.exists():
        return {}
    with contextlib.closing(
        sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    ) as conn:
        names = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' "
                "AND sql NOT LIKE 'CREATE VIRTUAL TABLE%' ORDER BY name"
            )
        ]
        return {
            n: int(conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0])
            for n in names
        }


def _sql(db: Path, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with contextlib.closing(
        sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    ) as conn:
        conn.row_factory = sqlite3.Row
        return list(conn.execute(sql, params).fetchall())


def _pref_rows(db: Path) -> list[dict[str, Any]]:
    """Every preference row of a store, content parsed, oldest first."""
    if not db.exists():
        return []
    out = []
    for row in _sql(
        db, "SELECT * FROM memory_artifacts WHERE subject='preference' ORDER BY rowid"
    ):
        record = dict(row)
        record["content"] = json.loads(record["content"])
        out.append(record)
    return out


def _row_of(db: Path, artifact_id: str) -> dict[str, Any]:
    rows = _sql(db, "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,))
    assert len(rows) == 1, artifact_id
    record = dict(rows[0])
    record["content"] = json.loads(record["content"])
    return record


def _version_rows(db: Path, artifact_id: str) -> list[dict[str, Any]]:
    return [
        dict(r)
        for r in _sql(
            db,
            "SELECT * FROM memory_artifact_versions WHERE artifact_id = ? "
            "ORDER BY artifact_version",
            (artifact_id,),
        )
    ]


def _relations(db: Path) -> list[tuple[Any, ...]]:
    if not db.exists():
        return []
    return [
        tuple(r)
        for r in _sql(
            db,
            "SELECT source_id, source_version, target_id, target_version, kind "
            "FROM memory_relations ORDER BY sequence",
        )
    ]


def _receipts(db: Path, like: str = "%") -> list[dict[str, Any]]:
    if not db.exists():
        return []
    out = []
    for r in _sql(
        db,
        "SELECT * FROM mutation_receipts WHERE operation_id LIKE ? ORDER BY created_at",
        (like,),
    ):
        record = dict(r)
        record["payload"] = json.loads(record["payload"] or "null")
        out.append(record)
    return out


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


# --- environment --------------------------------------------------------------


@dataclasses.dataclass
class Env:
    root: Path
    data_root: Path
    owner: OwnerScope
    overlay_owner: OwnerScope
    project_grant: dict[str, Any] | None
    overlay_grant: dict[str, Any] | None
    project_id: str | None
    worktree_id: str | None

    @property
    def db(self) -> Path:
        return _db(self.root)

    @property
    def overlay_db(self) -> Path:
        return self.data_root / "user" / ".rush" / "memory.db"

    @property
    def prefs_json(self) -> Path:
        return self.root / ".rush" / "preferences.json"


def _registered(path: Path, data_root: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    register_project(path, data_root=data_root)
    return path.resolve()


def _revision(auth: Any, data_root: Path) -> int:
    return int(auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0)


def _grant(
    auth: Any,
    root: Path,
    owner: OwnerScope,
    data_root: Path,
    *,
    sources: tuple[str, ...],
    ops: tuple[str, ...],
) -> dict[str, Any]:
    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=_revision(auth, data_root),
        consent=True,
        data_root=data_root,
    )


def make_env(
    tmp_path: Path,
    name: str = "proj",
    *,
    project: bool = True,
    overlay: bool = True,
    project_ops: tuple[str, ...] = PROJECT_OPS,
    overlay_ops: tuple[str, ...] = OVERLAY_OPS,
    project_sources: tuple[str, ...] = (PREFS, MIG),
    overlay_sources: tuple[str, ...] = (PERSONAL,),
    legacy_json: dict[str, Any] | None = None,
) -> Env:
    """A registered project under the conftest-isolated HOME. `legacy_json` seeds
    `.rush/preferences.json` through the CAS JSON writer before any grant exists (no
    `memory.db` is created; the legacy `PreferenceStore.set` creates one). Grants: project owner `legacy_owner_scope(root)` and the
    separate overlay owner `user_overlay_owner_scope()`."""
    from rush.memory import authorization as auth

    data_root = default_data_root()
    root = _registered(tmp_path / name, data_root)
    if legacy_json:
        from rush.memory.transactions import CASMapTransaction

        (root / ".rush").mkdir(exist_ok=True)
        CASMapTransaction(
            file_path=root / ".rush" / "preferences.json", root_path=root
        ).update(lambda data: {**data, **legacy_json}, max_retries=20)
    owner = legacy_owner_scope(root)
    overlay_owner = auth.user_overlay_owner_scope(data_root=data_root)
    project_grant = overlay_grant = None
    if project:
        project_grant = _grant(
            auth, root, owner, data_root, sources=project_sources, ops=project_ops
        )
    if overlay:
        overlay_grant = _grant(
            auth,
            root,
            overlay_owner,
            data_root,
            sources=overlay_sources,
            ops=overlay_ops,
        )
    ids = project_grant or overlay_grant
    return Env(
        root=root,
        data_root=data_root,
        owner=owner,
        overlay_owner=overlay_owner,
        project_grant=project_grant,
        overlay_grant=overlay_grant,
        project_id=ids["project_id"] if ids else None,
        worktree_id=ids["worktree_id"] if ids else None,
    )


def _own_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> None:
    """Point HOME and the data-root variables at `home`, so the next `make_env` gets its
    own data root and overlay store instead of the earlier fixtures'."""
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "lad"))


def regrant(
    env: Env,
    which: str,
    *,
    ops: tuple[str, ...],
    sources: tuple[str, ...] | None = None,
) -> None:
    """Supersede the project or overlay grant with a changed operation/source set."""
    from rush.memory import authorization as auth

    owner = env.owner if which == "project" else env.overlay_owner
    default = (PREFS, MIG) if which == "project" else (PERSONAL,)
    issued = _grant(
        auth, env.root, owner, env.data_root, sources=sources or default, ops=ops
    )
    if which == "project":
        env.project_grant = issued
    else:
        env.overlay_grant = issued


def revoke(env: Env, which: str) -> None:
    from rush.memory import authorization as auth

    grant = env.project_grant if which == "project" else env.overlay_grant
    assert grant is not None
    auth.revoke_memory_scope(
        grant_id=grant["grant_id"],
        expected_policy_revision=_revision(auth, env.data_root),
        consent=True,
        data_root=env.data_root,
    )


def snapshot(env: Env) -> dict[str, Any]:
    """Everything a zero-effect call must leave unchanged (brief section 1: sha256 of
    every file under the project and the data root minus the lock directory, and every
    memory.db row count)."""
    return {
        "project": _digest_tree(env.root),
        "data": _digest_tree(env.data_root, skip=LOCKS),
        "counts": _counts(env.db),
        "overlay_counts": _counts(env.overlay_db),
    }


# --- drivers ------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Res:
    code: str | None
    data: dict[str, Any]
    status: str | None
    raw: dict[str, Any]

    @property
    def reason(self) -> Any:
        return self.data.get("reason")

    def dump(self) -> str:
        return _dump(self.raw)


def _res(out: Any) -> Res:
    payload = dict(out) if isinstance(out, dict) else {}
    raw = payload.get("raw")
    raw = raw if isinstance(raw, dict) else {}
    data = raw.get("data")
    return Res(
        code=raw.get("code"),
        data=data if isinstance(data, dict) else {},
        status=payload.get("status"),
        raw=raw,
    )


def _root_of(target: Env | Path) -> Path:
    return target.root if isinstance(target, Env) else target


def call(
    target: Env | Path,
    action: str,
    *,
    via: str = "tool",
    task_id: str | None = None,
    session: list[str] | None = None,
    cache_write: bool = True,
    agent_id: str | None = None,
    **request: Any,
) -> Res:
    """One `preference` action over `MemoryTool.run` (`tool`), the MCP wrapper (`mcp`)
    or the `rush memory preference` leaf (`cli`)."""
    root = _root_of(target)
    body = {"action": action, **request}
    extra: dict[str, Any] = {}
    if task_id is not None and action == "end_task":
        body["task_id"] = task_id  # the `end_task` target is a request field
    elif task_id is not None:
        extra["task_id"] = task_id
    if session is not None:
        extra["session_allowlist"] = session
    if agent_id is not None:
        extra["agent_id"] = agent_id
    if via == "tool":
        return _res(
            MemoryTool().run(
                root,
                operation="preference",
                request=body,
                permissions=ExecutionPermissions(cache_write=cache_write),
                **extra,
            )
        )
    if via == "mcp":
        tool = MemoryTool()
        executor = InvocationExecutor()
        executor.register("memory", tool.__call__)
        wrapper = make_tool_wrapper(tool, executor)
        grants = {"allow_cache_write": True} if cache_write else {}
        return _res(
            wrapper(path=root, operation="preference", request=body, **grants, **extra)
        )
    assert via == "cli", via
    request_file = root / ".rush-pref-request.json"
    request_file.write_text(json.dumps(body), encoding="utf-8")
    argv = ["memory", "preference", "--input", str(request_file), "--json"]
    for source in session or ():
        argv += ["--session", source]
    if task_id is not None and action != "end_task":
        argv += ["--task-id", task_id]
    if cache_write:
        argv.append("--allow-cache-write")
    old = os.getcwd()
    os.chdir(root)
    try:
        result = CliRunner().invoke(cli, argv)
    finally:
        os.chdir(old)
        with contextlib.suppress(OSError):
            request_file.unlink()
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        result.output
    )
    return _res(json.loads(result.output))


def rec(
    env: Env,
    key: str,
    value: Any,
    *,
    scope: str = "project",
    authority: str = "explicit",
    task_id: str | None = None,
    via: str = "tool",
    apply: bool = True,
    user_stated: bool | None = None,
    cache_write: bool = True,
    source: str | None = None,
    expires_at: float | None = None,
    attribution: str | None = None,
    **extra: Any,
) -> Res:
    request: dict[str, Any] = {
        "key": key,
        "value": value,
        "scope": scope,
        "authority": authority,
        "source": source or (PERSONAL if scope == "personal" else PREFS),
        "apply": apply,
        "user_stated": (authority == "explicit")
        if user_stated is None
        else user_stated,
    }
    if scope == "personal":
        request["owner_scope"] = env.overlay_owner.as_dict()
    if expires_at is not None:
        request["expires_at"] = expires_at
    if attribution is not None:
        request["attribution"] = attribution
    request.update(extra)
    return call(
        env, "record", via=via, task_id=task_id, cache_write=cache_write, **request
    )


def rec_ok(env: Env, key: str, value: Any, **kwargs: Any) -> dict[str, Any]:
    result = rec(env, key, value, **kwargs)
    assert result.code == "OK", (key, result.dump())
    return result.data


def resolve(
    env: Env | Path,
    *,
    key: str | None = None,
    query: str | None = None,
    via: str = "tool",
    task_id: str | None = None,
    **extra: Any,
) -> Res:
    request: dict[str, Any] = dict(extra)
    if key is not None:
        request["key"] = key
    if query is not None:
        request["query"] = query
    return call(env, "resolve", via=via, task_id=task_id, **request)


def entry(res: Res, key: str) -> dict[str, Any]:
    found = [e for e in res.data["preferences"] if e["key"] == key]
    assert len(found) == 1, (key, res.dump())
    return found[0]


def ref_view(ref: dict[str, Any]) -> tuple[Any, ...]:
    return (
        ref["artifact_id"],
        ref["artifact_version"],
        ref["scope"],
        ref["authority"],
        ref["value"],
        ref["storage"],
    )


def why_view(item: dict[str, Any]) -> list[tuple[Any, ...]]:
    return [
        (w["artifact_id"], w["artifact_version"], w["decision"]) for w in item["why"]
    ]


def expected_why(rows: list[tuple[str, str, int, str]]) -> list[tuple[Any, ...]]:
    """`(scope, artifact_id, version, decision)` rows ordered by scope rank (task,
    project, personal) then artifact id, as brief 3.4 item 8 orders `why`."""
    ordered = sorted(rows, key=lambda r: (SCOPE_RANK[r[0]], r[1]))
    return [
        (artifact_id, version, decision)
        for _s, artifact_id, version, decision in ordered
    ]


def project_denial_reason(env: Env, action: str = "resolve") -> str:
    """The actual project-layer denial for this root (D1 mode reason, else the D2
    resolve reason for the project owner)."""
    from rush.memory.retrieval import MemoryAccess, memory_policy_decision

    mode, why = memory_policy_decision(env.root)
    if mode == "unavailable":
        assert why is not None
        return why
    access, reason = MemoryAccess.resolve_with_reason(
        env.root, operation="preference", action=action, owner_scope=env.owner
    )
    assert access is None, "the project layer is not denied"
    return reason


def seed_row(
    store: TypedArtifactStore,
    artifact_id: str,
    owner: OwnerScope | None,
    *,
    key: str,
    value: Any,
    scope: str,
    authority: str = "inferred",
    applicability: str | None = None,
    source: str = PREFS,
    project_id: str | None = None,
    worktree_id: str | None = None,
    task_id: str | None = None,
    symbol_ref: str | None = None,
    content_hash: str | None = None,
) -> MemoryArtifact:
    """A DERIVED preference row written directly (STATED is reachable only by
    promotion). Task-binding and `applicability` fields are the T05 additions and are
    passed only when given."""
    content = {
        "key": key,
        "value": value,
        "scope": scope,
        "authority": authority,
        "applicability": applicability or "active",
        "project_id": project_id,
        "worktree_id": worktree_id,
        "task_id": task_id,
        "expires_at": None,
        "source": source,
        "correction_refs": [],
        "attribution": None,
    }
    fields: dict[str, Any] = {}
    if applicability is not None:
        fields["applicability"] = applicability
    if task_id is not None:
        fields.update(
            task_project_id=project_id, task_worktree_id=worktree_id, task_id=task_id
        )
    return store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject="preference",
            trust_tier="DERIVED",
            content=content,
            source=source,
            created_at=time.time(),
            symbol_ref=symbol_ref,
            content_hash=content_hash,
            owner_scope=owner,
            **fields,
        )
    )


def access_for(
    env: Env,
    action: str,
    *,
    apply: bool = False,
    personal: bool = False,
    task_id: str | None = None,
    sources: tuple[str, ...] | None = None,
) -> Any:
    """A policy `MemoryAccess` for one preference action (brief 3.1), as the route
    builds it; asserts the grant resolves."""
    from rush.memory.retrieval import MemoryAccess

    owner = env.overlay_owner if personal else env.owner
    access, reason = MemoryAccess.resolve_with_reason(
        env.root,
        operation="preference",
        action=action,
        apply=apply,
        owner_scope=owner,
        requested_sources=sources or (),
        task_id=task_id,
    )
    assert access is not None, reason
    return access


# --- R1: scope precedence ----------------------------------------------------


def test_t05_scope_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R1/B7/B9: authority before scope, then task > project > personal; an ended task
    stops applying; every case asserts the exact `why` list (brief 3.4 item 8)."""
    a = make_env(tmp_path, "proj_a")
    b = make_env(tmp_path, "proj_b")
    personal = rec_ok(a, "format", "compact", scope="personal")
    project_a = rec_ok(a, "format", "wide")
    task_a = rec_ok(a, "format", "plain", scope="task", task_id="TaskA")
    assert [d["artifact_version"] for d in (personal, project_a, task_a)] == [2, 2, 2]
    t_id, p_id, s_id = (
        task_a["artifact_id"],
        project_a["artifact_id"],
        personal["artifact_id"],
    )

    res = resolve(a, key="format", task_id="TaskA")
    assert res.code == "OK", res.dump()
    item = entry(res, "format")
    assert item["status"] == "applied"
    assert ref_view(item["selected"]) == (
        t_id,
        2,
        "task",
        "explicit",
        "plain",
        "project",
    )
    assert [ref_view(r) for r in item["applied_refs"]] == [
        (t_id, 2, "task", "explicit", "plain", "project")
    ]
    assert item["unresolved"] == [] and item["advice"] == []
    assert why_view(item) == expected_why(
        [
            ("task", t_id, 2, "selected"),
            ("project", p_id, 2, "shadowed_by_task"),
            ("personal", s_id, 2, "shadowed_by_task"),
        ]
    )

    res = resolve(a, key="format")
    item = entry(res, "format")
    assert item["status"] == "applied"
    assert ref_view(item["selected"]) == (
        p_id,
        2,
        "project",
        "explicit",
        "wide",
        "project",
    )
    assert why_view(item) == expected_why(
        [("project", p_id, 2, "selected"), ("personal", s_id, 2, "shadowed_by_project")]
    )

    res = resolve(b, key="format")
    item = entry(res, "format")
    assert item["status"] == "applied"
    assert ref_view(item["selected"]) == (
        s_id,
        2,
        "personal",
        "explicit",
        "compact",
        "personal",
    )
    assert why_view(item) == expected_why([("personal", s_id, 2, "selected")])

    ended = call(
        a,
        "end_task",
        task_id="TaskA",
        expected_versions={t_id: 2},
        apply=True,
    )
    assert ended.code == "OK", ended.dump()
    assert ended.data["applied"] is True
    assert [e["artifact_id"] for e in ended.data["ended"]] == [t_id]
    res = resolve(a, key="format", task_id="TaskA")
    item = entry(res, "format")
    assert item["status"] == "applied"
    assert ref_view(item["selected"]) == (
        p_id,
        2,
        "project",
        "explicit",
        "wide",
        "project",
    )
    assert why_view(item) == expected_why(
        [("project", p_id, 2, "selected"), ("personal", s_id, 2, "shadowed_by_project")]
    )

    # Fixture B: inferred project and task rows are advice and never override explicit.
    _own_home(monkeypatch, tmp_path / "home_fb")
    fb = make_env(tmp_path, "proj_fb")
    personal_b = rec_ok(fb, "format", "compact", scope="personal")
    project_b = rec_ok(fb, "format", "wide", authority="inferred", scope="project")
    task_b = rec_ok(
        fb, "format", "plain", authority="inferred", scope="task", task_id="TaskA"
    )
    assert project_b["artifact_version"] == 1 and task_b["artifact_version"] == 1
    res = resolve(fb, key="format", task_id="TaskA")
    item = entry(res, "format")
    assert item["status"] == "applied"
    assert ref_view(item["selected"]) == (
        personal_b["artifact_id"],
        2,
        "personal",
        "explicit",
        "compact",
        "personal",
    )
    assert sorted(ref_view(r) for r in item["advice"]) == sorted(
        [
            (project_b["artifact_id"], 1, "project", "inferred", "wide", "project"),
            (task_b["artifact_id"], 1, "task", "inferred", "plain", "project"),
        ]
    )
    assert why_view(item) == expected_why(
        [
            ("task", task_b["artifact_id"], 1, "advice_inferred"),
            ("project", project_b["artifact_id"], 1, "advice_inferred"),
            ("personal", personal_b["artifact_id"], 2, "selected"),
        ]
    )

    # Fixture C: an inferred personal row (reachable only by direct seeding, since
    # `record` refuses it) cannot replace the explicit personal rule at equal scope.
    _own_home(monkeypatch, tmp_path / "home_fc")
    fc = make_env(tmp_path, "proj_fc")
    explicit_c = rec_ok(fc, "format", "compact", scope="personal")
    seed_row(
        TypedArtifactStore(fc.data_root / "user"),
        "inf-personal",
        fc.overlay_owner,
        key="format",
        value="wide",
        scope="personal",
        authority="inferred",
        source=PERSONAL,
    )
    res = resolve(fc, key="format")
    item = entry(res, "format")
    assert item["status"] == "applied"
    assert item["selected"]["value"] == "compact"
    assert [ref_view(r) for r in item["advice"]] == [
        ("inf-personal", 1, "personal", "inferred", "wide", "personal")
    ]
    assert why_view(item) == expected_why(
        [
            ("personal", explicit_c["artifact_id"], 2, "selected"),
            ("personal", "inf-personal", 1, "advice_inferred"),
        ]
    )


# --- R2: consent and the separate overlay grant -------------------------------


def test_t05_consent_and_overlay_grant(tmp_path: Path) -> None:
    """R2/B2/B3/B4/B5/B6: a project grant alone never reads the overlay; the separate
    overlay-owner grant does, across projects; revocation returns to project-only."""
    from rush.memory import authorization as auth

    seeder = make_env(tmp_path, "seed")
    assert not seeder.overlay_db.exists()
    created = rec_ok(seeder, "format", "compact", scope="personal")
    pid = created["artifact_id"]
    assert seeder.overlay_db.exists()
    assert sorted(
        p.name for p in (seeder.data_root / "user" / ".rush").glob("*.db")
    ) == ["memory.db"]
    overlay_schema = _sql(
        seeder.overlay_db,
        "SELECT type, name, sql FROM sqlite_master ORDER BY type, name",
    )
    project_a = make_env(tmp_path, "pa", overlay=False)
    rec_ok(project_a, "other.key", "x")
    project_schema = _sql(
        project_a.db, "SELECT type, name, sql FROM sqlite_master ORDER BY type, name"
    )
    assert [tuple(r) for r in overlay_schema] == [tuple(r) for r in project_schema]

    # Project grant alone: overlay unread, every overlay route refused.
    before = snapshot(project_a)
    res = resolve(project_a, key="format")
    assert res.code == "OK", res.dump()
    personal = res.data["layers"]["personal"]
    assert personal["state"] == "denied" and personal["reason"] == "owner_not_granted"
    assert "compact" not in res.dump()
    assert all(e["selected"] is None for e in res.data["preferences"])
    assert snapshot(project_a) == before
    tool = MemoryTool()
    for operation, request in (
        ("ask", {"view": "compact"}),
        ("recall", {"view": "compact"}),
        ("list", {"view": "compact"}),
    ):
        denied = tool.run(
            project_a.root,
            operation=operation,  # type: ignore[arg-type]
            subject="preference",
            query="compact",
            owner_scope=project_a.overlay_owner.as_dict(),
            request=request,
        )
        out = _res(denied)
        assert out.code == "E_PERMISSION" and out.reason == "owner_not_granted", (
            operation
        )
        assert "compact" not in out.dump()
    expand_denied = _res(
        tool.run(
            project_a.root,
            operation="expand",
            owner_scope=project_a.overlay_owner.as_dict(),
            request={"id": pid, "version": 2},
        )
    )
    assert expand_denied.code == "E_PERMISSION"
    assert expand_denied.reason == "owner_not_granted"
    personal_write = rec(project_a, "format", "loud", scope="personal")
    assert (
        personal_write.code == "E_OWNER"
        and personal_write.reason == "owner_not_granted"
    )
    assert snapshot(project_a) == before

    # Separate overlay-owner grant: the personal rule applies across two projects.
    project_b = make_env(tmp_path, "pb")
    project_c = make_env(tmp_path, "pc")
    for env in (project_b, project_c):
        res = resolve(env, key="format")
        item = entry(res, "format")
        assert item["status"] == "applied"
        assert ref_view(item["selected"]) == (
            pid,
            2,
            "personal",
            "explicit",
            "compact",
            "personal",
        )
        assert res.data["layers"]["personal"]["state"] == "read"
        read = _res(
            tool.run(
                env.root,
                operation="ask",
                subject="preference",
                query="compact",
                owner_scope=env.overlay_owner.as_dict(),
                request={"view": "compact"},
            )
        )
        assert read.code == "OK", read.dump()
        assert [i["id"] for i in read.data["items"]] == [pid]
        paged = _res(
            tool.run(
                env.root,
                operation="expand",
                owner_scope=env.overlay_owner.as_dict(),
                request={"id": pid, "version": 2},
            )
        )
        assert paged.code == "OK", paged.dump()
    # Personal write and correction go through the overlay-owner {write} grant.
    written = rec_ok(project_b, "theme", "dark", scope="personal")
    corrected = call(
        project_b,
        "correct",
        artifact_id=written["artifact_id"],
        layer="personal",
        kind="correct",
        reason="prefer light",
        expected_version=2,
        value="light",
        user_stated=True,
        apply=True,
        owner_scope=project_b.overlay_owner.as_dict(),
    )
    assert corrected.code == "OK", corrected.dump()
    assert corrected.data["artifact_version"] == 4
    assert (
        entry(resolve(project_c, key="theme"), "theme")["selected"]["value"] == "light"
    )

    # B5/B6: no global row is copied into a project DB; only explicit personal rules
    # enter the overlay; project/task actions never touch the overlay DB.
    overlay_sha = _sha(project_b.overlay_db)
    for env in (project_a, project_b, project_c):
        if env.db.exists():
            assert (
                _sql(
                    env.db,
                    "SELECT COUNT(*) AS n FROM memory_artifacts "
                    "WHERE owner_scope_kind = 'user'",
                )[0]["n"]
                == 0
            )
    inferred = rec(project_b, "mood", "calm", scope="personal", authority="inferred")
    assert inferred.code == "E_INPUT"
    assert inferred.reason == "personal_requires_explicit"
    rec_ok(project_b, "proj.only", "p")
    rec_ok(project_b, "task.only", "t", scope="task", task_id="T9")
    rec_ok(project_b, "inferred.only", "i", authority="inferred")
    assert _sha(project_b.overlay_db) == overlay_sha

    # Revoked overlay grant: project-only, a next_action, and every overlay route refused.
    res = resolve(project_c, key="format")
    assert res.data["layers"]["personal"]["state"] == "read"
    revoke(project_c, "overlay")
    res = resolve(project_c, key="format")
    assert res.code == "OK", res.dump()
    personal = res.data["layers"]["personal"]
    assert personal["state"] == "denied" and personal["reason"] == "revoked"
    next_action = personal["next_action"]
    assert next_action["text"] == (
        "Personal overlay not applied (revoked): grant overlay_read and list on owner "
        f"user:{project_c.overlay_owner.id} for this project."
    )
    assert "command" in next_action
    assert "compact" not in res.dump()
    assert res.data["layers"]["project"]["state"] == "read"
    gone = _res(
        tool.run(
            project_c.root,
            operation="expand",
            owner_scope=project_c.overlay_owner.as_dict(),
            request={"id": pid, "version": 2},
        )
    )
    assert gone.code == "E_PERMISSION" and gone.reason == "revoked"
    revoked_write = rec(project_c, "theme", "x", scope="personal")
    assert revoked_write.code == "E_PERMISSION" and revoked_write.reason == "revoked"
    assert auth.load_policy_readonly(data_root=project_c.data_root)["state"] == "ok"

    # Expansion needs the overlay `expand` operation: a grant without it refuses.
    project_d = make_env(tmp_path, "pd", overlay_ops=("overlay_read", "list", "write"))
    no_expand = _res(
        tool.run(
            project_d.root,
            operation="expand",
            owner_scope=project_d.overlay_owner.as_dict(),
            request={"id": pid, "version": 2},
        )
    )
    assert no_expand.code == "E_PERMISSION"
    assert no_expand.reason == "operation_not_granted"


@pytest.mark.parametrize("via", TRANSPORTS)
@pytest.mark.parametrize(
    "root_kind",
    [
        pytest.param("overlay_root", id="overlay_root"),
        pytest.param("overlay_subdir", id="overlay_subdir"),
        pytest.param("symlink", id="symlink", marks=pytest.mark.posix_only),
    ],
)
@pytest.mark.parametrize("apply", [False, True], ids=["preview", "apply"])
@pytest.mark.parametrize(
    "action", ["resolve", "record", "correct", "end_task", "migrate"]
)
def test_t05_overlay_storage_root_preference_cells(
    action: str, apply: bool, root_kind: str, via: str, tmp_path: Path
) -> None:
    """R2 row 1a / B14: a `path` equal to or under the overlay storage root is refused
    for every preference action on MCP, CLI and `MemoryTool.run`, previews and applies
    (`user_stated=True`) alike: `E_PERMISSION overlay_storage_root`, no overlay value in
    the result, the overlay DB and the file list under `<data_root>/user` unchanged."""
    env = make_env(tmp_path, "holder")
    rec_ok(env, "p1.key", "p1-secret", scope="personal")
    overlay_root = env.data_root / "user"
    (overlay_root / "sub").mkdir(exist_ok=True)
    if root_kind == "overlay_root":
        target = overlay_root
    elif root_kind == "overlay_subdir":
        target = overlay_root / "sub"
    else:
        link = tmp_path / "overlay-link"
        link.symlink_to(overlay_root)
        target = link
    requests_by_action: dict[str, dict[str, Any]] = {
        "resolve": {"key": "p1.key"},
        "record": {
            "key": "k",
            "value": "v",
            "scope": "project",
            "authority": "explicit",
            "source": PREFS,
        },
        "correct": {
            "artifact_id": "x",
            "layer": "project",
            "kind": "correct",
            "reason": "r",
            "expected_version": 1,
            "value": "v",
        },
        "end_task": {"task_id": "T", "expected_versions": {}},
        "migrate": {"preview_digest": "0" * 64},
    }
    request = requests_by_action[action]
    if action != "resolve":
        request = {**request, "apply": apply, "user_stated": True}
    before_sha = _sha(env.overlay_db)
    before_tree = _tree(overlay_root)
    result = call(target, action, via=via, **request)
    assert result.code == "E_PERMISSION", result.dump()
    assert result.reason == "overlay_storage_root"
    assert "p1-secret" not in result.dump()
    assert _sha(env.overlay_db) == before_sha
    assert _tree(overlay_root) == before_tree


def test_t05_overlay_resolve_without_project_read_grant(tmp_path: Path) -> None:
    """Addendum: an overlay-owner grant resolves personal rules on its own; it never
    creates or substitutes a project access, and the project DB stays unopened."""
    seeder = make_env(tmp_path, "seed")
    rec_ok(seeder, "format", "compact", scope="personal")

    only = make_env(tmp_path, "only")
    rec_ok(only, "format", "wide")
    revoke(only, "project")
    project_digest = _sha(only.db)
    before = snapshot(only)
    for via in TRANSPORTS:
        res = resolve(only, key="format", via=via)
        assert res.code == "OK", (via, res.dump())
        item = entry(res, "format")
        assert item["status"] == "applied"
        assert item["selected"]["value"] == "compact"
        assert item["selected"]["scope"] == "personal"
        assert "wide" not in res.dump()
        layers = res.data["layers"]
        assert layers["personal"]["state"] == "read"
        assert layers["project"]["state"] == "denied"
        assert layers["project"]["reason"] == project_denial_reason(only)
    from rush.memory.retrieval import MemoryAccess

    overlay_access = MemoryAccess.resolve(
        only.root,
        operation="preference",
        action="resolve",
        owner_scope=only.overlay_owner,
    )
    assert overlay_access is not None
    inproc = PreferenceStore(only.root).resolve(
        "format",
        access=None,
        overlay_access=overlay_access,
        project_id=only.project_id,
        worktree_id=only.worktree_id,
    )
    assert inproc["preferences"][0]["selected"]["value"] == "compact"
    assert _sha(only.db) == project_digest
    assert snapshot(only) == before

    # A project-only grant cannot expose personal content.
    proj_only = make_env(tmp_path, "proj_only", overlay=False)
    res = resolve(proj_only, key="format")
    assert res.code == "OK", res.dump()
    assert "compact" not in res.dump()
    assert res.data["layers"]["personal"]["reason"] == "owner_not_granted"

    # No usable grant (granted, then both revoked): neither store is exposed or opened.
    marked = make_env(tmp_path, "marked")
    revoke(marked, "project")
    revoke(marked, "overlay")
    overlay_sha = _sha(marked.overlay_db)
    marked_before = snapshot(marked)
    for via in TRANSPORTS:
        res = resolve(marked, key="format", via=via)
        assert res.code == "E_PERMISSION", (via, res.dump())
        assert res.reason == project_denial_reason(marked)
        assert "compact" not in res.dump()
    assert _sha(marked.overlay_db) == overlay_sha
    assert snapshot(marked) == marked_before

    # Revocation removes personal content from an overlay-only access.
    solo = make_env(tmp_path, "solo", project=False)
    res = resolve(solo, key="format")
    assert res.code == "OK" and entry(res, "format")["selected"]["value"] == "compact"
    revoke(solo, "overlay")
    res = resolve(solo, key="format")
    assert res.code == "E_PERMISSION", res.dump()
    assert "compact" not in res.dump()


# --- R3: explicit authority needs the user's word ------------------------------


def test_t05_explicit_requires_user_stated_write(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    before = snapshot(env)

    no_user = rec(env, "color", "blue", user_stated=False)
    assert no_user.code == "E_PERMISSION" and no_user.reason == "user_stated_required"
    no_cache = rec(env, "color", "blue", cache_write=False)
    assert no_cache.code == "E_PERMISSION" and no_cache.reason == "cache_write_required"
    both_missing = rec(env, "color", "blue", user_stated=False, cache_write=False)
    assert both_missing.reason == "cache_write_required"  # checked first (brief 3.1)
    preview = rec(env, "color", "blue", apply=False, cache_write=False)
    assert preview.code == "OK", preview.dump()
    assert preview.data["applied"] is False
    assert preview.data["record"]["key"] == "color"
    assert preview.data["record"]["value"] == "blue"
    assert preview.data["record"]["authority"] == "explicit"
    assert preview.data["artifact_version_after"] == 2
    assert snapshot(env) == before
    assert not env.db.exists()

    no_write = make_env(tmp_path, "no_write", project_ops=("ask", "expand", "list"))
    no_write_before = snapshot(no_write)
    denied = rec(no_write, "color", "blue")
    assert denied.code == "E_PERMISSION" and denied.reason == "operation_not_granted"
    assert snapshot(no_write) == no_write_before

    ok = rec(env, "color", "blue")
    assert ok.code == "OK", ok.dump()
    assert ok.data["applied"] is True
    assert ok.data["trust_tier"] == "STATED"
    assert ok.data["corroboration_count"] == 0
    assert ok.data["artifact_version"] == 2
    row = _row_of(env.db, ok.data["artifact_id"])
    assert row["trust_tier"] == "STATED" and row["corroboration_count"] == 0
    assert row["artifact_version"] == 2
    assert row["content"]["authority"] == "explicit"

    stored = _sql(env.db, "SELECT COUNT(*) AS n FROM memory_artifacts")[0]["n"]
    after_ok = snapshot(env)
    extras: tuple[tuple[str, dict[str, Any]], ...] = (("reject", {}), ("supersede", {}))
    for kind, extra in extras:
        refused = call(
            env,
            "correct",
            artifact_id=ok.data["artifact_id"],
            layer="project",
            kind=kind,
            reason="changed my mind",
            expected_version=2,
            apply=True,
            user_stated=False,
            **extra,
        )
        assert refused.code == "E_PERMISSION", (kind, refused.dump())
        assert refused.reason == "user_stated_required"
    assert snapshot(env) == after_ok
    assert _sql(env.db, "SELECT COUNT(*) AS n FROM memory_artifacts")[0]["n"] == stored


def test_t05_preview_list_only(tmp_path: Path) -> None:
    """R3: a {list}-only grant previews every action with zero effects and no
    `cache_write`; the same grant with `apply=True` is refused; a personal preview needs
    {overlay_read, list} on the overlay-owner grant."""
    env = make_env(tmp_path, legacy_json={"legacy.k": "L"})
    project_row = rec_ok(env, "format", "wide")
    task_row = rec_ok(env, "format", "plain", scope="task", task_id="T1")
    personal_row = rec_ok(env, "format", "compact", scope="personal")
    regrant(env, "project", ops=("list",))
    regrant(env, "overlay", ops=("overlay_read", "list"))
    before = snapshot(env)

    previews: dict[str, Res] = {
        "record": rec(env, "k2", "v2", apply=False, cache_write=False),
        "correct": call(
            env,
            "correct",
            cache_write=False,
            artifact_id=project_row["artifact_id"],
            layer="project",
            kind="correct",
            reason="r",
            expected_version=2,
            value="narrow",
        ),
        "end_task": call(
            env,
            "end_task",
            cache_write=False,
            task_id="T1",
            expected_versions={task_row["artifact_id"]: 2},
        ),
        "migrate": call(env, "migrate", cache_write=False),
        "personal_record": rec(
            env, "k3", "v3", scope="personal", apply=False, cache_write=False
        ),
        "personal_correct": call(
            env,
            "correct",
            cache_write=False,
            artifact_id=personal_row["artifact_id"],
            layer="personal",
            kind="correct",
            reason="r",
            expected_version=2,
            value="tight",
            owner_scope=env.overlay_owner.as_dict(),
        ),
    }
    for name, result in previews.items():
        assert result.code == "OK", (name, result.dump())
        assert result.data["applied"] is False, name
    assert [e["artifact_id"] for e in previews["end_task"].data["ended"]] == [
        task_row["artifact_id"]
    ]
    assert snapshot(env) == before

    applies: dict[str, Res] = {
        "record": rec(env, "k2", "v2"),
        "correct": call(
            env,
            "correct",
            artifact_id=project_row["artifact_id"],
            layer="project",
            kind="correct",
            reason="r",
            expected_version=2,
            value="narrow",
            user_stated=True,
            apply=True,
        ),
        "end_task": call(
            env,
            "end_task",
            task_id="T1",
            expected_versions={task_row["artifact_id"]: 2},
            apply=True,
        ),
        "migrate": call(
            env,
            "migrate",
            apply=True,
            preview_digest=previews["migrate"].data["preview_digest"],
        ),
        "personal_record": rec(env, "k3", "v3", scope="personal"),
    }
    for name, result in applies.items():
        assert result.code == "E_PERMISSION", (name, result.dump())
        assert result.reason == "operation_not_granted", name
    assert snapshot(env) == before

    # A personal preview needs overlay_read: {list, expand} alone is not enough.
    regrant(env, "overlay", ops=("list", "expand"))
    before = snapshot(env)
    no_overlay_read = rec(
        env, "k3", "v3", scope="personal", apply=False, cache_write=False
    )
    assert no_overlay_read.code == "E_PERMISSION"
    assert no_overlay_read.reason == "operation_not_granted"
    assert snapshot(env) == before


# --- R4: rejection retrieval ---------------------------------------------------


def test_t05_rejection_retrieval(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    panel = rec_ok(env, "ui.panel_layout", "verbose")
    width = rec_ok(env, "int.width", "wide")
    rejected = call(
        env,
        "correct",
        artifact_id=panel["artifact_id"],
        layer="project",
        kind="reject",
        reason="too noisy",
        expected_version=2,
        user_stated=True,
        apply=True,
    )
    assert rejected.code == "OK", rejected.dump()
    assert rejected.data["artifact_version"] == 3

    res = resolve(env, query="verbose panels")
    assert res.code == "OK", res.dump()
    assert [e["key"] for e in res.data["preferences"]] == ["ui.panel_layout"]
    item = res.data["preferences"][0]
    assert item["status"] == "none" and item["selected"] is None
    assert item["applied_refs"] == [] and item["unresolved"] == []
    assert item["contrary"] == [
        {
            "artifact_id": panel["artifact_id"],
            "artifact_version": 3,
            "scope": "project",
            "authority": "explicit",
            "applicability": "rejected",
            "value": "verbose",
            "storage": "project",
            "source": PREFS,
        }
    ]
    assert why_view(item) == [(panel["artifact_id"], 3, "rejected_contrary")]

    res = resolve(env, query="wide integer")
    assert [e["key"] for e in res.data["preferences"]] == ["int.width"]
    item = res.data["preferences"][0]
    assert item["status"] == "applied"
    assert item["selected"]["value"] == "wide"
    assert item["selected"]["artifact_id"] == width["artifact_id"]
    assert item["contrary"] == []

    # The original version stays retrievable with its reason, source and downstream refs.
    store = TypedArtifactStore(env.root)
    original = store.get_version_payload(panel["artifact_id"], 2)
    assert original is not None
    assert json.loads(original[0])["applicability"] == "active"
    assert json.loads(original[0])["value"] == "verbose"
    current = _row_of(env.db, panel["artifact_id"])
    assert current["content"]["applicability"] == "rejected"
    last = current["content"]["correction_refs"][-1]
    assert last["kind"] == "reject" and last["reason"] == "too noisy"
    assert last["from_version"] == 2 and last["affected"] == []
    assert current["source"] == PREFS


# --- R5/R14/R15: migration ----------------------------------------------------


class _Crash(BaseException):
    """A simulated process death at an injected point (never caught by `except Exception`)."""


def _backup_name(source_bytes: bytes) -> str:
    return "preferences.json.migrated." + hashlib.sha256(source_bytes).hexdigest()[:16]


def _external_edit(env: Env, mutate: Any) -> None:
    """Edit the live `preferences.json` the way an external tool would: through the CAS
    JSON writer, outside `PreferenceStore`."""
    from rush.memory.transactions import CASMapTransaction

    CASMapTransaction(file_path=env.prefs_json, root_path=env.root).update(
        mutate, max_retries=20
    )


def _migrate_apply(env: Env, *, via: str = "tool") -> tuple[Res, Res]:
    preview = call(env, "migrate", via=via)
    assert preview.code == "OK", preview.dump()
    applied = call(
        env,
        "migrate",
        via=via,
        apply=True,
        preview_digest=preview.data["preview_digest"],
    )
    return preview, applied


def test_t05_migration_replay_and_tombstone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.trust import default_entry_tier

    env = make_env(tmp_path, legacy_json={"format": "compact"})
    source_bytes = env.prefs_json.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    backup = env.prefs_json.with_name(_backup_name(source_bytes))
    assert not env.db.exists()

    preview = call(env, "migrate")
    assert preview.code == "OK", preview.dump()
    assert preview.data["applied"] is False
    assert preview.data["inserts"] == [{"key": "format", "value": "compact"}]
    assert preview.data["conflicts"] == []
    assert preview.data["receipt"] == "absent"
    assert preview.data["publication"] == "pending"
    assert env.prefs_json.exists() and not backup.exists()
    assert not env.db.exists()

    applied = call(
        env, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
    )
    assert applied.code == "OK", applied.dump()
    assert applied.data["applied"] is True
    assert applied.data["inserted"] == [{"key": "format", "value": "compact"}]
    assert applied.data["inserted_count"] == 1
    assert applied.data["receipt"] == "committed"
    assert applied.data["publication"] == "published"
    assert not env.prefs_json.exists()
    assert backup.read_bytes() == source_bytes
    rows = _pref_rows(env.db)
    assert len(rows) == 1
    assert rows[0]["origin_kind"] == "preference" and rows[0]["origin_id"] == "format"
    assert rows[0]["content"] == {"key": "format", "value": "compact"}
    assert rows[0]["source"] == MIG
    assert rows[0]["trust_tier"] == default_entry_tier("local_tool")
    receipts = _receipts(env.db, "preference-migration:%")
    assert [r["operation_id"] for r in receipts] == ["preference-migration:" + digest]
    assert receipts[0]["payload"] == {
        "source_path": str(env.prefs_json),
        "digest": digest,
        "stage": "committed",
        "inserted": [{"key": "format", "value": "compact"}],
    }

    # Replay: the same source again changes 0 rows and finishes publication only.
    env.prefs_json.write_bytes(source_bytes)
    replay_preview, replay = _migrate_apply(env)
    assert replay_preview.data["receipt"] == "committed"
    assert replay_preview.data["inserts"] == []
    assert replay.code == "OK", replay.dump()
    assert replay.data["inserted"] == [] and replay.data["inserted_count"] == 0
    assert replay.data["publication"] == "published"
    assert not env.prefs_json.exists()
    assert backup.read_bytes() == source_bytes
    assert [r["artifact_version"] for r in _pref_rows(env.db)] == [1]

    # A deleted key plus a retained backup stays absent: the tombstone origin row wins.
    tomb = make_env(tmp_path, "tomb", legacy_json={"a": 1, "b": 2})
    first_bytes = tomb.prefs_json.read_bytes()
    _migrate_apply(tomb)
    store = PreferenceStore(tomb.root)
    assert store.delete("a") is True
    store.set("c", 3)
    preview, applied = _migrate_apply(tomb)
    assert preview.data["inserts"] == [{"key": "c", "value": 3}]
    assert preview.data["conflicts"] == []
    assert applied.code == "OK" and applied.data["inserted_count"] == 1
    by_origin = {r["origin_id"]: r["content"] for r in _pref_rows(tomb.db)}
    assert by_origin == {
        "a": {"deleted": True},
        "b": {"key": "b", "value": 2},
        "c": {"key": "c", "value": 3},
    }
    assert (tomb.prefs_json.with_name(_backup_name(first_bytes))).exists()
    assert store.get("a", "dflt") == "dflt"
    assert store.list_all() == {"b": 2, "c": 3}
    gone = resolve(tomb, key="a")
    assert gone.code == "OK", gone.dump()
    assert all(e.get("selected") is None for e in gone.data["preferences"])

    # A concurrent edit between preview and apply: exact E_VERSION, original intact.
    cas = make_env(tmp_path, "cas", legacy_json={"k": "v"})
    preview = call(cas, "migrate")
    _external_edit(cas, lambda data: {**data, "extra": "e"})
    before = snapshot(cas)
    stale = call(
        cas, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
    )
    assert stale.code == "E_VERSION" and stale.reason == "preview_changed"
    assert snapshot(cas) == before
    assert not cas.db.exists()
    missing_digest = call(cas, "migrate", apply=True)
    assert missing_digest.code == "E_INPUT"
    assert missing_digest.reason == "preview_digest_required"
    assert snapshot(cas) == before

    # A verification mismatch rolls back and leaves the original unpublished.
    bad = make_env(tmp_path, "bad", legacy_json={"k": "v"})
    bad_bytes = bad.prefs_json.read_bytes()
    real_insert = TypedArtifactStore._insert_row

    def corrupt(self: Any, conn: Any, stored: MemoryArtifact) -> None:
        if stored.origin_kind == "preference":
            stored = dataclasses.replace(
                stored, content={**stored.content, "value": "tampered"}
            )
        return real_insert(self, conn, stored)  # type: ignore[no-any-return]

    preview = call(bad, "migrate")
    with monkeypatch.context() as patch:
        patch.setattr(TypedArtifactStore, "_insert_row", corrupt)
        failed = call(
            bad, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
        )
    assert failed.code == "E_MIGRATION"
    assert failed.reason == "migration_verify_mismatch"
    assert bad.prefs_json.read_bytes() == bad_bytes
    assert not bad.prefs_json.with_name(_backup_name(bad_bytes)).exists()
    assert _pref_rows(bad.db) == []
    assert _receipts(bad.db, "preference-migration:%") == []


def test_t05_migration_conflict_external_json_edit(tmp_path: Path) -> None:
    """R5/D27: a live `preferences.json` that differs from an existing origin row (value
    changed, or a tombstoned key re-added) is a preview conflict; apply refuses with
    `E_VERSION migration_conflict`, zero effects, source unpublished."""
    env = make_env(tmp_path, legacy_json={"k1": "v1", "tomb": "t", "same": "s"})
    _migrate_apply(env)
    assert PreferenceStore(env.root).delete("tomb") is True
    # Re-create the live source: one value changed, one tombstoned key re-added, one
    # value equal to its origin (no conflict).
    PreferenceStore(env.root).set("same", "s")
    _external_edit(env, lambda d: {**d, "k1": "external", "tomb": "again"})
    live_bytes = env.prefs_json.read_bytes()
    before = snapshot(env)
    preview = call(env, "migrate")
    assert preview.code == "OK", preview.dump()
    assert preview.data["conflicts"] == ["k1", "tomb"]
    assert preview.data["inserts"] == []
    assert snapshot(env) == before
    refused = call(
        env, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
    )
    assert refused.code == "E_VERSION" and refused.reason == "migration_conflict"
    assert snapshot(env) == before
    assert env.prefs_json.read_bytes() == live_bytes
    assert not env.prefs_json.with_name(_backup_name(live_bytes)).exists()
    rows = {r["origin_id"]: r["content"] for r in _pref_rows(env.db)}
    assert rows["k1"] == {"key": "k1", "value": "v1"}
    assert rows["tomb"] == {"deleted": True}


def test_t05_migration_conflict_resolved_via_correct(tmp_path: Path) -> None:
    """R15/D27: a `migration_conflict` is resolved with the exact D27 `correct` request
    through `rush memory preference --input <file> --allow-cache-write`."""
    env = make_env(tmp_path, legacy_json={"k": "old"})
    _migrate_apply(env)
    origin = _pref_rows(env.db)[0]
    _external_edit(env, lambda d: {**d, "k": "live-value"})
    preview = call(env, "migrate")
    assert preview.data["conflicts"] == ["k"]
    refused = call(
        env, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
    )
    assert refused.code == "E_VERSION" and refused.reason == "migration_conflict"

    bytes_before = env.prefs_json.read_bytes()
    request = {
        "action": "correct",
        "artifact_id": origin["id"],
        "layer": "project",
        "kind": "correct",
        "reason": "keep the live value",
        "expected_version": origin["artifact_version"],
        "value": "live-value",
        "user_stated": True,
        "apply": True,
    }
    # The same request without `user_stated` is refused with zero effects.
    without = {k: v for k, v in request.items() if k != "user_stated"}
    before = snapshot(env)
    refused_write = call(
        env, "correct", via="cli", **{k: v for k, v in without.items() if k != "action"}
    )
    assert refused_write.code == "E_PERMISSION"
    assert refused_write.reason == "user_stated_required"
    assert snapshot(env) == before
    assert env.prefs_json.read_bytes() == bytes_before

    resolved = call(
        env, "correct", via="cli", **{k: v for k, v in request.items() if k != "action"}
    )
    assert resolved.code == "OK", resolved.dump()
    assert resolved.data["applied"] is True
    assert resolved.data["artifact_version"] == origin["artifact_version"] + 2
    row = _row_of(env.db, origin["id"])
    assert row["trust_tier"] == "STATED"
    assert row["artifact_version"] == origin["artifact_version"] + 2
    assert row["content"]["applicability"] == "active"
    assert row["content"]["value"] == "live-value"

    preview = call(env, "migrate")
    assert preview.data["conflicts"] == []
    done = call(
        env, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
    )
    assert done.code == "OK", done.dump()
    assert done.data["publication"] == "published"
    assert not env.prefs_json.exists()

    # A receipt id supplied with the correction is written exactly once.
    second = make_env(tmp_path, "second", legacy_json={"k": "old"})
    _migrate_apply(second)
    origin2 = _pref_rows(second.db)[0]
    receipt_id = "resolve-conflict-1"
    out = call(
        second,
        "correct",
        artifact_id=origin2["id"],
        layer="project",
        kind="correct",
        reason="confirm",
        expected_version=origin2["artifact_version"],
        value="old",
        user_stated=True,
        apply=True,
        receipt_operation_id=receipt_id,
    )
    assert out.code == "OK", out.dump()
    receipts = _receipts(second.db, receipt_id)
    assert [r["operation_id"] for r in receipts] == [receipt_id]
    assert receipts[0]["artifact_id"] == origin2["id"]
    assert receipts[0]["kind"] == "edit"


@pytest.mark.parametrize("via", TRANSPORTS)
def test_t05_migration_crash_points(
    via: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R14/D27: a crash after commit before link, after link before unlink, and a
    Windows-style unlink `PermissionError` each replay to publication only (0 rows)."""
    import errno

    real_link, real_unlink = os.link, os.unlink

    def make(name: str, data: dict[str, Any]) -> tuple[Env, bytes, Path, Path]:
        env = make_env(tmp_path, name, legacy_json=data)
        raw = env.prefs_json.read_bytes()
        return env, raw, env.prefs_json, env.prefs_json.with_name(_backup_name(raw))

    # Crash after the DB commit, before the link.
    env, raw, src, backup = make("crash_before_link", {"a": 1})
    preview = call(env, "migrate", via=via)

    def crash_link(a: Any, b: Any, *args: Any, **kw: Any) -> None:
        if ".migrated." in str(b):
            raise _Crash
        real_link(a, b, *args, **kw)

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", crash_link)
        with pytest.raises(_Crash):
            call(
                env,
                "migrate",
                via=via,
                apply=True,
                preview_digest=preview.data["preview_digest"],
            )
    assert src.read_bytes() == raw and not backup.exists()
    assert len(_pref_rows(env.db)) == 1
    stages = [
        r["payload"]["stage"] for r in _receipts(env.db, "preference-migration:%")
    ]
    assert stages == ["committed"]
    replay_preview, replay = _migrate_apply(env, via=via)
    assert replay_preview.data["receipt"] == "committed"
    assert replay_preview.data["inserts"] == []
    assert replay.code == "OK" and replay.data["inserted_count"] == 0
    assert replay.data["publication"] == "published"
    assert backup.read_bytes() == raw and not src.exists()
    assert len(_pref_rows(env.db)) == 1

    # Crash after the link, before the unlink: the same-digest backup is kept.
    env, raw, src, backup = make("crash_before_unlink", {"b": 2})
    preview = call(env, "migrate", via=via)

    def crash_unlink(path: Any, *args: Any, **kw: Any) -> None:
        if Path(path) == src:
            raise _Crash
        real_unlink(path, *args, **kw)

    with monkeypatch.context() as patch:
        patch.setattr(os, "unlink", crash_unlink)
        with pytest.raises(_Crash):
            call(
                env,
                "migrate",
                via=via,
                apply=True,
                preview_digest=preview.data["preview_digest"],
            )
    assert src.read_bytes() == raw and backup.read_bytes() == raw
    replay_preview, replay = _migrate_apply(env, via=via)
    assert replay.code == "OK" and replay.data["inserted_count"] == 0
    assert not src.exists() and backup.read_bytes() == raw
    assert len(_pref_rows(env.db)) == 1

    # A Windows unlink PermissionError: committed-unpublished, replay completes.
    env, raw, src, backup = make("unlink_permission", {"c": 3})
    preview = call(env, "migrate", via=via)

    def deny_unlink(path: Any, *args: Any, **kw: Any) -> None:
        if Path(path) == src:
            raise PermissionError(errno.EACCES, "in use", str(path))
        real_unlink(path, *args, **kw)

    with monkeypatch.context() as patch:
        patch.setattr(os, "unlink", deny_unlink)
        unconfirmed = call(
            env,
            "migrate",
            via=via,
            apply=True,
            preview_digest=preview.data["preview_digest"],
        )
    assert unconfirmed.code == "E_UNAVAILABLE"
    assert unconfirmed.reason == "publication_unconfirmed"
    assert src.read_bytes() == raw
    replay_preview, replay = _migrate_apply(env, via=via)
    assert replay.code == "OK" and replay.data["inserted_count"] == 0
    assert not src.exists() and backup.read_bytes() == raw

    # EXDEV from os.link: E_UNAVAILABLE publication_unsupported, receipt committed,
    # source unpublished and readable; replay finishes publication only.
    env, raw, src, backup = make("exdev", {"d": 4})
    preview = call(env, "migrate", via=via)

    def exdev_link(a: Any, b: Any, *args: Any, **kw: Any) -> None:
        if ".migrated." in str(b):
            raise OSError(errno.EXDEV, "cross-device link", str(b))
        real_link(a, b, *args, **kw)

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", exdev_link)
        unsupported = call(
            env,
            "migrate",
            via=via,
            apply=True,
            preview_digest=preview.data["preview_digest"],
        )
    assert unsupported.code == "E_UNAVAILABLE"
    assert unsupported.reason == "publication_unsupported"
    assert src.read_bytes() == raw and not backup.exists()
    stages = [
        r["payload"]["stage"] for r in _receipts(env.db, "preference-migration:%")
    ]
    assert stages == ["committed"]
    assert PreferenceStore(env.root).get("d") == 4
    replay_preview, replay = _migrate_apply(env, via=via)
    assert replay.code == "OK" and replay.data["inserted_count"] == 0
    assert replay.data["publication"] == "published"
    assert not src.exists() and backup.read_bytes() == raw
    assert len(_pref_rows(env.db)) == 1

    # A backup whose bytes differ from an existing same-named backup is never overwritten.
    env, raw, src, backup = make("digest_mismatch", {"e": 5})
    preview = call(env, "migrate", via=via)
    backup.write_bytes(b"not the same bytes")
    conflict = call(
        env,
        "migrate",
        via=via,
        apply=True,
        preview_digest=preview.data["preview_digest"],
    )
    assert conflict.code == "E_VERSION"
    assert conflict.reason == "backup_digest_mismatch"
    assert backup.read_bytes() == b"not the same bytes"
    assert src.read_bytes() == raw

    # A changed source after a committed migration is a new preview.
    env, raw, src, backup = make("changed_source", {"f": 6})
    preview = call(env, "migrate", via=via)
    with monkeypatch.context() as patch:
        patch.setattr(os, "link", crash_link)
        with pytest.raises(_Crash):
            call(
                env,
                "migrate",
                via=via,
                apply=True,
                preview_digest=preview.data["preview_digest"],
            )
    _external_edit(env, lambda d: {**d, "g": 7})
    changed = call(env, "migrate", via=via)
    assert changed.data["receipt"] == "absent"
    assert changed.data["inserts"] == [{"key": "g", "value": 7}]
    assert changed.data["conflicts"] == []


def test_t05_migration_backup_merge_order(tmp_path: Path) -> None:
    """R14/A1: `.migrated` then `.migrated.<sha16>` backups merge in receipt
    `created_at` order (an unreceipted backup after every receipted one, by name; a
    backup whose bytes do not hash to its suffix is ignored) and contribute only keys
    with no origin row."""
    from rush.memory.migration import migrate_preference_store

    env = make_env(tmp_path, legacy_json={"o": "origin"})
    _migrate_apply(env)  # an origin row for `o`
    rush = env.root / ".rush"
    store = TypedArtifactStore(env.root)

    def write_backup(data: dict[str, Any]) -> tuple[bytes, Path]:
        from rush.memory.transactions import CASMapTransaction

        scratch = rush / "scratch-map.json"
        CASMapTransaction(file_path=scratch, root_path=env.root).update(
            lambda _d: dict(data), max_retries=20
        )
        raw = scratch.read_bytes()
        scratch.unlink()
        path = rush / _backup_name(raw)
        path.write_bytes(raw)
        return raw, path

    legacy_raw, _ = write_backup({"y": "legacy", "w": "legacy", "o": "from-backup"})
    (rush / "preferences.json.migrated").write_bytes(legacy_raw)
    for stale in rush.glob("preferences.json.migrated.*"):
        if stale.read_bytes() == legacy_raw:
            stale.unlink()
    raw1, path1 = write_backup({"y": "one", "x1": "one", "o": "from-backup"})
    raw2, path2 = write_backup({"y": "two", "x2": "two"})
    # Receipts: the later `created_at` belongs to the lexically smaller backup name, so
    # name order and receipt order disagree.
    first, second = sorted([(path1, raw1), (path2, raw2)], key=lambda p: p[0].name)
    times = {first[0].name: 200.0, second[0].name: 100.0}
    with contextlib.closing(sqlite3.connect(store.db_path)) as conn:
        for path, raw in (first, second):
            digest = hashlib.sha256(raw).hexdigest()
            conn.execute(
                "INSERT INTO mutation_receipts "
                "(operation_id, artifact_id, kind, revision, payload, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (
                    "preference-migration:" + digest,
                    None,
                    "preference_migration",
                    None,
                    json.dumps(
                        {
                            "source_path": str(env.prefs_json),
                            "digest": digest,
                            "stage": "committed",
                            "inserted": [],
                        }
                    ),
                    times[path.name],
                ),
            )
        conn.commit()
    # A backup whose bytes do not hash to its suffix is ignored.
    (rush / ("preferences.json.migrated." + "0" * 16)).write_bytes(
        json.dumps({"data": {"bogus": "b"}}).encode()
    )
    migrated = migrate_preference_store(env.root)
    rows = {r["origin_id"]: r["content"] for r in _pref_rows(env.db)}
    later_receipt = (
        second[0] if times[second[0].name] > times[first[0].name] else first[0]
    )
    expected_y = "one" if later_receipt == path1 else "two"
    assert rows["y"] == {"key": "y", "value": expected_y}
    assert rows["w"] == {"key": "w", "value": "legacy"}
    assert rows["x1"] == {"key": "x1", "value": "one"}
    assert rows["x2"] == {"key": "x2", "value": "two"}
    assert rows["o"] == {"key": "o", "value": "origin"}
    assert "bogus" not in rows
    assert migrated == 4


# --- R6/R7 -----------------------------------------------------------------------


def test_t05_readonly_paths_create_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R6/D10: the constructor, `get_preference_readonly`, `resolve` and overlay
    `resolve` create no file on a missing project root or a missing data root."""
    from rush.memory.preference_store import get_preference_readonly

    missing = tmp_path / "missing_project"
    store = PreferenceStore(missing)
    assert not missing.exists()
    assert get_preference_readonly(missing, "k", "dflt") == "dflt"
    assert not missing.exists()
    existing = tmp_path / "existing_no_rush"
    existing.mkdir()
    PreferenceStore(existing)
    assert not (existing / ".rush").exists()
    assert store.project_root == missing.resolve()

    for via in ("tool",):  # a missing root is no cwd or MCP target
        out = resolve(
            missing,
            key="k",
            via=via,
            session=[PREFS],
            project_id="p",
            worktree_id="w",
        )
        assert not missing.exists(), via
        assert out.code == "OK", (via, out.dump())
        assert out.data["preferences"] == [] or all(
            e["selected"] is None for e in out.data["preferences"]
        )
        assert out.data["layers"]["personal"]["state"] == "denied"
        assert out.data["layers"]["personal"]["reason"] == "policy_missing"

    # A missing data root: HOME points at a directory that does not exist.
    fresh_home = tmp_path / "fresh_home"
    monkeypatch.setenv("HOME", str(fresh_home))
    monkeypatch.setenv("XDG_DATA_HOME", str(fresh_home / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(fresh_home / "lad"))
    project = tmp_path / "project_fresh"
    project.mkdir()
    before = _digest_tree(project)
    for via in TRANSPORTS:
        out = resolve(
            project,
            key="k",
            via=via,
            session=[PREFS],
            project_id="p",
            worktree_id="w",
        )
        assert out.code == "OK", (via, out.dump())
        assert out.data["layers"]["personal"]["state"] == "denied"
        assert out.data["layers"]["personal"]["reason"] == "policy_missing"
        assert not fresh_home.exists(), via
    assert _digest_tree(project) == before
    assert get_preference_readonly(project, "k") is None
    assert not fresh_home.exists()
    assert not (project / ".rush").exists()


def test_t05_foreign_project_private_row_absent(tmp_path: Path) -> None:
    """R7: a project B private row never reaches project A on any route."""
    a = make_env(tmp_path, "proj_a")
    b = make_env(tmp_path, "proj_b")
    secret = rec_ok(b, "secret.key", "b-private")
    rec_ok(a, "a.key", "a-value")
    secret_id = secret["artifact_id"]

    outputs = [
        resolve(a, key="secret.key"),
        resolve(a, query="private"),
        resolve(a, key="secret.key", via="mcp"),
        resolve(a, key="secret.key", via="cli"),
    ]
    tool = MemoryTool()
    for operation, request in (
        ("ask", {"view": "compact"}),
        ("recall", {"view": "compact"}),
        ("list", {"view": "compact"}),
    ):
        outputs.append(
            _res(
                tool.run(
                    a.root,
                    operation=operation,  # type: ignore[arg-type]
                    subject="preference",
                    query="private",
                    request=request,
                )
            )
        )
    outputs.append(
        _res(
            tool.run(
                a.root,
                operation="expand",
                request={"id": secret_id, "version": 2},
            )
        )
    )
    for result in outputs:
        assert "b-private" not in result.dump(), result.dump()
    # The last output is the expand: its identical-denial body echoes the caller's own
    # id (T02_B64_KEYS pins `id`), so only the row-content check applies to it.
    for result in outputs[:-1]:
        assert secret_id not in result.dump(), result.dump()
    # Naming B's owner or ids from A gets no row either.
    spoof_owner = call(a, "resolve", key="secret.key", owner_scope=b.owner.as_dict())
    assert "b-private" not in spoof_owner.dump()
    assert spoof_owner.code == "E_OWNER" and spoof_owner.reason == "owner_not_granted"
    spoof_ids = call(
        a,
        "resolve",
        key="secret.key",
        project_id=b.project_id,
        worktree_id=b.worktree_id,
    )
    assert spoof_ids.code == "E_INPUT" and spoof_ids.reason == "ids_mismatch"
    assert "b-private" not in spoof_ids.dump()


def test_t05_host_string_not_authority(tmp_path: Path) -> None:
    """R7/B10: the agent host string is attribution, never authority."""
    inferred = make_env(tmp_path, "inferred")
    rec_ok(inferred, "host.key", "claimed", authority="inferred", attribution="user")
    res = resolve(inferred, key="host.key")
    item = entry(res, "host.key")
    assert item["status"] == "none" and item["selected"] is None
    assert [ref_view(r)[3] for r in item["advice"]] == ["inferred"]
    assert [w["decision"] for w in item["why"]] == ["advice_inferred"]

    def normalized(result: Res) -> list[dict[str, Any]]:
        return [
            {
                "key": e["key"],
                "status": e["status"],
                "selected": (e["selected"] or {}).get("value"),
                "scope": (e["selected"] or {}).get("scope"),
                "advice": sorted(r["value"] for r in e["advice"]),
                "why": [w["decision"] for w in e["why"]],
            }
            for e in result.data["preferences"]
        ]

    seen: dict[str, list[dict[str, Any]]] = {}
    for host in ("claude-code", "codex"):
        env = make_env(tmp_path, f"host_{host}")
        rec_ok(env, "host.key", "explicit-value", attribution=host)
        rec_ok(
            env, "host.other", "advice-value", authority="inferred", attribution=host
        )
        results = [
            resolve(env, key="host.key", via="mcp", agent_id=host),
            resolve(env, key="host.other", via="mcp", agent_id=host),
            resolve(env, key="host.key", via="mcp", agent_id="someone-else"),
        ]
        assert all(r.code == "OK" for r in results), [r.dump() for r in results]
        assert normalized(results[0]) == normalized(results[2])
        seen[host] = normalized(results[0]) + normalized(results[1])
    assert seen["claude-code"] == seen["codex"]
    assert seen["claude-code"][0]["selected"] == "explicit-value"
    assert seen["claude-code"][1]["status"] == "none"


# --- R9: the correction core -------------------------------------------------------


def _db_state(db: Path) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of every memory table (FTS shadow tables excluded), for an exact
    before/after comparison of a rolled-back transaction."""
    if not db.exists():
        return {}
    out: dict[str, list[tuple[Any, ...]]] = {}
    names = [
        r["name"]
        for r in _sql(
            db,
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'memory_fts%' "
            "ORDER BY name",
        )
    ]
    for name in names:
        out[name] = [
            tuple(r) for r in _sql(db, f'SELECT * FROM "{name}" ORDER BY 1, 2')
        ]
    return out


class _LockProbe:
    """Tells whether the policy lock is held, by trying to take it from another thread."""

    def __init__(self, data_root: Path) -> None:
        self.data_root = data_root
        self._threads: list[Any] = []

    def held(self) -> bool:
        import threading

        from rush.memory.authorization import hold_policy_lock

        acquired = threading.Event()

        def worker() -> None:
            with hold_policy_lock(data_root=self.data_root):
                acquired.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self._threads.append(thread)
        return not acquired.wait(0.3)

    def finish(self) -> None:
        for thread in self._threads:
            thread.join(30)
            assert not thread.is_alive()


def _ref(kind: str, reason: str, from_version: int) -> dict[str, Any]:
    return {
        "kind": kind,
        "reason": reason,
        "at": time.time(),
        "from_version": from_version,
        "affected": [],
    }


def _target_content(
    row: dict[str, Any], applicability: str, kind: str
) -> dict[str, Any]:
    content = dict(row["content"])
    content["applicability"] = applicability
    content["correction_refs"] = [
        *content.get("correction_refs", []),
        _ref(kind, "because", row["artifact_version"]),
    ]
    return content


def _binding(applicability: str, task: tuple[str, str, str] | None = None) -> Any:
    from rush.memory.store import VersionBinding

    project_id, worktree_id, task_id = task or (None, None, None)
    return VersionBinding(
        applicability=applicability,
        task_project_id=project_id,
        task_worktree_id=worktree_id,
        task_id=task_id,
    )


def test_t05_correction_core_transaction(tmp_path: Path) -> None:
    """R9: reject/supersede/correct each append the written `applicability` version in
    one `BEGIN IMMEDIATE` under the policy lock, supersede writes the `supersedes` edge
    and the receipt goes through `receipt_writer`; rejected/superseded/pending/
    task-mismatched rows are not `usable_as_current`."""
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility

    env = make_env(tmp_path)
    store = TypedArtifactStore(env.root)
    access = access_for(env, "correct", apply=True)
    ask = MemoryAccess.resolve(env.root, operation="ask", owner_scope=env.owner)
    assert ask is not None

    def usable(artifact_id: str, mode_access: Any = None) -> Any:
        row = store.get_current_row(artifact_id)
        assert row is not None
        return evaluate_artifact_visibility(
            store, row, access=mode_access or ask, mode="ordinary"
        )

    # reject: one new version, original retained, binding recorded.
    rejected = rec_ok(env, "k.reject", "v")
    row = _row_of(env.db, rejected["artifact_id"])
    content = _target_content(row, "rejected", "reject")
    out = store.apply_correction(
        access=access,
        kind="reject",
        artifact_id=rejected["artifact_id"],
        expected_version=2,
        target_content=content,
        binding=_binding("rejected"),
    )
    assert out == {
        "code": "OK",
        "artifact_id": rejected["artifact_id"],
        "artifact_version": 3,
        "replacement": None,
        "edge": None,
    }
    current = _row_of(env.db, rejected["artifact_id"])
    assert current["artifact_version"] == 3
    assert current["applicability"] == "rejected"
    assert current["trust_tier"] == "DERIVED"
    assert current["content"] == content
    versions = _version_rows(env.db, rejected["artifact_id"])
    assert [v["artifact_version"] for v in versions] == [1, 2, 3]
    assert versions[2]["applicability"] == "rejected"
    assert versions[2]["binding_recorded"] == 1
    assert (
        versions[2]["task_project_id"],
        versions[2]["task_worktree_id"],
        versions[2]["task_id"],
    ) == (None, None, None)
    assert json.loads(versions[1]["content"])["applicability"] == "active"
    decision = usable(rejected["artifact_id"])
    assert decision.usable_as_current is False
    assert "applicability_rejected" in decision.reason_codes

    # correct: the correction version, then the STATED promotion version.
    corrected = rec_ok(env, "k.correct", "v")
    row = _row_of(env.db, corrected["artifact_id"])
    content = _target_content(row, "active", "correct")
    content["value"] = "v-new"
    out = store.apply_correction(
        access=access,
        kind="correct",
        artifact_id=corrected["artifact_id"],
        expected_version=2,
        target_content=content,
        binding=_binding("active"),
    )
    assert out["code"] == "OK" and out["artifact_version"] == 4
    assert out["replacement"] is None and out["edge"] is None
    current = _row_of(env.db, corrected["artifact_id"])
    assert current["trust_tier"] == "STATED" and current["corroboration_count"] == 0
    assert current["applicability"] == "active"
    assert current["content"]["value"] == "v-new"
    versions = _version_rows(env.db, corrected["artifact_id"])
    assert [v["artifact_version"] for v in versions] == [1, 2, 3, 4]
    assert all(v["binding_recorded"] == 1 for v in versions[2:])
    assert usable(corrected["artifact_id"]).usable_as_current is True

    # supersede: a new replacement id, the edge, and the original's superseded version.
    old = rec_ok(env, "k.sup", "old")
    row = _row_of(env.db, old["artifact_id"])
    replacement_content = _target_content(row, "active", "supersede")
    replacement_content["value"] = "replaced"
    replacement_content["correction_refs"] = []
    target = _target_content(row, "superseded", "supersede")
    statements: list[str] = []
    real_connect = TypedArtifactStore._connect

    def traced(self: Any) -> Any:
        conn = real_connect(self)
        conn.set_trace_callback(statements.append)
        return conn

    probe = _LockProbe(env.data_root)
    held: list[bool] = []

    def receipt_writer(conn: Any, payload: dict[str, Any]) -> None:
        held.append(probe.held())
        store._write_receipt(
            conn,
            "correction-receipt-1",
            payload["artifact_id"],
            "edit",
            payload["artifact_version"],
            payload["result"],
        )
        assert payload["artifact_id"] == old["artifact_id"]
        assert [
            (r["artifact_id"], r["artifact_version"]) for r in payload["result_refs"]
        ] == [
            (payload["result"]["replacement"]["artifact_id"], 1),
            (payload["result"]["replacement"]["artifact_id"], 2),
            (old["artifact_id"], 3),
        ]
        assert payload["artifact_version"] == 3

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(TypedArtifactStore, "_connect", traced)
        out = store.apply_correction(
            access=access,
            kind="supersede",
            artifact_id=old["artifact_id"],
            expected_version=2,
            target_content=target,
            replacement_content=replacement_content,
            binding=_binding("superseded"),
            receipt_writer=receipt_writer,
        )
    probe.finish()
    assert held == [True]  # the policy lock spans the receipt write
    assert sum(1 for s in statements if s.strip().upper().startswith("BEGIN")) == 1
    assert out["code"] == "OK" and out["artifact_version"] == 3
    rep = out["replacement"]
    assert rep["artifact_version"] == 2
    assert out["edge"] == {
        "source_id": rep["artifact_id"],
        "source_version": 1,
        "target_id": old["artifact_id"],
        "target_version": 2,
    }
    assert _relations(env.db) == [
        (rep["artifact_id"], 1, old["artifact_id"], 2, "supersedes")
    ]
    replacement_row = _row_of(env.db, rep["artifact_id"])
    assert replacement_row["trust_tier"] == "STATED"
    assert replacement_row["applicability"] == "active"
    assert replacement_row["content"]["value"] == "replaced"
    original = _row_of(env.db, old["artifact_id"])
    assert (
        original["applicability"] == "superseded" and original["artifact_version"] == 3
    )
    for field in ("owner_scope_kind", "owner_scope_id", "source"):
        assert replacement_row[field] == original[field], field
    assert [r["operation_id"] for r in _receipts(env.db, "correction-receipt-1")] == [
        "correction-receipt-1"
    ]
    superseded = usable(old["artifact_id"])
    assert superseded.usable_as_current is False
    assert "applicability_superseded" in superseded.reason_codes
    assert usable(rep["artifact_id"]).usable_as_current is True

    # pending and task-mismatched rows are not usable as current either.
    seed_row(
        store,
        "pending-row",
        env.owner,
        key="k.pending",
        value="v",
        scope="project",
        authority="explicit",
        applicability="pending",
        project_id=env.project_id,
        worktree_id=env.worktree_id,
    )
    pending = usable("pending-row")
    assert pending.usable_as_current is False
    assert "applicability_pending" in pending.reason_codes
    seed_row(
        store,
        "task-row-a",
        env.owner,
        key="k.task",
        value="v",
        scope="task",
        project_id=env.project_id,
        worktree_id=env.worktree_id,
        task_id="A",
    )
    for task, expected in (("A", True), ("B", False), (None, False)):
        scoped = MemoryAccess.resolve(
            env.root, operation="ask", owner_scope=env.owner, task_id=task
        )
        assert scoped is not None
        decision = usable("task-row-a", scoped)
        assert decision.usable_as_current is expected, task
        assert ("task_mismatch" in decision.reason_codes) is (not expected), task


def test_t05_correction_cited_versions_and_owner(tmp_path: Path) -> None:
    """Addendum: `apply_correction(supersedes=[...])` validates every cited ref before
    its first write and writes one `supersedes` edge per cited version."""
    env = make_env(tmp_path)
    store = TypedArtifactStore(env.root)
    access = access_for(env, "correct", apply=True)
    first = rec_ok(env, "cite.a", "one")
    second = rec_ok(env, "cite.b", "two")
    seed_row(
        store,
        "foreign-owner",
        OwnerScope("project", "somewhere-else"),
        key="cite.c",
        value="x",
        scope="project",
        project_id=env.project_id,
        worktree_id=env.worktree_id,
    )
    primary = _row_of(env.db, first["artifact_id"])
    replacement = {
        **_target_content(primary, "active", "supersede"),
        "correction_refs": [],
    }
    replacement["value"] = "three"
    target = _target_content(primary, "superseded", "supersede")

    def attempt(**overrides: Any) -> Any:
        arguments: dict[str, Any] = {
            "access": access,
            "kind": "supersede",
            "artifact_id": first["artifact_id"],
            "expected_version": 2,
            "target_content": target,
            "replacement_content": replacement,
            "binding": _binding("superseded"),
        }
        arguments.update(overrides)
        return store.apply_correction(**arguments)

    def ref(artifact_id: str, version: Any) -> dict[str, Any]:
        return {"artifact_id": artifact_id, "artifact_version": version}

    before = _db_state(env.db)
    rejected: list[tuple[str, Any, tuple[str, str]]] = [
        ("changed", [ref(second["artifact_id"], 1)], ("E_VERSION", "version_changed")),
        ("foreign", [ref("foreign-owner", 1)], ("E_NOT_VISIBLE", "")),
        ("missing", [ref("does-not-exist", 1)], ("E_NOT_VISIBLE", "")),
        ("bool_version", [ref(second["artifact_id"], True)], ("E_INPUT", "")),
        ("zero_version", [ref(second["artifact_id"], 0)], ("E_INPUT", "")),
        ("negative_version", [ref(second["artifact_id"], -1)], ("E_INPUT", "")),
        ("huge_version", [ref(second["artifact_id"], 10**400)], ("E_INPUT", "")),
        (
            "duplicate",
            [ref(second["artifact_id"], 2), ref(second["artifact_id"], 2)],
            ("E_INPUT", ""),
        ),
        ("malformed_ref", [{"artifact_id": second["artifact_id"]}], ("E_INPUT", "")),
        ("not_a_dict", ["nope"], ("E_INPUT", "")),
        ("empty_id", [ref("", 1)], ("E_INPUT", "")),
    ]
    for name, cited, (code, reason) in rejected:
        out = attempt(supersedes=cited)
        assert out["code"] == code, (name, out)
        if reason:
            assert out["reason"] == reason, (name, out)
        assert _db_state(env.db) == before, name

    # A mismatched storage root: the personal (overlay) access on the project store.
    overlay_access = access_for(env, "correct", apply=True, personal=True)
    mismatch = attempt(access=overlay_access, supersedes=None)
    assert mismatch["code"] == "E_NOT_VISIBLE"
    assert _db_state(env.db) == before

    # A failure after the second edge writes nothing: inject on the 2nd edge.
    from rush.memory import relations

    real_edge = relations.insert_relation_tx
    seen: list[int] = []

    def second_edge_fails(conn: Any, **kwargs: Any) -> Any:
        seen.append(1)
        if len(seen) == 2:
            raise RuntimeError("injected after the first edge")
        return real_edge(conn, **kwargs)

    probe = _LockProbe(env.data_root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(relations, "insert_relation_tx", second_edge_fails)
        with pytest.raises(RuntimeError, match="injected after the first edge"):
            attempt(supersedes=[ref(second["artifact_id"], 2)])
    assert len(seen) == 2
    assert _db_state(env.db) == before
    assert probe.held() is False
    probe.finish()

    # Success: two cited versions -> two exact edges; the non-primary original is kept.
    out = attempt(supersedes=[ref(second["artifact_id"], 2)])
    assert out["code"] == "OK", out
    new_id = out["replacement"]["artifact_id"]
    assert sorted(_relations(env.db)) == sorted(
        [
            (new_id, 1, first["artifact_id"], 2, "supersedes"),
            (new_id, 1, second["artifact_id"], 2, "supersedes"),
        ]
    )
    other = _row_of(env.db, second["artifact_id"])
    assert other["artifact_version"] == 2 and other["applicability"] == "active"
    assert _row_of(env.db, first["artifact_id"])["applicability"] == "superseded"
    assert _row_of(env.db, first["artifact_id"])["artifact_version"] == 3

    # A re-cited primary appears once: the normalized set is {primary} + extras.
    third = rec_ok(env, "cite.d", "four")
    row = _row_of(env.db, third["artifact_id"])
    out = store.apply_correction(
        access=access,
        kind="supersede",
        artifact_id=third["artifact_id"],
        expected_version=2,
        target_content=_target_content(row, "superseded", "supersede"),
        replacement_content={**row["content"], "correction_refs": []},
        binding=_binding("superseded"),
        supersedes=[ref(third["artifact_id"], 2)],
    )
    assert out["code"] == "OK", out
    new_id = out["replacement"]["artifact_id"]
    assert [e for e in _relations(env.db) if e[0] == new_id] == [
        (new_id, 1, third["artifact_id"], 2, "supersedes")
    ]


def test_t05_correction_rollback_each_effect(tmp_path: Path) -> None:
    """R9: an injected failure after the replacement insert, after the history version,
    after the edge, and inside `receipt_writer` leaves zero rows, versions, edges and
    receipts, and releases the policy lock."""
    from rush.memory import relations
    from rush.memory import store as store_module

    env = make_env(tmp_path)
    store = TypedArtifactStore(env.root)
    access = access_for(env, "correct", apply=True)
    seeded = rec_ok(env, "roll.k", "v")
    row = _row_of(env.db, seeded["artifact_id"])
    target = _target_content(row, "superseded", "supersede")
    replacement = {**_target_content(row, "active", "supersede"), "correction_refs": []}
    before = _db_state(env.db)

    def run(**extra: Any) -> Any:
        return store.apply_correction(
            access=access,
            kind="supersede",
            artifact_id=seeded["artifact_id"],
            expected_version=2,
            target_content=target,
            replacement_content=replacement,
            binding=_binding("superseded"),
            **extra,
        )

    real_insert = TypedArtifactStore._insert_row
    real_write_version = store_module._write_version
    real_edge = relations.insert_relation_tx

    def after_insert(self: Any, conn: Any, stored: Any) -> None:
        real_insert(self, conn, stored)
        raise RuntimeError("after replacement insert")

    def after_history(conn: Any, artifact_id: str, *args: Any, **kwargs: Any) -> Any:
        result = real_write_version(conn, artifact_id, *args, **kwargs)
        if artifact_id == seeded["artifact_id"]:
            raise RuntimeError("after history version")
        return result

    def after_edge(conn: Any, **kwargs: Any) -> Any:
        real_edge(conn, **kwargs)
        raise RuntimeError("after edge")

    def receipt_raises(conn: Any, payload: dict[str, Any]) -> None:
        raise RuntimeError("inside receipt_writer")

    def receipt_written_then_raises(conn: Any, payload: dict[str, Any]) -> None:
        store._write_receipt(
            conn, "rollback-receipt", payload["artifact_id"], "edit", 3, {}
        )
        raise RuntimeError("after receipt row")

    cases = [
        (TypedArtifactStore, "_insert_row", after_insert, {}, "after replacement"),
        (store_module, "_write_version", after_history, {}, "after history"),
        (relations, "insert_relation_tx", after_edge, {}, "after edge"),
        (None, "", None, {"receipt_writer": receipt_raises}, "inside receipt_writer"),
        (
            None,
            "",
            None,
            {"receipt_writer": receipt_written_then_raises},
            "after receipt row",
        ),
    ]
    for owner, attribute, replacement_fn, extra, message in cases:
        with pytest.MonkeyPatch.context() as patch:
            if owner is not None:
                patch.setattr(owner, attribute, replacement_fn)
            with pytest.raises(RuntimeError, match=message):
                run(**extra)
        assert _db_state(env.db) == before, message
        probe = _LockProbe(env.data_root)
        assert probe.held() is False, message
        probe.finish()
    assert _relations(env.db) == []
    assert _receipts(env.db, "rollback-receipt") == []

    # A final access recheck failure rolls back too (no receipt, no versions).
    revoke(env, "project")
    out = run()
    assert out["code"] == "E_PERMISSION"
    assert _db_state(env.db) == before


def test_t05_correction_edge_to_superseded_version(tmp_path: Path) -> None:
    """R9: after supersede the edge replacement@1 -> original@cited exists while the
    original's current version is newer and `superseded`; the public `link` on the same
    endpoints is refused and adds no edge."""
    env = make_env(tmp_path)
    store = TypedArtifactStore(env.root)
    access = access_for(env, "correct", apply=True)
    original = rec_ok(env, "edge.k", "old")
    row = _row_of(env.db, original["artifact_id"])
    out = store.apply_correction(
        access=access,
        kind="supersede",
        artifact_id=original["artifact_id"],
        expected_version=2,
        target_content=_target_content(row, "superseded", "supersede"),
        replacement_content={**row["content"], "value": "new", "correction_refs": []},
        binding=_binding("superseded"),
    )
    assert out["code"] == "OK", out
    rep_id = out["replacement"]["artifact_id"]
    edges = _relations(env.db)
    assert edges == [(rep_id, 1, original["artifact_id"], 2, "supersedes")]
    assert _row_of(env.db, original["artifact_id"])["artifact_version"] == 3

    link = _res(
        MemoryTool().run(
            env.root,
            operation="link",
            request={
                "source_id": rep_id,
                "source_version": 2,
                "target_id": original["artifact_id"],
                "target_version": 2,
                "kind": "supersedes",
            },
            permissions=ExecutionPermissions(cache_write=True),
        )
    )
    assert link.code == "E_NOT_VISIBLE", link.dump()
    assert _relations(env.db) == edges

    # reject and correct write no edge.
    other = rec_ok(env, "edge.other", "v")
    other_row = _row_of(env.db, other["artifact_id"])
    store.apply_correction(
        access=access,
        kind="reject",
        artifact_id=other["artifact_id"],
        expected_version=2,
        target_content=_target_content(other_row, "rejected", "reject"),
        binding=_binding("rejected"),
    )
    assert _relations(env.db) == edges


def test_t05_insert_relation_tx_contract(tmp_path: Path) -> None:
    """R9: `insert_relation_tx` runs inside the caller's transaction (a rollback removes
    the edge), validates input and endpoint version rows, and performs no visibility,
    owner or current-version check."""
    from rush.memory.relations import insert_relation_tx

    env = make_env(tmp_path)
    first = rec_ok(env, "rel.a", 1)
    second = rec_ok(env, "rel.b", 2)
    seed_row(
        TypedArtifactStore(env.root),
        "foreign",
        OwnerScope("project", "somewhere-else"),
        key="rel.c",
        value=3,
        scope="project",
    )
    a, b = first["artifact_id"], second["artifact_id"]

    def run(commit: bool, **kwargs: Any) -> dict[str, Any]:
        with contextlib.closing(sqlite3.connect(env.db, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute("BEGIN IMMEDIATE")
            out = insert_relation_tx(conn, **kwargs)
            (conn.commit if commit else conn.rollback)()
            return out

    edge = {
        "source_id": a,
        "source_version": 2,
        "target_id": b,
        "target_version": 2,
        "kind": "depends_on",
    }
    out = run(False, **edge)
    assert out["code"] == "OK" and isinstance(out["sequence"], int)
    assert _relations(env.db) == []  # the caller's rollback removed it
    out = run(True, **edge)
    assert out["code"] == "OK"
    assert _relations(env.db) == [(a, 2, b, 2, "depends_on")]

    def code(**overrides: Any) -> str:
        return str(run(False, **{**edge, **overrides})["code"])

    assert code(kind="not_a_kind") == "E_INPUT"
    assert code(source_version=True) == "E_INPUT"
    assert code(target_version=10**400) == "E_INPUT"
    assert code(source_version="2") == "E_INPUT"
    assert code(kind="supersedes", target_id=a) == "E_INPUT"  # self edge
    assert code(source_version=99) == "E_NOT_VISIBLE"
    assert code(target_id="does-not-exist") == "E_NOT_VISIBLE"
    # No current-version and no owner check: a non-current version and a foreign-owner
    # row are accepted when their version rows exist.
    assert code(source_version=1) == "OK"
    assert code(target_id="foreign", target_version=1) == "OK"
    # A deleted version row is not an endpoint.
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(
            "UPDATE memory_artifact_versions SET deleted = 1 "
            "WHERE artifact_id = ? AND artifact_version = 1",
            (b,),
        )
        conn.commit()
    assert code(target_version=1) == "E_NOT_VISIBLE"
    # A supersedes cycle is refused.
    assert run(True, **{**edge, "kind": "supersedes"})["code"] == "OK"
    inverse = {**edge, "source_id": b, "target_id": a, "kind": "supersedes"}
    assert run(False, **inverse)["code"] == "E_INPUT"
    assert _relations(env.db) == [
        (a, 2, b, 2, "depends_on"),
        (a, 2, b, 2, "supersedes"),
    ]


def test_t05_correction_on_pending_and_stale_rows(tmp_path: Path) -> None:
    """R9: `reject` of a `pending` row and `correct` of a stale-anchored row both apply
    (usable_as_current is not required to correct)."""
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility

    env = make_env(tmp_path)
    (env.root / "mod.py").write_text("def Known():\n    return 1\n", encoding="utf-8")
    store = TypedArtifactStore(env.root)
    seed_row(
        store,
        "pending-1",
        env.owner,
        key="p.k",
        value="v",
        scope="project",
        authority="explicit",
        applicability="pending",
        project_id=env.project_id,
        worktree_id=env.worktree_id,
    )
    seed_row(
        store,
        "stale-1",
        env.owner,
        key="s.k",
        value="v",
        scope="project",
        authority="explicit",
        project_id=env.project_id,
        worktree_id=env.worktree_id,
        symbol_ref="mod.py::Known",
        content_hash="0" * 64,
    )
    ask = MemoryAccess.resolve(env.root, operation="ask", owner_scope=env.owner)
    assert ask is not None
    stale_decision = evaluate_artifact_visibility(
        store, store.get_current_row("stale-1"), access=ask, mode="ordinary"
    )
    assert stale_decision.freshness == "stale"
    assert stale_decision.usable_as_current is False

    pending = call(
        env,
        "correct",
        artifact_id="pending-1",
        layer="project",
        kind="reject",
        reason="not wanted",
        expected_version=1,
        user_stated=True,
        apply=True,
    )
    assert pending.code == "OK", pending.dump()
    assert pending.data["artifact_version"] == 2
    assert _row_of(env.db, "pending-1")["applicability"] == "rejected"
    assert [v["artifact_version"] for v in _version_rows(env.db, "pending-1")] == [1, 2]

    stale = call(
        env,
        "correct",
        artifact_id="stale-1",
        layer="project",
        kind="correct",
        reason="still true",
        expected_version=1,
        value="v2",
        user_stated=True,
        apply=True,
    )
    assert stale.code == "OK", stale.dump()
    assert stale.data["artifact_version"] == 3
    row = _row_of(env.db, "stale-1")
    assert row["trust_tier"] == "STATED" and row["applicability"] == "active"
    assert row["symbol_ref"] == "mod.py::Known"
    assert [v["artifact_version"] for v in _version_rows(env.db, "stale-1")] == [
        1,
        2,
        3,
    ]


# --- R10/R11: the preference API contract --------------------------------------------


def test_t05_preference_api_contract(tmp_path: Path) -> None:
    import inspect

    from rush.memory.preference_store import PreferenceError

    keyword_only = inspect.Parameter.KEYWORD_ONLY

    def shape(function: Any) -> dict[str, tuple[Any, Any]]:
        return {
            name: (p.kind, p.default)
            for name, p in inspect.signature(function).parameters.items()
            if name != "self"
        }

    ctor = shape(PreferenceStore.__init__)
    assert list(ctor) == ["project_root", "data_root"]
    assert ctor["project_root"][1] is None
    assert ctor["data_root"] == (keyword_only, None)

    record = shape(PreferenceStore.record)
    assert list(record) == [
        "key",
        "value",
        "access",
        "apply",
        "cache_write",
        "scope",
        "authority",
        "task_id",
        "expires_at",
        "user_stated",
        "attribution",
    ]
    assert all(record[n][0] == keyword_only for n in list(record)[2:])
    assert [record[n][1] for n in ("apply", "cache_write", "user_stated")] == [
        False
    ] * 3
    assert [record[n][1] for n in ("task_id", "expires_at", "attribution")] == [
        None
    ] * 3

    correct = shape(PreferenceStore.correct)
    assert list(correct) == [
        "artifact_id",
        "access",
        "apply",
        "cache_write",
        "layer",
        "kind",
        "reason",
        "expected_version",
        "value",
        "user_stated",
    ]
    assert all(correct[n][0] == keyword_only for n in list(correct)[1:])
    assert [correct[n][1] for n in ("apply", "cache_write", "user_stated")] == [
        False
    ] * 3
    assert correct["value"][1] is not inspect.Parameter.empty

    end_task = shape(PreferenceStore.end_task)
    assert list(end_task) == [
        "access",
        "apply",
        "cache_write",
        "project_id",
        "worktree_id",
        "task_id",
        "expected_versions",
    ]
    assert all(p[0] == keyword_only for p in end_task.values())

    migrate = shape(PreferenceStore.migrate)
    assert list(migrate) == ["access", "apply", "cache_write", "preview_digest"]
    assert all(p[0] == keyword_only for p in migrate.values())

    resolve_shape = shape(PreferenceStore.resolve)
    assert list(resolve_shape) == [
        "key",
        "access",
        "overlay_access",
        "query",
        "project_id",
        "worktree_id",
        "task_id",
        "now",
    ]
    assert all(resolve_shape[n][0] == keyword_only for n in list(resolve_shape)[1:])
    assert resolve_shape["overlay_access"][1] is None
    assert resolve_shape["task_id"][1] is None

    # PreferenceError(code, reason): the seven documented codes, `CODE: reason` text.
    for code in (
        "E_INPUT",
        "E_PERMISSION",
        "E_OWNER",
        "E_SCOPE",
        "E_VERSION",
        "E_MIGRATION",
        "E_UNAVAILABLE",
    ):
        error = PreferenceError(code, "some_reason")
        assert (error.code, error.reason) == (code, "some_reason")
        assert str(error) == f"{code}: some_reason"

    env = make_env(tmp_path)
    store = PreferenceStore(env.root)
    rec_ok(env, "format", "wide")
    project_access = access_for(env, "resolve")
    overlay_access = access_for(env, "resolve", personal=True)

    # `layer` / `scope` must match the access owner: E_OWNER layer_owner_mismatch.
    with pytest.raises(PreferenceError) as exc:
        store.record(
            "k",
            "v",
            access=access_for(env, "record", apply=True),
            apply=True,
            cache_write=True,
            scope="personal",
            authority="explicit",
            user_stated=True,
        )
    assert (exc.value.code, exc.value.reason) == ("E_OWNER", "layer_owner_mismatch")
    with pytest.raises(PreferenceError) as exc:
        store.correct(
            "x",
            access=access_for(env, "correct", apply=True),
            layer="personal",
            kind="correct",
            reason="r",
            expected_version=1,
            value="v",
        )
    assert (exc.value.code, exc.value.reason) == ("E_OWNER", "layer_owner_mismatch")
    assert env.project_id is not None and env.worktree_id is not None
    with pytest.raises(PreferenceError) as exc:
        store.end_task(
            access=access_for(env, "end_task", personal=True),
            project_id=env.project_id,
            worktree_id=env.worktree_id,
            task_id="T",
            expected_versions={},
        )
    assert (exc.value.code, exc.value.reason) == ("E_OWNER", "layer_owner_mismatch")
    with pytest.raises(PreferenceError) as exc:
        store.resolve(
            "format",
            access=overlay_access,
            project_id=env.project_id,
            worktree_id=env.worktree_id,
        )
    assert (exc.value.code, exc.value.reason) == ("E_OWNER", "layer_owner_mismatch")

    # Policy-mode ids: differing project/worktree/task ids are E_INPUT.
    bad_ids: tuple[dict[str, Any], ...] = (
        {"project_id": "other", "worktree_id": env.worktree_id},
        {"project_id": env.project_id, "worktree_id": "other"},
    )
    for bad in bad_ids:
        with pytest.raises(PreferenceError) as exc:
            store.resolve("format", access=project_access, **bad)
        assert (exc.value.code, exc.value.reason) == ("E_INPUT", "ids_mismatch")
    with pytest.raises(PreferenceError) as exc:
        store.resolve(
            "format",
            access=project_access,
            project_id=env.project_id,
            worktree_id=env.worktree_id,
            task_id="T",
        )
    assert (exc.value.code, exc.value.reason) == ("E_INPUT", "task_id_mismatch")

    # MCP and in-process answers are identical.
    inproc = store.resolve(
        "format",
        access=project_access,
        overlay_access=overlay_access,
        project_id=env.project_id,
        worktree_id=env.worktree_id,
    )
    assert inproc["code"] == "OK"
    mcp = resolve(env, key="format", via="mcp")
    assert mcp.code == "OK"
    assert mcp.data == {k: v for k, v in inproc.items() if k != "code"}
    assert resolve(env, key="format", via="cli").data == mcp.data
    assert resolve(env, key="format", via="tool").data == mcp.data

    # A PreferenceError and its transport form carry the same reason and message.
    with pytest.raises(PreferenceError) as exc:
        store.record(
            "k",
            "v",
            access=access_for(env, "record", apply=True),
            apply=True,
            cache_write=True,
            scope="project",
            authority="explicit",
            user_stated=False,
        )
    error = exc.value
    assert (error.code, error.reason) == ("E_PERMISSION", "user_stated_required")
    for via in TRANSPORTS:
        wire = rec(env, "k", "v", via=via, user_stated=False)
        assert wire.code == error.code, via
        assert wire.data == {"reason": error.reason, "message": str(error)}, via

    _api_predicate_rows(tmp_path, env)


def _api_predicate_rows(tmp_path: Path, env: Env) -> None:
    """G8 (brief 3.1): the layer/owner, id and apply-only predicates, one row per access
    form (`policy`, `overlay`, `legacy_allowlist`), asserted in the brief 3.14 order."""
    from rush.memory import authorization as auth

    ov = env.overlay_owner.as_dict()
    record = {"key": "k", "value": "v", "authority": "explicit", "source": PREFS}
    correct = {
        "artifact_id": "x",
        "kind": "correct",
        "reason": "r",
        "expected_version": 1,
        "value": "v",
    }
    before = snapshot(env)

    def row(label: str, expected: tuple[str, str], action: str, **request: Any) -> None:
        task = request.pop("task_id", None)
        for via in ("tool", "mcp"):
            out = call(
                env,
                action,
                via=via,
                task_id=task,
                apply=True,
                user_stated=True,
                **request,
            )
            assert (out.code, out.reason) == expected, (label, via, out.dump())
        assert snapshot(env) == before, label

    owner_mismatch = ("E_OWNER", "layer_owner_mismatch")
    # policy form (the project owner's access).
    row("policy-record-personal", owner_mismatch, "record", scope="personal", **record)
    row(
        "policy-correct-personal",
        owner_mismatch,
        "correct",
        layer="personal",
        **correct,
    )
    row(
        "policy-record-task-without-id",
        ("E_INPUT", "task_id_mismatch"),
        "record",
        scope="task",
        **record,
    )
    row(
        "policy-record-project-with-task-id",
        ("E_INPUT", "task_id_mismatch"),
        "record",
        scope="project",
        task_id="T",
        **record,
    )
    row(
        "policy-record-source",
        ("E_SCOPE", "source_not_granted"),
        "record",
        scope="project",
        **{**record, "source": "not-granted"},
    )
    # overlay form (owner == the overlay owner): the layer predicate comes first.
    row(
        "overlay-record-project",
        owner_mismatch,
        "record",
        scope="project",
        owner_scope=ov,
        **record,
    )
    row(
        "overlay-record-task",
        owner_mismatch,
        "record",
        scope="task",
        task_id="T",
        owner_scope=ov,
        **record,
    )
    row(
        "overlay-correct-project",
        owner_mismatch,
        "correct",
        layer="project",
        owner_scope=ov,
        **correct,
    )
    row("overlay-resolve", owner_mismatch, "resolve", key="k", owner_scope=ov)
    row(
        "overlay-end-task",
        owner_mismatch,
        "end_task",
        task_id="T",
        owner_scope=ov,
        expected_versions={},
    )
    row(
        "overlay-migrate",
        owner_mismatch,
        "migrate",
        owner_scope=ov,
        preview_digest="0" * 64,
    )

    # `owner_required`: two non-overlay owners hold grants and the request names none.
    two = make_env(tmp_path, "two_owners")
    _grant(
        auth,
        two.root,
        OwnerScope("user", "alice"),
        two.data_root,
        sources=(PREFS,),
        ops=PROJECT_OPS,
    )
    ambiguous = call(two, "resolve", key="k")
    assert (ambiguous.code, ambiguous.reason) == ("E_INPUT", "owner_required")
    assert ambiguous.data["field"] == "owner_scope"
    named = call(two, "resolve", key="k", owner_scope=two.owner.as_dict())
    assert named.code == "OK", named.dump()

    # legacy_allowlist form: every write predicate yields to `policy_grant_required`.
    legacy_root = _registered(tmp_path / "predicates_legacy", env.data_root)
    for action, request in (
        ("record", {"scope": "personal", **record}),
        ("record", {"scope": "task", **record}),
        ("correct", {"layer": "personal", **correct}),
    ):
        out = call(
            legacy_root,
            action,
            session=[PREFS],
            apply=True,
            user_stated=True,
            **request,
        )
        assert (out.code, out.reason) == ("E_PERMISSION", "policy_grant_required")


def test_t05_legacy_preference_writes_refused(tmp_path: Path) -> None:
    """R10: with no policy (D1 `legacy`) every write action, preview and apply, is
    `E_PERMISSION policy_grant_required` with the `.rush/` inventory unchanged; `resolve`
    still answers with caller ids."""
    data_root = default_data_root()
    root = _registered(tmp_path / "legacy", data_root)
    legacy = PreferenceStore(root)
    legacy.set("format", "compact")
    from rush.memory.migration import migrate_preference_store

    assert migrate_preference_store(root) == 1
    rush_before = _digest_tree(root / ".rush")
    origin = _pref_rows(_db(root))[0]
    actions: dict[str, dict[str, Any]] = {
        "record": {
            "key": "k",
            "value": "v",
            "scope": "project",
            "authority": "explicit",
            "source": PREFS,
            "user_stated": True,
        },
        "correct": {
            "artifact_id": origin["id"],
            "layer": "project",
            "kind": "reject",
            "reason": "r",
            "expected_version": origin["artifact_version"],
            "user_stated": True,
        },
        "end_task": {"task_id": "T", "expected_versions": {}},
        "migrate": {"preview_digest": "0" * 64},
    }
    for action, request in actions.items():
        for apply in (False, True):
            for via in ("tool", "mcp"):
                result = call(
                    root, action, via=via, session=[PREFS, MIG], apply=apply, **request
                )
                assert result.code == "E_PERMISSION", (
                    action,
                    apply,
                    via,
                    result.dump(),
                )
                assert result.reason == "policy_grant_required", (action, apply, via)
                assert _digest_tree(root / ".rush") == rush_before, (action, apply, via)

    from rush.memory.preference_store import PreferenceError
    from rush.memory.retrieval import MemoryAccess

    legacy_access = MemoryAccess.legacy(
        root,
        [PREFS, MIG],
        owner_scope=legacy_owner_scope(root),
        operation="preference",
    )
    for apply in (False, True):
        with pytest.raises(PreferenceError) as exc:
            legacy.record(
                "k",
                "v",
                access=legacy_access,
                apply=apply,
                cache_write=True,
                scope="project",
                authority="explicit",
                user_stated=True,
            )
        assert (exc.value.code, exc.value.reason) == (
            "E_PERMISSION",
            "policy_grant_required",
        )
    assert _digest_tree(root / ".rush") == rush_before

    # resolve still answers, with the caller's ids and an allowlist: origin rows are advice.
    for via in TRANSPORTS:
        out = call(
            root,
            "resolve",
            via=via,
            session=[PREFS, MIG],
            key="format",
            project_id="legacy-project",
            worktree_id="legacy-worktree",
        )
        assert out.code == "OK", (via, out.dump())
        item = entry(out, "format")
        assert item["status"] == "none" and item["selected"] is None
        assert [r["source"] for r in item["advice"]] == [MIG]
        assert out.data["layers"]["personal"]["state"] == "denied"
        assert out.data["layers"]["personal"]["reason"] == "policy_missing"
    empty_allowlist = call(
        root, "resolve", session=[], key="format", project_id="p", worktree_id="w"
    )
    assert empty_allowlist.code == "E_PERMISSION"
    assert empty_allowlist.reason == "session_allowlist_required"
    missing_ids = call(root, "resolve", session=[PREFS], key="format")
    assert missing_ids.code == "E_INPUT" and missing_ids.reason == "ids_required"
    assert _digest_tree(root / ".rush") == rush_before


def test_t05_legacy_readers_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R11/D10: `get`/`list_all` outputs are pinned (recorded from HEAD), `resolve`
    never calls them, and no `src/rush` module outside `preference_store.py` calls
    `list_all` or `PreferenceStore(...).get`."""
    from rush.memory.migration import migrate_preference_store

    data_root = default_data_root()
    root = _registered(tmp_path / "pinned", data_root)
    store = PreferenceStore(root)
    store.set("a", 1)
    store.set("b", {"n": [1, 2]})
    assert store.get("a") == 1
    assert store.list_all() == {"a": 1, "b": {"n": [1, 2]}}
    assert migrate_preference_store(root) == 2
    assert store.get("a") == 1
    assert store.get("b") == {"n": [1, 2]}
    assert store.get("zz", "dflt") == "dflt"
    assert store.list_all() == {"a": 1, "b": {"n": [1, 2]}}
    origin = next(r for r in _pref_rows(_db(root)) if r["origin_id"] == "a")
    TypedArtifactStore(root).archive(
        origin["id"],
        expected_version=origin["artifact_version"],
        scope="preference",
        owner_scope=legacy_owner_scope(root),
        apply=True,
    )
    assert store.get("a") == 1  # an archived migrated row is still returned
    assert store.list_all() == {"a": 1, "b": {"n": [1, 2]}}
    store.set("a", 5)
    assert store.get("a") == 5
    assert store.delete("b") is True
    assert store.get("b", "dflt") == "dflt"
    assert store.list_all() == {"a": 5}

    # (b) resolve in every transport never touches the compatibility readers.
    env = make_env(tmp_path, "resolve_env")
    rec_ok(env, "format", "wide")
    rec_ok(env, "format", "compact", scope="personal")

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("resolve must not call a compatibility reader")

    with monkeypatch.context() as patch:
        patch.setattr(PreferenceStore, "get", boom)
        patch.setattr(PreferenceStore, "list_all", boom)
        for via in TRANSPORTS:
            assert resolve(env, key="format", via=via).code == "OK"
            assert resolve(env, query="wide", via=via).code == "OK"
        inproc = PreferenceStore(env.root).resolve(
            "format",
            access=access_for(env, "resolve"),
            overlay_access=access_for(env, "resolve", personal=True),
            project_id=env.project_id,
            worktree_id=env.worktree_id,
        )
        assert inproc["code"] == "OK"

    # (c) AST: no `.list_all(` and no `PreferenceStore(...).get(` outside the module.
    offenders: list[str] = []
    for path in sorted((REPO_SRC / "rush").rglob("*.py")):
        if path.as_posix().endswith("rush/memory/preference_store.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bound: set[str] = set()

        def is_store_call(node: ast.AST) -> bool:
            return isinstance(node, ast.Call) and (
                (isinstance(node.func, ast.Name) and node.func.id == "PreferenceStore")
                or (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr == "PreferenceStore"
                )
            )

        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and is_store_call(node.value):
                bound.update(t.id for t in node.targets if isinstance(t, ast.Name))
            if (
                isinstance(node, ast.AnnAssign)
                and node.value
                and is_store_call(node.value)
                and isinstance(node.target, ast.Name)
            ):
                bound.add(node.target.id)
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            ):
                continue
            receiver = node.func.value
            if node.func.attr == "list_all":
                offenders.append(f"{path}:{node.lineno} list_all")
            elif node.func.attr == "get" and (
                is_store_call(receiver)
                or (isinstance(receiver, ast.Name) and receiver.id in bound)
            ):
                offenders.append(f"{path}:{node.lineno} PreferenceStore.get")
    assert offenders == []


# --- R12/R13 ---------------------------------------------------------------------------


def test_t05_same_scope_conflict_unresolved(tmp_path: Path) -> None:
    a = make_env(tmp_path, "a")
    b = make_env(tmp_path, "b")
    wide = rec_ok(a, "format", "wide")
    narrow = rec_ok(a, "format", "narrow")
    ids = sorted([wide["artifact_id"], narrow["artifact_id"]])

    item = entry(resolve(a, key="format"), "format")
    assert item["status"] == "unresolved"
    assert item["selected"] is None and item["applied_refs"] == []
    assert [r["artifact_id"] for r in item["unresolved"]] == ids
    assert sorted(r["value"] for r in item["unresolved"]) == ["narrow", "wide"]
    assert why_view(item) == expected_why(
        [
            ("project", wide["artifact_id"], 2, "conflict_unresolved"),
            ("project", narrow["artifact_id"], 2, "conflict_unresolved"),
        ]
    )

    # Equal values are not a conflict: both apply.
    c = make_env(tmp_path, "c")
    one = rec_ok(c, "format", "wide")
    two = rec_ok(c, "format", "wide")
    item = entry(resolve(c, key="format"), "format")
    low, high = sorted([one["artifact_id"], two["artifact_id"]])
    assert item["status"] == "applied"
    assert item["selected"]["artifact_id"] == low
    assert [r["artifact_id"] for r in item["applied_refs"]] == [low, high]
    assert why_view(item) == expected_why(
        [("project", low, 2, "selected"), ("project", high, 2, "applied")]
    )

    # A rejection of one side resolves the conflict.
    rejected = call(
        a,
        "correct",
        artifact_id=narrow["artifact_id"],
        layer="project",
        kind="reject",
        reason="wrong",
        expected_version=2,
        user_stated=True,
        apply=True,
    )
    assert rejected.code == "OK", rejected.dump()
    item = entry(resolve(a, key="format"), "format")
    assert item["status"] == "applied" and item["selected"]["value"] == "wide"
    assert [r["artifact_id"] for r in item["contrary"]] == [narrow["artifact_id"]]
    assert why_view(item) == expected_why(
        [
            ("project", wide["artifact_id"], 2, "selected"),
            ("project", narrow["artifact_id"], 3, "rejected_contrary"),
        ]
    )

    # PR3 keys: personal records from two projects both match `(key)`; a project record
    # of A never matches in B.
    from_a = rec_ok(a, "theme", "dark", scope="personal")
    from_b = rec_ok(b, "theme", "dark", scope="personal")
    for env in (a, b):
        item = entry(resolve(env, key="theme"), "theme")
        assert item["status"] == "applied"
        assert sorted(r["artifact_id"] for r in item["applied_refs"]) == sorted(
            [from_a["artifact_id"], from_b["artifact_id"]]
        )
    in_b = resolve(b, key="format")
    assert "narrow" not in in_b.dump() and "wide" not in in_b.dump()
    assert wide["artifact_id"] not in in_b.dump()

    # A later supersession edge, written by the correction core citing both rows,
    # settles a same-scope conflict: the replacement wins over the cited row.
    d = make_env(tmp_path, "d")
    x = rec_ok(d, "layout", "one")
    y = rec_ok(d, "layout", "two")
    store = TypedArtifactStore(d.root)
    x_row = _row_of(d.db, x["artifact_id"])
    out = store.apply_correction(
        access=access_for(d, "correct", apply=True),
        kind="supersede",
        artifact_id=x["artifact_id"],
        expected_version=2,
        target_content=_target_content(x_row, "superseded", "supersede"),
        replacement_content={
            **x_row["content"],
            "value": "three",
            "correction_refs": [],
        },
        binding=_binding("superseded"),
        supersedes=[{"artifact_id": y["artifact_id"], "artifact_version": 2}],
    )
    assert out["code"] == "OK", out
    new_id = out["replacement"]["artifact_id"]
    item = entry(resolve(d, key="layout"), "layout")
    assert item["status"] == "applied"
    assert item["selected"]["artifact_id"] == new_id
    assert item["selected"]["value"] == "three"
    assert why_view(item) == expected_why(
        [
            ("project", new_id, 2, "selected"),
            ("project", y["artifact_id"], 2, "superseded_by_edge"),
            ("project", x["artifact_id"], 3, "superseded"),
        ]
    )


def test_t05_task_id_two_projects(tmp_path: Path) -> None:
    """R13/F2: the same `task_id` in two projects applies only in its own
    `(project_id, worktree_id, task_id)`; `end_task` ends only that triple."""
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility

    p1 = make_env(tmp_path, "p1")
    p2 = make_env(tmp_path, "p2")
    r1 = rec_ok(p1, "width", 10, scope="task", task_id="T1")
    r2 = rec_ok(p2, "width", 20, scope="task", task_id="T1")
    assert (
        entry(resolve(p1, key="width", task_id="T1"), "width")["selected"]["value"]
        == 10
    )
    assert (
        entry(resolve(p2, key="width", task_id="T1"), "width")["selected"]["value"]
        == 20
    )
    for env in (p1, p2):
        untasked = resolve(env, key="width")
        assert untasked.code == "OK", untasked.dump()
        assert all(e["selected"] is None for e in untasked.data["preferences"])

    # A different worktree id never matches the task triple.
    acc1 = MemoryAccess.resolve(
        p1.root, operation="ask", owner_scope=p1.owner, task_id="T1"
    )
    assert acc1 is not None
    store1 = TypedArtifactStore(p1.root)
    row1 = store1.get_current_row(r1["artifact_id"])
    assert evaluate_artifact_visibility(store1, row1, access=acc1).usable_as_current
    moved = dataclasses.replace(acc1, worktree_id=p2.worktree_id)
    decision = evaluate_artifact_visibility(store1, row1, access=moved)
    assert decision.usable_as_current is False
    assert "task_mismatch" in decision.reason_codes
    wrong_ids = call(
        p1,
        "end_task",
        project_id=p1.project_id,
        worktree_id=p2.worktree_id,
        task_id="T1",
        expected_versions={r1["artifact_id"]: 2},
        apply=True,
    )
    assert wrong_ids.code == "E_INPUT" and wrong_ids.reason == "ids_mismatch"

    ended = call(
        p1,
        "end_task",
        project_id=p1.project_id,
        worktree_id=p1.worktree_id,
        task_id="T1",
        expected_versions={r1["artifact_id"]: 2},
        apply=True,
    )
    assert ended.code == "OK", ended.dump()
    assert [e["artifact_id"] for e in ended.data["ended"]] == [r1["artifact_id"]]
    after = resolve(p1, key="width", task_id="T1")
    assert all(e["selected"] is None for e in after.data["preferences"])
    assert (
        entry(resolve(p2, key="width", task_id="T1"), "width")["selected"]["value"]
        == 20
    )
    row = _row_of(p1.db, r1["artifact_id"])
    assert row["expired_at"] is not None
    assert row["expired_by"] == "end_task:T1"
    assert _row_of(p2.db, r2["artifact_id"])["expired_at"] is None

    # Stale, extra or missing expected_versions are E_VERSION with zero effects.
    other = rec_ok(p2, "width2", 5, scope="task", task_id="T1")
    before = snapshot(p2)
    for versions, reason in (
        ({r2["artifact_id"]: 2}, "task_records_changed"),  # misses `width2`
        ({r2["artifact_id"]: 2, other["artifact_id"]: 1}, "version_changed"),
        (
            {r2["artifact_id"]: 2, other["artifact_id"]: 2, "ghost": 1},
            "task_records_changed",
        ),
    ):
        refused = call(
            p2, "end_task", task_id="T1", expected_versions=versions, apply=True
        )
        assert refused.code == "E_VERSION", (versions, refused.dump())
        assert refused.reason == reason, versions
    assert snapshot(p2) == before


# --- R15: compatibility `set`/`delete` and `rush context persona --set` ----------------


def _json_data(env: Env) -> dict[str, Any]:
    from rush.memory.transactions import CASMapTransaction

    return dict(
        CASMapTransaction(file_path=env.prefs_json, root_path=env.root)
        .read(allow_missing=True)
        .data
    )


def _persona(root: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> Any:
    monkeypatch.chdir(root)
    return CliRunner().invoke(cli, ["context", "persona", *args])


def _migrated_env(
    tmp_path: Path, name: str, data: dict[str, Any], **kwargs: Any
) -> Env:
    """A policy-mode project whose `preferences.json` keys were migrated to origin rows
    and whose source file was then re-created with the same content."""
    env = make_env(tmp_path, name, legacy_json=data, **kwargs)
    _migrate_apply(env)
    assert not env.prefs_json.exists()
    _external_edit(env, lambda _d: dict(data))
    return env


def test_t05_preference_set_policy_mode_requires_write_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.preference_store import PreferenceError

    # No {write} grant: set/delete/persona refuse with zero effects.
    nowrite = make_env(
        tmp_path,
        "nowrite",
        project_ops=("ask", "expand", "list"),
        overlay=False,
        legacy_json={"json.only": "j", "persona_style": "default"},
    )
    before_json = nowrite.prefs_json.read_bytes()
    before = snapshot(nowrite)
    with pytest.raises(PreferenceError) as exc:
        PreferenceStore(nowrite.root).set("json.only", "changed")
    assert (exc.value.code, exc.value.reason) == (
        "E_PERMISSION",
        "operation_not_granted",
    )
    with pytest.raises(PreferenceError) as exc:
        PreferenceStore(nowrite.root).delete("json.only")
    assert (exc.value.code, exc.value.reason) == (
        "E_PERMISSION",
        "operation_not_granted",
    )
    out = _persona(nowrite.root, monkeypatch, "--set", "terse")
    assert out.exit_code == 0, out.output
    assert out.output == "skipped: E_PERMISSION operation_not_granted\n"
    assert nowrite.prefs_json.read_bytes() == before_json
    assert snapshot(nowrite) == before

    # With the grant: the JSON and the origin row are both updated.
    env = _migrated_env(
        tmp_path,
        "granted",
        {"o.key": "v1", "json.only": "j", "persona_style": "default"},
    )
    store = PreferenceStore(env.root)
    store.set("o.key", "v2")
    assert store.get("o.key") == "v2"
    assert _json_data(env)["o.key"] == "v2"
    origin = next(r for r in _pref_rows(env.db) if r["origin_id"] == "o.key")
    assert origin["content"] == {"key": "o.key", "value": "v2"}
    assert origin["artifact_version"] == 2
    store.set("fresh.key", "f")  # no origin row: a JSON-only update
    assert _json_data(env)["fresh.key"] == "f"
    assert all(r["origin_id"] != "fresh.key" for r in _pref_rows(env.db))
    out = _persona(env.root, monkeypatch, "--set", "terse")
    assert out.exit_code == 0 and out.output == "Persona style set to: terse\n"
    assert _json_data(env)["persona_style"] == "terse"
    assert store.delete("fresh.key") is True
    assert "fresh.key" not in _json_data(env)
    assert store.delete("o.key") is True
    assert _json_data(env).get("o.key") is None
    tombstone = next(r for r in _pref_rows(env.db) if r["origin_id"] == "o.key")
    assert tombstone["content"] == {"deleted": True}

    # {write} without source `migration:preference_store`: refused for an origin key,
    # allowed for a JSON-only key; bytes and rows unchanged on refusal.
    narrow = _migrated_env(tmp_path, "narrow", {"persona_style": "default", "o2": "v"})
    regrant(narrow, "project", ops=PROJECT_OPS, sources=(PREFS,))
    narrow_json = narrow.prefs_json.read_bytes()
    narrow_before = snapshot(narrow)
    with pytest.raises(PreferenceError) as exc:
        PreferenceStore(narrow.root).set("persona_style", "terse")
    assert (exc.value.code, exc.value.reason) == ("E_PERMISSION", "source_not_granted")
    with pytest.raises(PreferenceError) as exc:
        PreferenceStore(narrow.root).delete("o2")
    assert (exc.value.code, exc.value.reason) == ("E_PERMISSION", "source_not_granted")
    out = _persona(narrow.root, monkeypatch, "--set", "terse")
    assert out.exit_code == 0, out.output
    assert out.output == (
        "skipped: E_PERMISSION source_not_granted "
        "(grant source migration:preference_store)\n"
    )
    assert narrow.prefs_json.read_bytes() == narrow_json
    assert snapshot(narrow) == narrow_before
    PreferenceStore(narrow.root).set("json.only.new", "ok")
    assert _json_data(narrow)["json.only.new"] == "ok"

    # `legacy` mode is unchanged: no receipts, no policy lock.
    legacy_root = _registered(tmp_path / "legacy", default_data_root())
    legacy = PreferenceStore(legacy_root)
    legacy.set("k", "v")
    assert legacy.get("k") == "v"
    assert legacy.delete("k") is True
    assert _receipts(_db(legacy_root), "preference-%") == []


# --- R15: lock order 2 then 4 ----------------------------------------------------------

_LOCK_CHILD = textwrap.dedent(
    """
    import contextlib, json, sys, time
    from pathlib import Path

    args = json.loads(sys.argv[1])
    import rush.dashboard.state as state

    real = state.cross_process_project_lock
    events = []

    @contextlib.contextmanager
    def spy(project_id, *a, **k):
        events.append(["enter", str(project_id), time.monotonic()])
        with real(project_id, *a, **k):
            events.append(["held", str(project_id), time.monotonic()])
            yield
        events.append(["exit", str(project_id), time.monotonic()])

    state.cross_process_project_lock = spy
    from rush.memory.preference_store import PreferenceStore
    from rush.memory.retrieval import MemoryAccess
    from rush.memory.store import legacy_owner_scope

    root = Path(args["root"])
    Path(args["ready"]).write_text("ready")
    deadline = time.monotonic() + 60
    while not Path(args["go"]).exists():
        if time.monotonic() > deadline:
            sys.exit(3)
        time.sleep(0.005)
    if args["role"] == "set":
        PreferenceStore(root).set("lock.key", "v")
    else:
        store = PreferenceStore(root)
        owner = legacy_owner_scope(root)

        def access(apply):
            found = MemoryAccess.resolve(
                root,
                operation="preference",
                action="migrate",
                apply=apply,
                owner_scope=owner,
                requested_sources=["migration:preference_store"],
            )
            assert found is not None
            return found

        from rush.memory.preference_store import PreferenceError

        for _attempt in range(10):
            preview = store.migrate(access=access(False), preview_digest=None)
            try:
                store.migrate(
                    access=access(True),
                    apply=True,
                    cache_write=True,
                    preview_digest=preview["preview_digest"],
                )
                break
            except PreferenceError as error:
                # Losing the race with the concurrent `set` is a re-preview, not a bug.
                if error.reason != "preview_changed":
                    raise
        else:
            sys.exit(4)
    Path(args["log"]).write_text(json.dumps(events))
    """
)


def test_t05_preference_set_lock_order_2_then_4(tmp_path: Path) -> None:
    """R15/G3: concurrent `set` and preference `migrate` apply in two processes both
    finish within 5 s (no deadlock) and take the policy lock before the `"preferences:"`
    lock, nested, in both."""
    env = make_env(tmp_path, legacy_json={"m.key": "m"})
    go = tmp_path / "go"
    children: list[tuple[str, Path, subprocess.Popen[str]]] = []
    for role in ("set", "migrate"):
        log = tmp_path / f"{role}.log"
        ready = tmp_path / f"{role}.ready"
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                _LOCK_CHILD,
                json.dumps(
                    {
                        "role": role,
                        "root": str(env.root),
                        "log": str(log),
                        "ready": str(ready),
                        "go": str(go),
                    }
                ),
            ],
            env={**os.environ, "PYTHONPATH": str(REPO_SRC)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        children.append((role, log, process))
    deadline = time.monotonic() + 60
    for role, _log, process in children:
        ready = tmp_path / f"{role}.ready"
        while not ready.exists():
            assert process.poll() is None, process.communicate()
            assert time.monotonic() < deadline, "child did not become ready"
            time.sleep(0.01)
    go.write_text("go")
    started = time.monotonic()
    for role, _log, process in children:
        remaining = max(0.1, 5.0 - (time.monotonic() - started))
        try:
            out, err = process.communicate(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
            out, err = process.communicate()
            raise AssertionError(
                f"{role} did not finish within 5 s: {out}{err}"
            ) from None
        assert process.returncode == 0, (role, out, err)
    for role, log, _process in children:
        events = json.loads(log.read_text())
        policy = [e for e in events if e[1].startswith("memory-policy:")]
        prefs = [e for e in events if e[1].startswith("preferences:")]
        assert policy and prefs, (role, events)
        names = [(e[0], e[1].split(":", 1)[0]) for e in events]
        enter_policy = names.index(("enter", "memory-policy"))
        enter_prefs = names.index(("enter", "preferences"))
        last = len(names) - 1
        exit_prefs = last - names[::-1].index(("exit", "preferences"))
        exit_policy = last - names[::-1].index(("exit", "memory-policy"))
        assert enter_policy < enter_prefs < exit_prefs < exit_policy, (role, events)
    assert PreferenceStore(env.root).get("lock.key") == "v"
    assert PreferenceStore(env.root).get("m.key") == "m"


# --- R15: publication recovery -------------------------------------------------------


def _publication_receipts(env: Env) -> list[dict[str, Any]]:
    return _receipts(env.db, "preference-publication:%")


def test_t05_preference_set_publication_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.preference_store import PreferenceError
    from rush.memory.transactions import (
        CASConflictError,
        CASMapTransaction,
        StoreIOError,
    )

    real_write = CASMapTransaction.write

    def failing_write(error: Exception, *, lands: bool = False) -> Any:
        def write(self: Any, *args: Any, **kwargs: Any) -> Any:
            if lands:
                real_write(self, *args, **kwargs)
            raise error

        return write

    def origin(env: Env, key: str = "k") -> dict[str, Any]:
        return next(r for r in _pref_rows(env.db) if r["origin_id"] == key)

    # (a) a fault before the DB commit: zero effects, JSON untouched.
    a = _migrated_env(tmp_path, "a", {"k": "v0"})
    json_before, rows_before = a.prefs_json.read_bytes(), _db_state(a.db)

    def receipt_fault(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("fault at DB commit")

    with monkeypatch.context() as patch:
        patch.setattr(TypedArtifactStore, "_write_receipt", receipt_fault)
        with pytest.raises(RuntimeError, match="fault at DB commit"):
            PreferenceStore(a.root).set("k", "v1")
    assert a.prefs_json.read_bytes() == json_before
    assert _db_state(a.db) == rows_before
    assert _publication_receipts(a) == []

    # (b)/(c) a JSON CAS conflict or write error after the commit.
    for name, error in (
        ("b", CASConflictError("conflict")),
        ("c", StoreIOError("disk gone")),
    ):
        env = _migrated_env(tmp_path, name, {"k": "v0"})
        json_before = env.prefs_json.read_bytes()
        version_before = origin(env)["artifact_version"]
        with monkeypatch.context() as patch:
            patch.setattr(CASMapTransaction, "write", failing_write(error))
            with pytest.raises(PreferenceError) as exc:
                PreferenceStore(env.root).set("k", "v1")
        assert (exc.value.code, exc.value.reason) == (
            "E_UNAVAILABLE",
            "publication_unconfirmed",
        )
        assert env.prefs_json.read_bytes() == json_before
        assert origin(env)["content"] == {"key": "k", "value": "v1"}
        assert origin(env)["artifact_version"] == version_before + 1
        receipts = _publication_receipts(env)
        assert len(receipts) == 1 and receipts[0]["payload"]["stage"] == "committed"
        payload = receipts[0]["payload"]
        assert payload["key"] == "k" and payload["action"] == "set"
        assert payload["desired"] == {"k": "v1"}
        assert receipts[0]["kind"] == "preference_publication"
        created_at = receipts[0]["created_at"]
        # The next authorized set publishes it exactly once.
        PreferenceStore(env.root).set("other.key", "o")
        assert _json_data(env) == {"k": "v1", "other.key": "o"}
        receipts = _publication_receipts(env)
        assert len(receipts) == 1 and receipts[0]["payload"]["stage"] == "published"
        assert receipts[0]["created_at"] == created_at
        PreferenceStore(env.root).set("other.key", "o2")
        assert _json_data(env) == {"k": "v1", "other.key": "o2"}
        assert len(_publication_receipts(env)) == 1

    # (d) the JSON write landed but the call failed before the receipt completed.
    d = _migrated_env(tmp_path, "d", {"k": "v0"})
    with monkeypatch.context() as patch:
        patch.setattr(
            CASMapTransaction, "write", failing_write(StoreIOError("late"), lands=True)
        )
        with pytest.raises(PreferenceError) as exc:
            PreferenceStore(d.root).set("k", "v1")
    assert exc.value.reason == "publication_unconfirmed"
    assert _json_data(d) == {"k": "v1"}
    assert _publication_receipts(d)[0]["payload"]["stage"] == "committed"
    PreferenceStore(d.root).set("other.key", "o")
    assert _json_data(d) == {"k": "v1", "other.key": "o"}
    assert _publication_receipts(d)[0]["payload"]["stage"] == "published"

    # (e) the process dies after the commit: the next authorized set publishes.
    e = _migrated_env(tmp_path, "e", {"k": "v0"})
    child = textwrap.dedent(
        """
        import json, os, sys
        from pathlib import Path
        from rush.memory.transactions import CASMapTransaction
        from rush.memory.preference_store import PreferenceStore

        CASMapTransaction.write = lambda self, *a, **k: os._exit(9)
        PreferenceStore(Path(json.loads(sys.argv[1])["root"])).set("k", "v1")
        """
    )
    process = subprocess.run(
        [sys.executable, "-c", child, json.dumps({"root": str(e.root)})],
        env={**os.environ, "PYTHONPATH": str(REPO_SRC)},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert process.returncode == 9, process.stderr
    assert _json_data(e) == {"k": "v0"}
    assert origin(e)["content"] == {"key": "k", "value": "v1"}
    assert _publication_receipts(e)[0]["payload"]["stage"] == "committed"
    PreferenceStore(e.root).set("after.kill", "x")
    assert _json_data(e) == {"k": "v1", "after.kill": "x"}
    assert _publication_receipts(e)[0]["payload"]["stage"] == "published"

    # (f) an external JSON edit before the resume: E_VERSION, no overwrite, a conflict.
    f = _migrated_env(tmp_path, "f", {"k": "v0"})
    with monkeypatch.context() as patch:
        patch.setattr(
            CASMapTransaction, "write", failing_write(CASConflictError("conflict"))
        )
        with pytest.raises(PreferenceError):
            PreferenceStore(f.root).set("k", "v1")
    _external_edit(f, lambda d: {**d, "k": "third"})
    third = f.prefs_json.read_bytes()
    with pytest.raises(PreferenceError) as exc:
        PreferenceStore(f.root).set("other.key", "o")
    assert (exc.value.code, exc.value.reason) == ("E_VERSION", "migration_conflict")
    assert f.prefs_json.read_bytes() == third
    assert _publication_receipts(f)[0]["payload"]["stage"] == "superseded"
    assert call(f, "migrate").data["conflicts"] == ["k"]

    # (g) a delete tombstone survives every path.
    g = _migrated_env(tmp_path, "g", {"k": "v0", "keep": "x"})
    with monkeypatch.context() as patch:
        patch.setattr(
            CASMapTransaction, "write", failing_write(CASConflictError("conflict"))
        )
        with pytest.raises(PreferenceError) as exc:
            PreferenceStore(g.root).delete("k")
    assert exc.value.reason == "publication_unconfirmed"
    assert origin(g)["content"] == {"deleted": True}
    assert _json_data(g) == {"k": "v0", "keep": "x"}
    PreferenceStore(g.root).set("later", "1")
    assert _json_data(g) == {"keep": "x", "later": "1"}
    assert PreferenceStore(g.root).get("k", "dflt") == "dflt"
    assert "k" not in PreferenceStore(g.root).list_all()
    assert origin(g)["content"] == {"deleted": True}
    assert [r["payload"]["action"] for r in _publication_receipts(g)] == ["delete"]
    assert _publication_receipts(g)[0]["payload"]["stage"] == "published"

    # get/list_all outputs after a clean set.
    h = _migrated_env(tmp_path, "h", {"k": "v0"})
    PreferenceStore(h.root).set("k", "v9")
    assert PreferenceStore(h.root).get("k") == "v9"
    assert PreferenceStore(h.root).list_all() == {"k": "v9"}


# --- R16: task context ------------------------------------------------------------------

R16_SOURCES = (PREFS, MIG, "intent:*", "recipe:*", "repair_attempt:*")
REPAIR_SYMPTOM = "boomsym"


def _seed_task_rows(
    store: TypedArtifactStore, owner: OwnerScope | None, binding: tuple[str, str, str]
) -> dict[str, str]:
    """Task-bound intent, recipe and repair-episode rows (written through the store
    with the task binding, as the packet's `_insert_row` seeding)."""
    from rush.memory.store import compute_content_signature
    from rush.memory.trust import default_entry_tier

    project_id, worktree_id, task_id = binding
    task: dict[str, Any] = {
        "task_project_id": project_id,
        "task_worktree_id": worktree_id,
        "task_id": task_id,
    }
    intent = {
        "schema_version": 1,
        "kind": "intent",
        "intent_id": "i-task",
        "behavior_id": "b-task",
        "statement_ref": None,
        "source_refs": [],
        "check_refs": [],
        "exceptions": [],
        "status": "candidate",
    }
    recipe = {
        "schema_version": 1,
        "kind": "recipe",
        "recipe_id": "r-task",
        "purpose": "p",
        "helper_ref": None,
        "helper_source": None,
        "helper_source_hash": None,
        "required_symbols": [],
        "required_dependencies": {},
        "required_config_digest": None,
        "checks": [],
        "exceptions": [],
        "outcomes": [],
    }
    episode = {
        "schema_version": 1,
        "kind": "repair_episode",
        "symptom": REPAIR_SYMPTOM,
        "hypothesis": "h",
        "patch_hash": None,
        "conditions": {},
        "receipt_ref": None,
        "behavior_ids": [],
        "affected_symbols": [],
        "outcome": "untested",
        "commit_message": None,
    }
    tier = default_entry_tier("local_tool")
    now = time.time()
    for artifact in (
        MemoryArtifact(
            id="i-task",
            family="memory",
            subject="architectural_decision",
            trust_tier=tier,
            content=intent,
            source="intent:i-task",
            created_at=now,
            content_hash=compute_content_signature(intent),
            owner_scope=owner,
            **task,
        ),
        MemoryArtifact(
            id="r-task",
            family="skill",
            subject="skill_pattern",
            trust_tier=tier,
            content=recipe,
            source="recipe:r-task",
            created_at=now,
            content_hash=compute_content_signature(recipe),
            owner_scope=owner,
            **task,
        ),
        MemoryArtifact(
            id="ep-task",
            family="experience",
            subject="failure",
            trust_tier=tier,
            content=episode,
            source=f"repair_attempt:{REPAIR_SYMPTOM}",
            created_at=now,
            content_hash=compute_content_signature(episode),
            owner_scope=owner,
            **task,
        ),
    ):
        store.write(artifact)
    return {"intent": "i-task", "recipe": "r-task", "episode": "ep-task"}


def _read_ops(
    root: Path,
    owner: OwnerScope,
    task: str | None,
    *,
    session: list[str] | None,
    row_id: str,
    version: int,
    neighbor_root: str,
    neighbor_version: int,
) -> dict[str, Res]:
    """Every read route of R16 for one `task_id` (omitted when `None`)."""
    tool = MemoryTool()
    extra: dict[str, Any] = {"owner_scope": owner.as_dict()}
    if task is not None:
        extra["task_id"] = task
    if session is not None:
        extra["session_allowlist"] = session
    out: dict[str, Res] = {}
    for operation in ("ask", "recall", "list"):
        out[operation] = _res(
            tool.run(
                root,
                operation=operation,  # type: ignore[arg-type]
                subject="preference",
                query="taskneedle",
                request={"view": "compact"},
                **extra,
            )
        )
    out["expand"] = _res(
        tool.run(
            root,
            operation="expand",
            request={"id": row_id, "version": version},
            **extra,
        )
    )
    out["related_root"] = _res(
        tool.run(
            root,
            operation="related",
            request={"id": row_id, "version": version},
            **extra,
        )
    )
    out["related_neighbor"] = _res(
        tool.run(
            root,
            operation="related",
            request={"id": neighbor_root, "version": neighbor_version},
            **extra,
        )
    )
    for operation in ("prepare", "resume"):
        out[operation] = _res(
            tool.run(
                root,
                operation=operation,  # type: ignore[arg-type]
                request={"task": REPAIR_SYMPTOM, "conditions": {}},
                **extra,
            )
        )
    out["intent"] = _res(
        tool.run(
            root,
            operation="intent",
            request={"action": "check", "intent_id": "i-task"},
            **extra,
        )
    )
    out["recipe"] = _res(
        tool.run(
            root,
            operation="recipe",
            request={"action": "resolve", "recipe_id": "r-task"},
            **extra,
        )
    )
    return out


def _link_rows(db: Path, source: str, target: str, version: int) -> None:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "INSERT INTO memory_relations "
            "(source_id, source_version, target_id, target_version, kind, origin_ref, "
            "created_at) VALUES (?,?,?,?,?,?,?)",
            (source, version, target, version, "depends_on", None, time.time()),
        )
        conn.commit()


def test_t05_task_context_on_read_routes(tmp_path: Path) -> None:
    """R16/B9: a task-bound row is delivered as current only to the request carrying its
    `task_id`; `edit`/`archive`/`delete` never read `usable_as_current`."""
    from rush.memory.preference_store import PreferenceError
    from rush.memory.retrieval import MemoryAccess

    env = make_env(tmp_path, project_sources=R16_SOURCES)
    task_pref = rec_ok(env, "task.pref", "taskneedle", scope="task", task_id="A")
    project_pref = rec_ok(env, "proj.pref", "taskneedle project")
    store = TypedArtifactStore(env.root)
    seeded = _seed_task_rows(
        store, env.owner, (env.project_id or "", env.worktree_id or "", "A")
    )
    _link_rows(env.db, project_pref["artifact_id"], task_pref["artifact_id"], 2)

    for task in ("A", "B", None):
        reads = _read_ops(
            env.root,
            env.owner,
            task,
            session=None,
            row_id=task_pref["artifact_id"],
            version=2,
            neighbor_root=project_pref["artifact_id"],
            neighbor_version=2,
        )
        delivered = task == "A"
        for operation in ("ask", "recall", "list"):
            assert reads[operation].code == "OK", (task, operation)
            ids = {i["id"] for i in reads[operation].data["items"]}
            expected = {project_pref["artifact_id"]}
            if delivered:
                expected.add(task_pref["artifact_id"])
            assert ids == expected, (task, operation)
        assert reads["expand"].code == ("OK" if delivered else "E_NOT_VISIBLE"), task
        assert reads["related_root"].code == ("OK" if delivered else "E_NOT_VISIBLE")
        assert reads["related_neighbor"].code == "OK", task
        neighbors = [i["id"] for i in reads["related_neighbor"].data["items"]]
        assert neighbors == ([task_pref["artifact_id"]] if delivered else []), task
        for operation in ("prepare", "resume"):
            assert reads[operation].code == "OK", (task, operation)
            found = [e["id"] for e in reads[operation].data["untested_hypotheses"]]
            assert found == ([seeded["episode"]] if delivered else []), (
                task,
                operation,
            )
        assert reads["intent"].code == ("UNRESOLVED" if delivered else "E_INPUT"), task
        assert reads["recipe"].code == ("OK" if delivered else "E_INPUT"), task
        resolved = resolve(env, key="task.pref", task_id=task)
        assert resolved.code == "OK", (task, resolved.dump())
        selected = [
            e["selected"] for e in resolved.data["preferences"] if e["selected"]
        ]
        assert [s["value"] for s in selected] == (["taskneedle"] if delivered else [])

    # A `legacy_allowlist` access with task_id "A" never delivers a task-bound row.
    legacy_root = _registered(tmp_path / "legacy_task", default_data_root())
    legacy_store = TypedArtifactStore(legacy_root)
    legacy_owner = legacy_owner_scope(legacy_root)
    seed_row(
        legacy_store,
        "legacy-task-row",
        legacy_owner,
        key="task.pref",
        value="taskneedle",
        scope="task",
        project_id="p",
        worktree_id="w",
        task_id="A",
    )
    seed_row(
        legacy_store,
        "legacy-proj-row",
        legacy_owner,
        key="proj.pref",
        value="taskneedle project",
        scope="project",
        project_id="p",
        worktree_id="w",
    )
    _seed_task_rows(legacy_store, legacy_owner, ("p", "w", "A"))
    _link_rows(_db(legacy_root), "legacy-proj-row", "legacy-task-row", 1)
    legacy_sources = [
        PREFS,
        "intent:i-task",
        "recipe:r-task",
        f"repair_attempt:{REPAIR_SYMPTOM}",
    ]
    reads = _read_ops(
        legacy_root,
        legacy_owner,
        "A",
        session=legacy_sources,
        row_id="legacy-task-row",
        version=1,
        neighbor_root="legacy-proj-row",
        neighbor_version=1,
    )
    for operation in ("ask", "recall", "list"):
        assert {i["id"] for i in reads[operation].data["items"]} == {"legacy-proj-row"}
    assert reads["expand"].code == "E_NOT_VISIBLE"
    assert reads["related_root"].code == "E_NOT_VISIBLE"
    assert [i["id"] for i in reads["related_neighbor"].data["items"]] == []
    for operation in ("prepare", "resume"):
        assert reads[operation].data["untested_hypotheses"] == []
    # Legacy-mode resolve matches by the caller's triple (PR3), and only that triple.
    matched = call(
        legacy_root,
        "resolve",
        session=[PREFS],
        key="task.pref",
        project_id="p",
        worktree_id="w",
        task_id="A",
    )
    assert matched.code == "OK", matched.dump()
    assert [r["artifact_id"] for r in entry(matched, "task.pref")["advice"]] == [
        "legacy-task-row"
    ]
    for id_pair, task in (
        (("p", "w"), "B"),
        (("p", "other"), "A"),
        (("other", "w"), "A"),
    ):
        wrong = call(
            legacy_root,
            "resolve",
            session=[PREFS],
            key="task.pref",
            project_id=id_pair[0],
            worktree_id=id_pair[1],
            task_id=task,
        )
        assert wrong.code == "OK"
        assert "legacy-task-row" not in wrong.dump(), (id_pair, task)

    # A cursor minted under "A" is bound to "A".
    paged: dict[str, Any] = {"view": "compact", "limit": 1}
    tool = MemoryTool()
    owner = env.owner.as_dict()
    first = _res(
        tool.run(
            env.root,
            operation="recall",
            subject="preference",
            query="taskneedle",
            owner_scope=owner,
            request=paged,
            task_id="A",
        )
    )
    token = first.data["next_cursor"]
    assert first.code == "OK" and token
    for task in ("B", None):
        extra: dict[str, Any] = {} if task is None else {"task_id": task}
        restarted = _res(
            tool.run(
                env.root,
                operation="recall",
                subject="preference",
                query="taskneedle",
                owner_scope=owner,
                request={**paged, "cursor": token},
                **extra,
            )
        )
        assert restarted.code == "E_RESTART", (task, restarted.dump())
    same = _res(
        tool.run(
            env.root,
            operation="recall",
            subject="preference",
            query="taskneedle",
            owner_scope=owner,
            request={**paged, "cursor": token},
            task_id="A",
        )
    )
    assert same.code == "OK", same.dump()

    # `recheck()` of an "A" access is ok; policy-mode resolve(task_id="B") under an "A"
    # access is E_INPUT.
    access = MemoryAccess.resolve(
        env.root, operation="ask", owner_scope=env.owner, task_id="A"
    )
    assert access is not None and access.task_id == "A"
    assert access.recheck() == "ok"
    with pytest.raises(PreferenceError) as exc:
        PreferenceStore(env.root).resolve(
            "task.pref",
            access=access_for(env, "resolve", task_id="A"),
            project_id=env.project_id,
            worktree_id=env.worktree_id,
            task_id="B",
        )
    assert (exc.value.code, exc.value.reason) == ("E_INPUT", "task_id_mismatch")

    # `edit` never reads `usable_as_current`: task "B" or none edits the task-A row.
    for row_id, task in (
        (task_pref["artifact_id"], "B"),
        (project_pref["artifact_id"], None),
    ):
        row = _row_of(env.db, row_id)
        content = {**row["content"], "value": "taskneedle edited"}
        extra = {} if task is None else {"task_id": task}
        edited = _res(
            tool.run(
                env.root,
                operation="edit",
                request={
                    "scope": "preference",
                    "id": row_id,
                    "expected_version": row["artifact_version"],
                    "content": content,
                    "owner_scope": owner,
                    "apply": True,
                },
                permissions=ExecutionPermissions(cache_write=True),
                **extra,
            )
        )
        assert edited.code == "OK", (task, edited.dump())
        after = _row_of(env.db, row_id)
        assert after["artifact_version"] == row["artifact_version"] + 1
        assert after["content"]["value"] == "taskneedle edited"

    # `archive` likewise ignores the task context.
    current = _row_of(env.db, task_pref["artifact_id"])
    archived = _res(
        tool.run(
            env.root,
            operation="archive",
            request={
                "scope": "preference",
                "id": task_pref["artifact_id"],
                "expected_version": current["artifact_version"],
                "owner_scope": owner,
                "apply": True,
            },
            permissions=ExecutionPermissions(cache_write=True),
            task_id="B",
        )
    )
    assert archived.code == "OK", archived.dump()
    assert _row_of(env.db, task_pref["artifact_id"])["archived_at"] is not None


def _cli_leaf(
    root: Path, leaf: str, request: dict[str, Any], *flags: str
) -> dict[str, Any]:
    request_file = root / f".{leaf}-request.json"
    request_file.write_text(json.dumps(request), encoding="utf-8")
    old = os.getcwd()
    os.chdir(root)
    try:
        result = CliRunner().invoke(
            cli, ["memory", leaf, "--input", str(request_file), "--json", *flags]
        )
    finally:
        os.chdir(old)
        request_file.unlink()
    assert result.exception is None or isinstance(result.exception, SystemExit), (
        result.output
    )
    return dict(json.loads(result.output))


def test_t05_task_context_handoff_and_cli(tmp_path: Path) -> None:
    from rush.mcp_support.tool_registry import build_memory_bridge_handler

    env = make_env(tmp_path, project_ops=PROJECT_OPS, project_sources=(PREFS, MIG))
    task_row = rec_ok(env, "task.h", "handoff needle", scope="task", task_id="A")
    plain_row = rec_ok(env, "plain.h", "handoff needle plain")
    store = TypedArtifactStore(env.root)
    permissions = ExecutionPermissions(cache_write=True)
    owner = env.owner.as_dict()

    def prepare(task: str | None, via: str = "tool") -> tuple[str, str]:
        request = {
            "action": "prepare",
            "receiver_namespace": PREFS,
            "receiver_audience": "codex_cli",
            "goal": "sync",
            "selected_refs": [
                {"id": task_row["artifact_id"], "version": 2},
                {"id": plain_row["artifact_id"], "version": 2},
            ],
        }
        if via == "cli":
            flags = ["--allow-cache-write", *(["--task-id", task] if task else [])]
            payload = _cli_leaf(env.root, "handoff", request, *flags)
            data = payload["raw"]["data"]
            assert payload["raw"]["code"] == "OK", payload
        else:
            kwargs: dict[str, Any] = {} if task is None else {"task_id": task}
            out = _res(
                MemoryTool().run(
                    env.root,
                    operation="handoff",
                    request=request,
                    owner_scope=owner,
                    permissions=permissions,
                    **kwargs,
                )
            )
            assert out.code == "OK", out.dump()
            data = out.data
        return data["handoff_id"], data["capability"]

    def readback(artifact_id: str) -> dict[str, Any]:
        content = store.get_version_content(artifact_id, 2)
        assert content is not None
        return {
            "id": artifact_id,
            "version": 2,
            "digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }

    def receive(sid: str, cap: str, **extra: Any) -> Res:
        return _res(
            MemoryTool().run(
                env.root,
                operation="receive",
                request={"session_id": sid, "capability": cap, **extra},
            )
        )

    for via in ("tool", "cli"):
        sid, cap = prepare("A", via)
        session = store.get_handoff_session(sid)
        assert session is not None and session["sender_task_id"] == "A"
        delivered = receive(sid, cap)
        assert delivered.code == "OK", delivered.dump()
        assert {c["id"] for c in delivered.data["changes"]} == {
            task_row["artifact_id"],
            plain_row["artifact_id"],
        }
        acked = receive(sid, cap, ack=[readback(task_row["artifact_id"])])
        assert acked.code == "OK", acked.dump()
        bridge = build_memory_bridge_handler(
            root=env.root, session_id=sid, capability=cap
        )
        expand = bridge("expand", {"id": task_row["artifact_id"], "version": 2})
        assert expand["code"] == "OK", expand

    sid, cap = prepare(None)
    session = store.get_handoff_session(sid)
    assert session is not None and session["sender_task_id"] is None
    delivered = receive(sid, cap)
    assert delivered.code == "OK", delivered.dump()
    assert {c["id"] for c in delivered.data["changes"]} == {plain_row["artifact_id"]}
    refused = receive(sid, cap, ack=[readback(task_row["artifact_id"])])
    assert refused.code == "E_NOT_VISIBLE", refused.dump()
    bridge = build_memory_bridge_handler(root=env.root, session_id=sid, capability=cap)
    expand = bridge("expand", {"id": task_row["artifact_id"], "version": 2})
    assert expand["code"] == "E_NOT_VISIBLE", expand
    assert (
        bridge("expand", {"id": plain_row["artifact_id"], "version": 2})["code"] == "OK"
    )


def test_t05_reader_access_none_unchanged(tmp_path: Path) -> None:
    """R16: the five readers called with `access=None` return what they return with the
    argument omitted (the 72-T01 behavior); a supplied access decides the rows."""
    from rush.memory.experience import (
        prepare_memory,
        recall_repair_episodes,
    )
    from rush.memory.intent import check_intent, intent_evidence, record_intent
    from rush.memory.recipes import record_recipe, resolve_recipe
    from rush.memory.retrieval import MemoryAccess

    env = make_env(tmp_path, project_sources=R16_SOURCES)
    (env.root / "helper.py").write_text(
        "def helper():\n    return 1\n", encoding="utf-8"
    )
    assert (
        record_intent(project_root=env.root, intent_id="i1", behavior_id="b1")["code"]
        == "OK"
    )
    assert (
        record_recipe(
            project_root=env.root,
            recipe_id="r1",
            purpose="p",
            helper_ref={"path": "helper.py", "symbol": "helper"},
        )["code"]
        == "OK"
    )
    store = TypedArtifactStore(env.root)
    seeded = _seed_task_rows(
        store, env.owner, (env.project_id or "", env.worktree_id or "", "A")
    )
    plain_episode = {
        "schema_version": 1,
        "kind": "repair_episode",
        "symptom": REPAIR_SYMPTOM,
        "hypothesis": "plain",
        "patch_hash": None,
        "conditions": {},
        "receipt_ref": None,
        "behavior_ids": ["b1"],
        "affected_symbols": [],
        "outcome": "untested",
        "commit_message": None,
    }
    plain = store.write(
        MemoryArtifact(
            id="ep-plain",
            family="experience",
            subject="failure",
            trust_tier="DERIVED",
            content=plain_episode,
            source=f"repair_attempt:{REPAIR_SYMPTOM}",
            created_at=time.time(),
            owner_scope=env.owner,
        )
    )
    assert plain.id == "ep-plain"

    check_literal = {
        "code": "UNRESOLVED",
        "intent_id": "i1",
        "behavior_id": "b1",
        "message": "no exact-revision execution evidence found for this intent's check_refs.",
    }
    assert check_intent(project_root=env.root, intent_id="i1") == check_literal
    assert (
        check_intent(project_root=env.root, intent_id="i1", access=None)
        == check_literal
    )
    evidence_literal = [
        {
            "id": "i1",
            "version": 1,
            "intent_id": "i1",
            "behavior_id": "b1",
            "status": "candidate",
            "statement_ref": None,
            "check_refs": [],
        }
    ]
    assert (
        intent_evidence(project_root=env.root, behavior_ids=["b1"]) == evidence_literal
    )
    assert (
        intent_evidence(project_root=env.root, behavior_ids=["b1"], access=None)
        == evidence_literal
    )
    recipe_default = resolve_recipe(project_root=env.root, recipe_id="r1")
    assert recipe_default["code"] == "OK" and recipe_default["recipe_id"] == "r1"
    assert (
        resolve_recipe(project_root=env.root, recipe_id="r1", access=None)
        == recipe_default
    )
    recalled = recall_repair_episodes(
        project_root=env.root,
        symptom=REPAIR_SYMPTOM,
        conditions={},
        session_allowlist=None,
    )
    assert recalled["code"] == "OK"
    assert [e["id"] for e in recalled["untested_hypotheses"]] == ["ep-plain"]
    assert (
        recall_repair_episodes(
            project_root=env.root,
            symptom=REPAIR_SYMPTOM,
            conditions={},
            session_allowlist=None,
            access=None,
        )
        == recalled
    )
    prepared = prepare_memory(
        project_root=env.root,
        symptom=REPAIR_SYMPTOM,
        conditions={},
        behavior_ids=["b1"],
    )
    assert [e["id"] for e in prepared["untested_hypotheses"]] == ["ep-plain"]
    assert [e["id"] for e in prepared["intent_evidence"]] == ["i1"]
    assert (
        prepare_memory(
            project_root=env.root,
            symptom=REPAIR_SYMPTOM,
            conditions={},
            behavior_ids=["b1"],
            access=None,
        )
        == prepared
    )

    # Task-bound rows are invisible by default and decided under a supplied access.
    assert (
        check_intent(project_root=env.root, intent_id=seeded["intent"])["code"]
        == "E_INPUT"
    )
    assert (
        resolve_recipe(project_root=env.root, recipe_id=seeded["recipe"])["code"]
        == "E_INPUT"
    )
    task_a = MemoryAccess.resolve(
        env.root, operation="ask", owner_scope=env.owner, task_id="A"
    )
    task_b = MemoryAccess.resolve(
        env.root, operation="ask", owner_scope=env.owner, task_id="B"
    )
    assert task_a is not None and task_b is not None
    assert (
        check_intent(project_root=env.root, intent_id=seeded["intent"], access=task_a)[
            "code"
        ]
        == "UNRESOLVED"
    )
    assert (
        check_intent(project_root=env.root, intent_id=seeded["intent"], access=task_b)[
            "code"
        ]
        == "E_INPUT"
    )
    assert (
        resolve_recipe(
            project_root=env.root, recipe_id=seeded["recipe"], access=task_a
        )["code"]
        == "OK"
    )
    under_a = recall_repair_episodes(
        project_root=env.root,
        symptom=REPAIR_SYMPTOM,
        conditions={},
        session_allowlist=None,
        access=task_a,
    )
    assert sorted(e["id"] for e in under_a["untested_hypotheses"]) == [
        "ep-plain",
        "ep-task",
    ]
    under_b = prepare_memory(
        project_root=env.root,
        symptom=REPAIR_SYMPTOM,
        conditions={},
        behavior_ids=[],
        access=task_b,
    )
    assert [e["id"] for e in under_b["untested_hypotheses"]] == ["ep-plain"]
    narrow = MemoryAccess.legacy(env.root, ["unrelated-source"], owner_scope=env.owner)
    assert (
        recall_repair_episodes(
            project_root=env.root,
            symptom=REPAIR_SYMPTOM,
            conditions={},
            session_allowlist=None,
            access=narrow,
        )["untested_hypotheses"]
        == []
    )
    assert (
        intent_evidence(project_root=env.root, behavior_ids=["b1"], access=narrow) == []
    )


# --- the packet deliverable ------------------------------------------------------------


def test_t05_scope_precedence_consent_and_migration(tmp_path: Path) -> None:
    """The packet's concrete fixture and exact acceptance, end to end over
    `MemoryTool.run` (one assertion block per sentence)."""
    # Sentence 1: personal compact, ProjectA wide, ProjectB none, TaskA plain.
    project_a = make_env(tmp_path, "project_a")
    project_b = make_env(tmp_path, "project_b")
    personal = rec_ok(project_a, "format", "compact", scope="personal")
    rec_ok(project_a, "format", "wide")
    task = rec_ok(project_a, "format", "plain", scope="task", task_id="TaskA")
    assert personal["artifact_version"] == 2
    chosen = [
        entry(resolve(project_a, key="format", task_id="TaskA"), "format"),
        entry(resolve(project_a, key="format"), "format"),
        entry(resolve(project_b, key="format"), "format"),
    ]
    assert [c["selected"]["value"] for c in chosen] == ["plain", "wide", "compact"]
    assert [c["selected"]["scope"] for c in chosen] == ["task", "project", "personal"]
    ended = call(
        project_a,
        "end_task",
        task_id="TaskA",
        expected_versions={task["artifact_id"]: 2},
        apply=True,
    )
    assert ended.code == "OK", ended.dump()
    after = entry(resolve(project_a, key="format", task_id="TaskA"), "format")
    assert after["selected"]["value"] == "wide"

    # Sentence 2: inferred rows are advice only, at any scope.
    inferred = make_env(tmp_path, "inferred")
    rec_ok(inferred, "format", "compact", scope="personal")
    rec_ok(inferred, "format", "wide", authority="inferred")
    rec_ok(
        inferred, "format", "plain", authority="inferred", scope="task", task_id="TaskA"
    )
    seed_row(
        TypedArtifactStore(inferred.data_root / "user"),
        "inferred-personal",
        inferred.overlay_owner,
        key="format",
        value="wide",
        scope="personal",
        authority="inferred",
        source=PERSONAL,
    )
    item = entry(resolve(inferred, key="format", task_id="TaskA"), "format")
    assert item["selected"]["value"] == "compact"
    assert sorted(r["value"] for r in item["advice"]) == ["plain", "wide", "wide"]
    assert item["status"] == "applied" and item["unresolved"] == []

    # Sentence 3: a correction (reject, then reversal) is retained; held-out wording.
    alice = make_env(tmp_path, "alice")
    panel = rec_ok(alice, "ui.panel_layout", "verbose")
    rec_ok(alice, "int.width", "wide")
    rejected = call(
        alice,
        "correct",
        artifact_id=panel["artifact_id"],
        layer="project",
        kind="reject",
        reason="too noisy",
        expected_version=2,
        user_stated=True,
        apply=True,
    )
    assert rejected.code == "OK", rejected.dump()
    hit = resolve(alice, query="verbose panels")
    assert [e["key"] for e in hit.data["preferences"]] == ["ui.panel_layout"]
    assert (
        hit.data["preferences"][0]["contrary"][0]["artifact_id"] == panel["artifact_id"]
    )
    free = resolve(alice, query="wide integer")
    # Env "inferred" shares the data root (so the overlay) and seeded a personal
    # format="wide" row, which the term "wide" also matches (brief 3.4 item 2).
    assert [e["key"] for e in free.data["preferences"]] == ["format", "int.width"]
    assert entry(free, "int.width")["status"] == "applied"
    reversed_ = call(
        alice,
        "correct",
        artifact_id=panel["artifact_id"],
        layer="project",
        kind="correct",
        reason="actually fine",
        expected_version=3,
        value="verbose",
        user_stated=True,
        apply=True,
    )
    assert reversed_.code == "OK", reversed_.dump()
    store = TypedArtifactStore(alice.root)
    assert (
        json.loads(store.get_version_payload(panel["artifact_id"], 2)[0])[  # type: ignore[index]
            "applicability"
        ]
        == "active"
    )
    kept = json.loads(store.get_version_payload(panel["artifact_id"], 3)[0])  # type: ignore[index]
    assert kept["applicability"] == "rejected"
    assert kept["correction_refs"][-1]["reason"] == "too noisy"
    assert (
        entry(resolve(alice, key="ui.panel_layout"), "ui.panel_layout")["status"]
        == "applied"
    )

    # Sentence 4: disabled or revoked overlay is project-only; B's private row never
    # reaches A.
    revoked = make_env(tmp_path, "revoked")
    rec_ok(project_b, "secret.key", "b-private")
    revoke(revoked, "overlay")
    res = resolve(revoked, key="format")
    assert res.data["layers"]["personal"]["state"] == "denied"
    assert "compact" not in res.dump()
    assert "b-private" not in resolve(project_a, key="secret.key").dump()
    assert "b-private" not in resolve(project_a, query="private").dump()

    # Sentence 5: legacy replay inserts 1 then 0; a deleted key stays absent; a concurrent
    # edit is exact E_VERSION with the original intact.
    legacy = make_env(tmp_path, "legacy", legacy_json={"format": "compact"})
    source_bytes = legacy.prefs_json.read_bytes()
    _, first = _migrate_apply(legacy)
    assert first.data["inserted_count"] == 1
    legacy.prefs_json.write_bytes(source_bytes)
    _, replay = _migrate_apply(legacy)
    assert replay.data["inserted_count"] == 0
    assert PreferenceStore(legacy.root).delete("format") is True
    PreferenceStore(legacy.root).set("other", "x")
    preview, applied = _migrate_apply(legacy)
    assert preview.data["inserts"] == [{"key": "other", "value": "x"}]
    assert applied.data["inserted_count"] == 1
    assert PreferenceStore(legacy.root).get("format", "gone") == "gone"
    edit = make_env(tmp_path, "edit", legacy_json={"k": "v"})
    preview = call(edit, "migrate")
    original = edit.prefs_json.read_bytes()
    _external_edit(edit, lambda d: {**d, "k2": "v2"})
    changed = edit.prefs_json.read_bytes()
    assert changed != original
    stale = call(
        edit, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
    )
    assert stale.code == "E_VERSION" and stale.reason == "preview_changed"
    assert edit.prefs_json.read_bytes() == changed
    assert not edit.db.exists()


# --- G3: first-effect order ------------------------------------------------------------


class _Trace:
    """Records the first filesystem-effect constructors/locks a route reaches."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def mark(self, kind: str, detail: Any) -> None:
        self.events.append((kind, str(detail)))

    def clear(self) -> None:
        self.events.clear()

    def kinds(self) -> list[str]:
        return [kind for kind, _detail in self.events]

    def index(self, kind: str, prefix: str = "") -> int:
        for position, (event, detail) in enumerate(self.events):
            if event == kind and detail.startswith(prefix):
                return position
        raise AssertionError(f"no {kind} {prefix!r} in {self.events}")


def _install_trace(monkeypatch: pytest.MonkeyPatch) -> _Trace:
    import importlib

    from rush.dashboard import state
    from rush.memory.transactions import CASMapTransaction

    trace = _Trace()
    real_store_init = TypedArtifactStore.__init__
    real_cas_init = CASMapTransaction.__init__
    real_lock = state.cross_process_project_lock
    real_link, real_unlink = os.link, os.unlink

    def store_init(self: Any, project_root: Any = None) -> None:
        trace.mark("store", Path(project_root).resolve() if project_root else "cwd")
        real_store_init(self, project_root)

    def cas_init(self: Any, file_path: Any, root_path: Any = None) -> None:
        trace.mark("cas", file_path)
        real_cas_init(self, file_path, root_path)

    @contextlib.contextmanager
    def lock(project_id: str, *args: Any, **kwargs: Any) -> Any:
        trace.mark("lock", project_id)
        with real_lock(project_id, *args, **kwargs):
            yield

    def link(src: Any, dst: Any, *args: Any, **kwargs: Any) -> None:
        if ".migrated." in str(dst):
            trace.mark("link", dst)
        real_link(src, dst, *args, **kwargs)

    def unlink(path: Any, *args: Any, **kwargs: Any) -> None:
        if Path(path).name == "preferences.json":
            trace.mark("unlink", path)
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(TypedArtifactStore, "__init__", store_init)
    monkeypatch.setattr(CASMapTransaction, "__init__", cas_init)
    monkeypatch.setattr(state, "cross_process_project_lock", lock)
    for name in (
        "rush.memory.preference_store",
        "rush.memory.migration",
        "rush.memory.store",
        "rush.memory.authorization",
    ):
        module = importlib.import_module(name)
        if hasattr(module, "cross_process_project_lock"):
            monkeypatch.setattr(module, "cross_process_project_lock", lock)
    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(os, "unlink", unlink)
    return trace


def test_t05_first_effect_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G3: reads and previews construct nothing; a mutation takes the policy lock, then
    opens its store, only after validation, mode, layer, `cache_write`, `user_stated`
    and the D2 resolve all succeed."""
    from rush.memory.preference_store import PreferenceError, get_preference_readonly

    env = make_env(tmp_path, "g3", legacy_json={"legacy.k": "L"})
    project_row = rec_ok(env, "g3.k", "v")
    task_row = rec_ok(env, "g3.t", "t", scope="task", task_id="T1")
    personal_row = rec_ok(env, "g3.p", "p", scope="personal")
    bare = _registered(tmp_path / "g3_bare", env.data_root)
    trace = _install_trace(monkeypatch)
    overlay_root = str((env.data_root / "user").resolve())

    # Reads and previews: no store, CAS, lock, link or unlink.
    trace.clear()
    reads: list[Res] = [
        resolve(env, key="g3.k"),
        resolve(env, query="g3 v", via="mcp"),
        rec(env, "g3.new", "v", apply=False, cache_write=False),
        call(
            env,
            "correct",
            cache_write=False,
            artifact_id=project_row["artifact_id"],
            layer="project",
            kind="correct",
            reason="r",
            expected_version=2,
            value="v2",
        ),
        call(
            env,
            "end_task",
            cache_write=False,
            task_id="T1",
            expected_versions={task_row["artifact_id"]: 2},
        ),
        call(env, "migrate", cache_write=False),
        rec(env, "g3.pnew", "v", scope="personal", apply=False, cache_write=False),
    ]
    assert [r.code for r in reads] == ["OK"] * len(reads), [r.dump() for r in reads]
    PreferenceStore(env.root)
    assert get_preference_readonly(bare, "g3.k") is None
    PreferenceStore(bare)
    assert trace.events == []
    assert sorted(p.name for p in (bare / ".rush").iterdir()) == ["project.json"]

    # Denials before the first effect: nothing is constructed or locked.
    trace.clear()
    denials = [
        rec(env, "g3.new", "v", user_stated=False),
        rec(env, "g3.new", "v", cache_write=False),
        rec(env, 123, "v"),  # type: ignore[arg-type]
        rec(env, "g3.new", "v", scope="personal", source="not-granted"),
        call(
            env,
            "end_task",
            task_id="T1",
            expected_versions={},
            apply=True,
            cache_write=False,
        ),
    ]
    assert [r.code for r in denials] == [
        "E_PERMISSION",
        "E_PERMISSION",
        "E_INPUT",
        "E_SCOPE",
        "E_PERMISSION",
    ], [r.dump() for r in denials]
    assert trace.events == []
    no_write = make_env(tmp_path, "g3_nowrite", project_ops=("ask", "expand", "list"))
    trace.clear()
    assert rec(no_write, "k", "v").code == "E_PERMISSION"
    assert trace.events == []

    # Mutations: the policy lock first, then the store they write.
    trace.clear()
    assert rec(env, "g3.applied", "v").code == "OK"
    assert trace.kinds()[0] == "lock" and trace.events[0][1].startswith(
        "memory-policy:"
    )
    assert trace.index("lock", "memory-policy:") < trace.index("store", str(env.root))
    trace.clear()
    corrected = call(
        env,
        "correct",
        artifact_id=project_row["artifact_id"],
        layer="project",
        kind="correct",
        reason="r",
        expected_version=2,
        value="v2",
        user_stated=True,
        apply=True,
    )
    assert corrected.code == "OK", corrected.dump()
    assert trace.index("lock", "memory-policy:") < trace.index("store", str(env.root))
    trace.clear()
    ended = call(
        env,
        "end_task",
        task_id="T1",
        expected_versions={task_row["artifact_id"]: 2},
        apply=True,
    )
    assert ended.code == "OK", ended.dump()
    assert trace.index("lock", "memory-policy:") < trace.index("store", str(env.root))

    # Personal apply opens the overlay store, after the policy lock.
    trace.clear()
    assert rec(env, "g3.personal", "v", scope="personal").code == "OK"
    assert trace.index("lock", "memory-policy:") < trace.index("store", overlay_root)
    trace.clear()
    personal = call(
        env,
        "correct",
        artifact_id=personal_row["artifact_id"],
        layer="personal",
        kind="reject",
        reason="r",
        expected_version=2,
        owner_scope=env.overlay_owner.as_dict(),
        user_stated=True,
        apply=True,
    )
    assert personal.code == "OK", personal.dump()
    assert trace.index("lock", "memory-policy:") < trace.index("store", overlay_root)

    # migrate apply: policy lock, preferences lock, the project store, link, unlink.
    preview = call(env, "migrate")
    trace.clear()
    done = call(
        env, "migrate", apply=True, preview_digest=preview.data["preview_digest"]
    )
    assert done.code == "OK", done.dump()
    order = [
        trace.index("lock", "memory-policy:"),
        trace.index("lock", "preferences:"),
        trace.index("store", str(env.root)),
        trace.index("link"),
        trace.index("unlink"),
    ]
    assert order == sorted(order) and len(set(order)) == 5, trace.events

    # Compatibility set/delete: policy lock, then (after the grant) the preferences lock.
    trace.clear()
    PreferenceStore(env.root).set("g3.json", "j")
    assert trace.index("lock", "memory-policy:") < trace.index("lock", "preferences:")
    assert trace.index("lock", "preferences:") < trace.index("cas")
    denied = make_env(tmp_path, "g3_set_denied", project_ops=("ask", "expand", "list"))
    trace.clear()
    with pytest.raises(PreferenceError):
        PreferenceStore(denied.root).set("k", "v")
    assert not [e for e in trace.events if e[0] in {"cas", "store"}]
    assert not [e for e in trace.events if e[1].startswith("preferences:")]
    assert not denied.prefs_json.exists() and not denied.db.exists()

    # Legacy mode: the preferences lock, then the JSON transaction; no policy lock.
    legacy_root = _registered(tmp_path / "g3_legacy", default_data_root())
    trace.clear()
    PreferenceStore(legacy_root).set("k", "v")
    assert trace.index("lock", "preferences:") < trace.index("cas")
    assert not [e for e in trace.events if e[1].startswith("memory-policy:")]


# --- G4: trust-boundary inputs ----------------------------------------------------------


def _expect_input(
    env: Env,
    action: str,
    request: dict[str, Any],
    *,
    reason: str | None,
    transports: tuple[str, ...] = ("tool", "mcp"),
    **kwargs: Any,
) -> None:
    before = snapshot(env)
    for via in transports:
        result = call(env, action, via=via, **kwargs, **request)
        assert result.code == "E_INPUT", (action, via, request, result.dump())
        if via == "tool" and reason is not None:
            assert result.reason == reason, (action, request, result.dump())
        assert snapshot(env) == before, (action, via, request)


def _g4_env(tmp_path: Path) -> tuple[Env, dict[str, Any]]:
    env = make_env(tmp_path, "g4")
    row = rec_ok(env, "g4.k", "v")
    return env, row


_RECORD: dict[str, Any] = {
    "key": "k",
    "value": "v",
    "scope": "project",
    "authority": "explicit",
    "source": PREFS,
    "apply": True,
    "user_stated": True,
}


def _g4_wrong_types(tmp_path: Path) -> None:
    env, _row = _g4_env(tmp_path)
    _expect_input(env, "record", {**_RECORD, "key": 123}, reason="key_invalid")
    _expect_input(env, "record", {**_RECORD, "scope": "global"}, reason="scope_invalid")
    _expect_input(
        env,
        "end_task",
        {"task_id": "T", "expected_versions": [1], "apply": True},
        reason="expected_versions_invalid",
    )
    _expect_input(env, "record", {**_RECORD, "scope": ["x"]}, reason=None)
    _expect_input(env, "record", {**_RECORD, "authority": {"a": 1}}, reason=None)
    _expect_input(
        env, "record", {**_RECORD, "authority": "imported_unverified"}, reason=None
    )


def _g4_bool_as_int(tmp_path: Path) -> None:
    env, row = _g4_env(tmp_path)
    correct = {
        "artifact_id": row["artifact_id"],
        "layer": "project",
        "kind": "correct",
        "reason": "r",
        "expected_version": True,
        "value": "v2",
        "user_stated": True,
        "apply": True,
    }
    _expect_input(env, "correct", correct, reason="expected_version_invalid")
    _expect_input(env, "record", {**_RECORD, "apply": 1}, reason=None)
    _expect_input(env, "record", {**_RECORD, "user_stated": 1}, reason=None)


def _g4_huge_int(tmp_path: Path) -> None:
    env, row = _g4_env(tmp_path)
    correct = {
        "artifact_id": row["artifact_id"],
        "layer": "project",
        "kind": "correct",
        "reason": "r",
        "expected_version": 10**400,
        "value": "v2",
        "user_stated": True,
        "apply": True,
    }
    _expect_input(env, "correct", correct, reason="expected_version_invalid")
    _expect_input(
        env,
        "end_task",
        {
            "task_id": "T",
            "expected_versions": {row["artifact_id"]: 10**400},
            "apply": True,
        },
        reason="expected_version_invalid",
    )


def _g4_nan_inf(tmp_path: Path) -> None:
    env, _row = _g4_env(tmp_path)
    for bad in (float("nan"), float("inf"), float("-inf")):
        _expect_input(
            env, "record", {**_RECORD, "expires_at": bad}, reason="expires_at_invalid"
        )
    _expect_input(
        env,
        "record",
        {**_RECORD, "expires_at": time.time() - 10},
        reason="expires_at_invalid",
    )
    _expect_input(
        env, "record", {**_RECORD, "value": float("nan")}, reason="value_invalid"
    )


def _g4_nul(tmp_path: Path) -> None:
    env, row = _g4_env(tmp_path)
    _expect_input(env, "record", {**_RECORD, "key": "a\x00b"}, reason="key_invalid")
    _expect_input(env, "record", {**_RECORD, "value": "a\x00b"}, reason="value_invalid")
    _expect_input(
        env,
        "record",
        {**_RECORD, "value": {"deep": ["a\x00b"]}},
        reason="value_invalid",
    )
    correct = {
        "artifact_id": row["artifact_id"],
        "layer": "project",
        "kind": "reject",
        "reason": "a\x00b",
        "expected_version": 2,
        "user_stated": True,
        "apply": True,
    }
    _expect_input(env, "correct", correct, reason="reason_invalid")
    before = snapshot(env)
    for via in ("tool", "mcp"):
        bad_task = call(env, "resolve", via=via, key="g4.k", task_id="a\x00b")
        assert bad_task.code == "E_INPUT", (via, bad_task.dump())
        assert snapshot(env) == before


def _g4_lone_surrogate(tmp_path: Path) -> None:
    env, _row = _g4_env(tmp_path)
    _expect_input(env, "record", {**_RECORD, "key": "\ud800"}, reason="key_invalid")
    _expect_input(env, "record", {**_RECORD, "value": "\udc00"}, reason="value_invalid")


def _g4_cc_cf(tmp_path: Path) -> None:
    env, _row = _g4_env(tmp_path)
    _expect_input(env, "record", {**_RECORD, "key": "a\u202eb"}, reason="key_invalid")
    _expect_input(env, "record", {**_RECORD, "key": "a\x07b"}, reason="key_invalid")
    _expect_input(
        env, "record", {**_RECORD, "value": "x\u202ey"}, reason="value_invalid"
    )
    _expect_input(env, "record", {**_RECORD, "attribution": "a\x07b"}, reason=None)


def _g4_task_id_values(tmp_path: Path) -> None:
    env, _row = _g4_env(tmp_path)
    before = snapshot(env)
    for bad in (123, "", "a\x00b", "a\u202eb", "\ud800", "a\x07b"):
        result = _res(
            MemoryTool().run(
                env.root,
                operation="preference",
                request={"action": "resolve", "key": "g4.k"},
                task_id=bad,  # type: ignore[arg-type]
            )
        )
        assert result.code == "E_INPUT", (bad, result.dump())
        assert result.data["field"] == "task_id" and result.reason == "task_id_invalid"
        assert result.data["message"] == (
            "task_id must be a non-empty string without control characters."
        )
        assert snapshot(env) == before
    # `task_id` is a top-level argument except for the `end_task` target.
    nested = _res(
        MemoryTool().run(
            env.root,
            operation="preference",
            request={"action": "resolve", "key": "g4.k", "task_id": "x"},
        )
    )
    assert nested.code == "E_INPUT" and nested.reason == "task_id_top_level"
    assert snapshot(env) == before


def _g4_symlink_loop(tmp_path: Path) -> None:
    from rush.memory.preference_store import PreferenceError

    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    with pytest.raises(PreferenceError) as exc:
        PreferenceStore(loop)
    assert (exc.value.code, exc.value.reason) == ("E_INPUT", "project_root_invalid")
    reference = MemoryTool().run(
        loop,
        operation="ask",
        subject="preference",
        query="q",
        session_allowlist=[PREFS],
    )
    expected = {
        "schema_version": 1,
        "operation": "ask",
        "code": "E_INPUT",
        "data": {"field": "path", "message": "invalid project path"},
    }
    assert reference["raw"] == expected
    for via in ("tool", "mcp"):
        result = call(loop, "resolve", via=via, key="k", session=[PREFS])
        assert result.code == "E_INPUT", (via, result.dump())
        assert result.data == expected["data"], via


def _g4_bad_paths(tmp_path: Path) -> None:
    from rush.memory.preference_store import PreferenceError

    for bad in (123, "a\x00b", object()):
        with pytest.raises(PreferenceError) as exc:
            PreferenceStore(bad)  # type: ignore[arg-type]
        assert (exc.value.code, exc.value.reason) == ("E_INPUT", "project_root_invalid")
    for bad_path in (123, "a\x00b"):
        result = _res(
            MemoryTool().run(
                bad_path,  # type: ignore[arg-type]
                operation="preference",
                request={"action": "resolve", "key": "k"},
            )
        )
        assert result.code == "E_INPUT"
        assert result.data == {"field": "path", "message": "invalid project path"}


def _g4_missing_path_policy(tmp_path: Path) -> None:
    import shutil

    env = make_env(tmp_path, "g4_gone")
    gone = env.root
    shutil.rmtree(gone)
    for via in ("tool", "mcp"):
        for action, request in (
            ("resolve", {"key": "k"}),
            ("record", {**_RECORD}),
        ):
            result = call(gone, action, via=via, **request)
            assert result.code == "E_PERMISSION", (via, action, result.dump())
            assert result.reason == "project_missing", (via, action)
    assert not gone.exists()


def _g4_missing_path_legacy(tmp_path: Path) -> None:
    missing = tmp_path / "never_registered"
    for via in ("tool", "mcp"):
        read = call(
            missing,
            "resolve",
            via=via,
            session=[PREFS],
            key="k",
            project_id="p",
            worktree_id="w",
        )
        assert read.code == "OK", (via, read.dump())
        write = call(missing, "record", via=via, session=[PREFS], **_RECORD)
        assert write.code == "E_PERMISSION", (via, write.dump())
        assert write.reason == "policy_grant_required"
    assert not missing.exists()


def _g4_data_root(tmp_path: Path) -> None:
    from rush.memory.preference_store import PreferenceError

    for bad in (42, 4.5, ["x"], object()):
        with pytest.raises(PreferenceError) as exc:
            PreferenceStore(tmp_path, data_root=bad)  # type: ignore[arg-type]
        assert (exc.value.code, exc.value.reason) == ("E_INPUT", "data_root_invalid")


def _g4_unhashable_owner(tmp_path: Path) -> None:
    env, _row = _g4_env(tmp_path)
    before = snapshot(env)
    for owner in (
        {"kind": ["x"], "id": "y"},
        {"kind": {"k": 1}, "id": "y"},
        {"kind": "user", "id": ["y"]},
        {"kind": True, "id": "y"},
    ):
        for via in ("tool", "mcp"):
            result = call(env, "resolve", via=via, key="g4.k", owner_scope=owner)
            assert result.code == "E_INPUT", (owner, via, result.dump())
        assert snapshot(env) == before


def _g4_bom_and_non_utf8(tmp_path: Path) -> None:
    from rush.memory.transactions import StoreCorruptionError

    for name, payload in (
        (
            "bom",
            b"\xef\xbb\xbf" + b'{"schema_version": "1.0.0", "version": 1, "data": {}}',
        ),
        ("invalid", b"\xff\xfe\x00"),
    ):
        env = make_env(tmp_path, f"g4_{name}")
        env.prefs_json.parent.mkdir(parents=True, exist_ok=True)
        env.prefs_json.write_bytes(payload)
        before = snapshot(env)
        for via in ("tool", "mcp"):
            preview = call(env, "migrate", via=via)
            assert preview.code == "E_MIGRATION", (name, via, preview.dump())
            assert preview.reason == "source_corrupt"
            applied = call(env, "migrate", via=via, apply=True, preview_digest="0" * 64)
            assert applied.code == "E_MIGRATION" and applied.reason == "source_corrupt"
            assert resolve(env, key="k", via=via).code == "OK"
        assert snapshot(env) == before
        legacy_root = _registered(tmp_path / f"g4_legacy_{name}", default_data_root())
        (legacy_root / ".rush").mkdir(exist_ok=True)
        (legacy_root / ".rush" / "preferences.json").write_bytes(payload)
        with pytest.raises(StoreCorruptionError):
            PreferenceStore(legacy_root).set("k", "v")


def _expected_for_root(root: Path) -> tuple[str, str | None]:
    """The code and reason a `preference resolve` at `root` must answer, from the same
    policy decision and resolver the route uses."""
    from rush.memory import authorization as auth
    from rush.memory.retrieval import memory_policy_decision

    mode, reason = memory_policy_decision(root)
    if mode == "unavailable":
        return "E_PERMISSION", reason
    if mode == "legacy":
        return "OK", None
    scope = auth.resolve_memory_scope(project_root=root, operation="list")
    return "E_PERMISSION", str(scope["reason"])


def _g4_moved_root(tmp_path: Path) -> None:
    env = make_env(tmp_path, "g4_moved_from")
    rec_ok(env, "moved.k", "moved-value")
    moved = tmp_path / "g4_moved_to"
    env.root.rename(moved)
    code, reason = _expected_for_root(moved)
    assert code == "E_PERMISSION" and reason is not None
    for via in ("tool", "mcp"):
        result = call(moved, "resolve", via=via, key="moved.k")
        assert result.code == code and result.reason == reason, (via, result.dump())
        assert "moved-value" not in result.dump()


def _g4_case_variant_root(tmp_path: Path) -> None:
    env = make_env(tmp_path, "G4_Case_Root")
    rec_ok(env, "case.k", "case-value")
    variant = Path(str(env.root).replace("G4_Case_Root", "g4_case_root"))
    code, reason = _expected_for_root(variant)
    for via in ("tool", "mcp"):
        result = call(
            variant,
            "resolve",
            via=via,
            key="case.k",
            session=[PREFS],
            project_id="p",
            worktree_id="w",
        )
        assert result.code == code, (via, result.dump())
        if reason is not None:
            assert result.reason == reason, via
        assert "case-value" not in result.dump(), via


_G4_ROWS: dict[str, Any] = {
    "wrong_type": _g4_wrong_types,
    "bool_as_int": _g4_bool_as_int,
    "huge_int": _g4_huge_int,
    "nan_inf": _g4_nan_inf,
    "nul": _g4_nul,
    "lone_surrogate": _g4_lone_surrogate,
    "cc_cf": _g4_cc_cf,
    "task_id_values": _g4_task_id_values,
    "bad_paths": _g4_bad_paths,
    "missing_path_policy": _g4_missing_path_policy,
    "missing_path_legacy": _g4_missing_path_legacy,
    "data_root_non_path": _g4_data_root,
    "unhashable_owner_kind": _g4_unhashable_owner,
    "bom_and_non_utf8": _g4_bom_and_non_utf8,
    "moved_root": _g4_moved_root,
    "case_variant_root": _g4_case_variant_root,
}


@pytest.mark.parametrize(
    "row",
    [pytest.param(name, id=name) for name in _G4_ROWS]
    + [pytest.param("symlink_loop", id="symlink_loop", marks=pytest.mark.posix_only)],
)
def test_t05_trust_boundary_inputs(row: str, tmp_path: Path) -> None:
    """G4: every trust-boundary row is a named `E_INPUT`/`E_PERMISSION`/`E_MIGRATION`
    with zero effects on MCP, `MemoryTool.run` and the in-process API."""
    runners = {**_G4_ROWS, "symlink_loop": _g4_symlink_loop}
    runners[row](tmp_path)


# --- AST guard ---------------------------------------------------------------------------


def test_t05_every_tool_access_carries_task_id() -> None:
    """3.11: every access `MemoryTool` builds carries `task_id`, and `run`/`__call__`
    accept it as an optional keyword."""
    import inspect

    source = (REPO_SRC / "rush" / "tools" / "memory.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    tool_class = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MemoryTool"
    )

    def accessor(call_node: ast.Call) -> str | None:
        func = call_node.func
        if isinstance(func, ast.Attribute):
            if func.attr == "_read_access":
                return "_read_access"
            if (
                isinstance(func.value, ast.Name)
                and func.value.id == "MemoryAccess"
                and func.attr in {"resolve", "resolve_with_reason", "legacy"}
            ):
                return f"MemoryAccess.{func.attr}"
        if isinstance(func, ast.Name) and func.id in {"read_access", "route_access"}:
            return func.id
        return None

    found = 0
    offenders: list[str] = []
    for node in ast.walk(tool_class):
        if isinstance(node, ast.Call) and (name := accessor(node)) is not None:
            found += 1
            if "task_id" not in {kw.arg for kw in node.keywords}:
                offenders.append(f"line {node.lineno}: {name}")
    assert found >= 15, found  # the scan is not vacuous
    assert offenders == []

    for method in (MemoryTool.run, MemoryTool.__call__):
        parameter = inspect.signature(method).parameters["task_id"]
        assert parameter.default is None
    assert (
        inspect.signature(MemoryTool._read_access).parameters["task_id"].default is None
    )


# --- G2: route x mode matrix ---------------------------------------------------------------

FMT = "fmt"
ACTIONS = ("resolve", "record", "correct", "end_task", "migrate")
MUTATING = ("record", "correct", "end_task", "migrate")
BRIDGE_DENIAL = {
    "schema_version": 1,
    "operation": "preference",
    "code": "E_PERMISSION",
    "data": {
        "message": "This restricted handoff receiver only permits "
        "('receive', 'expand', 'related', 'resume')."
    },
}


@dataclasses.dataclass
class MEnv:
    env: Env
    project: str = ""
    task: str = ""
    personal: str = ""
    digest: str = "0" * 64


def _menv(
    tmp_path: Path,
    *,
    seed: bool = True,
    project_ops: tuple[str, ...] | None = None,
    overlay_ops: tuple[str, ...] | None = None,
    overlay: bool = True,
) -> MEnv:
    """A project with the project and overlay grants, a legacy `preferences.json`, and
    (when `seed`) an explicit project row `fmt=wide`, an explicit task row `T1` and an
    explicit personal row; narrower grants are applied after seeding."""
    env = make_env(tmp_path, "matrix", legacy_json={"legacy.k": "L"}, overlay=overlay)
    m = MEnv(env)
    if seed:
        m.project = rec_ok(env, FMT, "wide")["artifact_id"]
        m.task = rec_ok(env, FMT, "plain", scope="task", task_id="T1")["artifact_id"]
        if overlay:
            m.personal = rec_ok(env, FMT, "compact", scope="personal")["artifact_id"]
    m.digest = call(env, "migrate").data.get("preview_digest", m.digest)
    if project_ops is not None:
        regrant(env, "project", ops=project_ops)
    if overlay_ops is not None:
        regrant(env, "overlay", ops=overlay_ops)
    return m


def _request(
    m: MEnv, action: str, apply: bool, *, personal: bool = False
) -> dict[str, Any]:
    ov = m.env.overlay_owner.as_dict()
    if action == "resolve":
        return {"key": FMT}
    if action == "record":
        request: dict[str, Any] = {
            "key": "new.k",
            "value": "nv",
            "scope": "personal" if personal else "project",
            "authority": "explicit",
            "source": PERSONAL if personal else PREFS,
            "apply": apply,
            "user_stated": True,
        }
    elif action == "correct":
        request = {
            "artifact_id": m.personal if personal else m.project,
            "layer": "personal" if personal else "project",
            "kind": "correct",
            "reason": "r",
            "expected_version": 2,
            "value": "changed",
            "apply": apply,
            "user_stated": True,
        }
    elif action == "end_task":
        request = {"task_id": "T1", "expected_versions": {m.task: 2}, "apply": apply}
    else:
        request = {"apply": apply}
        if apply:
            request["preview_digest"] = m.digest
    if personal:
        request["owner_scope"] = ov
    return request


def _send(
    m: MEnv,
    via: str,
    action: str,
    apply: bool,
    *,
    personal: bool = False,
    cache_write: bool = True,
    extra: dict[str, Any] | None = None,
) -> Res:
    request = _request(m, action, apply, personal=personal)
    request.update(extra or {})
    return call(m.env, action, via=via, cache_write=cache_write, **request)


def _denied(res: Res, code: str, reason: str) -> None:
    assert (res.code, res.reason) == (code, reason), res.dump()


def _assert_applied(m: MEnv, action: str, res: Res, *, personal: bool = False) -> None:
    assert res.code == "OK", res.dump()
    if action == "resolve":
        return
    assert res.data["applied"] is True, res.dump()
    db = m.env.overlay_db if personal else m.env.db
    if action == "record":
        assert any(r["content"].get("key") == "new.k" for r in _pref_rows(db))
    elif action == "correct":
        assert res.data["artifact_version"] == 4
        assert (
            _row_of(db, m.personal if personal else m.project)["artifact_version"] == 4
        )
    elif action == "end_task":
        assert [e["artifact_id"] for e in res.data["ended"]] == [m.task]
        assert _row_of(m.env.db, m.task)["expired_at"] is not None
    else:
        assert res.data["publication"] == "published"
        assert not m.env.prefs_json.exists()


def _resolve_baseline(m: MEnv, res: Res) -> None:
    assert res.code == "OK", res.dump()
    item = entry(res, FMT)
    assert item["status"] == "applied" and item["selected"]["value"] == "wide"
    assert res.data["layers"]["project"]["state"] == "read"
    assert res.data["layers"]["personal"]["state"] == "read"
    assert (m.personal, 2, "shadowed_by_project") in why_view(item)


# Each scenario takes (tmp_path, via, action) and asserts the whole cell.


def _sc_preview(tmp_path: Path, via: str, action: str) -> None:
    m = _menv(tmp_path)
    before = snapshot(m.env)
    res = _send(m, via, action, False, cache_write=action == "resolve")
    if action == "resolve":
        _resolve_baseline(m, res)
    else:
        assert res.code == "OK", res.dump()
        assert res.data["applied"] is False
    assert snapshot(m.env) == before


def _sc_apply(tmp_path: Path, via: str, action: str) -> None:
    m = _menv(tmp_path)
    res = _send(m, via, action, True)
    _assert_applied(m, action, res)


def _sc_cache_write_off(tmp_path: Path, via: str, action: str) -> None:
    m = _menv(tmp_path)
    before = snapshot(m.env)
    res = _send(m, via, action, True, cache_write=False)
    if action == "resolve":
        _resolve_baseline(m, res)
    else:
        _denied(res, "E_PERMISSION", "cache_write_required")
    assert snapshot(m.env) == before


def _sc_grant_missing_one(tmp_path: Path, via: str, action: str) -> None:
    apply = action != "resolve"
    needed = "write" if apply else "list"
    ops = tuple(o for o in PROJECT_OPS if o != needed)
    m = _menv(tmp_path, project_ops=ops, overlay=False)
    before = snapshot(m.env)
    res = _send(m, via, action, apply)
    _denied(res, "E_PERMISSION", "operation_not_granted")
    assert snapshot(m.env) == before
    if apply:
        # The preview needs only `list`, which this grant still has.
        preview = _send(m, via, action, False, cache_write=False)
        assert preview.code == "OK", preview.dump()
    else:
        # With the overlay grant intact the personal rule still resolves; the project
        # layer reports the actual denial (addendum: layers resolve independently).
        both = _menv(tmp_path / "both", project_ops=ops)
        res = _send(both, via, action, False)
        assert res.code == "OK", res.dump()
        layers = res.data["layers"]
        assert layers["project"]["state"] == "denied"
        assert layers["project"]["reason"] == "operation_not_granted"
        assert layers["personal"]["state"] == "read"
        assert entry(res, FMT)["selected"]["value"] == "compact"


_DENIAL_REQUESTS: dict[str, dict[str, Any]] = {
    "record": {
        "key": "k",
        "value": "v",
        "scope": "project",
        "authority": "explicit",
        "source": PREFS,
        "user_stated": True,
    },
    "correct": {
        "artifact_id": "x",
        "layer": "project",
        "kind": "reject",
        "reason": "r",
        "expected_version": 1,
        "user_stated": True,
    },
    "end_task": {"task_id": "T1", "expected_versions": {}},
    "migrate": {"preview_digest": "0" * 64},
    "resolve": {"key": FMT},
}


def _sc_legacy(tmp_path: Path, via: str, action: str, apply: bool) -> None:
    root = _registered(tmp_path / "legacy", default_data_root())
    PreferenceStore(root).set("legacy.k", "L")
    before = _digest_tree(root / ".rush")
    if action == "resolve":
        res = call(
            root,
            action,
            via=via,
            session=[PREFS, MIG],
            key=FMT,
            project_id="p",
            worktree_id="w",
        )
        assert res.code == "OK", res.dump()
        assert all(e["selected"] is None for e in res.data["preferences"])
        assert res.data["layers"]["personal"]["reason"] == "policy_missing"
    else:
        res = call(
            root,
            action,
            via=via,
            session=[PREFS, MIG],
            apply=apply,
            **_DENIAL_REQUESTS[action],
        )
        _denied(res, "E_PERMISSION", "policy_grant_required")
    assert _digest_tree(root / ".rush") == before


def _sc_overlay(tmp_path: Path, via: str, action: str, apply: bool) -> None:
    m = _menv(tmp_path)
    before = snapshot(m.env)
    if action == "resolve":
        res = _send(m, via, action, False)
        _resolve_baseline(m, res)
        assert snapshot(m.env) == before
        return
    if action in {"end_task", "migrate"}:
        res = _send(
            m, via, action, apply, extra={"owner_scope": m.env.overlay_owner.as_dict()}
        )
        _denied(res, "E_OWNER", "layer_owner_mismatch")
        assert snapshot(m.env) == before
        return
    res = _send(m, via, action, apply, personal=True)
    if apply:
        _assert_applied(m, action, res, personal=True)
    else:
        assert res.code == "OK" and res.data["applied"] is False, res.dump()
        assert snapshot(m.env) == before


def _sc_overlay_owner_argument(tmp_path: Path, via: str, action: str) -> None:
    m = _menv(tmp_path)
    before = snapshot(m.env)
    res = _send(
        m, via, "resolve", False, extra={"owner_scope": m.env.overlay_owner.as_dict()}
    )
    _denied(res, "E_OWNER", "layer_owner_mismatch")
    assert snapshot(m.env) == before


def _sc_overlay_missing_op(tmp_path: Path, via: str, action: str) -> None:
    m = _menv(tmp_path, overlay_ops=("list", "expand", "write"))
    before = snapshot(m.env)
    if action == "resolve":
        res = _send(m, via, action, False)
        assert res.code == "OK", res.dump()
        personal = res.data["layers"]["personal"]
        assert personal["state"] == "denied"
        assert personal["reason"] == "operation_not_granted"
        assert "compact" not in res.dump()
    else:
        res = _send(m, via, action, False, personal=True, cache_write=False)
        _denied(res, "E_PERMISSION", "operation_not_granted")
    assert snapshot(m.env) == before


def _sc_overlay_revoked(tmp_path: Path, via: str, action: str) -> None:
    m = _menv(tmp_path)
    revoke(m.env, "overlay")
    before = snapshot(m.env)
    if action == "resolve":
        res = _send(m, via, action, False)
        assert res.code == "OK", res.dump()
        personal = res.data["layers"]["personal"]
        assert personal["state"] == "denied" and personal["reason"] == "revoked"
        assert personal["next_action"]["text"].startswith(
            "Personal overlay not applied"
        )
        assert "compact" not in res.dump()
    else:
        res = _send(m, via, action, True, personal=True)
        _denied(res, "E_PERMISSION", "revoked")
    assert snapshot(m.env) == before


def _sc_policy_state(tmp_path: Path, via: str, action: str, state: str) -> None:
    from rush.memory import authorization as auth

    m = _menv(tmp_path)
    policy = auth.policy_path(data_root=m.env.data_root)
    if state == "missing_with_marker":
        policy.unlink()
        expected = "policy_missing"
    else:
        policy.write_bytes(b"{not json")
        expected = "policy_invalid"
    before = snapshot(m.env)
    for apply in (False,) if action == "resolve" else (False, True):
        res = _send(m, via, action, apply)
        _denied(res, "E_PERMISSION", expected)
    assert snapshot(m.env) == before


def _sc_extra_key(tmp_path: Path, via: str, action: str, key: str, value: Any) -> None:
    m = _menv(tmp_path, seed=False)
    before = snapshot(m.env)
    res = _send(m, via, action, False, extra={key: value})
    assert res.code == "E_INPUT", res.dump()
    assert key in res.dump()
    assert snapshot(m.env) == before


def _sc_store_absent(tmp_path: Path, via: str, action: str, apply: bool) -> None:
    m = _menv(tmp_path, seed=False)
    assert not m.env.db.exists()
    before = snapshot(m.env)
    if action == "resolve":
        res = _send(m, via, action, False)
        assert res.code == "OK", res.dump()
        assert snapshot(m.env) == before
        return
    if action == "correct":
        res = call(
            m.env,
            "correct",
            via=via,
            artifact_id="not-there",
            layer="project",
            kind="reject",
            reason="r",
            expected_version=1,
            user_stated=True,
            apply=apply,
        )
        assert res.code == "E_NOT_VISIBLE", res.dump()
        assert not m.env.db.exists()
        return
    if action == "end_task":
        res = call(
            m.env, "end_task", via=via, task_id="T1", expected_versions={}, apply=apply
        )
        assert res.code == "OK", res.dump()
        assert res.data["ended"] == [] and res.data["applied"] is apply
        assert not m.env.db.exists()
        return
    res = _send(m, via, action, apply)
    assert res.code == "OK", res.dump()
    if action == "record" and not apply:
        assert not m.env.db.exists()
    if action == "record" and apply:
        assert m.env.db.exists()
        assert [r["content"]["key"] for r in _pref_rows(m.env.db)] == ["new.k"]
    if action == "migrate" and not apply:
        assert res.data["inserts"] == [{"key": "legacy.k", "value": "L"}]
        assert not m.env.db.exists()
    if action == "migrate" and apply:
        assert [r["origin_id"] for r in _pref_rows(m.env.db)] == ["legacy.k"]


def _drop_payload_columns(db: Path) -> None:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        for table in ("memory_artifacts", "memory_artifact_versions"):
            for column in ("payload_hash", "payload_hash_origin"):
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()


def _sc_store_old_schema(tmp_path: Path, via: str, action: str, apply: bool) -> None:
    m = _menv(tmp_path)
    _drop_payload_columns(m.env.db)
    before = _sha(m.env.db)
    res = _send(m, via, action, apply)
    if not apply:
        _denied(res, "E_MIGRATION", "migration_required")
        assert _sha(m.env.db) == before
        return
    assert res.code == "OK", res.dump()
    assert "payload_hash" in {
        r["name"] for r in _sql(m.env.db, "PRAGMA table_info(memory_artifacts)")
    }


def _sc_row_state(tmp_path: Path, via: str, action: str, state: str) -> None:
    m = _menv(tmp_path)
    db, target = m.env.db, m.project
    if state == "archived":
        TypedArtifactStore(m.env.root).archive(
            target,
            expected_version=2,
            scope="preference",
            owner_scope=m.env.owner,
            apply=True,
        )
    elif state == "expired":
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET expires_at = ? WHERE id = ?",
                (time.time() - 100, target),
            )
            conn.commit()
    elif state == "tampered":
        with contextlib.closing(sqlite3.connect(db)) as conn:
            conn.execute(
                "UPDATE memory_artifacts SET content = ? WHERE id = ?",
                (json.dumps({"key": FMT, "value": "forged"}), target),
            )
            conn.commit()
    elif state == "rejected":
        out = call(
            m.env,
            "correct",
            via=via,
            artifact_id=target,
            layer="project",
            kind="reject",
            reason="r",
            expected_version=2,
            user_stated=True,
            apply=True,
        )
        assert out.code == "OK", out.dump()
    else:
        assert state == "pending"
        seed_row(
            TypedArtifactStore(m.env.root),
            "pending-row",
            m.env.owner,
            key=FMT,
            value="pending-value",
            scope="project",
            authority="explicit",
            applicability="pending",
            project_id=m.env.project_id,
            worktree_id=m.env.worktree_id,
        )
    if action == "resolve":
        res = _send(m, via, action, False)
        assert res.code == "OK", res.dump()
        item = entry(res, FMT)
        refs_for_target = [
            r["artifact_id"]
            for key in ("applied_refs", "unresolved", "advice", "pending", "contrary")
            for r in item[key]
        ]
        if state == "rejected":
            assert [r["artifact_id"] for r in item["contrary"]] == [target]
            assert item["selected"]["value"] == "compact"
        elif state == "pending":
            assert [r["artifact_id"] for r in item["pending"]] == ["pending-row"]
            assert item["selected"]["value"] == "wide"
        else:
            assert target not in refs_for_target
            assert "forged" not in res.dump()
            assert item["selected"]["value"] == "compact"
        return
    if state in {"rejected", "pending"}:
        row_id = target if state == "rejected" else "pending-row"
        version = 3 if state == "rejected" else 1
        res = _send(
            m,
            via,
            "correct",
            True,
            extra={
                "artifact_id": row_id,
                "expected_version": version,
                "kind": "correct",
            },
        )
        assert res.code == "OK", res.dump()
        return
    res = _send(m, via, "correct", True)
    assert res.code == "E_NOT_VISIBLE", res.dump()


def _sc_cache_write_ask_only(tmp_path: Path, via: str, action: str) -> None:
    m = _menv(tmp_path, project_ops=("ask",), overlay=False)
    before = snapshot(m.env)
    res = _send(m, via, action, True)
    _denied(res, "E_PERMISSION", "operation_not_granted")
    assert snapshot(m.env) == before


def _sc_legacy_with_policy(tmp_path: Path, via: str, action: str, apply: bool) -> None:
    """Policy mode (another project holds a grant and this one is marked) with only a
    `session_allowlist`: no grant, no access."""
    other = make_env(tmp_path, "granted_elsewhere")
    assert other.project_grant is not None
    root = _registered(tmp_path / "marked_no_grant", other.data_root)
    (root / ".rush").mkdir(exist_ok=True)
    (root / ".rush" / "memory-policy.required").write_text("", encoding="utf-8")
    before = _digest_tree(root)
    extra: dict[str, Any] = {} if action == "resolve" else {"apply": apply}
    res = call(
        root, action, via=via, session=[PREFS], **_DENIAL_REQUESTS[action], **extra
    )
    _denied(res, "E_PERMISSION", "no_grant")
    assert _digest_tree(root) == before
    assert not _db(root).exists()


def _sc_bridge(tmp_path: Path, selected: bool) -> None:
    from rush.mcp_support.tool_registry import build_memory_bridge_handler

    m = _menv(tmp_path)
    plain = rec_ok(m.env, "bridge.plain", "p")["artifact_id"]
    refs = [{"id": m.project if selected else plain, "version": 2}]
    prepared = _res(
        MemoryTool().run(
            m.env.root,
            operation="handoff",
            owner_scope=m.env.owner.as_dict(),
            request={
                "action": "prepare",
                "receiver_namespace": PREFS,
                "receiver_audience": "codex_cli",
                "goal": "sync",
                "selected_refs": refs,
            },
            permissions=ExecutionPermissions(cache_write=True),
        )
    )
    assert prepared.code == "OK", prepared.dump()
    handler = build_memory_bridge_handler(
        root=m.env.root,
        session_id=prepared.data["handoff_id"],
        capability=prepared.data["capability"],
    )
    before = snapshot(m.env)
    for action in ACTIONS:
        assert handler("preference", {"action": action, "key": FMT}) == BRIDGE_DENIAL
    assert snapshot(m.env) == before


@dataclasses.dataclass(frozen=True)
class _Cell:
    ident: str
    run: Any


def _matrix_cells() -> list[Any]:
    cells: list[_Cell] = []
    seen: set[str] = set()

    def add(ident: str, run: Any) -> None:
        assert ident not in seen, ident
        seen.add(ident)
        cells.append(_Cell(ident, run))

    def name(via: str, action: str, dims: str, producer: str | None = None) -> str:
        suffix = f"-{producer}" if producer else ""
        return f"{via}.preference_{action}-{dims}{suffix}"

    for via in TRANSPORTS:
        for action in ACTIONS:
            add(
                name(via, action, "access-policy-apply-preview-cache_write-off"),
                lambda t, v=via, a=action: _sc_preview(t, v, a),
            )
            add(
                name(
                    via, action, "access-policy-policy_state-ok-grant_ops-missing_one"
                ),
                lambda t, v=via, a=action: _sc_grant_missing_one(t, v, a),
            )
            add(
                name(via, action, "cache_write-off-apply-apply"),
                lambda t, v=via, a=action: _sc_cache_write_off(t, v, a),
            )
            if action in {"resolve", "record", "correct"}:
                add(
                    name(via, action, "access-overlay-grant_ops-missing_one"),
                    lambda t, v=via, a=action: _sc_overlay_missing_op(t, v, a),
                )
            if via != "cli":
                if action in {"resolve", "record", "correct"}:
                    add(
                        name(via, action, "access-overlay-revoked-apply-apply"),
                        lambda t, v=via, a=action: _sc_overlay_revoked(t, v, a),
                    )
                add(
                    name(via, action, "cache_write-on-grant_ops-ask_only"),
                    lambda t, v=via, a=action: _sc_cache_write_ask_only(t, v, a),
                )
            for state in ("missing_with_marker", "invalid"):
                add(
                    name(via, action, f"policy_state-{state}"),
                    lambda t, v=via, a=action, s=state: _sc_policy_state(t, v, a, s),
                )
            for key, value, dimension, producer in (
                ("archive_mode", "inspect", "mode-inspect", "72-T06"),
                ("archive_mode", "historical", "mode-historical", "72-T06"),
                ("representation", "utf8", "representation-utf8", None),
                ("retrieval", "hybrid", "retrieval-hybrid", None),
                (
                    "ack",
                    [{"id": "x", "version": 1, "digest": "0" * 64}],
                    "ack-ack",
                    None,
                ),
            ):
                add(
                    name(via, action, dimension, producer),
                    lambda t, v=via, a=action, k=key, val=value: _sc_extra_key(
                        t, v, a, k, val
                    ),
                )
            for apply in (False, True):
                phase = "apply" if apply else "preview"
                if action != "resolve" or not apply:
                    add(
                        name(via, action, f"access-legacy_allowlist-apply-{phase}"),
                        lambda t, v=via, a=action, ap=apply: _sc_legacy(t, v, a, ap),
                    )
                    add(
                        name(via, action, f"store-absent-apply-{phase}"),
                        lambda t, v=via, a=action, ap=apply: _sc_store_absent(
                            t, v, a, ap
                        ),
                    )
                    add(
                        name(via, action, f"access-overlay-apply-{phase}"),
                        lambda t, v=via, a=action, ap=apply: _sc_overlay(t, v, a, ap),
                    )
                    add(
                        name(via, action, f"store-old_schema-apply-{phase}"),
                        lambda t, v=via, a=action, ap=apply: _sc_store_old_schema(
                            t, v, a, ap
                        ),
                    )
                    if via != "cli":
                        add(
                            name(
                                via,
                                action,
                                f"access-legacy_allowlist-policy_state-marked-apply-{phase}",
                            ),
                            lambda t, v=via, a=action, ap=apply: _sc_legacy_with_policy(
                                t, v, a, ap
                            ),
                        )
            if action != "resolve":
                add(
                    name(via, action, "access-policy-apply-apply"),
                    lambda t, v=via, a=action: _sc_apply(t, v, a),
                )
        add(
            name(via, "resolve", "access-overlay_owner_argument"),
            lambda t, v=via: _sc_overlay_owner_argument(t, v, "resolve"),
        )
        for state in ("archived", "expired", "tampered", "rejected", "pending"):
            for action in ("resolve", "correct"):
                add(
                    name(via, action, f"row_state-{state}"),
                    lambda t, v=via, a=action, s=state: _sc_row_state(t, v, a, s),
                )
    for selected in (True, False):
        value = "selected" if selected else "unselected"
        add(
            f"bridge.mcp_bridge-operation-preference-capability_ids-{value}",
            lambda t, s=selected: _sc_bridge(t, s),
        )
    return cells


_MATRIX = _matrix_cells()


@pytest.mark.parametrize("cell", _MATRIX, ids=[c.ident for c in _MATRIX])
def test_t05_route_mode_matrix(cell: _Cell, tmp_path: Path) -> None:
    """G2/G2a: every preference action x transport x dimension is one cell asserting the
    exact code, reason and effects; producer-staged cells name their producer."""
    cell.run(tmp_path)


# --- D25 / brief 3.2: overlay route results for the other MemoryTool routes --------------


def _overlay_row(env: Env, artifact_id: str, marker: str) -> None:
    TypedArtifactStore(env.data_root / "user").write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"text": f"needle {marker}"},
            source=PERSONAL,
            created_at=time.time(),
            owner_scope=env.overlay_owner,
        )
    )


def _overlay_driver(env: Env, name: str, row_id: str = "ov1") -> Res:
    ov = env.overlay_owner.as_dict()
    permissions = ExecutionPermissions(cache_write=True)
    tool = MemoryTool()
    link = {
        "source_id": row_id,
        "source_version": 1,
        "target_id": row_id,
        "target_version": 1,
        "kind": "depends_on",
    }
    archive = {"id": row_id, "expected_version": 1, "scope": "domain_knowledge"}
    delete = {
        "artifact_ids": [row_id],
        "expected_revisions": {row_id: 1},
        "scope": "domain_knowledge",
    }
    edit = {
        "id": row_id,
        "expected_version": 1,
        "scope": "domain_knowledge",
        "content": {"text": "overlay changed"},
    }

    def query(operation: str, **extra: Any) -> Any:
        return tool.run(
            env.root,
            operation=operation,  # type: ignore[arg-type]
            subject="domain_knowledge",
            query="needle",
            owner_scope=ov,
            **extra,
        )

    def generic(operation: str, request: dict[str, Any], **extra: Any) -> Any:
        return tool.run(
            env.root,
            operation=operation,  # type: ignore[arg-type]
            owner_scope=ov,
            request=request,
            permissions=permissions,
            **extra,
        )

    runs: dict[str, Any] = {
        "ask": lambda: query("ask", request={"view": "compact"}),
        "recall": lambda: query("recall", request={"view": "compact"}),
        "list": lambda: query("list", request={"view": "compact"}),
        "list_legacy": lambda: query("list"),
        "expand": lambda: generic("expand", {"id": row_id, "version": 1}),
        "related": lambda: generic("related", {"id": row_id, "version": 1}),
        "link": lambda: generic("link", link),
        "consolidate": lambda: generic("consolidate", {"symptom": "overlay"}),
        "write_preview": lambda: generic(
            "write",
            {"apply": False},
            subject="domain_knowledge",
            content={"text": "overlay write"},
            source=PERSONAL,
        ),
        "write_apply": lambda: generic(
            "write",
            {"apply": True},
            subject="domain_knowledge",
            content={"text": "overlay write"},
            source=PERSONAL,
        ),
        "promote_preview": lambda: generic(
            "promote",
            {"apply": False},
            subject="domain_knowledge",
            content={"text": "overlay promote"},
            source=PERSONAL,
            user_stated=True,
        ),
        "promote_apply": lambda: generic(
            "promote",
            {"apply": True},
            subject="domain_knowledge",
            content={"text": "overlay promote"},
            source=PERSONAL,
            user_stated=True,
        ),
        "edit_preview": lambda: generic("edit", edit),
        "edit_apply": lambda: generic("edit", {**edit, "apply": True}),
        "maintain_preview": lambda: generic(
            "maintain", {"apply": False}, task="staleness_sweep"
        ),
        "maintain_apply": lambda: generic(
            "maintain", {"apply": True}, task="staleness_sweep"
        ),
        "archive_preview": lambda: generic("archive", archive),
        "archive_apply": lambda: generic("archive", {**archive, "apply": True}),
        "delete_preview": lambda: generic("delete", delete),
        "delete_apply": lambda: generic("delete", {**delete, "apply": True}),
    }
    return _res(runs[name]())


_OVERLAY_REFUSED = (
    "link",
    "consolidate",
    "write_preview",
    "write_apply",
    "promote_preview",
    "promote_apply",
    "edit_preview",
    "edit_apply",
    "maintain_preview",
    "maintain_apply",
)
_OVERLAY_READS = ("ask", "recall", "list", "list_legacy", "expand", "related")


@pytest.mark.parametrize("name", _OVERLAY_REFUSED + _OVERLAY_READS)
def test_t05_overlay_route_results(name: str, tmp_path: Path) -> None:
    """Brief 3.2/D25: an `owner_scope == user_overlay_owner_scope()` request reads the
    overlay store on the read routes; `write`, `promote`, `edit`, `link`, `consolidate`
    and `maintain` refuse it with `E_OWNER overlay_requires_preference_route` and zero
    effects, before any resolution."""
    env = make_env(tmp_path)
    _overlay_row(env, "ov1", "ov1-marker")
    before = snapshot(env)
    result = _overlay_driver(env, name)
    if name in _OVERLAY_REFUSED:
        assert (result.code, result.reason) == (
            "E_OWNER",
            "overlay_requires_preference_route",
        ), result.dump()
        assert snapshot(env) == before
        assert "ov1-marker" not in result.dump()
        return
    assert result.code == "OK", result.dump()
    assert snapshot(env) == before
    if name == "related":
        assert result.data["items"] == []
        return
    assert "ov1-marker" in result.dump(), name
    if name in {"ask", "recall", "list"}:
        assert [i["id"] for i in result.data["items"]] == ["ov1"]


@pytest.mark.parametrize("name", ["archive", "delete"])
def test_t05_overlay_archive_delete_use_the_overlay_store(
    name: str, tmp_path: Path
) -> None:
    """Brief 3.2: `archive`/`delete` preview with {overlay_read, list} and apply with
    {write} on the overlay-owner grant, against `TypedArtifactStore(<data>/user)`."""
    env = make_env(tmp_path)
    _overlay_row(env, "ov1", "ov1-marker")
    before = snapshot(env)
    preview = _overlay_driver(env, f"{name}_preview")
    assert preview.code == "OK", preview.dump()
    assert preview.data["applied"] is False
    assert snapshot(env) == before
    applied = _overlay_driver(env, f"{name}_apply")
    assert applied.code == "OK", applied.dump()
    assert applied.data["applied"] is True
    assert not env.db.exists()  # the project store is never touched
    row = _sql(
        env.overlay_db, "SELECT archived_at FROM memory_artifacts WHERE id = 'ov1'"
    )
    if name == "archive":
        assert row[0]["archived_at"] is not None
    else:
        assert row == []
    # Without the overlay `write` operation the apply is refused, the preview is not.
    other = make_env(
        tmp_path, "limited", overlay_ops=("overlay_read", "list", "expand")
    )
    _overlay_row(other, "ov2", "ov2-marker")
    limited_before = snapshot(other)
    assert _overlay_driver(other, f"{name}_preview", "ov2").code == "OK"
    denied = _overlay_driver(other, f"{name}_apply", "ov2")
    assert (denied.code, denied.reason) == ("E_PERMISSION", "operation_not_granted")
    assert snapshot(other) == limited_before


# --- schema additions: reads never migrate a store lacking only the T05 columns ---------


def test_t05_read_routes_never_migrate_t05_columns(tmp_path: Path) -> None:
    """Addendum (T02 no-migration-on-read): a store that lacks only the T05 additions is
    read through the read view; compact reads with `cache_write` and `resolve` keep the
    DB bytes and add no column."""
    env = make_env(tmp_path)
    rec_ok(env, "cols.k", "needle value")
    rec_ok(env, "cols.p", "needle personal", scope="personal")
    t05_columns = {
        "memory_artifacts": (
            "applicability",
            "task_project_id",
            "task_worktree_id",
            "task_id",
        ),
        "memory_artifact_versions": (
            "applicability",
            "task_project_id",
            "task_worktree_id",
            "task_id",
            "binding_recorded",
        ),
    }
    for db in (env.db, env.overlay_db):
        with contextlib.closing(sqlite3.connect(db)) as conn:
            for table, columns in t05_columns.items():
                for column in columns:
                    conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
            conn.commit()

        def names(table: str, path: Path = db) -> set[str]:
            return {r["name"] for r in _sql(path, f"PRAGMA table_info({table})")}

        assert not names("memory_artifacts") & set(t05_columns["memory_artifacts"])
    before = {db: _sha(db) for db in (env.db, env.overlay_db)}
    tool = MemoryTool()
    permissions = ExecutionPermissions(cache_write=True)
    for operation in ("ask", "recall", "list"):
        result = _res(
            tool.run(
                env.root,
                operation=operation,  # type: ignore[arg-type]
                subject="preference",
                query="needle",
                owner_scope=env.owner.as_dict(),
                request={"view": "compact"},
                permissions=permissions,
            )
        )
        assert result.code == "OK", (operation, result.dump())
    for via in TRANSPORTS:
        assert resolve(env, key="cols.k", via=via).code == "OK", via
    for db in (env.db, env.overlay_db):
        assert _sha(db) == before[db]
        artifact_columns = {
            r["name"] for r in _sql(db, "PRAGMA table_info(memory_artifacts)")
        }
        assert not artifact_columns & set(t05_columns["memory_artifacts"])
        version_columns = {
            r["name"] for r in _sql(db, "PRAGMA table_info(memory_artifact_versions)")
        }
        assert not version_columns & set(t05_columns["memory_artifact_versions"])


# --- B13 / B9 / D41 / schema: the remaining observable behaviors --------------------------


def test_t05_correction_records_affected_downstream_refs(tmp_path: Path) -> None:
    """B13: `correction_refs[-1].affected` lists, sorted, the visible sources of the
    relations whose target is the corrected id; a source the access cannot see is
    absent."""
    env = make_env(tmp_path)
    target = rec_ok(env, "affected.k", "v")
    store = TypedArtifactStore(env.root)
    for artifact_id in ("zz-derived", "aa-derived"):
        store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"text": f"derived {artifact_id}"},
                source=PREFS,
                created_at=time.time(),
                owner_scope=env.owner,
            )
        )
    store.write(
        MemoryArtifact(
            id="hidden-derived",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"text": "hidden"},
            source="not-granted-source",
            created_at=time.time(),
            owner_scope=env.owner,
        )
    )
    for source_id in ("zz-derived", "aa-derived", "hidden-derived"):
        _link_rows(env.db, source_id, target["artifact_id"], 1)
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        # `_link_rows` writes version 1 on both ends; the target is at version 2.
        conn.execute(
            "UPDATE memory_relations SET target_version = 2 WHERE target_id = ?",
            (target["artifact_id"],),
        )
        conn.commit()
    out = call(
        env,
        "correct",
        artifact_id=target["artifact_id"],
        layer="project",
        kind="reject",
        reason="downstream matters",
        expected_version=2,
        user_stated=True,
        apply=True,
    )
    assert out.code == "OK", out.dump()
    refs = _row_of(env.db, target["artifact_id"])["content"]["correction_refs"]
    assert refs[-1]["affected"] == [
        {"artifact_id": "aa-derived", "artifact_version": 1},
        {"artifact_id": "zz-derived", "artifact_version": 1},
    ]
    assert refs[-1]["kind"] == "reject" and refs[-1]["from_version"] == 2
    assert "hidden-derived" not in _dump(refs)


def test_t05_task_expiry_and_explicit_end(tmp_path: Path) -> None:
    """B9: a task key carries its expiry or ends explicitly; an expired task row stops
    applying, and the `expires_at` column mirrors the request."""
    env = make_env(tmp_path)
    expires = time.time() + 3600
    row = rec_ok(
        env, "expiry.k", "task-value", scope="task", task_id="T1", expires_at=expires
    )
    stored = _row_of(env.db, row["artifact_id"])
    assert stored["expires_at"] == expires
    assert stored["content"]["expires_at"] == expires
    assert (
        entry(resolve(env, key="expiry.k", task_id="T1"), "expiry.k")["selected"][
            "value"
        ]
        == "task-value"
    )
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET expires_at = ? WHERE id = ?",
            (time.time() - 10, row["artifact_id"]),
        )
        conn.commit()
    after = resolve(env, key="expiry.k", task_id="T1")
    assert after.code == "OK", after.dump()
    assert all(e["selected"] is None for e in after.data["preferences"])
    assert "task-value" not in after.dump()


def test_t05_imported_rows_are_pending_or_advice(tmp_path: Path) -> None:
    """Brief 3.4/4: imported records classify as `pending` (review required) or advice
    (active but not STATED); neither is selected; `record` refuses the import authority."""
    env = make_env(tmp_path)
    store = TypedArtifactStore(env.root)
    for artifact_id, applicability in (
        ("imp-pending", "pending"),
        ("imp-active", "active"),
    ):
        seed_row(
            store,
            artifact_id,
            env.owner,
            key="imported.k",
            value=artifact_id,
            scope="project",
            authority="imported_unverified",
            applicability=applicability,
            project_id=env.project_id,
            worktree_id=env.worktree_id,
        )
    item = entry(resolve(env, key="imported.k"), "imported.k")
    assert item["status"] == "none" and item["selected"] is None
    assert [r["artifact_id"] for r in item["pending"]] == ["imp-pending"]
    assert [r["artifact_id"] for r in item["advice"]] == ["imp-active"]
    assert why_view(item) == expected_why(
        [
            ("project", "imp-pending", 1, "pending_review"),
            ("project", "imp-active", 1, "advice_not_explicit"),
        ]
    )
    refused = rec(env, "imported.k", "v", authority="imported_unverified")
    assert refused.code == "E_INPUT" and refused.reason == "authority_import_only"


def test_t05_row_mac_covers_applicability_and_task_columns(tmp_path: Path) -> None:
    """D41/3.15: the four T05 current-row columns extend `ROW_MAC_COLUMNS` (NULL values
    are omitted, so pre-T05 MACs stay valid); setting a covered column by SQL, even to a
    value that changes no visibility rule, breaks the row's MAC and hides it."""
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility
    from rush.memory.store import ROW_MAC_COLUMNS

    assert ROW_MAC_COLUMNS[-4:] == (
        "applicability",
        "task_project_id",
        "task_worktree_id",
        "task_id",
    )
    env = make_env(tmp_path)
    store = TypedArtifactStore(env.root)
    ask = MemoryAccess.resolve(env.root, operation="ask", owner_scope=env.owner)
    assert ask is not None

    def visible(artifact_id: str) -> bool:
        row = store.get_current_row(artifact_id)
        assert row is not None
        return bool(evaluate_artifact_visibility(store, row, access=ask).visible)

    for index, (column, value) in enumerate(
        (
            ("applicability", "active"),
            ("task_project_id", "p-x"),
            ("task_worktree_id", "w-x"),
        )
    ):
        artifact_id = f"mac-{index}"
        seed_row(
            store,
            artifact_id,
            env.owner,
            key=f"mac.k{index}",
            value="v",
            scope="project",
            project_id=env.project_id,
            worktree_id=env.worktree_id,
        )
        assert visible(artifact_id), column
        with contextlib.closing(sqlite3.connect(env.db)) as conn:
            conn.execute(
                f"UPDATE memory_artifacts SET {column} = ? WHERE id = ?",
                (value, artifact_id),
            )
            conn.commit()
        assert not visible(artifact_id), column
        res = resolve(env, key=f"mac.k{index}")
        assert res.code == "OK" and artifact_id not in res.dump(), column
        with contextlib.closing(sqlite3.connect(env.db)) as conn:
            conn.execute(
                f"UPDATE memory_artifacts SET {column} = NULL WHERE id = ?",
                (artifact_id,),
            )
            conn.commit()
        assert visible(artifact_id), column


def test_t05_additive_columns_and_binding_recorded(tmp_path: Path) -> None:
    """3.15: the writable constructor adds the T05 columns to an older store; pre-T05
    version rows keep `binding_recorded` NULL, versions written afterwards carry 1."""
    env = make_env(tmp_path)
    first = rec_ok(env, "cols.k", "v")
    t05_columns = {
        "memory_artifacts": (
            "applicability",
            "task_project_id",
            "task_worktree_id",
            "task_id",
        ),
        "memory_artifact_versions": (
            "applicability",
            "task_project_id",
            "task_worktree_id",
            "task_id",
            "binding_recorded",
        ),
    }
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        for table, columns in t05_columns.items():
            for column in columns:
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()
    TypedArtifactStore(env.root)  # the writable constructor migrates
    for table, columns in t05_columns.items():
        present = {r["name"] for r in _sql(env.db, f"PRAGMA table_info({table})")}
        assert set(columns) <= present, table
    old_versions = _version_rows(env.db, first["artifact_id"])
    assert [v["binding_recorded"] for v in old_versions] == [None, None]
    second = rec_ok(env, "cols.k2", "v2")
    new_versions = _version_rows(env.db, second["artifact_id"])
    assert [v["binding_recorded"] for v in new_versions] == [1, 1]
    assert {v["applicability"] for v in new_versions} == {"active"}
    handoff_columns = {
        r["name"] for r in _sql(env.db, "PRAGMA table_info(memory_handoff_sessions)")
    }
    assert "sender_task_id" in handoff_columns


def test_t05_mcp_task_id_field_validation() -> None:
    """3.9/3.11: `task_id` is an optional non-empty string on every memory operation's
    strict model (the `end_task` target stays a request field)."""
    from rush.mcp_support.request_models import validate_and_normalize

    base = {"path": ".", "operation": "ask", "subject": "episodic", "query": "q"}
    ok = validate_and_normalize("rush_memory", {**base, "task_id": "A"})
    assert not ok.rejected and ok.arguments is not None
    assert ok.arguments["task_id"] == "A"
    preference = {
        "path": ".",
        "operation": "preference",
        "request": {"action": "resolve", "key": "k"},
    }
    assert not validate_and_normalize(
        "rush_memory", {**preference, "task_id": "A"}
    ).rejected
    for bad in ("", 123, ["A"]):
        outcome = validate_and_normalize("rush_memory", {**base, "task_id": bad})
        assert outcome.rejected, bad
        assert outcome.error is not None, bad
        assert outcome.error["data"]["details"][0]["loc"][0] == "task_id", bad
    end_task = {
        "path": ".",
        "operation": "preference",
        "request": {
            "action": "end_task",
            "task_id": "T",
            "expected_versions": {"a": 2},
        },
    }
    assert not validate_and_normalize("rush_memory", end_task).rejected


def _t05_flip_cells() -> list[Any]:
    import importlib

    cap = importlib.import_module("tests.test_memory_capsule")

    return cap.flip_params("t05")


@pytest.mark.parametrize("cell", _t05_flip_cells())
def test_t05_codec_route_mode_matrix(cell: Any, tmp_path: Path) -> None:
    """G2a, 73-T09/CODEC: the capsule/import cells of this matrix (access,
    cache_write) are the real `preview_export`/`export`/`preview_import`/`import`/
    `bridge`/mapping cells of the CODEC G2 table, never producer-staged `E_INPUT`
    placeholders."""
    import importlib

    cap = importlib.import_module("tests.test_memory_capsule")

    assert "producer" not in cell.id
    cap.run_cell(cell, tmp_path)
