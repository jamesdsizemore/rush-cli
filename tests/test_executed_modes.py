"""Phase 07.B Executed modes contract tests across advanced evidence tools."""

from __future__ import annotations

import subprocess
from pathlib import Path

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
