"""73-T09/CODEC: portable capsule codec, public `capsule` operation, mapping consent.

G5 tests, written against the pinned interfaces of `docs/phase-plans/
phase-72-memory-correctness-and-user-control-plan.md` (73-T09/CODEC packet and
design brief). Every test imports the symbols the packet adds
(`rush.memory.capsule`, the `authorization` mapping helpers, ...) inside its own
body, so this module collects at a HEAD that has none of them and each test
fails on its own until CODEC lands.

Isolation (G10): the autouse `_isolated_home` fixture of `tests/conftest.py`
places HOME, XDG_DATA_HOME and LOCALAPPDATA of every test under a temporary
directory, so `default_data_root()` never names the real data root.
"""

from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import importlib
import json
import os
import re
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

import pytest
from click.testing import CliRunner

from rush.delivery.compact import canonical_json
from rush.memory.store import MemoryArtifact, OwnerScope, TypedArtifactStore
from rush.permissions import ExecutionPermissions
from rush.setup.provision import default_data_root
from rush.tools.memory import MemoryTool
from rush.workflows.projects import register_project

SRC = "capsule-src"
IMPORT_SRC = "capsule:import"
ALICE = OwnerScope("user", "alice")
BOB = OwnerScope("user", "bob")
COMMIT = "a" * 40
COMMIT_2 = "b" * 40
ZERO_UUID = "00000000-0000-0000-0000-000000000000"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
ALL_OPS = ("ask", "expand", "list", "write")

CAPSULE_KEYS = {
    "schema_version",
    "format",
    "capsule_id",
    "created_at",
    "origin",
    "scope",
    "task",
    "evidence",
    "manifest",
    "payload_sha256",
}
ORIGIN_KEYS = {"rush_version", "project_id", "worktree_id", "git", "store_revision"}
SCOPE_KEYS = {"owner", "sources", "personal_owner"}
TASK_KEYS = {
    "description",
    "objective",
    "completed",
    "remaining",
    "next_action",
    "constraints",
    "decisions",
    "failed_approaches",
    "blockers",
    "discoveries",
    "last_verified_checkpoint",
}
MANIFEST_KEYS = {
    "selected",
    "omitted",
    "redactions",
    "required_body_coverage",
    "encoding",
    "evidence_bytes",
    "evidence_tokens",
    "source_paths",
    "local_only_refs",
    "mapping_requirement",
    "omitted_bytes",
    "omitted_tokens",
    "export_effect",
}
EVIDENCE_KEYS = {
    "artifact_id",
    "version",
    "content_hash",
    "subject",
    "source",
    "owner",
    "provenance",
    "symbol_ref",
    "source_path",
    "source_revision",
    "freshness",
    "body",
    "body_sha256",
}
EXPORT_EFFECT_KEYS = {"invocation_id", "effect_id", "request_digest"}
RECORD_KEYS = {
    "foreign_origin_id",
    "family",
    "subject",
    "content",
    "foreign_source",
    "foreign_owner",
    "foreign_symbol_ref",
    "foreign_content_hash",
}
SUBJECT_FAMILY = {
    "active_context": "handoff",
    "episodic": "experience",
    "preference": "memory",
    "failure": "memory",
    "architectural_decision": "memory",
    "domain_knowledge": "memory",
    "skill_pattern": "skill",
}


# --- small pure helpers ---------------------------------------------------------


def sha(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


def canon(value: Any) -> bytes:
    return canonical_json(value)


def owner_hex(owner: OwnerScope) -> dict[str, str]:
    return {"kind": owner.kind, "id": sha(owner.id)}


def token_count(text: str) -> int:
    from rush.memory import retrieval

    return retrieval._count_tokens(text, retrieval.DEFAULT_ENCODING)


def payload_digest(capsule: dict[str, Any]) -> str:
    return sha(canon({k: v for k, v in capsule.items() if k != "payload_sha256"}))


def revision_of(data_root: Path) -> int:
    from rush.memory import authorization as auth

    return int(auth.load_policy_readonly(data_root=data_root)["policy_revision"] or 0)


def new_uuid() -> str:
    return str(uuid.uuid4())


def tree_state(*roots: Path) -> dict[str, Any]:
    """Every path under each root: directories as `"d"`, files as their sha256
    (SQLite `-wal`/`-shm` side files excluded: a read-only open may touch them
    without changing the store)."""
    state: dict[str, Any] = {}
    for root in roots:
        if not root.exists():
            state[f"{root}::absent"] = True
            continue
        for path in sorted(root.rglob("*")):
            if path.name.endswith(("-wal", "-shm")):
                continue
            if path.is_symlink():
                state[str(path)] = ("l", os.readlink(path))
            elif path.is_dir():
                state[str(path)] = "d"
            else:
                state[str(path)] = sha(path.read_bytes())
    return state


# --- environment -----------------------------------------------------------------


@dataclasses.dataclass
class CapEnv:
    root: Path
    data_root: Path
    store: TypedArtifactStore | None
    project_id: str
    worktree_id: str
    owner: OwnerScope
    exports: Path
    outside: Path
    grant: dict[str, Any] | None
    tmp: Path

    @property
    def db(self) -> Path:
        return self.root / ".rush" / "memory.db"

    def effects(self, *extra: Path) -> dict[str, Any]:
        """Everything a zero-effects assertion compares."""
        from rush.memory import authorization as auth

        policy = auth.policy_path(data_root=self.data_root)
        return {
            "tree": tree_state(self.root, self.data_root, self.outside, *extra),
            "db": sha(self.db.read_bytes()) if self.db.exists() else None,
            "policy": sha(policy.read_bytes()) if policy.exists() else None,
        }


def grant_for(
    root: Path,
    owner: OwnerScope,
    data_root: Path,
    *,
    sources: tuple[str, ...] = (SRC, IMPORT_SRC),
    ops: tuple[str, ...] = ALL_OPS,
) -> dict[str, Any]:
    from rush.memory import authorization as auth

    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=revision_of(data_root),
        consent=True,
        data_root=data_root,
    )


def make_env(
    tmp_path: Path,
    name: str = "project",
    *,
    owner: OwnerScope = ALICE,
    ops: tuple[str, ...] = ALL_OPS,
    sources: tuple[str, ...] = (SRC, IMPORT_SRC),
    grant: bool = True,
    seed: bool = True,
    files: dict[str, str] | None = None,
    create_store: bool = True,
) -> CapEnv:
    """A registered project with a store, one consented grant and (by default) one
    open task whose newest checkpoint `cp1` cites evidence rows `ev1` and `ev2`."""
    from rush.memory import authorization as auth

    data_root = default_data_root()
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    if files:
        git_commit_files(root, files)
    record = register_project(root, data_root=data_root)
    root = root.resolve()
    exports = root / "exports"
    exports.mkdir()
    outside = (tmp_path / f"{name}-outside").resolve()
    outside.mkdir(exist_ok=True)
    store = TypedArtifactStore(root) if create_store else None
    env = CapEnv(
        root=root,
        data_root=data_root,
        store=store,
        project_id=record.project_id,
        worktree_id=auth._worktree_id(root),
        owner=owner,
        exports=exports,
        outside=outside,
        grant=None,
        tmp=tmp_path,
    )
    if grant:
        env.grant = grant_for(root, owner, data_root, sources=sources, ops=ops)
    if seed and create_store:
        seed_open_task(env)
    return env


def git_commit_files(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    for args in (
        ("init", "--initial-branch=main"),
        ("add", "-A"),
        ("commit", "-m", "fixture"),
    ):
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=fixture",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


KNOWN_SRC = "def Known():\n    return 1\n"


def put_anchored_evidence(env: CapEnv, artifact_id: str) -> MemoryArtifact:
    """An evidence row anchored at `src_mod.py::Known` whose stored hash matches the
    committed file, so its freshness is `current`."""
    assert env.store is not None
    return env.store.write(
        MemoryArtifact(
            id=artifact_id,
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content=evidence_body(artifact_id),
            source=SRC,
            created_at=time.time(),
            symbol_ref="src_mod.py::Known",
            content_hash=sha((env.root / "src_mod.py").read_bytes()),
            owner_scope=env.owner,
        )
    )


def evidence_body(tag: str) -> dict[str, Any]:
    return {"text": f"needle {tag}", "note": f"Ünïcode ✓ {tag}"}


def cp_content(
    env: CapEnv,
    task_id: str = "task-1",
    event_id: str = "ev-1",
    event_kind: str = "verified_outcome",
    **override: Any,
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "kind": "checkpoint",
        "schema_version": 1,
        "task_id": task_id,
        "task_lineage_id": f"lineage-{task_id}",
        "event_id": event_id,
        "event_kind": event_kind,
        "project_id": env.project_id,
        "worktree_id": env.worktree_id,
        "source": {
            "commit": COMMIT,
            "branch": "main",
            "dirty": False,
            "file_sha256": None,
        },
        "requirements": [
            {
                "id": "c1",
                "text": "Never rewrite history ünïcode",
                "authority": "user_explicit",
                "provenance": "user:turn-1",
            },
            {
                "id": "c2",
                "text": "Keep the suite green",
                "authority": "user_explicit",
                "provenance": "user:turn-2",
            },
        ],
        "implemented": ["parsed config", "wrote codec"],
        "attempted": ["tried a regex"],
        "disproved": [{"text": "regex parsing is unsafe", "origin_ref": "attempt-1"}],
        "checks": [
            {
                "command": ["pytest", "-q"],
                "exit_code": 0,
                "status": "passed",
                "source_revision": COMMIT,
                "receipt_id": "r1",
            },
            {
                "command": ["ruff", "check"],
                "exit_code": 1,
                "status": "failed",
                "source_revision": COMMIT,
                "receipt_id": "r2",
            },
            {
                "command": ["pytest", "-q", "tests/x.py"],
                "exit_code": 0,
                "status": "passed",
                "source_revision": COMMIT,
                "receipt_id": "r3",
            },
        ],
        "unresolved": ["wire the CLI flag"],
        "next_action": "Wire the CLI flag and rerun the suite",
        "origin": "tool_receipt",
        "description": "Portable capsule work",
        "objective": "Ship offline continuation",
        "decisions": [{"text": "use canonical json", "origin_ref": "d1"}],
        "blockers": [{"text": "awaiting review", "origin_ref": "b1"}],
        "discoveries": [{"text": "cap is 64 KiB", "origin_ref": "x1"}],
        "evidence_refs": [
            {"artifact_id": "ev1", "version": 1},
            {"artifact_id": "ev2", "version": 1},
        ],
    }
    content.update(override)
    return content


def put_checkpoint(
    env: CapEnv,
    artifact_id: str,
    *,
    task_id: str = "task-1",
    event_id: str | None = None,
    event_kind: str = "verified_outcome",
    created_at: float | None = None,
    owner: OwnerScope | None = None,
    source: str = SRC,
    **override: Any,
) -> MemoryArtifact:
    content = cp_content(
        env, task_id, event_id or f"ev-{artifact_id}", event_kind, **override
    )
    assert env.store is not None
    return env.store.write(
        MemoryArtifact(
            id=artifact_id,
            family="experience",
            subject="episodic",
            trust_tier="DERIVED",
            content=content,
            source=source,
            created_at=created_at if created_at is not None else time.time(),
            owner_scope=owner or env.owner,
        )
    )


def put_evidence(
    env: CapEnv,
    artifact_id: str,
    *,
    body: dict[str, Any] | None = None,
    owner: OwnerScope | None = None,
    subject: str = "domain_knowledge",
    source: str = SRC,
    store: TypedArtifactStore | None = None,
) -> MemoryArtifact:
    target_store = store or env.store
    assert target_store is not None
    return target_store.write(
        MemoryArtifact(
            id=artifact_id,
            family=SUBJECT_FAMILY[subject],  # type: ignore[arg-type]
            subject=subject,  # type: ignore[arg-type]
            trust_tier="DERIVED",
            content=body if body is not None else evidence_body(artifact_id),
            source=source,
            created_at=time.time(),
            owner_scope=owner or env.owner,
        )
    )


def seed_open_task(env: CapEnv) -> None:
    now = time.time() - 100.0
    put_evidence(env, "ev1")
    put_evidence(env, "ev2")
    put_checkpoint(env, "cp1", created_at=now)


def row_of(env: CapEnv, artifact_id: str) -> dict[str, Any]:
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM memory_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
    assert row is not None, artifact_id
    return dict(row)


def raw_sql(env: CapEnv, sql: str, *params: Any) -> None:
    """A raw write behind the store's back (used to plant bodies the writer refuses)."""
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(sql, params)
        conn.commit()


def plant_content(env: CapEnv, artifact_id: str, content: dict[str, Any]) -> None:
    """Replace a row's stored content behind the writer (which redacts secrets),
    keeping its payload hash and row MAC consistent so the row stays usable."""
    plant_content_text(env, artifact_id, json.dumps(content))


def plant_content_text(env: CapEnv, artifact_id: str, text: str) -> None:
    """`plant_content` for stored text that `json.dumps` cannot produce (nesting past
    the recursion limit): the text is written exactly as given."""
    from rush.memory.store import next_row_mac, payload_digest

    digest = payload_digest(text)
    version = row_of(env, artifact_id)["artifact_version"]
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        mac = next_row_mac(
            conn, env.root, artifact_id, {"content": text, "payload_hash": digest}
        )
        conn.execute(
            "UPDATE memory_artifacts SET content = ?, payload_hash = ?, row_mac = ? "
            "WHERE id = ?",
            (text, digest, mac, artifact_id),
        )
        conn.execute(
            "UPDATE memory_artifact_versions SET content = ?, payload_hash = ? "
            "WHERE artifact_id = ? AND artifact_version = ?",
            (text, digest, artifact_id, version),
        )
        conn.commit()


def store_revision(db: Path) -> int:
    if not db.exists():
        return 0
    with contextlib.closing(sqlite3.connect(db)) as conn:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_changes'"
        ).fetchone()
        if exists is None:
            return 0
        return int(
            conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM memory_changes"
            ).fetchone()[0]
        )


# --- expected capsule content, computed independently of the implementation ------


def expected_task(content: dict[str, Any]) -> dict[str, Any]:
    passed = [
        c for c in content["checks"] if c["status"] == "passed" and c["exit_code"] == 0
    ]
    last = passed[-1]
    return {
        "description": content["description"],
        "objective": content["objective"],
        "completed": content["implemented"],
        "remaining": content["unresolved"],
        "next_action": content["next_action"],
        "constraints": [
            {"constraint_id": q["id"], "text": q["text"], "origin_ref": q["provenance"]}
            for q in content["requirements"]
        ],
        "decisions": content["decisions"],
        "failed_approaches": content["disproved"],
        "blockers": content["blockers"],
        "discoveries": content["discoveries"],
        "last_verified_checkpoint": {
            "command": last["command"],
            "status": last["status"],
            "source_revision": last["source_revision"],
        },
    }


def expected_evidence(env: CapEnv, artifact_id: str, freshness: str) -> dict[str, Any]:
    row = row_of(env, artifact_id)
    body = json.loads(row["content"])
    symbol_ref = row["symbol_ref"]
    path_part = symbol_ref.partition("::")[0] if symbol_ref else None
    return {
        "artifact_id": artifact_id,
        "version": row["artifact_version"],
        "content_hash": row["content_hash"],
        "subject": row["subject"],
        "source": row["source"],
        "owner": {"kind": row["owner_scope_kind"], "id": sha(row["owner_scope_id"])},
        "provenance": {
            "trust_tier": row["trust_tier"],
            "origin_kind": row["origin_kind"],
            "origin_id": row["origin_id"],
        },
        "symbol_ref": symbol_ref,
        "source_path": path_part,
        "source_revision": COMMIT if symbol_ref else None,
        "freshness": freshness,
        "body": body,
        "body_sha256": sha(canon(body)),
    }


def verify_rush_v1(raw: bytes) -> dict[str, Any]:
    """Parse a written `rush_v1` file and check the invariants every export shares."""
    capsule = json.loads(raw)
    assert set(capsule) >= CAPSULE_KEYS
    assert raw == canon(capsule), "the file is canonical_json(capsule)"
    assert capsule["payload_sha256"] == payload_digest(capsule)
    return capsule


# --- calling the public operation through each transport -------------------------


class R:
    """A `capsule` result seen through any transport."""

    def __init__(self, result: Any) -> None:
        self.result = result
        raw = result.get("raw") if hasattr(result, "get") else None
        self.raw: dict[str, Any] = raw if isinstance(raw, dict) else {}
        data = self.raw.get("data")
        self.data: dict[str, Any] = data if isinstance(data, dict) else {}
        self.code: str | None = self.raw.get("code")
        self.reason: Any = self.data.get("reason")
        self.field: Any = self.data.get("field")
        self.status: str | None = (
            result.get("status") if hasattr(result, "get") else None
        )

    def __repr__(self) -> str:
        return (
            f"R(status={self.status!r}, raw={json.dumps(self.raw, default=str)[:1500]})"
        )


def perms(*, cache: bool = True, artifact: bool = True) -> ExecutionPermissions:
    return ExecutionPermissions(cache_write=cache, artifact_write=artifact)


def call_inproc(
    root: Path,
    request: dict[str, Any] | None,
    *,
    cache: bool = True,
    artifact: bool = True,
    **extra: Any,
) -> R:
    return R(
        MemoryTool().run(
            root,
            operation="capsule",
            request=request,
            permissions=perms(cache=cache, artifact=artifact),
            **extra,
        )
    )


_SERVER: list[Any] = []


def _mcp_call(arguments: dict[str, Any]) -> dict[str, Any]:
    import asyncio

    from rush.mcp import build_server

    if not _SERVER:
        _SERVER.append(build_server())
    server = _SERVER[0]

    async def _go() -> Any:
        return await server.call_tool("rush_memory", arguments)

    result = asyncio.run(_go())
    return json.loads(result.content[0].text)


def call_mcp(
    root: Path,
    request: dict[str, Any] | None,
    *,
    cache: bool = True,
    artifact: bool = True,
    **top: Any,
) -> R:
    arguments: dict[str, Any] = {"path": str(root), "operation": "capsule", **top}
    if request is not None:
        arguments["request"] = request
    if cache:
        arguments["allow_cache_write"] = True
    if artifact:
        arguments["allow_artifact_write"] = True
    return R(_mcp_call(arguments))


_CLI_LEAF = {
    "preview_export": "preview-export",
    "export": "export",
    "preview_import": "preview-import",
    "import": "import",
    "bridge": "bridge",
}


def cli_args(
    root: Path,
    request: dict[str, Any],
    *,
    cache: bool = True,
    artifact: bool = True,
    json_out: bool = True,
) -> list[str]:
    args = ["memory", "capsule", _CLI_LEAF[request["action"]], "--project", str(root)]
    for key, flag in (
        ("format", "--format"),
        ("input", "--input"),
        ("instructions", "--instructions"),
        ("output", "--output"),
        ("max_bytes", "--max-bytes"),
        ("max_tokens", "--max-tokens"),
        ("mapping_id", "--mapping-id"),
        ("expected_digest", "--expected-digest"),
        ("expected_store_revision", "--expected-store-revision"),
        ("invocation_id", "--invocation-id"),
    ):
        if key in request:
            args += [flag, str(request[key])]
    for constraint_id in request.get("confirm_constraint_ids", []):
        args += ["--confirm-constraint-id", str(constraint_id)]
    if request.get("apply") is True:
        args.append("--apply")
    selectors = request.get("selectors", {})
    task_ref = selectors.get("task_ref")
    if task_ref is not None:
        args += ["--task-ref", f"{task_ref['artifact_id']}:{task_ref['version']}"]
    owner = selectors.get("owner_scope")
    if owner is not None:
        args += ["--owner", f"{owner['kind']}:{owner['id']}"]
    for source in selectors.get("sources", []):
        args += ["--source", source]
    if selectors.get("include_personal") is True:
        args.append("--include-personal")
    if cache:
        args.append("--allow-cache-write")
    if artifact:
        args.append("--allow-artifact-write")
    if json_out:
        args.append("--json")
    return args


def cli_invoke(args: list[str]) -> Any:
    from rush.cli import cli

    return CliRunner().invoke(cli, args)


def call_cli(
    root: Path,
    request: dict[str, Any],
    *,
    cache: bool = True,
    artifact: bool = True,
) -> R:
    result = cli_invoke(cli_args(root, request, cache=cache, artifact=artifact))
    assert result.exit_code in (0, 1, 2), (result.exit_code, result.output[-1500:])
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - failure diagnostics
        raise AssertionError(
            f"CLI did not print JSON: exit={result.exit_code} out={result.output[-1500:]!r}"
        ) from exc
    return R(payload)


TRANSPORTS = ("inproc", "mcp", "cli")


def call(
    transport: str,
    root: Path,
    request: dict[str, Any],
    *,
    cache: bool = True,
    artifact: bool = True,
) -> R:
    if transport == "inproc":
        return call_inproc(root, request, cache=cache, artifact=artifact)
    if transport == "mcp":
        return call_mcp(root, request, cache=cache, artifact=artifact)
    return call_cli(root, request, cache=cache, artifact=artifact)


def out_for(env: CapEnv, transport: str, name: str) -> Path:
    """An absent output path valid for the transport (MCP needs it under the root)."""
    base = env.exports if transport == "mcp" else env.outside
    return base / name


def exported(
    env: CapEnv,
    name: str = "cap.json",
    *,
    transport: str = "inproc",
    fmt: str | None = None,
    invocation_id: str | None = None,
    **extra: Any,
) -> tuple[Path, R, R]:
    """`preview_export` then `export` with the preview digest; returns the output
    path and both results. `extra` request fields are shared by both calls."""
    out = out_for(env, transport, name)
    base: dict[str, Any] = {
        "output": str(out),
        "invocation_id": invocation_id or new_uuid(),
        **extra,
    }
    if fmt is not None:
        base["format"] = fmt
    preview = call(transport, env.root, {**base, "action": "preview_export"})
    assert preview.code == "OK", preview
    done = call(
        transport,
        env.root,
        {
            **base,
            "action": "export",
            "expected_digest": preview.data["digest"],
        },
    )
    return out, preview, done


def preview_store_revision(data: dict[str, Any]) -> int:
    if "store_revision" in data:
        return int(data["store_revision"])
    return int(data["preview_binding"]["store_revision"])


def preview_store_state(data: dict[str, Any]) -> str:
    if "store_state" in data:
        return str(data["store_state"])
    return str(data["preview_binding"]["store_state"])


def imported(
    env: CapEnv,
    path: Path,
    *,
    transport: str = "inproc",
    fmt: str | None = None,
    invocation_id: str | None = None,
    confirm: list[str] | None = None,
    **extra: Any,
) -> tuple[R, R]:
    """`preview_import` then `import` bound to the preview; returns both results."""
    base: dict[str, Any] = {
        "input": str(path),
        "invocation_id": invocation_id or new_uuid(),
        **extra,
    }
    if fmt is not None:
        base["format"] = fmt
    if confirm:
        base["confirm_constraint_ids"] = confirm
    preview = call(transport, env.root, {**base, "action": "preview_import"})
    if preview.code != "OK":
        return preview, preview
    done = call(
        transport,
        env.root,
        {
            **base,
            "action": "import",
            "apply": True,
            "expected_digest": preview.data["digest"],
            "expected_store_revision": preview_store_revision(preview.data),
        },
    )
    return preview, done


def export_file(env: CapEnv, name: str = "cap.json", **extra: Any) -> Path:
    out, _preview, done = exported(env, name, **extra)
    assert done.code == "OK", done
    return out


def imported_rows(env: CapEnv) -> list[dict[str, Any]]:
    if not env.db.exists():
        return []
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM memory_artifacts WHERE trust_tier = 'IMPORTED' ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


def lock_acquisitions(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record `(thread name, lock id)` for every cross-process lock acquisition that
    reaches the OS primitive, in order (a nested same-id entry never reaches it)."""
    from rush.dashboard import state

    acquired: list[tuple[str, str]] = []
    original = state._acquire_cross_process_project_lock

    @contextlib.contextmanager
    def spy(project_id: str, *args: Any, **kwargs: Any) -> Iterator[None]:
        acquired.append((threading.current_thread().name, project_id))
        with original(project_id, *args, **kwargs):
            yield

    monkeypatch.setattr(state, "_acquire_cross_process_project_lock", spy)
    return acquired


def assert_denied(res: R, code: str, reason: str | None = None) -> None:
    assert res.code == code, res
    if reason is not None:
        assert res.reason == reason, res


def write_capsule_file(path: Path, capsule: dict[str, Any]) -> Path:
    """Write `capsule` as a canonical `rush_v1` file with a recomputed payload hash."""
    capsule = dict(capsule)
    capsule.pop("payload_sha256", None)
    capsule["payload_sha256"] = sha(canon(capsule))
    path.write_bytes(canon(capsule))
    return path


def mutated_capsule(raw: bytes, mutate: Any, *, rehash: bool = True) -> bytes:
    """`raw` with `mutate(capsule)` applied; the payload hash is recomputed unless
    `rehash` is false (a tampered file)."""
    capsule = json.loads(raw)
    mutate(capsule)
    if rehash:
        capsule.pop("payload_sha256", None)
        capsule["payload_sha256"] = sha(canon(capsule))
    return canon(capsule)


FIXTURES = Path(__file__).parent / "fixtures" / "memory_capsule"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def copy_fixture(name: str, dest: Path, new_name: str | None = None) -> Path:
    target = dest / (new_name or name)
    target.write_bytes(fixture_bytes(name))
    return target


def approved_mapping(
    env: CapEnv, origin: dict[str, Any], owner: OwnerScope | None = None
) -> str:
    """An approved capsule mapping for `origin` onto `env`'s project (policy CAS)."""
    from rush.memory import authorization as auth

    view = auth.approve_capsule_mapping(
        capsule_origin={
            "project_id": origin["project_id"],
            "worktree_id": origin["worktree_id"],
        },
        project_root=env.root,
        owner_scope=owner,
        expected_policy_revision=revision_of(env.data_root),
        consent=True,
        data_root=env.data_root,
    )
    return str(view["mapping_id"])


def expected_records(capsule: dict[str, Any], fmt: str) -> list[dict[str, Any]]:
    """The item 7 import records of a verified `rush_v1` capsule, computed here."""
    task = {k: v for k, v in capsule["task"].items() if k != "constraints"}
    nulls = {
        "foreign_owner": None,
        "foreign_symbol_ref": None,
        "foreign_content_hash": None,
    }
    records: list[dict[str, Any]] = [
        {
            "foreign_origin_id": "task:" + capsule["capsule_id"],
            "family": "experience",
            "subject": "episodic",
            "content": {
                "kind": "imported_task",
                "origin": capsule["origin"],
                "task": task,
            },
            "foreign_source": fmt,
            **nulls,
        }
    ]
    for item in capsule["task"]["constraints"]:
        records.append(
            {
                "foreign_origin_id": "constraint:" + item["constraint_id"],
                "family": "memory",
                "subject": "domain_knowledge",
                "content": {
                    "kind": "constraint",
                    "constraint_id": item["constraint_id"],
                    "text": item["text"],
                    "origin_ref": item["origin_ref"],
                },
                "foreign_source": fmt,
                **nulls,
            }
        )
    for entry in capsule["evidence"]:
        records.append(
            {
                "foreign_origin_id": f"evidence:{entry['artifact_id']}@{entry['version']}",
                "family": SUBJECT_FAMILY[entry["subject"]],
                "subject": entry["subject"],
                "content": entry["body"],
                "foreign_source": entry["source"],
                "foreign_owner": entry["owner"],
                "foreign_symbol_ref": entry["symbol_ref"],
                "foreign_content_hash": entry["content_hash"],
            }
        )
    return records


def record_view(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each preview record reduced to the item 7 keys."""
    return [{k: r[k] for k in RECORD_KEYS} for r in records]


def mutation_receipt_count(env: CapEnv) -> int:
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM mutation_receipts").fetchone()[0])


# --- the zero-effects oracle checks itself ---------------------------------------


def _oracle_state(env: CapEnv) -> str:
    return json.dumps(env.effects(), sort_keys=True, default=str)


def assert_preservation_oracle_complete(tmp_path: Path) -> None:
    """`CapEnv.effects` is the oracle of every zero-effects assertion. Mutate each
    state component it must capture, alone and inside an isolated fixture, and
    require the snapshot to differ before any unchanged-snapshot assertion relies on
    it: database bytes, sidecar bytes, file names, file types, symlink targets,
    policy bytes, data-root files, files beside the project and the Git index."""
    env = make_env(tmp_path / "oracle", files={"src_mod.py": KNOWN_SRC})
    sidecar = Path(str(env.exports / "o.json") + ".rush-manifest.json")
    index = env.root / ".git" / "index"
    baseline = _oracle_state(env)
    assert _oracle_state(env) == baseline, "the oracle is deterministic"
    captured = env.effects()["tree"]
    assert any(k.endswith("/.git/index") for k in captured), (
        "the Git index bytes are captured evidence"
    )
    assert any(k.endswith("/.rush/memory.db") for k in captured)

    def differs(label: str, mutate: Any, revert: Any, base: str | None = None) -> None:
        reference = baseline if base is None else base
        mutate()
        changed = _oracle_state(env)
        revert()
        assert changed != reference, f"{label}: the oracle did not see the change"
        assert _oracle_state(env) == reference, f"{label}: revert"

    original_db = env.db.read_bytes()
    differs(
        "database bytes",
        lambda: raw_sql(env, "UPDATE memory_artifacts SET source = 'oracle' WHERE 1"),
        lambda: env.db.write_bytes(original_db),
    )
    differs(
        "sidecar created",
        lambda: sidecar.write_bytes(b"one"),
        lambda: sidecar.unlink(),
    )
    sidecar.write_bytes(b"one")
    with_sidecar = _oracle_state(env)
    differs(
        "sidecar bytes",
        lambda: sidecar.write_bytes(b"two"),
        lambda: sidecar.write_bytes(b"one"),
        with_sidecar,
    )
    sidecar.unlink()
    named = env.exports / "named.json"
    named.write_bytes(b"x")
    renamed = env.exports / "renamed.json"
    with_named = _oracle_state(env)
    differs(
        "file name",
        lambda: named.rename(renamed),
        lambda: renamed.rename(named),
        with_named,
    )

    def as_directory() -> None:
        named.unlink()
        named.mkdir()

    def as_file() -> None:
        named.rmdir()
        named.write_bytes(b"x")

    differs("file type", as_directory, as_file, with_named)
    if sys.platform != "win32":
        target_a = env.exports / "target-a.json"
        target_b = env.exports / "target-b.json"
        target_a.write_bytes(b"same bytes")
        target_b.write_bytes(b"same bytes")
        with_file = _oracle_state(env)

        def as_link() -> None:
            named.unlink()
            named.symlink_to(target_a)

        def back_to_file() -> None:
            named.unlink()
            named.write_bytes(b"x")

        differs("symlink in place of a file", as_link, back_to_file, with_file)
        named.unlink()
        named.symlink_to(target_a)
        with_link = _oracle_state(env)

        def retarget() -> None:
            named.unlink()
            named.symlink_to(target_b)

        def retarget_back() -> None:
            named.unlink()
            named.symlink_to(target_a)

        differs("symlink target", retarget, retarget_back, with_link)
        named.unlink()
        named.write_bytes(b"x")
        target_a.unlink()
        target_b.unlink()
    named.unlink()
    assert _oracle_state(env) == baseline, "the fixture is back at its baseline"
    from rush.memory import authorization as auth

    policy = auth.policy_path(data_root=env.data_root)
    original_policy = policy.read_bytes()
    differs(
        "policy bytes",
        lambda: policy.write_bytes(original_policy + b" "),
        lambda: policy.write_bytes(original_policy),
    )
    stray = env.data_root / "stray.txt"
    differs("data-root file", lambda: stray.write_bytes(b"x"), lambda: stray.unlink())
    beside = env.outside / "beside.txt"
    differs("file beside the project", lambda: beside.write_bytes(b"x"), beside.unlink)
    original_index = index.read_bytes()
    differs(
        "git index bytes",
        lambda: subprocess.run(
            ["git", "update-index", "--index-version", "4"],
            cwd=env.root,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ),
        lambda: index.write_bytes(original_index),
    )
    tracked = env.root / "src_mod.py"
    original_tracked = tracked.read_bytes()
    differs(
        "tracked file bytes",
        lambda: tracked.write_bytes(original_tracked + b"# edit\n"),
        lambda: tracked.write_bytes(original_tracked),
    )


# =============================================================================
# R5/R6: export content
# =============================================================================


def test_rush_capsule_offline_required_bodies_and_hashes(tmp_path: Path) -> None:
    env = make_env(tmp_path, seed=False, files={"src_mod.py": KNOWN_SRC})
    put_evidence(env, "ev1")
    put_evidence(env, "ev2")
    put_anchored_evidence(env, "ev3")
    put_checkpoint(
        env,
        "cp1",
        created_at=time.time() - 50,
        evidence_refs=[
            {"artifact_id": "ev1", "version": 1},
            {"artifact_id": "ev2", "version": 1},
            {"artifact_id": "ev3", "version": 1},
        ],
    )
    out, preview, done = exported(env)
    assert preview.code == "OK", preview
    assert done.code == "OK", done
    raw = out.read_bytes()
    capsule = verify_rush_v1(raw)
    assert set(capsule) == CAPSULE_KEYS
    assert capsule["schema_version"] == 1 and capsule["format"] == "rush_v1"
    assert UUID_RE.match(capsule["capsule_id"])
    assert isinstance(capsule["created_at"], float)
    assert done.data["payload_sha256"] == capsule["payload_sha256"]
    assert done.data["capsule_id"] == capsule["capsule_id"]
    assert done.data["bytes"] == len(raw)

    cp_content_stored = json.loads(row_of(env, "cp1")["content"])
    assert set(capsule["origin"]) == ORIGIN_KEYS
    assert capsule["origin"]["project_id"] == env.project_id
    assert capsule["origin"]["worktree_id"] == env.worktree_id
    assert capsule["origin"]["git"] == {
        "commit": COMMIT,
        "branch": "main",
        "dirty": False,
    }
    assert capsule["origin"]["store_revision"] == store_revision(env.db)
    assert set(capsule["scope"]) == SCOPE_KEYS
    assert capsule["scope"]["owner"] == owner_hex(ALICE)
    assert capsule["scope"]["sources"] == sorted([SRC, IMPORT_SRC])
    assert capsule["scope"]["personal_owner"] is None

    assert set(capsule["task"]) == TASK_KEYS
    assert capsule["task"] == expected_task(cp_content_stored)
    assert capsule["task"]["last_verified_checkpoint"]["command"] == [
        "pytest",
        "-q",
        "tests/x.py",
    ], "the LAST passing check is exported"

    assert [e["artifact_id"] for e in capsule["evidence"]] == ["ev1", "ev2", "ev3"]
    for entry in capsule["evidence"]:
        assert set(entry) == EVIDENCE_KEYS
        assert HEX64.match(entry["owner"]["id"])
        assert entry["body_sha256"] == sha(canon(entry["body"]))
    assert capsule["evidence"][0] == expected_evidence(env, "ev1", "not_applicable")
    assert capsule["evidence"][1] == expected_evidence(env, "ev2", "not_applicable")
    anchored = capsule["evidence"][2]
    assert anchored == expected_evidence(env, "ev3", "current")
    assert anchored["symbol_ref"] == "src_mod.py::Known"
    assert anchored["source_path"] == "src_mod.py"
    assert anchored["source_revision"] == COMMIT

    manifest = capsule["manifest"]
    assert set(manifest) == MANIFEST_KEYS
    assert manifest["selected"] == [
        {"artifact_id": "cp1", "version": 1},
        {"artifact_id": "ev1", "version": 1},
        {"artifact_id": "ev2", "version": 1},
        {"artifact_id": "ev3", "version": 1},
    ]
    assert manifest["omitted"] == [] and manifest["redactions"] == []
    assert manifest["local_only_refs"] == []
    assert manifest["omitted_bytes"] == 0 and manifest["omitted_tokens"] == 0
    assert manifest["required_body_coverage"] == "complete"
    assert manifest["encoding"] == "cl100k_base"
    assert manifest["source_paths"] == ["src_mod.py"]
    assert manifest["mapping_requirement"] == (
        "origin_pair_mismatch_requires_local_approval"
    )
    evidence_bytes = canon(capsule["evidence"])
    assert manifest["evidence_bytes"] == len(evidence_bytes)
    assert manifest["evidence_tokens"] == token_count(evidence_bytes.decode("utf-8"))
    assert set(manifest["export_effect"]) == EXPORT_EFFECT_KEYS

    # The file is self-contained: no absolute path, data root, grant id or project
    # root of the origin machine, and unicode is written as UTF-8, not escapes.
    text = raw.decode("utf-8")
    for needle in (
        str(env.root),
        str(env.data_root),
        str(tmp_path),
        str(default_data_root()),
        env.grant["grant_id"] if env.grant else "",
    ):
        assert needle and needle not in text, needle
    assert "Ünïcode ✓".encode() in raw
    assert "\\u00dc" not in text

    # Offline: with the origin store gone, the capsule alone still carries the next
    # action, every constraint and every evidence body.
    import shutil

    shutil.rmtree(env.root / ".rush")
    offline = json.loads(raw)
    assert offline["task"]["next_action"] == cp_content_stored["next_action"]
    assert [c["text"] for c in offline["task"]["constraints"]] == [
        q["text"] for q in cp_content_stored["requirements"]
    ]
    assert [e["body"] for e in offline["evidence"][:2]] == [
        evidence_body("ev1"),
        evidence_body("ev2"),
    ]


def test_tiny_budget_rejects_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import capsule

    monkeypatch.setattr(capsule, "_now", lambda: 1_760_000_000.5)
    env = make_env(tmp_path)
    before = env.effects()
    required: dict[str, Any] = {}
    for transport in TRANSPORTS:
        out = out_for(env, transport, "tiny.json")
        for limits in ({"max_bytes": 100}, {"max_tokens": 10}):
            res = call(
                transport,
                env.root,
                {
                    "action": "preview_export",
                    "output": str(out),
                    "invocation_id": new_uuid(),
                    **limits,
                },
            )
            assert res.code == "E_INPUT", (transport, limits, res)
            assert res.data["admission_failure"] is True
            required = res.data["required"]
            assert set(required) == {"bytes", "tokens"}
            assert isinstance(required["bytes"], int) and required["bytes"] > 0
            assert isinstance(required["tokens"], int) and required["tokens"] > 0
            assert res.data["limits"] == {
                "max_bytes": limits.get("max_bytes", 65536),
                "max_tokens": limits.get("max_tokens", 8192),
            }
            assert required["bytes"] > limits.get("max_bytes", 0) or required[
                "tokens"
            ] > limits.get("max_tokens", 0)
            assert not out.exists()
    assert env.effects() == before

    # Raising the limits to `required` (an explicit new request) then succeeds.
    out = env.outside / "ok.json"
    base = {
        "output": str(out),
        "invocation_id": new_uuid(),
        "max_bytes": required["bytes"],
        "max_tokens": required["tokens"],
    }
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    assert preview.code == "E_BUDGET", preview
    assert preview.data["admission_failure"] is False
    base.update(
        max_bytes=preview.data["required"]["bytes"],
        max_tokens=preview.data["required"]["tokens"],
    )
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    assert preview.code == "OK", preview
    done = call_inproc(
        env.root,
        {**base, "action": "export", "expected_digest": preview.data["digest"]},
    )
    assert done.code == "OK", done
    assert len(out.read_bytes()) <= base["max_bytes"]


def test_secret_or_private_required_body_rejects(tmp_path: Path) -> None:
    secret = "ghp_" + "a" * 36
    env = make_env(tmp_path)
    base = {
        "output": str(env.outside / "secret.json"),
        "invocation_id": new_uuid(),
    }
    clean = call_inproc(env.root, {**base, "action": "preview_export"})
    assert clean.code == "OK", clean

    for target, content in (
        ("ev1", {"note": f"token {secret}"}),
        (
            "cp1",
            cp_content(
                env, event_id="ev-cp1", next_action=f"use token {secret} to deploy"
            ),
        ),
    ):
        plant_content(env, target, content)
        db_before = sha(env.db.read_bytes())
        tree_before = env.effects()
        preview = call_inproc(env.root, {**base, "action": "preview_export"})
        assert_denied(preview, "E_PERMISSION", "export_blocked")
        assert "digest" not in preview.data, "no digest is issued for a blocked export"
        done = call_inproc(
            env.root,
            {**base, "action": "export", "expected_digest": clean.data["digest"]},
        )
        assert_denied(done, "E_PERMISSION", "export_blocked")
        assert not (env.outside / "secret.json").exists()
        assert sha(env.db.read_bytes()) == db_before
        assert env.effects() == tree_before
        assert secret not in json.dumps(done.raw) + json.dumps(preview.raw)
        # restore a clean body for the next case
        if target == "ev1":
            plant_content(env, "ev1", evidence_body("ev1"))

    # Control on a clean store: a round trip keeps body_sha256 == sha256(stored
    # content) and preview_import / import succeed.
    clean_env = make_env(tmp_path, name="clean")
    out, _preview, done = exported(clean_env, "clean.json")
    assert done.code == "OK", done
    capsule = verify_rush_v1(out.read_bytes())
    for entry in capsule["evidence"]:
        stored = json.loads(row_of(clean_env, entry["artifact_id"])["content"])
        assert entry["body_sha256"] == sha(canon(stored))
    preview_i, done_i = imported(clean_env, out)
    assert preview_i.code == "OK", preview_i
    assert done_i.code == "OK", done_i


def test_export_bytes_equal_hashed_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.io import atomic_file

    seen: list[tuple[str, bytes, int]] = []
    original = atomic_file.AtomicFile.write_bytes

    def spy(self: Any, name: str, sanitized: Any, *args: Any, **kwargs: Any) -> Any:
        seen.append((name, bytes(sanitized.data), sanitized.redaction_count))
        return original(self, name, sanitized, *args, **kwargs)

    # setup commits the policy through write_bytes: not counted
    env = make_env(tmp_path)
    monkeypatch.setattr(atomic_file.AtomicFile, "write_bytes", spy)
    out, _preview, done = exported(env)
    assert done.code == "OK", done
    raw = out.read_bytes()
    assert [s[0] for s in seen] == [out.name]
    assert seen[0][1] == raw, "the written bytes equal the sanitizer-checked bytes"
    assert seen[0][2] == 0
    capsule = json.loads(raw)
    assert raw == canon(capsule)
    without = {k: v for k, v in capsule.items() if k != "payload_sha256"}
    assert sha(canon(without)) == capsule["payload_sha256"]
    assert done.data["bytes"] == len(raw)
    assert stat.S_IFMT(out.stat().st_mode) == stat.S_IFREG
    # no temp file is left behind next to the output
    assert sorted(p.name for p in out.parent.iterdir()) == [out.name]

    # Hashed, sanitized and published bytes must be one view: a sanitizer result that
    # differs from the bytes the capsule hashed is never published.
    real_from_bytes = atomic_file.SanitizedBytes.from_bytes

    def altered(data: bytes, *args: Any, **kwargs: Any) -> Any:
        return real_from_bytes(data + b" ", *args, **kwargs)

    stale_out = env.exports / "stale-view.json"
    base = {"output": str(stale_out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    assert preview.code == "OK", preview
    before = env.effects()
    with monkeypatch.context() as scoped:
        scoped.setattr(atomic_file.SanitizedBytes, "from_bytes", staticmethod(altered))
        res = call_inproc(
            env.root,
            {**base, "action": "export", "expected_digest": preview.data["digest"]},
        )
    assert_denied(res, "E_PERMISSION", "export_blocked")
    assert not stale_out.exists() and env.effects() == before
    assert sorted(p.name for p in out.parent.iterdir()) == [out.name]


def test_explicit_budget_increase_and_hard_caps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import capsule

    monkeypatch.setattr(capsule, "_now", lambda: 1_760_000_000.5)
    env = make_env(tmp_path)
    before = env.effects()
    out = env.outside / "cap.json"

    def preview(**limits: Any) -> R:
        return call_inproc(
            env.root,
            {
                "action": "preview_export",
                "output": str(out),
                "invocation_id": new_uuid(),
                **limits,
            },
            cache=False,
        )

    # Invalid request values (not budgets): zero, negative, bool, string, float.
    for field in ("max_bytes", "max_tokens"):
        for bad in (0, -1, True, "10", 1.5):
            res = preview(**{field: bad})
            assert res.code == "E_INPUT", (field, bad, res)
            assert res.reason != "budget_above_hard_cap", (field, bad)
    # A requested value above the hard cap: budget_above_hard_cap.
    for field, over in (
        ("max_bytes", 1048577),
        ("max_tokens", 131073),
        ("max_bytes", 10**400),
        ("max_tokens", 10**400),
    ):
        res = preview(**{field: over})
        assert res.code == "E_INPUT", (field, over, res)
        assert res.reason == "budget_above_hard_cap", (field, over, res)
    # The caps themselves are accepted values.
    assert preview(max_bytes=1048576, max_tokens=131072).code == "OK"
    # Content above the request limits: E_BUDGET with `required`; the limit never
    # rises on its own, and an explicit larger request succeeds.
    below = preview(max_bytes=1)
    assert below.code == "E_INPUT" and below.data["admission_failure"] is True
    minimum = below.data["required"]["bytes"]
    small = preview(max_bytes=minimum)
    assert small.code == "E_BUDGET", small
    assert small.data["limits"]["max_bytes"] == minimum
    need = small.data["required"]["bytes"]
    assert need > minimum
    assert preview(max_bytes=need - 1).code == "E_BUDGET"
    assert preview(max_bytes=need).code == "OK"
    assert not out.exists()
    assert env.effects() == before

    # Content above the hard cap: E_BUDGET even at the highest allowed limits.
    big = make_env(tmp_path, name="big", seed=False)
    put_checkpoint(
        big,
        "cp1",
        created_at=time.time() - 10,
        evidence_refs=[{"artifact_id": "huge", "version": 1}],
    )
    put_evidence(big, "huge", body={"text": "x" * 1_100_000})
    huge = call_inproc(
        big.root,
        {
            "action": "preview_export",
            "output": str(big.outside / "huge.json"),
            "invocation_id": new_uuid(),
            "max_bytes": 1048576,
            "max_tokens": 131072,
        },
    )
    assert huge.code == "E_BUDGET", huge
    assert huge.data["required"]["bytes"] > 1048576
    assert not (big.outside / "huge.json").exists()

    # An import input above the hard cap is E_BUDGET before any effect.
    path = env.outside / "toobig.json"
    path.write_bytes(b"{" + b" " * 1_100_000 + b"}")
    over_cap = call_inproc(
        env.root,
        {"action": "preview_import", "input": str(path), "invocation_id": new_uuid()},
    )
    assert over_cap.code == "E_BUDGET", over_cap
    assert over_cap.data["required"]["bytes"] > 1048576


# =============================================================================
# R4/R6/R2: strict parsing, digests and compare-and-set
# =============================================================================


def _byte_variants(raw: bytes) -> dict[str, bytes]:
    """Hostile or corrupt capsule bytes derived from a valid export `raw`."""
    nested: Any = "leaf"
    for _ in range(17):
        nested = [nested]

    def with_entry(c: dict[str, Any]) -> None:
        extra = dict(c["evidence"][0])
        extra["artifact_id"] = "overflow"
        c["evidence"] = [dict(extra, artifact_id=f"e{i}") for i in range(129)]

    def deep(c: dict[str, Any]) -> None:
        c["evidence"][0]["body"] = {"deep": nested}
        c["evidence"][0]["body_sha256"] = sha(canon(c["evidence"][0]["body"]))

    def item_hash(c: dict[str, Any]) -> None:
        c["evidence"][0]["body_sha256"] = "0" * 64

    variants: dict[str, bytes] = {}

    def mut(name: str, fn: Any, *, rehash: bool = True) -> None:
        variants[name] = mutated_capsule(raw, fn, rehash=rehash)

    mut("schema_version_2", lambda c: c.__setitem__("schema_version", 2))
    mut("schema_version_true", lambda c: c.__setitem__("schema_version", True))
    mut("format_rush_v2", lambda c: c.__setitem__("format", "rush_v2"))
    mut("unknown_top_key", lambda c: c.__setitem__("extra", 1))
    mut("missing_task", lambda c: c.pop("task"))
    mut("unknown_task_key", lambda c: c["task"].__setitem__("zzz", 1))
    mut("missing_manifest_key", lambda c: c["manifest"].pop("selected"))
    mut("unknown_origin_key", lambda c: c["origin"].__setitem__("zzz", 1))
    mut("capsule_id_not_uuid", lambda c: c.__setitem__("capsule_id", "not-a-uuid"))
    mut("capsule_id_int", lambda c: c.__setitem__("capsule_id", 7))
    mut("created_at_true", lambda c: c.__setitem__("created_at", True))
    mut("created_at_string", lambda c: c.__setitem__("created_at", "1.0"))
    mut("created_at_huge_int", lambda c: c.__setitem__("created_at", 10**400))
    mut("evidence_item_hash_mismatch", item_hash)
    mut("evidence_over_128", with_entry)
    mut("body_deeper_than_16", deep)
    mut(
        "tampered_payload_hash",
        lambda c: c["task"].__setitem__("description", "x"),
        rehash=False,
    )
    mut(
        "tampered_payload_field",
        lambda c: c.__setitem__("payload_sha256", "0" * 64),
        rehash=False,
    )
    text = raw.decode("utf-8")
    variants["duplicate_key"] = raw[:-1] + b',"format":"rush_v1"}'
    variants["bom"] = b"\xef\xbb\xbf" + raw
    variants["non_utf8"] = raw[:20] + b"\xff\xfe" + raw[20:]
    variants["nan_token"] = raw.replace(
        b'"store_revision":', b'"zz":NaN,"store_revision":'
    )
    variants["infinity_token"] = raw.replace(
        b'"store_revision":', b'"zz":Infinity,"store_revision":'
    )
    variants["lone_surrogate"] = text.replace(
        '"description":"Portable capsule work"', '"description":"\\ud800"'
    ).encode("utf-8")
    variants["nul_in_id"] = text.replace(
        '"project_id":"', '"project_id":"\\u0000'
    ).encode("utf-8")
    variants["top_level_array"] = b"[]"
    variants["top_level_string"] = b'"capsule"'
    variants["empty"] = b""
    variants["trailing_garbage"] = raw + b"x"
    return variants


def test_unknown_schema_duplicate_key_and_tamper_rejected(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    good = export_file(env, "good.json")
    raw = good.read_bytes()
    control = call_inproc(
        env.root,
        {"action": "preview_import", "input": str(good), "invocation_id": new_uuid()},
    )
    assert control.code == "OK", control
    before = env.effects()
    variants = _byte_variants(raw)
    assert len(variants) >= 25
    for name, data in sorted(variants.items()):
        path = env.outside / f"{name}.json"
        path.write_bytes(data)
        # `outside` holds the variants themselves; compare the rest of the state.
        res = call_inproc(
            env.root,
            {
                "action": "preview_import",
                "input": str(path),
                "invocation_id": new_uuid(),
            },
        )
        assert res.code == "E_INPUT", (name, res)
        assert res.reason == "capsule_invalid", (name, res)
    after = env.effects()
    for key in ("db", "policy"):
        assert after[key] == before[key]
    assert {
        k: v for k, v in after["tree"].items() if not k.startswith(str(env.outside))
    } == {k: v for k, v in before["tree"].items() if not k.startswith(str(env.outside))}
    assert not imported_rows(env)
    # A tampered file is also refused on `import` (never partially applied).
    tampered = env.outside / "tampered_payload_hash.json"
    done = call_inproc(
        env.root,
        {
            "action": "import",
            "apply": True,
            "input": str(tampered),
            "invocation_id": new_uuid(),
            "expected_digest": control.data["digest"],
            "expected_store_revision": preview_store_revision(control.data),
        },
    )
    assert done.code == "E_INPUT" and done.reason == "capsule_invalid", done
    assert not imported_rows(env)


def test_preview_readonly_and_import_cas(tmp_path: Path) -> None:
    assert_preservation_oracle_complete(tmp_path)
    env = make_env(tmp_path)
    out = env.outside / "cap.json"
    invocation_id = new_uuid()
    selectors = {
        "task_ref": {"artifact_id": "cp1", "version": 1},
        "owner_scope": ALICE.as_dict(),
        "sources": [IMPORT_SRC, SRC],
        "include_personal": False,
    }
    base = {"output": str(out), "invocation_id": invocation_id, "selectors": selectors}
    before = env.effects()
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    assert preview.code == "OK", preview
    assert env.effects() == before and not out.exists(), "a preview has no effects"
    assert not (env.data_root / "dashboard" / "project_locks").exists()
    assert preview.data["invocation_id"] == invocation_id
    assert "capsule_id" not in preview.data and "created_at" not in preview.data

    digest_input = {
        "action": "export",
        "format": "rush_v1",
        "invocation_id": invocation_id,
        "selectors": {
            "include_personal": False,
            "owner_scope": {"kind": "user", "id": "alice"},
            "sources": sorted([SRC, IMPORT_SRC]),
            "task_ref": {"artifact_id": "cp1", "version": 1},
        },
        "mapping_id": None,
        "confirm_constraint_ids": [],
        "max_bytes": 65536,
        "max_tokens": 8192,
        "policy_revision": revision_of(env.data_root),
        "input_sha256": None,
        "source_store_revision": store_revision(env.db),
        "selected_ids": [["cp1", 1], ["ev1", 1], ["ev2", 1]],
        "target": {"path": str(out.resolve()), "exists": False, "sha256": None},
    }
    assert len(digest_input) == 13
    assert preview.data["digest"] == sha(canon(digest_input))
    # sources order is not a digest input; the invocation id is.
    reordered = call_inproc(
        env.root,
        {
            **base,
            "selectors": {**selectors, "sources": [SRC, IMPORT_SRC]},
            "action": "preview_export",
        },
    )
    assert reordered.data["digest"] == preview.data["digest"]
    other = call_inproc(
        env.root, {**base, "invocation_id": new_uuid(), "action": "preview_export"}
    )
    assert other.data["digest"] != preview.data["digest"]
    omitted = call_inproc(
        env.root,
        {"action": "preview_export", "output": str(out)},
    )
    assert omitted.code == "OK" and UUID_RE.match(omitted.data["invocation_id"])

    # --- presence and compare-and-set rules (export side) ---
    o, i = str(out), str(env.outside / "in.json")
    iv = new_uuid()
    rejected: list[tuple[dict[str, Any], str | None]] = [
        ({"action": "preview_export", "invocation_id": iv}, "output"),
        ({"action": "preview_export", "output": o, "input": i}, "input"),
        (
            {"action": "export", "output": o, "expected_digest": "a" * 64},
            "invocation_id",
        ),
        ({"action": "export", "output": o, "invocation_id": iv}, "expected_digest"),
        (
            {
                "action": "export",
                "output": o,
                "invocation_id": iv,
                "expected_digest": "a" * 64,
                "apply": True,
            },
            "apply",
        ),
        (
            {
                "action": "preview_export",
                "output": o,
                "confirm_constraint_ids": ["c1"],
            },
            "confirm_constraint_ids",
        ),
        ({"action": "preview_import", "input": i, "output": o}, "output"),
        ({"action": "preview_import"}, "input"),
        ({"action": "preview_import", "input": i, "apply": True}, "apply"),
        (
            {
                "action": "preview_import",
                "input": i,
                "selectors": {"task_ref": {"artifact_id": "cp1", "version": 1}},
            },
            None,
        ),
        (
            {"action": "preview_import", "input": i, "selectors": {"sources": [SRC]}},
            None,
        ),
        (
            {
                "action": "preview_import",
                "input": i,
                "selectors": {"include_personal": True},
            },
            None,
        ),
        (
            {
                "action": "import",
                "input": i,
                "invocation_id": iv,
                "expected_digest": "a" * 64,
                "expected_store_revision": 0,
            },
            "apply",
        ),
        (
            {
                "action": "import",
                "input": i,
                "invocation_id": iv,
                "apply": True,
                "expected_store_revision": 0,
            },
            "expected_digest",
        ),
        (
            {
                "action": "import",
                "input": i,
                "invocation_id": iv,
                "apply": True,
                "expected_digest": "a" * 64,
            },
            "expected_store_revision",
        ),
        (
            {
                "action": "import",
                "input": i,
                "apply": True,
                "expected_digest": "a" * 64,
                "expected_store_revision": 0,
            },
            "invocation_id",
        ),
    ]
    for request, field in rejected:
        res = call_inproc(env.root, request)
        assert res.code == "E_INPUT", (request, res)
        if field is not None:
            assert res.field == field, (request, res)
    for name in ("x.rush-manifest.json", "x.rush-journal.json"):
        res = call_inproc(
            env.root,
            {
                "action": "preview_export",
                "output": str(env.outside / name),
                "invocation_id": iv,
            },
        )
        assert res.code == "E_INPUT" and res.reason == "capsule_invalid", res
    assert env.effects() == before

    mismatch = call_inproc(
        env.root,
        {**base, "action": "export", "expected_digest": "f" * 64},
    )
    assert_denied(mismatch, "E_VERSION", "recovery_required")
    assert not out.exists() and env.effects() == before

    # --- import side: exact new records, digest and store-revision CAS ---
    cap = export_file(env, "i.json")
    inv_i = new_uuid()
    base_i = {"input": str(cap), "invocation_id": inv_i}
    before_i = env.effects()
    prev_i = call_inproc(env.root, {**base_i, "action": "preview_import"})
    assert prev_i.code == "OK", prev_i
    assert preview_store_state(prev_i.data) == "current"
    assert env.effects() == before_i, "preview_import writes nothing"
    revision = preview_store_revision(prev_i.data)
    assert revision == store_revision(env.db)
    apply_base = {**base_i, "action": "import", "apply": True}
    wrong_digest = call_inproc(
        env.root,
        {
            **apply_base,
            "expected_digest": "e" * 64,
            "expected_store_revision": revision,
        },
    )
    assert_denied(wrong_digest, "E_VERSION", "recovery_required")
    wrong_revision = call_inproc(
        env.root,
        {
            **apply_base,
            "expected_digest": prev_i.data["digest"],
            "expected_store_revision": revision + 1,
        },
    )
    assert_denied(wrong_revision, "E_VERSION", "store_changed")
    assert env.effects() == before_i and not imported_rows(env)
    ok = call_inproc(
        env.root,
        {
            **apply_base,
            "expected_digest": prev_i.data["digest"],
            "expected_store_revision": revision,
        },
    )
    assert ok.code == "OK", ok
    rows = imported_rows(env)
    assert len(rows) == 5, "1 task + 2 constraints + 2 evidence"
    assert [m["foreign_origin_id"] for m in ok.data["mappings"]] == [
        r["foreign_origin_id"] for r in prev_i.data["records"]
    ]
    for row in rows:
        assert row["trust_tier"] == "IMPORTED" and row["source"] == IMPORT_SRC
        assert json.loads(row["content"])["authority"] == "imported_unverified"


def test_import_record_mapping_exact(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    capsule_fx = json.loads(fixture_bytes("rush_v1_two_constraints_two_evidence.json"))
    mapping_id = approved_mapping(env, capsule_fx["origin"])

    # --- rush_v1: 2 constraints, 2 evidence entries ---
    path = copy_fixture("rush_v1_two_constraints_two_evidence.json", env.outside)
    for transport in ("inproc", "cli"):
        res = call(
            transport,
            env.root,
            {
                "action": "preview_import",
                "input": str(path),
                "mapping_id": mapping_id,
                "invocation_id": new_uuid(),
            },
        )
        assert res.code == "OK", (transport, res)
        assert record_view(res.data["records"]) == expected_records(
            capsule_fx, "rush_v1"
        ), transport
        assert [r["foreign_origin_id"] for r in res.data["records"]] == [
            "task:7f1c2d3e-4b5a-4c6d-8e7f-0a1b2c3d4e5f",
            "constraint:c1",
            "constraint:c2",
            "evidence:ev-a@1",
            "evidence:ev-b@1",
        ]
        assert res.data["capsule_digest"] == capsule_fx["payload_sha256"]
        assert res.data["origin_match"] == "mapped"
        assert isinstance(res.data["redactions"], list)

    # --- pas_v1 pair: the sidecar's verified rush_v1 capsule is imported ---
    pas_dir = env.outside / "pair"
    pas_dir.mkdir()
    pas_path = copy_fixture("pas_session_schema1.json", pas_dir)
    copy_fixture("pas_session_schema1.json.rush-manifest.json", pas_dir)
    sidecar = json.loads(fixture_bytes("pas_session_schema1.json.rush-manifest.json"))
    pair = call_inproc(
        env.root,
        {
            "action": "preview_import",
            "format": "pas_v1",
            "input": str(pas_path),
            "mapping_id": mapping_id,
            "invocation_id": new_uuid(),
        },
    )
    assert pair.code == "OK", pair
    assert record_view(pair.data["records"]) == expected_records(
        sidecar["capsule"], "pas_v1"
    )
    assert pair.data["capsule_digest"] == sidecar["capsule"]["payload_sha256"]

    # --- standalone pas_v1 file (no sidecar): limited unverified task claims ---
    solo_dir = env.outside / "solo"
    solo_dir.mkdir()
    solo = copy_fixture("pas_session_schema1.json", solo_dir)
    pas_bytes = fixture_bytes("pas_session_schema1.json")
    session = json.loads(pas_bytes)
    alone = call_inproc(
        env.root,
        {
            "action": "preview_import",
            "format": "pas_v1",
            "input": str(solo),
            "invocation_id": new_uuid(),
        },
    )
    assert alone.code == "OK", alone
    assert alone.data["origin_match"] == "absent"
    assert alone.data["capsule_digest"] == sha(pas_bytes)
    records = alone.data["records"]
    assert records[0]["foreign_origin_id"] == "task:" + session["id"]
    assert records[0]["family"] == "experience" and records[0]["subject"] == "episodic"
    assert records[0]["foreign_source"] == "pas_v1"
    assert records[0]["content"]["kind"] == "imported_task"
    assert records[0]["content"]["origin"] == {
        "pas_session_id": session["id"],
        "project_name": session["project_name"],
    }
    assert records[0]["foreign_owner"] is None
    constraint_records = records[1:]
    assert [r["content"]["text"] for r in constraint_records] == session["task"][
        "constraints"
    ]
    ids = [r["content"]["constraint_id"] for r in constraint_records]
    assert len(set(ids)) == len(ids) and all(HEX64.match(i) for i in ids)
    assert [r["content"]["origin_ref"] for r in constraint_records] == [
        f"/task/constraints/{n}" for n in range(len(ids))
    ]
    assert all(
        r["foreign_origin_id"] == "constraint:" + r["content"]["constraint_id"]
        for r in constraint_records
    )
    again = call_inproc(
        env.root,
        {
            "action": "preview_import",
            "format": "pas_v1",
            "input": str(solo),
            "invocation_id": new_uuid(),
        },
    )
    assert [r["content"]["constraint_id"] for r in again.data["records"][1:]] == ids


def test_capsule_preview_apply_stable_across_clock_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import capsule

    clock = {"now": 1_760_000_000.5}
    monkeypatch.setattr(capsule, "_now", lambda: clock["now"])
    env = make_env(tmp_path)

    # export: preview at T0, export a day later against the same preview digest
    out = env.outside / "cap.json"
    base = {"output": str(out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    clock["now"] += 86400.0
    done = call_inproc(
        env.root,
        {**base, "action": "export", "expected_digest": preview.data["digest"]},
    )
    assert done.code == "OK", done
    capsule_doc = verify_rush_v1(out.read_bytes())
    assert capsule_doc["created_at"] == clock["now"] == done.data["created_at"]
    assert UUID_RE.match(capsule_doc["capsule_id"])

    # import: preview at T1, apply a day later against the same preview digest
    inv = new_uuid()
    base_i = {"input": str(out), "invocation_id": inv}
    prev_i = call_inproc(env.root, {**base_i, "action": "preview_import"})
    clock["now"] += 86400.0
    done_i = call_inproc(
        env.root,
        {
            **base_i,
            "action": "import",
            "apply": True,
            "expected_digest": prev_i.data["digest"],
            "expected_store_revision": preview_store_revision(prev_i.data),
        },
    )
    assert done_i.code == "OK", done_i

    # changed selectors, store revision or target pre-state between preview and
    # export: E_VERSION recovery_required and no output.
    def stale_case(
        name: str, mutate: Any, changed: dict[str, Any] | None = None
    ) -> None:
        target = env.outside / f"{name}.json"
        shared = {"output": str(target), "invocation_id": new_uuid()}
        first = call_inproc(env.root, {**shared, "action": "preview_export"})
        assert first.code == "OK", first
        mutate(target)
        before = target.read_bytes() if target.exists() else None
        res = call_inproc(
            env.root,
            {
                **shared,
                **(changed or {}),
                "action": "export",
                "expected_digest": first.data["digest"],
            },
        )
        assert_denied(res, "E_VERSION", "recovery_required")
        if before is None:
            assert not target.exists(), name
        else:
            assert target.read_bytes() == before, name

    stale_case("selectors", lambda t: None, {"selectors": {"sources": [SRC]}})
    stale_case(
        "store_revision",
        lambda t: put_evidence(env, f"late-{time.time_ns()}"),
    )
    stale_case("target_created", lambda t: t.write_bytes(b"{}"))


@pytest.mark.parametrize(
    "fmt",
    [pytest.param("rush_v1", id="rush_v1"), pytest.param("pas_v1", id="pas_v1")],
)
@pytest.mark.parametrize(
    "transport", [pytest.param("mcp", id="mcp"), pytest.param("cli", id="cli")]
)
def test_retry_same_invocation_is_idempotent(
    transport: str, fmt: str, tmp_path: Path
) -> None:
    env = make_env(tmp_path)
    out = out_for(env, transport, "retry.json")
    inv = new_uuid()
    base = {"format": fmt, "output": str(out), "invocation_id": inv}
    preview = call(transport, env.root, {**base, "action": "preview_export"})
    assert preview.code == "OK", preview
    export_req = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    first = call(transport, env.root, export_req)
    assert first.code == "OK", first
    files = [out] + (
        [Path(str(out) + ".rush-manifest.json")] if fmt == "pas_v1" else []
    )
    snapshot = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    second = call(transport, env.root, export_req)
    assert second.code == "OK", second
    assert second.data["replayed"] is True
    for key in (
        "effect_id",
        "capsule_id",
        "created_at",
        "payload_sha256",
        "bytes",
        "invocation_id",
        "format",
    ):
        assert second.data[key] == first.data[key], key
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == snapshot

    # import: the same invocation, action and target replay the original receipt
    in_base = {"format": fmt, "input": str(out), "invocation_id": new_uuid()}
    prev_i = call(transport, env.root, {**in_base, "action": "preview_import"})
    assert prev_i.code == "OK", prev_i
    import_req = {
        **in_base,
        "action": "import",
        "apply": True,
        "expected_digest": prev_i.data["digest"],
        "expected_store_revision": preview_store_revision(prev_i.data),
    }
    one = call(transport, env.root, import_req)
    assert one.code == "OK", one
    rows_after_first = imported_rows(env)
    assert len(rows_after_first) == 5
    two = call(transport, env.root, import_req)
    assert two.code == "OK", two
    assert two.data["replayed"] is True
    assert two.data["effect_id"] == one.data["effect_id"]
    assert two.data["mappings"] == one.data["mappings"]
    assert imported_rows(env) == rows_after_first, "one durable effect"


@pytest.mark.parametrize(
    "fmt",
    [pytest.param("rush_v1", id="rush_v1"), pytest.param("pas_v1", id="pas_v1")],
)
@pytest.mark.parametrize(
    "transport", [pytest.param("mcp", id="mcp"), pytest.param("cli", id="cli")]
)
def test_export_lost_response_replay(
    transport: str, fmt: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import capsule

    env = make_env(tmp_path)
    out = out_for(env, transport, "lost.json")
    base = {"format": fmt, "output": str(out), "invocation_id": new_uuid()}
    preview = call(transport, env.root, {**base, "action": "preview_export"})
    request = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    first = call(transport, env.root, request)
    assert first.code == "OK", first
    files = [out] + (
        [Path(str(out) + ".rush-manifest.json")] if fmt == "pas_v1" else []
    )
    stamps = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
    db_sha, receipts = sha(env.db.read_bytes()), mutation_receipt_count(env)

    calls = {"now": 0, "uuid": 0}
    real_now, real_uuid = capsule._now, capsule._new_uuid

    def counted_now() -> float:
        calls["now"] += 1
        return real_now()

    def counted_uuid() -> str:
        calls["uuid"] += 1
        return real_uuid()

    monkeypatch.setattr(capsule, "_now", counted_now)
    monkeypatch.setattr(capsule, "_new_uuid", counted_uuid)
    retry = call(transport, env.root, request)
    assert retry.code == "OK", retry
    assert retry.data["replayed"] is True
    for key in ("capsule_id", "created_at", "payload_sha256", "bytes"):
        assert retry.data[key] == first.data[key], key
    assert calls == {"now": 0, "uuid": 0}, "a replay generates nothing"
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == stamps
    assert sha(env.db.read_bytes()) == db_sha
    assert mutation_receipt_count(env) == receipts

    # A new invocation id is not a replay.
    fresh_base = {**base, "invocation_id": new_uuid()}
    fresh_preview = call(
        transport, env.root, {**fresh_base, "action": "preview_export"}
    )
    if transport == "mcp":
        # MCP exports only to an absent target: the published capsule is refused.
        assert_denied(fresh_preview, "E_PERMISSION", "export_target_refused")
    else:
        assert fresh_preview.code == "OK", fresh_preview
        fresh = call(
            transport,
            env.root,
            {
                **fresh_base,
                "action": "export",
                "expected_digest": fresh_preview.data["digest"],
            },
        )
        assert fresh.code == "OK" and fresh.data.get("replayed") is not True
        assert fresh.data["capsule_id"] != first.data["capsule_id"]


def test_export_replay_changed_request_conflicts(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    out = env.exports / "conflict.json"
    base = {"output": str(out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    request = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    assert call_inproc(env.root, request).code == "OK"
    stamp = (out.read_bytes(), out.stat().st_mtime_ns)
    for changed in (
        {"max_bytes": 70000},
        {"max_tokens": 9000},
        {"selectors": {"sources": [SRC]}},
    ):
        for transport in ("inproc", "mcp"):
            res = call(transport, env.root, {**request, **changed})
            assert_denied(res, "E_VERSION", "effect_digest_conflict")
            assert (out.read_bytes(), out.stat().st_mtime_ns) == stamp, changed


def test_export_replay_edited_target_recovery_required(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    out = env.outside / "edited.json"
    base = {"output": str(out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    request = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    assert call_inproc(env.root, request).code == "OK"
    raw = bytearray(out.read_bytes())
    index = raw.index(b"Portable capsule work")
    raw[index] = ord("p")
    out.write_bytes(bytes(raw))
    edited = out.read_bytes()
    res = call_inproc(env.root, request)
    assert_denied(res, "E_VERSION", "recovery_required")
    assert out.read_bytes() == edited, "the edited bytes are kept"


def test_export_replay_revoked_grant_denied(tmp_path: Path) -> None:
    from rush.memory import authorization as auth

    env = make_env(tmp_path)
    out = env.outside / "revoked.json"
    base = {"output": str(out), "invocation_id": new_uuid()}
    preview = call_inproc(env.root, {**base, "action": "preview_export"})
    request = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    first = call_inproc(env.root, request)
    assert first.code == "OK", first
    stamp = (out.read_bytes(), out.stat().st_mtime_ns)
    auth.revoke_memory_scope(
        grant_id=(env.grant or {})["grant_id"],
        expected_policy_revision=revision_of(env.data_root),
        consent=True,
        data_root=env.data_root,
    )
    res = call_inproc(env.root, request)
    assert_denied(res, "E_PERMISSION", "revoked")
    text = json.dumps(res.raw)
    assert first.data["capsule_id"] not in text
    assert first.data["payload_sha256"] not in text
    assert (out.read_bytes(), out.stat().st_mtime_ns) == stamp


def test_import_ignores_export_effect(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    out = export_file(env, "marked.json")
    raw = out.read_bytes()
    capsule_doc = json.loads(raw)
    assert set(capsule_doc["manifest"]["export_effect"]) == EXPORT_EFFECT_KEYS
    with_marker = call_inproc(
        env.root,
        {"action": "preview_import", "input": str(out), "invocation_id": new_uuid()},
    )
    assert with_marker.code == "OK", with_marker
    assert record_view(with_marker.data["records"]) == expected_records(
        capsule_doc, "rush_v1"
    )
    assert "export_effect" not in json.dumps(with_marker.data["records"])

    bare = env.outside / "bare.json"
    bare.write_bytes(mutated_capsule(raw, lambda c: c["manifest"].pop("export_effect")))
    without = call_inproc(
        env.root,
        {"action": "preview_import", "input": str(bare), "invocation_id": new_uuid()},
    )
    assert without.code == "OK", without
    assert with_marker.data["records"] == without.data["records"]

    good = capsule_doc["manifest"]["export_effect"]
    malformed = {
        "missing_key": {k: v for k, v in good.items() if k != "effect_id"},
        "unknown_key": {**good, "extra": "x"},
        "invocation_not_uuid": {**good, "invocation_id": "nope"},
        "invocation_uppercase": {
            **good,
            "invocation_id": good["invocation_id"].upper(),
        },
        "effect_id_short": {**good, "effect_id": "ab"},
        "effect_id_uppercase": {**good, "effect_id": "A" * 64},
        "request_digest_int": {**good, "request_digest": 7},
        "not_an_object": "marker",
        "null": None,
    }
    before = env.effects()
    for name, marker in malformed.items():
        path = env.outside / f"bad-{name}.json"
        path.write_bytes(
            mutated_capsule(
                raw, lambda c, m=marker: c["manifest"].__setitem__("export_effect", m)
            )
        )
        res = call_inproc(
            env.root,
            {
                "action": "preview_import",
                "input": str(path),
                "invocation_id": new_uuid(),
            },
        )
        assert res.code == "E_INPUT" and res.reason == "capsule_invalid", (name, res)
    after = env.effects()
    assert after["db"] == before["db"] and after["policy"] == before["policy"]


# =============================================================================
# R8: origin, mapping and import authority
# =============================================================================


def _with_origin(raw: bytes, project_id: str | None, worktree_id: str | None) -> bytes:
    def mutate(c: dict[str, Any]) -> None:
        if project_id is not None:
            c["origin"]["project_id"] = project_id
        if worktree_id is not None:
            c["origin"]["worktree_id"] = worktree_id

    return mutated_capsule(raw, mutate)


def test_foreign_or_moved_worktree_needs_approved_mapping(tmp_path: Path) -> None:
    from rush.memory import authorization as auth

    src = make_env(tmp_path, "src")
    dest = make_env(tmp_path, "dest", owner=BOB, seed=False)
    cap = export_file(src, "foreign.json")
    raw = cap.read_bytes()
    origin = json.loads(raw)["origin"]
    base = {"input": str(cap), "invocation_id": new_uuid()}
    imp = {
        **base,
        "action": "import",
        "apply": True,
        "expected_digest": "a" * 64,
        "expected_store_revision": 0,
    }

    # a foreign origin pair without a mapping: refused before anything is read
    before = dest.effects()
    for request in ({**base, "action": "preview_import"}, imp):
        res = call_inproc(dest.root, request)
        assert_denied(res, "E_PERMISSION", "mapping_required")
    assert dest.effects() == before and not imported_rows(dest)

    # a moved checkout (same project, other worktree id) and a changed project id are
    # foreign too: the capsule's own claim is never enough
    claimed = call_inproc(src.root, {**base, "action": "preview_import"})
    assert claimed.code == "OK" and claimed.data["origin_match"] == "claimed", claimed
    for name, project_id, worktree_id in (
        ("moved", None, sha("moved-worktree")),
        ("renamed", "other-project-id", None),
    ):
        path = src.outside / f"{name}.json"
        path.write_bytes(_with_origin(raw, project_id, worktree_id))
        res = call_inproc(
            src.root,
            {
                "action": "preview_import",
                "input": str(path),
                "invocation_id": new_uuid(),
            },
        )
        assert_denied(res, "E_PERMISSION", "mapping_required")

    mapping_id = approved_mapping(dest, origin)
    mapped = call_inproc(
        dest.root, {**base, "action": "preview_import", "mapping_id": mapping_id}
    )
    assert mapped.code == "OK", mapped
    assert mapped.data["origin_match"] == "mapped"
    done = call_inproc(
        dest.root,
        {
            **base,
            "action": "import",
            "apply": True,
            "mapping_id": mapping_id,
            "expected_digest": mapped.data["digest"],
            "expected_store_revision": preview_store_revision(mapped.data),
        },
    )
    assert done.code == "OK", done
    rows = imported_rows(dest)
    assert len(rows) == 5
    assert {(r["owner_scope_kind"], r["owner_scope_id"]) for r in rows} == {
        ("user", "bob")
    }, "rows are owned by the mapping's target owner"
    assert {r["source"] for r in rows} == {IMPORT_SRC}

    # an owner other than the mapping's target owner
    clash = call_inproc(
        dest.root,
        {
            **base,
            "action": "preview_import",
            "mapping_id": mapping_id,
            "selectors": {"owner_scope": ALICE.as_dict()},
        },
    )
    assert_denied(clash, "E_PERMISSION", "mapping_mismatch")

    # unknown, foreign-origin, revoked and superseded-grant mappings
    unknown = call_inproc(
        dest.root,
        {**base, "action": "preview_import", "mapping_id": new_uuid()},
    )
    assert_denied(unknown, "E_PERMISSION", "mapping_unknown")
    other_origin = approved_mapping(
        dest, {"project_id": "other-project", "worktree_id": sha("other-worktree")}
    )
    wrong = call_inproc(
        dest.root, {**base, "action": "preview_import", "mapping_id": other_origin}
    )
    assert_denied(wrong, "E_PERMISSION", "mapping_mismatch")
    # a standalone mapping_id on an origin-absent input is itself a mismatch (A8):
    # covered with the PAS fixtures in test_memory_capsule_pas.py.
    auth.revoke_capsule_mapping(
        mapping_id=mapping_id,
        expected_policy_revision=revision_of(dest.data_root),
        consent=True,
        data_root=dest.data_root,
    )
    revoked = call_inproc(
        dest.root, {**base, "action": "preview_import", "mapping_id": mapping_id}
    )
    assert_denied(revoked, "E_PERMISSION", "mapping_revoked")

    fresh = approved_mapping(dest, origin)
    assert fresh != mapping_id
    assert (
        call_inproc(
            dest.root, {**base, "action": "preview_import", "mapping_id": fresh}
        ).code
        == "OK"
    )
    # superseding the mapped owner's grant changes grant_id: the mapping no longer holds
    grant_for(dest.root, BOB, dest.data_root, ops=(*ALL_OPS, "history"))
    superseded = call_inproc(
        dest.root, {**base, "action": "preview_import", "mapping_id": fresh}
    )
    assert_denied(superseded, "E_PERMISSION", "mapping_mismatch")


def test_forged_origin_import_gains_no_authority(tmp_path: Path) -> None:
    env = make_env(tmp_path, seed=False)
    raw = fixture_bytes("rush_v1_two_constraints_two_evidence.json")

    def forge(c: dict[str, Any]) -> None:
        c["origin"]["project_id"] = env.project_id
        c["origin"]["worktree_id"] = env.worktree_id
        c["scope"]["owner"] = {"kind": "user", "id": sha("mallory")}
        c["scope"]["sources"] = ["trusted-source", IMPORT_SRC]
        for entry in c["evidence"]:
            entry["provenance"] = {
                "trust_tier": "STATED",
                "origin_kind": "human",
                "origin_id": "root",
            }

    forged = env.outside / "forged.json"
    forged.write_bytes(mutated_capsule(raw, forge))
    preview, done = imported(env, forged)
    assert preview.code == "OK", preview
    assert preview.data["origin_match"] == "claimed"
    assert done.code == "OK", done
    rows = imported_rows(env)
    assert len(rows) == 5
    for row in rows:
        content = json.loads(row["content"])
        assert row["trust_tier"] == "IMPORTED"
        assert row["source"] == IMPORT_SRC
        assert (row["owner_scope_kind"], row["owner_scope_id"]) == ("user", "alice")
        assert content["authority"] == "imported_unverified"
        assert row["promoted_at"] is None and row["corroboration_count"] == 0
        assert row["origin_kind"] is None and row["origin_id"] is None
        assert row["symbol_ref"] is None and row["content_hash"] is None
    assert {m["applicability"] for m in done.data["mappings"]} == {"pending"}


def test_unverified_constraints_not_instructions(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    cap = export_file(env, "c.json")
    capsule_doc = json.loads(cap.read_bytes())
    preview, done = imported(env, cap)
    assert preview.code == "OK" and done.code == "OK", (preview, done)
    kinds = [r["content"].get("kind") for r in preview.data["records"][:3]]
    assert kinds == ["imported_task", "constraint", "constraint"]
    assert [r["applicability"] for r in preview.data["records"]] == ["pending"] * 5
    assert [m["applicability"] for m in done.data["mappings"]] == ["pending"] * 5
    assert [m["artifact_version"] for m in done.data["mappings"]] == [1] * 5
    by_id = {r["id"]: r for r in imported_rows(env)}
    for mapping in done.data["mappings"]:
        row = by_id[mapping["artifact_id"]]
        content = json.loads(row["content"])
        assert content["authority"] == "imported_unverified"
        assert (
            content["import_provenance"]["capsule_digest"]
            == capsule_doc["payload_sha256"]
        )
        assert (
            content["import_provenance"]["foreign_origin_id"]
            == mapping["foreign_origin_id"]
        )
    constraint_texts = {c["text"] for c in capsule_doc["task"]["constraints"]}
    stored_constraints = {
        json.loads(r["content"])["text"]
        for r in by_id.values()
        if json.loads(r["content"]).get("kind") == "constraint"
    }
    assert stored_constraints == constraint_texts
    # Nothing the capsule said is promoted or corroborated by importing it.
    assert all(
        r["promoted_at"] is None and r["corroboration_count"] == 0
        for r in by_id.values()
    )


def test_import_requires_apply_and_preview_bound_constraint_ids(
    tmp_path: Path,
) -> None:
    env = make_env(tmp_path)
    cap = export_file(env, "c.json")
    base = {"input": str(cap), "invocation_id": new_uuid()}

    # apply is mandatory for import, on every transport that carries the field
    no_apply = call_inproc(
        env.root,
        {
            **base,
            "action": "import",
            "expected_digest": "a" * 64,
            "expected_store_revision": 0,
        },
    )
    assert no_apply.code == "E_INPUT" and no_apply.field == "apply", no_apply
    assert not imported_rows(env)

    preview = call_cli_request(
        env, {**base, "action": "preview_import", "confirm_constraint_ids": ["c1"]}
    )
    assert preview.code == "OK", preview
    assert [r["applicability"] for r in preview.data["records"]] == [
        "pending",
        "active",
        "pending",
        "pending",
        "pending",
    ]
    revision = preview_store_revision(preview.data)
    apply_req = {
        **base,
        "action": "import",
        "apply": True,
        "expected_digest": preview.data["digest"],
        "expected_store_revision": revision,
    }
    # omitted, changed and unknown selections conflict with the preview; none writes
    before = env.effects()
    for name, confirm, code, reason in (
        ("omitted", None, "E_VERSION", "recovery_required"),
        ("changed", ["c1", "c2"], "E_VERSION", "recovery_required"),
        ("other", ["c2"], "E_VERSION", "recovery_required"),
    ):
        request = dict(apply_req)
        if confirm is not None:
            request["confirm_constraint_ids"] = confirm
        res = call_cli_request(env, request)
        assert_denied(res, code, reason)
        assert env.effects() == before, name
    for bad in (["unknown"], ["c1", "c1"], [""]):
        _prev, res = imported(env, cap, transport="cli", confirm=bad)
        assert res.code == "E_INPUT", (bad, res)
    assert env.effects() == before and not imported_rows(env)

    done = call_cli_request(env, {**apply_req, "confirm_constraint_ids": ["c1"]})
    assert done.code == "OK", done
    assert [m["applicability"] for m in done.data["mappings"]] == [
        "pending",
        "active",
        "pending",
        "pending",
        "pending",
    ]
    assert len(imported_rows(env)) == 5

    # bulk consent: one explicit selection covers the enumerated set; the task and
    # evidence records stay pending and every record stays imported_unverified.
    bulk_base = {"input": str(cap), "invocation_id": new_uuid()}
    bulk_prev = call_cli_request(
        env,
        {
            **bulk_base,
            "action": "preview_import",
            "confirm_constraint_ids": ["c1", "c2"],
        },
    )
    bulk = call_cli_request(
        env,
        {
            **bulk_base,
            "action": "import",
            "apply": True,
            "confirm_constraint_ids": ["c1", "c2"],
            "expected_digest": bulk_prev.data["digest"],
            "expected_store_revision": preview_store_revision(bulk_prev.data),
        },
    )
    assert bulk.code == "OK", bulk
    assert [m["applicability"] for m in bulk.data["mappings"]] == [
        "pending",
        "active",
        "active",
        "pending",
        "pending",
    ]
    for row in imported_rows(env):
        assert json.loads(row["content"])["authority"] == "imported_unverified"


def call_cli_request(env: CapEnv, request: dict[str, Any]) -> R:
    return call_cli(env.root, request)


# --- mapping consent (CLI only) ------------------------------------------------------


def mapping_cli(*args: str, project: Path | None = None) -> tuple[Any, R]:
    argv = ["memory", "capsule", "mapping", *args, "--json"]
    if project is not None and args[0] == "create":
        argv += ["--project", str(project)]
    result = cli_invoke(argv)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {}
    return result, R(payload)


def pick(data: dict[str, Any], key: str) -> Any:
    """`key` from a mapping result: top level, or one level down (`preview`/`mapping`)."""
    if key in data:
        return data[key]
    for nested in ("preview", "mapping"):
        inner = data.get(nested)
        if isinstance(inner, dict) and key in inner:
            return inner[key]
    raise AssertionError(f"{key!r} not in {data!r}")


def test_mapping_create_revoke_policy_cas(tmp_path: Path) -> None:
    from rush.memory import authorization as auth

    src = make_env(tmp_path, "src")
    dest = make_env(tmp_path, "dest", owner=BOB, seed=False)
    cap = export_file(src, "foreign.json")
    origin = json.loads(cap.read_bytes())["origin"]
    policy = auth.policy_path(data_root=dest.data_root)

    def create(
        revision: int, *flags: str, project: Path | None = None
    ) -> tuple[Any, R]:
        return mapping_cli(
            "create",
            "--input",
            str(cap),
            "--expected-policy-revision",
            str(revision),
            *flags,
            project=project or dest.root,
        )

    revision = revision_of(dest.data_root)
    # no --approve: a read-only preview of the exact pair and scope
    before = sha(policy.read_bytes())
    result, preview = create(revision, "--allow-cache-write")
    assert result.exit_code == 0, result.output
    assert preview.raw["operation"] == "capsule_mapping" and preview.code == "OK"
    assert pick(preview.data, "origin") == {
        "project_id": origin["project_id"],
        "worktree_id": origin["worktree_id"],
    }
    target = pick(preview.data, "target")
    assert target["project_id"] == dest.project_id
    assert target["worktree_id"] == dest.worktree_id
    assert pick(preview.data, "target_owner_scope") == {"kind": "user", "id": "bob"}
    assert pick(preview.data, "grant_id") == (dest.grant or {})["grant_id"]
    assert pick(preview.data, "policy_revision") == revision
    assert sha(policy.read_bytes()) == before

    # --approve without --allow-cache-write: skipped, naming the permission, no write
    result, skipped = create(revision, "--approve")
    assert result.exit_code == 0
    assert skipped.status == "skipped"
    assert "--allow-cache-write" in json.dumps(skipped.result)
    assert sha(policy.read_bytes()) == before

    # a stale revision: E_VERSION, no write
    result, stale = create(revision - 1, "--approve", "--allow-cache-write")
    assert stale.code == "E_VERSION", stale
    assert sha(policy.read_bytes()) == before

    # approve: one new mapping record at revision + 1
    result, approved = create(revision, "--approve", "--allow-cache-write")
    assert approved.code == "OK", approved
    mapping_id = pick(approved.data, "mapping_id")
    assert UUID_RE.match(mapping_id)
    assert revision_of(dest.data_root) == revision + 1
    view = auth.load_policy_readonly(data_root=dest.data_root)["mappings"][mapping_id]
    assert set(view) == {
        "mapping_id",
        "purpose",
        "origin_project_id",
        "origin_worktree_id",
        "target_project_id",
        "target_worktree_id",
        "target_root",
        "target_owner_scope",
        "grant_id",
        "created_revision",
        "approved_at",
        "revoked",
        "revoked_revision",
    }
    assert view["purpose"] == "capsule_import"
    assert view["target_root"] == str(dest.root)
    assert view["target_owner_scope"] == {"kind": "user", "id": "bob"}
    assert view["grant_id"] == (dest.grant or {})["grant_id"]
    assert view["created_revision"] == revision + 1
    assert view["revoked"] is False and view["revoked_revision"] is None
    after_approve = sha(policy.read_bytes())

    # approving the identical mapping again returns it unchanged (no new write)
    result, again = create(revision, "--approve", "--allow-cache-write")
    assert again.code == "OK" and pick(again.data, "mapping_id") == mapping_id
    assert sha(policy.read_bytes()) == after_approve

    # a bound import preview works, then revoking invalidates it
    base = {"input": str(cap), "invocation_id": new_uuid(), "mapping_id": mapping_id}
    prev = call_inproc(dest.root, {**base, "action": "preview_import"})
    assert prev.code == "OK", prev

    def revoke(rev: int, mid: str, *flags: str) -> tuple[Any, R]:
        return mapping_cli(
            "revoke",
            "--mapping-id",
            mid,
            "--expected-policy-revision",
            str(rev),
            *flags,
        )

    current = revision_of(dest.data_root)
    result, preview_r = revoke(current, mapping_id, "--allow-cache-write")
    assert preview_r.code == "OK" and sha(policy.read_bytes()) == after_approve
    result, skipped_r = revoke(current, mapping_id, "--approve")
    assert skipped_r.status == "skipped" and sha(policy.read_bytes()) == after_approve
    result, stale_r = revoke(
        current - 1, mapping_id, "--approve", "--allow-cache-write"
    )
    assert stale_r.code == "E_VERSION"
    assert sha(policy.read_bytes()) == after_approve
    result, bad_id = revoke(current, "not-a-uuid", "--approve", "--allow-cache-write")
    assert bad_id.code == "E_INPUT" and bad_id.field == "mapping_id"
    result, ghost = revoke(current, new_uuid(), "--approve", "--allow-cache-write")
    assert_denied(ghost, "E_PERMISSION", "mapping_unknown")
    result, revoked = revoke(current, mapping_id, "--approve", "--allow-cache-write")
    assert revoked.code == "OK", revoked
    assert revision_of(dest.data_root) == current + 1
    view = auth.load_policy_readonly(data_root=dest.data_root)["mappings"][mapping_id]
    assert view["revoked"] is True and view["revoked_revision"] == current + 1
    after_revoke = sha(policy.read_bytes())
    result, twice = revoke(current + 1, mapping_id, "--approve", "--allow-cache-write")
    assert twice.code == "OK" and sha(policy.read_bytes()) == after_revoke

    done = call_inproc(
        dest.root,
        {
            **base,
            "action": "import",
            "apply": True,
            "expected_digest": prev.data["digest"],
            "expected_store_revision": preview_store_revision(prev.data),
        },
    )
    assert_denied(done, "E_PERMISSION", "mapping_revoked")
    assert not imported_rows(dest)

    # No MCP route creates or revokes a mapping; imported content cannot either.
    for extra in ({"approve": True}, {"mapping": {"action": "create"}}):
        res = call_mcp(dest.root, {**base, "action": "preview_import", **extra})
        assert res.code == "E_INPUT", (extra, res)
    assert sha(policy.read_bytes()) == after_revoke


# =============================================================================
# G8-T4/T5: export task selection, projection and mandatory bodies
# =============================================================================


def test_export_task_selection_and_ambiguity(tmp_path: Path) -> None:
    env = make_env(tmp_path, seed=False)
    now = time.time()
    for name in ("ev1", "ev2", "evb"):
        put_evidence(env, name)
    put_checkpoint(
        env, "cp-a1", task_id="t-a", created_at=now - 300, description="first"
    )
    put_checkpoint(
        env, "cp-a2", task_id="t-a", created_at=now - 200, description="newest"
    )
    put_checkpoint(
        env,
        "cp-b1",
        task_id="t-b",
        created_at=now - 250,
        description="other task",
        evidence_refs=[{"artifact_id": "evb", "version": 1}],
    )
    put_checkpoint(
        env, "cp-e1", task_id="t-ended", created_at=now - 100, event_kind="task_end"
    )
    put_checkpoint(
        env, "cp-c1", task_id="t-cancel", created_at=now - 90, event_kind="task_cancel"
    )
    put_checkpoint(
        env, "cp-wt", task_id="t-w", created_at=now - 80, worktree_id=sha("elsewhere")
    )
    put_checkpoint(env, "cp-v2", task_id="t-v2", created_at=now - 70, schema_version=2)
    before = env.effects()

    def request(action: str, **extra: Any) -> dict[str, Any]:
        return {
            "action": action,
            "output": str(env.outside / "sel.json"),
            "invocation_id": inv,
            **extra,
        }

    inv = new_uuid()
    # more than one eligible open task and no task_ref
    ambiguous = call_inproc(env.root, request("preview_export"))
    assert ambiguous.code == "E_INPUT" and ambiguous.reason == "task_ref_required", (
        ambiguous
    )

    def ref(artifact_id: str, version: int = 1) -> dict[str, Any]:
        return {
            "selectors": {"task_ref": {"artifact_id": artifact_id, "version": version}}
        }

    assert_denied(
        call_inproc(env.root, request("preview_export", **ref("ghost"))),
        "E_NOT_VISIBLE",
    )
    assert_denied(
        call_inproc(env.root, request("preview_export", **ref("cp-wt"))),
        "E_NOT_VISIBLE",
    )
    assert_denied(
        call_inproc(env.root, request("preview_export", **ref("cp-a1"))),
        "E_VERSION",
        "recovery_required",
    )
    assert_denied(
        call_inproc(env.root, request("preview_export", **ref("cp-a2", 2))),
        "E_VERSION",
        "recovery_required",
    )
    for ended in ("cp-e1", "cp-c1"):
        assert_denied(
            call_inproc(env.root, request("preview_export", **ref(ended))),
            "E_PERMISSION",
            "export_blocked",
        )
    assert env.effects() == before

    # the exact task_ref exports that row and only its evidence_refs
    for artifact_id, expected_ids in (
        ("cp-a2", ["cp-a2", "ev1", "ev2"]),
        ("cp-b1", ["cp-b1", "evb"]),
    ):
        out = env.outside / f"{artifact_id}.json"
        shared = {
            "output": str(out),
            "invocation_id": new_uuid(),
            **ref(artifact_id),
        }
        preview = call_inproc(env.root, {**shared, "action": "preview_export"})
        assert preview.code == "OK", preview
        done = call_inproc(
            env.root,
            {**shared, "action": "export", "expected_digest": preview.data["digest"]},
        )
        assert done.code == "OK", done
        capsule_doc = verify_rush_v1(out.read_bytes())
        assert [
            s["artifact_id"] for s in capsule_doc["manifest"]["selected"]
        ] == expected_ids
        assert [e["artifact_id"] for e in capsule_doc["evidence"]] == expected_ids[1:]
        stored = json.loads(row_of(env, artifact_id)["content"])
        assert capsule_doc["task"] == expected_task(stored)
        assert set(capsule_doc["task"]) == TASK_KEYS

    # exactly one eligible open task: no task_ref needed, its newest row is exported
    solo = make_env(tmp_path, "solo", seed=False)
    put_evidence(solo, "ev1")
    put_evidence(solo, "ev2")
    put_checkpoint(solo, "cp-old", created_at=now - 50, description="old")
    put_checkpoint(solo, "cp-new", created_at=now - 10, description="the newest")
    put_checkpoint(
        solo, "cp-end", task_id="t-done", created_at=now - 5, event_kind="task_end"
    )
    out, _preview, done = exported(solo, "solo.json")
    assert done.code == "OK", done
    assert verify_rush_v1(out.read_bytes())["task"]["description"] == "the newest"

    # zero eligible rows
    none = make_env(tmp_path, "none", seed=False)
    put_checkpoint(
        none, "cp-end", task_id="t-done", created_at=now - 5, event_kind="task_end"
    )
    res = call_inproc(
        none.root,
        {"action": "preview_export", "output": str(none.outside / "n.json")},
    )
    assert_denied(res, "E_PERMISSION", "export_blocked")
    empty = make_env(tmp_path, "empty", seed=False)
    res = call_inproc(
        empty.root,
        {"action": "preview_export", "output": str(empty.outside / "n.json")},
    )
    assert_denied(res, "E_PERMISSION", "export_blocked")

    # two granted owners and no owner_scope
    grant_for(env.root, BOB, env.data_root)
    owner_clash = call_inproc(env.root, request("preview_export", **ref("cp-a2")))
    assert owner_clash.code == "E_INPUT", owner_clash
    assert owner_clash.field == "owner_scope" and owner_clash.reason == "owner_required"
    explicit = call_inproc(
        env.root,
        request(
            "preview_export",
            selectors={
                "task_ref": {"artifact_id": "cp-a2", "version": 1},
                "owner_scope": ALICE.as_dict(),
            },
        ),
    )
    assert explicit.code == "OK", explicit


def _mutations() -> list[tuple[str, Any, bool]]:
    """`(name, mutate(content), keeps_selection)` for checkpoint rows that must block
    export; `keeps_selection` is false when the change alters the selected ids."""

    def drop(key: str) -> Any:
        return lambda c: c.pop(key)

    def put(key: str, value: Any) -> Any:
        return lambda c: c.__setitem__(key, value)

    def entry(
        key: str, index: int, field: str, value: Any = None, *, remove: bool = False
    ) -> Any:
        def mutate(c: dict[str, Any]) -> None:
            item = c[key][index]
            if remove:
                item.pop(field)
            else:
                item[field] = value

        return mutate

    failed_only = [
        {
            "command": ["pytest"],
            "exit_code": 1,
            "status": "failed",
            "source_revision": COMMIT,
            "receipt_id": "r9",
        }
    ]
    passed_nonzero = [dict(failed_only[0], status="passed")]
    cases: list[tuple[str, Any, bool]] = []
    for key in (
        "description",
        "objective",
        "next_action",
        "implemented",
        "unresolved",
        "decisions",
        "blockers",
        "discoveries",
        "disproved",
        "requirements",
        "checks",
        "source",
    ):
        cases.append((f"missing-{key}", drop(key), True))
    cases += [
        ("missing-evidence_refs", drop("evidence_refs"), False),
        ("next_action-empty", put("next_action", ""), True),
        ("next_action-int", put("next_action", 5), True),
        ("objective-int", put("objective", 5), True),
        ("description-int", put("description", 5), True),
        ("implemented-str", put("implemented", "x"), True),
        ("unresolved-dict", put("unresolved", {}), True),
        ("checks-empty", put("checks", []), True),
        ("checks-only-failed", put("checks", failed_only), True),
        ("checks-passed-nonzero-exit", put("checks", passed_nonzero), True),
        (
            "requirement-missing-authority",
            entry("requirements", 0, "authority", remove=True),
            True,
        ),
        ("requirement-extra-key", entry("requirements", 0, "extra", "x"), True),
        ("requirement-int-text", entry("requirements", 1, "text", 4), True),
        (
            "check-missing-receipt_id",
            entry("checks", 0, "receipt_id", remove=True),
            True,
        ),
        ("check-command-str", entry("checks", 0, "command", "pytest"), True),
        ("check-exit-bool", entry("checks", 0, "exit_code", True), True),
        ("check-status-unknown", entry("checks", 0, "status", "ok"), True),
        (
            "decision-missing-origin_ref",
            entry("decisions", 0, "origin_ref", remove=True),
            True,
        ),
        ("blocker-missing-text", entry("blockers", 0, "text", remove=True), True),
        ("discovery-extra-key", entry("discoveries", 0, "extra", 1), True),
        ("disproved-str", put("disproved", ["regex"]), True),
        ("evidence_ref-version-str", entry("evidence_refs", 0, "version", "1"), False),
        (
            "evidence_ref-version-bool",
            entry("evidence_refs", 0, "version", True),
            False,
        ),
        ("evidence_ref-version-zero", entry("evidence_refs", 0, "version", 0), False),
        (
            "evidence_ref-missing-version",
            entry("evidence_refs", 0, "version", remove=True),
            False,
        ),
        ("evidence_ref-empty-id", entry("evidence_refs", 0, "artifact_id", ""), False),
        (
            "evidence_ref-ghost",
            entry("evidence_refs", 0, "artifact_id", "ghost"),
            False,
        ),
        ("evidence_ref-future-version", entry("evidence_refs", 1, "version", 2), False),
        ("source-dirty-str", lambda c: c["source"].__setitem__("dirty", "no"), True),
        ("source-commit-int", lambda c: c["source"].__setitem__("commit", 7), True),
        ("source-not-object", put("source", "main"), True),
    ]
    return cases


def test_export_missing_mandatory_task_body_blocked(tmp_path: Path) -> None:
    cases = _mutations()
    assert len(cases) >= 40
    for index, (name, mutate, keeps_selection) in enumerate(cases):
        env = make_env(tmp_path, f"case{index}")
        base = {
            "output": str(env.outside / "blocked.json"),
            "invocation_id": new_uuid(),
        }
        clean = call_inproc(env.root, {**base, "action": "preview_export"})
        assert clean.code == "OK", (name, clean)
        content = json.loads(row_of(env, "cp1")["content"])
        mutate(content)
        plant_content(env, "cp1", content)
        before = env.effects()
        res = call_inproc(env.root, {**base, "action": "preview_export"})
        assert_denied(res, "E_PERMISSION", "export_blocked")
        assert "digest" not in res.data, name
        if keeps_selection:
            done = call_inproc(
                env.root,
                {**base, "action": "export", "expected_digest": clean.data["digest"]},
            )
            assert_denied(done, "E_PERMISSION", "export_blocked")
        assert not (env.outside / "blocked.json").exists(), name
        assert env.effects() == before, name

    # evidence states that are not usable: archived, owned by an ungranted owner
    env = make_env(tmp_path, "evidence-states")
    assert env.store is not None
    put_evidence(env, "ev-bob", owner=BOB)
    cp = json.loads(row_of(env, "cp1")["content"])
    cp["evidence_refs"] = [{"artifact_id": "ev-bob", "version": 1}]
    plant_content(env, "cp1", cp)
    base = {"output": str(env.outside / "ev.json"), "invocation_id": new_uuid()}
    assert_denied(
        call_inproc(env.root, {**base, "action": "preview_export"}),
        "E_PERMISSION",
        "export_blocked",
    )
    cp["evidence_refs"] = [{"artifact_id": "ev1", "version": 1}]
    plant_content(env, "cp1", cp)
    assert call_inproc(env.root, {**base, "action": "preview_export"}).code == "OK"
    env.store.archive(
        "ev1",
        expected_version=1,
        scope="domain_knowledge",
        owner_scope=ALICE,
        apply=True,
    )
    assert_denied(
        call_inproc(env.root, {**base, "action": "preview_export"}),
        "E_PERMISSION",
        "export_blocked",
    )

    # bodies canonical_json cannot encode: NaN and a lone surrogate
    for bad_name, body in (
        ("nan", {"x": float("nan")}),
        ("surrogate", {"x": "\ud800"}),
    ):
        env = make_env(tmp_path, f"unencodable-{bad_name}")
        base = {"output": str(env.outside / "u.json"), "invocation_id": new_uuid()}
        clean = call_inproc(env.root, {**base, "action": "preview_export"})
        plant_content(env, "ev1", body)
        res = call_inproc(env.root, {**base, "action": "preview_export"})
        assert_denied(res, "E_PERMISSION", "export_blocked")
        done = call_inproc(
            env.root,
            {**base, "action": "export", "expected_digest": clean.data["digest"]},
        )
        assert_denied(done, "E_PERMISSION", "export_blocked")
        assert not (env.outside / "u.json").exists()


# =============================================================================
# Concurrency and storage atomicity
# =============================================================================


@pytest.mark.parametrize(
    "action",
    [pytest.param("export", id="export"), pytest.param("import", id="import")],
)
def test_policy_revocation_race_blocks_capsule_commit(
    action: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import authorization as auth

    env = make_env(tmp_path)
    cap = export_file(env, "race-src.json")
    if action == "export":
        out = env.outside / "race.json"
        base: dict[str, Any] = {"output": str(out), "invocation_id": new_uuid()}
        preview = call_inproc(env.root, {**base, "action": "preview_export"})
        request = {
            **base,
            "action": "export",
            "expected_digest": preview.data["digest"],
        }
    else:
        base = {"input": str(cap), "invocation_id": new_uuid()}
        preview = call_inproc(env.root, {**base, "action": "preview_import"})
        request = {
            **base,
            "action": "import",
            "apply": True,
            "expected_digest": preview.data["digest"],
            "expected_store_revision": preview_store_revision(preview.data),
        }
    assert preview.code == "OK", preview
    db_before = sha(env.db.read_bytes())

    # The grant is revoked after the unlocked recheck and before the policy lock is
    # held: the commit must re-read the policy under the lock and refuse.
    state = {"armed": True}
    real = auth.hold_policy_lock

    @contextlib.contextmanager
    def racing(*args: Any, **kwargs: Any) -> Iterator[None]:
        if state["armed"]:
            state["armed"] = False
            auth.revoke_memory_scope(
                grant_id=(env.grant or {})["grant_id"],
                expected_policy_revision=revision_of(env.data_root),
                consent=True,
                data_root=env.data_root,
            )
        with real(*args, **kwargs):
            yield

    from rush.memory import capsule

    monkeypatch.setattr(auth, "hold_policy_lock", racing)
    monkeypatch.setattr(capsule, "hold_policy_lock", racing, raising=False)
    res = call_inproc(env.root, request)
    assert state["armed"] is False, "the capsule never took the policy lock"
    assert_denied(res, "E_PERMISSION", "revoked")
    assert sha(env.db.read_bytes()) == db_before
    assert not imported_rows(env)
    if action == "export":
        assert not out.exists()


_CHILD = """
import json, sys, time
from pathlib import Path
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

root, request, ready, go, result_path = sys.argv[1:6]
Path(ready).write_text("ready")
deadline = time.time() + 90
while not Path(go).exists():
    if time.time() > deadline:
        sys.exit(3)
    time.sleep(0.005)
result = MemoryTool().run(
    Path(root),
    operation="capsule",
    request=json.loads(request),
    permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
)
Path(result_path).write_text(json.dumps({"status": result["status"], "raw": result["raw"]}, default=str))
"""


def test_two_process_same_store_revision_one_import(tmp_path: Path) -> None:
    import rush

    env = make_env(tmp_path)
    cap = export_file(env, "shared.json")
    work = tmp_path / "work"
    work.mkdir()
    requests = []
    for _ in range(2):
        base = {"input": str(cap), "invocation_id": new_uuid()}
        preview = call_inproc(env.root, {**base, "action": "preview_import"})
        assert preview.code == "OK", preview
        requests.append(
            {
                **base,
                "action": "import",
                "apply": True,
                "expected_digest": preview.data["digest"],
                "expected_store_revision": preview_store_revision(preview.data),
            }
        )
    assert (
        requests[0]["expected_store_revision"] == requests[1]["expected_store_revision"]
    )
    go = work / "go"
    src_dir = str(Path(rush.__file__).resolve().parents[1])
    child_env = {**os.environ, "PYTHONPATH": src_dir}
    procs = []
    for n, request in enumerate(requests):
        procs.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    _CHILD,
                    str(env.root),
                    json.dumps(request),
                    str(work / f"ready{n}"),
                    str(go),
                    str(work / f"result{n}.json"),
                ],
                env=child_env,
                cwd=work,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        )
    try:
        deadline = time.time() + 90
        while not all((work / f"ready{n}").exists() for n in range(2)):
            assert time.time() < deadline, "children never became ready"
            time.sleep(0.01)
        go.write_text("go")
        for proc in procs:
            _out, err = proc.communicate(timeout=180)
            assert proc.returncode == 0, err.decode("utf-8", "replace")[-2000:]
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    results = [R(json.loads((work / f"result{n}.json").read_text())) for n in range(2)]
    codes = sorted(str(r.code) for r in results)
    assert codes == ["E_VERSION", "OK"], results
    loser = next(r for r in results if r.code != "OK")
    assert loser.reason == "store_changed", loser
    assert len(imported_rows(env)) == 5, "exactly one import committed"


def test_committed_import_replay_precedes_revision_conflict(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    cap = export_file(env, "replay.json")
    inv = new_uuid()
    base = {"input": str(cap), "invocation_id": inv}
    preview = call_inproc(env.root, {**base, "action": "preview_import"})
    revision = preview_store_revision(preview.data)
    request = {
        **base,
        "action": "import",
        "apply": True,
        "expected_digest": preview.data["digest"],
        "expected_store_revision": revision,
    }
    first = call_inproc(env.root, request)
    assert first.code == "OK", first
    assert store_revision(env.db) > revision, "the import advanced the store"
    rows = imported_rows(env)

    # the identical request replays the original receipt even though the store
    # revision it names is no longer current
    again = call_inproc(env.root, request)
    assert again.code == "OK", again
    assert again.data["replayed"] is True
    assert again.data["mappings"] == first.data["mappings"]
    assert again.data["capsule_digest"] == first.data["capsule_digest"]
    assert imported_rows(env) == rows

    # another invocation, previewed afresh but naming the stale revision, is a real
    # conflict
    other_base = {"input": str(cap), "invocation_id": new_uuid()}
    other_preview = call_inproc(env.root, {**other_base, "action": "preview_import"})
    assert other_preview.code == "OK", other_preview
    other = call_inproc(
        env.root,
        {
            **other_base,
            "action": "import",
            "apply": True,
            "expected_digest": other_preview.data["digest"],
            "expected_store_revision": revision,
        },
    )
    assert_denied(other, "E_VERSION", "store_changed")
    # the same invocation with a different request digest conflicts with the receipt
    for changed in (
        {"expected_store_revision": revision + 1},
        {"expected_digest": "d" * 64},
    ):
        res = call_inproc(env.root, {**request, **changed})
        assert_denied(res, "E_VERSION", "effect_digest_conflict")
    assert imported_rows(env) == rows


def test_preview_absent_store_and_apply_atomic_initialization(tmp_path: Path) -> None:
    dest = make_env(tmp_path, "dest", create_store=False)
    assert not dest.db.exists()
    raw = fixture_bytes("rush_v1_two_constraints_two_evidence.json")
    cap = dest.outside / "claimed.json"
    cap.write_bytes(_with_origin(raw, dest.project_id, dest.worktree_id))
    base = {"input": str(cap), "invocation_id": new_uuid()}
    before = dest.effects()
    preview = call_inproc(dest.root, {**base, "action": "preview_import"})
    assert preview.code == "OK", preview
    assert preview_store_state(preview.data) == "absent"
    assert preview_store_revision(preview.data) == 0
    assert dest.effects() == before and not dest.db.exists(), (
        "a preview creates no store"
    )
    assert not (dest.data_root / "dashboard" / "project_locks").exists()

    apply_request = {
        **base,
        "action": "import",
        "apply": True,
        "expected_digest": preview.data["digest"],
        "expected_store_revision": 0,
    }
    stale = call_inproc(dest.root, {**apply_request, "expected_digest": "c" * 64})
    assert_denied(stale, "E_VERSION", "recovery_required")
    assert not dest.db.exists(), "a refused import publishes nothing"

    done = call_inproc(dest.root, apply_request)
    assert done.code == "OK", done
    assert dest.db.exists()
    with contextlib.closing(sqlite3.connect(dest.db)) as conn:
        names = {
            (kind, name)
            for kind, name in conn.execute("SELECT type, name FROM sqlite_master")
        }
    assert ("index", "idx_mutation_receipts_v2") in names
    assert ("trigger", "memory_event_identity_immutable") in names
    assert len(imported_rows(dest)) == 5
    leftovers = [p.name for p in (dest.root / ".rush").iterdir() if "import-" in p.name]
    assert leftovers == [], "no publication temp file survives"
    replay = call_inproc(dest.root, apply_request)
    assert replay.code == "OK" and replay.data["replayed"] is True
    assert len(imported_rows(dest)) == 5


# =============================================================================
# Error codes, bridge, targets, transport, locks, permissions, parity
# =============================================================================


def test_capsule_error_codes_are_existing_codes(tmp_path: Path) -> None:
    from rush.memory import authorization as auth
    from rush.tools.memory import _CODE_STATUS

    results: list[R] = []

    def record(
        res: R, code: str, reason: str | None = None, field: str | None = None
    ) -> R:
        results.append(res)
        assert res.code == code, res
        if reason is not None:
            assert res.reason == reason, res
        if field is not None:
            assert res.field == field, res
        return res

    env = make_env(tmp_path)
    out = str(env.outside / "codes.json")
    base = {"output": out, "invocation_id": new_uuid()}

    def preview(env_: CapEnv = env, **extra: Any) -> R:
        return call_inproc(
            env_.root,
            {
                "action": "preview_export",
                "output": str(env_.outside / "c.json"),
                "invocation_id": new_uuid(),
                **extra,
            },
        )

    # an explicit ungranted owner is E_OWNER; an ungranted source is E_SCOPE
    record(
        preview(selectors={"owner_scope": BOB.as_dict()}),
        "E_OWNER",
        "owner_not_granted",
    )
    record(
        preview(selectors={"sources": ["not-granted"]}), "E_SCOPE", "source_not_granted"
    )
    # two granted owners and no owner_scope: E_INPUT naming the field
    two = make_env(tmp_path, "two")
    grant_for(two.root, BOB, two.data_root)
    record(preview(two), "E_INPUT", "owner_required", "owner_scope")
    # no policy at all, a grant without {expand}, a revoked grant: E_PERMISSION
    bare = make_env(tmp_path, "bare", grant=False, seed=False)
    record(preview(bare), "E_PERMISSION", "policy_missing")
    narrow = make_env(tmp_path, "narrow", ops=("list",))
    record(preview(narrow), "E_PERMISSION", "operation_not_granted")
    gone = make_env(tmp_path, "gone")
    auth.revoke_memory_scope(
        grant_id=(gone.grant or {})["grant_id"],
        expected_policy_revision=revision_of(gone.data_root),
        consent=True,
        data_root=gone.data_root,
    )
    record(preview(gone), "E_PERMISSION", "revoked")
    # budget, version and input faults
    record(preview(max_bytes=100), "E_INPUT")
    record(
        call_inproc(
            env.root, {**base, "action": "export", "expected_digest": "b" * 64}
        ),
        "E_VERSION",
        "recovery_required",
    )
    record(
        call_inproc(env.root, {**base, "action": "preview_export", "input": "x"}),
        "E_INPUT",
    )
    junk = env.outside / "junk.json"
    junk.write_bytes(b"{")
    record(
        call_inproc(
            env.root,
            {
                "action": "preview_import",
                "input": str(junk),
                "invocation_id": new_uuid(),
            },
        ),
        "E_INPUT",
        "capsule_invalid",
    )
    record(call_inproc(env.root, {"action": "bridge"}), "E_INPUT", field="input")
    ok = record(preview(), "OK")
    assert ok.status == "ok"
    for res in results:
        assert res.code in _CODE_STATUS, res
        assert res.status == _CODE_STATUS[res.code], res


def test_bridge_action_refused_in_codec(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    cap = export_file(env, "b.json", transport="mcp")
    before = env.effects()
    for transport in TRANSPORTS:
        for extra in ({}, {"input": str(cap)}, {"format": "pas_v1", "input": str(cap)}):
            res = call(transport, env.root, {"action": "bridge", **extra})
            assert res.code == "E_INPUT", (transport, extra, res)
            assert res.data["field"] == (
                "instructions" if "input" in extra else "input"
            ), (transport, extra, res)
    assert env.effects() == before


# --- export target refusal rules (G8-T2) ---------------------------------------------


def _watch(*paths: Path) -> dict[Path, str]:
    return {p: sha(p.read_bytes()) for p in paths if p.is_file() and not p.is_symlink()}


def _refused(
    env: CapEnv,
    out: Path,
    *,
    fmt: str = "rush_v1",
    transport: str = "inproc",
    code: str = "E_PERMISSION",
    reason: str = "export_target_refused",
    watch: tuple[Path, ...] = (),
) -> None:
    before = env.effects()
    watched = _watch(*watch)
    base = {"format": fmt, "output": str(out), "invocation_id": new_uuid()}
    for request in (
        {**base, "action": "preview_export"},
        {**base, "action": "export", "expected_digest": "a" * 64},
    ):
        res = call(transport, env.root, request)
        assert_denied(res, code, reason)
        assert env.effects() == before
        assert _watch(*watch) == watched


def _t_root_rush_memory_db(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    _refused(env, env.root / ".rush" / "memory.db", watch=(env.db,))


def _t_root_rush_other(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    _refused(env, env.root / ".rush" / "x.json", watch=(env.db,))


def _t_overlay_policy_file(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    policy = env.data_root / "user" / ".rush" / "memory_authorization.json"
    assert policy.exists()
    _refused(env, policy, watch=(policy,))


def _t_overlay_memory_db(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    (env.data_root / "user" / ".rush").mkdir(parents=True, exist_ok=True)
    _refused(env, env.data_root / "user" / ".rush" / "memory.db")


def _t_data_root_anything(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    _refused(env, env.data_root / "x.json")


def _t_reserved_wal(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    (env.root / "sub").mkdir()
    _refused(env, env.root / "sub" / "memory.db-wal")


def _t_reserved_preferences(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    _refused(env, env.root / "preferences.json")


def _t_reserved_policy_marker(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    _refused(env, env.root / "memory-policy.required.json")


def _t_existing_directory(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    (env.outside / "adir").mkdir()
    _refused(env, env.outside / "adir")


def _t_in_root_symlink(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    victim = env.outside / "victim.json"
    victim.write_bytes(b"victim")
    (env.root / "link.json").symlink_to(victim)
    _refused(env, env.root / "link.json", watch=(victim,))
    assert victim.read_bytes() == b"victim"


def _t_final_symlink_loop(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    loop = env.outside / "loop.json"
    loop.symlink_to(loop)
    _refused(env, loop)


def _t_parent_symlink_loop(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    loop = env.outside / "loopdir"
    loop.symlink_to(loop)
    _refused(env, loop / "x.json")


def _t_pas_sidecar_symlink(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    victim = env.outside / "victim.json"
    victim.write_bytes(b"victim")
    out = env.outside / "p.json"
    Path(str(out) + ".rush-manifest.json").symlink_to(victim)
    _refused(env, out, fmt="pas_v1", watch=(victim,))
    assert not out.exists()


def _t_pas_sidecar_is_directory(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    out = env.outside / "p.json"
    Path(str(out) + ".rush-manifest.json").mkdir()
    _refused(env, out, fmt="pas_v1")
    assert not out.exists()


def _t_missing_parent(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    out = env.outside / "no-such-dir" / "x.json"
    _refused(env, out, code="E_INPUT", reason="output_parent_missing")
    assert not out.parent.exists()


def _t_mcp_outside_root(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    _refused(env, env.outside / "x.json", transport="mcp")


def _t_mcp_existing_in_root(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    existing = env.exports / "exists.json"
    existing.write_bytes(b"{}")
    _refused(env, existing, transport="mcp", watch=(existing,))


def _spy_opens(mp: pytest.MonkeyPatch, under: Path) -> list[str]:
    opened: list[str] = []
    real = os.open

    def spy(path: Any, *args: Any, **kwargs: Any) -> int:
        try:
            text = os.fsdecode(os.fspath(path))
        except TypeError:
            text = ""
        if text.startswith(str(under)):
            opened.append(text)
        return real(path, *args, **kwargs)

    mp.setattr(os, "open", spy)
    return opened


def _mcp_outside_replay(fmt: str) -> Any:
    def run(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
        out = env.outside / "replay.json"
        base = {"format": fmt, "output": str(out), "invocation_id": new_uuid()}
        preview = call_cli(env.root, {**base, "action": "preview_export"})
        assert preview.code == "OK", preview
        request = {
            **base,
            "action": "export",
            "expected_digest": preview.data["digest"],
        }
        first = call_cli(env.root, request)
        assert first.code == "OK", first
        files = [out] + (
            [Path(str(out) + ".rush-manifest.json")] if fmt == "pas_v1" else []
        )
        stamps = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}
        opened = _spy_opens(mp, env.outside)
        res = call_mcp(env.root, request)
        assert_denied(res, "E_PERMISSION", "export_target_refused")
        assert "replayed" not in res.data
        assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files} == stamps
        assert opened == [], "no open of any path under the outside directory"

    return run


def _t_mcp_outside_existing_no_marker(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    plain = env.outside / "plain.json"
    plain.write_bytes(b"{}")
    stamp = (plain.read_bytes(), plain.stat().st_mtime_ns)
    opened = _spy_opens(mp, env.outside)
    res = call_mcp(
        env.root,
        {
            "action": "export",
            "output": str(plain),
            "invocation_id": new_uuid(),
            "expected_digest": "a" * 64,
        },
    )
    assert_denied(res, "E_PERMISSION", "export_target_refused")
    assert (plain.read_bytes(), plain.stat().st_mtime_ns) == stamp
    assert opened == []


def _t_control_cli_outside_absent(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    out, _preview, done = exported(env, "ctl.json", transport="cli")
    assert done.code == "OK", done
    assert verify_rush_v1(out.read_bytes())


def _t_control_cli_overwrite(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    out, _p1, first = exported(env, "over.json", transport="cli")
    assert first.code == "OK"
    old = json.loads(out.read_bytes())["capsule_id"]
    _out, _p2, second = exported(env, "over.json", transport="cli")
    assert second.code == "OK", second
    assert json.loads(out.read_bytes())["capsule_id"] != old, (
        "replaced through the preview-bound pre-state"
    )


def _t_control_mcp_replay(env: CapEnv, mp: pytest.MonkeyPatch) -> None:
    out = env.exports / "mcp-replay.json"
    base = {"output": str(out), "invocation_id": new_uuid()}
    preview = call_mcp(env.root, {**base, "action": "preview_export"})
    request = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    first = call_mcp(env.root, request)
    assert first.code == "OK", first
    again = call_mcp(env.root, request)
    assert again.code == "OK" and again.data["replayed"] is True, again


_TARGET_CASES: list[Any] = [
    pytest.param(_t_root_rush_memory_db, id="root-rush-memory-db"),
    pytest.param(_t_root_rush_other, id="root-rush-other-file"),
    pytest.param(_t_overlay_policy_file, id="overlay-policy-file"),
    pytest.param(_t_overlay_memory_db, id="overlay-memory-db"),
    pytest.param(_t_data_root_anything, id="data-root-file"),
    pytest.param(_t_reserved_wal, id="reserved-memory-db-wal-name"),
    pytest.param(_t_reserved_preferences, id="reserved-preferences-name"),
    pytest.param(_t_reserved_policy_marker, id="reserved-policy-marker-name"),
    pytest.param(_t_existing_directory, id="existing-directory"),
    pytest.param(
        _t_in_root_symlink,
        id="in-root-symlink-to-outside",
        marks=pytest.mark.posix_only,
    ),
    pytest.param(
        _t_final_symlink_loop, id="final-symlink-loop", marks=pytest.mark.posix_only
    ),
    pytest.param(
        _t_parent_symlink_loop, id="parent-symlink-loop", marks=pytest.mark.posix_only
    ),
    pytest.param(
        _t_pas_sidecar_symlink, id="pas-sidecar-symlink", marks=pytest.mark.posix_only
    ),
    pytest.param(_t_pas_sidecar_is_directory, id="pas-sidecar-is-directory"),
    pytest.param(_t_missing_parent, id="missing-parent"),
    pytest.param(_t_mcp_outside_root, id="mcp-outside-root"),
    pytest.param(_t_mcp_existing_in_root, id="mcp-existing-in-root"),
    pytest.param(_mcp_outside_replay("rush_v1"), id="mcp-outside-root-replay-rush_v1"),
    pytest.param(_mcp_outside_replay("pas_v1"), id="mcp-outside-root-replay-pas_v1"),
    pytest.param(
        _t_mcp_outside_existing_no_marker, id="mcp-outside-existing-without-marker"
    ),
    pytest.param(_t_control_cli_outside_absent, id="control-cli-outside-absent"),
    pytest.param(_t_control_cli_overwrite, id="control-cli-overwrite-in-root"),
    pytest.param(_t_control_mcp_replay, id="control-mcp-same-invocation-replay"),
]


@pytest.mark.parametrize("case", _TARGET_CASES)
def test_export_target_refusals(
    case: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    case(env, monkeypatch)


# --- transport and constraint confirmation ------------------------------------------


def test_mcp_cannot_confirm_constraints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path)
    cap = export_file(env, "c.json", transport="mcp")
    before = env.effects()
    with monkeypatch.context() as scoped:
        opened = _spy_opens(scoped, env.exports)
        for action in ("preview_import", "import"):
            request: dict[str, Any] = {
                "action": action,
                "input": str(cap),
                "invocation_id": new_uuid(),
                "confirm_constraint_ids": ["c1"],
            }
            if action == "import":
                request.update(
                    apply=True, expected_digest="a" * 64, expected_store_revision=0
                )
            res = call_mcp(env.root, request)
            assert_denied(res, "E_PERMISSION", "constraint_confirmation_requires_cli")
            assert env.effects() == before and not imported_rows(env)
        assert str(cap) not in opened, "refused before the input file was opened"
    # The CLI confirms the same selection.
    preview, done = imported(env, cap, transport="cli", confirm=["c1"])
    assert preview.code == "OK" and done.code == "OK", (preview, done)
    assert [m["applicability"] for m in done.data["mappings"]][1] == "active"
    # And MCP imports without a selection still work (constraints stay pending).
    _other_prev, other = imported(env, cap, transport="mcp")
    assert other.code == "OK", other
    assert {m["applicability"] for m in other.data["mappings"]} == {"pending"}


def test_capsule_transport_not_request_settable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import inspect

    from rush.mcp_support.request_models import published_schema
    from rush.mcp_support.tool_registry import make_tool_wrapper
    from rush.memory import capsule

    env = make_env(tmp_path)
    cap = export_file(env, "t-src.json", transport="mcp")
    seen: list[str] = []
    real = capsule.run_capsule

    def spy(
        root: Path,
        request: dict[str, Any],
        *,
        permissions: Any,
        transport: Literal["cli", "mcp"] = "cli",
        frame_bytes: Any = None,
    ) -> Any:
        seen.append(transport)
        return real(
            root,
            request,
            permissions=permissions,
            transport=transport,
            frame_bytes=frame_bytes,
        )

    monkeypatch.setattr(capsule, "run_capsule", spy)
    base = {
        "action": "preview_export",
        "output": str(env.exports / "t.json"),
        "invocation_id": new_uuid(),
    }
    before = env.effects()

    # the strict model rejects `transport` at the top level and inside `request`
    top = call_mcp(env.root, base, transport="cli")
    assert top.code == "E_INPUT", top
    assert any("transport" in d["loc"] for d in top.data["details"]), top
    nested = call_mcp(env.root, {**base, "transport": "cli"})
    assert nested.code == "E_INPUT", nested
    assert any("transport" in d["loc"] for d in nested.data["details"]), nested
    assert seen == [], "run_capsule was never reached"
    # the in-process and CLI-shaped path rejects the key by name as well
    inproc = call_inproc(env.root, {**base, "transport": "mcp"})
    assert inproc.code == "E_INPUT" and inproc.field == "transport", inproc
    assert seen == [] and env.effects() == before

    # the caller's transport is bound by the invocation, never by the request
    assert call_mcp(env.root, base).code == "OK"
    preview_import = {
        "action": "preview_import",
        "input": str(cap),
        "invocation_id": new_uuid(),
    }
    assert call_mcp(env.root, preview_import).code == "OK"
    assert seen == ["mcp", "mcp"]
    seen.clear()
    assert call_cli(env.root, base).code == "OK"
    assert call_inproc(env.root, base).code == "OK"
    assert seen == ["cli", "cli"]

    wrapper = make_tool_wrapper(MemoryTool())
    assert "transport" not in inspect.signature(wrapper).parameters
    assert "transport" not in published_schema("rush_memory")["properties"]
    assert MemoryTool.internal_parameters == frozenset({"transport"})
    assert "transport" in inspect.signature(MemoryTool.__call__).parameters
    assert "transport" in inspect.signature(MemoryTool.run).parameters


def test_capsule_lock_order_vs_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.dashboard import state
    from rush.memory import authorization as auth

    env = make_env(tmp_path)
    cap = export_file(env, "lock-src.json")
    acquired = lock_acquisitions(monkeypatch)

    # import: policy lock, then the capsule-target lock on the canonical DB path
    _prev, done = imported(env, cap)
    assert done.code == "OK", done
    ids = [i for _t, i in acquired]
    policy = [i for i in ids if i.startswith("memory-policy:")]
    target = [i for i in ids if i.startswith("memory-capsule-target:")]
    assert policy and target == ["memory-capsule-target:" + str(env.db.resolve())]
    assert ids.index(policy[0]) < ids.index(target[0])
    assert env.project_id not in ids, "the dashboard project lock is never taken"

    # export: policy lock, then the target lock on the --output path
    acquired.clear()
    out, _p, exp = exported(env, "lock-out.json")
    assert exp.code == "OK", exp
    ids = [i for _t, i in acquired]
    expected_target = "memory-capsule-target:" + str(out.parent.resolve() / out.name)
    assert expected_target in ids
    assert ids.index(
        next(i for i in ids if i.startswith("memory-policy:"))
    ) < ids.index(expected_target)
    assert env.project_id not in ids

    # a dashboard dispatch holds the project lock (position 1) and later takes the
    # policy lock; capsule actions run to completion meanwhile and never need it
    acquired.clear()
    held, release = threading.Event(), threading.Event()
    failures: list[BaseException] = []

    def dashboard() -> None:
        try:
            with state.cross_process_project_lock(
                env.project_id, data_root=env.data_root
            ):
                held.set()
                assert release.wait(30)
                with auth.hold_policy_lock(data_root=env.data_root):
                    pass
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            failures.append(exc)
            held.set()

    outcome: dict[str, R] = {}

    def worker() -> None:
        outcome["export"] = exported(env, "lock-out2.json")[2]
        outcome["import"] = imported(env, cap)[1]

    dash = threading.Thread(target=dashboard, name="dashboard")
    dash.start()
    assert held.wait(10) and not failures
    work = threading.Thread(target=worker, name="capsule-worker")
    work.start()
    work.join(10)
    stuck = work.is_alive()
    release.set()
    dash.join(10)
    work.join(10)
    assert not stuck, "capsule actions blocked behind the dashboard project lock"
    assert not dash.is_alive() and not failures, failures
    assert outcome["export"].code == "OK" and outcome["import"].code == "OK"
    worker_ids = [i for t, i in acquired if t == "capsule-worker"]
    assert worker_ids and env.project_id not in worker_ids


def test_restricted_session_capsule_denied(tmp_path: Path) -> None:
    import inspect

    from rush.mcp_support.tool_registry import build_memory_bridge_handler

    env = make_env(tmp_path)
    bare = make_env(tmp_path, "bare", create_store=False, seed=False)
    for target in (env, bare):
        before = target.effects()
        handler = build_memory_bridge_handler(
            root=target.root, session_id="session-1", capability="capability-1"
        )
        assert list(inspect.signature(handler).parameters) == ["operation", "request"]
        for request in (
            None,
            {"action": "preview_export", "output": str(target.outside / "r.json")},
            {"action": "preview_import", "input": str(target.outside / "r.json")},
        ):
            result = handler("capsule", request)
            assert result["code"] == "E_PERMISSION", result
        assert target.effects() == before
    assert not bare.db.exists()


def test_capsule_permission_flags(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    cap = export_file(env, "perm-src.json")
    for transport in TRANSPORTS:
        out = out_for(env, transport, f"perm-{transport}.json")
        base = {"output": str(out), "invocation_id": new_uuid()}
        # previews need no permission
        preview = call(
            transport,
            env.root,
            {**base, "action": "preview_export"},
            cache=False,
            artifact=False,
        )
        assert preview.code == "OK", (transport, preview)
        before = env.effects()
        skipped = call(
            transport,
            env.root,
            {**base, "action": "export", "expected_digest": preview.data["digest"]},
            cache=True,
            artifact=False,
        )
        assert skipped.status == "skipped", (transport, skipped)
        assert skipped.raw["missing_permissions"] == ["--allow-artifact-write"]
        assert "--allow-artifact-write" in json.dumps(skipped.result)
        assert not out.exists() and env.effects() == before

        # over MCP the input must sit under the project root
        src = out_for(env, transport, f"perm-in-{transport}.json")
        src.write_bytes(cap.read_bytes())
        in_base = {"input": str(src), "invocation_id": new_uuid()}
        prev_i = call(
            transport,
            env.root,
            {**in_base, "action": "preview_import"},
            cache=False,
            artifact=False,
        )
        assert prev_i.code == "OK", (transport, prev_i)
        before = env.effects()
        skipped_i = call(
            transport,
            env.root,
            {
                **in_base,
                "action": "import",
                "apply": True,
                "expected_digest": prev_i.data["digest"],
                "expected_store_revision": preview_store_revision(prev_i.data),
            },
            cache=False,
            artifact=True,
        )
        assert skipped_i.status == "skipped", (transport, skipped_i)
        assert skipped_i.raw["missing_permissions"] == ["--allow-cache-write"]
        assert not imported_rows(env) and env.effects() == before


# =============================================================================
# CLI/MCP parity
# =============================================================================


def test_cli_mcp_capsule_parity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import capsule

    monkeypatch.setattr(capsule, "_now", lambda: 1_760_000_000.5)
    monkeypatch.setattr(
        capsule, "_new_uuid", lambda: "11111111-1111-4111-8111-111111111111"
    )
    env = make_env(tmp_path)
    inv = "22222222-2222-4222-8222-222222222222"
    out = env.exports / "parity.json"
    src = env.exports / "parity-src.json"

    def both(request: dict[str, Any], label: str) -> tuple[R, R]:
        mcp = call_mcp(env.root, request)
        cli = call_cli(env.root, request)
        assert mcp.status == cli.status, (label, mcp, cli)
        assert mcp.raw == cli.raw, (label, mcp.raw, cli.raw)
        assert mcp.raw.get("operation") == "capsule", label
        return mcp, cli

    base = {"output": str(out), "invocation_id": inv}
    selectors = {
        "task_ref": {"artifact_id": "cp1", "version": 1},
        "owner_scope": ALICE.as_dict(),
        "sources": [IMPORT_SRC, SRC],
    }
    # previews (success), with every selector flag and the explicit limits
    plain, _ = both({**base, "action": "preview_export"}, "preview_export")
    assert plain.code == "OK"
    both(
        {
            **base,
            "action": "preview_export",
            "format": "rush_v1",
            "max_bytes": 70000,
            "max_tokens": 9000,
            "selectors": selectors,
        },
        "preview_export selectors",
    )
    # handler-level errors
    budget_request = {**base, "action": "preview_export", "max_bytes": 100}
    mcp_budget = call_mcp(env.root, budget_request)
    cli_budget = call_cli(env.root, budget_request)
    for result in (mcp_budget, cli_budget):
        assert_denied(result, "E_INPUT", "budget_below_minimum")
        assert result.data["admission_failure"] is True
        assert set(result.data["required"]) == {"bytes", "tokens"}
        assert result.data["required"]["bytes"] > 100
        assert result.data["required"]["tokens"] > 0
    # Each transport reserves its actual wrapper; wire-floor tests measure both.
    assert {**mcp_budget.raw, "data": {**mcp_budget.data, "required": None}} == {
        **cli_budget.raw,
        "data": {**cli_budget.data, "required": None},
    }
    both({**base, "action": "preview_export", "max_bytes": 1048577}, "hard cap")
    both(
        {**base, "action": "preview_export", "selectors": {"sources": ["nope"]}},
        "scope",
    )
    both(
        {
            **base,
            "action": "preview_export",
            "selectors": {"owner_scope": BOB.as_dict()},
        },
        "owner",
    )
    both(
        {**base, "action": "preview_export", "selectors": {"include_personal": True}},
        "include_personal",
    )
    both(
        {
            **base,
            "action": "preview_export",
            "selectors": {"task_ref": {"artifact_id": "ghost", "version": 1}},
        },
        "task_ref unknown",
    )
    both(
        {"action": "export", "output": str(out), "expected_digest": "a" * 64},
        "no invocation",
    )
    both({**base, "action": "export", "expected_digest": "a" * 64}, "digest mismatch")
    both({"action": "bridge"}, "bridge")
    both(
        {
            "action": "preview_export",
            "output": str(env.exports / "x.rush-manifest.json"),
        },
        "reserved output name",
    )
    both(
        {"action": "preview_import", "input": str(env.exports / "missing.json")},
        "missing input",
    )
    both(
        {
            **base,
            "action": "preview_export",
            "output": str(env.exports / "a" / "b.json"),
        },
        "parent",
    )

    # export: the same absent output, once per transport (removed in between)
    preview = call_mcp(env.root, {**base, "action": "preview_export"})
    request = {**base, "action": "export", "expected_digest": preview.data["digest"]}
    first = call_mcp(env.root, request)
    assert first.code == "OK", first
    published = out.read_bytes()
    out.unlink()
    second = call_cli(env.root, request)
    assert second.code == "OK", second
    assert second.status == first.status and second.raw == first.raw
    assert out.read_bytes() == published, "both transports write identical bytes"

    # import: previews and stale applications agree
    src.write_bytes(published)
    in_base = {"input": str(src), "invocation_id": inv}
    prev, _ = both({**in_base, "action": "preview_import"}, "preview_import")
    assert prev.code == "OK"
    both(
        {
            **in_base,
            "action": "import",
            "apply": True,
            "expected_digest": "e" * 64,
            "expected_store_revision": preview_store_revision(prev.data),
        },
        "import digest mismatch",
    )
    both(
        {
            **in_base,
            "action": "import",
            "apply": True,
            "expected_digest": prev.data["digest"],
            "expected_store_revision": preview_store_revision(prev.data) + 3,
        },
        "import store changed",
    )
    both(
        {
            **in_base,
            "action": "import",
            "expected_digest": "e" * 64,
            "expected_store_revision": 0,
        },
        "import without apply",
    )

    # the CLI help lists exactly the actions' options; every leaf exists
    for leaf in ("preview-export", "export", "preview-import", "import", "bridge"):
        helped = cli_invoke(["memory", "capsule", leaf, "--help"])
        assert helped.exit_code == 0, (leaf, helped.output)
        for option in (
            "--project",
            "--format",
            "--max-bytes",
            "--max-tokens",
            "--mapping-id",
            "--expected-digest",
            "--expected-store-revision",
            "--confirm-constraint-id",
            "--invocation-id",
            "--task-ref",
            "--owner",
            "--source",
            "--include-personal",
            "--apply",
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ):
            assert option in helped.output, (leaf, option)
        assert ("--input" in helped.output) and ("--output" in helped.output)
    for sub in ("create", "revoke"):
        helped = cli_invoke(["memory", "capsule", "mapping", sub, "--help"])
        assert helped.exit_code == 0, (sub, helped.output)
        for option in (
            "--expected-policy-revision",
            "--approve",
            "--allow-cache-write",
            "--json",
        ):
            assert option in helped.output, (sub, option)
    group = cli_invoke(["memory", "capsule", "--help"])
    assert group.exit_code == 0
    for leaf in (
        "preview-export",
        "export",
        "preview-import",
        "import",
        "bridge",
        "mapping",
    ):
        assert leaf in group.output


# =============================================================================
# G2: route x mode matrix (`test_codec_route_mode_matrix`)
# =============================================================================
#
# Rows are the entry points of the capsule operation; columns are the §5.0 G2
# dimensions (grammar `[<transport>.]<route>-<dimension>-<value>`, hyphen joined,
# dimension tokens exactly as the plan names them). Each cell asserts the code
# plus exact refs / zero effects; a dimension a route does not accept is one cell
# asserting the strict model's `E_INPUT` (MCP, in-process) or Click's exit 2 (CLI).

OVERLAY_SRC = "personal-preferences"
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
EXPORT_ROUTES = ("preview_export", "export")
IMPORT_ROUTES = ("preview_import", "import")
# G2a: dimension values that only fail in combination, one cell per route family.
INTERSECTIONS = (
    "legacy_with_policy",
    "historical_compound",
    "no_store_denial",
    "no_store_admission",
    "overlay_revocation",
    "selected_id",
    "cache_write_ask_only",
    "stale_view",
)


_ID_ROUTE = {
    "preview_export": "capsule-action-preview_export",
    "export": "capsule-action-export",
    "bridge": "capsule-action-bridge",
    "mapping_create": "capsule-action-mapping_create",
    "mapping_revoke": "capsule-action-mapping_revoke",
    "preview_import": "import-function-preview_import",
}


@dataclasses.dataclass(frozen=True)
class Cell:
    transport: str
    route: str
    dim: str
    val: str

    @property
    def id(self) -> str:
        # Grammar `<transport>.<route>-<dim>-<value>`: the route is a ROUTE_KEYS entry and
        # the entry point is a paired `action-` / `function-` token. `route` stays the
        # entry point's own name; the handlers dispatch on it.
        transport, route = self.transport, _ID_ROUTE.get(self.route, self.route)
        if (transport, self.route) == ("mcp_restricted", "capsule"):
            transport = "bridge"
            route = "mcp_bridge-operation-capsule-function-mcp_restricted.capsule"
        elif (transport, self.route) == ("dashboard", "memory_capsule"):
            route = "capsule-function-memory_capsule"
        prefix = "" if transport == "-" else f"{transport}."
        return f"{prefix}{route}-{self.dim}-{self.val}"

    @property
    def family(self) -> str:
        if self.route in EXPORT_ROUTES:
            return "E"
        if self.route in IMPORT_ROUTES:
            return "I"
        return self.route

    @property
    def final(self) -> bool:
        return self.route in ("export", "import")


def codec_cells() -> list[Cell]:
    cells: list[Cell] = []
    for transport in TRANSPORTS:
        routes = [*EXPORT_ROUTES, *IMPORT_ROUTES, "bridge"]
        if transport == "cli":
            routes += ["mapping_create", "mapping_revoke"]
        for route in routes:
            for dim, values in DIMENSIONS.items():
                cells.extend(Cell(transport, route, dim, v) for v in values)
    for transport in TRANSPORTS:
        for route in (*EXPORT_ROUTES, *IMPORT_ROUTES):
            cells.extend(
                Cell(transport, route, "intersection", v) for v in INTERSECTIONS
            )
    cells.append(Cell("mcp_restricted", "capsule", "access", "policy"))
    cells.append(Cell("dashboard", "memory_capsule", "access", "policy"))
    cells.append(Cell("tui", "capsule", "access", "policy"))
    return cells


CODEC_CELLS = codec_cells()


def overlay_owner(env: CapEnv) -> OwnerScope:
    from rush.memory import authorization as auth

    return auth.user_overlay_owner_scope(data_root=env.data_root)


def grant_overlay(env: CapEnv, ops: tuple[str, ...]) -> None:
    grant_for(
        env.root,
        overlay_owner(env),
        env.data_root,
        sources=(OVERLAY_SRC, IMPORT_SRC),
        ops=ops,
    )


def old_schema_store(env: CapEnv) -> None:
    (env.root / ".rush").mkdir(exist_ok=True)
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        conn.execute(
            "CREATE TABLE memory_artifacts (id TEXT PRIMARY KEY, content TEXT)"
        )
        conn.commit()


def set_applicability(env: CapEnv, artifact_id: str, value: str) -> None:
    from rush.memory.store import next_row_mac

    version = row_of(env, artifact_id)["artifact_version"]
    with contextlib.closing(sqlite3.connect(env.db)) as conn:
        for table in ("memory_artifacts", "memory_artifact_versions"):
            columns = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
            if "applicability" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN applicability TEXT")
        mac = next_row_mac(conn, env.root, artifact_id, {"applicability": value})
        conn.execute(
            "UPDATE memory_artifacts SET applicability = ?, row_mac = ? WHERE id = ?",
            (value, mac, artifact_id),
        )
        conn.execute(
            "UPDATE memory_artifact_versions SET applicability = ? "
            "WHERE artifact_id = ? AND artifact_version = ?",
            (value, artifact_id, version),
        )
        conn.commit()


def set_state(env: CapEnv, artifact_id: str, subject: str, state: str) -> None:
    """Move a current row into one of the G2 `row_state` values."""
    assert env.store is not None
    if state == "active":
        return
    if state == "archived":
        env.store.archive(
            artifact_id,
            expected_version=1,
            scope=subject,
            owner_scope=env.owner,
            apply=True,
        )
    elif state == "expired":
        raw_sql(
            env,
            "UPDATE memory_artifacts SET expired_at = ?, expired_by = 'sweep' WHERE id = ?",
            time.time(),
            artifact_id,
        )
    elif state in ("rejected", "pending"):
        set_applicability(env, artifact_id, state)
    elif state == "tampered":
        # keep the event-identity keys: the T06 `memory_event_identity_immutable` trigger
        # aborts any content update that changes them, and the payload hash stays stale.
        body = json.loads(row_of(env, artifact_id)["content"])
        text = json.dumps({**body, "tampered": True})
        raw_sql(
            env,
            "UPDATE memory_artifacts SET content = ? WHERE id = ?",
            text,
            artifact_id,
        )
    else:  # pragma: no cover - guards the table above
        raise AssertionError(state)


class Scn:
    """One matrix cell's scenario: an environment, an optional input capsule, and
    the request for the cell's route built against the *current* state."""

    def __init__(self, c: Cell, env: CapEnv, cap: Path | None) -> None:
        self.c, self.env, self.cap = c, env, cap
        self.invocation_id = new_uuid()
        self.out = out_for(env, c.transport, "cell.json") if c.family == "E" else None

    def base(self, **extra: Any) -> dict[str, Any]:
        if self.c.family == "E":
            return {
                "output": str(self.out),
                "invocation_id": self.invocation_id,
                **extra,
            }
        return {"input": str(self.cap), "invocation_id": self.invocation_id, **extra}

    def preview_action(self) -> str:
        return "preview_export" if self.c.family == "E" else "preview_import"

    def probe(self, **extra: Any) -> R:
        """The in-process preview of the same request in the current state."""
        return call_inproc(
            self.env.root, {**self.base(**extra), "action": self.preview_action()}
        )

    def request(self, **extra: Any) -> dict[str, Any]:
        base = self.base(**extra)
        if not self.c.final:
            return {**base, "action": self.preview_action()}
        probe = self.probe(**extra)
        digest = probe.data.get("digest") if probe.code == "OK" else None
        digest = digest or "a" * 64
        if self.c.family == "E":
            return {**base, "action": "export", "expected_digest": digest}
        revision = preview_store_revision(probe.data) if probe.code == "OK" else 0
        return {
            **base,
            "action": "import",
            "apply": True,
            "expected_digest": digest,
            "expected_store_revision": revision,
        }

    def call(self, *, cache: bool = True, artifact: bool = True, **extra: Any) -> R:
        return call(
            self.c.transport,
            self.env.root,
            self.request(**extra),
            cache=cache,
            artifact=artifact,
        )

    def cli_extra(self, *flags: str) -> Any:
        return cli_invoke([*cli_args(self.env.root, self.request()), *flags])


_SOURCE_CAPSULE: list[bytes] = []


def forged_capsule_for(env: CapEnv, tmp_path: Path) -> Path:
    """A capsule exported by another project, claiming `env`'s own origin pair, placed
    where every transport may read it. The exported bytes hold no path, so one export
    serves every cell."""
    if not _SOURCE_CAPSULE:
        src = make_env(tmp_path, "capsule-source")
        _SOURCE_CAPSULE.append(export_file(src, "src.json").read_bytes())
    target = env.exports / "in.json"
    target.write_bytes(
        _with_origin(_SOURCE_CAPSULE[0], env.project_id, env.worktree_id)
    )
    return target


def scenario(c: Cell, tmp_path: Path, **env_kwargs: Any) -> Scn:
    env = make_env(tmp_path, "cell", **env_kwargs)
    cap = forged_capsule_for(env, tmp_path) if c.family == "I" else None
    return Scn(c, env, cap)


def assert_unknown_option(result: Any, flag: str) -> None:
    """Click rejected `flag` itself (not a missing command): exit 2, `No such option`."""
    assert result.exit_code == 2, result.output[-600:]
    assert "No such option" in result.output, result.output[-600:]
    assert flag.split("=")[0] in result.output, result.output[-600:]


def expect_cli_exit2(sc: Scn, flag: str, value: str | None = None) -> None:
    leaf = {
        "preview_export": "preview-export",
        "export": "export",
        "preview_import": "preview-import",
        "import": "import",
    }[sc.c.route]
    helped = cli_invoke(["memory", "capsule", leaf, "--help"])
    assert helped.exit_code == 0, f"the {leaf} leaf exists: {helped.output[-300:]}"
    flags = [flag] + ([value] if value is not None else [])
    assert_unknown_option(sc.cli_extra(*flags), flag)


def rejected_field(res: R, name: str) -> None:
    assert res.code == "E_INPUT", res
    blob = json.dumps(res.raw)
    assert name in blob, (name, res)


# --- per-dimension handlers ---------------------------------------------------


def _h_access(c: Cell, tmp_path: Path) -> None:
    sc = scenario(c, tmp_path)
    env = sc.env
    if c.val == "policy":
        assert sc.call().code == "OK"
        return
    if c.val == "legacy_allowlist":
        if c.transport == "mcp":
            res = call_mcp(env.root, sc.request(), session_allowlist=[SRC])
            rejected_field(res, "session_allowlist")
        elif c.transport == "cli":
            expect_cli_exit2(sc, "--session", SRC)
        else:
            request = sc.request()
            with_allowlist = call_inproc(env.root, request, session_allowlist=[SRC])
            if not c.final:
                plain = call_inproc(env.root, request)
                assert (with_allowlist.status, with_allowlist.raw) == (
                    plain.status,
                    plain.raw,
                )
            assert with_allowlist.code == "OK", with_allowlist
        return
    # overlay
    owner = overlay_owner(env)
    if c.family == "E":
        assert env.store is not None
        overlay_root = env.data_root / "user"
        overlay_root.mkdir(parents=True, exist_ok=True)
        overlay_store = TypedArtifactStore(overlay_root)
        put_evidence(env, "ov1", owner=owner, source=OVERLAY_SRC, store=overlay_store)
        content = json.loads(row_of(env, "cp1")["content"])
        content["evidence_refs"] = [
            *content["evidence_refs"],
            {"artifact_id": "ov1", "version": 1},
        ]
        plant_content(env, "cp1", content)
        selectors: dict[str, Any] = {"selectors": {"include_personal": True}}
        denied = sc.call(**selectors)
        assert_denied(denied, "E_OWNER", "owner_not_granted")
        grant_overlay(env, ("overlay_read", "expand"))
        res = sc.call(**selectors)
        assert res.code == "OK", res
        if c.route == "export":
            capsule_doc = verify_rush_v1(sc.out.read_bytes())  # type: ignore[union-attr]
            assert "ov1" in [e["artifact_id"] for e in capsule_doc["evidence"]]
            assert capsule_doc["scope"]["personal_owner"] == owner_hex(owner)
        return
    selectors = {"selectors": {"owner_scope": owner.as_dict()}}
    denied = sc.call(**selectors)
    assert_denied(denied, "E_OWNER", "owner_not_granted")
    grant_overlay(env, ("list", "write"))
    res = sc.call(**selectors)
    assert res.code == "OK", res
    if c.route == "import":
        overlay_db = env.data_root / "user" / ".rush" / "memory.db"
        with contextlib.closing(sqlite3.connect(overlay_db)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM memory_artifacts WHERE trust_tier = 'IMPORTED'"
            ).fetchone()[0]
        assert count == 5
        assert not imported_rows(env), "nothing lands in the project store"


def _env_for_policy_state(c: Cell, tmp_path: Path) -> Scn:
    from rush.memory import authorization as auth

    if c.val == "missing_no_marker":
        sc = scenario(c, tmp_path, grant=False)
        auth.policy_path(data_root=sc.env.data_root).unlink(missing_ok=True)
        return sc
    sc = scenario(c, tmp_path)
    policy = auth.policy_path(data_root=sc.env.data_root)
    if c.val == "missing_marker":
        policy.unlink()
    elif c.val == "invalid":
        policy.write_bytes(b"{")
    return sc


def _h_policy_state(c: Cell, tmp_path: Path) -> None:
    sc = _env_for_policy_state(c, tmp_path)
    before = sc.env.effects()
    res = sc.call()
    if c.val == "ok":
        assert res.code == "OK", res
        return
    assert res.code == "E_PERMISSION", res
    if c.val == "missing_no_marker":
        assert res.reason == "policy_missing"
    elif c.val == "invalid":
        assert res.reason == "policy_invalid"
    else:
        assert isinstance(res.reason, str) and res.reason
    assert sc.env.effects() == before


def _h_mode(c: Cell, tmp_path: Path) -> None:
    """The capsule request has no `mode`: MCP/in-process get the strict `E_INPUT`, the
    CLI has no such option; in-process `include_archived` changes nothing."""
    sc = scenario(c, tmp_path)
    if c.val == "ordinary":
        assert sc.call().code == "OK"
        return
    key = "archive_mode" if c.val == "historical" else "mode"
    if c.transport == "cli":
        expect_cli_exit2(sc, "--" + key.replace("_", "-"), c.val)
    elif c.transport == "mcp":
        rejected_field(call_mcp(sc.env.root, {**sc.request(), key: c.val}), key)
    else:
        request = sc.request()
        historical = call_inproc(sc.env.root, request, include_archived=True)
        assert historical.code == "OK", historical
        if not c.final:
            plain = call_inproc(sc.env.root, request)
            assert (plain.status, plain.raw) == (historical.status, historical.raw)


def _h_missing_field(c: Cell, tmp_path: Path, field: str, value: Any) -> None:
    sc = scenario(c, tmp_path)
    before = sc.env.effects()
    if c.transport == "cli":
        expect_cli_exit2(
            sc, "--" + field, None if isinstance(value, bool) else str(value)
        )
    else:
        res = call(c.transport, sc.env.root, {**sc.request(), field: value})
        rejected_field(res, field)
    if not c.final:
        assert sc.env.effects() == before


def _h_representation(c: Cell, tmp_path: Path) -> None:
    _h_missing_field(c, tmp_path, "representation", c.val)


def _h_retrieval(c: Cell, tmp_path: Path) -> None:
    _h_missing_field(c, tmp_path, "retrieval", c.val)


def _h_ack(c: Cell, tmp_path: Path) -> None:
    _h_missing_field(c, tmp_path, "ack", c.val == "ack")


def _h_store(c: Cell, tmp_path: Path) -> None:
    if c.val == "present":
        sc = scenario(c, tmp_path)
        assert sc.call().code == "OK"
        return
    if c.val == "absent":
        sc = scenario(c, tmp_path, create_store=False)
        before = sc.env.effects()
        res = sc.call()
        if c.family == "E":
            assert_denied(res, "E_PERMISSION", "export_blocked")
            assert sc.env.effects() == before and not sc.env.db.exists()
            return
        assert res.code == "OK", res
        if c.route == "preview_import":
            assert preview_store_state(res.data) == "absent"
            assert preview_store_revision(res.data) == 0
            assert sc.env.effects() == before and not sc.env.db.exists()
        else:
            assert sc.env.db.exists() and len(imported_rows(sc.env)) == 5
        return
    sc = scenario(c, tmp_path, create_store=False)
    old_schema_store(sc.env)
    before = sc.env.effects()
    res = sc.call()
    if c.family == "E":
        assert res.code == "E_MIGRATION", res
    elif c.route == "preview_import":
        assert res.code == "OK", res
        assert preview_store_state(res.data) == "migration_required"
    else:
        assert res.code == "E_MIGRATION", res
    assert sc.env.effects() == before


def _h_apply(c: Cell, tmp_path: Path) -> None:
    sc = scenario(c, tmp_path)
    env = sc.env
    before = env.effects()
    if c.val == "preview":
        res = call(c.transport, env.root, {**sc.base(), "action": sc.preview_action()})
        assert res.code == "OK", res
        assert env.effects() == before
        return
    if c.route == "preview_export":
        res = call(
            c.transport,
            env.root,
            {**sc.base(), "action": "preview_export", "apply": True},
        )
        assert res.code == "E_INPUT" and "apply" in json.dumps(res.raw), res
        assert env.effects() == before
    elif c.route == "export":
        res = call(c.transport, env.root, {**sc.request(), "apply": True})
        assert res.code == "E_INPUT", res
        assert not sc.out.exists()  # type: ignore[union-attr]
        assert sc.call().code == "OK" and sc.out.exists()  # type: ignore[union-attr]
    elif c.route == "preview_import":
        res = call(
            c.transport,
            env.root,
            {**sc.base(), "action": "preview_import", "apply": True},
        )
        assert res.code == "E_INPUT", res
        assert env.effects() == before
    else:
        request = sc.request()
        request.pop("apply")
        res = call(c.transport, env.root, request)
        assert res.code == "E_INPUT" and "apply" in json.dumps(res.raw), res
        assert not imported_rows(env)
        assert sc.call().code == "OK" and len(imported_rows(env)) == 5


def _h_cache_write(c: Cell, tmp_path: Path) -> None:
    sc = scenario(c, tmp_path)
    if c.val == "on":
        assert sc.call(cache=True).code == "OK"
        return
    if c.route in ("preview_export", "preview_import"):
        assert sc.call(cache=False, artifact=False).code == "OK"
    elif c.route == "export":
        assert sc.call(cache=False, artifact=True).code == "OK"  # export is unaffected
        sc2 = scenario(c, tmp_path / "again")
        res = sc2.call(cache=True, artifact=False)
        assert res.status == "skipped" and res.raw["missing_permissions"] == [
            "--allow-artifact-write"
        ]
    else:
        res = sc.call(cache=False, artifact=True)
        assert res.status == "skipped" and res.raw["missing_permissions"] == [
            "--allow-cache-write"
        ]
        assert not imported_rows(sc.env)


def _h_grant_ops(c: Cell, tmp_path: Path) -> None:
    if c.val == "exact":
        sc = scenario(c, tmp_path)
        assert sc.call().code == "OK"
        return
    lacking = {
        "preview_export": "expand",
        "export": "expand",
        "preview_import": "list",
        "import": "write",
    }[c.route]
    ops = tuple(o for o in ALL_OPS if o != lacking)
    sc = scenario(c, tmp_path, ops=ops)
    before = sc.env.effects()
    res = sc.call()
    assert_denied(res, "E_PERMISSION", "operation_not_granted")
    assert sc.env.effects() == before


def _h_row_state(c: Cell, tmp_path: Path) -> None:
    if c.family == "E":
        task_ref: dict[str, Any] = {
            "selectors": {"task_ref": {"artifact_id": "cp1", "version": 1}}
        }
        sc = scenario(c, tmp_path / "task")
        set_state(sc.env, "cp1", "episodic", c.val)
        res = sc.call(**task_ref)
        if c.val == "active":
            assert res.code == "OK", res
            if c.route == "export":
                doc = verify_rush_v1(sc.out.read_bytes())  # type: ignore[union-attr]
                assert doc["manifest"]["selected"][0]["artifact_id"] == "cp1"
            return
        assert res.code == "E_NOT_VISIBLE", (c.val, res)
        ev = scenario(c, tmp_path / "evidence")
        set_state(ev.env, "ev1", "domain_knowledge", c.val)
        res = ev.call()
        assert_denied(res, "E_PERMISSION", "export_blocked")
        return
    sc = scenario(c, tmp_path)
    assert sc.env.store is not None
    local = sc.env.store.write(
        MemoryArtifact(
            id="local-c1",
            family="memory",
            subject="domain_knowledge",
            trust_tier="DERIVED",
            content={"kind": "constraint", "constraint_id": "c1", "text": "local copy"},
            source=SRC,
            created_at=time.time(),
            owner_scope=sc.env.owner,
        )
    )
    set_state(sc.env, local.id, "domain_knowledge", c.val)
    probe = sc.probe()
    assert probe.code == "OK", probe
    versions = probe.data.get("expected_versions")
    if versions is None:
        versions = probe.data["preview_binding"]["existing_versions"]
    if c.val == "active":
        assert versions == {"local-c1": 1}
    else:
        assert versions == {}
    assert sc.call().code == "OK"


def _h_capability_ids(c: Cell, tmp_path: Path) -> None:
    if c.family == "E":
        now = time.time()
        sc = scenario(c, tmp_path, seed=False)
        env = sc.env
        for name in ("ev1", "ev2", "evb"):
            put_evidence(env, name)
        put_checkpoint(
            env, "cp-a", task_id="t-a", created_at=now - 20, description="task a"
        )
        if c.val == "unselected":
            put_checkpoint(
                env,
                "cp-b",
                task_id="t-b",
                created_at=now - 10,
                description="task b",
                evidence_refs=[{"artifact_id": "evb", "version": 1}],
            )
            two = sc.call()  # two open tasks and no task_ref
            assert two.code == "E_INPUT" and two.reason == "task_ref_required", two
            put_checkpoint(
                env,
                "cp-b-end",
                task_id="t-b",
                created_at=now - 5,
                event_kind="task_end",
            )
            one = sc.call()  # exactly one open task left: its newest row
            assert one.code == "OK", one
            return
        put_checkpoint(
            env,
            "cp-b",
            task_id="t-b",
            created_at=now - 10,
            description="task b",
            evidence_refs=[{"artifact_id": "evb", "version": 1}],
        )
        res = sc.call(selectors={"task_ref": {"artifact_id": "cp-a", "version": 1}})
        assert res.code == "OK", res
        if c.route == "export":
            doc = verify_rush_v1(sc.out.read_bytes())  # type: ignore[union-attr]
            assert doc["task"]["description"] == "task a"
            assert [s["artifact_id"] for s in doc["manifest"]["selected"]] == [
                "cp-a",
                "ev1",
                "ev2",
            ]
        return
    sc = scenario(c, tmp_path)
    if c.val == "unselected":
        probe = sc.probe()
        assert probe.code == "OK"
        assert {r["applicability"] for r in probe.data["records"]} == {"pending"}
        assert sc.call().code == "OK"
        return
    if c.transport == "mcp":
        res = sc.call(confirm_constraint_ids=["c1"])
        assert_denied(res, "E_PERMISSION", "constraint_confirmation_requires_cli")
        return
    res = sc.call(confirm_constraint_ids=["c1"])
    assert res.code == "OK", res
    probe = sc.probe(confirm_constraint_ids=["c1"])
    assert [r["applicability"] for r in probe.data["records"]] == [
        "pending",
        "active",
        "pending",
        "pending",
        "pending",
    ]


# --- G2a intersections ---------------------------------------------------------


def _x_legacy_with_policy(c: Cell, tmp_path: Path) -> None:
    """A policy grant AND a legacy allowlist on one request: the allowlist is never an
    access form of the capsule, whatever the policy holds."""
    sc = scenario(c, tmp_path)
    env = sc.env
    before = env.effects()
    if c.transport == "mcp":
        for allowlist in ([SRC], []):
            res = call_mcp(env.root, sc.request(), session_allowlist=allowlist)
            rejected_field(res, "session_allowlist")
        assert env.effects() == before
        return
    if c.transport == "cli":
        expect_cli_exit2(sc, "--session", SRC)
        assert env.effects() == before
        return
    request = sc.request()
    if c.final:
        got = call_inproc(env.root, request, session_allowlist=["unrelated"])
        assert got.code == "OK", got
        return
    plain = call_inproc(env.root, request)
    assert plain.code == "OK", plain
    for allowlist in ([SRC], [], ["unrelated"]):
        got = call_inproc(env.root, request, session_allowlist=allowlist)
        assert (got.status, got.raw) == (plain.status, plain.raw), allowlist
    assert env.effects() == before


def _x_historical_compound(c: Cell, tmp_path: Path) -> None:
    """Historical access with a compound `{history, expand}` grant: the capsule request
    still has no historical field."""
    sc = scenario(c, tmp_path, ops=("history", "expand", "list", "write"))
    env = sc.env
    before = env.effects()
    if c.transport == "cli":
        expect_cli_exit2(sc, "--archive-mode", "historical")
        assert env.effects() == before
        return
    if c.transport == "mcp":
        for key in ("archive_mode", "mode"):
            res = call_mcp(env.root, {**sc.request(), key: "historical"})
            rejected_field(res, key)
        assert env.effects() == before
        return
    request = sc.request()
    if c.final:
        got = call_inproc(env.root, request, include_archived=True)
        assert got.code == "OK", got
        return
    plain = call_inproc(env.root, request)
    got = call_inproc(env.root, request, include_archived=True)
    assert plain.code == "OK" and (got.status, got.raw) == (plain.status, plain.raw)
    assert env.effects() == before


def _x_no_store_denial(c: Cell, tmp_path: Path) -> None:
    """No store AND no grant: the policy denial wins and nothing is created."""
    from rush.memory import authorization as auth

    sc = scenario(c, tmp_path, create_store=False, grant=False)
    env = sc.env
    auth.policy_path(data_root=env.data_root).unlink(missing_ok=True)
    before = env.effects()
    rush_before = tree_state(env.root / ".rush")  # register_project already made it
    res = sc.call()
    assert_denied(res, "E_PERMISSION", "policy_missing")
    assert tree_state(env.root / ".rush") == rush_before
    assert not env.db.exists()
    assert env.effects() == before


def _x_no_store_admission(c: Cell, tmp_path: Path) -> None:
    """No store AND an inadmissible request: admission fails before any read."""
    sc = scenario(c, tmp_path, create_store=False)
    env = sc.env
    before = env.effects()
    rush_before = tree_state(env.root / ".rush")  # register_project already made it
    res = sc.call(max_bytes=1048577)
    assert_denied(res, "E_INPUT", "budget_above_hard_cap")
    assert tree_state(env.root / ".rush") == rush_before
    assert not env.db.exists()
    assert env.effects() == before


def _x_overlay_revocation(c: Cell, tmp_path: Path) -> None:
    """The overlay grant is revoked between discovery and the final call."""
    from rush.memory import authorization as auth

    sc = scenario(c, tmp_path)
    env = sc.env
    owner = overlay_owner(env)
    if c.family == "E":
        overlay_root = env.data_root / "user"
        overlay_root.mkdir(parents=True, exist_ok=True)
        overlay_store = TypedArtifactStore(overlay_root)
        put_evidence(env, "ov1", owner=owner, source=OVERLAY_SRC, store=overlay_store)
        content = json.loads(row_of(env, "cp1")["content"])
        content["evidence_refs"] = [
            *content["evidence_refs"],
            {"artifact_id": "ov1", "version": 1},
        ]
        plant_content(env, "cp1", content)
        extra: dict[str, Any] = {"selectors": {"include_personal": True}}
        grant = grant_for(
            env.root,
            owner,
            env.data_root,
            sources=(OVERLAY_SRC, IMPORT_SRC),
            ops=("overlay_read", "expand"),
        )
    else:
        extra = {"selectors": {"owner_scope": owner.as_dict()}}
        grant = grant_for(
            env.root,
            owner,
            env.data_root,
            sources=(OVERLAY_SRC, IMPORT_SRC),
            ops=("list", "write"),
        )
    assert sc.probe(**extra).code == "OK", "the overlay grant admits the request"
    request = sc.request(**extra)
    auth.revoke_memory_scope(
        grant_id=grant["grant_id"],
        expected_policy_revision=revision_of(env.data_root),
        consent=True,
        data_root=env.data_root,
    )
    before = env.effects()
    res = call(c.transport, env.root, request)
    assert_denied(res, "E_PERMISSION", "revoked")
    if sc.out is not None:
        assert not sc.out.exists()
    assert not imported_rows(env)
    if c.family == "I":
        assert not (env.data_root / "user" / ".rush" / "memory.db").exists()
    assert env.effects() == before


def _x_selected_id(c: Cell, tmp_path: Path) -> None:
    """A selected identifier outside the caller's authority or preview binding."""
    sc = scenario(c, tmp_path)
    env = sc.env
    if c.family == "E":
        put_checkpoint(
            env,
            "cp-foreign",
            task_id="t-foreign",
            created_at=time.time() - 5,
            worktree_id="0" * 64,
        )
        before = env.effects()
        res = sc.call(
            selectors={"task_ref": {"artifact_id": "cp-foreign", "version": 1}}
        )
        assert_denied(res, "E_NOT_VISIBLE")
        assert env.effects() == before
        return
    if not c.final:
        before = env.effects()
        res = sc.call(confirm_constraint_ids=["unknown"])
        if c.transport == "mcp":
            assert_denied(res, "E_PERMISSION", "constraint_confirmation_requires_cli")
        else:
            assert res.code == "E_INPUT", res
        assert env.effects() == before
        return
    # a preview binds the confirmed set: other ids on the final call conflict (MCP
    # cannot confirm at all)
    bound = sc.probe(confirm_constraint_ids=["c1"])
    assert bound.code == "OK", bound
    request = {
        **sc.base(confirm_constraint_ids=["unknown"]),
        "action": "import",
        "apply": True,
        "expected_digest": bound.data["digest"],
        "expected_store_revision": preview_store_revision(bound.data),
    }
    before = env.effects()
    res = call(c.transport, env.root, request)
    if c.transport == "mcp":
        assert_denied(res, "E_PERMISSION", "constraint_confirmation_requires_cli")
    else:
        assert_denied(res, "E_VERSION", "recovery_required")
    assert env.effects() == before and not imported_rows(env)


def _x_cache_write_ask_only(c: Cell, tmp_path: Path) -> None:
    """The write permission flag is on, but the grant holds only `ask`."""
    sc = scenario(c, tmp_path, ops=("ask",))
    before = sc.env.effects()
    res = sc.call(cache=True, artifact=True)
    assert_denied(res, "E_PERMISSION", "operation_not_granted")
    if sc.out is not None:
        assert not sc.out.exists()
    assert sc.env.effects() == before


def _x_stale_view(c: Cell, tmp_path: Path) -> None:
    """Discovery and the final read are two views of the store and of the files: a
    change between them never lets the stale view authorize delivery."""
    sc = scenario(c, tmp_path)
    env = sc.env
    if c.family == "E":
        if not c.final:
            first = sc.probe()
            put_checkpoint(env, "cp-newer", created_at=time.time())
            second = sc.probe()
            assert first.code == "OK" and second.code == "OK", (first, second)
            assert first.data["digest"] != second.data["digest"]
            return
        request = sc.request()
        put_checkpoint(env, "cp-newer", created_at=time.time())
        before = env.effects()
        res = call(c.transport, env.root, request)
        assert_denied(res, "E_VERSION", "recovery_required")
        assert not sc.out.exists() and env.effects() == before  # type: ignore[union-attr]
        # an evidence row that stops being usable after discovery is never exported
        hidden = scenario(c, tmp_path / "hidden")
        request = hidden.request()
        set_state(hidden.env, "ev2", "domain_knowledge", "archived")
        before = hidden.env.effects()
        res = call(c.transport, hidden.env.root, request)
        assert_denied(res, "E_PERMISSION", "export_blocked")
        assert not hidden.out.exists()  # type: ignore[union-attr]
        assert hidden.env.effects() == before
        return
    if not c.final:
        first = sc.probe()
        put_evidence(env, f"late-{time.time_ns()}")
        second = sc.probe()
        assert first.code == "OK" and second.code == "OK", (first, second)
        assert preview_store_revision(second.data) > preview_store_revision(first.data)
        return
    request = sc.request()
    put_evidence(env, f"late-{time.time_ns()}")
    before = env.effects()
    res = call(c.transport, env.root, request)
    assert_denied(res, "E_VERSION", "store_changed")
    assert env.effects() == before and not imported_rows(env)
    # the capsule file is a second view: bytes replaced after discovery are refused
    replaced = scenario(c, tmp_path / "replaced")
    request = replaced.request()
    assert replaced.cap is not None
    replaced.cap.write_bytes(
        mutated_capsule(
            replaced.cap.read_bytes(),
            lambda d: d["task"].__setitem__("description", "replaced after discovery"),
        )
    )
    before = replaced.env.effects()
    res = call(c.transport, replaced.env.root, request)
    assert_denied(res, "E_VERSION", "recovery_required")
    assert replaced.env.effects() == before and not imported_rows(replaced.env)


_INTERSECTION_HANDLERS = {
    "legacy_with_policy": _x_legacy_with_policy,
    "historical_compound": _x_historical_compound,
    "no_store_denial": _x_no_store_denial,
    "no_store_admission": _x_no_store_admission,
    "overlay_revocation": _x_overlay_revocation,
    "selected_id": _x_selected_id,
    "cache_write_ask_only": _x_cache_write_ask_only,
    "stale_view": _x_stale_view,
}


def _h_intersection(c: Cell, tmp_path: Path) -> None:
    _INTERSECTION_HANDLERS[c.val](c, tmp_path)


_HANDLERS = {
    "intersection": _h_intersection,
    "access": _h_access,
    "policy_state": _h_policy_state,
    "mode": _h_mode,
    "representation": _h_representation,
    "retrieval": _h_retrieval,
    "store": _h_store,
    "apply": _h_apply,
    "cache_write": _h_cache_write,
    "grant_ops": _h_grant_ops,
    "row_state": _h_row_state,
    "ack": _h_ack,
    "capability_ids": _h_capability_ids,
}


# --- bridge, mapping, restricted, dashboard, tui rows -------------------------------


def _bridge_env(c: Cell, tmp_path: Path) -> CapEnv:
    from rush.memory import authorization as auth

    if c.dim == "policy_state" and c.val == "missing_no_marker":
        return make_env(tmp_path, "cell", grant=False)
    env = make_env(
        tmp_path, "cell", create_store=c.dim != "store" or c.val == "present"
    )
    policy = auth.policy_path(data_root=env.data_root)
    if c.dim == "policy_state" and c.val == "missing_marker":
        policy.unlink()
    if c.dim == "policy_state" and c.val == "invalid":
        policy.write_bytes(b"{")
    if c.dim == "store" and c.val == "old_schema":
        old_schema_store(env)
    return env


def _h_bridge(c: Cell, tmp_path: Path) -> None:
    env = _bridge_env(c, tmp_path)
    before = env.effects()
    request: dict[str, Any] = {"action": "bridge"}
    if c.dim == "apply" and c.val == "apply":
        request["apply"] = True
    if c.transport == "cli":
        extra: list[str] = []
        if c.dim == "apply" and c.val == "apply":
            extra = ["--apply"]
        result = cli_invoke([*cli_args(env.root, {"action": "bridge"}), *extra])
        assert result.exit_code == 2, result.output[-500:]
        res = R(json.loads(result.stdout))
    else:
        res = call(c.transport, env.root, request)
    assert res.code == "E_INPUT" and res.data["field"] == "input", (c.id, res)
    assert env.effects() == before


def _h_mapping(c: Cell, tmp_path: Path) -> None:
    """`rush memory capsule mapping create|revoke` (CLI only)."""
    from rush.memory import authorization as auth

    src = make_env(tmp_path, "mapsrc")
    cap = export_file(src, "map.json")
    origin = json.loads(cap.read_bytes())["origin"]
    dest = make_env(
        tmp_path,
        "cell",
        seed=False,
        create_store=c.dim != "store" or c.val == "present",
    )
    if c.dim == "store" and c.val == "old_schema":
        old_schema_store(dest)
    policy = auth.policy_path(data_root=dest.data_root)

    existing: str | None = None
    wants_existing = c.route == "mapping_revoke" and (
        c.dim != "policy_state" or c.val == "ok"
    )
    if wants_existing:
        existing = approved_mapping(dest, origin)
    if c.dim == "grant_ops" and c.val == "missing_one":
        grant_for(dest.root, dest.owner, dest.data_root, ops=("ask", "expand", "list"))
    if c.dim == "policy_state":
        if c.val == "missing_no_marker":
            policy.unlink()
            marker = dest.root / ".rush" / "memory-policy.required"
            if marker.exists():
                marker.unlink()
        elif c.val == "missing_marker":
            policy.unlink()
        elif c.val == "invalid":
            policy.write_bytes(b"{")
    revision = revision_of(dest.data_root) if policy.exists() else 0
    before = sha(policy.read_bytes()) if policy.exists() else None

    def act(*flags: str) -> tuple[Any, R]:
        if c.route == "mapping_create":
            return mapping_cli(
                "create",
                "--input",
                str(cap),
                "--expected-policy-revision",
                str(revision),
                *flags,
                project=dest.root,
            )
        return mapping_cli(
            "revoke",
            "--mapping-id",
            existing or new_uuid(),
            "--expected-policy-revision",
            str(revision),
            *flags,
        )

    if c.dim in ("mode", "representation", "retrieval", "ack"):
        flag = "--" + c.dim.replace("_", "-")
        result, _res = act(flag, c.val)
        assert_unknown_option(result, flag)
        return
    if c.dim == "access":
        if c.val == "legacy_allowlist":
            result, _res = act("--session", SRC)
            assert_unknown_option(result, "--session")
        elif c.val == "overlay":
            owner = overlay_owner(dest)
            if c.route == "mapping_create":
                result, res = act(
                    "--owner",
                    f"{owner.kind}:{owner.id}",
                    "--approve",
                    "--allow-cache-write",
                )
                assert_denied(res, "E_OWNER", "owner_not_granted")
            else:
                result, _res = act("--owner", f"{owner.kind}:{owner.id}")
                assert_unknown_option(result, "--owner")
            assert sha(policy.read_bytes()) == before
        else:
            result, res = act("--allow-cache-write")
            assert res.code == "OK", res
        return
    if c.dim == "policy_state":
        if c.val == "ok":
            result, res = act("--allow-cache-write")
            assert res.code == "OK", res
            return
        result, res = act("--approve", "--allow-cache-write")
        if c.val == "invalid":
            assert res.code == "E_POLICY_INVALID", res
        else:
            assert res.code == "E_PERMISSION", res
            if c.val == "missing_no_marker" and c.route == "mapping_create":
                assert res.reason == "policy_missing"
        return
    if c.dim == "apply":
        if c.val == "preview":
            result, res = act("--allow-cache-write")
            assert res.code == "OK", res
            assert sha(policy.read_bytes()) == before
        else:
            result, res = act("--approve", "--allow-cache-write")
            assert res.code == "OK", res
            assert sha(policy.read_bytes()) != before
        return
    if c.dim == "cache_write":
        if c.val == "on":
            result, res = act("--approve", "--allow-cache-write")
            assert res.code == "OK", res
        else:
            result, res = act("--approve")
            assert res.status == "skipped" and "--allow-cache-write" in json.dumps(
                res.result
            )
            assert sha(policy.read_bytes()) == before
        return
    result, res = act("--approve", "--allow-cache-write")
    if c.dim == "grant_ops" and c.val == "missing_one" and c.route == "mapping_create":
        assert_denied(res, "E_PERMISSION", "operation_not_granted")
        assert sha(policy.read_bytes()) == before
        return
    # store (any state), row_state, capability_ids, grant_ops exact: the store is
    # not read, so the mapping command is unaffected.
    assert res.code == "OK", (c.id, res)


def _h_restricted(c: Cell, tmp_path: Path) -> None:
    from rush.mcp_support.tool_registry import build_memory_bridge_handler

    env = make_env(tmp_path)
    before = env.effects()
    handler = build_memory_bridge_handler(root=env.root, session_id="s", capability="c")
    res = handler(
        "capsule", {"action": "preview_export", "output": str(env.outside / "r.json")}
    )
    assert res["code"] == "E_PERMISSION"
    assert env.effects() == before


def _h_dashboard(c: Cell, tmp_path: Path) -> None:
    import urllib.error
    import urllib.request

    from rush.dashboard.server import (
        ALLOWED_ACTIONS,
        create_dashboard_server,
        stop_all_dashboard_contexts,
    )

    assert "memory_capsule" not in ALLOWED_ACTIONS
    assert not any("capsule" in action for action in ALLOWED_ACTIONS)
    project = json.loads(
        (
            Path(__file__).parent / "fixtures" / "dashboard" / "project_a.json"
        ).read_text()
    )
    server, ctx, token = create_dashboard_server({"project-a": project})
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    try:
        base_url = ctx.launch_origin

        def post(path: str, headers: dict[str, str], body: bytes = b"") -> Any:
            req = urllib.request.Request(
                base_url + path, data=body, headers=headers, method="POST"
            )
            try:
                return urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as exc:
                return exc

        session = post("/api/session", {"Authorization": f"Bearer {token}"})
        assert session.status == 200
        csrf = json.loads(session.read())["csrf_token"]
        cookie = session.headers.get("Set-Cookie").split(";")[0]
        headers = {
            "Cookie": cookie,
            "X-Rush-CSRF": csrf,
            "Origin": base_url,
            "Content-Type": "application/json",
        }
        before = tree_state(default_data_root())
        reply = post(
            "/api/projects/project-a/actions",
            headers,
            json.dumps(
                {
                    "schema_version": 1,
                    "operation": "memory_capsule",
                    "request_id": "r-1",
                }
            ).encode(),
        )
        assert reply.status == 400
        assert json.loads(reply.read())["error"]["code"] == "unknown_operation"
        assert tree_state(default_data_root()) == before
    finally:
        server.shutdown()
        server.server_close()
        stop_all_dashboard_contexts()


def _h_tui(c: Cell, tmp_path: Path) -> None:
    import ast

    import rush.tui as tui_module

    tree = ast.parse(Path(tui_module.__file__).read_text(encoding="utf-8"))
    # 72-T07 R13: the TUI import review is the only capsule consumer. It names the
    # `capsule` operation solely as `memory_run(operation="capsule", request={"action":
    # "preview_import" | "import", ...})`; it never names `memory_capsule`, an export,
    # bridge, mapping or grant action, or the operation anywhere else.
    allowed_actions = {"preview_import", "import"}
    sanctioned: set[int] = set()
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        kwargs = {kw.arg: kw.value for kw in node.keywords}
        operation = kwargs.get("operation")
        if not (isinstance(operation, ast.Constant) and operation.value == "capsule"):
            continue
        request = kwargs.get("request")
        action = None
        if isinstance(request, ast.Dict):
            for key, value in zip(request.keys, request.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "action"
                    and isinstance(value, ast.Constant)
                ):
                    action = value.value
        if action in allowed_actions:
            sanctioned.add(operation.lineno)
        else:
            offenders.append(operation.lineno)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and node.value in ("capsule", "memory_capsule")
            and node.lineno not in sanctioned
        ):
            offenders.append(node.lineno)
    assert offenders == [], f"tui.py names a capsule route at lines {offenders}"


def run_cell(c: Cell, tmp_path: Path) -> None:
    if c.transport == "mcp_restricted":
        return _h_restricted(c, tmp_path)
    if c.transport == "dashboard":
        return _h_dashboard(c, tmp_path)
    if c.transport == "tui":
        return _h_tui(c, tmp_path)
    if c.family == "bridge":
        return _h_bridge(c, tmp_path)
    if c.family in ("mapping_create", "mapping_revoke"):
        return _h_mapping(c, tmp_path)
    return _HANDLERS[c.dim](c, tmp_path)


def _cell_param(c: Cell) -> Any:
    return pytest.param(c, id=c.id)


@pytest.mark.parametrize("cell", [_cell_param(c) for c in CODEC_CELLS])
def test_codec_route_mode_matrix(cell: Cell, tmp_path: Path) -> None:
    run_cell(cell, tmp_path)


# G2a: the producer matrices (`test_t02_route_mode_matrix` .. `test_t06_route_mode_matrix`)
# each carry staged capsule/import cells that CODEC flips into real cells. Each
# producer matrix runs the CODEC cells of the dimensions it owns; together the five
# own every dimension of the G2 table exactly once.
PRODUCER_FLIPS: dict[str, tuple[str, ...]] = {
    "t02": ("representation", "retrieval", "ack", "mode"),
    "t03": ("capability_ids", "row_state"),
    "t04": ("apply", "grant_ops", "store"),
    "t05": ("access", "cache_write"),
    "t06": ("policy_state", "intersection"),
}


def flip_params(task: str) -> list[Any]:
    dims = PRODUCER_FLIPS[task]
    return [_cell_param(c) for c in CODEC_CELLS if c.dim in dims]


def test_producer_flips_cover_every_dimension() -> None:
    owned = [d for dims in PRODUCER_FLIPS.values() for d in dims]
    assert len(owned) == len(set(owned)), "a dimension is owned by two producers"
    assert set(owned) == {*DIMENSIONS, "intersection"}
    for task in PRODUCER_FLIPS:
        assert flip_params(task), task


def test_codec_matrix_has_no_producer_staged_cells() -> None:
    """After CODEC no capsule/import cell is a producer-staged `E_INPUT` placeholder:
    every route x dimension x value of the G2 table is a real, uniquely named cell."""
    ids = [c.id for c in CODEC_CELLS]
    assert len(ids) == len(set(ids))
    assert not any("producer" in i for i in ids)
    per_route = sum(len(v) for v in DIMENSIONS.values())
    for transport in TRANSPORTS:
        for route in (*EXPORT_ROUTES, *IMPORT_ROUTES, "bridge"):
            got = [
                c for c in CODEC_CELLS if c.transport == transport and c.route == route
            ]
            extra = 0 if route == "bridge" else len(INTERSECTIONS)
            assert len(got) == per_route + extra, (transport, route)
            if route != "bridge":
                assert {c.val for c in got if c.dim == "intersection"} == set(
                    INTERSECTIONS
                ), (transport, route)
    assert {c.route for c in CODEC_CELLS if c.transport == "cli"} >= {
        "mapping_create",
        "mapping_revoke",
    }


# =============================================================================
# G4: trust-boundary inputs (`test_codec_trust_boundary_inputs`)
# =============================================================================
#
# Rows are request fields, CLI options, policy helpers and input-byte classes;
# columns are the hostile value classes of §5.0 G4. Every rejection names its
# exact code, leaves every file unchanged, and only declared exception types
# escape (a Python traceback fails the test, it is never an accepted outcome).

NAN = float("nan")
STR_CLASSES: tuple[tuple[str, Any], ...] = (
    ("wrong_type", 5),
    ("bool_as_int", True),
    ("huge_int", 10**400),
    ("nan", NAN),
    ("nul", "a\x00b"),
    ("lone_surrogate", "\ud800"),
    ("cc_cf", "a\u202eb"),
    ("list", ["x"]),
    ("dict", {"k": "v"}),
)
INT_CLASSES: tuple[tuple[str, Any], ...] = (
    ("string", "10"),
    ("bool", True),
    ("nan", NAN),
    ("float", 1.5),
)


def _row(
    cls: str, value: Any, code: str = "E_INPUT", reason: str | None = None
) -> tuple[str, Any, str, str | None]:
    return (cls, value, code, reason)


def _str_rows(*, path_reason: bool = False) -> list[tuple[str, Any, str, str | None]]:
    rows = []
    for cls, value in STR_CLASSES:
        reason = (
            "path_invalid"
            if path_reason and cls in ("nul", "lone_surrogate", "cc_cf")
            else None
        )
        rows.append(_row(cls, value, "E_INPUT", reason))
    return rows


def _group(
    action: str, path: str, rows: list[tuple[str, Any, str, str | None]], **kw: Any
) -> dict[str, Any]:
    return {"action": action, "path": path, "rows": rows, **kw}


def field_groups() -> dict[str, dict[str, Any]]:
    uuid_value = new_uuid()
    return {
        "action": _group(
            "preview_export", "action", [*_str_rows(), _row("unknown", "frobnicate")]
        ),
        "format": _group(
            "preview_export", "format", [*_str_rows(), _row("pas_v2", "pas_v2")]
        ),
        "input": _group(
            "preview_import",
            "input",
            [
                *_str_rows(path_reason=True),
                _row("missing_file", "@missing", "E_INPUT", "capsule_invalid"),
                _row("directory", "@directory", "E_INPUT", "capsule_invalid"),
                _row(
                    "lone_surrogate_parent",
                    "@surrogate-parent",
                    "E_INPUT",
                    "path_invalid",
                ),
            ],
        ),
        "output": _group(
            "preview_export",
            "output",
            [
                *_str_rows(path_reason=True),
                _row(
                    "parent_missing", "@no-parent", "E_INPUT", "output_parent_missing"
                ),
                _row(
                    "lone_surrogate_parent",
                    "@surrogate-parent",
                    "E_INPUT",
                    "path_invalid",
                ),
            ],
        ),
        "max_bytes": _group(
            "preview_export",
            "max_bytes",
            [
                *(_row(c, v) for c, v in INT_CLASSES),
                _row("zero", 0),
                _row("negative", -1),
                _row("huge_int", 10**400, "E_INPUT", "budget_above_hard_cap"),
                _row("over_cap", 1048577, "E_INPUT", "budget_above_hard_cap"),
            ],
        ),
        "max_tokens": _group(
            "preview_export",
            "max_tokens",
            [
                *(_row(c, v) for c, v in INT_CLASSES),
                _row("zero", 0),
                _row("negative", -1),
                _row("huge_int", 10**400, "E_INPUT", "budget_above_hard_cap"),
                _row("over_cap", 131073, "E_INPUT", "budget_above_hard_cap"),
            ],
        ),
        "mapping_id": _group(
            "preview_import",
            "mapping_id",
            [
                *_str_rows(),
                _row("uppercase", uuid_value.upper()),
                _row("not_a_uuid", "mapping"),
                _row("unknown", uuid_value, "E_PERMISSION", "mapping_unknown"),
            ],
        ),
        "invocation_id": _group(
            "preview_export",
            "invocation_id",
            [
                *_str_rows(),
                _row("uppercase", uuid_value.upper()),
                _row("braced", "{" + uuid_value + "}"),
                _row("simple", uuid_value.replace("-", "")),
            ],
        ),
        "expected_digest": _group(
            "export",
            "expected_digest",
            [
                *_str_rows(),
                _row("uppercase_hex", "A" * 64),
                _row("short", "ab"),
                _row("mismatch", "f" * 64, "E_VERSION", "recovery_required"),
            ],
        ),
        "expected_store_revision": _group(
            "import",
            "expected_store_revision",
            [
                *(_row(c, v) for c, v in INT_CLASSES),
                _row("huge_int", 10**400),
                _row("negative", -1),
                _row("mismatch", 10**6, "E_VERSION", "store_changed"),
            ],
        ),
        "confirm_constraint_ids": _group(
            "preview_import",
            "confirm_constraint_ids",
            [
                _row("not_a_list", "c1"),
                _row("bool_element", [True]),
                _row("huge_element", [10**400]),
                _row("nan_element", [NAN]),
                _row("nul_element", ["a\x00b"]),
                _row("surrogate_element", ["\ud800"]),
                _row("cc_cf_element", ["a\u202eb"]),
                _row("empty_string", [""]),
                _row("duplicates", ["c1", "c1"]),
            ],
        ),
        "apply": _group(
            "import",
            "apply",
            [
                _row("string", "true"),
                _row("int", 1),
                _row("huge_int", 10**400),
                _row("nan", NAN),
            ],
        ),
        "task_ref": _group(
            "preview_export",
            "selectors.task_ref",
            [
                _row("string", "cp1"),
                _row("list", ["cp1", 1]),
                _row("version_bool", {"artifact_id": "cp1", "version": True}),
                _row("version_huge", {"artifact_id": "cp1", "version": 10**400}),
                _row("version_nan", {"artifact_id": "cp1", "version": NAN}),
                _row("version_string", {"artifact_id": "cp1", "version": "1"}),
                _row("version_zero", {"artifact_id": "cp1", "version": 0}),
                _row("id_nul", {"artifact_id": "a\x00b", "version": 1}),
                _row("id_surrogate", {"artifact_id": "\ud800", "version": 1}),
                _row("id_cc_cf", {"artifact_id": "a\u202eb", "version": 1}),
                _row("extra_key", {"artifact_id": "cp1", "version": 1, "extra": 1}),
                _row("missing_version", {"artifact_id": "cp1"}),
            ],
        ),
        "owner_scope": _group(
            "preview_export",
            "selectors.owner_scope",
            [
                _row("string", "alice"),
                _row("bool", True),
                _row("huge_int", 10**400),
                _row("nan", NAN),
                _row("id_nul", {"kind": "user", "id": "a\x00b"}),
                _row("id_surrogate", {"kind": "user", "id": "\ud800"}),
                _row("id_cc_cf", {"kind": "user", "id": "a\u202eb"}),
                _row("unhashable_kind", {"kind": ["user"], "id": "x"}),
                _row("unknown_kind", {"kind": "robot", "id": "x"}),
                _row("kind_dict", {"kind": {"user": 1}, "id": "x"}),
                _row("kind_none", {"kind": None, "id": "x"}),
                _row("id_list", {"kind": "user", "id": ["x"]}),
                _row("id_dict", {"kind": "user", "id": {"k": "v"}}),
                _row("id_none", {"kind": "user", "id": None}),
                _row("missing_id", {"kind": "user"}),
                _row("extra_key", {"kind": "user", "id": "x", "extra": 1}),
                _row("empty_object", {}),
                _row("ungranted_owner", BOB.as_dict(), "E_OWNER", "owner_not_granted"),
            ],
        ),
        "sources": _group(
            "preview_export",
            "selectors.sources",
            [
                _row("string", SRC),
                _row("bool_element", [True]),
                _row("huge_element", [10**400]),
                _row("nan_element", [NAN]),
                _row("nul_element", ["a\x00b"]),
                _row("surrogate_element", ["\ud800"]),
                _row("cc_cf_element", ["a\u202eb"]),
                _row("duplicates", [SRC, SRC]),
                _row("padded_leading", [" " + SRC]),
                _row("padded_trailing", [SRC + " "]),
                _row("wildcard", ["*"]),
                _row("family_wildcard", ["capsule:*"]),
                _row("embedded_wildcard", ["capsule-*"]),
                _row("empty_element", [""]),
                _row("control_element", ["a\x07b"]),
                _row("none_element", [None]),
                _row("list_element", [["x"]]),
                _row("dict_element", [{"k": "v"}]),
                _row(
                    "ungranted_source", ["not-granted"], "E_SCOPE", "source_not_granted"
                ),
            ],
        ),
        "include_personal": _group(
            "preview_export",
            "selectors.include_personal",
            [
                _row("string", "yes"),
                _row("int", 1),
                _row("huge_int", 10**400),
                _row("nan", NAN),
            ],
        ),
        "include_personal_on_import": _group(
            "preview_import",
            "selectors.include_personal",
            [_row("true_on_import", True)],
        ),
    }


def _set_path(request: dict[str, Any], path: str, value: Any) -> None:
    node = request
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _field_env(tmp_path: Path) -> tuple[CapEnv, Path]:
    env = make_env(tmp_path)
    cap = export_file(env, "claimed-src.json", transport="mcp")
    return env, cap


def _base_request(
    env: CapEnv, cap: Path, action: str, transport: str
) -> dict[str, Any]:
    out = out_for(env, transport, "g4.json")
    inv = new_uuid()
    if action in ("preview_export",):
        return {"action": action, "output": str(out), "invocation_id": inv}
    if action == "export":
        return {
            "action": action,
            "output": str(out),
            "invocation_id": inv,
            "expected_digest": "a" * 64,
        }
    base = {"input": str(cap), "invocation_id": inv}
    if action == "preview_import":
        return {"action": action, **base}
    preview = call_inproc(env.root, {"action": "preview_import", **base})
    assert preview.code == "OK", preview
    return {
        "action": "import",
        "apply": True,
        "expected_digest": preview.data["digest"],
        "expected_store_revision": preview_store_revision(preview.data),
        **base,
    }


def _resolve_value(value: Any, env: CapEnv, cap: Path) -> Any:
    if value == "@missing":
        return str(env.exports / "missing.json")
    if value == "@directory":
        return str(env.exports)
    if value == "@no-parent":
        return str(env.exports / "no-such-dir" / "g4.json")
    if value == "@surrogate-parent":
        return str(env.exports / "d\ud800" / "g4.json")
    return value


def _run_group(transport: str, group: str, tmp_path: Path) -> None:
    spec = field_groups()[group]
    env, cap = _field_env(tmp_path)
    before = env.effects()
    for cls, value, code, reason in spec["rows"]:
        if transport == "mcp" and cls in spec.get("mcp_override", {}):
            code, reason = spec["mcp_override"][cls]
        request = _base_request(env, cap, spec["action"], transport)
        _set_path(request, spec["path"], _resolve_value(value, env, cap))
        # a path under the project root when the transport is MCP
        res = call(transport, env.root, request)
        label = (transport, group, cls)
        assert res.code == code, (label, res)
        if reason is not None and not (
            transport == "mcp"
            and code == "E_INPUT"
            and cls.startswith(("nul", "lone_surrogate", "cc_cf"))
        ):
            assert res.reason == reason, (label, res)
        assert env.effects() == before, label
    assert group


def _group_params() -> list[Any]:
    params = []
    for transport in ("mcp", "inproc"):
        for group in field_groups():
            params.append(pytest.param(transport, group, id=f"{transport}-{group}"))
    return params


# --- CLI options ------------------------------------------------------------------


def _run_cli_option(option: str, tmp_path: Path) -> None:
    env, cap = _field_env(tmp_path)
    before = env.effects()
    out = env.outside / "cli-g4.json"
    base = [
        "memory",
        "capsule",
        "preview-export",
        "--project",
        str(env.root),
        "--output",
        str(out),
        "--json",
    ]
    cases: list[tuple[str, list[str], str]] = []
    if option == "task-ref":
        for value in ("nocolon", "id:notint", "id:1.5"):
            cases.append((value, ["--task-ref", value], "click"))
        cases.append(("id:", ["--task-ref", "id:"], "any"))
        for value in (
            f"a:{10**400}",
            "a\x00b:1",
            "\ud800:1",
            "a\u202eb:1",
            "id:0",
            "id:-1",
        ):
            cases.append((value, ["--task-ref", value], "handler"))
    elif option == "owner":
        for value in (
            "nocolon",
            "bogus:x",
            "user:a\x00b",
            "user:\ud800",
            "user:a\u202eb",
        ):
            cases.append((value, ["--owner", value], "any"))
    elif option == "numeric":
        for flag, value, kind in (
            ("--max-bytes", "abc", "click"),
            ("--max-bytes", "1.5", "click"),
            ("--max-bytes", "0", "handler"),
            ("--max-bytes", "-1", "handler"),
            ("--max-bytes", str(10**400), "handler"),
            ("--max-tokens", "abc", "click"),
            ("--max-tokens", "0", "handler"),
            ("--max-tokens", str(10**400), "handler"),
            ("--invocation-id", "not-a-uuid", "handler"),
            ("--invocation-id", new_uuid().upper(), "handler"),
            ("--mapping-id", new_uuid().upper(), "handler"),
            ("--format", "pas_v2", "any"),
        ):
            cases.append((f"{flag} {value}", [flag, value], kind))
    else:
        raise AssertionError(option)
    for label, extra, kind in cases:
        result = cli_invoke([*base, *extra])
        assert result.exit_code == 2, (label, result.output[-500:])
        if kind == "handler":
            payload = json.loads(result.stdout)
            assert payload["raw"]["code"] == "E_INPUT", (label, payload)
        assert not out.exists(), label
        assert env.effects() == before, label
    # import-side options
    imp = cli_invoke(
        [
            "memory",
            "capsule",
            "import",
            "--project",
            str(env.root),
            "--input",
            str(cap),
            "--apply",
            "--invocation-id",
            new_uuid(),
            "--expected-digest",
            "a" * 64,
            "--expected-store-revision",
            "-1",
            "--allow-cache-write",
            "--json",
        ]
    )
    assert imp.exit_code == 2
    assert json.loads(imp.stdout)["raw"]["code"] == "E_INPUT"


# --- roots ---------------------------------------------------------------------------


def _run_moved_root(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    moved = env.root.parent / "moved-project"
    env.root.rename(moved)
    for action_request in (
        {"action": "preview_export", "output": str(env.outside / "m.json")},
        {"action": "preview_import", "input": str(env.outside / "m.json")},
    ):
        res = call_inproc(moved, {**action_request, "invocation_id": new_uuid()})
        assert res.code in ("E_PERMISSION", "E_INPUT"), res
        if res.code == "E_PERMISSION":
            assert isinstance(res.reason, str) and res.reason
    exp = call_inproc(
        moved,
        {
            "action": "preview_export",
            "output": str(env.outside / "m.json"),
            "invocation_id": new_uuid(),
        },
    )
    assert exp.code == "E_PERMISSION", exp


def _run_case_variant_root(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    variant = Path(str(env.root).swapcase())
    request = {
        "action": "preview_export",
        "output": str(env.outside / "c.json"),
        "invocation_id": new_uuid(),
    }
    if variant != env.root and variant.exists() and os.path.samefile(variant, env.root):
        # a case-insensitive filesystem: the other spelling of the root is not the
        # registered root, so the grant does not apply to it
        res = call_inproc(variant, request)
        assert res.code in ("E_PERMISSION", "OK"), res
    else:
        res = call_inproc(env.root, request)
        assert res.code == "OK", res


def _run_symlinks(tmp_path: Path) -> None:
    env, cap = _field_env(tmp_path)
    before = env.effects()
    parent_loop = env.outside / "loopdir"
    parent_loop.symlink_to(parent_loop)
    final_loop = env.outside / "loop.json"
    final_loop.symlink_to(final_loop)
    for transport in ("inproc", "cli"):
        for target in (parent_loop / "x.json", final_loop):
            res = call(
                transport,
                env.root,
                {
                    "action": "preview_export",
                    "output": str(target),
                    "invocation_id": new_uuid(),
                },
            )
            assert_denied(res, "E_PERMISSION", "export_target_refused")
        res = call(
            transport,
            env.root,
            {
                "action": "preview_import",
                "input": str(final_loop),
                "invocation_id": new_uuid(),
            },
        )
        assert_denied(res, "E_INPUT", "capsule_invalid")
    # MCP: an input outside the root, or a symlink inside it, is refused unread
    inside_link = env.exports / "link.json"
    inside_link.symlink_to(cap)
    outside_copy = env.outside / "copy.json"
    outside_copy.write_bytes(cap.read_bytes())
    for source in (inside_link, outside_copy):
        res = call_mcp(
            env.root,
            {
                "action": "preview_import",
                "input": str(source),
                "invocation_id": new_uuid(),
            },
        )
        assert_denied(res, "E_PERMISSION", "import_source_refused")
    after = env.effects()
    assert after["db"] == before["db"] and after["policy"] == before["policy"]


# --- policy helpers ------------------------------------------------------------------


def _run_helper_capsule_origin(tmp_path: Path) -> None:
    from rush.memory import authorization as auth

    env = make_env(tmp_path)
    good_hex = sha("worktree")
    secret = "ghp_" + "a" * 36
    bad_origins: list[tuple[str, Any, str]] = [
        ("string", "origin", "capsule_origin"),
        ("int", 5, "capsule_origin"),
        ("bool", True, "capsule_origin"),
        ("none", None, "capsule_origin"),
        ("list", [], "capsule_origin"),
        ("missing_worktree", {"project_id": "p"}, "capsule_origin"),
        ("missing_project", {"worktree_id": good_hex}, "capsule_origin"),
        (
            "extra_key",
            {"project_id": "p", "worktree_id": good_hex, "x": 1},
            "capsule_origin",
        ),
        (
            "worktree_not_hex",
            {"project_id": "p", "worktree_id": "xyz"},
            "capsule_origin",
        ),
        (
            "worktree_uppercase",
            {"project_id": "p", "worktree_id": good_hex.upper()},
            "capsule_origin",
        ),
        ("project_int", {"project_id": 5, "worktree_id": good_hex}, "capsule_origin"),
        (
            "project_huge",
            {"project_id": 10**400, "worktree_id": good_hex},
            "capsule_origin",
        ),
        ("project_nan", {"project_id": NAN, "worktree_id": good_hex}, "capsule_origin"),
        (
            "project_nul",
            {"project_id": "a\x00b", "worktree_id": good_hex},
            "capsule_origin",
        ),
        (
            "project_surrogate",
            {"project_id": "\ud800", "worktree_id": good_hex},
            "capsule_origin",
        ),
        (
            "project_cc_cf",
            {"project_id": "a\u202eb", "worktree_id": good_hex},
            "capsule_origin",
        ),
        (
            "project_secret_like",
            {"project_id": secret, "worktree_id": good_hex},
            "secret_like_value",
        ),
    ]
    revision = revision_of(env.data_root)
    policy = auth.policy_path(data_root=env.data_root)
    before = sha(policy.read_bytes())
    for label, origin, reason in bad_origins:
        with pytest.raises(auth.MemoryPolicyError) as raised:
            auth.approve_capsule_mapping(
                capsule_origin=origin,
                project_root=env.root,
                expected_policy_revision=revision,
                consent=True,
                data_root=env.data_root,
            )
        assert raised.value.code == "E_INPUT", label
        assert raised.value.reason == reason, (label, raised.value.reason)
    assert sha(policy.read_bytes()) == before

    # consent, revision and owner faults of the writers
    origin = {"project_id": "p", "worktree_id": good_hex}
    for kwargs, code, want_reason in (
        ({"consent": False}, "E_CONSENT", "consent_required"),
        ({"expected_policy_revision": -1}, "E_INPUT", "expected_policy_revision"),
        ({"expected_policy_revision": True}, "E_INPUT", "expected_policy_revision"),
        ({"expected_policy_revision": revision + 5}, "E_VERSION", None),
        ({"owner_scope": "alice"}, "E_INPUT", "owner_scope"),
        ({"owner_scope": {"kind": ["user"], "id": "x"}}, "E_INPUT", "owner_scope"),
    ):
        params: dict[str, Any] = {
            "capsule_origin": origin,
            "project_root": env.root,
            "expected_policy_revision": revision,
            "consent": True,
            "data_root": env.data_root,
        }
        params.update(kwargs)
        with pytest.raises(auth.MemoryPolicyError) as raised:
            auth.approve_capsule_mapping(**params)
        assert raised.value.code == code, (kwargs, raised.value.code)
        if want_reason is not None:
            assert raised.value.reason == want_reason, kwargs
    assert sha(policy.read_bytes()) == before


def _run_helper_data_root(tmp_path: Path) -> None:
    from rush.memory import authorization as auth

    env = make_env(tmp_path)
    good_hex = sha("worktree")
    revision = revision_of(env.data_root)
    bad_roots: list[tuple[str, Any]] = [
        ("int", 123),
        ("nul", "a\x00b"),
        ("surrogate", "\ud800"),
    ]
    for label, bad in bad_roots:
        with pytest.raises(auth.MemoryPolicyError) as writer:
            auth.approve_capsule_mapping(
                capsule_origin={"project_id": "p", "worktree_id": good_hex},
                project_root=env.root,
                expected_policy_revision=revision,
                consent=True,
                data_root=bad,
            )
        assert (writer.value.code, writer.value.reason) == (
            "E_POLICY_INVALID",
            "data_root_unavailable",
        ), label
        with pytest.raises(auth.MemoryPolicyError) as revoker:
            auth.revoke_capsule_mapping(
                mapping_id=new_uuid(),
                expected_policy_revision=revision,
                consent=True,
                data_root=bad,
            )
        assert (revoker.value.code, revoker.value.reason) == (
            "E_POLICY_INVALID",
            "data_root_unavailable",
        ), label
        with pytest.raises(auth.MemoryPolicyError) as resolver:
            auth.resolve_capsule_mapping(
                mapping_id=new_uuid(),
                origin_project_id="p",
                origin_worktree_id=good_hex,
                project_root=env.root,
                data_root=bad,
            )
        assert (resolver.value.code, resolver.value.reason) == (
            "E_PERMISSION",
            "data_root_unavailable",
        ), label
    # the revoke / resolve helpers' other arguments
    for bad_id in (5, True, None, "x", new_uuid().upper(), "a\x00b"):
        with pytest.raises(auth.MemoryPolicyError) as raised:
            auth.revoke_capsule_mapping(
                mapping_id=bad_id,  # type: ignore[arg-type]  # a non-str id is the test intent
                expected_policy_revision=revision,
                consent=True,
                data_root=env.data_root,
            )
        assert (raised.value.code, raised.value.reason) == ("E_INPUT", "mapping_id"), (
            bad_id
        )


# --- input bytes ---------------------------------------------------------------------


def _run_bytes_rush(tmp_path: Path) -> None:
    env = make_env(tmp_path)
    good = export_file(env, "good.json")
    raw = good.read_bytes()
    variants = _byte_variants(raw)
    cc_id = mutated_capsule(
        raw, lambda c: c["origin"].__setitem__("project_id", "p\u202eq")
    )
    variants["cc_cf_in_id"] = cc_id
    before = env.effects()
    for name, data in sorted(variants.items()):
        path = env.outside / f"g4-{name}.json"
        path.write_bytes(data)
        res = call_inproc(
            env.root,
            {
                "action": "preview_import",
                "input": str(path),
                "invocation_id": new_uuid(),
            },
        )
        assert res.code == "E_INPUT" and res.reason == "capsule_invalid", (name, res)
    assert env.effects()["db"] == before["db"] and not imported_rows(env)


def _run_bytes_pas(tmp_path: Path) -> None:
    pas_mod = importlib.import_module("tests.test_memory_capsule_pas")

    env = make_env(tmp_path)
    origin = json.loads(fixture_bytes("pas_session_schema1.json.rush-manifest.json"))[
        "capsule"
    ]["origin"]
    mapping_id = approved_mapping(env, origin)
    for name, (pas, side) in sorted(pas_mod.pas_byte_variants().items()):
        path = pas_mod.write_pair(tmp_path / f"g4-{name}", pas, side)
        pas_mod.assert_pas_invalid(env, path, name, mapping_id=mapping_id)


# --- G15 classes: portable-path spellings, persisted discriminators, unencodable
# --- paths and bounded recursion --------------------------------------------------

# Spellings that are drive-relative, drive-qualified, rooted or traversing on some
# host; none is a portable relative path whichever OS the capsule is read on.
PORTABLE_PATH_REJECTS: tuple[str, ...] = (
    "/abs/x.py",
    "C:x.py",
    "C:\\x.py",
    "c:/x.py",
    "..\\x.py",
    "a\\..\\..\\b.py",
    "../x.py",
    "a/../../b.py",
)


def _anchored_env(tmp_path: Path) -> tuple[CapEnv, Path]:
    env = make_env(tmp_path, seed=False, files={"src_mod.py": KNOWN_SRC})
    put_evidence(env, "ev1")
    put_evidence(env, "ev2")
    put_anchored_evidence(env, "ev3")
    put_checkpoint(
        env,
        "cp1",
        created_at=time.time() - 50,
        evidence_refs=[
            {"artifact_id": "ev1", "version": 1},
            {"artifact_id": "ev2", "version": 1},
            {"artifact_id": "ev3", "version": 1},
        ],
    )
    return env, export_file(env, "anchored.json")


def _with_path_fields(raw: bytes, path: str) -> bytes:
    """The anchored export with evidence `ev3` re-pointed at `path` (hashes redone)."""

    def mutate(c: dict[str, Any]) -> None:
        entry = next(e for e in c["evidence"] if e["artifact_id"] == "ev3")
        entry["symbol_ref"] = f"{path}::Known"
        entry["source_path"] = path
        c["manifest"]["source_paths"] = sorted(
            {e["source_path"] for e in c["evidence"] if e["source_path"]}
        )

    return mutated_capsule(raw, mutate)


def _run_portable_paths(tmp_path: Path) -> None:
    env, cap = _anchored_env(tmp_path)
    raw = cap.read_bytes()
    target = env.outside / "paths.json"
    request = {"action": "preview_import", "input": str(target)}
    for spelling in PORTABLE_PATH_REJECTS:
        target.write_bytes(_with_path_fields(raw, spelling))
        before = env.effects()
        res = call_inproc(env.root, {**request, "invocation_id": new_uuid()})
        assert_denied(res, "E_INPUT", "capsule_invalid")
        assert env.effects() == before, spelling
    # a literal backslash file name has no drive and no traversal: it stays valid
    target.write_bytes(_with_path_fields(raw, "dir\\file.py"))
    ok = call_inproc(env.root, {**request, "invocation_id": new_uuid()})
    assert ok.code == "OK", ok
    # an unencodable path field (a lone surrogate escape in the JSON text)
    text = raw.decode("utf-8")
    assert '"source_path":"src_mod.py"' in text
    target.write_bytes(
        text.replace(
            '"source_path":"src_mod.py"', '"source_path":"\\ud800.py"'
        ).encode()
    )
    before = env.effects()
    res = call_inproc(env.root, {**request, "invocation_id": new_uuid()})
    assert_denied(res, "E_INPUT", "capsule_invalid")
    assert env.effects() == before

    # export: required evidence anchored at such a path is never exported
    assert env.store is not None
    for index, spelling in enumerate(PORTABLE_PATH_REJECTS):
        env.store.write(
            MemoryArtifact(
                id=f"bad{index}",
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content=evidence_body(f"bad{index}"),
                source=SRC,
                created_at=time.time(),
                symbol_ref=f"{spelling}::Known",
                owner_scope=env.owner,
            )
        )
        stored = json.loads(row_of(env, "cp1")["content"])
        stored["evidence_refs"] = [{"artifact_id": f"bad{index}", "version": 1}]
        plant_content(env, "cp1", stored)
        out = env.outside / f"bad{index}.json"
        before = env.effects()
        res = call_inproc(
            env.root,
            {
                "action": "preview_export",
                "output": str(out),
                "invocation_id": new_uuid(),
            },
        )
        assert_denied(res, "E_PERMISSION", "export_blocked")
        assert not out.exists() and env.effects() == before, spelling
    # a POSIX file whose name holds a literal backslash is a valid native output path
    if sys.platform != "win32":
        stored["evidence_refs"] = [{"artifact_id": "ev1", "version": 1}]
        plant_content(env, "cp1", stored)
        native = env.outside / "back\\slash.json"
        res = call_inproc(
            env.root,
            {
                "action": "preview_export",
                "output": str(native),
                "invocation_id": new_uuid(),
            },
        )
        assert res.code == "OK", res


_PERSISTED_DISCRIMINATORS: dict[str, Any] = {
    "purpose_list": lambda r: r.__setitem__("purpose", ["capsule_import"]),
    "purpose_dict": lambda r: r.__setitem__("purpose", {"capsule_import": 1}),
    "owner_kind_list": lambda r: r["target_owner_scope"].__setitem__("kind", ["user"]),
    "owner_kind_dict": lambda r: r["target_owner_scope"].__setitem__("kind", {"a": 1}),
    "grant_id_list": lambda r: r.__setitem__("grant_id", [r["grant_id"]]),
    "grant_id_dict": lambda r: r.__setitem__("grant_id", {}),
    "origin_project_list": lambda r: r.__setitem__("origin_project_id", ["p"]),
    "revoked_list": lambda r: r.__setitem__("revoked", []),
    "mapping_id_list": lambda r: r.__setitem__("mapping_id", [r["mapping_id"]]),
    "root_invalid_utf8": lambda r: r.__setitem__("target_root_hex", "eda080"),
}


def _run_persisted_discriminators(tmp_path: Path) -> None:
    """A malformed persisted mapping follows its declared policy error through every
    helper and the public route; no `TypeError` escapes and no byte is written."""
    from rush.memory import authorization as auth

    env, _cap = _field_env(tmp_path)
    foreign_bytes = fixture_bytes("rush_v1_two_constraints_two_evidence.json")
    origin = json.loads(foreign_bytes)["origin"]
    mapping_id = approved_mapping(env, origin)
    foreign = env.exports / "foreign.json"
    foreign.write_bytes(foreign_bytes)
    policy = auth.policy_path(data_root=env.data_root)
    base = json.loads(policy.read_bytes())
    revision = base["data"]["policy_revision"]
    approve_args = {
        "capsule_origin": {
            "project_id": origin["project_id"],
            "worktree_id": origin["worktree_id"],
        },
        "project_root": env.root,
        "expected_policy_revision": revision,
        "consent": True,
        "data_root": env.data_root,
    }
    resolve_args = {
        "mapping_id": mapping_id,
        "origin_project_id": origin["project_id"],
        "origin_worktree_id": origin["worktree_id"],
        "project_root": env.root,
        "data_root": env.data_root,
    }
    revoke_args = {
        "mapping_id": mapping_id,
        "expected_policy_revision": revision,
        "consent": True,
        "data_root": env.data_root,
    }
    for name, mutate in _PERSISTED_DISCRIMINATORS.items():
        data = json.loads(json.dumps(base))
        mutate(data["data"]["mappings"][mapping_id])
        policy.write_bytes(json.dumps(data).encode("utf-8"))
        tampered = sha(policy.read_bytes())
        loaded = auth.load_policy_readonly(data_root=env.data_root)
        assert (loaded["state"], loaded["reason"]) == ("invalid", "record_invalid"), (
            name
        )
        for fn, kwargs, code in (
            (auth.resolve_capsule_mapping, resolve_args, "E_PERMISSION"),
            (auth.revoke_capsule_mapping, revoke_args, "E_POLICY_INVALID"),
            (auth.approve_capsule_mapping, approve_args, "E_POLICY_INVALID"),
        ):
            with pytest.raises(auth.MemoryPolicyError) as raised:
                fn(**kwargs)
            assert (raised.value.code, raised.value.reason) == (
                code,
                "record_invalid",
            ), (name, fn.__name__)
        res = call_inproc(
            env.root,
            {
                "action": "preview_import",
                "input": str(foreign),
                "mapping_id": mapping_id,
                "invocation_id": new_uuid(),
            },
        )
        assert res.code == "E_PERMISSION", (name, res)
        assert sha(policy.read_bytes()) == tampered, name
    policy.write_bytes(json.dumps(base).encode("utf-8"))
    assert auth.load_policy_readonly(data_root=env.data_root)["state"] == "ok"


def _run_unencodable_paths(tmp_path: Path) -> None:
    """A lone surrogate in a project, mapping or helper path is refused with the
    field's own error before any OS call, and nothing is written."""
    from rush.memory import authorization as auth

    env, cap = _field_env(tmp_path)
    bad = "\ud800"
    before = env.effects()
    for body in (
        {"action": "preview_export", "output": str(env.outside / "u.json")},
        {"action": "preview_import", "input": str(cap)},
    ):
        res = call_inproc(Path(bad), {**body, "invocation_id": new_uuid()})
        assert res.code == "E_INPUT" and res.field == "path", res
    assert env.effects() == before

    origin = json.loads(fixture_bytes("rush_v1_two_constraints_two_evidence.json"))[
        "origin"
    ]
    mapping_id = approved_mapping(env, origin)
    policy = auth.policy_path(data_root=env.data_root)
    sealed = sha(policy.read_bytes())
    revision = revision_of(env.data_root)
    approve = {
        "capsule_origin": {
            "project_id": origin["project_id"],
            "worktree_id": origin["worktree_id"],
        },
        "project_root": env.root,
        "expected_policy_revision": revision,
        "consent": True,
        "data_root": env.data_root,
    }
    for override, code, reason in (
        ({"project_root": bad}, "E_INPUT", "project_missing"),
        ({"project_root": Path(bad)}, "E_INPUT", "project_missing"),
        ({"owner_scope": OwnerScope("user", "\udcff")}, "E_INPUT", "owner_scope"),
    ):
        with pytest.raises(auth.MemoryPolicyError) as raised:
            auth.approve_capsule_mapping(**{**approve, **override})  # type: ignore[arg-type]  # bad override values are the test intent
        assert (raised.value.code, raised.value.reason) == (code, reason), override
    with pytest.raises(auth.MemoryPolicyError) as resolved:
        auth.resolve_capsule_mapping(
            mapping_id=mapping_id,
            origin_project_id=origin["project_id"],
            origin_worktree_id=origin["worktree_id"],
            project_root=bad,  # type: ignore[arg-type]  # a bad root is the test intent
            data_root=env.data_root,
        )
    assert (resolved.value.code, resolved.value.reason) == (
        "E_PERMISSION",
        "mapping_mismatch",
    )
    with pytest.raises(auth.MemoryPolicyError) as revoked:
        auth.revoke_capsule_mapping(
            mapping_id=bad,
            expected_policy_revision=revision,
            consent=True,
            data_root=env.data_root,
        )
    assert (revoked.value.code, revoked.value.reason) == ("E_INPUT", "mapping_id")
    identity = auth.project_identity(bad, data_root=env.data_root)
    assert identity["project_id"] is None and identity["worktree_id"] is None
    assert sha(policy.read_bytes()) == sealed
    assert env.effects()["db"] == before["db"]


def _run_bounded_recursion(tmp_path: Path) -> None:
    """Hostile nesting is bounded: the decoder refuses depth past 16 as
    `capsule_invalid` and an unserializable stored body is `export_blocked`; no
    `RecursionError` escapes on any path."""
    env, _cap = _field_env(tmp_path)
    bomb = env.exports / "bomb.json"
    for label, data in (
        ("array-17", b'{"schema_version":1,"x":' + b"[" * 17 + b"]" * 17 + b"}"),
        ("array-600", b'{"schema_version":1,"x":' + b"[" * 600 + b"]" * 600 + b"}"),
        ("array-5000", b'{"schema_version":1,"x":' + b"[" * 5000 + b"]" * 5000 + b"}"),
        (
            "array-100000",
            b'{"schema_version":1,"x":' + b"[" * 100000 + b"]" * 100000 + b"}",
        ),
        (
            "object-100000",
            b'{"schema_version":1,"x":'
            + b'{"a":' * 100000
            + b"1"
            + b"}" * 100000
            + b"}",
        ),
        ("leading-array", b"[" * 100000 + b"]" * 100000),
    ):
        bomb.write_bytes(data)
        before = env.effects()
        for transport in ("inproc", "mcp", "cli"):
            res = call(
                transport,
                env.root,
                {
                    "action": "preview_import",
                    "input": str(bomb),
                    "invocation_id": new_uuid(),
                },
            )
            assert_denied(res, "E_INPUT", "capsule_invalid")
        assert env.effects() == before, label
    # a stored body that cannot be serialized (nesting past the recursion limit) is an
    # invalid mandatory export body
    depth = 5000
    plant_content_text(env, "ev1", '{"a":' * depth + "1" + "}" * depth)
    out = env.outside / "deep-body.json"
    before = env.effects()
    for action in ("preview_export",):
        res = call_inproc(
            env.root,
            {"action": action, "output": str(out), "invocation_id": new_uuid()},
        )
        assert_denied(res, "E_PERMISSION", "export_blocked")
    assert not out.exists() and env.effects() == before


_SINGLES = {
    "cli-task-ref": lambda p: _run_cli_option("task-ref", p),
    "cli-owner": lambda p: _run_cli_option("owner", p),
    "cli-numeric-options": lambda p: _run_cli_option("numeric", p),
    "root-moved": _run_moved_root,
    "root-case-variant": _run_case_variant_root,
    "symlinks-and-containment": _run_symlinks,
    "helper-capsule-origin": _run_helper_capsule_origin,
    "helper-data-root-and-ids": _run_helper_data_root,
    "bytes-rush_v1": _run_bytes_rush,
    "bytes-pas_v1": _run_bytes_pas,
    "portable-path-spellings": _run_portable_paths,
    "persisted-mapping-discriminators": _run_persisted_discriminators,
    "unencodable-paths": _run_unencodable_paths,
    "bounded-recursion": _run_bounded_recursion,
}


def _cases() -> list[Any]:
    params = list(_group_params())
    for name in _SINGLES:
        marks = [pytest.mark.posix_only] if name == "symlinks-and-containment" else []
        params.append(pytest.param(None, name, id=name, marks=marks))
    return params


@pytest.mark.parametrize(("transport", "case"), _cases())
def test_codec_trust_boundary_inputs(
    transport: str | None, case: str, tmp_path: Path
) -> None:
    if transport is None:
        _SINGLES[case](tmp_path)
    else:
        _run_group(transport, case, tmp_path)
