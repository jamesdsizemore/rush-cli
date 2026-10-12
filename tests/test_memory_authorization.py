"""73-T02/POLICY: the memory authorization policy (`rush.memory.authorization`).

Every test imports `rush.memory.authorization` inside its own body so each one
fails on its own until the module exists. The module-level imports below are
existing code only.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
        result = _resolve(auth, bad, d)
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
