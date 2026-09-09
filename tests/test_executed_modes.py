"""Phase 07.B Executed modes contract tests across advanced evidence tools."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from rush.permissions import ExecutionPermissions
from rush.tools.codeql import CodeqlTool
from rush.tools.contract import ContractTool
from rush.tools.coverage import CoverageTool
from rush.tools.flaky import FlakyTool
from rush.tools.fuzz import FuzzTool
from rush.tools.load import LoadTool
from rush.tools.mutation import MutationTool
from rush.tools.pbt import PbtTool
from rush.tools.snapshot import SnapshotTool


def test_coverage_executed_mode_requires_slow_permission(tmp_path: Path) -> None:
    tool = CoverageTool()
    # Default denial
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-slow" in res_denied["summary"]
    assert res_denied["metadata"]["execution"]["mode"] == "executed"
    assert res_denied["metadata"]["execution"]["requested_permissions"]["slow"] is True

    # With permission granted
    perms = ExecutionPermissions(slow=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"
    assert res_granted["metadata"]["execution"]["granted_permissions"]["slow"] is True


def test_contract_executed_mode_requires_slow_permission(tmp_path: Path) -> None:
    tool = ContractTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-slow" in res_denied["summary"]

    perms = ExecutionPermissions(slow=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"


def test_mutation_executed_mode_requires_slow_permission(tmp_path: Path) -> None:
    tool = MutationTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-slow" in res_denied["summary"]

    perms = ExecutionPermissions(slow=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"


@pytest.mark.parametrize("entrypoint", ["config", "mcp-config", "mcp-explicit"])
def test_mutation_executes_tests_and_counts_survivors(
    monkeypatch, tmp_path: Path, entrypoint: str
) -> None:
    source = tmp_path / "src" / "calculator.py"
    test_file = tmp_path / "tests" / "test_calculator.py"
    source.parent.mkdir()
    test_file.parent.mkdir()
    source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    test_file.write_text(
        "from calculator import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
        encoding="utf-8",
    )

    import rush.tools.mutation as mutation_mod

    monkeypatch.setattr(mutation_mod, "engine_on_path", lambda name: name == "mutmut")
    originals = {p: p.read_bytes() for p in (source, test_file)}
    calls = []

    def fake_run(argv, *, cwd=None, timeout=120, env=None):
        calls.append(argv)
        assert timeout == 17
        assert Path(cwd) != tmp_path
        for original, content in originals.items():
            assert (Path(cwd) / original.relative_to(tmp_path)).read_bytes() == content
        config = tomllib.loads((Path(cwd) / "pyproject.toml").read_text())
        assert config["tool"]["mutmut"]["source_paths"] == ["src"]
        assert config["tool"]["mutmut"]["pytest_add_cli_args_test_selection"] == [
            "tests"
        ]
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(
                argv, 0, stdout="mutmut 3.7.0", stderr=""
            )
        if argv[1:] == ["run"]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        if argv[1:2] == ["export-cicd-stats"]:
            report = Path(cwd) / "mutants" / "mutmut-cicd-stats.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                json.dumps(
                    {
                        "total": 2,
                        "killed": 1,
                        "survived": 1,
                        "timeout": 0,
                        "no_tests": 0,
                        "skipped": 0,
                        "suspicious": 0,
                        "segfault": 0,
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr(mutation_mod, "run_subprocess", fake_run)
    options = {"source_paths": ["src"], "test_paths": ["tests"], "timeout_seconds": 17}
    if entrypoint == "config":
        from rush.config import _parse

        config = _parse({"tools": {"mutation": options}}, tmp_path / "rush.toml")
        result = MutationTool().run(
            tmp_path,
            config=config,
            permissions=ExecutionPermissions(
                build=True, slow=True, artifact_write=True
            ),
        )
    else:
        from rush.invocation import InvocationExecutor
        from rush.mcp_support.tool_registry import make_tool_wrapper

        if entrypoint == "mcp-config":
            (tmp_path / "rush.toml").write_text(
                '[tools.mutation]\nsource_paths = ["src"]\ntest_paths = ["tests"]\ntimeout_seconds = 17\n'
            )
            options = {}
        tool = MutationTool()
        executor = InvocationExecutor()
        executor.register(tool.name, tool.__call__)
        result = make_tool_wrapper(tool, executor)(
            tmp_path,
            allow_build=True,
            allow_slow=True,
            allow_artifact_write=True,
            **options,
        )

    assert result["status"] == "fail"
    assert result["engine_version"] == "3.7.0"
    assert result["metrics"] == {
        "generated": 2,
        "killed": 1,
        "survived": 1,
        "timeout": 0,
        "untested": 0,
        "incompetent": 0,
    }
    assert result["duration_ms"] > 0
    assert result["artifacts"]
    assert Path(result["artifacts"][0]).is_file()
    assert calls == [
        ["mutmut", "--version"],
        ["mutmut", "run"],
        ["mutmut", "export-cicd-stats"],
    ]
    assert all(p.read_bytes() == content for p, content in originals.items())


@pytest.mark.parametrize("interrupted", [1, 2, True])
def test_mutation_interrupted_counts_are_cancelled(monkeypatch, tmp_path, interrupted):
    import rush.tools.mutation as mutation_mod

    (tmp_path / "source.py").write_text("def identity(value):\n    return value\n")
    (tmp_path / "test_source.py").write_text(
        "from source import identity\ndef test_identity():\n    assert identity(3) == 3\n"
    )
    monkeypatch.setattr(mutation_mod, "engine_on_path", lambda _: True)

    def fake_run(argv, *, cwd=None, **kwargs):
        if argv[1] == "export-cicd-stats":
            report = Path(cwd) / "mutants" / "mutmut-cicd-stats.json"
            report.parent.mkdir()
            report.write_text(
                json.dumps({"check_was_interrupted_by_user": interrupted})
            )
        return subprocess.CompletedProcess(argv, 0, stdout="mutmut 3.7.0", stderr="")

    monkeypatch.setattr(mutation_mod, "run_subprocess", fake_run)
    result = MutationTool().run(
        tmp_path,
        source_paths=["source.py"],
        test_paths=["test_source.py"],
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"
    assert result["metadata"]["terminal_reason"] == "cancelled"


def test_mutation_rejects_failed_process_and_option_paths(monkeypatch, tmp_path):
    import rush.tools.mutation as mutation_mod

    (tmp_path / "source.py").write_text("def identity(value):\n    return value\n")
    test_path = tmp_path / "-x.py"
    test_path.write_text(
        "from source import identity\ndef test_identity():\n    assert identity(3) == 3\n"
    )
    monkeypatch.setattr(mutation_mod, "engine_on_path", lambda _: True)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, int(argv[1] == "run"), stdout="mutmut 3.7.0", stderr=""
        )

    monkeypatch.setattr(mutation_mod, "run_subprocess", fake_run)
    permissions = ExecutionPermissions(build=True, slow=True, artifact_write=True)
    result = MutationTool().run(
        tmp_path,
        source_paths=["source.py"],
        test_paths=["-x.py"],
        permissions=permissions,
    )
    assert result["status"] == "error"
    assert calls == []
    test_path.rename(tmp_path / "test_source.py")
    result = MutationTool().run(
        tmp_path,
        source_paths=["source.py"],
        test_paths=["test_source.py"],
        permissions=permissions,
    )
    assert result["status"] == "error"
    assert calls == [["mutmut", "--version"], ["mutmut", "run"]]


def _require_real_engine(name: str) -> None:
    if os.environ.get("RUSH_REQUIRE_REAL_ENGINES") == "1":
        assert shutil.which(name), f"required engine absent: {name}"


def test_required_engine_absence_fails(monkeypatch) -> None:
    monkeypatch.setenv("RUSH_REQUIRE_REAL_ENGINES", "1")
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    with pytest.raises(AssertionError, match="required engine absent: mutmut"):
        _require_real_engine("mutmut")


def test_mutation_requires_live_workload_inputs(tmp_path: Path) -> None:
    result = MutationTool().run(
        tmp_path,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "skipped"
    assert result["metadata"]["requires_input"] == "source_paths"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (None, "workload failed"),
        (
            {
                "total": 2,
                "killed": 1,
                "survived": 0,
                "timeout": 0,
                "no_tests": 0,
                "skipped": 0,
                "suspicious": 0,
                "segfault": 0,
            },
            "workload failed",
        ),
    ],
)
def test_mutation_rejects_version_only_and_nonconserving_reports(
    monkeypatch, tmp_path: Path, payload: dict | None, expected: str
) -> None:
    (tmp_path / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (tmp_path / "test_calculator.py").write_text(
        "def test_add():\n    assert True\n", encoding="utf-8"
    )
    import rush.tools.mutation as mutation_mod

    monkeypatch.setattr(mutation_mod, "engine_on_path", lambda _name: True)

    def fake_run(argv, *, cwd=None, **_kwargs):
        if argv[1:] == ["--version"]:
            return subprocess.CompletedProcess(
                argv, 0, stdout="mutmut 3.7.0", stderr=""
            )
        if argv[1:2] == ["export-cicd-stats"] and payload is not None:
            report = Path(cwd) / "mutants" / "mutmut-cicd-stats.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(mutation_mod, "run_subprocess", fake_run)
    result = MutationTool().run(
        tmp_path,
        source_paths=["calculator.py"],
        test_paths=["test_calculator.py"],
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"
    assert expected in result["summary"]


def test_mutation_real_workload(tmp_path: Path) -> None:
    _require_real_engine("mutmut")
    if os.environ.get("RUSH_REQUIRE_REAL_ENGINES") != "1":
        pytest.skip("real mutation engine acceptance disabled")

    source = tmp_path / "calculator.py"
    test_file = tmp_path / "test_calculator.py"
    source.write_text(
        "def add(a, b):\n    return a + b\n\ndef threshold(value):\n    return value > 0\n",
        encoding="utf-8",
    )
    test_file.write_text(
        "from calculator import add, threshold\n\ndef test_add():\n    assert add(1, 2) == 3\n\ndef test_threshold():\n    assert threshold(1)\n",
        encoding="utf-8",
    )
    result = MutationTool().run(
        tmp_path,
        source_paths=["calculator.py"],
        test_paths=["test_calculator.py"],
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "fail"
    metrics = result["metrics"]
    assert metrics["generated"] == sum(
        metrics[name]
        for name in ("killed", "survived", "timeout", "untested", "incompetent")
    )
    assert metrics["killed"] > 0
    assert metrics["survived"] > 0
    assert result["duration_ms"] > 0


def test_pbt_executed_mode_requires_slow_permission(tmp_path: Path) -> None:
    tool = PbtTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-slow" in res_denied["summary"]

    perms = ExecutionPermissions(slow=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"


def test_fuzz_executed_mode_requires_slow_permission(tmp_path: Path) -> None:
    tool = FuzzTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-slow" in res_denied["summary"]

    perms = ExecutionPermissions(slow=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"


def test_fuzz_runs_target_and_reports_reproducer(monkeypatch, tmp_path: Path) -> None:
    harness = tmp_path / "harness.py"
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    seed = corpus / "seed"
    seed.write_bytes(b"RUSH_CRASH")
    original_harness = b"def target(data):\n    return data\n"
    harness.write_bytes(original_harness)

    import rush.tools.fuzz as fuzz_mod

    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)
    calls = []

    def fake_run(argv, *, cwd=None, timeout=120, **_kwargs):
        calls.append((argv, cwd, timeout))
        prefix = next(
            arg.split("=", 1)[1] for arg in argv if arg.startswith("-artifact_prefix=")
        )
        crash = Path(f"{prefix}RUSH_CRASH")
        assert crash.parent.is_dir()
        crash.write_bytes(b"RUSH_CRASH")
        return subprocess.CompletedProcess(
            argv, 77, stdout="", stderr="stat::number_of_executed_units: 3\n"
        )

    monkeypatch.setattr(fuzz_mod, "run_subprocess", fake_run)
    result = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        seed=7,
        max_runs=20,
        timeout_seconds=9,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )

    assert result["status"] == "fail", result
    assert result["metrics"]["crashes"] == 1
    assert result["metrics"]["iterations"] == 3
    assert result["metadata"]["execution"]["mode"] == "executed"
    assert calls[0][0][:2] == [sys.executable, "harness.py"]
    assert calls[0][0][2:7] == [
        "corpus",
        "-seed=7",
        "-runs=20",
        "-max_total_time=9",
        "-print_final_stats=1",
    ]
    assert calls[0][2] == 9
    reproducer = Path(result["artifacts"][0])
    assert reproducer.is_file()
    assert reproducer.read_bytes() == b"RUSH_CRASH"
    assert harness.read_bytes() == original_harness
    assert seed.read_bytes() == b"RUSH_CRASH"


def _write_fuzz_inputs(tmp_path: Path) -> tuple[Path, Path]:
    harness = tmp_path / "harness.py"
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "seed").write_bytes(b"SAFE")
    harness.write_text("print('clean')\n", encoding="utf-8")
    return harness, corpus


def test_fuzz_config_and_explicit_options_reach_argv(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fuzz_inputs(tmp_path)
    import rush.tools.fuzz as fuzz_mod

    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)
    calls = []

    def fake_run(argv, *, cwd=None, timeout=120, **_kwargs):
        calls.append((argv, cwd, timeout))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="",
            stderr="stat::number_of_executed_units: 3\n",
        )

    monkeypatch.setattr(fuzz_mod, "run_subprocess", fake_run)
    permissions = ExecutionPermissions(build=True, slow=True, artifact_write=True)
    direct = FuzzTool().run(
        tmp_path,
        config={
            "options": {
                "harness": "harness.py",
                "corpus": "corpus",
                "seed": 11,
                "max_runs": 12,
                "timeout_seconds": 13,
            }
        },
        permissions=permissions,
    )
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import make_tool_wrapper

    tool = FuzzTool()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    wrapped = make_tool_wrapper(tool, executor)
    explicit = wrapped(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        seed=17,
        max_runs=18,
        timeout_seconds=19,
        allow_build=True,
        allow_slow=True,
        allow_artifact_write=True,
    )
    assert direct["status"] == "ok"
    assert explicit["status"] == "ok"
    assert calls[0][0][2:7] == [
        "corpus",
        "-seed=11",
        "-runs=12",
        "-max_total_time=13",
        "-print_final_stats=1",
    ]
    assert calls[1][0][2:7] == [
        "corpus",
        "-seed=17",
        "-runs=18",
        "-max_total_time=19",
        "-print_final_stats=1",
    ]
    assert [call[2] for call in calls] == [13, 19]
    (tmp_path / "rush.toml").write_text(
        '[tools.fuzz]\nharness = "harness.py"\ncorpus = "corpus"\nseed = 23\nmax_runs = 24\ntimeout_seconds = 25\n'
    )
    configured = wrapped(
        tmp_path, allow_build=True, allow_slow=True, allow_artifact_write=True
    )
    assert configured["status"] == "ok"
    assert calls[2][0][3:6] == ["-seed=23", "-runs=24", "-max_total_time=25"]
    assert calls[2][2] == 25


def test_fuzz_uses_anchored_stderr_stats_and_rejects_fake_stdout(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fuzz_inputs(tmp_path)
    import rush.tools.fuzz as fuzz_mod

    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)
    outputs = iter(
        [
            (0, "runs 1000", ""),
            (0, "", "stat::number_of_executed_units: 3\n"),
        ]
    )

    def fake_run(argv, **_kwargs):
        code, stdout, stderr = next(outputs)
        return subprocess.CompletedProcess(argv, code, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(fuzz_mod, "run_subprocess", fake_run)
    permissions = ExecutionPermissions(build=True, slow=True, artifact_write=True)
    first = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        permissions=permissions,
    )
    second = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        permissions=permissions,
    )
    assert first["status"] == "skipped"
    assert first["metadata"]["incomplete"] is True
    assert second["status"] == "ok"
    assert second["metrics"]["iterations"] == 3


def test_fuzz_timeout_and_positive_exit_without_reproducer_are_errors(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fuzz_inputs(tmp_path)
    import rush.tools.fuzz as fuzz_mod

    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)
    calls = iter((subprocess.TimeoutExpired([sys.executable], 4),))

    def timeout_run(*_args, **_kwargs):
        raise next(calls)

    monkeypatch.setattr(fuzz_mod, "run_subprocess", timeout_run)
    permissions = ExecutionPermissions(build=True, slow=True, artifact_write=True)
    timed_out = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        seed=2,
        max_runs=3,
        timeout_seconds=4,
        permissions=permissions,
    )
    assert timed_out["status"] == "error"
    assert timed_out["metadata"]["terminal_reason"] == "timeout"
    assert timed_out["metadata"]["seed"] == 2
    assert timed_out["metadata"]["max_runs"] == 3
    assert timed_out["metadata"]["timeout_seconds"] == 4
    assert (
        timed_out["metadata"]["execution"]["granted_permissions"]
        == permissions.to_dict()
    )


def test_fuzz_positive_exit_without_reproducer_is_error(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fuzz_inputs(tmp_path)
    import rush.tools.fuzz as fuzz_mod

    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)
    monkeypatch.setattr(
        fuzz_mod,
        "run_subprocess",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="stat::number_of_executed_units: 2\n"
        ),
    )
    result = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"


def test_fuzz_report_symlink_cannot_overwrite_outside_file(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fuzz_inputs(tmp_path)
    outside = tmp_path.parent / "fuzz-victim.json"
    outside.write_text("sentinel", encoding="utf-8")
    import rush.tools.fuzz as fuzz_mod

    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)

    def fake_run(argv, *, cwd=None, **_kwargs):
        report = Path(cwd) / "fuzz-report.json"
        report.symlink_to(outside)
        return subprocess.CompletedProcess(
            argv, 0, stdout="", stderr="stat::number_of_executed_units: 2\n"
        )

    monkeypatch.setattr(fuzz_mod, "run_subprocess", fake_run)
    result = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"
    assert outside.read_text(encoding="utf-8") == "sentinel"


def test_fuzz_crash_symlink_outside_run_is_rejected(
    monkeypatch, tmp_path: Path
) -> None:
    _write_fuzz_inputs(tmp_path)
    outside = tmp_path.parent / "fuzz-outside-crashes"
    outside.mkdir()
    import rush.tools.fuzz as fuzz_mod

    monkeypatch.setattr(fuzz_mod, "atheris_available", lambda: True)

    def fake_run(argv, *, cwd=None, **_kwargs):
        crashes = Path(cwd) / "crashes"
        (crashes / "escape").symlink_to(outside, target_is_directory=True)
        return subprocess.CompletedProcess(
            argv, 1, stdout="", stderr="stat::number_of_executed_units: 2\n"
        )

    monkeypatch.setattr(fuzz_mod, "run_subprocess", fake_run)
    result = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"


def _require_real_module(name: str) -> None:
    if os.environ.get("RUSH_REQUIRE_REAL_ENGINES") == "1":
        assert importlib.util.find_spec(name), f"required engine module absent: {name}"


def test_required_atheris_module_absence_fails(monkeypatch) -> None:
    monkeypatch.setenv("RUSH_REQUIRE_REAL_ENGINES", "1")
    monkeypatch.setattr(importlib.util, "find_spec", lambda _name: None)
    with pytest.raises(AssertionError, match="required engine module absent: atheris"):
        _require_real_module("atheris")


def test_fuzz_real_workload(tmp_path: Path) -> None:
    _require_real_module("atheris")
    if os.environ.get("RUSH_REQUIRE_REAL_ENGINES") != "1":
        pytest.skip("real fuzz engine acceptance disabled")

    harness = tmp_path / "harness.py"
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "seed").write_bytes(b"RUSH_CRASH")
    harness.write_text(
        "import atheris\n"
        "@atheris.instrument_func\n"
        "def TestOneInput(data):\n"
        "    if data == b'RUSH_CRASH':\n"
        "        raise RuntimeError('known crash')\n"
        "atheris.Setup(__import__('sys').argv, TestOneInput)\n"
        "atheris.Fuzz()\n",
        encoding="utf-8",
    )
    original = harness.read_bytes()
    result = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        seed=0,
        max_runs=1000,
        timeout_seconds=60,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "fail"
    assert result["metrics"]["iterations"] > 0
    assert result["engine_version"] == "3.1.0"
    assert harness.read_bytes() == original
    assert (corpus / "seed").read_bytes() == b"RUSH_CRASH"
    reproducer = next(
        Path(path) for path in result["artifacts"] if Path(path).is_file()
    )
    assert reproducer.read_bytes() == b"RUSH_CRASH"
    run_root = reproducer.parent.parent
    assert run_root.is_relative_to(tmp_path.resolve() / ".rush" / "runs")
    replay = subprocess.run(
        [
            sys.executable,
            str(run_root / "harness.py"),
            str(reproducer),
            "-runs=1",
            f"-artifact_prefix={reproducer.parent}/",
        ],
        cwd=run_root,
        timeout=60,
        capture_output=True,
        check=False,
    )
    assert replay.returncode != 0
    assert b"RuntimeError: known crash" in replay.stderr

    harness.write_text(
        "import atheris\n"
        "@atheris.instrument_func\n"
        "def TestOneInput(data):\n"
        "    if data:\n"
        "        return data[0]\n"
        "    return 0\n"
        "atheris.Setup(__import__('sys').argv, TestOneInput)\n"
        "atheris.Fuzz()\n"
    )
    clean = FuzzTool().run(
        tmp_path,
        harness="harness.py",
        corpus="corpus",
        max_runs=20,
        timeout_seconds=60,
        permissions=ExecutionPermissions(build=True, slow=True, artifact_write=True),
    )
    assert clean["status"] == "ok"
    assert clean["metrics"]["iterations"] > 0
    assert clean["metrics"]["crashes"] == 0


def test_load_executed_mode_requires_network_permission(tmp_path: Path) -> None:
    tool = LoadTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-network" in res_denied["summary"]

    perms = ExecutionPermissions(network=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"


def test_load_contacts_target_and_enforces_threshold(
    monkeypatch, tmp_path: Path
) -> None:
    script = tmp_path / "load.js"
    script.write_text("export default function () {}\n", encoding="utf-8")
    import rush.tools.load as load_mod

    monkeypatch.setattr(load_mod, "engine_on_path", lambda name: name == "k6")
    calls = []

    def fake_run(argv, *, cwd=None, timeout=120, env=None):
        calls.append((argv, cwd, timeout, env))
        if argv[1:] == ["version"]:
            return subprocess.CompletedProcess(argv, 0, stdout="k6 v2.2.0", stderr="")
        report = Path(argv[argv.index("--summary-export") + 1])
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "metrics": {
                        "http_reqs": {"count": 10},
                        "http_req_failed": {"passes": 2, "fails": 8, "value": 0.2},
                        "http_req_duration": {
                            "values": {"count": 10},
                            "thresholds": {"p(95)<100": True},
                        },
                    }
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            argv, 99, stdout="", stderr="threshold failed"
        )

    monkeypatch.setattr(load_mod, "run_subprocess", fake_run)
    result = LoadTool().run(
        tmp_path,
        script="load.js",
        target_url="http://127.0.0.1:8765",
        vus=2,
        duration_seconds=7,
        timeout_seconds=9,
        permissions=ExecutionPermissions(network=True, slow=True, artifact_write=True),
    )

    assert result["status"] == "fail"
    assert result["engine_version"] == "2.2.0"
    assert result["metrics"]["total_requests"] == 10
    assert result["metrics"]["failed_requests"] == 2
    assert result["metadata"]["target_contacted"] is True
    assert result["artifacts"]
    assert Path(result["artifacts"][0]).is_file()
    assert calls[1][0][0:7] == [
        "k6",
        "run",
        "--vus",
        "2",
        "--duration",
        "7s",
        "--summary-export",
    ]
    assert calls[1][2] == 9
    assert calls[1][3]["RUSH_TARGET_URL"] == "http://127.0.0.1:8765"


@pytest.mark.parametrize(
    "metric,value",
    [
        ("http_reqs", {"count": True}),
        ("http_reqs", {"count": 1.5}),
        ("http_reqs", {"count": "2"}),
        ("http_reqs", []),
        ("http_req_failed", {"value": 0}),
        ("http_req_failed", {"passes": 0, "fails": 1}),
        ("http_req_duration", {"thresholds": []}),
        ("http_req_duration", {"thresholds": {"p(95)<100": "false"}}),
    ],
)
def test_load_rejects_malformed_native_summary(monkeypatch, tmp_path, metric, value):
    import rush.tools.load as load_mod

    (tmp_path / "load.js").write_text("export default function () {}")
    monkeypatch.setattr(load_mod, "engine_on_path", lambda _: True)

    def run(argv, **kwargs):
        if argv[1] == "version":
            return subprocess.CompletedProcess(argv, 0, "k6 v2.2.0", "")
        metrics = {
            "http_reqs": {"count": 2},
            "http_req_failed": {"passes": 0, "fails": 2},
        }
        metrics[metric] = value
        Path(argv[argv.index("--summary-export") + 1]).write_text(
            json.dumps({"metrics": metrics})
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(load_mod, "run_subprocess", run)
    result = LoadTool().run(
        tmp_path,
        script="load.js",
        target_url="http://localhost",
        permissions=ExecutionPermissions(network=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "error"


@pytest.mark.parametrize(
    "url,status",
    [("", "skipped"), ("http://[invalid", "error"), ("http://localhost:bad", "error")],
)
def test_load_validates_target_before_launch(monkeypatch, tmp_path, url, status):
    import rush.tools.load as load_mod

    monkeypatch.setattr(
        load_mod,
        "engine_on_path",
        lambda _: pytest.fail("discovered before validation"),
    )
    result = LoadTool().run(
        tmp_path,
        script="load.js",
        target_url=url,
        permissions=ExecutionPermissions(network=True, slow=True, artifact_write=True),
    )
    assert result["status"] == status
    if not url:
        assert result["metadata"]["requires_input"] == "target_url"


def test_load_zero_requests_are_incomplete_and_output_is_sanitized(
    monkeypatch, tmp_path
):
    import rush.tools.load as load_mod

    (tmp_path / "load.js").write_text("export default function () {}")
    monkeypatch.setattr(load_mod, "engine_on_path", lambda _: True)

    def run(argv, **kwargs):
        if argv[1] == "version":
            return subprocess.CompletedProcess(argv, 0, "k6 v2.2.0", "")
        Path(argv[argv.index("--summary-export") + 1]).write_text(
            json.dumps(
                {
                    "metrics": {
                        "http_reqs": {"count": 0},
                        "http_req_failed": {"passes": 0, "fails": 0},
                    },
                    "password": "private-password",
                }
            )
        )
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(load_mod, "run_subprocess", run)
    result = LoadTool().run(
        tmp_path,
        script="load.js",
        target_url="http://localhost/?password=private-password",
        permissions=ExecutionPermissions(network=True, slow=True, artifact_write=True),
    )
    assert result["status"] == "skipped"
    assert result["metadata"]["target_contacted"] is False
    assert "private-password" not in json.dumps(result)


def test_load_options_reach_execution_and_invalid_duration_denies_launch(
    monkeypatch, tmp_path: Path
) -> None:
    script = tmp_path / "load.js"
    script.write_text("export default function () {}\n", encoding="utf-8")
    import rush.tools.load as load_mod

    monkeypatch.setattr(load_mod, "engine_on_path", lambda _name: True)
    calls = []

    def fake_run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="k6 v2.2.0", stderr="")

    monkeypatch.setattr(load_mod, "run_subprocess", fake_run)
    permissions = ExecutionPermissions(network=True, slow=True, artifact_write=True)
    result = LoadTool().run(
        tmp_path,
        config={
            "options": {
                "script": "load.js",
                "target_url": "http://127.0.0.1:8765",
                "vus": 3,
                "duration_seconds": 4,
                "timeout_seconds": 5,
            }
        },
        permissions=permissions,
    )
    assert result["status"] == "error"
    assert calls[1][0:7] == [
        "k6",
        "run",
        "--vus",
        "3",
        "--duration",
        "4s",
        "--summary-export",
    ]
    call_count = len(calls)
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import make_tool_wrapper

    tool = LoadTool()
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    invalid = make_tool_wrapper(tool, executor)(
        tmp_path,
        script="load.js",
        target_url="http://127.0.0.1:8765",
        vus=1,
        duration_seconds=10,
        timeout_seconds=5,
        allow_network=True,
        allow_slow=True,
        allow_artifact_write=True,
    )
    assert invalid["status"] == "error"
    assert len(calls) == call_count


def test_load_real_workload(tmp_path: Path) -> None:
    _require_real_engine("k6")
    if os.environ.get("RUSH_REQUIRE_REAL_ENGINES") != "1":
        pytest.skip("real load engine acceptance disabled")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.counter += 1
            status = 500 if self.server.counter % 2 == 0 else 200
            self.send_response(status)
            self.end_headers()
            self.wfile.write(b"ok" if status == 200 else b"error")

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.counter = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        script = tmp_path / "load.js"
        script.write_text(
            "import http from 'k6/http';\n"
            "export const options = { thresholds: { http_req_failed: ['rate<0.25'] } };\n"
            "export default function () { http.get(__ENV.RUSH_TARGET_URL); }\n",
            encoding="utf-8",
        )
        result = LoadTool().run(
            tmp_path,
            script="load.js",
            target_url=f"http://127.0.0.1:{server.server_port}",
            vus=1,
            duration_seconds=2,
            timeout_seconds=10,
            permissions=ExecutionPermissions(
                network=True, slow=True, artifact_write=True
            ),
        )
        assert result["status"] == "fail"
        assert result["metadata"]["target_contacted"] is True
        assert result["metrics"]["total_requests"] == server.counter
        assert result["metrics"]["failed_requests"] == server.counter // 2
        assert result["engine_version"] == "2.2.0"
        assert result["artifacts"]
        assert Path(result["artifacts"][0]).is_file()
        import hashlib

        assert (
            result["metadata"]["raw_artifact_sha256"]
            == hashlib.sha256(Path(result["artifacts"][0]).read_bytes()).hexdigest()
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_load_real_workload_clean_target(tmp_path: Path) -> None:
    _require_real_engine("k6")
    if os.environ.get("RUSH_REQUIRE_REAL_ENGINES") != "1":
        pytest.skip("real load engine acceptance disabled")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.counter += 1
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.counter = 0
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        (tmp_path / "load.js").write_text(
            "import http from 'k6/http';\n"
            "export const options = { thresholds: { http_req_failed: ['rate<0.01'] } };\n"
            "export default function () { http.get(__ENV.RUSH_TARGET_URL); }\n",
            encoding="utf-8",
        )
        result = LoadTool().run(
            tmp_path,
            script="load.js",
            target_url=f"http://127.0.0.1:{server.server_port}",
            vus=1,
            duration_seconds=1,
            timeout_seconds=10,
            permissions=ExecutionPermissions(
                network=True, slow=True, artifact_write=True
            ),
        )
        assert result["status"] == "ok"
        assert result["metrics"]["total_requests"] == server.counter
        assert result["metrics"]["failed_requests"] == 0
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_flaky_executed_mode_requires_slow_permission(tmp_path: Path) -> None:
    tool = FlakyTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-slow" in res_denied["summary"]

    perms = ExecutionPermissions(slow=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"


def test_snapshot_executed_mode_requires_permissions(
    monkeypatch, tmp_path: Path
) -> None:
    tool = SnapshotTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-slow" in res_denied["summary"]

    # When accept=True without artifact_write permission
    perms_slow_only = ExecutionPermissions(slow=True)
    res_accept_denied = tool.run(tmp_path, accept=True, permissions=perms_slow_only)
    assert res_accept_denied["status"] == "skipped"
    assert "--allow-artifact-write" in res_accept_denied["summary"]

    # When both granted
    perms_both = ExecutionPermissions(slow=True, artifact_write=True)
    import rush.tools.snapshot as snapshot_mod

    monkeypatch.setattr(snapshot_mod, "engine_on_path", lambda _b: True)
    monkeypatch.setattr(
        snapshot_mod,
        "run_subprocess",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 0, stdout="snapshots updated", stderr=""
        ),
    )
    res_accept_granted = tool.run(tmp_path, accept=True, permissions=perms_both)
    assert res_accept_granted["status"] == "ok"
    assert res_accept_granted["metadata"]["baseline_mutated"] is True


def test_codeql_executed_mode_requires_build_permission(tmp_path: Path) -> None:
    tool = CodeqlTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-build" in res_denied["summary"]

    perms = ExecutionPermissions(build=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"
