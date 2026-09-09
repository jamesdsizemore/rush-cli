"""Phase 07.B Executed modes contract tests across advanced evidence tools."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
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


def test_load_executed_mode_requires_network_permission(tmp_path: Path) -> None:
    tool = LoadTool()
    res_denied = tool.run(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-network" in res_denied["summary"]

    perms = ExecutionPermissions(network=True)
    res_granted = tool.run(tmp_path, permissions=perms)
    assert res_granted["metadata"]["execution"]["mode"] == "executed"


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
