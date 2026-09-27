"""Phase 70 T7 fix round 1: setup-provisioned aislop is the engine slop runs,
a reused aislop still gets its npm runtime, prefetch failures stay per-engine,
and aislop never phones home."""

from __future__ import annotations

import dataclasses
import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest

from rush.permissions import ExecutionPermissions
from rush.setup.provision import (
    ProvisionError,
    build_provision_plan,
    prefetch_npm_runtime,
    resolve_and_apply_provision_plan,
)
from tests.test_phase70_t26 import (
    _FAKE_RUSH_BINARY,
    _AnswerByPrompt,
    _fake_claude_runner,
    _fake_host_which,
)
from tests.test_phase70_t26 import (
    warm_npm_cache as _shared_warm_npm_cache,
)

# The session fixture shared with t26: one warm npm cache per session.
warm_npm_cache = _shared_warm_npm_cache

_AISLOP_REPORT = (
    '{"diagnostics": [{"filePath": "mod.py", "line": 1, "engine": "ai-slop",'
    ' "rule": "narrative-comment", "severity": "warning", "message": "slop"}]}'
)


def _aislop_pypi(url: str) -> bytes:
    return json.dumps(
        {
            "info": {"version": "0.16.1"},
            "releases": {
                "0.16.1": [
                    {
                        "packagetype": "bdist_wheel",
                        "url": "u",
                        "digests": {"sha256": "a"},
                    }
                ]
            },
        }
    ).encode()


def _fake_aislop_runner(
    calls: list[tuple[list[str], dict[str, str] | None]], cached: dict[str, bool]
):
    def runner(
        argv: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        calls.append((argv, env))
        if argv[:3] == ["uv", "tool", "install"]:
            assert env is not None
            exe = Path(env["UV_TOOL_BIN_DIR"]) / "aislop"
            exe.write_text(f"#!/bin/sh\nprintf '%s' '{_AISLOP_REPORT}'\n")
            exe.chmod(0o755)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        offline = (env or {}).get("npm_config_offline")
        if offline == "false":
            cached["npm"] = True
        ok = offline == "false" or cached["npm"]
        return subprocess.CompletedProcess(
            argv, 0 if ok else 1, stdout="", stderr="" if ok else "ENOTCACHED"
        )

    return runner


def _provision_aislop(
    project: Path,
    data_root: Path,
    runner,
    platform: tuple[str, str] = ("linux", "x86_64"),
):
    plan = build_provision_plan(
        project,
        ["aislop"],
        os_name=platform[0],
        arch=platform[1],
        data_root=data_root,
        runner=runner,
    )
    return resolve_and_apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True, build=True),
        project_id="proj-a",
        current_platform=platform,
        data_root=data_root,
        http_get=_aislop_pypi,
        runner=runner,
        prober=lambda argv: subprocess.CompletedProcess(
            argv, 0, stdout="0.16.1", stderr=""
        ),
        which=lambda name: f"/usr/bin/{name}",
    )


def test_slop_runs_setup_provisioned_aislop_not_on_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """aislop provisioned only through a setup manifest (not on PATH, not in
    the Rush venv) is the engine `rush slop` runs."""
    from rush.runtime.binaries import clear_binary_cache
    from rush.tools import common
    from rush.tools.slop import SlopTool

    project = tmp_path / "proj"
    project.mkdir()
    (project / "mod.py").write_text("x = 1\n")
    result = _provision_aislop(
        project, tmp_path / "data", _fake_aislop_runner([], {"npm": False})
    )
    assert "aislop" in result.applied, result.failed

    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))
    monkeypatch.setattr(common, "_venv_scripts_dir", lambda: None)
    clear_binary_cache()
    try:
        slop = SlopTool().run(project)
    finally:
        clear_binary_cache()

    assert slop["engine"] == "aislop", slop["summary"]
    assert slop["status"] == "warn", slop["summary"]
    assert [f["rule"] for f in slop["findings"]] == ["aislop/ai-slop/narrative-comment"]


def test_reused_aislop_with_cold_npm_cache_fetches_its_runtime(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "data"
    first = _provision_aislop(
        project, data_root, _fake_aislop_runner([], {"npm": False})
    )
    assert "aislop" in first.applied, first.failed

    calls: list[tuple[list[str], dict[str, str] | None]] = []
    second = _provision_aislop(
        project, data_root, _fake_aislop_runner(calls, {"npm": False})
    )

    assert "aislop" in second.reused, second.failed
    # The plan's offline probe, then apply's offline check, the granted
    # online fetch, and the offline verification.
    assert [
        ((env or {}).get("npm_config_offline"), argv[1:]) for argv, env in calls
    ] == [
        ("true", ["--version"]),
        ("true", ["--version"]),
        ("false", ["--version"]),
        ("true", ["--version"]),
    ]


_FETCH_FLAGS = ["--allow-network", "--allow-download", "--allow-cache-write"]


def _offline_modes(calls: list[tuple[list[str], dict[str, str] | None]]) -> list:
    return [(env or {}).get("npm_config_offline") for _, env in calls]


def test_reused_aislop_with_cold_cache_plans_fetch_grants_and_never_fetches_without(
    tmp_path: Path,
) -> None:
    """A reused aislop whose npm runtime is not usable offline lists the
    fetch grants in the plan; with no grant, apply fetches nothing and
    reports the engine as needing them."""
    from rush.setup.provision import apply_provision_plan

    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "data"
    first = _provision_aislop(
        project, data_root, _fake_aislop_runner([], {"npm": False})
    )
    assert "aislop" in first.applied, first.failed

    calls: list[tuple[list[str], dict[str, str] | None]] = []
    runner = _fake_aislop_runner(calls, {"npm": False})
    plan = build_provision_plan(
        project,
        ["aislop"],
        os_name="linux",
        arch="x86_64",
        data_root=data_root,
        runner=runner,
    )
    (entry,) = plan.entries
    assert entry.identity_state == "reuse_verified"
    assert entry.required_grants == ("network", "download", "cache_write")

    result = apply_provision_plan(
        plan,
        ExecutionPermissions(),
        project_id="proj-a",
        data_root=data_root,
        reviewed_plan_id=plan.plan_id,
        runner=runner,
        current_platform=("linux", "x86_64"),
    )
    assert result.permission_blocked == {"aislop": _FETCH_FLAGS}
    assert "aislop" not in result.reused
    assert _offline_modes(calls) == ["true"]


def test_reused_aislop_cache_cold_after_review_is_not_fetched_without_grant(
    tmp_path: Path,
) -> None:
    """Cache warm at review, cold at apply, no grant: no online run; the
    engine is reported as needing the fetch grants."""
    from rush.setup.provision import apply_provision_plan

    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "data"
    first = _provision_aislop(
        project, data_root, _fake_aislop_runner([], {"npm": False})
    )
    assert "aislop" in first.applied, first.failed

    plan = build_provision_plan(
        project,
        ["aislop"],
        os_name="linux",
        arch="x86_64",
        data_root=data_root,
        runner=_fake_aislop_runner([], {"npm": True}),
    )
    assert plan.entries[0].required_grants == ()

    calls: list[tuple[list[str], dict[str, str] | None]] = []
    result = apply_provision_plan(
        plan,
        ExecutionPermissions(),
        project_id="proj-a",
        data_root=data_root,
        reviewed_plan_id=plan.plan_id,
        runner=_fake_aislop_runner(calls, {"npm": False}),
        current_platform=("linux", "x86_64"),
    )
    assert result.permission_blocked == {"aislop": _FETCH_FLAGS}
    assert "aislop" not in result.reused
    assert _offline_modes(calls) == ["true"]


def test_setup_review_lists_fetch_grants_for_reused_aislop_with_cold_cache(
    tmp_path: Path,
) -> None:
    """The real setup review probes the reused aislop offline (a real
    subprocess, no network) and lists the fetch grants; without them setup
    applies nothing."""
    from rush.setup.provision import current_os_arch
    from rush.tools.setup_wizard import (
        apply_setup_review,
        build_setup_review,
        render_setup_review,
    )

    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text('[project]\nname = "p"\n')
    data_root = tmp_path / "data"
    warm = tmp_path / "npm-cache-warm"

    def runner(
        argv: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if argv[:3] == ["uv", "tool", "install"]:
            assert env is not None
            exe = Path(env["UV_TOOL_BIN_DIR"]) / "aislop"
            # A real offline run succeeds only while the cache is warm.
            exe.write_text(
                "#!/bin/sh\n"
                f'if [ "$npm_config_offline" = true ] && [ ! -f "{warm}" ]; '
                "then exit 1; fi\n"
            )
            exe.chmod(0o755)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if (env or {}).get("npm_config_offline") == "false":
            warm.touch()
        ok = warm.exists()
        return subprocess.CompletedProcess(argv, 0 if ok else 1, "", "")

    first = _provision_aislop(project, data_root, runner, current_os_arch())
    assert "aislop" in first.applied, first.failed
    warm.unlink()  # the npm cache goes cold

    review = build_setup_review(project, data_root)
    (entry,) = [e for e in review["provision"]["entries"] if e["engine_id"] == "aislop"]
    assert entry["identity_state"] == "reuse_verified"
    assert list(entry["required_grants"]) == ["network", "download", "cache_write"]
    assert "--allow-download" in render_setup_review(review)

    result = apply_setup_review(review, ExecutionPermissions(), None)
    assert result["status"] == "permission_denied", result
    assert result["missing"]["engine:aislop"] == _FETCH_FLAGS


@pytest.mark.parametrize(
    "error",
    [OSError("npx vanished"), subprocess.TimeoutExpired(["aislop"], 600)],
    ids=["oserror", "timeout"],
)
def test_prefetch_npm_runtime_runner_failure_is_a_provision_error(
    tmp_path: Path, error: Exception
) -> None:
    def runner(argv, env=None):
        raise error

    with pytest.raises(ProvisionError) as caught:
        prefetch_npm_runtime("aislop", tmp_path / "aislop", runner)
    assert caught.value.code == "SYSTEM_PREREQUISITE_REQUIRED"


def test_prefetch_runner_failure_does_not_abort_other_engines(tmp_path: Path) -> None:
    """One engine's prefetch crash is that engine's failure, not the apply's."""
    project = tmp_path / "proj"
    project.mkdir()
    inner = _fake_aislop_runner([], {"npm": False})

    def runner(argv, env=None):
        if argv[:3] == ["uv", "tool", "install"]:
            return inner(argv, env)
        raise subprocess.TimeoutExpired(argv, 600)

    result = _provision_aislop(project, tmp_path / "data", runner)
    assert result.failed["aislop"]["code"] == "SYSTEM_PREREQUISITE_REQUIRED"


def test_prefetch_npm_runtime_disables_aislop_telemetry(tmp_path: Path) -> None:
    envs: list[dict[str, str] | None] = []

    def runner(argv, env=None):
        envs.append(env)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    assert prefetch_npm_runtime("aislop", tmp_path / "aislop", runner) == (
        "already_cached"
    )
    assert envs
    for env in envs:
        assert env is not None
        assert env["AISLOP_NO_TELEMETRY"] == "1"
        assert env["DO_NOT_TRACK"] == "1"


def test_aislop_without_node_on_path_is_not_installed_not_an_engine_error(
    tmp_path: Path,
) -> None:
    """aislop's pip shim exits 127 when Node.js/npx is absent from PATH (the
    project journey's hermetic PATH): a missing runtime, never `error`."""
    from rush.engines.aislop import AislopEngine

    result = AislopEngine().normalize(
        {
            "exit_code": 127,
            "stdout": "",
            "stderr": "aislop for Python requires Node.js tooling on PATH.\n",
            "parsed": None,
            "findings": [],
            "summary": "aislop exit 127",
            "duration_ms": 0,
            "cwd": str(tmp_path),
        },
        tmp_path,
        "slop",
    )

    assert result["status"] == "skipped", result["summary"]
    assert "not on PATH" in result["summary"]
    assert "Node.js" in result["summary"]


@pytest.mark.parametrize("download", [True, False], ids=["granted", "ungranted"])
def test_aislop_child_env_disables_telemetry_and_is_offline_without_grant(
    download: bool,
) -> None:
    from rush.engines.aislop import AislopEngine, aislop_grants

    with aislop_grants(ExecutionPermissions(download=download)):
        env = AislopEngine().child_env()

    assert env is not None
    assert env["AISLOP_NO_TELEMETRY"] == "1"
    assert env["DO_NOT_TRACK"] == "1"
    if download:
        assert "npm_config_offline" not in env
    else:
        assert env["npm_config_offline"] == "true"


# --- Items 2, 5, 6: setup's host check and hooks stages ----------------------

_HOST_PERMISSIONS = ExecutionPermissions(
    network=True, download=True, cache_write=True, artifact_write=True, build=True
)
_PROBE_FILES = [".rush-probe-owner.json", "probe.py", "pyproject.toml", "test_probe.py"]


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HOME in a temp dir, so no host config or data root is the real one."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    return home


def _host_review(
    root: Path, data_root: Path, *, run_check: bool = False, hooks: bool = False
) -> dict[str, Any]:
    from rush.tools.setup_wizard import build_setup_review

    return build_setup_review(
        root,
        data_root,
        host="claude",
        permissions=_HOST_PERMISSIONS,
        which=_fake_host_which,
        rush_binary=_FAKE_RUSH_BINARY,
        run_check=run_check,
        enable_hooks=hooks,
    )


def _apply(
    review: dict[str, Any],
    home: Path,
    permissions: ExecutionPermissions,
    choices: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Interactive ("y" to all but the probe) or, with ``choices``,
    non-interactive under exactly ``permissions``."""
    from rush.tools.setup_wizard import apply_setup_review

    return apply_setup_review(
        {"kind": "setup", "schema_version": 1, "review": review},
        permissions,
        None if choices is not None else _AnswerByPrompt(("Verify the connection",)),
        host_runner=_fake_claude_runner(home, []),
        choices=choices,
    )


def test_setup_check_grants_are_build_and_cache_write_and_required(
    tmp_path: Path, isolated_home: Path
) -> None:
    from rush.tools.setup_wizard import HOST_STAGE_GRANTS

    assert HOST_STAGE_GRANTS["check"] == ("build", "cache_write")
    root = tmp_path / "project"
    root.mkdir()
    review = _host_review(root, tmp_path / "data", run_check=True)
    assert tuple(review["grants"]["check"]) == ("build", "cache_write")
    no_build = dataclasses.replace(_HOST_PERMISSIONS, build=False)
    result = _apply(review, isolated_home, no_build, {"check": True})
    assert result["status"] == "permission_denied", result
    assert set(result["missing"]) == {"check"}


def test_setup_check_runs_on_rush_owned_fixture_outside_lock_never_user_root(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.tools.check import CheckTool

    root = tmp_path / "project"
    root.mkdir()
    review = _host_review(root, tmp_path / "data", run_check=True)
    probes = Path(review["data_root"]) / "probes"
    fixture_command = f"rush check {shlex.quote(str(probes / '<nonce>'))} --json"
    assert review["check"]["command"] == fixture_command

    seen: dict[str, Any] = {}

    def fake_run(self: object, path: Path, **kwargs: Any) -> dict[str, Any]:
        path = Path(path)
        seen["path"] = path
        seen["files"] = sorted(p.name for p in path.iterdir())
        seen["probe"] = (path / "probe.py").read_text()
        seen["marker"] = json.loads((path / ".rush-probe-owner.json").read_text())
        seen["kwargs"] = kwargs
        seen["cancelled_now"] = kwargs["cancel_check"]()
        seen["locked"] = (root / ".rush" / "setup.lock").exists()
        return {
            "status": "fail",
            "summary": "1 finding",
            "findings": [{"rule": "F401"}],
            "metadata": {"children": []},
        }

    monkeypatch.setattr(CheckTool, "run", fake_run)
    result = _apply(review, isolated_home, _HOST_PERMISSIONS)

    check = result["raw"]["check"]
    assert check["state"] == "ran", check
    assert result["status"] == "ok", result
    assert seen["path"].parent == probes
    assert seen["path"] != root.resolve() and root.resolve() not in seen["path"].parents
    assert seen["files"] == _PROBE_FILES
    assert seen["probe"] == "import os\n"
    assert seen["marker"]["nonce"] == seen["path"].name
    assert seen["kwargs"]["permissions"] == ExecutionPermissions(build=True)
    assert seen["kwargs"]["invocation_start_cwd"] == seen["path"]
    assert seen["kwargs"]["cancel_cause"] == "setup_check_deadline"
    assert seen["cancelled_now"] is False
    assert seen["locked"] is False
    assert check["fixture"] == str(seen["path"])
    assert check["fixture_removed"] is True
    assert not seen["path"].exists()
    assert check["finding_rules"] == ["F401"]
    assert check["command"] == fixture_command


def test_setup_check_deadline_cancels_the_check(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.tools import setup_wizard
    from rush.tools.check import CheckTool

    monkeypatch.setattr(setup_wizard, "_CHECK_DEADLINE_SECONDS", 0.0)
    cancelled: list[bool] = []

    def fake_run(self: object, path: Path, **kwargs: Any) -> dict[str, Any]:
        cancelled.append(kwargs["cancel_check"]())
        return {"status": "error", "findings": [], "metadata": {"children": []}}

    monkeypatch.setattr(CheckTool, "run", fake_run)
    root = tmp_path / "project"
    root.mkdir()
    _apply(
        _host_review(root, tmp_path / "data", run_check=True),
        isolated_home,
        _HOST_PERMISSIONS,
    )
    assert cancelled == [True]


def test_probe_fixture_is_removed_only_while_its_marker_matches(
    tmp_path: Path,
) -> None:
    from rush.tools.setup_wizard import _create_probe_fixture, _remove_probe_fixture

    fixture, nonce = _create_probe_fixture(tmp_path)
    assert fixture.parent == tmp_path / "probes"
    assert sorted(p.name for p in fixture.iterdir()) == _PROBE_FILES
    (fixture / ".rush-probe-owner.json").write_text(json.dumps({"nonce": "other"}))
    assert _remove_probe_fixture(fixture, nonce) is False
    assert fixture.exists()
    (fixture / ".rush-probe-owner.json").unlink()
    assert _remove_probe_fixture(fixture, nonce) is False
    assert fixture.exists()

    owned, owned_nonce = _create_probe_fixture(tmp_path)
    assert owned != fixture
    assert _remove_probe_fixture(owned, owned_nonce) is True
    assert not owned.exists()


def test_setup_hooks_oserror_is_partial_with_blocker_and_one_recovery(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.tools import setup_wizard

    def broken(*args: object, **kwargs: object) -> dict[str, Any]:
        raise OSError("No space left on device")

    monkeypatch.setattr(setup_wizard, "set_hook_activation", broken)
    root = tmp_path / "project"
    root.mkdir()
    review = _host_review(root, tmp_path / "data", hooks=True)
    result = _apply(review, isolated_home, _HOST_PERMISSIONS)

    assert (result["status"], result["reason"]) == ("partial", "hooks_failed")
    hooks = result["raw"]["hooks"]
    assert hooks["state"] == "failed"
    assert hooks["blocker"] == "hook_activation_failed"
    assert "No space left on device" in hooks["detail"]
    assert hooks["recovery_actions"] == [
        f"{review['resume_command']} --enable-agent-hooks"
    ]


@pytest.mark.parametrize("reason", ["not_owned", "unreadable", "cas_conflict"])
def test_setup_hooks_conflict_is_partial_with_blocker_and_one_recovery(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    """Round-2 M3: a hooks stage `conflict` (foreign, unreadable or CAS-raced
    activation ledger) leaves the hook inactive, so setup is partial with a
    blocker and one recovery command, never ok."""
    from rush.tools import setup_wizard

    def conflicted(*args: object, **kwargs: object) -> dict[str, Any]:
        return {"state": "conflict", "conflict": reason}

    monkeypatch.setattr(setup_wizard, "set_hook_activation", conflicted)
    root = tmp_path / "project"
    root.mkdir()
    review = _host_review(root, tmp_path / "data", hooks=True)
    result = _apply(review, isolated_home, _HOST_PERMISSIONS)

    assert (result["status"], result["reason"]) == ("partial", "hooks_conflict")
    hooks = result["raw"]["hooks"]
    assert hooks["state"] == "conflict"
    assert hooks["conflict"] == reason
    assert hooks["blocker"] == "hook_activation_conflict"
    assert hooks["recovery_actions"] == [
        f"{review['resume_command']} --enable-agent-hooks"
    ]


def test_setup_check_crash_is_partial_with_blocker_and_one_recovery(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.tools.check import CheckTool

    def crash(self: object, path: Path, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("engine exploded")

    monkeypatch.setattr(CheckTool, "run", crash)
    root = tmp_path / "project"
    root.mkdir()
    review = _host_review(root, tmp_path / "data", run_check=True)
    result = _apply(review, isolated_home, _HOST_PERMISSIONS)

    assert (result["status"], result["reason"]) == ("partial", "check_failed")
    check = result["raw"]["check"]
    assert check["state"] == "failed"
    assert check["blocker"] == "check_crashed"
    assert "RuntimeError: engine exploded" in check["detail"]
    assert check["recovery_actions"] == [f"{review['resume_command']} --run-check"]
    assert check["fixture_removed"] is True
    assert list((Path(review["data_root"]) / "probes").iterdir()) == []


def test_setup_hooks_stage_grants_match_agent_connect() -> None:
    from rush.tools.agent_connection import _CONNECT_PERMISSION
    from rush.tools.setup_wizard import HOST_STAGE_GRANTS

    connect = tuple(k for k, v in _CONNECT_PERMISSION.to_dict().items() if v)
    assert HOST_STAGE_GRANTS["hooks"] == connect == ("cache_write", "artifact_write")


def test_setup_hooks_need_artifact_write_and_store_recovery_from_the_grant(
    tmp_path: Path, isolated_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.integrations.agent_hooks import activation_record_path
    from rush.tools import setup_wizard

    root = tmp_path / "project"
    root.mkdir()
    data_root = tmp_path / "data"
    review = _host_review(root, data_root, hooks=True)
    assert review["hooks"]["activation"]["recovery_cache_write"] is True

    no_artifact = dataclasses.replace(_HOST_PERMISSIONS, artifact_write=False)
    denied = _apply(review, isolated_home, no_artifact, {"hooks": True})
    assert denied["status"] == "permission_denied", denied
    assert "hooks" in denied["missing"]

    calls: list[dict[str, Any]] = []
    real = setup_wizard.set_hook_activation

    def spy(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(setup_wizard, "set_hook_activation", spy)
    result = _apply(review, isolated_home, _HOST_PERMISSIONS)
    assert result["raw"]["hooks"]["state"] == "applied", result["raw"]["hooks"]
    assert [c["recovery_cache_write"] for c in calls] == [True]
    records = json.loads(activation_record_path(data_root).read_text())["activations"]
    assert [r["recovery_cache_write"] for r in records] == [True]


def _bind_setup_engines(root: Path, data_root: Path) -> None:
    """What setup's engine stage leaves behind: a verified manifest per
    engine, scoped to ``root`` under ``data_root``'s toolchains, and the
    project's `.rush/toolchains.json` selection naming them."""
    from rush.runtime.binaries import (
        MANIFEST_SCHEMA_VERSION,
        ProvisionManifest,
        compute_file_sha256,
        write_manifest,
    )
    from rush.setup.provision import current_os_arch
    from rush.tools.common import clear_binary_cache, resolve_binary

    os_name, arch = current_os_arch()
    selection: dict[str, dict[str, str]] = {}
    clear_binary_cache()
    for engine_id in ("ruff", "mypy", "vulture", "aislop", "pytest"):
        executable = resolve_binary(engine_id)
        assert executable is not None, engine_id
        manifest = ProvisionManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            engine_id=engine_id,
            package_id=engine_id,
            version="0",
            source="pypi",
            manager="uv",
            executable=executable,
            executable_sha256=compute_file_sha256(executable),
            os_name=os_name,
            arch=arch,
            project_id="proj",
            project_root=str(root.resolve()),
            runtime_identity="",
            plan_id="",
            created_at="",
        )
        dest = data_root / "toolchains" / engine_id / "0" / f"{os_name}-{arch}"
        selection[engine_id] = {"manifest": str(write_manifest(dest, manifest))}
    clear_binary_cache()
    (root / ".rush").mkdir()
    (root / ".rush" / "toolchains.json").write_text(json.dumps(selection))


def test_setup_check_runs_the_engines_setup_provisioned_for_the_project(
    tmp_path: Path,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    warm_npm_cache: str,
) -> None:
    """The fixture check resolves engines from the project's setup-written
    toolchains manifests: with no engine on PATH and the Rush venv's bin
    excluded, every one of the six steps still executes."""
    import shutil

    from rush.runtime import binaries
    from rush.tools import common
    from rush.tools.common import clear_binary_cache

    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "x"\nversion = "0.0.1"\n')
    data_root = tmp_path / "data"
    _bind_setup_engines(root, data_root)
    review = _host_review(root, data_root, run_check=True)

    # PATH holds only node/npx (aislop's own runtime) and /bin (sh), no engine.
    node_bin = tmp_path / "node-bin"
    node_bin.mkdir()
    for name in ("node", "npx"):
        found = shutil.which(name)
        assert found is not None, name
        (node_bin / name).symlink_to(found)
    monkeypatch.setenv("PATH", os.pathsep.join([str(node_bin), "/bin"]))
    monkeypatch.setattr(common, "_venv_scripts_dir", lambda: None)
    monkeypatch.setattr(binaries, "_venv_scripts_dir", lambda: None, raising=False)
    monkeypatch.setenv("npm_config_cache", warm_npm_cache)
    monkeypatch.delenv("npm_config_offline", raising=False)
    clear_binary_cache()
    try:
        result = _apply(review, isolated_home, _HOST_PERMISSIONS, {"check": True})
    finally:
        clear_binary_cache()

    check = result.get("raw", result)["check"]
    assert check["state"] == "ran", check
    steps = {step["tool"]: step for step in check["steps"]}
    assert list(steps) == ["format", "lint", "typecheck", "dead", "slop", "test"]
    assert all(s["disposition"] == "executed" for s in steps.values()), steps
    assert not any(s["status"] == "skipped" for s in steps.values()), steps
    assert "F401" in check["finding_rules"]


def test_every_ci_job_with_aislop_warms_its_npm_runtime_after_sync() -> None:
    """Item 9: every job that syncs the dev extra (which installs aislop)
    warms aislop's npm runtime into a runner-temp cache exported to later
    steps, so tests, including ones with a temp HOME, run aislop offline, and
    no job deselects the aislop tests."""
    from ruamel.yaml import YAML

    workflow = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"
    jobs = YAML(typ="safe").load(workflow.read_text(encoding="utf-8"))["jobs"]
    synced = []
    for name, job in jobs.items():
        runs = [str(step.get("run", "")) for step in job.get("steps", [])]
        sync = [i for i, run in enumerate(runs) if "uv sync --all-extras" in run]
        if not sync:
            continue
        synced.append(name)
        warm = [
            i
            for i, run in enumerate(runs)
            if "npm_config_cache=$RUNNER_TEMP/" in run
            and '>> "$GITHUB_ENV"' in run
            and 'npm exec --yes --package "aislop@$version" -- aislop --version' in run
            and "import aislop_py; print(aislop_py.__version__)" in run
        ]
        assert warm and warm[0] > sync[0], name
        step = job["steps"][warm[0]]
        assert step.get("shell") == "bash", name
        assert step["env"] == {"AISLOP_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
        assert not any("needs_aislop" in run for run in runs), name
    assert len(synced) == 5, synced


def test_setup_result_renders_permission_blocked_engine_with_one_recovery() -> None:
    """Round-2 M1: a reused engine blocked on its fetch grants is shown with
    the missing grants and one exact recovery command naming them."""
    from rush.tools.setup_wizard import render_setup_result

    text = render_setup_result(
        {
            "status": "partial",
            "resume_command": "rush setup /p --agent claude",
            "provision": {"permission_blocked": {"aislop": list(_FETCH_FLAGS)}},
        }
    )
    assert (
        "engine aislop needs --allow-network --allow-download --allow-cache-write"
    ) in text
    assert (
        "recover: rush setup /p --agent claude "
        "--allow-network --allow-download --allow-cache-write"
    ) in text
    assert "--allow---" not in text
    assert text.count("rush setup /p --agent claude") == 1, text


def test_run_setup_wizard_passes_its_runner_to_the_provision_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Final review: the caller's runner reaches `build_provision_plan`, so a
    reused engine is verified with the same runner that applies the plan."""
    from rush.tools import setup_wizard

    seen: dict[str, Any] = {}
    real = setup_wizard.build_provision_plan

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        return real(*args, **kwargs)

    def runner(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("plan building runs nothing here")

    monkeypatch.setattr(setup_wizard, "build_provision_plan", spy)
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "p"\n')
    setup_wizard.run_setup_wizard(
        root, install=True, data_root=tmp_path / "data", runner=runner
    )
    assert seen["runner"] is runner


def test_legacy_provision_permission_blocked_renders_one_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fix-round review: a provision-only payload whose engine is blocked on
    grants carries the resume command, so the rendering names one exact
    recovery command with the missing grants."""
    from types import SimpleNamespace

    from rush.setup.provision import build_provision_plan, plan_to_dict
    from rush.tools import setup_wizard

    root = tmp_path / "project"
    root.mkdir()
    plan = build_provision_plan(root, [], data_root=tmp_path / "data")
    outcome = SimpleNamespace(
        plan_id=plan.plan_id,
        identity_source="reviewed",
        applied={},
        reused={},
        failed={},
        permission_blocked={"aislop": list(_FETCH_FLAGS)},
        requires_input={},
        recovery_required={},
    )
    monkeypatch.setattr(setup_wizard, "_registered_project_id", lambda *a: "p1")
    monkeypatch.setattr(setup_wizard, "apply_provision_plan", lambda *a, **k: outcome)
    envelope = {
        "kind": "provision",
        "schema_version": 1,
        "review": {"provision": plan_to_dict(plan)},
    }
    result = setup_wizard.apply_setup_review(envelope, None, None)
    assert result["status"] == "partial", result
    resume = setup_wizard.setup_resume_command(root)
    assert result["resume_command"] == resume
    text = setup_wizard.render_setup_result(result)
    assert f"recover: {resume} {' '.join(_FETCH_FLAGS)}" in text
    assert text.count(resume) == 1, text
