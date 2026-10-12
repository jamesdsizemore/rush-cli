"""73-T02/POLICY: the memory authorization policy (`rush.memory.authorization`).

Every test imports `rush.memory.authorization` inside its own body so each one
fails on its own until the module exists. The module-level imports below are
existing code only.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import textwrap
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from rush.memory.store import OwnerScope, legacy_owner_scope
from rush.workflows.projects import register_project, relink_project

REPO_SRC = Path(__file__).resolve().parents[1] / "src"
FIVE_OPS = ("ask", "bootstrap", "expand", "list", "write")
RESOLVE_KEYS = {
    "access",
    "reason",
    "operation",
    "grant_id",
    "grant_revision",
    "policy_revision",
    "project_id",
    "worktree_id",
    "project_root",
    "owner_scope",
    "approved_sources",
    "allowed_operations",
    "session_binding",
}
GRANT_RESULT_KEYS = {
    "grant_id",
    "policy_revision",
    "project_id",
    "worktree_id",
    "owner_scope",
    "approved_sources",
    "allowed_operations",
}
BINDING_KEYS = {
    "binding_id",
    "grant_id",
    "policy_revision",
    "project_id",
    "worktree_id",
    "scope_fingerprint",
    "host_id",
    "session_id",
    "revoked",
}
LOAD_KEYS = {
    "state",
    "reason",
    "policy_path",
    "policy_revision",
    "content_sha256",
    "grants",
    "bindings",
    "mappings",
}
_EMPTY = inspect.Parameter.empty
EXPECTED_SIGNATURES: dict[str, list[tuple[str, Any]]] = {
    "policy_path": [("data_root", None)],
    "user_overlay_owner_scope": [("data_root", None)],
    "hold_policy_lock": [("data_root", None)],
    "load_policy_readonly": [("data_root", None)],
    "grant_memory_scope": [
        ("project_root", _EMPTY),
        ("owner_scope", _EMPTY),
        ("approved_sources", _EMPTY),
        ("allowed_operations", _EMPTY),
        ("expected_policy_revision", _EMPTY),
        ("consent", _EMPTY),
        ("expires_at", None),
        ("data_root", None),
    ],
    "revoke_memory_scope": [
        ("grant_id", _EMPTY),
        ("expected_policy_revision", _EMPTY),
        ("consent", _EMPTY),
        ("data_root", None),
    ],
    "resolve_memory_scope": [
        ("project_root", _EMPTY),
        ("operation", _EMPTY),
        ("owner_scope", None),
        ("requested_sources", ()),
        ("session_binding", None),
        ("data_root", None),
    ],
    "register_memory_binding": [
        ("grant_id", _EMPTY),
        ("session_id", _EMPTY),
        ("host_id", _EMPTY),
        ("expected_policy_revision", _EMPTY),
        ("consent", _EMPTY),
        ("data_root", None),
    ],
}


# --- helpers (existing code and stdlib only) --------------------------------


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "user-data"


def _project(tmp_path: Path, name: str, data_root: Path) -> tuple[Path, Any]:
    root = tmp_path / name
    root.mkdir(parents=True)
    record = register_project(root, data_root=data_root)
    return root.resolve(), record


def _policy_file(data_root: Path) -> Path:
    return data_root.resolve() / "user" / ".rush" / "memory_authorization.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(base: Path) -> list[str]:
    return sorted(str(p.relative_to(base)) for p in base.rglob("*"))


def _snapshot(*bases: Path) -> list[tuple[str, ...]]:
    """Every entry under `bases`: symlink target, directory, or file sha256."""
    state: list[tuple[str, ...]] = []
    for base in bases:
        for p in [base, *sorted(base.rglob("*"))]:
            if p.is_symlink():
                state.append((str(p), "link", os.readlink(p)))
            elif p.is_dir():
                state.append((str(p), "dir"))
            elif p.is_file():
                state.append((str(p), "file", _sha(p)))
    return state


def _worktree_id(root: Path) -> str:
    canonical = Path(root).resolve()
    ino = os.stat(canonical).st_ino
    return hashlib.sha256(f"{canonical}\0{ino}".encode()).hexdigest()


def _raw(data_root: Path) -> dict[str, Any]:
    return json.loads(_policy_file(data_root).read_bytes().decode("utf-8"))


def _write_raw(data_root: Path, payload: dict[str, Any]) -> None:
    _policy_file(data_root).write_text(json.dumps(payload), encoding="utf-8")


def _expect(auth: Any, code: str, reason: str, func: Any, **kwargs: Any) -> Any:
    with pytest.raises(auth.MemoryPolicyError) as info:
        func(**kwargs)
    assert info.value.code == code
    assert info.value.reason == reason
    return info.value


def _grant(
    auth: Any,
    root: Path,
    owner: OwnerScope,
    data_root: Path,
    *,
    sources: tuple[str, ...] = ("source-a",),
    ops: tuple[str, ...] = ("ask",),
    expected: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=list(sources),
        allowed_operations=list(ops),
        expected_policy_revision=expected,
        consent=True,
        data_root=data_root,
        **extra,
    )


def _bind(
    auth: Any,
    grant_id: str,
    data_root: Path,
    *,
    expected: int,
    session_id: str = "session-1",
    host_id: str = "host-1",
) -> dict[str, Any]:
    return auth.register_memory_binding(
        grant_id=grant_id,
        session_id=session_id,
        host_id=host_id,
        expected_policy_revision=expected,
        consent=True,
        data_root=data_root,
    )


def _resolve(
    auth: Any, root: Path | str, data_root: Path, operation: str = "ask", **kwargs: Any
) -> dict[str, Any]:
    return auth.resolve_memory_scope(
        project_root=root, operation=operation, data_root=data_root, **kwargs
    )


def _assert_denied(result: dict[str, Any], reason: str) -> None:
    assert set(result) == RESOLVE_KEYS
    assert result["access"] == "denied"
    assert result["reason"] == reason
    assert result["grant_id"] is None
    assert result["grant_revision"] is None
    assert result["owner_scope"] is None
    assert result["approved_sources"] == []
    assert result["allowed_operations"] == []


def _assert_granted(result: dict[str, Any], access: str = "read") -> None:
    assert set(result) == RESOLVE_KEYS
    assert result["reason"] == "granted"
    assert result["access"] == access


def _is_uuid4(value: Any) -> bool:
    return isinstance(value, str) and str(uuid.UUID(value)) == value


def _child_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_SRC)
    return env


def _wait_for(path: Path, *children: subprocess.Popen[str]) -> None:
    """Wait until `path` exists; fail at once if a child already exited."""
    deadline = time.monotonic() + 60
    while not path.exists():
        for child in children:
            if child.poll() is not None:
                out, err = child.communicate()
                raise AssertionError(
                    f"child exited {child.returncode} before {path.name}: {out}{err}"
                )
        assert time.monotonic() < deadline, f"timed out waiting for {path}"
        time.sleep(0.01)


def _git(*args: str, cwd: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Rush Test",
            "-c",
            "user.email=rush-test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
    )


_GRANT_CHILD = textwrap.dedent(
    """
    import json, sys, time
    from pathlib import Path
    import rush.memory.authorization as auth
    from rush.memory.store import OwnerScope
    args = json.loads(sys.argv[1])
    Path(args["ready"]).write_text("ready")
    deadline = time.monotonic() + 60
    while not Path(args["go"]).exists():
        if time.monotonic() > deadline:
            sys.exit(3)
        time.sleep(0.005)
    try:
        result = auth.grant_memory_scope(
            project_root=Path(args["root"]),
            owner_scope=OwnerScope("agent", args["owner"]),
            approved_sources=["source-a"],
            allowed_operations=["ask"],
            expected_policy_revision=1,
            consent=True,
            data_root=Path(args["data_root"]),
        )
    except auth.MemoryPolicyError as exc:
        print(json.dumps({"code": exc.code}))
    else:
        print(json.dumps({"grant_id": result["grant_id"],
                          "policy_revision": result["policy_revision"]}))
    """
)

_REVOKE_CHILD = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    import rush.memory.authorization as auth
    args = json.loads(sys.argv[1])
    Path(args["marker"]).write_text("started")
    result = auth.revoke_memory_scope(
        grant_id=args["grant_id"],
        expected_policy_revision=1,
        consent=True,
        data_root=Path(args["data_root"]),
    )
    print(json.dumps(result))
    """
)


# --- tests -------------------------------------------------------------------


def test_missing_policy_read_does_not_initialize_data_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth
    from rush.setup.provision import default_data_root

    # Case 1: an unregistered root under a data root that holds only a registry.
    # Case 2: an absent data root. Case 3: an empty data root.
    # Case 4: data_root=None with HOME, XDG_DATA_HOME and LOCALAPPDATA in tmp.
    cases: list[tuple[str, Path | None]] = []
    case1 = tmp_path / "case1"
    case1.mkdir()
    (case1 / "other").mkdir()
    register_project(case1 / "other", data_root=_data_root(case1))
    cases.append(("case1", _data_root(case1)))
    (tmp_path / "case2").mkdir()
    cases.append(("case2", _data_root(tmp_path / "case2")))
    (tmp_path / "case3").mkdir()
    _data_root(tmp_path / "case3").mkdir()
    cases.append(("case3", _data_root(tmp_path / "case3")))
    case4 = tmp_path / "case4"
    for sub in ("home", "xdg", "localappdata"):
        (case4 / sub).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(case4 / "home"))
    monkeypatch.setenv("XDG_DATA_HOME", str(case4 / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(case4 / "localappdata"))
    cases.append(("case4", None))

    for name, data_root in cases:
        project = tmp_path / name / "project"
        project.mkdir()
        effective_root = (
            data_root if data_root is not None else default_data_root()
        ).resolve()
        expected_path = effective_root / "user" / ".rush" / "memory_authorization.json"
        before = _tree(tmp_path)

        assert auth.policy_path(data_root=data_root) == expected_path
        loaded = auth.load_policy_readonly(data_root=data_root)
        assert set(loaded) == LOAD_KEYS
        assert Path(loaded["policy_path"]) == expected_path
        assert {k: v for k, v in loaded.items() if k != "policy_path"} == {
            "state": "missing",
            "reason": "policy_missing",
            "policy_revision": 0,
            "content_sha256": None,
            "grants": {},
            "bindings": {},
            "mappings": {},
        }
        resolved = auth.resolve_memory_scope(
            project_root=project, operation="ask", data_root=data_root
        )
        _assert_denied(resolved, "policy_missing")
        assert resolved["operation"] == "ask"
        assert resolved["policy_revision"] == 0
        assert resolved["session_binding"] is None

        assert _tree(tmp_path) == before, name
        assert not (effective_root / "dashboard").exists(), name
        assert not (effective_root / "user").exists(), name
        assert not (project / ".rush").exists(), name


def test_explicit_setup_grant_and_cas_revision(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    owner = legacy_owner_scope(project)

    _expect(
        auth,
        "E_CONSENT",
        "consent_required",
        auth.grant_memory_scope,
        project_root=project,
        owner_scope=owner,
        approved_sources=["source-a"],
        allowed_operations=["ask", "write"],
        expected_policy_revision=0,
        consent=False,
        data_root=d,
    )
    assert not d.exists()

    record = register_project(project, data_root=d)
    root = project.resolve()
    first = _grant(
        auth, root, owner, d, sources=("source-b", "source-a"), ops=("write", "ask")
    )
    assert set(first) == GRANT_RESULT_KEYS
    assert _is_uuid4(first["grant_id"])
    assert first == {
        "grant_id": first["grant_id"],
        "policy_revision": 1,
        "project_id": record.project_id,
        "worktree_id": _worktree_id(root),
        "owner_scope": {"kind": "project", "id": str(root)},
        "approved_sources": ["source-a", "source-b"],
        "allowed_operations": ["ask", "write"],
    }
    raw = _raw(d)
    assert set(raw) == {"schema_version", "version", "data"}
    assert raw["schema_version"] == "1.0.0"
    assert raw["version"] == 1
    assert set(raw["data"]) == {
        "schema_version",
        "policy_revision",
        "grants",
        "bindings",
        "mappings",
    }
    assert raw["data"]["schema_version"] == 1
    assert raw["data"]["policy_revision"] == 1
    assert list(raw["data"]["grants"]) == [first["grant_id"]]
    assert raw["data"]["bindings"] == {}
    assert raw["data"]["mappings"] == {}

    alice = OwnerScope("agent", "alice")
    sha_rev1 = _sha(_policy_file(d))
    _expect(
        auth,
        "E_VERSION",
        "expected revision 0, found 1",
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=alice,
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=0,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_rev1

    second = _grant(auth, root, alice, d, expected=1)
    assert second["policy_revision"] == 2
    assert second["grant_id"] != first["grant_id"]
    assert _raw(d)["version"] == 2
    assert _raw(d)["data"]["policy_revision"] == 2

    sha_rev2 = _sha(_policy_file(d))
    retry = _grant(auth, root, alice, d, expected=0)
    assert retry == second
    assert _sha(_policy_file(d)) == sha_rev2
    assert auth.load_policy_readonly(data_root=d)["policy_revision"] == 2

    stat_before = _policy_file(d).stat()
    r1 = _resolve(auth, root, d, "ask", owner_scope=owner)
    _assert_granted(r1, "read")
    assert r1["grant_id"] == first["grant_id"]
    r2 = _resolve(auth, root, d, "write", owner_scope=owner)
    _assert_granted(r2, "write")
    r3 = _resolve(auth, root, d, "ask", owner_scope=alice)
    _assert_granted(r3, "read")
    assert r3["grant_id"] == second["grant_id"]
    r4 = _resolve(
        auth, root, d, "ask", owner_scope=owner, requested_sources=["source-a"]
    )
    _assert_granted(r4, "read")
    assert r4["approved_sources"] == ["source-a"]
    _assert_denied(
        _resolve(auth, root, d, "write", owner_scope=alice), "operation_not_granted"
    )
    stat_after = _policy_file(d).stat()
    assert _sha(_policy_file(d)) == sha_rev2
    assert stat_after.st_mtime_ns == stat_before.st_mtime_ns


def test_concurrent_grant_conflict_preserves_first(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    initial = _grant(auth, root, OwnerScope("agent", "initial"), d)
    assert initial["policy_revision"] == 1

    go = tmp_path / "go"
    children: list[subprocess.Popen[str]] = []
    try:
        for owner in ("one", "two"):
            args = {
                "ready": str(tmp_path / f"ready-{owner}"),
                "go": str(go),
                "root": str(root),
                "owner": owner,
                "data_root": str(d),
            }
            children.append(
                subprocess.Popen(
                    [sys.executable, "-c", _GRANT_CHILD, json.dumps(args)],
                    env=_child_env(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        for owner in ("one", "two"):
            _wait_for(tmp_path / f"ready-{owner}", *children)
        go.write_text("go")
        outputs = []
        for child in children:
            out, err = child.communicate(timeout=120)
            assert child.returncode == 0, err
            outputs.append(json.loads(out.strip().splitlines()[-1]))
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()

    winners = [o for o in outputs if "grant_id" in o]
    losers = [o for o in outputs if "code" in o]
    assert len(winners) == 1
    assert winners[0]["policy_revision"] == 2
    assert losers == [{"code": "E_VERSION"}]
    loaded = auth.load_policy_readonly(data_root=d)
    assert loaded["policy_revision"] == 2
    assert set(loaded["grants"]) == {initial["grant_id"], winners[0]["grant_id"]}


def test_policy_lock_serializes_revoke(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    grant = _grant(auth, root, owner, d)
    assert grant["policy_revision"] == 1
    sha_before = _sha(_policy_file(d))

    marker = tmp_path / "marker"
    args = {"marker": str(marker), "grant_id": grant["grant_id"], "data_root": str(d)}
    child: subprocess.Popen[str] | None = None
    try:
        with auth.hold_policy_lock(data_root=d):
            child = subprocess.Popen(
                [sys.executable, "-c", _REVOKE_CHILD, json.dumps(args)],
                env=_child_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            _wait_for(marker, child)
            time.sleep(0.5)
            assert child.poll() is None
            assert _sha(_policy_file(d)) == sha_before
        out, err = child.communicate(timeout=120)
        assert child.returncode == 0, err
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate()

    assert json.loads(out.strip().splitlines()[-1])["revoked"] is True
    _assert_denied(_resolve(auth, root, d, "ask", owner_scope=owner), "revoked")


def test_revocation_and_expiry_rechecked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    clock = {"now": time.time()}
    fake_now = clock["now"]
    monkeypatch.setattr(auth, "_now", lambda: clock["now"])

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    alpha = OwnerScope("agent", "alpha")
    beta = OwnerScope("agent", "beta")
    grant_a = _grant(auth, root, alpha, d)
    grant_b = _grant(auth, root, beta, d, expected=1, expires_at=fake_now + 60)
    assert grant_b["policy_revision"] == 2
    binding = _bind(auth, grant_a["grant_id"], d, expected=2)
    assert binding["policy_revision"] == 3

    _assert_granted(_resolve(auth, root, d, owner_scope=alpha))
    bound = _resolve(auth, root, d, session_binding=binding["binding_id"])
    _assert_granted(bound)
    assert bound["session_binding"] == binding["binding_id"]
    _assert_granted(_resolve(auth, root, d, owner_scope=beta))

    sha_rev3 = _sha(_policy_file(d))
    _expect(
        auth,
        "E_CONSENT",
        "consent_required",
        auth.revoke_memory_scope,
        grant_id=grant_a["grant_id"],
        expected_policy_revision=3,
        consent=False,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_rev3
    _expect(
        auth,
        "E_VERSION",
        "expected revision 2, found 3",
        auth.revoke_memory_scope,
        grant_id=grant_a["grant_id"],
        expected_policy_revision=2,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_rev3

    revoked = auth.revoke_memory_scope(
        grant_id=grant_a["grant_id"],
        expected_policy_revision=3,
        consent=True,
        data_root=d,
    )
    assert revoked == {
        "grant_id": grant_a["grant_id"],
        "policy_revision": 4,
        "revoked": True,
        "revoked_bindings": [binding["binding_id"]],
    }
    _assert_denied(_resolve(auth, root, d, owner_scope=alpha), "revoked")
    _assert_denied(
        _resolve(auth, root, d, session_binding=binding["binding_id"]),
        "binding_revoked",
    )

    sha_rev4 = _sha(_policy_file(d))
    auth.revoke_memory_scope(
        grant_id=grant_a["grant_id"],
        expected_policy_revision=3,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_rev4
    assert auth.load_policy_readonly(data_root=d)["policy_revision"] == 4

    clock["now"] = fake_now + 61
    _assert_denied(_resolve(auth, root, d, owner_scope=beta), "expired")

    _expect(
        auth,
        "E_INPUT",
        "expires_at",
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=OwnerScope("agent", "gamma"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=4,
        consent=True,
        expires_at=clock["now"] - 1,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_rev4


def test_relink_and_foreign_worktree_rejected(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    main = tmp_path / "main"
    main.mkdir()
    _git("init", "-q", cwd=main)
    _git("commit", "--allow-empty", "-q", "-m", "init", cwd=main)
    worktree = tmp_path / "worktree"
    _git("worktree", "add", "-q", str(worktree), cwd=main)
    main_record = register_project(main, data_root=d)
    register_project(worktree, data_root=d)
    main_root = main.resolve()

    grant = _grant(auth, main_root, legacy_owner_scope(main_root), d)
    binding = _bind(auth, grant["grant_id"], d, expected=1)
    _assert_granted(_resolve(auth, main_root, d))

    _assert_denied(_resolve(auth, worktree.resolve(), d), "no_grant")

    moved = tmp_path / "moved"
    main.rename(moved)
    relink_project(main_record.project_id, moved, expected_revision=1, data_root=d)
    _assert_denied(_resolve(auth, moved.resolve(), d), "relinked")
    _assert_denied(
        _resolve(auth, moved.resolve(), d, session_binding=binding["binding_id"]),
        "relinked",
    )
    _assert_denied(_resolve(auth, main_root, d), "project_missing")

    sha_before = _sha(_policy_file(d))
    error = _expect(
        auth,
        "E_GRANT_INACTIVE",
        "relinked",
        auth.register_memory_binding,
        grant_id=grant["grant_id"],
        session_id="session-2",
        host_id="host-1",
        expected_policy_revision=2,
        consent=True,
        data_root=d,
    )
    assert error.reason == "relinked"
    assert _sha(_policy_file(d)) == sha_before

    project_c = tmp_path / "project-c"
    project_c.mkdir()
    c_record = register_project(project_c, data_root=d)
    c_root = project_c.resolve()
    c_grant = _grant(auth, c_root, legacy_owner_scope(c_root), d, expected=2)
    assert c_grant["policy_revision"] == 3
    _assert_granted(_resolve(auth, c_root, d))
    project_c.rename(tmp_path / "project-c-away")
    project_c.mkdir()
    assert register_project(project_c, data_root=d).project_id == c_record.project_id
    _assert_denied(_resolve(auth, c_root, d), "worktree_mismatch")


@pytest.mark.posix_only
def test_wrong_os_user_denied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    grant = _grant(auth, root, owner, d)
    sha_before = _sha(_policy_file(d))

    monkeypatch.setattr(auth, "_current_os_principal", lambda: f"uid:{os.getuid() + 1}")
    loaded = auth.load_policy_readonly(data_root=d)
    assert loaded["state"] == "invalid"
    assert loaded["reason"] == "foreign_owner"
    _assert_denied(_resolve(auth, root, d, owner_scope=owner), "policy_invalid")
    _expect(
        auth,
        "E_POLICY_INVALID",
        "foreign_owner",
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=OwnerScope("agent", "other"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_POLICY_INVALID",
        "foreign_owner",
        auth.revoke_memory_scope,
        grant_id=grant["grant_id"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_before
    monkeypatch.undo()

    payload = _raw(d)
    payload["data"]["grants"][grant["grant_id"]]["principal"] = "uid:99999"
    _write_raw(d, payload)
    crafted_sha = _sha(_policy_file(d))
    _assert_denied(_resolve(auth, root, d, owner_scope=owner), "principal_mismatch")
    _expect(
        auth,
        "E_PRINCIPAL",
        "principal_mismatch",
        auth.revoke_memory_scope,
        grant_id=grant["grant_id"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == crafted_sha


def test_forged_host_session_or_binding_cannot_grant(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root_a, _ = _project(tmp_path, "project-a", d)
    root_b, _ = _project(tmp_path, "project-b", d)
    grant_a = _grant(auth, root_a, legacy_owner_scope(root_a), d)
    _grant(auth, root_b, legacy_owner_scope(root_b), d, expected=1)
    binding = _bind(auth, grant_a["grant_id"], d, expected=2)
    assert binding["policy_revision"] == 3

    _assert_denied(
        _resolve(auth, root_a, d, session_binding="forged"), "binding_unknown"
    )
    _assert_denied(
        _resolve(auth, root_b, d, session_binding=binding["binding_id"]),
        "binding_scope_mismatch",
    )

    sha_before = _sha(_policy_file(d))
    _expect(
        auth,
        "E_CONSENT",
        "consent_required",
        auth.register_memory_binding,
        grant_id=grant_a["grant_id"],
        session_id="session-2",
        host_id="host-1",
        expected_policy_revision=3,
        consent=False,
        data_root=d,
    )
    unknown_grant = str(uuid.uuid4())
    _expect(
        auth,
        "E_GRANT_NOT_FOUND",
        unknown_grant,
        auth.register_memory_binding,
        grant_id=unknown_grant,
        session_id="session-2",
        host_id="host-1",
        expected_policy_revision=3,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_before

    params = inspect.signature(auth.resolve_memory_scope).parameters.values()
    assert [(p.name, p.default) for p in params] == EXPECTED_SIGNATURES[
        "resolve_memory_scope"
    ]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params)

    payload = _raw(d)
    payload["data"]["bindings"][binding["binding_id"]]["grant_id"] = str(uuid.uuid4())
    _write_raw(d, payload)
    loaded = auth.load_policy_readonly(data_root=d)
    assert loaded["state"] == "invalid"
    assert loaded["reason"] == "dangling_binding"
    _assert_denied(_resolve(auth, root_a, d), "policy_invalid")


def test_owner_source_operation_filters(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    alice = OwnerScope("agent", "alice")
    bob = OwnerScope("agent", "bob")
    _grant(auth, root, alice, d, sources=("source-a", "source-b"), ops=("ask", "list"))
    bob_grant = _grant(
        auth, root, bob, d, sources=("source-c",), ops=FIVE_OPS, expected=1
    )

    _assert_denied(_resolve(auth, root, d), "owner_required")
    one = _resolve(auth, root, d, owner_scope=alice, requested_sources=["source-a"])
    _assert_granted(one)
    assert one["approved_sources"] == ["source-a"]
    both = _resolve(auth, root, d, owner_scope=alice, requested_sources=())
    _assert_granted(both)
    assert both["approved_sources"] == ["source-a", "source-b"]
    _assert_denied(
        _resolve(auth, root, d, owner_scope=alice, requested_sources=["source-c"]),
        "source_not_granted",
    )
    _assert_denied(
        _resolve(auth, root, d, "expand", owner_scope=alice), "operation_not_granted"
    )
    _assert_denied(
        _resolve(auth, root, d, "write", owner_scope=alice), "operation_not_granted"
    )
    _assert_granted(_resolve(auth, root, d, "write", owner_scope=bob), "write")
    _assert_denied(
        _resolve(auth, root, d, owner_scope=OwnerScope("agent", "carol")),
        "owner_not_granted",
    )
    _assert_denied(
        _resolve(auth, root, d, "bogus", owner_scope=alice), "invalid_request"
    )
    _assert_denied(
        _resolve(auth, root, d, owner_scope=alice, requested_sources="source-a"),
        "invalid_request",
    )

    sha_before = _sha(_policy_file(d))
    carol = OwnerScope("agent", "carol")
    bad_inputs: list[tuple[str, dict[str, Any]]] = [
        (
            "approved_sources",
            {
                "owner_scope": carol,
                "approved_sources": [],
                "allowed_operations": ["ask"],
            },
        ),
        (
            "approved_sources",
            {
                "owner_scope": carol,
                "approved_sources": ["source-x", "source-x"],
                "allowed_operations": ["ask"],
            },
        ),
        (
            "approved_sources",
            {
                "owner_scope": carol,
                "approved_sources": ["*"],
                "allowed_operations": ["ask"],
            },
        ),
        (
            "allowed_operations",
            {
                "owner_scope": carol,
                "approved_sources": ["source-x"],
                "allowed_operations": ["bogus"],
            },
        ),
        (
            "overlay_read_requires_overlay_owner",
            {
                "owner_scope": legacy_owner_scope(root),
                "approved_sources": ["source-x"],
                "allowed_operations": ["overlay_read"],
            },
        ),
        (
            "expected_policy_revision",
            {
                "owner_scope": carol,
                "approved_sources": ["source-x"],
                "allowed_operations": ["ask"],
                "expected_policy_revision": True,
            },
        ),
        (
            "expires_at",
            {
                "owner_scope": carol,
                "approved_sources": ["source-x"],
                "allowed_operations": ["ask"],
                "expires_at": 10**400,
            },
        ),
    ]
    for reason, bad in bad_inputs:
        kwargs: dict[str, Any] = {
            "project_root": root,
            "expected_policy_revision": 2,
            "consent": True,
            "data_root": d,
        }
        kwargs.update(bad)
        _expect(auth, "E_INPUT", reason, auth.grant_memory_scope, **kwargs)
        assert _sha(_policy_file(d)) == sha_before

    auth.revoke_memory_scope(
        grant_id=bob_grant["grant_id"],
        expected_policy_revision=2,
        consent=True,
        data_root=d,
    )
    selected = _resolve(auth, root, d)
    _assert_granted(selected)
    assert selected["owner_scope"] == {"kind": "agent", "id": "alice"}


def test_preferences_need_separate_approval(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    project_owner = legacy_owner_scope(root)
    overlay = auth.user_overlay_owner_scope(data_root=d)
    assert overlay == OwnerScope("user", str((d / "user").resolve()))

    project_grant = _grant(
        auth, root, project_owner, d, sources=("project-memory",), ops=FIVE_OPS
    )
    _assert_denied(
        _resolve(auth, root, d, "overlay_read", owner_scope=overlay),
        "owner_not_granted",
    )
    _assert_denied(
        _resolve(auth, root, d, "overlay_read", owner_scope=project_owner),
        "operation_not_granted",
    )

    overlay_grant = _grant(
        auth,
        root,
        overlay,
        d,
        sources=("personal-preferences",),
        ops=("overlay_read",),
        expected=1,
    )
    assert overlay_grant["grant_id"] != project_grant["grant_id"]
    assert overlay_grant["owner_scope"] == {"kind": "user", "id": overlay.id}
    granted = _resolve(auth, root, d, "overlay_read", owner_scope=overlay)
    _assert_granted(granted)
    assert granted["grant_id"] == overlay_grant["grant_id"]

    implicit = _resolve(auth, root, d, "ask")
    _assert_granted(implicit)
    assert implicit["grant_id"] == project_grant["grant_id"]

    auth.revoke_memory_scope(
        grant_id=project_grant["grant_id"],
        expected_policy_revision=2,
        consent=True,
        data_root=d,
    )
    _assert_granted(_resolve(auth, root, d, "overlay_read", owner_scope=overlay))
    auth.revoke_memory_scope(
        grant_id=overlay_grant["grant_id"],
        expected_policy_revision=3,
        consent=True,
        data_root=d,
    )
    _assert_denied(
        _resolve(auth, root, d, "overlay_read", owner_scope=overlay), "revoked"
    )


def test_binding_registration_requires_setup_consent(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    grant = _grant(auth, root, owner, d)
    n = grant["policy_revision"]
    sha_n = _sha(_policy_file(d))

    _expect(
        auth,
        "E_CONSENT",
        "consent_required",
        auth.register_memory_binding,
        grant_id=grant["grant_id"],
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=n,
        consent=False,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_n

    binding = _bind(auth, grant["grant_id"], d, expected=n)
    assert set(binding) == BINDING_KEYS
    assert _is_uuid4(binding["binding_id"])
    assert re.fullmatch(r"[0-9a-f]{64}", binding["scope_fingerprint"])
    assert binding == {
        "binding_id": binding["binding_id"],
        "grant_id": grant["grant_id"],
        "policy_revision": n + 1,
        "project_id": record.project_id,
        "worktree_id": _worktree_id(root),
        "scope_fingerprint": binding["scope_fingerprint"],
        "host_id": "host-1",
        "session_id": "session-1",
        "revoked": False,
    }
    assert _raw(d)["version"] == n + 1

    sha_n1 = _sha(_policy_file(d))
    assert _bind(auth, grant["grant_id"], d, expected=n) == binding
    assert _sha(_policy_file(d)) == sha_n1
    _expect(
        auth,
        "E_VERSION",
        f"expected revision {n}, found {n + 1}",
        auth.register_memory_binding,
        grant_id=grant["grant_id"],
        session_id="session-2",
        host_id="host-1",
        expected_policy_revision=n,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_n1

    bound = _resolve(auth, root, d, session_binding=binding["binding_id"])
    _assert_granted(bound)
    assert bound["session_binding"] == binding["binding_id"]

    superseding = _grant(auth, root, owner, d, sources=("source-b",), expected=n + 1)
    assert superseding["policy_revision"] == n + 2
    _assert_denied(
        _resolve(auth, root, d, session_binding=binding["binding_id"]),
        "binding_revoked",
    )
    loaded = auth.load_policy_readonly(data_root=d)
    old = loaded["grants"][grant["grant_id"]]
    assert old["superseded_by"] == superseding["grant_id"]
    assert old["revoked"] is True
    assert old["revoked_revision"] == n + 2
    assert loaded["bindings"][binding["binding_id"]]["revoked"] is True


def test_policy_values_survive_secret_redactor(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    project = tmp_path / "Developer" / "desk-assistant-project-v2"
    project.mkdir(parents=True)
    register_project(project, data_root=d)
    root = project.resolve()
    owner = OwnerScope("agent", "token:alice")

    grant = _grant(auth, root, owner, d, sources=("token:abc",))
    assert grant["owner_scope"] == {"kind": "agent", "id": "token:alice"}
    assert grant["approved_sources"] == ["token:abc"]
    view = auth.load_policy_readonly(data_root=d)["grants"][grant["grant_id"]]
    assert str(view["project_root"]) == str(root)
    assert view["owner_scope"] == {"kind": "agent", "id": "token:alice"}
    assert view["approved_sources"] == ["token:abc"]
    resolved = _resolve(auth, root, d, owner_scope=owner)
    _assert_granted(resolved)
    assert str(resolved["project_root"]) == str(root)
    assert resolved["owner_scope"] == {"kind": "agent", "id": "token:alice"}
    assert resolved["approved_sources"] == ["token:abc"]
    assert b"REDACTED" not in _policy_file(d).read_bytes()

    sha_before = _sha(_policy_file(d))
    error = _expect(
        auth,
        "E_INPUT",
        "secret_like_value",
        auth.register_memory_binding,
        grant_id=grant["grant_id"],
        session_id="session-1",
        host_id="token:abc",
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    assert error.reason == "secret_like_value"
    assert _sha(_policy_file(d)) == sha_before


def _craft_invalid(case: str, d: Path, tmp_path: Path) -> None:
    policy = _policy_file(d)
    payload = _raw(d)
    data = payload["data"]
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    if case == "duplicate_key":
        text = (
            '{"schema_version": "1.0.0", "version": 1, "version": 1, "data": '
            + json.dumps(data)
            + "}"
        )
        policy.write_text(text, encoding="utf-8")
    elif case == "malformed_json":
        policy.write_bytes(b'{"schema_version": "1.0.0", "version": ')
    elif case == "not_utf8":
        policy.write_bytes(b'{"schema_version": "\xff\xfe"}')
    elif case == "bool_version":
        payload["version"] = True
        _write_raw(d, payload)
    elif case == "revision_mismatch":
        data["policy_revision"] = 2
        _write_raw(d, payload)
    elif case == "schema_version_unsupported":
        data["schema_version"] = 2
        _write_raw(d, payload)
    elif case == "unknown_field":
        data["extra"] = {}
        _write_raw(d, payload)
    elif case == "unknown_grant_field":
        for record in data["grants"].values():
            record["color"] = "blue"
        _write_raw(d, payload)
    elif case == "bool_policy_revision":
        data["policy_revision"] = True
        _write_raw(d, payload)
    elif case == "duplicate_active_grant":
        (record,) = data["grants"].values()
        copy = dict(record)
        copy["grant_id"] = str(uuid.uuid4())
        data["grants"][copy["grant_id"]] = copy
        _write_raw(d, payload)
    elif case == "symlink_file":
        target = elsewhere / "memory_authorization.json"
        shutil.move(str(policy), str(target))
        policy.symlink_to(target)
    elif case == "symlink_user_dir":
        target = elsewhere / "user"
        shutil.move(str(d.resolve() / "user"), str(target))
        (d.resolve() / "user").symlink_to(target, target_is_directory=True)
    elif case == "directory_at_file":
        policy.unlink()
        policy.mkdir()
    elif case in ("huge_int_consented_at", "huge_int_expires_at"):
        field = case.removeprefix("huge_int_")
        for record in data["grants"].values():
            record[field] = 10**400
        _write_raw(d, payload)
    elif case == "overlay_read_on_project_grant":
        for record in data["grants"].values():
            record["allowed_operations"] = ["ask", "overlay_read"]
        _write_raw(d, payload)
    elif case in ("owner_kind_list", "owner_kind_dict"):
        for record in data["grants"].values():
            record["owner_scope"]["kind"] = [] if case == "owner_kind_list" else {}
        _write_raw(d, payload)
    elif case == "bool_consented_at":
        for record in data["grants"].values():
            record["consented_at"] = True
        _write_raw(d, payload)
    elif case == "bool_revoked_at":
        for record in data["grants"].values():
            record.update(revoked=True, revoked_at=True, revoked_revision=1)
        _write_raw(d, payload)
    else:  # pragma: no cover - parametrize ids are fixed
        raise AssertionError(case)


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        pytest.param("duplicate_key", "duplicate_key", id="duplicate_key"),
        pytest.param("malformed_json", "malformed_json", id="malformed_json"),
        pytest.param("not_utf8", "not_utf8", id="not_utf8"),
        pytest.param("bool_version", "revision_invalid", id="bool_version"),
        pytest.param("revision_mismatch", "revision_mismatch", id="revision_mismatch"),
        pytest.param(
            "schema_version_unsupported",
            "schema_version_unsupported",
            id="schema_version_unsupported",
        ),
        pytest.param("unknown_field", "unknown_field", id="unknown_field"),
        pytest.param("unknown_grant_field", "record_invalid", id="unknown_grant_field"),
        pytest.param(
            "bool_policy_revision", "revision_mismatch", id="bool_policy_revision"
        ),
        pytest.param(
            "duplicate_active_grant",
            "duplicate_active_grant",
            id="duplicate_active_grant",
        ),
        pytest.param(
            "symlink_file", "symlink", id="symlink_file", marks=pytest.mark.posix_only
        ),
        pytest.param(
            "symlink_user_dir",
            "symlink",
            id="symlink_user_dir",
            marks=pytest.mark.posix_only,
        ),
        pytest.param("directory_at_file", "not_regular_file", id="directory_at_file"),
        pytest.param(
            "huge_int_consented_at", "record_invalid", id="huge_int_consented_at"
        ),
        pytest.param("huge_int_expires_at", "record_invalid", id="huge_int_expires_at"),
        pytest.param(
            "overlay_read_on_project_grant",
            "record_invalid",
            id="overlay_read_on_project_grant",
        ),
        pytest.param("bool_consented_at", "record_invalid", id="bool_consented_at"),
        pytest.param("bool_revoked_at", "record_invalid", id="bool_revoked_at"),
        pytest.param("owner_kind_list", "record_invalid", id="owner_kind_list"),
        pytest.param("owner_kind_dict", "record_invalid", id="owner_kind_dict"),
    ],
)
def test_load_policy_rejects_invalid_file(
    tmp_path: Path, case: str, reason: str
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    _grant(auth, root, owner, d)
    _craft_invalid(case, d, tmp_path)
    before = _snapshot(d.resolve() / "user", tmp_path / "elsewhere")

    loaded = auth.load_policy_readonly(data_root=d)
    assert loaded["state"] == "invalid"
    assert loaded["reason"] == reason
    assert loaded["policy_revision"] == 0
    assert loaded["content_sha256"] is None
    assert (loaded["grants"], loaded["bindings"], loaded["mappings"]) == ({}, {}, {})
    _assert_denied(_resolve(auth, root, d, owner_scope=owner), "policy_invalid")
    _expect(
        auth,
        "E_POLICY_INVALID",
        reason,
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=OwnerScope("agent", "other"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    assert _snapshot(d.resolve() / "user", tmp_path / "elsewhere") == before


def test_module_import_is_cycle_free() -> None:
    code = (
        "import json, sys\n"
        "import rush.memory.authorization\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith('rush'))))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=_child_env(),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    assert "rush.memory.authorization" in loaded
    forbidden = [
        m
        for m in loaded
        if m.startswith(("rush.tools", "rush.dashboard", "rush.workflows"))
        or m in {"rush.memory.store", "rush.memory.retrieval"}
    ]
    assert forbidden == []


def test_t01_fixture_call_contract(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    root = tmp_path / "project"
    root.mkdir()
    record = register_project(root, data_root=tmp_path / "user-data")
    owner = OwnerScope("agent", "alice")
    grant = auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=["source-a"],
        allowed_operations=["write", "ask", "expand", "list", "bootstrap"],
        expected_policy_revision=0,
        consent=True,
        data_root=tmp_path / "user-data",
    )
    result = auth.resolve_memory_scope(
        project_root=root,
        operation="ask",
        owner_scope=owner,
        requested_sources=["source-a"],
        data_root=tmp_path / "user-data",
    )
    assert set(result) == RESOLVE_KEYS
    assert str(result["project_root"]) == str(root.resolve())
    assert {k: v for k, v in result.items() if k != "project_root"} == {
        "access": "read",
        "reason": "granted",
        "operation": "ask",
        "grant_id": grant["grant_id"],
        "grant_revision": 1,
        "policy_revision": 1,
        "project_id": record.project_id,
        "worktree_id": _worktree_id(root),
        "owner_scope": {"kind": "agent", "id": "alice"},
        "approved_sources": ["source-a"],
        "allowed_operations": ["ask", "bootstrap", "expand", "list", "write"],
        "session_binding": None,
    }

    assert (
        frozenset(
            {"ask", "bootstrap", "expand", "list", "write", "history", "overlay_read"}
        )
        == auth.GRANT_OPERATIONS
    )
    assert Path("user/.rush/memory_authorization.json") == auth.POLICY_RELATIVE_PATH
    for name, expected in EXPECTED_SIGNATURES.items():
        params = inspect.signature(getattr(auth, name)).parameters.values()
        assert [(p.name, p.default) for p in params] == expected, name
        assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params), name


@pytest.mark.posix_only
def test_os_principal_posix(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    principal = auth._current_os_principal()
    assert principal == f"uid:{os.getuid()}"
    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    grant = _grant(auth, root, legacy_owner_scope(root), d)
    loaded = auth.load_policy_readonly(data_root=d)
    assert loaded["grants"][grant["grant_id"]]["principal"] == principal


@pytest.mark.windows_only
def test_os_principal_windows_sid() -> None:
    import rush.memory.authorization as auth

    assert re.fullmatch(r"sid:S-1(-\d+)+", auth._current_os_principal())


def test_resolve_overlay_read_requires_overlay_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    _grant(auth, root, owner, d)
    sha_before = _sha(_policy_file(d))

    # The loader rejects such a file, so inject the view past it (defense in depth).
    real_load = auth._load

    def tampered(data_root: Path | None) -> Any:
        result, data = real_load(data_root)
        for view in result["grants"].values():
            view["allowed_operations"] = ["ask", "overlay_read"]
        return result, data

    monkeypatch.setattr(auth, "_load", tampered)
    _assert_denied(
        _resolve(auth, root, d, "overlay_read", owner_scope=owner),
        "operation_not_granted",
    )
    _assert_denied(_resolve(auth, root, d, "overlay_read"), "operation_not_granted")
    _assert_granted(_resolve(auth, root, d, "ask", owner_scope=owner))
    assert _sha(_policy_file(d)) == sha_before


@pytest.mark.posix_only
def test_writers_deny_symlink_loop_data_root(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    project = tmp_path / "project"
    project.mkdir()
    before = _snapshot(tmp_path)

    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.grant_memory_scope,
        project_root=project,
        owner_scope=OwnerScope("agent", "alice"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=0,
        consent=True,
        data_root=loop,
    )
    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.revoke_memory_scope,
        grant_id=str(uuid.uuid4()),
        expected_policy_revision=0,
        consent=True,
        data_root=loop,
    )
    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.register_memory_binding,
        grant_id=str(uuid.uuid4()),
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=0,
        consent=True,
        data_root=loop,
    )
    loaded = auth.load_policy_readonly(data_root=loop)
    assert (loaded["state"], loaded["reason"]) == (
        "unavailable",
        "data_root_unavailable",
    )
    _assert_denied(_resolve(auth, project, loop), "policy_invalid")
    assert _snapshot(tmp_path) == before


def test_register_rejects_format_characters(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    grant = _grant(auth, root, legacy_owner_scope(root), d)
    sha_before = _sha(_policy_file(d))

    cases = [
        ("session_id", "ses\u202eion"),
        ("session_id", "a\u200bb"),
        ("host_id", "host\u200b1"),
    ]
    for name, value in cases:
        labels = {"session_id": "session-1", "host_id": "host-1", name: value}
        _expect(
            auth,
            "E_INPUT",
            name,
            auth.register_memory_binding,
            grant_id=grant["grant_id"],
            expected_policy_revision=1,
            consent=True,
            data_root=d,
            **labels,
        )
        assert _sha(_policy_file(d)) == sha_before


def test_binding_stale_on_tampered_fingerprint(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    grant = _grant(auth, root, legacy_owner_scope(root), d)
    binding = _bind(auth, grant["grant_id"], d, expected=1)
    _assert_granted(_resolve(auth, root, d, session_binding=binding["binding_id"]))

    payload = _raw(d)
    payload["data"]["bindings"][binding["binding_id"]]["scope_fingerprint"] = "0" * 64
    _write_raw(d, payload)
    crafted_sha = _sha(_policy_file(d))
    assert auth.load_policy_readonly(data_root=d)["state"] == "ok"
    _assert_denied(
        _resolve(auth, root, d, session_binding=binding["binding_id"]), "binding_stale"
    )
    assert _sha(_policy_file(d)) == crafted_sha


def test_swap_between_lstat_and_open_is_file_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    grant = _grant(auth, root, owner, d)
    policy = _policy_file(d)
    sha_before = _sha(policy)
    real_open = os.open

    def swapping_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        # Replace the policy with an identical copy (new inode) on every open.
        if not isinstance(path, int) and Path(path) == policy:
            spare = policy.with_name("swap.tmp")
            spare.write_bytes(policy.read_bytes())
            os.replace(spare, policy)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(auth.os, "open", swapping_open)
    loaded = auth.load_policy_readonly(data_root=d)
    assert (loaded["state"], loaded["reason"]) == ("invalid", "file_changed")
    _assert_denied(_resolve(auth, root, d, owner_scope=owner), "policy_invalid")
    _expect(
        auth,
        "E_POLICY_INVALID",
        "file_changed",
        auth.revoke_memory_scope,
        grant_id=grant["grant_id"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    monkeypatch.undo()
    assert _sha(policy) == sha_before
    assert not policy.with_name("swap.tmp").exists()
    assert auth.load_policy_readonly(data_root=d)["state"] == "ok"


def test_grant_requires_registered_project(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    _project(tmp_path, "registered", d)
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    kwargs: dict[str, Any] = {
        "project_root": stranger,
        "owner_scope": OwnerScope("agent", "alice"),
        "approved_sources": ["source-a"],
        "allowed_operations": ["ask"],
        "expected_policy_revision": 0,
        "consent": True,
        "data_root": d,
    }
    before = _snapshot(d)
    _expect(
        auth,
        "E_PROJECT_NOT_REGISTERED",
        "project_not_registered",
        auth.grant_memory_scope,
        **kwargs,
    )
    assert _snapshot(d) == before

    (d / "projects.json").write_bytes(b"{not json")
    before = _snapshot(d)
    _expect(
        auth,
        "E_PROJECT_NOT_REGISTERED",
        "project_registry_invalid",
        auth.grant_memory_scope,
        **{**kwargs, "project_root": tmp_path / "registered"},
    )
    assert _snapshot(d) == before
    assert not _policy_file(d).exists()


@pytest.mark.posix_only
def test_principal_unavailable_in_load_resolve_and_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    grant = _grant(auth, root, owner, d)
    sha_before = _sha(_policy_file(d))
    real_principal = auth._current_os_principal

    def failing() -> str:
        raise OSError("no principal")

    monkeypatch.setattr(auth, "_current_os_principal", failing)
    loaded = auth.load_policy_readonly(data_root=d)
    assert (loaded["state"], loaded["reason"]) == ("invalid", "principal_unavailable")

    calls = {"n": 0}

    def fails_after_load() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return real_principal()
        raise OSError("no principal")

    monkeypatch.setattr(auth, "_current_os_principal", fails_after_load)
    _assert_denied(_resolve(auth, root, d, owner_scope=owner), "principal_unavailable")
    assert calls["n"] == 2

    monkeypatch.setattr(auth, "_current_os_principal", failing)
    _expect(
        auth,
        "E_PRINCIPAL",
        "principal_unavailable",
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=OwnerScope("agent", "alice"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_PRINCIPAL",
        "principal_unavailable",
        auth.revoke_memory_scope,
        grant_id=grant["grant_id"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_PRINCIPAL",
        "principal_unavailable",
        auth.register_memory_binding,
        grant_id=grant["grant_id"],
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_before


def test_commit_redaction_precheck_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    grant = _grant(auth, root, legacy_owner_scope(root), d)
    sha_before = _sha(_policy_file(d))

    monkeypatch.setattr(
        auth, "sanitize_value", lambda value: SimpleNamespace(redacted=True)
    )
    _expect(
        auth,
        "E_POLICY_REDACTION",
        "secret_like_value",
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=OwnerScope("agent", "alice"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_POLICY_REDACTION",
        "secret_like_value",
        auth.register_memory_binding,
        grant_id=grant["grant_id"],
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_before


def test_register_refuses_revoked_and_expired_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    clock = {"now": time.time()}
    monkeypatch.setattr(auth, "_now", lambda: clock["now"])
    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    alpha = _grant(auth, root, OwnerScope("agent", "alpha"), d)
    beta = _grant(
        auth,
        root,
        OwnerScope("agent", "beta"),
        d,
        expected=1,
        expires_at=clock["now"] + 60,
    )
    auth.revoke_memory_scope(
        grant_id=alpha["grant_id"],
        expected_policy_revision=2,
        consent=True,
        data_root=d,
    )
    sha_before = _sha(_policy_file(d))

    _expect(
        auth,
        "E_GRANT_INACTIVE",
        "revoked",
        auth.register_memory_binding,
        grant_id=alpha["grant_id"],
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=3,
        consent=True,
        data_root=d,
    )
    clock["now"] += 61
    _expect(
        auth,
        "E_GRANT_INACTIVE",
        "expired",
        auth.register_memory_binding,
        grant_id=beta["grant_id"],
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=3,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_before


def test_lock_acquisition_failure_is_e_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.dashboard.state as dashboard_state
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    grant = _grant(auth, root, legacy_owner_scope(root), d)
    sha_before = _sha(_policy_file(d))

    storages: list[str] = []

    def failing_acquire(
        project_id: str, *, data_root: Path | None = None, storage: str = "file"
    ) -> Any:
        storages.append(storage)
        raise OSError("lock busy")

    monkeypatch.setattr(
        dashboard_state, "_acquire_cross_process_project_lock", failing_acquire
    )
    _expect(
        auth,
        "E_LOCK",
        "lock busy",
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=OwnerScope("agent", "alice"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_LOCK",
        "lock busy",
        auth.revoke_memory_scope,
        grant_id=grant["grant_id"],
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_LOCK",
        "lock busy",
        auth.register_memory_binding,
        grant_id=grant["grant_id"],
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=1,
        consent=True,
        data_root=d,
    )
    # D2: every policy writer takes the policy lock on the data-root directory.
    assert storages == ["directory"] * 3
    assert _sha(_policy_file(d)) == sha_before


def test_nul_byte_paths_raise_only_policy_errors(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    bad = Path(str(tmp_path) + "/a\x00b")
    d = _data_root(tmp_path)
    project = tmp_path / "project"
    project.mkdir()
    before = _snapshot(tmp_path)

    loaded = auth.load_policy_readonly(data_root=bad)
    assert set(loaded) == LOAD_KEYS
    assert (loaded["state"], loaded["reason"]) == (
        "unavailable",
        "data_root_unavailable",
    )
    for func in (auth.policy_path, auth.user_overlay_owner_scope):
        _expect(auth, "E_POLICY_INVALID", "data_root_unavailable", func, data_root=bad)
    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.grant_memory_scope,
        project_root=project,
        owner_scope=OwnerScope("agent", "alice"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=0,
        consent=True,
        data_root=bad,
    )
    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.revoke_memory_scope,
        grant_id=str(uuid.uuid4()),
        expected_policy_revision=0,
        consent=True,
        data_root=bad,
    )
    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.register_memory_binding,
        grant_id=str(uuid.uuid4()),
        session_id="session-1",
        host_id="host-1",
        expected_policy_revision=0,
        consent=True,
        data_root=bad,
    )
    _expect(
        auth,
        "E_INPUT",
        "project_missing",
        auth.grant_memory_scope,
        project_root=bad,
        owner_scope=OwnerScope("agent", "alice"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=0,
        consent=True,
        data_root=d,
    )
    _assert_denied(_resolve(auth, project, bad), "policy_invalid")
    assert _snapshot(tmp_path) == before


def test_lone_surrogates_rejected_before_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    grant = _grant(auth, root, OwnerScope("agent", "alice"), d)
    sha_before = _sha(_policy_file(d))

    def no_lock(**_kwargs: Any) -> Any:
        raise AssertionError("the lock must not be taken")

    monkeypatch.setattr(auth, "hold_policy_lock", no_lock)
    base: dict[str, Any] = {
        "project_root": root,
        "owner_scope": OwnerScope("agent", "alice"),
        "approved_sources": ["source-a"],
        "allowed_operations": ["ask"],
        "expected_policy_revision": 1,
        "consent": True,
        "data_root": d,
    }
    _expect(
        auth,
        "E_INPUT",
        "approved_sources",
        auth.grant_memory_scope,
        **{**base, "approved_sources": ["a\ud800"]},
    )
    _expect(
        auth,
        "E_INPUT",
        "owner_scope",
        auth.grant_memory_scope,
        **{**base, "owner_scope": OwnerScope("agent", "\udcff")},
    )
    binding: dict[str, Any] = {
        "grant_id": grant["grant_id"],
        "session_id": "session-1",
        "host_id": "host-1",
        "expected_policy_revision": 1,
        "consent": True,
        "data_root": d,
    }
    _expect(
        auth,
        "E_INPUT",
        "session_id",
        auth.register_memory_binding,
        **{**binding, "session_id": "a\ud800b"},
    )
    _expect(
        auth,
        "E_INPUT",
        "host_id",
        auth.register_memory_binding,
        **{**binding, "host_id": "h\udcff"},
    )
    _assert_denied(
        _resolve(auth, root, d, owner_scope=OwnerScope("agent", "\udcff")),
        "invalid_request",
    )
    assert _sha(_policy_file(d)) == sha_before


@pytest.mark.posix_only
def test_overlay_symlink_loop_is_policy_error(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    d.mkdir()
    (d / "user").symlink_to(d / "user")
    project = tmp_path / "project"
    project.mkdir()
    before = _snapshot(tmp_path)

    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.grant_memory_scope,
        project_root=project,
        owner_scope=OwnerScope("user", "q"),
        approved_sources=["source-a"],
        allowed_operations=["overlay_read"],
        expected_policy_revision=0,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_POLICY_INVALID",
        "data_root_unavailable",
        auth.user_overlay_owner_scope,
        data_root=d,
    )
    assert auth.policy_path(data_root=d) == d.resolve() / auth.POLICY_RELATIVE_PATH
    _assert_denied(_resolve(auth, project, d), "policy_invalid")
    assert _snapshot(tmp_path) == before


def test_moved_data_root_keeps_project_grants(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    project_owner = legacy_owner_scope(root)
    overlay = auth.user_overlay_owner_scope(data_root=d)
    project_grant = _grant(
        auth, root, project_owner, d, sources=("project-memory",), ops=FIVE_OPS
    )
    overlay_grant = _grant(
        auth,
        root,
        overlay,
        d,
        sources=("personal-preferences",),
        ops=("overlay_read",),
        expected=1,
    )

    def check(data_root: Path) -> None:
        loaded = auth.load_policy_readonly(data_root=data_root)
        assert (loaded["state"], loaded["reason"]) == ("ok", "ok")
        assert loaded["policy_revision"] == 2
        assert auth.user_overlay_owner_scope(data_root=data_root) != overlay
        for kwargs in ({"owner_scope": project_owner}, {}):
            result = _resolve(auth, root, data_root, "ask", **kwargs)
            _assert_granted(result)
            assert result["grant_id"] == project_grant["grant_id"]
        _assert_denied(
            _resolve(auth, root, data_root, "overlay_read", owner_scope=overlay),
            "operation_not_granted",
        )

    # A case variant of the data root names the same directory only on a
    # case-insensitive filesystem; the probe picks the branch, both assert.
    variant = tmp_path / d.name.upper()
    if variant.exists() and os.path.samefile(variant, d):
        check(variant)
    else:
        assert not variant.exists()
        loaded = auth.load_policy_readonly(data_root=variant)
        assert (loaded["state"], loaded["reason"]) == ("missing", "policy_missing")

    moved = tmp_path / "moved-data"
    shutil.move(str(d), str(moved))
    check(moved)
    revoked = auth.revoke_memory_scope(
        grant_id=overlay_grant["grant_id"],
        expected_policy_revision=2,
        consent=True,
        data_root=moved,
    )
    assert (revoked["revoked"], revoked["policy_revision"]) == (True, 3)
    loaded = auth.load_policy_readonly(data_root=moved)
    assert (loaded["state"], loaded["policy_revision"]) == ("ok", 3)
    assert loaded["grants"][overlay_grant["grant_id"]]["revoked"] is True
    _assert_granted(_resolve(auth, root, moved, "ask"))


def test_resolve_bad_project_root_is_project_missing(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    _grant(auth, root, legacy_owner_scope(root), d)
    for bad in (Path(str(root) + "\x00x"), str(root) + "\ud800"):
        result = _resolve(auth, bad, d)  # type: ignore[arg-type]  # a str project_root is the deliberately wrong type
        _assert_denied(result, "project_missing")
        assert result["policy_revision"] == 1


def test_hold_policy_lock_and_load_reject_unusable_data_roots(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    for bad in (Path(str(tmp_path) + "/a\x00b"), loop):
        with (
            pytest.raises(auth.MemoryPolicyError) as info,
            auth.hold_policy_lock(data_root=bad),
        ):
            pass
        assert (info.value.code, info.value.reason) == (
            "E_POLICY_INVALID",
            "data_root_unavailable",
        )
    for bad_root in (5, 1.5):
        loaded = auth.load_policy_readonly(data_root=bad_root)  # type: ignore[arg-type]
        assert (loaded["state"], loaded["reason"]) == (
            "unavailable",
            "data_root_unavailable",
        )
        _expect(
            auth,
            "E_POLICY_INVALID",
            "data_root_unavailable",
            auth.policy_path,
            data_root=bad_root,
        )
    assert sorted(p.name for p in tmp_path.iterdir()) == ["loop"]


def test_grant_rejects_non_utf8_canonical_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    real_resolve = Path.resolve

    def fake_resolve(self: Path, strict: bool = False) -> Path:
        resolved = real_resolve(self, strict=strict)
        return (
            Path(str(resolved) + "\udcff")
            if resolved == real_resolve(root)
            else resolved
        )

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    monkeypatch.setattr(Path, "is_dir", lambda self: True)
    _expect(
        auth,
        "E_INPUT",
        "project_missing",
        auth.grant_memory_scope,
        project_root=root,
        owner_scope=OwnerScope("agent", "alice"),
        approved_sources=["source-a"],
        allowed_operations=["ask"],
        expected_policy_revision=0,
        consent=True,
        data_root=d,
    )


# --- 72-T01 R12: PR6 survivors, one case per surviving guard mutant -------------


def _inject_grants(monkeypatch: pytest.MonkeyPatch, auth: Any, mutate: Any) -> None:
    """Wrap the strict loader so `mutate(loaded)` can add records the writer could
    never produce (defence in depth behind the loader's own validation)."""
    import copy as _copy

    real_load = auth._load

    def load(data_root: Path | None) -> Any:
        loaded, data = real_load(data_root)
        loaded = _copy.deepcopy(loaded)
        mutate(loaded)
        return loaded, data

    monkeypatch.setattr(auth, "_load", load)


PR6_CASES = [
    "principal_regex",
    "snapshot_version",
    "snapshot_data",
    "revoke_grant_id_input",
    "binding_grant_id_input",
    "resolve_project_root_type",
    "session_binding_type",
    "registry_invalid",
    "duplicate_candidates",
    "revoke_unknown_grant",
    "binding_principal_mismatch",
    "project_is_a_file",
    "project_removed",
    "unregistered_project",
    "overlay_only_no_owner",
    "binding_stale_project_id",
    "binding_stale_worktree_id",
    "root_match_unregistered",
    "other_project_grant_is_no_candidate",
    "relink_moved_root",
    "overlay_owner_without_overlay_read",
    "agent_overlay_read_injected",
    "grant_without_project_id_injected",
    "user_kind_owner_without_overlay_read",
    "stage0_wildcard_requested_source",
    "stage14_family_item_granted",
    "require_sources_pattern_item",
]


@pytest.mark.parametrize("case", PR6_CASES)
def test_t01_pr6_authorization_guards(
    case: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types as _types
    import uuid as _uuid

    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    policy = _policy_file(d)

    if case == "principal_regex":
        grant = _grant(auth, root, owner, d)
        sha = _sha(policy)
        monkeypatch.setattr(auth, "_current_os_principal", lambda: "root")
        for call in (
            lambda: auth.revoke_memory_scope(
                grant_id=grant["grant_id"],
                expected_policy_revision=1,
                consent=True,
                data_root=d,
            ),
            lambda: auth.register_memory_binding(
                grant_id=grant["grant_id"],
                session_id="s",
                host_id="h",
                expected_policy_revision=1,
                consent=True,
                data_root=d,
            ),
            lambda: _grant(auth, root, OwnerScope("agent", "x"), d, expected=1),
        ):
            with pytest.raises(auth.MemoryPolicyError) as info:
                call()
            assert (info.value.code, info.value.reason) == (
                "E_PRINCIPAL",
                "principal_unavailable",
            )
        assert _sha(policy) == sha
        return

    if case in {"snapshot_version", "snapshot_data"}:
        real = auth.CASMapTransaction

        class Skewed:
            def __init__(self, **kwargs: Any) -> None:
                self._real = real(**kwargs)

            def write(self, data: Any, expected_version: int) -> Any:
                snap = self._real.write(data, expected_version=expected_version)
                return _types.SimpleNamespace(
                    version=snap.version + (1 if case == "snapshot_version" else 0),
                    data=snap.data
                    if case == "snapshot_version"
                    else {**snap.data, "extra": 1},
                )

        monkeypatch.setattr(auth, "CASMapTransaction", Skewed)
        _expect(
            auth,
            "E_POLICY_IO",
            "written_snapshot_mismatch",
            auth.grant_memory_scope,
            project_root=root,
            owner_scope=owner,
            approved_sources=["source-a"],
            allowed_operations=["ask"],
            expected_policy_revision=0,
            consent=True,
            data_root=d,
        )
        monkeypatch.setattr(auth, "CASMapTransaction", real)
        control = _grant(auth, root, OwnerScope("agent", "control"), d, expected=1)
        assert control["policy_revision"] == 2
        return

    if case in {"revoke_grant_id_input", "binding_grant_id_input"}:
        grant = _grant(auth, root, owner, d)
        sha = _sha(policy)
        bad: Any
        for bad in ("", 5, None):
            if case == "revoke_grant_id_input":
                _expect(
                    auth,
                    "E_INPUT",
                    "grant_id",
                    auth.revoke_memory_scope,
                    grant_id=bad,
                    expected_policy_revision=1,
                    consent=True,
                    data_root=d,
                )
            else:
                _expect(
                    auth,
                    "E_INPUT",
                    "grant_id",
                    auth.register_memory_binding,
                    grant_id=bad,
                    session_id="s",
                    host_id="h",
                    expected_policy_revision=1,
                    consent=True,
                    data_root=d,
                )
        assert _sha(policy) == sha
        assert grant["grant_id"]
        return

    if case == "resolve_project_root_type":
        _grant(auth, root, owner, d)
        _assert_granted(_resolve(auth, root, d))
        for bad_root in (5, None, b"x", 1.5):
            result = auth.resolve_memory_scope(
                project_root=bad_root,  # type: ignore[arg-type]  # deliberate wrong type
                operation="ask",
                data_root=d,
            )
            _assert_denied(result, "invalid_request")
        return

    if case == "session_binding_type":
        grant = _grant(auth, root, owner, d)
        binding = _bind(auth, grant["grant_id"], d, expected=1)
        _assert_granted(_resolve(auth, root, d, session_binding=binding["binding_id"]))
        for bad_binding in (5, b"x", ["b"]):
            _assert_denied(
                _resolve(auth, root, d, session_binding=bad_binding),
                "invalid_request",
            )
        return

    if case == "registry_invalid":
        _grant(auth, root, owner, d)
        _assert_granted(_resolve(auth, root, d))
        (d / "projects.json").write_bytes(b"{not json")
        _assert_denied(_resolve(auth, root, d), "project_registry_invalid")
        return

    if case == "duplicate_candidates":
        grant = _grant(auth, root, owner, d)
        _assert_granted(_resolve(auth, root, d))

        def duplicate(loaded: dict[str, Any]) -> None:
            twin = dict(loaded["grants"][grant["grant_id"]])
            twin["grant_id"] = str(_uuid.uuid4())
            loaded["grants"][twin["grant_id"]] = twin

        _inject_grants(monkeypatch, auth, duplicate)
        _assert_denied(_resolve(auth, root, d), "policy_invalid")
        _assert_denied(_resolve(auth, root, d, owner_scope=owner), "policy_invalid")
        return

    if case == "revoke_unknown_grant":
        grant = _grant(auth, root, owner, d)
        sha = _sha(policy)
        unknown = str(_uuid.uuid4())
        _expect(
            auth,
            "E_GRANT_NOT_FOUND",
            unknown,
            auth.revoke_memory_scope,
            grant_id=unknown,
            expected_policy_revision=1,
            consent=True,
            data_root=d,
        )
        _expect(
            auth,
            "E_GRANT_NOT_FOUND",
            unknown,
            auth.register_memory_binding,
            grant_id=unknown,
            session_id="s",
            host_id="h",
            expected_policy_revision=1,
            consent=True,
            data_root=d,
        )
        assert _sha(policy) == sha
        assert grant["grant_id"]
        return

    if case == "binding_principal_mismatch":
        grant = _grant(auth, root, owner, d)
        control = _bind(auth, grant["grant_id"], d, expected=1, session_id="one")
        assert control["revoked"] is False
        payload = _raw(d)
        payload["data"]["grants"][grant["grant_id"]]["principal"] = "uid:999999"
        _write_raw(d, payload)
        assert auth.load_policy_readonly(data_root=d)["state"] == "ok"
        sha = _sha(policy)
        _expect(
            auth,
            "E_PRINCIPAL",
            "principal_mismatch",
            auth.register_memory_binding,
            grant_id=grant["grant_id"],
            session_id="two",
            host_id="h",
            expected_policy_revision=2,
            consent=True,
            data_root=d,
        )
        assert _sha(policy) == sha
        return

    if case in {"project_is_a_file", "project_removed"}:
        _grant(auth, root, owner, d)
        _assert_granted(_resolve(auth, root, d))
        if case == "project_is_a_file":
            target = tmp_path / "file.txt"
            target.write_text("not a directory", encoding="utf-8")
        else:
            target = root
            shutil.rmtree(root)
        _assert_denied(_resolve(auth, target, d), "project_missing")
        return

    if case == "unregistered_project":
        _grant(auth, root, owner, d)
        other = tmp_path / "other"
        other.mkdir()
        _assert_denied(_resolve(auth, other.resolve(), d), "project_not_registered")
        register_project(other, data_root=d)
        _assert_denied(_resolve(auth, other.resolve(), d), "no_grant")
        return

    if case == "overlay_only_no_owner":
        overlay = auth.user_overlay_owner_scope(data_root=d)
        _grant(auth, root, overlay, d, ops=("overlay_read",))
        _assert_denied(_resolve(auth, root, d, "ask"), "owner_not_granted")
        _grant(auth, root, owner, d, ops=("ask",), expected=1)
        _assert_granted(_resolve(auth, root, d, "ask"))
        return

    if case in {"binding_stale_project_id", "binding_stale_worktree_id"}:
        grant = _grant(auth, root, owner, d)
        binding = _bind(auth, grant["grant_id"], d, expected=1)
        _assert_granted(_resolve(auth, root, d, session_binding=binding["binding_id"]))
        payload = _raw(d)
        field = "project_id" if case.endswith("project_id") else "worktree_id"
        payload["data"]["bindings"][binding["binding_id"]][field] = (
            "other-project" if field == "project_id" else "1" * 64
        )
        _write_raw(d, payload)
        assert auth.load_policy_readonly(data_root=d)["state"] == "ok"
        _assert_denied(
            _resolve(auth, root, d, session_binding=binding["binding_id"]),
            "binding_stale",
        )
        return

    if case == "root_match_unregistered":
        _grant(auth, root, owner, d)
        _assert_granted(_resolve(auth, root, d))
        (d / "projects.json").write_text(
            json.dumps({"version": 1, "projects": {}}), encoding="utf-8"
        )
        _assert_denied(_resolve(auth, root, d), "relinked")
        (root / ".rush" / "project.json").unlink()
        reborn = register_project(root, data_root=d)
        assert reborn.project_id != record.project_id
        _assert_denied(_resolve(auth, root, d), "relinked")
        return

    if case == "other_project_grant_is_no_candidate":
        _grant(auth, root, owner, d)
        other, _rec = _project(tmp_path, "other", d)
        _assert_denied(_resolve(auth, other, d), "no_grant")
        return

    if case == "relink_moved_root":
        _grant(auth, root, owner, d)
        new_root = tmp_path / "relinked"
        new_root.mkdir()
        relink_project(
            record.project_id,
            new_root,
            expected_revision=record.revision,
            data_root=d,
        )
        _assert_denied(_resolve(auth, new_root.resolve(), d), "relinked")
        return

    if case == "overlay_owner_without_overlay_read":
        alice = OwnerScope("agent", "alice")
        _grant(auth, root, alice, d, ops=("ask",))
        overlay = auth.user_overlay_owner_scope(data_root=d)
        _grant(auth, root, overlay, d, ops=("ask",), expected=1)
        granted = _resolve(auth, root, d, "ask")
        _assert_granted(granted)
        assert granted["owner_scope"] == {"kind": "agent", "id": "alice"}
        return

    if case == "user_kind_owner_without_overlay_read":
        alice = OwnerScope("user", "alice")
        _grant(auth, root, alice, d, ops=("ask",))
        granted = _resolve(auth, root, d, "ask")
        _assert_granted(granted)
        assert granted["owner_scope"] == {"kind": "user", "id": "alice"}
        return

    if case == "stage0_wildcard_requested_source":
        # D40 stage 0: a requested source is a literal label. The control grants the
        # family item and a literal; only the wildcard request differs.
        _grant(auth, root, owner, d, sources=("intent:*", "source-a"))
        _assert_granted(_resolve(auth, root, d, requested_sources=["source-a"]))
        _assert_denied(
            _resolve(auth, root, d, requested_sources=["intent:*"]), "invalid_request"
        )
        return

    if case == "stage14_family_item_granted":
        # D40 stage 14: `source_granted` decides, so a family item authorizes a
        # non-empty suffix of its own family only.
        _grant(auth, root, owner, d, sources=("intent:*",))
        _assert_granted(_resolve(auth, root, d, requested_sources=["intent:i1"]))
        _assert_denied(
            _resolve(auth, root, d, requested_sources=["recipe:r1"]),
            "source_not_granted",
        )
        _assert_denied(
            _resolve(auth, root, d, requested_sources=["intent:"]),
            "source_not_granted",
        )
        return

    if case == "require_sources_pattern_item":
        # `_require_sources` rejects a pattern item that is not a canonical family.
        _expect(
            auth,
            "E_INPUT",
            "approved_sources",
            auth.grant_memory_scope,
            project_root=root,
            owner_scope=owner,
            approved_sources=["a*b"],
            allowed_operations=["ask"],
            expected_policy_revision=0,
            consent=True,
            data_root=d,
        )
        assert not policy.exists()
        _grant(auth, root, owner, d, sources=("intent:*",))
        assert _sha(policy)
        return

    if case == "grant_without_project_id_injected":
        grant = _grant(auth, root, owner, d)
        _assert_granted(_resolve(auth, root, d))
        (d / "projects.json").write_text(
            json.dumps({"version": 1, "projects": {}}), encoding="utf-8"
        )

        def orphan(loaded: dict[str, Any]) -> None:
            twin = dict(loaded["grants"][grant["grant_id"]])
            twin["project_id"] = None
            twin["project_root"] = str(tmp_path / "elsewhere")
            loaded["grants"] = {_uuid.uuid4().hex: twin}

        _inject_grants(monkeypatch, auth, orphan)
        _assert_denied(_resolve(auth, root, d), "project_not_registered")
        return

    assert case == "agent_overlay_read_injected"
    alice = OwnerScope("agent", "alice")
    grant = _grant(auth, root, alice, d, ops=("ask",))
    _assert_granted(_resolve(auth, root, d, "ask"))

    def foreign_overlay_read(loaded: dict[str, Any]) -> None:
        twin = dict(loaded["grants"][grant["grant_id"]])
        twin["grant_id"] = str(_uuid.uuid4())
        twin["owner_scope"] = {"kind": "agent", "id": "robot"}
        twin["allowed_operations"] = ["ask", "overlay_read"]
        loaded["grants"][twin["grant_id"]] = twin

    _inject_grants(monkeypatch, auth, foreign_overlay_read)
    _assert_denied(_resolve(auth, root, d, "ask"), "owner_required")


# --- 72-T01 R23: D40 writer-source families ----------------------------------------


def test_source_granted_family_items() -> None:
    from rush.memory.authorization import WRITER_SOURCE_FAMILIES, source_granted

    assert dict(WRITER_SOURCE_FAMILIES) == {
        "intent": "intent:",
        "recipe": "recipe:",
        "repair_attempt": "repair_attempt:",
        "invocation": "invocation:",
        "verify_attempt": "verify_attempt:",
    }
    # exact label
    assert source_granted("source-a", ["source-a"]) is True
    assert source_granted("source-b", ["source-a"]) is False
    # family item: a canonical prefix with a non-empty suffix
    for family in WRITER_SOURCE_FAMILIES.values():
        assert source_granted(f"{family}x", [f"{family}*"]) is True, family
        assert source_granted(f"{family}a:b", [f"{family}*"]) is True, family
    # empty suffix and foreign family
    assert source_granted("intent:", ["intent:*"]) is False
    assert source_granted("recipe:x", ["intent:*"]) is False
    assert source_granted("intentx", ["intent:*"]) is False
    assert source_granted("intent:x", ["recipe:*", "invocation:*"]) is False
    # an exact label never authorizes a prefix, and `unknown:*` is not a family
    assert source_granted("intent:x", ["intent:"]) is False
    assert source_granted("intent:", ["intent:"]) is True
    assert source_granted("unknown:x", ["unknown:*"]) is False
    assert source_granted("anything", ["*"]) is False
    # not a string
    for bad in (5, None, b"intent:x", ("intent:x",)):
        assert source_granted(bad, ["intent:*"]) is False, bad  # type: ignore[arg-type]


def test_t01_grant_rejects_pattern_sources_and_accepts_families(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    owner = legacy_owner_scope(root)
    for bad in (["intent*"], ["unknown:*"], ["*"], ["a*b"], ["source-a", "*"]):
        _expect(
            auth,
            "E_INPUT",
            "approved_sources",
            auth.grant_memory_scope,
            project_root=root,
            owner_scope=owner,
            approved_sources=bad,
            allowed_operations=["ask"],
            expected_policy_revision=0,
            consent=True,
            data_root=d,
        )
    assert not _policy_file(d).exists()
    granted = _grant(
        auth,
        root,
        owner,
        d,
        sources=("intent:*", "recipe:*", "intent:", "source-a"),
    )
    assert granted["approved_sources"] == sorted(
        ["intent:*", "recipe:*", "intent:", "source-a"]
    )
    _assert_granted(_resolve(auth, root, d, requested_sources=["intent:i1"]))
    _assert_granted(
        _resolve(auth, root, d, requested_sources=["recipe:r1", "source-a"])
    )
    _assert_denied(
        _resolve(auth, root, d, requested_sources=["verify_attempt:v1"]),
        "source_not_granted",
    )
    # the exact label `intent:` is granted as itself only
    _assert_granted(_resolve(auth, root, d, requested_sources=["intent:"]))


def test_requested_sources_reject_family_patterns(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "project", d)
    _grant(auth, root, legacy_owner_scope(root), d, sources=("intent:*", "source-a"))
    _assert_granted(_resolve(auth, root, d, requested_sources=["intent:i1"]))
    bad: Any
    for bad in (
        ["intent:*"],
        ["*"],
        ["a*b"],
        ["source-a", "intent:*"],
        ["x\x00"],
        ["a\ud800"],
        [""],
        [" source-a"],
        ["a\u200bb"],
        [1],
        [True],
    ):
        _assert_denied(
            _resolve(auth, root, d, requested_sources=bad), "invalid_request"
        )
    assert auth.literal_source_is_valid("source-a") is True
    assert auth.literal_source_is_valid("intent:i1") is True
    for bad_source in (
        "",
        " x",
        "x ",
        "a*",
        "*",
        "x\x00",
        "a\u200bb",
        "a\ud800",
        3,
        None,
    ):
        assert auth.literal_source_is_valid(bad_source) is False, bad_source  # type: ignore[arg-type]


# =============================================================================
# 73-T09/CODEC: capsule mapping consent (`approve_capsule_mapping`,
# `revoke_capsule_mapping`, `resolve_capsule_mapping`, `project_identity`)
# =============================================================================

ALICE = OwnerScope("agent", "alice")
BOB = OwnerScope("agent", "bob")
MAPPING_VIEW_KEYS = {
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
MAPPING_RECORD_KEYS = (MAPPING_VIEW_KEYS - {"target_root"}) | {"target_root_hex"}
ORIGIN_WORKTREE = hashlib.sha256(b"origin-worktree").hexdigest()


def _origin(project: str = "origin-project") -> dict[str, str]:
    return {"project_id": project, "worktree_id": ORIGIN_WORKTREE}


def _revision(auth: Any, d: Path) -> int:
    return int(auth.load_policy_readonly(data_root=d)["policy_revision"] or 0)


def _mapped(
    tmp_path: Path, *, ops: tuple[str, ...] = ("ask", "write")
) -> tuple[Any, Path, Path, dict[str, Any]]:
    """A registered project with one consented `agent:alice` grant holding `ops`."""
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "dest", d)
    grant = _grant(auth, root, ALICE, d, sources=("source-a",), ops=ops)
    return auth, d, root, grant


def _approve(auth: Any, root: Path, d: Path, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "capsule_origin": _origin(),
        "project_root": root,
        "expected_policy_revision": _revision(auth, d),
        "consent": True,
        "data_root": d,
    }
    params.update(extra)
    return auth.approve_capsule_mapping(**params)


def test_capsule_mapping_record_schema_and_cas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, record = _project(tmp_path, "dest", d)
    stranger = tmp_path / "unregistered"
    stranger.mkdir()
    not_a_directory = tmp_path / "example.txt"
    not_a_directory.write_text("not a directory", encoding="utf-8")

    # --- project_identity: read-only, shared with BOOTSTRAP-CONSENT ---
    before = _snapshot(tmp_path)
    identity = auth.project_identity(root, data_root=d)
    assert set(identity) == {"canonical_root", "project_id", "worktree_id"}
    assert identity == {
        "canonical_root": str(root),
        "project_id": record.project_id,
        "worktree_id": _worktree_id(root),
    }
    unregistered = auth.project_identity(stranger, data_root=d)
    assert unregistered == {
        "canonical_root": str(stranger.resolve()),
        "project_id": None,
        "worktree_id": None,
    }
    for unusable in (tmp_path / "missing", not_a_directory, "a\x00b", "\ud800"):
        found = auth.project_identity(unusable, data_root=d)
        assert set(found) == {"canonical_root", "project_id", "worktree_id"}, unusable
        assert found["project_id"] is None and found["worktree_id"] is None, unusable
    assert _snapshot(tmp_path) == before, "project_identity is read-only"
    assert not _policy_file(d).exists(), "project_identity creates no policy"
    assert not (stranger / ".rush").exists()

    # --- approve: the record shape, hex path storage, one revision step ---
    grant = _grant(auth, root, ALICE, d, sources=("source-a",), ops=("ask", "write"))
    monkeypatch.setattr(auth, "_now", lambda: 1_760_000_000.25)
    revision = _revision(auth, d)
    view = auth.approve_capsule_mapping(
        capsule_origin=_origin(),
        project_root=root,
        expected_policy_revision=revision,
        consent=True,
        data_root=d,
    )
    assert set(view) == MAPPING_VIEW_KEYS
    assert _is_uuid4(view["mapping_id"])
    assert view["purpose"] == "capsule_import"
    assert (view["origin_project_id"], view["origin_worktree_id"]) == (
        "origin-project",
        ORIGIN_WORKTREE,
    )
    assert (view["target_project_id"], view["target_worktree_id"]) == (
        record.project_id,
        _worktree_id(root),
    )
    assert view["target_root"] == str(root)
    assert view["target_owner_scope"] == {"kind": "agent", "id": "alice"}
    assert view["grant_id"] == grant["grant_id"]
    assert view["created_revision"] == revision + 1
    assert view["approved_at"] == 1_760_000_000.25
    assert view["revoked"] is False and view["revoked_revision"] is None
    stored = _raw(d)["data"]
    assert stored["policy_revision"] == revision + 1
    mapping = stored["mappings"][view["mapping_id"]]
    assert set(mapping) == MAPPING_RECORD_KEYS
    grant_record = stored["grants"][grant["grant_id"]]
    assert mapping["target_root_hex"] == grant_record["project_root_hex"]
    assert mapping["target_root_hex"] == str(root).encode("utf-8").hex()
    assert mapping["target_owner_scope"] == {
        "kind": "agent",
        "id_hex": b"alice".hex(),
    }
    assert auth.load_policy_readonly(data_root=d)["mappings"] == {
        view["mapping_id"]: view
    }
    after_approve = _sha(_policy_file(d))

    # an identical active mapping is returned unchanged, before the revision check
    for expected in (revision, revision + 1):
        again = auth.approve_capsule_mapping(
            capsule_origin=_origin(),
            project_root=root,
            expected_policy_revision=expected,
            consent=True,
            data_root=d,
        )
        assert again == view
    assert _sha(_policy_file(d)) == after_approve

    # a different origin is a new mapping and obeys the compare-and-set
    _expect(
        auth,
        "E_VERSION",
        f"expected revision {revision}, found {revision + 1}",
        auth.approve_capsule_mapping,
        capsule_origin=_origin("other-origin"),
        project_root=root,
        expected_policy_revision=revision,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_CONSENT",
        "consent_required",
        auth.approve_capsule_mapping,
        capsule_origin=_origin("other-origin"),
        project_root=root,
        expected_policy_revision=revision + 1,
        consent=False,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == after_approve
    second = _approve(auth, root, d, capsule_origin=_origin("other-origin"))
    assert second["mapping_id"] != view["mapping_id"]
    assert second["created_revision"] == revision + 2

    # --- revoke: unknown, stale, principal, success, repeat ---
    current = _revision(auth, d)
    _expect(
        auth,
        "E_INPUT",
        "mapping_id",
        auth.revoke_capsule_mapping,
        mapping_id="not-a-uuid",
        expected_policy_revision=current,
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_PERMISSION",
        "mapping_unknown",
        auth.revoke_capsule_mapping,
        mapping_id=str(uuid.uuid4()),
        expected_policy_revision=current,
        consent=True,
        data_root=d,
    )
    sha_before = _sha(_policy_file(d))
    real_principal = auth._current_os_principal
    monkeypatch.setattr(auth, "_current_os_principal", lambda: "uid:99999999")
    _expect(
        auth,
        "E_PRINCIPAL",
        "principal_mismatch",
        auth.revoke_capsule_mapping,
        mapping_id=view["mapping_id"],
        expected_policy_revision=current,
        consent=True,
        data_root=d,
    )
    monkeypatch.setattr(auth, "_current_os_principal", real_principal)
    _expect(
        auth,
        "E_VERSION",
        f"expected revision {current - 1}, found {current}",
        auth.revoke_capsule_mapping,
        mapping_id=view["mapping_id"],
        expected_policy_revision=current - 1,
        consent=True,
        data_root=d,
    )
    assert _sha(_policy_file(d)) == sha_before
    revoked = auth.revoke_capsule_mapping(
        mapping_id=view["mapping_id"],
        expected_policy_revision=current,
        consent=True,
        data_root=d,
    )
    assert set(revoked) == MAPPING_VIEW_KEYS
    assert revoked["revoked"] is True and revoked["revoked_revision"] == current + 1
    assert _revision(auth, d) == current + 1
    after_revoke = _sha(_policy_file(d))
    twice = auth.revoke_capsule_mapping(
        mapping_id=view["mapping_id"],
        expected_policy_revision=current + 1,
        consent=True,
        data_root=d,
    )
    assert twice == revoked and _sha(_policy_file(d)) == after_revoke

    # --- the loader validates every stored record (`_mapping_view`) ---
    base = _raw(d)
    good_id = second["mapping_id"]
    grant_ids = list(base["data"]["grants"])
    corruptions: dict[str, tuple[Any, str]] = {
        "missing_key": (lambda r: r.pop("purpose"), "record_invalid"),
        "extra_key": (lambda r: r.__setitem__("extra", 1), "record_invalid"),
        "wrong_purpose": (
            lambda r: r.__setitem__("purpose", "other"),
            "record_invalid",
        ),
        "id_mismatch": (
            lambda r: r.__setitem__("mapping_id", str(uuid.uuid4())),
            "record_invalid",
        ),
        "empty_origin_project": (
            lambda r: r.__setitem__("origin_project_id", ""),
            "record_invalid",
        ),
        "nul_origin_project": (
            lambda r: r.__setitem__("origin_project_id", "a\x00b"),
            "record_invalid",
        ),
        "int_origin_project": (
            lambda r: r.__setitem__("origin_project_id", 5),
            "record_invalid",
        ),
        "origin_worktree_not_hex": (
            lambda r: r.__setitem__("origin_worktree_id", "xyz"),
            "record_invalid",
        ),
        "target_worktree_uppercase": (
            lambda r: r.__setitem__(
                "target_worktree_id", r["target_worktree_id"].upper()
            ),
            "record_invalid",
        ),
        "target_root_odd_hex": (
            lambda r: r.__setitem__("target_root_hex", "abc"),
            "record_invalid",
        ),
        "target_root_not_hex": (
            lambda r: r.__setitem__("target_root_hex", "zz"),
            "record_invalid",
        ),
        "owner_not_dict": (
            lambda r: r.__setitem__("target_owner_scope", "alice"),
            "record_invalid",
        ),
        "owner_extra_key": (
            lambda r: r["target_owner_scope"].__setitem__("x", 1),
            "record_invalid",
        ),
        "owner_kind_unknown": (
            lambda r: r["target_owner_scope"].__setitem__("kind", "robot"),
            "record_invalid",
        ),
        "owner_id_odd_hex": (
            lambda r: r["target_owner_scope"].__setitem__("id_hex", "abc"),
            "record_invalid",
        ),
        "grant_id_not_uuid": (
            lambda r: r.__setitem__("grant_id", "g1"),
            "record_invalid",
        ),
        "purpose_list": (
            lambda r: r.__setitem__("purpose", ["capsule_import"]),
            "record_invalid",
        ),
        "purpose_dict": (
            lambda r: r.__setitem__("purpose", {"capsule_import": 1}),
            "record_invalid",
        ),
        "owner_kind_list": (
            lambda r: r["target_owner_scope"].__setitem__("kind", ["agent"]),
            "record_invalid",
        ),
        "owner_kind_dict": (
            lambda r: r["target_owner_scope"].__setitem__("kind", {"a": 1}),
            "record_invalid",
        ),
        "owner_id_hex_list": (
            lambda r: r["target_owner_scope"].__setitem__("id_hex", ["61"]),
            "record_invalid",
        ),
        "grant_id_list": (
            lambda r: r.__setitem__("grant_id", [r["grant_id"]]),
            "record_invalid",
        ),
        "grant_id_dict": (lambda r: r.__setitem__("grant_id", {}), "record_invalid"),
        "mapping_id_list": (
            lambda r: r.__setitem__("mapping_id", [r["mapping_id"]]),
            "record_invalid",
        ),
        "origin_project_list": (
            lambda r: r.__setitem__("origin_project_id", ["p"]),
            "record_invalid",
        ),
        "origin_worktree_dict": (
            lambda r: r.__setitem__("origin_worktree_id", {}),
            "record_invalid",
        ),
        "revoked_list": (lambda r: r.__setitem__("revoked", []), "record_invalid"),
        "revoked_revision_list": (
            lambda r: r.__setitem__("revoked_revision", []),
            "record_invalid",
        ),
        "target_root_invalid_utf8": (
            lambda r: r.__setitem__("target_root_hex", "eda080"),
            "record_invalid",
        ),
        "target_root_list": (
            lambda r: r.__setitem__("target_root_hex", ["61"]),
            "record_invalid",
        ),
        "grant_id_dangling": (
            lambda r: r.__setitem__("grant_id", str(uuid.uuid4())),
            "dangling_mapping",
        ),
        "created_revision_zero": (
            lambda r: r.__setitem__("created_revision", 0),
            "record_invalid",
        ),
        "created_revision_future": (
            lambda r: r.__setitem__("created_revision", 999),
            "record_invalid",
        ),
        "created_revision_bool": (
            lambda r: r.__setitem__("created_revision", True),
            "record_invalid",
        ),
        "created_revision_float": (
            lambda r: r.__setitem__("created_revision", 2.0),
            "record_invalid",
        ),
        "approved_at_bool": (
            lambda r: r.__setitem__("approved_at", True),
            "record_invalid",
        ),
        "approved_at_string": (
            lambda r: r.__setitem__("approved_at", "now"),
            "record_invalid",
        ),
        "revoked_not_bool": (lambda r: r.__setitem__("revoked", 0), "record_invalid"),
        "revoked_without_revision": (
            lambda r: r.__setitem__("revoked", True),
            "record_invalid",
        ),
        "active_with_revision": (
            lambda r: r.__setitem__("revoked_revision", 3),
            "record_invalid",
        ),
    }
    assert len(grant_ids) == 1
    for name, (mutate, reason) in corruptions.items():
        data = json.loads(json.dumps(base))
        mutate(data["data"]["mappings"][good_id])
        _write_raw(d, data)
        loaded = auth.load_policy_readonly(data_root=d)
        assert (loaded["state"], loaded["reason"]) == ("invalid", reason), name
        assert loaded["mappings"] == {}, name
        _assert_denied(
            _resolve(auth, root, d, "write", owner_scope=ALICE), "policy_invalid"
        )
    revoked_bad = json.loads(json.dumps(base))
    revoked_bad["data"]["mappings"][view["mapping_id"]]["revoked_revision"] = revoked[
        "created_revision"
    ]
    _write_raw(d, revoked_bad)
    loaded = auth.load_policy_readonly(data_root=d)
    assert (loaded["state"], loaded["reason"]) == ("invalid", "record_invalid")
    bad_key = json.loads(json.dumps(base))
    bad_key["data"]["mappings"]["not-a-uuid"] = bad_key["data"]["mappings"].pop(good_id)
    _write_raw(d, bad_key)
    assert auth.load_policy_readonly(data_root=d)["state"] == "invalid"


def test_capsule_mapping_forged_or_revoked_grant_rejected(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "dest", d)
    grant_alice = _grant(
        auth, root, ALICE, d, sources=("source-a",), ops=("ask", "write")
    )
    grant_bob = _grant(
        auth, root, BOB, d, sources=("source-a",), ops=("ask", "write"), expected=1
    )
    view = _approve(auth, root, d, owner_scope=ALICE)
    mapping_id = view["mapping_id"]
    sha_before = _sha(_policy_file(d))

    def resolve(**extra: Any) -> dict[str, Any]:
        params: dict[str, Any] = {
            "mapping_id": mapping_id,
            "origin_project_id": "origin-project",
            "origin_worktree_id": ORIGIN_WORKTREE,
            "project_root": root,
            "data_root": d,
        }
        params.update(extra)
        return auth.resolve_capsule_mapping(**params)

    ok = resolve()
    assert set(ok) == {"mapping", "grant_id", "policy_revision"}
    assert ok["mapping"] == view and ok["grant_id"] == grant_alice["grant_id"]
    assert ok["policy_revision"] == _revision(auth, d)
    assert _sha(_policy_file(d)) == sha_before, "resolve is read-only"

    # forged ids, origins and projects
    _expect(
        auth, "E_PERMISSION", "mapping_unknown", resolve, mapping_id=str(uuid.uuid4())
    )
    _expect(
        auth, "E_PERMISSION", "mapping_mismatch", resolve, origin_project_id="elsewhere"
    )
    _expect(
        auth,
        "E_PERMISSION",
        "mapping_mismatch",
        resolve,
        origin_worktree_id=hashlib.sha256(b"other").hexdigest(),
    )
    other_root, _ = _project(tmp_path, "other", d)
    _grant(
        auth,
        other_root,
        ALICE,
        d,
        sources=("source-a",),
        ops=("ask", "write"),
        expected=_revision(auth, d),
    )
    sha_before = _sha(_policy_file(d))
    _expect(auth, "E_PERMISSION", "mapping_mismatch", resolve, project_root=other_root)

    # a forged record naming another owner's grant for alice's owner scope
    forged = _raw(d)
    forged["data"]["mappings"][mapping_id]["grant_id"] = grant_bob["grant_id"]
    _write_raw(d, forged)
    _expect(auth, "E_PERMISSION", "mapping_mismatch", resolve)
    forged["data"]["mappings"][mapping_id]["grant_id"] = grant_alice["grant_id"]
    _write_raw(d, forged)
    assert resolve()["grant_id"] == grant_alice["grant_id"]

    # revoked underlying grant: the resolve reason decides
    auth.revoke_memory_scope(
        grant_id=grant_alice["grant_id"],
        expected_policy_revision=_revision(auth, d),
        consent=True,
        data_root=d,
    )
    denied = _resolve(auth, root, d, "write", owner_scope=ALICE)
    assert denied["access"] == "denied"
    _expect(auth, "E_PERMISSION", denied["reason"], resolve)
    sha_after_grant_revoke = _sha(_policy_file(d))

    # a revoked mapping
    auth2_view = _approve(auth, root, d, owner_scope=BOB, capsule_origin=_origin("o2"))
    auth.revoke_capsule_mapping(
        mapping_id=auth2_view["mapping_id"],
        expected_policy_revision=_revision(auth, d),
        consent=True,
        data_root=d,
    )
    _expect(
        auth,
        "E_PERMISSION",
        "mapping_revoked",
        resolve,
        mapping_id=auth2_view["mapping_id"],
        origin_project_id="o2",
    )
    assert sha_after_grant_revoke != _sha(_policy_file(d))

    # no policy / an invalid policy
    missing = tmp_path / "no-data-root"
    _expect(auth, "E_PERMISSION", "policy_missing", resolve, data_root=missing)
    _policy_file(d).write_bytes(b"{")
    invalid = auth.load_policy_readonly(data_root=d)
    assert invalid["state"] == "invalid"
    _expect(auth, "E_PERMISSION", invalid["reason"], resolve)


def test_capsule_mapping_unauthorized_worktree_remap_rejected(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    d = _data_root(tmp_path)
    granted, _r1 = _project(tmp_path, "granted", d)
    ask_only, _r2 = _project(tmp_path, "ask-only", d)
    ungranted, _r3 = _project(tmp_path, "ungranted", d)
    _grant(auth, granted, ALICE, d, sources=("source-a",), ops=("ask", "write"))
    _grant(
        auth,
        ask_only,
        ALICE,
        d,
        sources=("source-a",),
        ops=("ask", "list"),
        expected=_revision(auth, d),
    )
    unregistered = tmp_path / "unregistered"
    unregistered.mkdir()
    sha_before = _sha(_policy_file(d))
    before = _snapshot(tmp_path)

    for label, target in (
        ("no grant", ungranted),
        ("no write operation", ask_only),
        ("unregistered project", unregistered),
        ("missing directory", tmp_path / "gone"),
    ):
        resolved = auth.resolve_memory_scope(
            project_root=target, operation="write", data_root=d
        )
        assert resolved["access"] == "denied", label
        error = _expect(
            auth,
            "E_PERMISSION",
            resolved["reason"],
            auth.approve_capsule_mapping,
            capsule_origin=_origin(),
            project_root=target,
            expected_policy_revision=_revision(auth, d),
            consent=True,
            data_root=d,
        )
        assert error.code == "E_PERMISSION"
    assert _sha(_policy_file(d)) == sha_before
    assert _snapshot(tmp_path) == before, "a refused mapping writes nothing"

    # a mapping approved for one worktree never authorizes another
    view = _approve(auth, granted, d)
    other_granted, _r4 = _project(tmp_path, "second-granted", d)
    _grant(
        auth,
        other_granted,
        ALICE,
        d,
        sources=("source-a",),
        ops=("ask", "write"),
        expected=_revision(auth, d),
    )
    _expect(
        auth,
        "E_PERMISSION",
        "mapping_mismatch",
        auth.resolve_capsule_mapping,
        mapping_id=view["mapping_id"],
        origin_project_id="origin-project",
        origin_worktree_id=ORIGIN_WORKTREE,
        project_root=other_granted,
        data_root=d,
    )


def test_capsule_mapping_two_write_owners_no_inference(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    # two write-owner grants: an omitted owner is never inferred
    d = _data_root(tmp_path)
    root, _record = _project(tmp_path, "dest", d)
    grant_a = _grant(auth, root, ALICE, d, sources=("source-a",), ops=("ask", "write"))
    grant_b = _grant(
        auth, root, BOB, d, sources=("source-a",), ops=("ask", "write"), expected=1
    )
    sha_before = _sha(_policy_file(d))
    error = _expect(
        auth,
        "E_INPUT",
        "owner_required",
        auth.approve_capsule_mapping,
        capsule_origin=_origin(),
        project_root=root,
        owner_scope=None,
        expected_policy_revision=_revision(auth, d),
        consent=True,
        data_root=d,
    )
    assert error.code == "E_INPUT"
    assert _sha(_policy_file(d)) == sha_before
    chosen = _approve(auth, root, d, owner_scope=BOB)
    assert chosen["target_owner_scope"] == {"kind": "agent", "id": "bob"}
    assert chosen["grant_id"] == grant_b["grant_id"] != grant_a["grant_id"]

    # one write-owner grant plus one ask-only owner grant: still no inference
    d2 = tmp_path / "second-data"
    root2, _record2 = _project(tmp_path, "dest2", d2)
    writer = _grant(auth, root2, ALICE, d2, sources=("source-a",), ops=("ask", "write"))
    _grant(auth, root2, BOB, d2, sources=("source-a",), ops=("ask",), expected=1)
    sha_two = _sha(_policy_file(d2))
    _expect(
        auth,
        "E_INPUT",
        "owner_required",
        auth.approve_capsule_mapping,
        capsule_origin=_origin(),
        project_root=root2,
        expected_policy_revision=_revision(auth, d2),
        consent=True,
        data_root=d2,
    )
    assert _sha(_policy_file(d2)) == sha_two
    _expect(
        auth,
        "E_PERMISSION",
        "operation_not_granted",
        auth.approve_capsule_mapping,
        capsule_origin=_origin(),
        project_root=root2,
        owner_scope=BOB,
        expected_policy_revision=_revision(auth, d2),
        consent=True,
        data_root=d2,
    )
    explicit = _approve(auth, root2, d2, owner_scope=ALICE)
    assert explicit["grant_id"] == writer["grant_id"]
    assert explicit["target_owner_scope"] == {"kind": "agent", "id": "alice"}
    # an explicit ungranted owner is E_OWNER
    _expect(
        auth,
        "E_OWNER",
        "owner_not_granted",
        auth.approve_capsule_mapping,
        capsule_origin=_origin("p3"),
        project_root=root2,
        owner_scope=OwnerScope("agent", "mallory"),
        expected_policy_revision=_revision(auth, d2),
        consent=True,
        data_root=d2,
    )


def test_capsule_mapping_owner_change_requires_new_approval(tmp_path: Path) -> None:
    auth, d, root, grant = _mapped(tmp_path)
    view = _approve(auth, root, d, owner_scope=ALICE)

    def resolve() -> dict[str, Any]:
        return auth.resolve_capsule_mapping(
            mapping_id=view["mapping_id"],
            origin_project_id="origin-project",
            origin_worktree_id=ORIGIN_WORKTREE,
            project_root=root,
            data_root=d,
        )

    assert resolve()["grant_id"] == grant["grant_id"]
    # superseding the mapped owner's grant changes its id: the mapping no longer holds
    newer = _grant(
        auth,
        root,
        ALICE,
        d,
        sources=("source-a", "source-b"),
        ops=("ask", "write"),
        expected=_revision(auth, d),
    )
    assert newer["grant_id"] != grant["grant_id"]
    sha_before = _sha(_policy_file(d))
    _expect(auth, "E_PERMISSION", "mapping_mismatch", resolve)
    assert _sha(_policy_file(d)) == sha_before, "refusing writes nothing"
    # a new approval is a new mapping bound to the new grant
    renewed = _approve(auth, root, d, owner_scope=ALICE)
    assert renewed["mapping_id"] != view["mapping_id"]
    assert renewed["grant_id"] == newer["grant_id"]
    assert (
        auth.resolve_capsule_mapping(
            mapping_id=renewed["mapping_id"],
            origin_project_id="origin-project",
            origin_worktree_id=ORIGIN_WORKTREE,
            project_root=root,
            data_root=d,
        )["grant_id"]
        == newer["grant_id"]
    )
    # the superseded mapping stays refused
    _expect(auth, "E_PERMISSION", "mapping_mismatch", resolve)


# --- 73-T02/BOOTSTRAP-CONSENT: grant, revoke and bind-store CLI -----------------------
#
# Every command below runs through the public Click CLI against the per-test HOME's
# default data root (conftest `_isolated_home`); symbols an earlier task adds are
# imported inside the test body.

CONSENT_DEFAULT_OPS = ["ask", "bootstrap", "expand", "history", "list", "write"]
OVERLAY_SOURCE = "personal-preferences"
_EXIT_FOR_STATUS = {"ok": 0, "skipped": 0, "warn": 1, "fail": 1, "error": 2}
SKIPPED_NO_CACHE_WRITE = {"permission": "cache_write", "flag": "--allow-cache-write"}


def _c_data_root() -> Path:
    from rush.setup.provision import default_data_root

    return default_data_root()


def _c_project(tmp_path: Path, name: str = "project") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    register_project(root, data_root=_c_data_root())
    return root.resolve()


def _c_project_id(root: Path) -> str:
    return str(register_project(root, data_root=_c_data_root()).project_id)


def _c_write_rows(root: Path, rows: list[tuple[str, str, Any]]) -> Any:
    """Write DERIVED rows `(id, source, owner or None)` through the store."""
    from rush.memory.store import MemoryArtifact, TypedArtifactStore

    store = TypedArtifactStore(root)
    for artifact_id, source, owner in rows:
        store.write(
            MemoryArtifact(
                id=artifact_id,
                family="memory",
                subject="domain_knowledge",
                trust_tier="DERIVED",
                content={"text": f"needle {artifact_id}"},
                source=source,
                created_at=time.time(),
                owner_scope=owner,
            )
        )
    return store


def _c_unbound_stated(
    store_root: Path, row_id: str, source: str, owner: Any = None, **extra: Any
) -> Path:
    """A store at `store_root` whose binding row was deleted by SQL and whose row
    `row_id` is STATED (a promotion the writer cannot do directly)."""
    from rush.memory.store import compute_content_signature

    store = _c_write_rows(store_root, [(row_id, source, owner)])
    db = Path(store.db_path)
    with contextlib.closing(sqlite3.connect(db)) as conn:
        content = json.loads(
            conn.execute(
                "SELECT content FROM memory_artifacts WHERE id = ?", (row_id,)
            ).fetchone()[0]
        )
        conn.execute(
            "UPDATE memory_artifacts SET trust_tier = 'STATED', signature = ? "
            "WHERE id = ?",
            (compute_content_signature(content), row_id),
        )
        conn.execute("DELETE FROM memory_store_binding")
        conn.commit()
    return db


def _c_binding(store_root: Path) -> str:
    from rush.memory.store import store_binding

    with contextlib.closing(
        sqlite3.connect(store_root / ".rush" / "memory.db")
    ) as conn:
        return str(store_binding(conn, store_root))


def _c_groups(store_root: Path) -> list[tuple[Any, Any, str, int]]:
    db = store_root / ".rush" / "memory.db"
    if not db.exists():
        return []
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return [
            (r[0], r[1], r[2], int(r[3]))
            for r in conn.execute(
                "SELECT owner_scope_kind, owner_scope_id, source, COUNT(*) "
                "FROM memory_artifacts WHERE archived_at IS NULL "
                "GROUP BY 1, 2, 3 ORDER BY 1, 2, 3"
            )
        ]


def _c_owner_dict(kind: Any, ident: Any) -> dict[str, Any] | None:
    return None if kind is None and ident is None else {"kind": kind, "id": ident}


def _c_expected_inventory(root: Path) -> dict[str, Any]:
    """A2.3 / A2.4 computed from the stored rows, independently of the CLI."""
    import rush.memory.authorization as auth

    groups = _c_groups(root)
    catalog_items = auth.writer_source_catalog(root)
    catalog = [
        {
            "source": item,
            "rows": sum(n for _k, _i, s, n in groups if auth.source_granted(s, [item])),
        }
        for item in catalog_items
    ]
    others = [
        {"owner_scope": _c_owner_dict(k, i), "source": s, "rows": n}
        for k, i, s, n in groups
        if not any(auth.source_granted(s, [item]) for item in catalog_items)
    ]
    owners: list[dict[str, Any]] = []
    seen: dict[tuple[Any, Any], int] = {}
    for k, i, _s, n in groups:
        if (k, i) not in seen:
            seen[(k, i)] = len(owners)
            owners.append({"owner_scope": _c_owner_dict(k, i), "rows": 0})
        owners[seen[(k, i)]]["rows"] += n
    return {"catalog": catalog, "other_sources": others, "owners": owners}


def _c_render(argv: list[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(argv)
    return shlex.join(argv)


def _c_argv_of(command: str, argv: list[str]) -> list[str]:
    """The argv a printed command stands for; each OS's rendering invariant holds."""
    if os.name == "nt":
        assert subprocess.list2cmdline(argv) == command
        return list(argv)
    parsed = shlex.split(command)
    assert parsed == argv
    return parsed


def _c_grant_argv(
    root: Path,
    ops: list[str],
    sources: list[str],
    *,
    owner: list[str] | None = None,
    expires: float | None = None,
    revision: int,
) -> list[str]:
    argv = ["rush", "memory", "grant", "--project", str(root), *(owner or [])]
    for op in sorted(ops):
        argv += ["--operation", op]
    for source in sorted(sources):
        argv += ["--source", source]
    if expires is not None:
        argv += ["--expires-at", repr(expires)]
    return [
        *argv,
        "--expected-policy-revision",
        str(revision),
        "--approve",
        "--allow-cache-write",
    ]


def _c_cli(*args: str) -> tuple[int, Any, str]:
    from click.testing import CliRunner

    from rush.cli import cli

    result = CliRunner().invoke(cli, list(args), catch_exceptions=False)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        payload = None
    return result.exit_code, payload, result.output


def _c_run(args: list[str], *, code: str) -> dict[str, Any]:
    """Run one consent command with `--json`; pin tool, envelope, code, status and
    the exit code the status maps to."""
    from rush.tools.memory import _CODE_STATUS

    exit_code, payload, output = _c_cli(*args, "--json")
    assert payload is not None, output
    assert payload["tool"] == "memory", payload
    raw = payload["raw"]
    assert raw["schema_version"] == 1, raw
    assert raw["code"] == code, (code, raw)
    status = _CODE_STATUS.get(code, "error")
    assert payload["status"] == status, payload
    assert exit_code == _EXIT_FOR_STATUS[status], (exit_code, payload)
    return payload


def _c_skipped(args: list[str], operation: str) -> dict[str, Any]:
    exit_code, payload, output = _c_cli(*args, "--json")
    assert payload is not None, output
    assert exit_code == 0, output
    assert payload["tool"] == "memory"
    assert payload["status"] == "skipped", payload
    assert payload["raw"] == {
        "schema_version": 1,
        "operation": operation,
        "skipped": SKIPPED_NO_CACHE_WRITE,
    }, payload["raw"]
    return payload


def _c_usage(args: list[str], message: str) -> None:
    exit_code, payload, output = _c_cli(*args)
    assert exit_code == 2, (args, output)
    assert payload is None
    assert message in output, (message, output)


def _c_state(*bases: Path) -> list[tuple[str, ...]]:
    """Zero-write evidence: every entry under HOME (the per-test data root included)
    and under each given base."""
    return _snapshot(Path(os.environ["HOME"]), *bases)


def _c_policy_bytes() -> bytes | None:
    import rush.memory.authorization as auth

    path = auth.policy_path(data_root=_c_data_root())
    return path.read_bytes() if path.exists() else None


@contextlib.contextmanager
def _c_forged_principal(grant_id: str, principal: str = "uid:99999") -> Iterator[None]:
    """The stored grant belongs to another OS principal (the policy file itself stays
    valid and owned by the current one); the original bytes come back on exit."""
    import rush.memory.authorization as auth

    path = auth.policy_path(data_root=_c_data_root())
    original = path.read_bytes()
    payload = json.loads(original.decode("utf-8"))
    payload["data"]["grants"][grant_id]["principal"] = principal
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        yield
    finally:
        path.write_bytes(original)


def _c_policy() -> dict[str, Any]:
    import rush.memory.authorization as auth

    return auth.load_policy_readonly(data_root=_c_data_root())


def _c_forbid_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """G3: a preview or a refusal never constructs a writable store, a telemetry or
    preference store, never takes the policy lock and never opens a CAS write."""
    import rush.memory.authorization as auth
    from rush.memory.preference_store import PreferenceStore
    from rush.memory.store import TypedArtifactStore
    from rush.token_economy.telemetry import TelemetryStore

    def forbid(name: str) -> Any:
        def refuse(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError(f"{name} constructed before admission")

        return refuse

    monkeypatch.setattr(TypedArtifactStore, "__init__", forbid("TypedArtifactStore"))
    monkeypatch.setattr(PreferenceStore, "__init__", forbid("PreferenceStore"))
    monkeypatch.setattr(TelemetryStore, "__init__", forbid("TelemetryStore"))
    monkeypatch.setattr(auth, "hold_policy_lock", forbid("hold_policy_lock"))
    monkeypatch.setattr(auth, "CASMapTransaction", forbid("CASMapTransaction"))


@contextlib.contextmanager
def _c_no_effects(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`_c_forbid_effects` for the extent of one `with` block only."""
    with monkeypatch.context() as scoped:
        _c_forbid_effects(scoped)
        yield


def _c_old_schema(store_root: Path) -> Path:
    db = Path(_c_write_rows(store_root, [("old-1", "src-old", None)]).db_path)
    with contextlib.closing(sqlite3.connect(db)) as conn:
        for table in ("memory_artifacts", "memory_artifact_versions"):
            for column in ("payload_hash", "payload_hash_origin"):
                conn.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        conn.commit()
    return db


def _c_readonly_state(
    monkeypatch: pytest.MonkeyPatch, state: str, only: Path | None = None
) -> None:
    """Make `open_readonly_view` report `state` (for `only`, else for every root)."""
    from rush.memory.store import TypedArtifactStore

    real = TypedArtifactStore.open_readonly_view

    def fake(cls: Any, project_root: Path) -> Any:
        if only is None or Path(project_root).resolve() == only.resolve():
            return None, state
        return real(project_root)

    monkeypatch.setattr(TypedArtifactStore, "open_readonly_view", classmethod(fake))


PREVIEW_KEYS = {
    "project_root",
    "project_id",
    "owner_scope",
    "overlay",
    "operations",
    "sources",
    "all_current_sources",
    "expires_at",
    "expected_policy_revision",
    "policy_revision",
    "policy_state",
    "catalog",
    "other_sources",
    "owners",
    "store_binding",
    "stated_rows",
    "approve_command",
    "approve_command_refused",
}


def _c_preview_scenario_rich(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A2.1-A2.4, A2.9, A2.11, A2.13: a bound store with every kind of group."""
    from rush.memory.store import OwnerScope, legacy_owner_scope

    root = _c_project(tmp_path)
    alice = OwnerScope("user", "alice")
    store = _c_write_rows(
        root,
        [
            ("k1", "src-a", None),
            ("k2", "src-a", None),
            ("k3", "checkpoint_journal:save_checkpoint", None),
            ("k4", "intent:abc", None),
            ("k5", "src-b", alice),
            ("k6", "src-gone", alice),
        ],
    )
    store.archive(
        "k6",
        expected_version=1,
        scope="domain_knowledge",
        owner_scope=alice,
        apply=True,
    )
    pid = _c_project_id(root)
    expected = _c_expected_inventory(root)
    assert {c["source"] for c in expected["catalog"]} >= {
        "checkpoint_journal:save_checkpoint",
        "intent:*",
        str(root),
    }
    assert sum(c["rows"] for c in expected["catalog"]) == 2
    assert [o["source"] for o in expected["other_sources"]] == ["src-a", "src-b"]
    before = _c_state(root)
    _c_forbid_effects(monkeypatch)

    payload = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--source",
            "src-a",
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )
    after = _c_state(root)
    data = payload["raw"]["data"]
    assert set(data) == PREVIEW_KEYS
    assert data["project_root"] == str(root)
    assert data["project_id"] == pid
    assert data["owner_scope"] == legacy_owner_scope(root).as_dict()
    assert data["overlay"] is False
    assert data["operations"] == CONSENT_DEFAULT_OPS
    assert data["sources"] == ["src-a"]
    assert data["all_current_sources"] is False
    assert data["expires_at"] is None
    assert data["expected_policy_revision"] == 0
    assert data["policy_revision"] == 0
    assert data["policy_state"] == "missing"
    assert data["catalog"] == expected["catalog"]
    assert data["other_sources"] == expected["other_sources"]
    assert data["owners"] == expected["owners"]
    assert data["store_binding"] == "bound"
    assert data["stated_rows"] == 0
    argv = _c_grant_argv(root, CONSENT_DEFAULT_OPS, ["src-a"], revision=0)
    assert data["approve_command"] == _c_render(argv)
    _c_argv_of(data["approve_command"], argv)
    assert data["approve_command_refused"] is None
    assert "next_action" not in payload["raw"]
    assert after == before
    assert _c_policy_bytes() is None
    assert not (root / ".rush" / "memory-policy.required").exists()


def _c_preview_scenario_nothing_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2.1, A2.5: neither the data root, the project's `.rush` nor a lock appears."""
    root = tmp_path / "unregistered"
    root.mkdir()
    root = root.resolve()
    data_root = _c_data_root()
    assert not data_root.exists() and not (root / ".rush").exists()
    _c_forbid_effects(monkeypatch)

    payload = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--owner",
            "user:alice",
            "--source",
            "src-a",
            "--operation",
            "ask",
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )
    data = payload["raw"]["data"]
    assert set(data) == PREVIEW_KEYS
    assert data["project_id"] is None
    assert data["owner_scope"] == {"kind": "user", "id": "alice"}
    assert data["operations"] == ["ask"]
    assert data["policy_state"] == "missing"
    assert data["store_binding"] is None
    assert data["stated_rows"] == 0
    assert data["other_sources"] == []
    assert data["owners"] == []
    assert all(c["rows"] == 0 for c in data["catalog"])
    assert [c["source"] for c in data["catalog"]] == _catalog_of(root)
    argv = _c_grant_argv(
        root, ["ask"], ["src-a"], owner=["--owner", "user:alice"], revision=0
    )
    assert data["approve_command"] == _c_render(argv)
    assert not data_root.exists()
    assert not (root / ".rush").exists()
    assert list(root.iterdir()) == []


def _catalog_of(root: Path) -> list[str]:
    import rush.memory.authorization as auth

    return auth.writer_source_catalog(root)


def _c_preview_scenario_absent_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _c_project(tmp_path)
    before = _c_state(root)
    _c_forbid_effects(monkeypatch)
    payload = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--source",
            "src-a",
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )
    data = payload["raw"]["data"]
    assert data["store_binding"] is None
    assert data["stated_rows"] == 0
    assert data["other_sources"] == []
    assert data["owners"] == []
    assert data["catalog"] == [{"source": s, "rows": 0} for s in _catalog_of(root)]
    assert not (root / ".rush" / "memory.db").exists()
    assert _c_state(root) == before


def _c_preview_scenario_old_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2.6: migration_required is `E_MIGRATION` with the upgrade next action."""
    from rush.memory.store import readonly_view_reason

    root = _c_project(tmp_path)
    db = _c_old_schema(root)
    before = (hashlib.sha256(db.read_bytes()).hexdigest(), _c_state(root))
    reason = readonly_view_reason("migration_required")
    payload = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--source",
            "src-old",
            "--expected-policy-revision",
            "0",
        ],
        code="E_MIGRATION",
    )
    assert payload["raw"]["data"] == {
        "reason": "store_migration_required",
        "message": reason,
    }
    assert payload["raw"]["next_action"] == {"text": reason, "command": None}
    assert (hashlib.sha256(db.read_bytes()).hexdigest(), _c_state(root)) == before


def _c_preview_scenario_unreadable_store(
    state: str, code: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.store import readonly_view_reason

    root = _c_project(tmp_path)
    _c_write_rows(root, [("r1", "src-a", None)])
    before = _c_state(root)
    _c_readonly_state(monkeypatch, state)
    payload = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--source",
            "src-a",
            "--expected-policy-revision",
            "0",
        ],
        code=code,
    )
    assert payload["raw"]["data"] == {
        "reason": f"store_{state}",
        "message": readonly_view_reason(state),
    }
    assert _c_state(root) == before


def _c_preview_scenario_overlay_store_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2.6 for the overlay store: reason `overlay_store_<state>`."""
    from rush.memory.store import readonly_view_reason

    root = _c_project(tmp_path)
    _c_write_rows(root, [("r1", "src-a", None)])
    overlay_root = _c_data_root() / "user"
    db = _c_old_schema(overlay_root)
    before = _c_state(root)
    payload = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--overlay",
            "--source",
            OVERLAY_SOURCE,
            "--expected-policy-revision",
            "0",
        ],
        code="E_MIGRATION",
    )
    assert payload["raw"]["data"] == {
        "reason": "overlay_store_migration_required",
        "message": readonly_view_reason("migration_required"),
    }
    assert db.exists() and _c_state(root) == before
    for state, code in (("corrupt", "E_STORE_CORRUPT"), ("busy", "E_STORE_BUSY")):
        _c_readonly_state(monkeypatch, state, only=overlay_root)
        payload = _c_run(
            [
                "memory",
                "grant",
                "--project",
                str(root),
                "--overlay",
                "--source",
                OVERLAY_SOURCE,
                "--expected-policy-revision",
                "0",
            ],
            code=code,
        )
        assert payload["raw"]["data"] == {
            "reason": f"overlay_store_{state}",
            "message": readonly_view_reason(state),
        }
        assert _c_state(root) == before


def _c_preview_scenario_policy_states(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2.7: invalid and unavailable policy are `E_POLICY_INVALID`, zero writes."""
    import rush.memory.authorization as auth

    root = _c_project(tmp_path)
    _c_write_rows(root, [("r1", "src-a", None)])
    args = [
        "memory",
        "grant",
        "--project",
        str(root),
        "--source",
        "src-a",
        "--expected-policy-revision",
        "0",
    ]
    policy = auth.policy_path(data_root=_c_data_root())
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy.write_bytes(b"{")
    loaded = _c_policy()
    assert loaded["state"] == "invalid"
    before = _c_state(root)
    payload = _c_run(args, code="E_POLICY_INVALID")
    assert payload["raw"]["data"]["reason"] == loaded["reason"]
    assert _c_state(root) == before

    policy.unlink()
    data_root = _c_data_root()
    shutil.rmtree(data_root)
    data_root.write_text("a file where the data root belongs", encoding="utf-8")
    loaded = _c_policy()
    assert loaded["state"] in ("invalid", "unavailable")
    before = _c_state(root)
    payload = _c_run(args, code="E_POLICY_INVALID")
    assert payload["raw"]["data"]["reason"] == loaded["reason"]
    assert _c_state(root) == before
    assert data_root.is_file()


_VALIDATOR_CASES = [
    pytest.param(["--source", ""], "approved_sources", id="source-empty"),
    pytest.param(["--source", " padded "], "approved_sources", id="source-padded"),
    pytest.param(
        ["--source", "dup", "--source", "dup"], "approved_sources", id="source-dup"
    ),
    pytest.param(["--source", "*"], "approved_sources", id="source-star"),
    pytest.param(["--source", "bogus:*"], "approved_sources", id="source-bad-family"),
    pytest.param(
        ["--source", "a\ud800"], "approved_sources", id="source-lone-surrogate"
    ),
    pytest.param(
        ["--source", "src", "--operation", "ask", "--operation", "ask"],
        "allowed_operations",
        id="operation-duplicate",
    ),
    pytest.param(
        ["--source", "src", "--expires-at", "1"], "expires_at", id="expires-past"
    ),
    pytest.param(
        ["--source", "src", "--expires-at", "nan"], "expires_at", id="expires-nan"
    ),
    pytest.param(
        ["--source", "src", "--expires-at", "inf"], "expires_at", id="expires-inf"
    ),
    pytest.param(
        ["--source", "src", "--expires-at", "1e400"], "expires_at", id="expires-huge"
    ),
    pytest.param(
        ["--source", "src", "--owner", "user:alice", "--operation", "overlay_read"],
        "overlay_read_requires_overlay_owner",
        id="overlay_read-on-project-owner",
    ),
    pytest.param(
        ["--source", "src", "--owner", "user:x\ud800y"],
        "owner_scope",
        id="owner-lone-surrogate",
    ),
    pytest.param(
        [
            "--source",
            "",
            "--operation",
            "ask",
            "--operation",
            "ask",
            "--expires-at",
            "1",
        ],
        "approved_sources",
        id="order-sources-first",
    ),
    pytest.param(
        ["--source", "src", "--operation", "ask", "--operation", "ask"]
        + ["--expires-at", "1"],
        "allowed_operations",
        id="order-operations-before-expiry",
    ),
    pytest.param(
        ["--source", "src", "--owner", "user:alice", "--operation", "overlay_read"]
        + ["--expires-at", "1"],
        "expires_at",
        id="order-expiry-before-overlay-owner",
    ),
]


def _c_preview_scenario_validators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A2.8: the writer's pure validators run in the writer's order; the preview
    fails with the writer's code and reason, before the inventory is read."""
    root = _c_project(tmp_path)
    _c_write_rows(root, [("r1", "src-a", None)])
    before = _c_state(root)
    _c_forbid_effects(monkeypatch)
    for param in _VALIDATOR_CASES:
        extra, reason = cast("tuple[list[str], str]", param.values)
        payload = _c_run(
            ["memory", "grant", "--project", str(root), *extra]
            + ["--expected-policy-revision", "0"],
            code="E_INPUT",
        )
        assert payload["raw"]["data"] == {
            "reason": reason,
            "message": f"E_INPUT: {reason}",
        }, param.id
        assert _c_state(root) == before, param.id


def _c_preview_scenario_corrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _c_preview_scenario_unreadable_store(
        "corrupt", "E_STORE_CORRUPT", tmp_path, monkeypatch
    )


def _c_preview_scenario_busy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _c_preview_scenario_unreadable_store("busy", "E_STORE_BUSY", tmp_path, monkeypatch)


_PREVIEW_SCENARIOS = {
    "corrupt": _c_preview_scenario_corrupt,
    "busy": _c_preview_scenario_busy,
    "rich": _c_preview_scenario_rich,
    "nothing_exists": _c_preview_scenario_nothing_exists,
    "absent_store": _c_preview_scenario_absent_store,
    "old_schema": _c_preview_scenario_old_schema,
    "overlay_store_states": _c_preview_scenario_overlay_store_states,
    "policy_states": _c_preview_scenario_policy_states,
    "validators": _c_preview_scenario_validators,
}


@pytest.mark.parametrize("scenario", sorted(_PREVIEW_SCENARIOS))
def test_consent_grant_preview_no_write(
    scenario: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _PREVIEW_SCENARIOS[scenario](tmp_path, monkeypatch)


def _c_grant_args(root: Path, revision: int, *extra: str) -> list[str]:
    return [
        "memory",
        "grant",
        "--project",
        str(root),
        *extra,
        "--expected-policy-revision",
        str(revision),
        "--approve",
        "--allow-cache-write",
    ]


def test_consent_grant_apply_cas_and_stale_revision(tmp_path: Path) -> None:
    import rush.memory.authorization as auth
    from rush.memory.store import legacy_owner_scope

    root = _c_project(tmp_path)
    first_args = _c_grant_args(
        root,
        0,
        "--source",
        "s1",
        "--operation",
        "ask",
        "--operation",
        "list",
        "--expires-at",
        "1893456000.5",
    )
    payload = _c_run(first_args, code="OK")
    data = payload["raw"]["data"]
    assert set(data) == GRANT_RESULT_KEYS
    grant_id = data["grant_id"]
    view = _c_policy()["grants"][grant_id]
    assert view["expires_at"] == 1893456000.5  # PR9: stored unchanged
    assert data == {
        "grant_id": grant_id,
        "policy_revision": 1,
        "project_id": _c_project_id(root),
        "worktree_id": view["worktree_id"],
        "owner_scope": legacy_owner_scope(root).as_dict(),
        "approved_sources": ["s1"],
        "allowed_operations": ["ask", "list"],
    }
    assert (root / ".rush" / "memory-policy.required").exists()
    after_first = _c_policy_bytes()

    # A3.3: a stale N on a changed grant is E_VERSION and writes nothing.
    before = _c_state(root)
    payload = _c_run(
        _c_grant_args(root, 0, "--source", "s2", "--operation", "ask"),
        code="E_VERSION",
    )
    assert payload["raw"]["data"]["reason"] == "expected revision 0, found 1"
    assert _c_policy_bytes() == after_first
    assert _c_state(root) == before

    # A3.4: a stale N repeating the identical active grant returns it, no write.
    payload = _c_run(first_args, code="OK")
    assert payload["raw"]["data"] == data
    assert _c_policy_bytes() == after_first
    assert _c_state(root) == before

    # The current N on a changed grant supersedes the active one.
    payload = _c_run(
        _c_grant_args(root, 1, "--source", "s2", "--operation", "ask"), code="OK"
    )
    second = payload["raw"]["data"]
    assert second["policy_revision"] == 2
    assert second["grant_id"] != grant_id
    assert second["approved_sources"] == ["s2"]
    loaded = _c_policy()
    assert loaded["grants"][grant_id]["revoked"] is True
    assert loaded["grants"][grant_id]["superseded_by"] == second["grant_id"]
    assert loaded["policy_revision"] == 2

    # A3.5: any other MemoryPolicyError is its own code and reason; an unregistered
    # root also carries the registration next action (both permissions, PR10).
    unregistered = tmp_path / "unregistered"
    unregistered.mkdir()
    unregistered = unregistered.resolve()
    before = _c_state(unregistered)
    payload = _c_run(
        _c_grant_args(unregistered, 2, "--source", "s1"),
        code="E_PROJECT_NOT_REGISTERED",
    )
    assert payload["raw"]["data"]["reason"] == "project_not_registered"
    expected_next = auth.memory_next_action(
        reason="project_not_registered",
        project_root=unregistered,
        operations=CONSENT_DEFAULT_OPS,
    )
    assert payload["raw"]["next_action"] == expected_next
    assert expected_next["command"] == _c_render(
        [
            "rush",
            "project",
            "add",
            str(unregistered),
            "--allow-cache-write",
            "--allow-artifact-write",
        ]
    )
    assert _c_state(unregistered) == before

    policy = auth.policy_path(data_root=_c_data_root())
    policy.write_bytes(b"{")
    invalid = _c_policy()
    assert invalid["state"] == "invalid"
    payload = _c_run(_c_grant_args(root, 2, "--source", "s1"), code="E_POLICY_INVALID")
    assert payload["raw"]["data"]["reason"] == invalid["reason"]
    assert policy.read_bytes() == b"{"


def _c_bound_grant(
    tmp_path: Path, bindings: tuple[tuple[str, str], ...] = ()
) -> tuple[Path, str]:
    import rush.memory.authorization as auth
    from rush.memory.store import legacy_owner_scope

    root = _c_project(tmp_path)
    data_root = _c_data_root()
    granted = _grant(
        auth,
        root,
        legacy_owner_scope(root),
        data_root,
        sources=("s1",),
        ops=("ask", "list"),
        expected=int(_c_policy()["policy_revision"]),
    )
    for session_id, host_id in bindings:
        _bind(
            auth,
            granted["grant_id"],
            data_root,
            expected=int(_c_policy()["policy_revision"]),
            session_id=session_id,
            host_id=host_id,
        )
    return root, granted["grant_id"]


def test_consent_revoke_preview_and_apply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth

    # A4.2: no policy at all is "grant not found"; an empty ID is the writer's own
    # input error and is decided before the policy is read.
    root = _c_project(tmp_path)
    ghost = str(uuid.uuid4())
    before = _c_state(root)
    payload = _c_run(
        ["memory", "revoke", "--grant-id", ghost, "--expected-policy-revision", "0"],
        code="E_GRANT_NOT_FOUND",
    )
    assert payload["raw"]["data"]["reason"] == ghost
    payload = _c_run(
        ["memory", "revoke", "--grant-id", "", "--expected-policy-revision", "0"],
        code="E_INPUT",
    )
    assert payload["raw"]["data"]["reason"] == "grant_id"
    assert _c_state(root) == before

    root, grant_id = _c_bound_grant(
        tmp_path / "bound", (("session-b", "host-b"), ("session-a", "host-a"))
    )
    loaded = _c_policy()
    current = int(loaded["policy_revision"])
    bindings = sorted(
        (b for b in loaded["bindings"].values() if b["grant_id"] == grant_id),
        key=lambda b: b["binding_id"],
    )
    assert len(bindings) == 2

    # A4.1: the preview shows the grant, its bindings and the current revision; no
    # writable store, telemetry or preference store, lock or CAS write is reached (G3).
    before = _c_state(root)
    sealed = _c_policy_bytes()
    with _c_no_effects(monkeypatch):
        payload = _c_run(
            [
                "memory",
                "revoke",
                "--grant-id",
                grant_id,
                "--expected-policy-revision",
                "0",
            ],
            code="OK",
        )
    argv = [
        "rush",
        "memory",
        "revoke",
        "--grant-id",
        grant_id,
        "--expected-policy-revision",
        str(current),
        "--approve",
        "--allow-cache-write",
    ]
    assert payload["raw"]["data"] == {
        "grant": loaded["grants"][grant_id],
        "bindings": bindings,
        "policy_revision": current,
        "expected_policy_revision": 0,
        "approve_command": _c_render(argv),
    }
    _c_argv_of(payload["raw"]["data"]["approve_command"], argv)
    assert _c_policy_bytes() == sealed
    assert _c_state(root) == before

    # A4.2: a grant of another OS principal is neither previewable nor revocable.
    with _c_forged_principal(grant_id):
        forged = _c_policy_bytes()
        payload = _c_run(
            [
                "memory",
                "revoke",
                "--grant-id",
                grant_id,
                "--expected-policy-revision",
                str(current),
            ],
            code="E_PRINCIPAL",
        )
        assert payload["raw"]["data"]["reason"] == "principal_mismatch"
        _c_run(
            [
                "memory",
                "revoke",
                "--grant-id",
                grant_id,
                "--expected-policy-revision",
                str(current),
                "--approve",
                "--allow-cache-write",
            ],
            code="E_PRINCIPAL",
        )
        assert _c_policy_bytes() == forged
    assert _c_policy_bytes() == sealed

    # A4.4: a stale N on an active grant is E_VERSION with the bytes unchanged.
    payload = _c_run(
        [
            "memory",
            "revoke",
            "--grant-id",
            grant_id,
            "--expected-policy-revision",
            str(current + 1),
            "--approve",
            "--allow-cache-write",
        ],
        code="E_VERSION",
    )
    assert payload["raw"]["data"]["reason"] == (
        f"expected revision {current + 1}, found {current}"
    )
    assert _c_policy_bytes() == sealed

    # The current N revokes the grant and every binding on it.
    payload = _c_run(
        [
            "memory",
            "revoke",
            "--grant-id",
            grant_id,
            "--expected-policy-revision",
            str(current),
            "--approve",
            "--allow-cache-write",
        ],
        code="OK",
    )
    result = {
        "grant_id": grant_id,
        "policy_revision": current + 1,
        "revoked": True,
        "revoked_bindings": [b["binding_id"] for b in bindings],
    }
    assert payload["raw"]["data"] == result
    after = _c_policy()
    assert after["grants"][grant_id]["revoked"] is True
    assert all(b["revoked"] for b in after["bindings"].values())
    revoked_bytes = _c_policy_bytes()

    # Already revoked: the idempotent result comes before any revision check.
    payload = _c_run(
        [
            "memory",
            "revoke",
            "--grant-id",
            grant_id,
            "--expected-policy-revision",
            "0",
            "--approve",
            "--allow-cache-write",
        ],
        code="OK",
    )
    assert payload["raw"]["data"] == result
    assert _c_policy_bytes() == revoked_bytes

    # An invalid policy file is E_POLICY_INVALID for the preview as well.
    auth.policy_path(data_root=_c_data_root()).write_bytes(b"{")
    invalid = _c_policy()
    payload = _c_run(
        ["memory", "revoke", "--grant-id", grant_id, "--expected-policy-revision", "0"],
        code="E_POLICY_INVALID",
    )
    assert payload["raw"]["data"]["reason"] == invalid["reason"]


def test_consent_defaults_operations_and_legacy_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.store import legacy_owner_scope

    root = _c_project(tmp_path)
    revision = 0

    def approve(*extra: str, project: Path | None = root) -> dict[str, Any]:
        nonlocal revision
        args = ["memory", "grant"]
        if project is not None:
            args += ["--project", str(project)]
        args += [*extra, "--expected-policy-revision", str(revision)]
        args += ["--approve", "--allow-cache-write"]
        data = _c_run(args, code="OK")["raw"]["data"]
        revision = data["policy_revision"]
        return data

    # A1.2 / A1.5: no owner and no operation → the legacy project owner, six ops.
    preview = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--source",
            "s-default",
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )["raw"]["data"]
    assert preview["owner_scope"] == legacy_owner_scope(root).as_dict()
    assert preview["operations"] == CONSENT_DEFAULT_OPS
    default = approve("--source", "s-default")
    assert default["owner_scope"] == legacy_owner_scope(root).as_dict()
    assert default["allowed_operations"] == CONSENT_DEFAULT_OPS
    assert "overlay_read" not in default["allowed_operations"]

    # A1.1: --owner splits on the first colon.
    alice = approve("--source", "s-alice", "--owner", "user:alice")
    assert alice["owner_scope"] == {"kind": "user", "id": "alice"}
    drive = approve("--source", "s-drive", "--owner", "project:C:\\x")
    assert drive["owner_scope"] == {"kind": "project", "id": "C:\\x"}

    # A1.5: an explicit --operation list is used exactly (sorted by the writer).
    explicit = approve(
        "--source",
        "s-explicit",
        "--owner",
        "agent:codex",
        "--operation",
        "write",
        "--operation",
        "ask",
    )
    assert explicit["allowed_operations"] == ["ask", "write"]
    owners = {
        (g["owner_scope"]["kind"], g["owner_scope"]["id"])
        for g in _c_policy()["grants"].values()
        if not g["revoked"]
    }
    assert owners == {
        ("project", str(root)),
        ("user", "alice"),
        ("project", "C:\\x"),
        ("agent", "codex"),
    }

    # --project defaults to the current directory.
    other = _c_project(tmp_path, "other")
    monkeypatch.chdir(other)
    previewed = _c_run(
        ["memory", "grant", "--source", "s", "--expected-policy-revision", "0"],
        code="OK",
    )["raw"]["data"]
    assert previewed["project_root"] == str(other)
    granted = approve("--source", "s", project=None)
    assert granted["project_id"] == _c_project_id(other)
    assert granted["owner_scope"] == legacy_owner_scope(other).as_dict()


def test_overlay_default_grant_authorizes_overlay_read(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    data_root = _c_data_root()
    overlay = auth.user_overlay_owner_scope(data_root=data_root)
    seven = sorted([*CONSENT_DEFAULT_OPS, "overlay_read"])
    root = _c_project(tmp_path, "overlay-project")
    preview = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--overlay",
            "--source",
            OVERLAY_SOURCE,
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )["raw"]["data"]
    assert set(preview) == PREVIEW_KEYS | {
        "overlay_store_binding",
        "overlay_stated_rows",
    }
    assert preview["overlay"] is True
    assert preview["owner_scope"] == overlay.as_dict()
    assert preview["operations"] == seven
    assert preview["overlay_store_binding"] is None
    assert preview["overlay_stated_rows"] == 0
    argv = _c_grant_argv(root, seven, [OVERLAY_SOURCE], owner=["--overlay"], revision=0)
    assert preview["approve_command"] == _c_render(argv)

    granted = _c_run(
        _c_grant_args(root, 0, "--overlay", "--source", OVERLAY_SOURCE), code="OK"
    )["raw"]["data"]
    assert granted["owner_scope"] == overlay.as_dict()
    assert granted["allowed_operations"] == seven
    resolved = _resolve(
        auth,
        root,
        data_root,
        operation="overlay_read",
        owner_scope=overlay,
        requested_sources=[OVERLAY_SOURCE],
    )
    _assert_granted(resolved)
    assert resolved["grant_id"] == granted["grant_id"]

    # The project-owner default holds no overlay_read and cannot reach the overlay.
    plain = _c_project(tmp_path, "plain-project")
    default = _c_run(_c_grant_args(plain, 1, "--source", "src"), code="OK")["raw"][
        "data"
    ]
    assert "overlay_read" not in default["allowed_operations"]
    denied = _resolve(
        auth,
        plain,
        data_root,
        operation="overlay_read",
        owner_scope=overlay,
        requested_sources=[OVERLAY_SOURCE],
    )
    assert denied["access"] == "denied"
    assert denied["reason"] == "owner_not_granted"


def test_consent_overlay_and_all_current_sources(tmp_path: Path) -> None:
    import rush.memory.authorization as auth
    from rush.memory.store import OwnerScope, legacy_owner_scope

    # A1.4: usage errors are exit 2 with the exact message and write nothing.
    root = _c_project(tmp_path)
    before = _c_state(root)
    base = ["memory", "grant", "--project", str(root)]
    revision = ["--expected-policy-revision", "0"]
    for extra, message in (
        (
            ["--owner", "user:alice", "--overlay", "--source", "s"],
            "--owner and --overlay are mutually exclusive",
        ),
        (
            ["--source", "s", "--all-current-sources"],
            "--source and --all-current-sources are mutually exclusive",
        ),
        ([], "--source or --all-current-sources is required"),
        (
            ["--all-current-sources", "--approve", "--allow-cache-write"],
            "--all-current-sources is preview-only",
        ),
        (
            ["--all-current-sources", "--approve"],
            "--all-current-sources is preview-only",
        ),
        (["--source", "s", "--owner", "nocolon"], "Invalid value for '--owner'"),
        (["--source", "s", "--owner", "bogus:x"], "Invalid value for '--owner'"),
        (["--source", "s", "--owner", "user:"], "Invalid value for '--owner'"),
        (["--source", "s", "--owner", "user:   "], "Invalid value for '--owner'"),
        (["--source", "s", "--owner", ":x"], "Invalid value for '--owner'"),
    ):
        _c_usage([*base, *extra, *revision], message)
    assert _c_state(root) == before

    # A2.12: --all-current-sources lists the catalog plus the resolved owner's
    # uncovered inventory sources, family items as `<name>:*`.
    alice = OwnerScope("user", "alice")
    overlay = auth.user_overlay_owner_scope(data_root=_c_data_root())
    store = _c_write_rows(
        root,
        [
            ("k1", "src-a", None),
            ("k2", "src-a", None),
            ("k3", "intent:abc", None),
            ("k4", "src-null", None),
            ("k5", "src-b", alice),
            ("k6", "ov-src", overlay),
        ],
    )
    db = Path(store.db_path)
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "UPDATE memory_artifacts SET owner_scope_kind = NULL, "
            "owner_scope_id = NULL WHERE id = 'k4'"
        )
        conn.commit()
    catalog = auth.writer_source_catalog(root)
    expected = sorted({*catalog, "src-a", "src-null"})
    payload = _c_run([*base, "--all-current-sources", *revision], code="OK")
    data = payload["raw"]["data"]
    assert data["all_current_sources"] is True
    assert sorted(data["sources"]) == expected
    assert len(set(data["sources"])) == len(data["sources"])
    assert "intent:*" in data["sources"] and "intent:abc" not in data["sources"]
    assert "src-b" not in data["sources"] and "ov-src" not in data["sources"]
    argv = _c_grant_argv(root, CONSENT_DEFAULT_OPS, expected, revision=0)
    assert data["approve_command"] == _c_render(argv)
    _c_argv_of(data["approve_command"], argv)
    assert data["approve_command_refused"] is None
    assert _c_policy_bytes() is None

    # --overlay adds only the project-store groups owned by the overlay owner.
    payload = _c_run(
        [*base, "--overlay", "--all-current-sources", *revision], code="OK"
    )
    overlay_data = payload["raw"]["data"]
    assert sorted(overlay_data["sources"]) == sorted({*catalog, "ov-src"})
    assert overlay_data["owner_scope"] == overlay.as_dict()
    assert overlay_data["overlay"] is True

    # A3.6: a source added after the preview is absent when the command is run.
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "INSERT INTO memory_artifacts (id, family, subject, trust_tier, content, "
            "source, created_at, owner_scope_kind, owner_scope_id) VALUES "
            "('k7', 'memory', 'domain_knowledge', 'DERIVED', '{\"t\": 1}', "
            "'src-new', 1.0, 'project', ?)",
            (str(root),),
        )
        conn.commit()
    printed = _c_argv_of(data["approve_command"], argv)
    exit_code, applied, output = _c_cli(*printed[1:], "--json")
    assert exit_code == 0, output
    assert applied["raw"]["code"] == "OK", applied
    granted = applied["raw"]["data"]
    assert granted["owner_scope"] == legacy_owner_scope(root).as_dict()
    assert granted["approved_sources"] == expected
    assert "src-new" not in granted["approved_sources"]

    # --overlay approve with explicit sources: the overlay owner holds overlay_read.
    overlay_grant = _c_run(
        _c_grant_args(root, 1, "--overlay", "--source", OVERLAY_SOURCE), code="OK"
    )["raw"]["data"]
    assert overlay_grant["owner_scope"] == overlay.as_dict()
    assert "overlay_read" in overlay_grant["allowed_operations"]


def test_consent_approve_needs_cache_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.memory.authorization as auth
    from rush.memory.store import TypedArtifactStore

    root = _c_project(tmp_path)
    _c_write_rows(root, [("r1", "src-a", None)])
    before = _c_state(root)

    def refuse(name: str) -> Any:
        def inner(*_args: Any, **_kwargs: Any) -> Any:
            raise AssertionError(f"{name} ran before the permission check")

        return inner

    # The permission check is decided before any read: nothing below may run.
    for name in ("load_policy_readonly", "grant_memory_scope", "revoke_memory_scope"):
        monkeypatch.setattr(auth, name, refuse(name))
    monkeypatch.setattr(
        TypedArtifactStore,
        "open_readonly_view",
        classmethod(lambda cls, _root: refuse("open_readonly_view")()),
    )
    monkeypatch.setattr(
        TypedArtifactStore, "bind_store", staticmethod(refuse("bind_store"))
    )
    digest = "0" * 64
    for extra in ([], ["--allow-artifact-write"], ["--allow-build", "--allow-slow"]):
        payload = _c_skipped(
            [
                "memory",
                "grant",
                "--project",
                str(root),
                "--source",
                "src-a",
                "--expected-policy-revision",
                "0",
                "--approve",
                *extra,
            ],
            "grant",
        )
        assert (
            payload["summary"] == "memory grant --approve requires --allow-cache-write."
        )
        payload = _c_skipped(
            [
                "memory",
                "revoke",
                "--grant-id",
                str(uuid.uuid4()),
                "--expected-policy-revision",
                "0",
                "--approve",
                *extra,
            ],
            "revoke",
        )
        assert (
            payload["summary"]
            == "memory revoke --approve requires --allow-cache-write."
        )
        payload = _c_skipped(
            [
                "memory",
                "bind-store",
                "--project",
                str(root),
                "--approve",
                "--expected-digest",
                digest,
                *extra,
            ],
            "bind_store",
        )
        assert "--approve requires --allow-cache-write" in payload["summary"]
    assert _c_state(root) == before


def test_no_mcp_dashboard_tui_grant_route() -> None:
    """A8.1: the only callers of the four consent writers are in `cli.py`; no MCP
    tool, request-model tag or memory operation names a grant, revoke or binding."""
    import ast
    import asyncio

    from rush.mcp import mcp_server
    from rush.mcp_support.request_models import memory_model_tags
    from rush.tools.memory import VALID_OPERATIONS

    names = {
        "grant_memory_scope",
        "revoke_memory_scope",
        "register_memory_binding",
        "bind_store",
    }
    src = Path(__file__).resolve().parents[1] / "src" / "rush"
    callers: dict[str, set[str]] = {}
    for path in sorted(src.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else None
            )
            if name in names:
                callers.setdefault(path.relative_to(src).as_posix(), set()).add(name)
    assert set(callers) <= {"cli.py"}, callers

    forbidden = ("grant", "revoke", "bind_store", "bind-store", "memory_binding")
    tools = asyncio.run(mcp_server.list_tools())
    for tool in tools:
        lowered = tool.name.lower()
        assert not any(word in lowered for word in forbidden), tool.name
    connection = next(t for t in tools if t.name == "rush_agent_connection")
    assert "memory_binding" not in json.dumps(connection.inputSchema)
    for tag in memory_model_tags() | set(VALID_OPERATIONS):
        assert not any(word in str(tag) for word in forbidden), tag
    assert "bootstrap" not in VALID_OPERATIONS

    # The three consent writers are governed as CLI-only admin operations.
    from rush.governance.public_operations import build_operations_inventory

    by_id = {op.id: op for op in build_operations_inventory()}
    for op_id, command in (
        ("admin.memory_grant", "memory grant"),
        ("admin.memory_revoke", "memory revoke"),
        ("admin.memory_bind_store", "memory bind-store"),
    ):
        assert op_id in by_id, op_id
        assert by_id[op_id].kind == "admin", op_id
        assert by_id[op_id].cli_command == command, op_id
        assert by_id[op_id].mcp_tool is None, op_id


def _c_bind_args(root: Path, *extra: str) -> list[str]:
    return ["memory", "bind-store", "--project", str(root), *extra]


def _c_bind_command(root: Path, digest: str, *, overlay: bool = False) -> list[str]:
    return [
        "rush",
        "memory",
        "bind-store",
        "--project",
        str(root),
        *(["--overlay"] if overlay else []),
        "--approve",
        "--expected-digest",
        digest,
        "--allow-cache-write",
        "--json",
    ]


def _c_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _c_insert_late_row(db: Path, source: str) -> None:
    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.execute(
            "INSERT INTO memory_artifacts (id, family, subject, trust_tier, content, "
            "source, created_at) VALUES ('late', 'memory', 'domain_knowledge', "
            "'DERIVED', '{\"t\": 1}', ?, 1.0)",
            (source,),
        )
        conn.commit()


def _c_visibility(root: Path, row_id: str, source: str) -> Any:
    from rush.memory.retrieval import MemoryAccess, evaluate_artifact_visibility
    from rush.memory.store import TypedArtifactStore

    view, state = TypedArtifactStore.open_readonly_view(root)
    assert view is not None, state
    try:
        row = view.get_current_row(row_id)
        return evaluate_artifact_visibility(
            view, row, access=MemoryAccess.legacy(root, [source])
        )
    finally:
        view.close()


def test_consent_bind_store_preview_and_approve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory.store import TypedArtifactStore

    digest0 = "0" * 64

    # A9.1: the two usage errors, each with its own message.
    usage = _c_project(tmp_path, "usage")
    before = _c_state(usage)
    _c_usage(_c_bind_args(usage, "--approve"), "--approve requires --expected-digest")
    _c_usage(
        _c_bind_args(usage, "--expected-digest", digest0),
        "--expected-digest requires --approve",
    )
    _c_usage(
        _c_bind_args(usage, "--approve", "--allow-cache-write"),
        "--approve requires --expected-digest",
    )
    assert _c_state(usage) == before

    # A9.2: --approve without --allow-cache-write is skipped, naming cache_write.
    _c_skipped(
        _c_bind_args(usage, "--approve", "--expected-digest", digest0), "bind_store"
    )
    assert _c_state(usage) == before

    # A9.4: an absent database previews as absent; approve is store_changed and
    # `bind_store` is never reached.
    def not_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("bind_store called for an absent store")

    with monkeypatch.context() as absent:
        absent.setattr(TypedArtifactStore, "bind_store", staticmethod(not_called))
        payload = _c_run(_c_bind_args(usage), code="OK")
        assert payload["raw"]["data"] == {
            "project_root": str(usage),
            "overlay": False,
            "store": "absent",
            "approve_command": None,
        }
        assert payload["raw"]["operation"] == "bind_store"
        payload = _c_run(
            _c_bind_args(
                usage,
                "--approve",
                "--expected-digest",
                digest0,
                "--allow-cache-write",
            ),
            code="E_VERSION",
        )
        assert payload["raw"]["data"]["reason"] == "store_changed"
    assert _c_state(usage) == before
    assert not (usage / ".rush" / "memory.db").exists()

    # A9.5: a present store previews as `bind_store(approve=False)` plus the store
    # marker and the exact approve command; zero bytes change.
    root = _c_project(tmp_path, "planted")
    db = _c_unbound_stated(root, "planted", "planted-source")
    expected = dict(TypedArtifactStore.bind_store(root, approve=False))
    assert expected.pop("code") == "OK"
    assert expected["store_binding"] == "unbound" and expected["stated_rows"] == 1
    before_bytes = _c_sha(db)
    before = _c_state(root)
    with _c_no_effects(monkeypatch):
        payload = _c_run(_c_bind_args(root), code="OK")
    data = payload["raw"]["data"]
    assert {k: data[k] for k in expected} == expected
    assert data["store"] == "present"
    assert data["approve_command"] == _c_render(
        _c_bind_command(root, expected["binding_digest"])
    )
    assert _c_sha(db) == before_bytes and _c_state(root) == before
    assert _c_visibility(root, "planted", "planted-source").usable_as_current is False

    # A9.6: a row inserted since the preview → store_changed, zero bytes changed.
    _c_insert_late_row(db, "planted-source")
    stale_bytes = _c_sha(db)
    stale_state = _c_state(root)
    payload = _c_run(
        _c_bind_args(
            root,
            "--approve",
            "--expected-digest",
            expected["binding_digest"],
            "--allow-cache-write",
        ),
        code="E_VERSION",
    )
    assert payload["raw"]["data"]["reason"] == "store_changed"
    assert _c_sha(db) == stale_bytes and _c_state(root) == stale_state
    assert _c_binding(root) == "unbound"

    # The fresh preview's command binds; the planted STATED row becomes usable.
    fresh = _c_run(_c_bind_args(root), code="OK")["raw"]["data"]
    assert fresh["binding_digest"] != expected["binding_digest"]
    printed = _c_argv_of(
        fresh["approve_command"], _c_bind_command(root, fresh["binding_digest"])
    )
    exit_code, applied, output = _c_cli(*printed[1:])
    assert exit_code == 0, output
    assert applied["raw"]["code"] == "OK", applied
    assert applied["raw"]["data"]["store_binding"] == "bound"
    assert _c_binding(root) == "bound"
    assert _c_visibility(root, "planted", "planted-source").usable_as_current is True
    # A second approval of the same digest is stale: the bound store's digest moved.
    payload = _c_run(
        _c_bind_args(
            root,
            "--approve",
            "--expected-digest",
            fresh["binding_digest"],
            "--allow-cache-write",
        ),
        code="E_VERSION",
    )
    assert payload["raw"]["data"]["reason"] == "store_changed"


def _c_overlay_fixture(tmp_path: Path) -> tuple[Path, Any, Path]:
    """Project P holding an overlay-owner grant and an overlay store whose STATED row
    `p1` lost its binding row."""
    import rush.memory.authorization as auth

    data_root = _c_data_root()
    overlay = auth.user_overlay_owner_scope(data_root=data_root)
    root = _c_project(tmp_path, "overlay-owner")
    _grant(
        auth,
        root,
        overlay,
        data_root,
        sources=(OVERLAY_SOURCE,),
        ops=("overlay_read", "list", "expand", "write"),
        expected=int(_c_policy()["policy_revision"]),
    )
    db = _c_unbound_stated(data_root / "user", "p1", OVERLAY_SOURCE, owner=overlay)
    return root, overlay, db


def _c_overlay_expand(root: Path, overlay: Any) -> Any:
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    return MemoryTool().run(
        root,
        operation="expand",
        session_allowlist=[OVERLAY_SOURCE],
        owner_scope=overlay.as_dict(),
        request={"id": "p1", "version": 1},
        permissions=ExecutionPermissions(cache_write=True),
    )


def test_consent_bind_store_overlay(tmp_path: Path) -> None:
    import rush.memory.authorization as auth
    from rush.memory.retrieval import required_operation_set

    # D1 row 1a is decided before any policy state: legacy, no policy and a project
    # with grants all give the same refusal.
    data_root = _c_data_root()
    legacy = _c_project(tmp_path, "legacy-first")
    overlay_root = data_root / "user"
    overlay_root.mkdir(parents=True, exist_ok=True)
    (overlay_root / "sub").mkdir(exist_ok=True)

    legacy_preview = _c_run(_c_bind_args(legacy, "--overlay"), code="E_PERMISSION")
    overlay_ref = auth.user_overlay_owner_scope(data_root=data_root)
    assert legacy_preview["raw"]["data"]["reason"] == "policy_missing"
    assert legacy_preview["raw"]["next_action"] == auth.memory_next_action(
        reason="policy_missing",
        project_root=legacy,
        operations=required_operation_set("list", overlay=True),
        owner_scope=overlay_ref,
    )
    assert "--overlay" in legacy_preview["raw"]["next_action"]["command"]

    root, overlay, db = _c_overlay_fixture(tmp_path)
    assert overlay == overlay_ref
    before_bytes = _c_sha(db)

    # A9.3: a project equal to, or under, the overlay storage root is refused with
    # or without --overlay, preview and approve, before any policy lookup.
    before = _c_state(root, overlay_root)
    for target in (overlay_root, overlay_root / "sub"):
        for overlay_flag in ([], ["--overlay"]):
            for approve in ([], ["--approve", "--expected-digest", "0" * 64]):
                extra = [*overlay_flag, *approve]
                if approve:
                    extra.append("--allow-cache-write")
                payload = _c_run(_c_bind_args(target, *extra), code="E_PERMISSION")
                assert payload["raw"]["data"]["reason"] == "overlay_storage_root"
    assert _c_state(root, overlay_root) == before and _c_sha(db) == before_bytes

    # A9.7: from a project holding the overlay-owner grant the overlay is previewed
    # as unbound with one STATED row, and the printed command binds it.
    with_before = _c_expand_state(root, overlay)
    assert with_before == "E_NOT_VISIBLE"
    preview = _c_run(_c_bind_args(root, "--overlay"), code="OK")["raw"]["data"]
    assert preview["overlay"] is True
    assert preview["store"] == "present"
    assert preview["store_binding"] == "unbound"
    assert preview["stated_rows"] == 1
    assert _c_sha(db) == before_bytes
    argv = _c_bind_command(root, preview["binding_digest"], overlay=True)
    assert preview["approve_command"] == _c_render(argv)
    printed = _c_argv_of(preview["approve_command"], argv)
    exit_code, applied, output = _c_cli(*printed[1:])
    assert exit_code == 0, output
    assert applied["raw"]["code"] == "OK", applied
    assert _c_binding(overlay_root) == "bound"
    with contextlib.closing(sqlite3.connect(db)) as conn:
        assert conn.execute(
            "SELECT trust_tier FROM memory_artifacts WHERE id = 'p1'"
        ).fetchone() == ("STATED",)
    assert _c_expand_state(root, overlay) == "OK"

    # A project without an overlay-owner grant, and a project with no grant at
    # all, get the item 7 denial with a --overlay next action and zero writes.
    plain = _c_project(tmp_path, "project-grant-only")
    _grant(
        auth,
        plain,
        _alice(),
        data_root,
        expected=int(_c_policy()["policy_revision"]),
    )
    none = _c_project(tmp_path, "no-grant")
    for project, code, reason in (
        (plain, "E_OWNER", "owner_not_granted"),
        (none, "E_PERMISSION", "no_grant"),
    ):
        for approve in ([], ["--approve", "--expected-digest", "0" * 64]):
            extra = ["--overlay", *approve]
            if approve:
                extra.append("--allow-cache-write")
            operations = required_operation_set(
                "write" if approve else "list", apply=bool(approve), overlay=True
            )
            snapshot = _c_state(project, overlay_root)
            payload = _c_run(_c_bind_args(project, *extra), code=code)
            assert payload["raw"]["data"]["reason"] == reason
            expected_next = auth.memory_next_action(
                reason=reason,
                project_root=project,
                operations=operations,
                owner_scope=overlay,
            )
            assert payload["raw"]["next_action"] == expected_next
            assert "--overlay" in str(expected_next["command"])
            assert _c_state(project, overlay_root) == snapshot


def _alice() -> Any:
    from rush.memory.store import OwnerScope

    return OwnerScope("user", "alice")


def _c_expand_state(root: Path, overlay: Any) -> str:
    result = _c_overlay_expand(root, overlay)
    return str(result["raw"]["code"])


def test_consent_preview_lists_writer_catalog(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    root = _c_project(tmp_path)
    catalog = auth.writer_source_catalog(root)
    assert any(item.endswith(":*") for item in catalog)
    # An empty project: every catalog item with zero rows, in catalog order.
    data = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--all-current-sources",
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )["raw"]["data"]
    assert data["catalog"] == [{"source": item, "rows": 0} for item in catalog]
    assert catalog == [c["source"] for c in data["catalog"]]

    # Rows under writer sources are counted against the item that grants them.
    _c_write_rows(
        root,
        [
            ("i1", "intent:one", None),
            ("i2", "intent:two", None),
            ("r1", "recipe:one", None),
            ("c1", "checkpoint_journal:save_checkpoint", None),
            ("x1", "plain-source", None),
        ],
    )
    expected = _c_expected_inventory(root)
    by_source = {c["source"]: c["rows"] for c in expected["catalog"]}
    assert by_source["intent:*"] == 2 and by_source["recipe:*"] == 1
    assert by_source["checkpoint_journal:save_checkpoint"] == 1
    data = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--all-current-sources",
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )["raw"]["data"]
    assert data["catalog"] == expected["catalog"]
    assert data["other_sources"] == expected["other_sources"]
    argv = _c_grant_argv(
        root, CONSENT_DEFAULT_OPS, sorted({*catalog, "plain-source"}), revision=0
    )
    printed = _c_argv_of(data["approve_command"], argv)
    sources_in_command = [
        printed[i + 1] for i, part in enumerate(printed) if part == "--source"
    ]
    assert "intent:*" in sources_in_command and "recipe:*" in sources_in_command
    assert "intent:one" not in sources_in_command

    # An explicit family item is printed as the family item.
    data = _c_run(
        [
            "memory",
            "grant",
            "--project",
            str(root),
            "--source",
            "intent:*",
            "--expected-policy-revision",
            "0",
        ],
        code="OK",
    )["raw"]["data"]
    argv = _c_grant_argv(root, CONSENT_DEFAULT_OPS, ["intent:*"], revision=0)
    assert data["approve_command"] == _c_render(argv)
    assert data["sources"] == ["intent:*"]
    assert data["approve_command_refused"] is None
    granted = _c_run(_c_grant_args(root, 0, "--source", "intent:*"), code="OK")
    assert granted["raw"]["data"]["approved_sources"] == ["intent:*"]


def test_consent_preview_reports_store_binding(tmp_path: Path) -> None:
    import rush.memory.authorization as auth

    data_root = _c_data_root()
    overlay = auth.user_overlay_owner_scope(data_root=data_root)
    text_project = "this project's memory store is unbound; preview binding it"
    text_overlay = "the personal overlay store is unbound; preview binding it"

    def preview(root: Path, *extra: str) -> dict[str, Any]:
        return _c_run(
            [
                "memory",
                "grant",
                "--project",
                str(root),
                *extra,
                "--source",
                "planted-source",
                "--expected-policy-revision",
                "0",
            ],
            code="OK",
        )

    # An unbound project store holding one planted STATED row.
    unbound = _c_project(tmp_path, "unbound")
    db = _c_unbound_stated(unbound, "planted", "planted-source")
    before_bytes, before = _c_sha(db), _c_state(unbound)
    payload = preview(unbound)
    assert payload["raw"]["data"]["store_binding"] == "unbound"
    assert payload["raw"]["data"]["stated_rows"] == 1
    assert payload["raw"]["next_action"] == {
        "text": text_project,
        "command": _c_render(
            ["rush", "memory", "bind-store", "--project", str(unbound)]
        ),
    }
    assert _c_sha(db) == before_bytes and _c_state(unbound) == before

    # A bound store: the same preview carries no next_action.
    bound = _c_project(tmp_path, "bound")
    bound_store = _c_write_rows(bound, [("k1", "planted-source", None)])
    payload = preview(bound)
    assert payload["raw"]["data"]["store_binding"] == "bound"
    assert payload["raw"]["data"]["stated_rows"] == 0
    assert "next_action" not in payload["raw"]
    assert bound_store.db_path.exists()

    # --overlay with a bound project store and an unbound overlay store.
    overlay_db = _c_unbound_stated(
        data_root / "user", "o1", OVERLAY_SOURCE, owner=overlay
    )
    overlay_before = _c_sha(overlay_db)
    before = _c_state(bound)
    payload = preview(bound, "--overlay")
    data = payload["raw"]["data"]
    assert data["store_binding"] == "bound"
    assert data["overlay_store_binding"] == "unbound"
    assert data["overlay_stated_rows"] == 1
    assert payload["raw"]["next_action"] == {
        "text": text_overlay,
        "command": _c_render(
            ["rush", "memory", "bind-store", "--project", str(bound), "--overlay"]
        ),
    }
    assert _c_sha(overlay_db) == overlay_before and _c_state(bound) == before

    # An unbound project store wins over an unbound overlay store.
    payload = preview(unbound, "--overlay")
    assert payload["raw"]["next_action"]["command"] == _c_render(
        ["rush", "memory", "bind-store", "--project", str(unbound)]
    )

    # An absent project store does not hide an unbound overlay store (D16/D41).
    absent = _c_project(tmp_path, "absent")
    payload = preview(absent, "--overlay")
    assert payload["raw"]["data"]["store_binding"] is None
    assert payload["raw"]["data"]["overlay_store_binding"] == "unbound"
    assert payload["raw"]["next_action"]["command"] == _c_render(
        ["rush", "memory", "bind-store", "--project", str(absent), "--overlay"]
    )

    # An absent overlay store reports null and 0 (the store key stays in place).
    overlay_db.unlink()
    payload = preview(bound, "--overlay")
    assert payload["raw"]["data"]["overlay_store_binding"] is None
    assert payload["raw"]["data"]["overlay_stated_rows"] == 0
    assert "next_action" not in payload["raw"]


# --- G4: trust-boundary inputs of the consent commands --------------------------------


def _c_exit2(args: list[str], *needles: str) -> None:
    exit_code, payload, output = _c_cli(*args)
    assert exit_code == 2, (args, output)
    assert payload is None, (args, output)
    for needle in needles:
        assert needle in output, (needle, output)


def _c_preview_args(root: Path, *extra: str, revision: str = "0") -> list[str]:
    return [
        "memory",
        "grant",
        "--project",
        str(root),
        *extra,
        "--expected-policy-revision",
        revision,
    ]


def _c_refused_preview(root: Path, element: str, *extra: str) -> None:
    """A preview whose approve command carries an unsafe element: the preview itself
    succeeds, the command is withheld and the refused element is named."""
    data = _c_run(_c_preview_args(root, *extra), code="OK")["raw"]["data"]
    assert data["approve_command"] is None, data
    assert data["approve_command_refused"] == repr(element), data


def _c_g4_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _c_project(tmp_path)
    store = _c_write_rows(root, [("k1", "src-a", None)])
    sources = ["--source", "src-a"]
    # NUL and a missing path are Click path errors, never a traceback.
    _c_exit2(_c_preview_args(Path("a\x00b"), *sources), "does not exist")
    _c_exit2(_c_preview_args(tmp_path / "missing", *sources), "does not exist")
    _c_exit2(["memory", "bind-store", "--project", "a\x00b"], "does not exist")
    _c_exit2(
        ["memory", "bind-store", "--project", str(tmp_path / "missing")],
        "does not exist",
    )
    # A canonical root that is not UTF-8 (POSIX non-UTF-8 argv) is project_missing.
    real_resolve = Path.resolve

    def fake_resolve(self: Path, strict: bool = False) -> Path:
        resolved = real_resolve(self, strict=strict)
        return (
            Path(str(resolved) + "\udcff")
            if resolved == real_resolve(root)
            else resolved
        )

    with monkeypatch.context() as bad_root:
        bad_root.setattr(Path, "resolve", fake_resolve)
        bad_root.setattr(Path, "is_dir", lambda self: True)
        for extra in ([], ["--approve", "--allow-cache-write"]):
            payload = _c_run(
                _c_preview_args(root, *sources, "--owner", "user:alice", *extra),
                code="E_INPUT",
            )
            assert payload["raw"]["data"]["reason"] == "project_missing"
    # A format character in the root path: the preview names the refused element.
    odd = _c_project(tmp_path, "pro\u202eject")
    _c_refused_preview(odd, str(odd), *sources)
    # A moved root is unregistered: preview succeeds, approve names the recovery;
    # the store still previews at the path it was moved to.
    moved = tmp_path / "moved-project"
    root.rename(moved)
    moved = moved.resolve()
    data = _c_run(_c_preview_args(moved, *sources), code="OK")["raw"]["data"]
    assert data["project_id"] is None
    payload = _c_run(
        _c_preview_args(moved, *sources, "--approve", "--allow-cache-write"),
        code="E_PROJECT_NOT_REGISTERED",
    )
    assert payload["raw"]["data"]["reason"] == "project_not_registered"
    assert payload["raw"]["next_action"]["command"] is not None
    present = _c_run(["memory", "bind-store", "--project", str(moved)], code="OK")
    assert present["raw"]["data"]["store"] == "present"
    assert store.db_path.parent.name == ".rush"
    # A case-variant root is another path on a case-sensitive file system and the
    # same directory under a different spelling on a case-insensitive one.
    variant = moved.parent / moved.name.swapcase()
    if variant.exists():
        data = _c_run(_c_preview_args(variant, *sources), code="OK")["raw"]["data"]
        assert data["project_id"] is None
    else:
        _c_exit2(_c_preview_args(variant, *sources), "does not exist")


def _c_g4_symlink_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loop_a, loop_b = tmp_path / "loop-a", tmp_path / "loop-b"
    loop_a.symlink_to(loop_b)
    loop_b.symlink_to(loop_a)
    _c_exit2(_c_preview_args(loop_a, "--source", "s"), "does not exist")
    _c_exit2(["memory", "bind-store", "--project", str(loop_a)], "does not exist")


def _c_g4_owner_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _c_project(tmp_path)
    src = ["--source", "src-a"]
    # NUL and format characters are accepted by the writer; the command is withheld.
    _c_refused_preview(root, "user:x\x00y", *src, "--owner", "user:x\x00y")
    _c_refused_preview(root, "user:x\u202ey", *src, "--owner", "user:x\u202ey")
    _c_refused_preview(root, "a\x00b", "--source", "a\x00b")
    _c_refused_preview(root, "a\u200bb", "--source", "a\u200bb")
    # A lone surrogate is E_INPUT for preview and approve alike.
    for approve in ([], ["--approve", "--allow-cache-write"]):
        payload = _c_run(
            _c_preview_args(root, *src, "--owner", "user:x\ud800y", *approve),
            code="E_INPUT",
        )
        assert payload["raw"]["data"]["reason"] == "owner_scope"
        payload = _c_run(
            _c_preview_args(root, "--source", "a\ud800", *approve), code="E_INPUT"
        )
        assert payload["raw"]["data"]["reason"] == "approved_sources"
    # An approved NUL source is accepted by the writer (and stored).
    payload = _c_run(
        _c_grant_args(root, 0, "--source", "a\x00b"),
        code="OK",
    )
    assert payload["raw"]["data"]["approved_sources"] == ["a\x00b"]


def _c_g4_operation_expiry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _c_project(tmp_path)
    src = ["--source", "s"]
    for bad in ("nope", "", "a\x00b", "a\ud800", "a\u202eb", "ASK"):
        _c_exit2(_c_preview_args(root, *src, "--operation", bad), "--operation")
    for bad in ("abc", "", "a\x00b", "1\ud800", "1\u202e", "0x10"):
        _c_exit2(_c_preview_args(root, *src, "--expires-at", bad), "--expires-at")
    payload = _c_run(
        _c_preview_args(root, *src, "--expires-at", "2000000000"), code="OK"
    )
    assert payload["raw"]["data"]["expires_at"] == 2000000000.0
    argv = _c_grant_argv(
        root, CONSENT_DEFAULT_OPS, ["s"], expires=2000000000.0, revision=0
    )
    assert payload["raw"]["data"]["approve_command"] == _c_render(argv)


def _c_g4_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _c_project(tmp_path)
    huge = "1" + "0" * 400
    src = ["--source", "s"]
    for bad in (
        "abc",
        "true",
        "-1",
        "1.5",
        "nan",
        "inf",
        "",
        "1\x00",
        "1\ud800",
        "1\u202e",
    ):
        _c_exit2(
            _c_preview_args(root, *src, revision=bad), "--expected-policy-revision"
        )
        _c_exit2(
            ["memory", "revoke", "--grant-id", "g", "--expected-policy-revision", bad],
            "--expected-policy-revision",
        )
    # 10**400 is a valid non-negative integer: preview reports it, a changed grant
    # fails the CAS, an identical grant and a revoked retry stay idempotent.
    payload = _c_run(_c_preview_args(root, *src, revision=huge), code="OK")
    assert payload["raw"]["data"]["expected_policy_revision"] == 10**400
    sealed = _c_policy_bytes()
    _c_run(_c_grant_args(root, 10**400, *src), code="E_VERSION")
    assert _c_policy_bytes() == sealed
    granted = _c_run(_c_grant_args(root, 0, *src), code="OK")["raw"]["data"]
    sealed = _c_policy_bytes()
    again = _c_run(_c_grant_args(root, 10**400, *src), code="OK")["raw"]["data"]
    assert again == granted and _c_policy_bytes() == sealed
    _c_run(_c_grant_args(root, 10**400, "--source", "other-source"), code="E_VERSION")
    revoke = [
        "memory",
        "revoke",
        "--grant-id",
        granted["grant_id"],
        "--expected-policy-revision",
        huge,
        "--approve",
        "--allow-cache-write",
    ]
    _c_run(revoke, code="E_VERSION")
    assert _c_policy_bytes() == sealed
    _c_run(
        [*revoke[:5], "1", *revoke[6:]],
        code="OK",
    )
    revoked = _c_policy_bytes()
    payload = _c_run(revoke, code="OK")
    assert payload["raw"]["data"]["revoked"] is True
    assert _c_policy_bytes() == revoked


def _c_g4_grant_id_digest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _c_project(tmp_path)
    for bad in ("a\x00b", "a\ud800", "a\u202eb", "not-a-uuid", " "):
        for approve in ([], ["--approve", "--allow-cache-write"]):
            payload = _c_run(
                [
                    "memory",
                    "revoke",
                    "--grant-id",
                    bad,
                    "--expected-policy-revision",
                    "0",
                    *approve,
                ],
                code="E_GRANT_NOT_FOUND",
            )
            assert payload["raw"]["data"]["reason"] == bad
    db = _c_unbound_stated(root, "planted", "planted-source")
    sealed = _c_sha(db)
    for bad in ("abc", "0" * 64, "a\x00b", "a\ud800", "a\u202eb", "0" * 4096):
        payload = _c_run(
            _c_bind_args(
                root, "--approve", "--expected-digest", bad, "--allow-cache-write"
            ),
            code="E_VERSION",
        )
        assert payload["raw"]["data"]["reason"] == "store_changed"
        assert _c_sha(db) == sealed


def _c_g4_helpers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import rush.memory.authorization as auth
    from rush.memory.store import OwnerScope

    root = _c_project(tmp_path)
    good: dict[str, Any] = {"project_root": root, "operations": ["ask"]}
    command = auth.memory_grant_command(**good)
    assert isinstance(command, str) and "--operation ask" in command
    foreign = object.__new__(OwnerScope)
    object.__setattr__(foreign, "kind", [])
    object.__setattr__(foreign, "id", "x")
    odd_id = object.__new__(OwnerScope)
    object.__setattr__(odd_id, "kind", "user")
    object.__setattr__(odd_id, "id", "x\ud800y")
    wrong_types: list[dict[str, Any]] = [
        {"operations": "ask"},
        {"operations": [1]},
        {"operations": [True]},
        {"operations": ["bogus"]},
        {"operations": b"ask"},
        {"operations": None},
        {"owner_scope": "user:alice"},
        {"owner_scope": {"kind": "user", "id": "alice"}},
        {"owner_scope": foreign},
        {"owner_scope": odd_id},
        {"requested_sources": "s"},
        {"requested_sources": [1]},
        {"requested_sources": [None]},
    ]
    wrong_roots: list[dict[str, Any]] = [
        {"project_root": 5},
        {"project_root": None},
        {"project_root": "a\x00b"},
    ]
    for override in wrong_types:
        with pytest.raises(ValueError):
            auth.memory_grant_command(**{**good, **override})
    # An unsafe element: ValueError carries it as args[0].
    for owner_id, element in (
        ("x\ny", "user:x\ny"),
        ("x\x00y", "user:x\x00y"),
        ("x\u202ey", "user:x\u202ey"),
        ("x\x1b[2Kcalc", "user:x\x1b[2Kcalc"),
    ):
        with pytest.raises(ValueError) as info:
            auth.memory_grant_command(**good, owner_scope=OwnerScope("user", owner_id))
        assert info.value.args[0] == element
    with pytest.raises(ValueError) as info:
        auth.memory_grant_command(**good, requested_sources=["fine", "a\x00b"])
    assert info.value.args[0] == "a\x00b"
    # `memory_next_action` never raises: bad input is a null command.
    for override in wrong_types:
        nxt = auth.memory_next_action(reason="no_grant", **{**good, **override})
        assert set(nxt) == {"text", "command"}
        assert nxt["command"] is None, override
        assert isinstance(nxt["text"], str) and nxt["text"]
    unsafe = auth.memory_next_action(
        reason="owner_not_granted",
        **good,
        owner_scope=OwnerScope("user", "x\x00y"),
    )
    assert unsafe["command"] is None and repr("user:x\x00y") in cast(
        "str", unsafe["text"]
    )
    unsafe = auth.memory_next_action(
        reason="owner_not_granted", **good, owner_scope=odd_id
    )
    assert unsafe["command"] is None and repr("user:x\ud800y") in cast(
        "str", unsafe["text"]
    )
    for override in wrong_roots:
        nxt = auth.memory_next_action(reason="no_grant", **{**good, **override})
        assert nxt["command"] is None, override
    # A non-path data_root: the policy loads as unavailable → no command.
    nxt = auth.memory_next_action(reason="no_grant", **good, data_root=5)  # type: ignore[arg-type]  # a non-path data_root is the deliberately wrong type
    assert nxt["command"] is None
    nxt = auth.memory_next_action(reason="no_grant", **good, data_root="a\x00b")  # type: ignore[arg-type]  # a str data_root is the deliberately wrong type
    assert nxt["command"] is None


def _c_g4_data_root_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _c_project(tmp_path)
    data_root = _c_data_root()
    shutil.rmtree(data_root)
    data_root.symlink_to(data_root)  # a self-referential link: ELOOP on every use
    loaded = _c_policy()
    assert loaded["state"] == "unavailable"
    for extra in ([], ["--approve", "--allow-cache-write"]):
        payload = _c_run(
            _c_preview_args(root, "--source", "s", *extra), code="E_POLICY_INVALID"
        )
        assert payload["raw"]["data"]["reason"] == loaded["reason"]
    payload = _c_run(
        ["memory", "revoke", "--grant-id", "g", "--expected-policy-revision", "0"],
        code="E_POLICY_INVALID",
    )
    assert payload["raw"]["data"]["reason"] == loaded["reason"]


def _c_g4_data_root_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _c_project(tmp_path)
    data_root = _c_data_root()
    shutil.rmtree(data_root)
    data_root.write_text("not a directory", encoding="utf-8")
    loaded = _c_policy()
    assert loaded["state"] in ("invalid", "unavailable")
    # The previews read the policy: the loader's own reason.
    payload = _c_run(_c_preview_args(root, "--source", "s"), code="E_POLICY_INVALID")
    assert payload["raw"]["data"]["reason"] == loaded["reason"]
    payload = _c_run(
        ["memory", "revoke", "--grant-id", "g", "--expected-policy-revision", "0"],
        code="E_POLICY_INVALID",
    )
    assert payload["raw"]["data"]["reason"] == loaded["reason"]
    # The grant writer reaches the project registry first: it cannot be read.
    payload = _c_run(
        _c_preview_args(root, "--source", "s", "--approve", "--allow-cache-write"),
        code="E_PROJECT_NOT_REGISTERED",
    )
    assert payload["raw"]["data"]["reason"] == "project_registry_invalid"
    assert "next_action" not in payload["raw"]
    assert data_root.read_bytes() == b"not a directory"


def _c_g4_inventory_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rush.memory.store import TypedArtifactStore, readonly_view_reason

    root = _c_project(tmp_path)
    _c_write_rows(root, [("k1", "src-a", None)])
    before = _c_state(root)

    def broken(self: Any) -> Any:
        raise sqlite3.DatabaseError("database disk image is malformed")

    with monkeypatch.context() as failing:
        failing.setattr(TypedArtifactStore, "consent_inventory", broken, raising=False)
        payload = _c_run(
            _c_preview_args(root, "--source", "src-a"), code="E_STORE_CORRUPT"
        )
    assert payload["raw"]["data"] == {
        "reason": "store_corrupt",
        "message": readonly_view_reason("corrupt"),
    }
    assert _c_state(root) == before
    # A file that is not a database at all: corrupt, never a traceback.
    garbage = _c_project(tmp_path, "garbage")
    (garbage / ".rush").mkdir(exist_ok=True)
    (garbage / ".rush" / "memory.db").write_bytes(b"this is not a sqlite database" * 20)
    sealed = _c_state(garbage)
    payload = _c_run(
        _c_preview_args(garbage, "--source", "src-a"), code="E_STORE_CORRUPT"
    )
    assert payload["raw"]["data"]["reason"] == "store_corrupt"
    assert _c_state(garbage) == sealed


_G4_GROUPS = {
    "project": _c_g4_project,
    "owner_source": _c_g4_owner_source,
    "operation_expiry": _c_g4_operation_expiry,
    "revision": _c_g4_revision,
    "grant_id_digest": _c_g4_grant_id_digest,
    "helpers": _c_g4_helpers,
    "data_root_file": _c_g4_data_root_file,
    "inventory_error": _c_g4_inventory_error,
}


@pytest.mark.parametrize(
    "group",
    [
        *(pytest.param(name, id=name) for name in sorted(_G4_GROUPS)),
        pytest.param("symlink_loop", id="symlink_loop", marks=pytest.mark.posix_only),
        pytest.param(
            "data_root_loop", id="data_root_loop", marks=pytest.mark.posix_only
        ),
    ],
)
def test_consent_trust_boundary_inputs(
    group: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G4: every option row of the consent commands and the two command helpers;
    wrong type, bool-as-int, 10**400, NaN/inf, NUL, lone surrogate, Cc/Cf, symlink
    loop, missing path, non-path data_root, unhashable owner kind, moved and
    case-variant roots. Only declared codes and Click usage errors come back."""
    runners = {
        **_G4_GROUPS,
        "symlink_loop": _c_g4_symlink_loop,
        "data_root_loop": _c_g4_data_root_loop,
    }
    runners[group](tmp_path, monkeypatch)


def test_consent_grant_approve_first_effect_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G3: the policy lock, then the CAS check, then the `.gitignore` and the pending
    D1 marker, then the policy commit; the final marker appears only after the commit."""
    import rush.memory.authorization as auth

    root = _c_project(tmp_path)
    rush_dir = root / ".rush"
    policy = auth.policy_path(data_root=_c_data_root())
    events: list[tuple[str, tuple[str, ...], bool]] = []

    def mark(label: str) -> None:
        names = (
            tuple(sorted(p.name for p in rush_dir.iterdir()))
            if rush_dir.exists()
            else ()
        )
        events.append((label, names, policy.exists()))

    real_lock, real_check, real_commit = (
        auth.hold_policy_lock,
        auth._check_version,
        auth._commit,
    )

    @contextlib.contextmanager
    def lock(**kwargs: Any) -> Iterator[None]:
        mark("lock")
        with real_lock(**kwargs):
            yield

    def check(*args: Any, **kwargs: Any) -> Any:
        mark("version")
        return real_check(*args, **kwargs)

    def commit(*args: Any, **kwargs: Any) -> Any:
        mark("commit")
        return real_commit(*args, **kwargs)

    with monkeypatch.context() as spied:
        spied.setattr(auth, "hold_policy_lock", lock)
        spied.setattr(auth, "_check_version", check)
        spied.setattr(auth, "_commit", commit)
        _c_run(_c_grant_args(root, 0, "--source", "s"), code="OK")
    order = [label for label, _names, _exists in events]
    assert order.index("lock") < order.index("version") < order.index("commit"), order
    first = {label: (names, exists) for label, names, exists in reversed(events)}
    lock_names, lock_policy = first["lock"]
    assert not lock_policy and not [
        n
        for n in lock_names
        if n.startswith("memory-policy.required") or n == ".gitignore"
    ], first["lock"]
    version_names, _ = first["version"]
    assert not [
        n
        for n in version_names
        if n.startswith("memory-policy.required") or n == ".gitignore"
    ], first["version"]
    commit_names, commit_policy = first["commit"]
    assert ".gitignore" in commit_names and not commit_policy
    assert [n for n in commit_names if n.startswith("memory-policy.required.pending-")]
    assert "memory-policy.required" not in commit_names
    assert (rush_dir / "memory-policy.required").exists()
    assert not [p for p in rush_dir.iterdir() if ".pending-" in p.name]


def test_consent_bind_store_approve_resolves_access_before_the_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G3: bind-store approve resolves its D2 access (a read) first and takes the
    policy lock only after it; a denied access never reaches the lock."""
    import rush.memory.authorization as auth
    from rush.memory.retrieval import MemoryAccess
    from rush.memory.store import TypedArtifactStore, legacy_owner_scope

    data_root = _c_data_root()
    root = _c_project(tmp_path)
    db = _c_unbound_stated(root, "planted", "planted-source")
    digest = TypedArtifactStore.bind_store(root, approve=False)["binding_digest"]
    events: list[str] = []
    real_resolve = MemoryAccess.resolve_with_reason
    real_lock = auth.hold_policy_lock

    def resolve(cls: Any, *args: Any, **kwargs: Any) -> Any:
        events.append("resolve")
        return real_resolve(*args, **kwargs)

    @contextlib.contextmanager
    def lock(**kwargs: Any) -> Iterator[None]:
        events.append("lock")
        with real_lock(**kwargs):
            yield

    approve = _c_bind_args(
        root, "--approve", "--expected-digest", digest, "--allow-cache-write"
    )
    _grant(
        auth,
        root,
        legacy_owner_scope(root),
        data_root,
        sources=("planted-source",),
        ops=("list",),
        expected=0,
    )
    before = _c_sha(db)
    with monkeypatch.context() as spied:
        spied.setattr(MemoryAccess, "resolve_with_reason", classmethod(resolve))
        spied.setattr(auth, "hold_policy_lock", lock)
        denied = _c_run(approve, code="E_PERMISSION")
    assert denied["raw"]["data"]["reason"] == "operation_not_granted"
    assert events == ["resolve"], events
    assert _c_sha(db) == before

    _grant(
        auth,
        root,
        legacy_owner_scope(root),
        data_root,
        sources=("planted-source",),
        ops=("list", "write"),
        expected=int(_c_policy()["policy_revision"]),
    )
    events.clear()
    with monkeypatch.context() as spied:
        spied.setattr(MemoryAccess, "resolve_with_reason", classmethod(resolve))
        spied.setattr(auth, "hold_policy_lock", lock)
        _c_run(approve, code="OK")
    assert events[:2] == ["resolve", "lock"], events
    assert _c_binding(root) == "bound"


_C_PRIMARY_FAILURE = "primary-inventory-failure-7f3a"
_C_CLEANUP_FAILURE = "cleanup-close-failure-9c1d"


def _c_spy_views(
    monkeypatch: pytest.MonkeyPatch, *, close_error: str | None
) -> list[dict[str, Any]]:
    """Record every read-only view the preview acquires. Each `close()` really closes
    the view, counts itself, then raises `close_error` (a DatabaseError) when given."""
    from rush.memory.store import TypedArtifactStore

    real = TypedArtifactStore.open_readonly_view
    acquired: list[dict[str, Any]] = []

    def spy(cls: Any, project_root: Path) -> Any:
        view, state = real(project_root)
        if view is not None:
            record: dict[str, Any] = {"root": Path(project_root).resolve(), "closed": 0}
            real_close = view.close

            def close() -> None:
                record["closed"] += 1
                real_close()
                if close_error is not None:
                    raise sqlite3.DatabaseError(close_error)

            monkeypatch.setattr(view, "close", close)
            acquired.append(record)
        return view, state

    monkeypatch.setattr(TypedArtifactStore, "open_readonly_view", classmethod(spy))
    return acquired


@pytest.mark.parametrize(
    ("failures", "overlay"),
    [
        pytest.param("inventory", False, id="inventory-project"),
        pytest.param("inventory", True, id="inventory-overlay"),
        pytest.param("close", False, id="close-project"),
        pytest.param("close", True, id="close-overlay"),
        pytest.param("both", False, id="both-project"),
        pytest.param("both", True, id="both-overlay"),
    ],
)
def test_consent_preview_cleanup_preserves_primary_error(
    failures: str, overlay: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G3 (cleanup masks primary failure): a DatabaseError from the inventory, from
    closing a view, or from both, is `E_STORE_CORRUPT` / `store_corrupt`, never a
    traceback; the two failures are both named when both happen; every acquired view
    is closed and nothing is written."""
    from rush.memory.store import TypedArtifactStore, readonly_view_reason

    root = _c_project(tmp_path)
    _c_write_rows(root, [("k1", "src-a", None)])
    overlay_root = _c_data_root() / "user"
    extra: list[str] = ["--source", "src-a"]
    if overlay:
        _c_write_rows(overlay_root, [("o1", OVERLAY_SOURCE, None)])
        extra = ["--overlay", "--source", OVERLAY_SOURCE]
    before = _c_state(root)
    acquired = _c_spy_views(
        monkeypatch,
        close_error=_C_CLEANUP_FAILURE if failures in ("close", "both") else None,
    )

    def broken(self: Any) -> Any:
        raise sqlite3.DatabaseError(_C_PRIMARY_FAILURE)

    with monkeypatch.context() as failing:
        if failures in ("inventory", "both"):
            failing.setattr(
                TypedArtifactStore, "consent_inventory", broken, raising=False
            )
        payload = _c_run(_c_preview_args(root, *extra), code="E_STORE_CORRUPT")

    data = payload["raw"]["data"]
    assert data["reason"] == "store_corrupt", data
    serialized = json.dumps(data)
    if failures == "inventory":
        assert data == {
            "reason": "store_corrupt",
            "message": readonly_view_reason("corrupt"),
        }
    if failures == "both":
        assert readonly_view_reason("corrupt") in serialized, data
        assert _C_PRIMARY_FAILURE in serialized, data
        assert _C_CLEANUP_FAILURE in serialized, data
    assert acquired, "the preview acquired no read-only view"
    assert all(record["closed"] >= 1 for record in acquired), acquired
    if overlay:
        assert {record["root"] for record in acquired} >= {
            root.resolve(),
            overlay_root.resolve(),
        }, acquired
    assert _c_state(root) == before


def _c_oracle_mutations(
    root: Path, store: Any, home: Path, data_root: Path
) -> dict[str, tuple[Any, Any]]:
    """One `(mutate, restore)` pair per component the zero-write oracle must see."""
    import rush.memory.authorization as auth

    policy = auth.policy_path(data_root=data_root)
    db = Path(store.db_path)
    key = data_root / "user" / ".rush" / "memory_store.key"
    marker = root / ".rush" / "memory-policy.required"
    config = home / ".codex" / "config.toml"
    ledger = home / "agent-ledger.json"
    index = root / ".git" / "index"
    link = root / "link"
    added = root / ".rush" / "extra-dir"

    def rewrite(path: Path) -> tuple[Any, Any]:
        original = path.read_bytes()
        return (
            lambda: path.write_bytes(original + b" changed"),
            lambda: path.write_bytes(original),
        )

    def retarget() -> None:
        link.unlink()
        link.symlink_to("target-b")

    def restore_link() -> None:
        link.unlink()
        link.symlink_to("target-a")

    index_bytes = index.read_bytes()
    return {
        "policy": rewrite(policy),
        "db": rewrite(db),
        "key": rewrite(key),
        "marker": rewrite(marker),
        "directory": (added.mkdir, added.rmdir),
        "symlink": (retarget, restore_link),
        "host_config": rewrite(config),
        "ledger": rewrite(ledger),
        "git_index": (
            lambda: _git("update-index", "--chmod=+x", "tracked.txt", cwd=root),
            lambda: index.write_bytes(index_bytes),
        ),
    }


@pytest.mark.parametrize(
    "component",
    [
        pytest.param("policy", id="policy"),
        pytest.param("db", id="db"),
        pytest.param("key", id="key"),
        pytest.param("marker", id="marker"),
        pytest.param("directory", id="directory"),
        pytest.param("symlink", id="symlink", marks=pytest.mark.posix_only),
        pytest.param("host_config", id="host_config"),
        pytest.param("ledger", id="ledger"),
        pytest.param("git_index", id="git_index"),
    ],
)
def test_consent_preservation_oracle_self_check(
    component: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G3 (preservation oracle drops evidence): mutating any one captured component
    (policy bytes, DB bytes, key, marker, directory membership, symlink target, host
    config, ledger, `.git/index` bytes) changes the `_c_state` snapshot, and restoring
    it brings the snapshot back; then a real consent preview over the same fixture
    leaves that snapshot identical."""
    import rush.memory.authorization as auth

    home = Path(os.environ["HOME"])
    data_root = _c_data_root()
    root = _c_project(tmp_path)
    store = _c_write_rows(root, [("k1", "src-a", None)])
    _grant(
        auth,
        root,
        legacy_owner_scope(root),
        data_root,
        sources=("src-a",),
        ops=("list",),
        expected=0,
    )
    key = data_root / "user" / ".rush" / "memory_store.key"
    key.parent.mkdir(parents=True, exist_ok=True)
    key.write_bytes(b"k" * 32)
    marker = root / ".rush" / "memory-policy.required"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_bytes(b'{"mode": "required"}')
    (home / ".codex").mkdir(parents=True, exist_ok=True)
    (home / ".codex" / "config.toml").write_text("model = 'x'\n", encoding="utf-8")
    (home / "agent-ledger.json").write_text("{}", encoding="utf-8")
    if component == "symlink":
        (root / "link").symlink_to("target-a")
    (root / "tracked.txt").write_text("tracked\n", encoding="utf-8")
    _git("init", cwd=root)
    _git("add", "tracked.txt", cwd=root)
    listed = subprocess.run(
        ["git", "ls-files"], cwd=root, check=True, capture_output=True, text=True
    )
    assert listed.stdout.split() == ["tracked.txt"], listed

    before = _c_state(root)
    mutate, restore = _c_oracle_mutations(root, store, home, data_root)[component]
    mutate()
    assert _c_state(root) != before, component
    restore()
    assert _c_state(root) == before, component

    _c_run(
        _c_preview_args(
            root, "--source", "src-a", revision=str(_c_policy()["policy_revision"])
        ),
        code="OK",
    )
    assert _c_state(root) == before
