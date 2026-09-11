"""MC05 (Phase 63): real observation capture routed through CLI/MCP transports.

Covers all three transport entry points named in the plan
(`rendering._run_tool`, `mcp_support.tool_registry.make_tool_wrapper`,
`mcp_support.tool_registry.make_custom_wrapper`), plus the direct
`InvocationExecutor`/`rush.memory.experience` contract exercised by all of
them under the hood.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from rush.cli_support import rendering
from rush.config import load_config
from rush.invocation import InvocationExecutor, resolve_invocation
from rush.mcp_support.tool_registry import make_custom_wrapper, make_tool_wrapper
from rush.memory.experience import classify_capability_family, record_observation
from rush.permissions import ExecutionPermissions


def _write_memory_config(root: Path, *, record: bool = True) -> None:
    (root / "rush.toml").write_text(
        f"[tools.memory]\nrecord = {'true' if record else 'false'}\n",
        encoding="utf-8",
    )


def _observations(root: Path) -> list[dict[str, Any]]:
    db = root / ".rush" / "memory.db"
    if not db.exists():
        return []
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT content FROM memory_artifacts WHERE family='experience' AND subject='episodic'"
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


class _ProbeTool:
    """Minimal ToolFn-shaped stub used to drive real invocation transports."""

    name = "probe"

    def __init__(self, status: str = "ok") -> None:
        self.status = status
        self.calls = 0

    def __call__(self, path: Path, allow_cache_write: bool = False) -> dict[str, Any]:
        self.calls += 1
        return {
            "tool": "probe",
            "engine": "probe-engine",
            "engine_version": "1.0",
            "status": self.status,
            "duration_ms": 1,
            "summary": "probe ran",
            "findings": [],
            "raw": {"detail": "value"},
        }


def _custom_probe(path: Path, allow_cache_write: bool = False) -> dict[str, Any]:
    return {
        "tool": "custom-probe",
        "engine": None,
        "engine_version": None,
        "status": "ok",
        "duration_ms": 1,
        "summary": "custom probe ran",
        "findings": [],
        "raw": None,
    }


def test_observer_covers_cli_mcp_without_duplicates(
    tmp_path: Path, monkeypatch
) -> None:
    # -- CLI transport via `rendering._run_tool` --
    cli_root = tmp_path / "cli"
    cli_root.mkdir()
    _write_memory_config(cli_root)
    monkeypatch.setattr(rendering, "ALL_TOOLS", [_ProbeTool()])
    with pytest.raises(SystemExit):
        rendering._run_tool(
            "probe",
            cli_root,
            as_json=True,
            permissions=ExecutionPermissions(cache_write=True),
        )
    cli_obs = _observations(cli_root)
    assert len(cli_obs) == 1
    assert cli_obs[0]["operation_id"] == "probe"
    assert cli_obs[0]["transport"] == "cli"

    # -- MCP transport via `make_tool_wrapper` --
    mcp_root = tmp_path / "mcp"
    mcp_root.mkdir()
    _write_memory_config(mcp_root)
    tool = _ProbeTool()
    tool_executor = InvocationExecutor()
    tool_executor.register(tool.name, tool.__call__)
    wrapped_tool = make_tool_wrapper(tool, tool_executor)
    wrapped_tool(mcp_root, allow_cache_write=True)
    mcp_obs = _observations(mcp_root)
    assert len(mcp_obs) == 1
    assert mcp_obs[0]["operation_id"] == "probe"
    assert mcp_obs[0]["transport"] == "mcp"

    # -- MCP transport via `make_custom_wrapper` --
    custom_root = tmp_path / "custom"
    custom_root.mkdir()
    _write_memory_config(custom_root)
    custom_executor = InvocationExecutor()
    custom_executor.register("custom-probe", _custom_probe)
    wrapped_custom = make_custom_wrapper(_custom_probe, "custom-probe", custom_executor)
    wrapped_custom(custom_root, allow_cache_write=True)
    custom_obs = _observations(custom_root)
    assert len(custom_obs) == 1
    assert custom_obs[0]["operation_id"] == "custom-probe"
    assert custom_obs[0]["transport"] == "mcp"


def test_observer_off_or_denied_writes_nothing(tmp_path: Path) -> None:
    target = tmp_path / "t.py"
    target.write_text("x = 1\n", encoding="utf-8")

    # Recording off (no `[tools.memory] record` config at all) + cache_write granted.
    off_root = tmp_path / "off"
    off_root.mkdir()
    off_target = off_root / "t.py"
    off_target.write_text("x = 1\n", encoding="utf-8")
    tool_off = _ProbeTool()
    executor_off = InvocationExecutor()
    executor_off.register(tool_off.name, tool_off.__call__)
    req_off = {
        "operation_id": "probe",
        "path": str(off_target),
        "allow_cache_write": True,
    }
    ctx_off = resolve_invocation(
        req_off,
        transport="cli",
        workspace_root=off_root,
        config=load_config(start=off_root),
    )
    assert ctx_off.memory_record is False
    executor_off.execute(ctx_off)
    assert _observations(off_root) == []

    # Recording on + cache_write denied.
    denied_root = tmp_path / "denied"
    denied_root.mkdir()
    denied_target = denied_root / "t.py"
    denied_target.write_text("x = 1\n", encoding="utf-8")
    _write_memory_config(denied_root)
    tool_denied = _ProbeTool()
    executor_denied = InvocationExecutor()
    executor_denied.register(tool_denied.name, tool_denied.__call__)
    req_denied = {"operation_id": "probe", "path": str(denied_target)}
    ctx_denied = resolve_invocation(
        req_denied,
        transport="cli",
        workspace_root=denied_root,
        config=load_config(start=denied_root),
    )
    assert ctx_denied.memory_record is True
    assert "cache_write" not in ctx_denied.permissions
    executor_denied.execute(ctx_denied)
    assert _observations(denied_root) == []


def test_cached_result_keeps_original_execution_identity(tmp_path: Path) -> None:
    root = tmp_path
    _write_memory_config(root)
    target = root / "target.py"
    target.write_text("value = 1\n", encoding="utf-8")

    class _DictCache:
        def __init__(self) -> None:
            self._store: dict[str, Any] = {}

        def get(self, key: str) -> Any:
            return self._store.get(key)

        def set(self, key: str, value: Any) -> None:
            self._store[key] = value

    tool = _ProbeTool()
    executor = InvocationExecutor(cache=_DictCache())
    executor.register(tool.name, tool.__call__, pure=True)

    req = {"operation_id": "probe", "path": str(target), "allow_cache_write": True}
    config = load_config(start=root)

    ctx1 = resolve_invocation(req, transport="cli", workspace_root=root, config=config)
    result1 = executor.execute(ctx1)
    assert tool.calls == 1
    assert len(_observations(root)) == 1

    ctx2 = resolve_invocation(req, transport="cli", workspace_root=root, config=config)
    result2 = executor.execute(ctx2)
    assert tool.calls == 1, "cache hit must not re-invoke the handler"
    assert result2 == result1, "cache hit must preserve the original receipt identity"
    assert len(_observations(root)) == 1, (
        "cache hit must not create a fresh observation"
    )


@pytest.mark.parametrize(
    "operation_id,expected_family",
    [
        ("test", "tests_contracts"),
        ("api-diff", "source_graph"),
        ("security", "security_dependency"),
        ("patch-apply", "sandbox_verification"),
        ("continuity", "continuity_checkpoint"),
    ],
)
def test_five_capability_families_preserve_evidence_kind(
    tmp_path: Path, operation_id: str, expected_family: str
) -> None:
    assert classify_capability_family(operation_id) == expected_family

    root = tmp_path / operation_id.replace("-", "_")
    root.mkdir()
    req = {"operation_id": operation_id, "path": str(root), "allow_cache_write": True}
    ctx = resolve_invocation(req, transport="cli", workspace_root=root)
    result = {
        "status": "ok",
        "summary": "ran",
        "engine": None,
        "engine_version": None,
        "raw": None,
        "metadata": {},
    }

    artifact = record_observation(ctx, result, project_root=root)

    assert artifact is not None
    assert artifact.content["evidence_kind"] == expected_family


def test_secret_redaction_precedes_persistence(tmp_path: Path) -> None:
    root = tmp_path
    req = {"operation_id": "probe", "path": str(root), "allow_cache_write": True}
    ctx = resolve_invocation(req, transport="cli", workspace_root=root)
    secret = "AKIAABCDEFGHIJKLMNOP"
    result = {
        "status": "ok",
        "summary": "ok",
        "engine": None,
        "engine_version": None,
        "raw": {"stdout": f"aws_key={secret}"},
        "metadata": {},
    }

    artifact = record_observation(ctx, result, project_root=root)

    assert artifact is not None
    serialized = json.dumps(artifact.content)
    assert secret not in serialized
    assert "[REDACTED_AWS_ACCESS_KEY]" in serialized

    with sqlite3.connect(root / ".rush" / "memory.db") as conn:
        stored_content = conn.execute(
            "SELECT content FROM memory_artifacts WHERE id = ?", (artifact.id,)
        ).fetchone()[0]
    assert secret not in stored_content
    assert "[REDACTED_AWS_ACCESS_KEY]" in stored_content


def test_failed_observation_preserves_original_tool_failure(tmp_path: Path) -> None:
    root = tmp_path
    _write_memory_config(root)
    target = root / "t.py"
    target.write_text("x = 1\n", encoding="utf-8")

    tool = _ProbeTool(status="fail")
    executor = InvocationExecutor()
    executor.register(tool.name, tool.__call__)
    req = {"operation_id": "probe", "path": str(target), "allow_cache_write": True}
    ctx = resolve_invocation(
        req, transport="cli", workspace_root=root, config=load_config(start=root)
    )

    result = executor.execute(ctx)

    assert result["status"] == "fail"
    obs = _observations(root)
    assert len(obs) == 1
    assert obs[0]["status"] == "fail"
