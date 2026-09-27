"""Phase 70 T7 fix round 1: setup-provisioned aislop is the engine slop runs,
a reused aislop still gets its npm runtime, prefetch failures stay per-engine,
and aislop never phones home."""

from __future__ import annotations

import dataclasses
import json
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


def _provision_aislop(project: Path, data_root: Path, runner):
    plan = build_provision_plan(
        project, ["aislop"], os_name="linux", arch="x86_64", data_root=data_root
    )
    return resolve_and_apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True, build=True),
        project_id="proj-a",
        current_platform=("linux", "x86_64"),
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
    assert [
        ((env or {}).get("npm_config_offline"), argv[1:]) for argv, env in calls
    ] == [
        ("true", ["--version"]),
        ("false", ["--version"]),
        ("true", ["--version"]),
    ]


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
            and "uv run --no-sync aislop --version" in run
        ]
        assert warm and warm[0] > sync[0], name
        step = job["steps"][warm[0]]
        assert step.get("shell") == "bash", name
        assert step["env"] == {"AISLOP_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
        assert not any("needs_aislop" in run for run in runs), name
    assert len(synced) == 5, synced
