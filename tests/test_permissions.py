"""Phase 07.0 execution permission contract tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.config import _parse
from rush.engines.base import Engine, EngineResult
from rush.permissions import (
    ExecutionPermissions,
    check_permissions,
)
from rush.tools import common
from rush.tools.base import ToolFn, ToolResult


class DummyPermissionEngine(Engine):
    name = "dummy-perm"
    binary = "dummy-perm"
    file_extensions = ("txt",)

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
    ) -> EngineResult:
        return {
            "exit_code": 0,
            "stdout": "dummy output",
            "stderr": "",
            "summary": "dummy clean",
            "findings": [],
        }


class DummyTool(ToolFn):
    name = "dummy-tool"

    @property
    def mcp_description(self) -> str:
        return "Dummy tool for permission tests."

    def __call__(
        self,
        path: Path,
        *,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, permissions=permissions)

    def run(
        self,
        path: Path,
        *,
        permissions: ExecutionPermissions | None = None,
        config=None,
    ) -> ToolResult:
        engine = DummyPermissionEngine()
        required = ExecutionPermissions(network=True, slow=True)
        return common.run_engine(
            engine,
            path,
            [],
            tool_name=self.name,
            permissions=permissions,
            required_permissions=required,
        )


def test_default_permissions_are_all_false() -> None:
    perms = ExecutionPermissions()
    assert perms.network is False
    assert perms.download is False
    assert perms.cache_write is False
    assert perms.build is False
    assert perms.slow is False
    assert perms.artifact_write is False
    assert perms.browser is False


def test_permission_check_identifies_missing_grants() -> None:
    required = ExecutionPermissions(network=True, slow=True)
    granted = ExecutionPermissions(network=True)
    ok, missing = check_permissions(required, granted)
    assert not ok
    assert missing == ["--allow-slow"]


def test_default_denial_skips_without_spawning_process(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    spawned = False

    def fake_subprocess(*args, **kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("Child process spawned despite denied permissions")

    monkeypatch.setattr(common, "engine_on_path", lambda _b: True)
    monkeypatch.setattr(common, "run_subprocess", fake_subprocess)

    engine = DummyPermissionEngine()
    result = common.run_engine(
        engine,
        tmp_path,
        [],
        tool_name="dummy",
        permissions=ExecutionPermissions(),  # all False
        required_permissions=ExecutionPermissions(network=True),
    )

    assert not spawned
    assert result["status"] == "skipped"
    assert "requires permission: --allow-network" in result["summary"]
    assert result["metadata"]["execution"]["mode"] == "executed"
    assert result["metadata"]["execution"]["granted_permissions"]["network"] is False
    assert result["metadata"]["execution"]["requested_permissions"]["network"] is True


def test_granted_permission_allows_engine_execution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: True)
    engine = DummyPermissionEngine()
    result = common.run_engine(
        engine,
        tmp_path,
        [],
        tool_name="dummy",
        permissions=ExecutionPermissions(network=True),
        required_permissions=ExecutionPermissions(network=True),
    )

    assert result["status"] == "ok"
    assert result["metadata"]["execution"]["mode"] == "executed"
    assert result["metadata"]["execution"]["granted_permissions"]["network"] is True


def test_project_config_cannot_escalate_permissions(tmp_path: Path) -> None:
    config_file = tmp_path / "rush.toml"
    cfg = _parse({"tools": {"security": {"check": True}}}, config_file)
    assert not hasattr(cfg, "allow_network")
    assert not hasattr(cfg, "permissions")


def test_mcp_call_forwards_explicit_permission_grants(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: True)
    tool = DummyTool()
    # Denied by default
    res_denied = tool(tmp_path)
    assert res_denied["status"] == "skipped"
    assert "--allow-network" in res_denied["summary"]

    # Granted
    res_granted = tool(tmp_path, allow_network=True, allow_slow=True)
    assert res_granted["status"] == "ok"
