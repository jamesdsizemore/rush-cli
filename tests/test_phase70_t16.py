"""RED tests for Phase 70 T16: scope, per-engine outcomes, recoverable output.

Binding design: ``.scratch/phase-70-design-gate/W2-T9-T17.md`` section ``## T16``.
Plan packet: ``docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md`` T16.

T8/T9/T10 are not implemented in this worktree. Every fixture below (child
``ToolResult`` dicts, CCR chunk content, legacy results) is fabricated
directly by the test rather than produced by running a real T8/T9/T10 code
path, so every case here asserts T16's own behavior directly against real,
current source -- none of them are ``RED-via-Tn``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from rush.contracts.results import adapt_legacy_tool_result, validate_tool_result
from rush.invocation import InvocationContext, PhysicalTarget
from rush.invocation.executor import InvocationExecutor
from rush.tools.base import ToolResult
from rush.tools.routing import aggregate_results, combine_status

pytestmark = pytest.mark.usefixtures("_isolated_home")


@pytest.fixture
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """No case in this file may touch the real user HOME."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


def _context(tmp_path: Path, *, operation_id: str = "lint") -> InvocationContext:
    return InvocationContext(
        workspace_root=tmp_path,
        transport="cli",
        operation_id=operation_id,
        operation_kind="tool",
        targets=(
            PhysicalTarget(
                relative_path=Path("f.py"),
                state="present",
                capability="read",
                provenance="explicit",
                content_hash="a" * 64,
            ),
        ),
        effective_config_digest="d" * 64,
        permissions=("read", "cache_write"),
        ordered_args=(),
        declared_ignored_inputs=(),
        cache_policy="eligible",
        artifact_build_identity="build-1",
        tool_revision="rev-1",
        normalizer_revision="norm-1",
        environment_digest="e" * 64,
        request_id="req-1",
    )


def _child(
    status: str,
    *,
    engine: str | None,
    engines: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> ToolResult:
    """Fabricate a legacy child ToolResult as if a run_engine-instrumented
    tool already produced it (T16 owns run_engine's entry shape; this test
    fabricates the entry so aggregate_results's own concatenation -- also
    T16's -- can be tested independently)."""
    if engines is None:
        engines = (
            [{"engine": engine, "status": status}]
            if engine or status == "skipped"
            else []
        )
    result: dict[str, Any] = {
        "tool": "lint",
        "engine": engine,
        "engine_version": None,
        "status": status,
        "duration_ms": 5,
        "summary": f"{engine or 'none'}: {status}",
        "findings": [],
        "raw": None,
        "metadata": {"engines": engines},
    }
    result.update(overrides)
    return result  # type: ignore[return-value]


def _canonical_json(obj: dict[str, Any]) -> str:
    """Mirrors R16.6/§3 item 7's own definition of canonical_json, which
    does not exist as a helper yet -- inlined so this test does not depend
    on an unwritten function to build its fixtures."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _seed_ccr_row(tmp_path: Path, content: str) -> str:
    """Insert `content` directly into `.rush/cache/ccr.db`'s `chunks` table
    under its sha256, reusing the existing CCR schema (G-G) without going
    through the decorated `CCRStore.store_chunk` markdown-tag wrapper."""
    handle = hashlib.sha256(content.encode("utf-8")).hexdigest()
    db_path = tmp_path / ".rush" / "cache" / "ccr.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
                hash TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                last_accessed_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO chunks VALUES (?, ?, ?, 0, 0)",
            (handle, content, len(content.encode("utf-8"))),
        )
        conn.commit()
    return handle


def _retrieve(tmp_path: Path, **kwargs: Any) -> Any:
    """Call T16's not-yet-existing shared retrieval entrypoint (design item
    10). Raises AttributeError today -- that IS the decisive RED reason for
    every case that calls this helper."""
    from rush.continuity import context as context_module

    return context_module.retrieve_result_view(root=tmp_path, **kwargs)


# --------------------------------------------------------------------------
# Group 1: S16.2/S16.3 -- per-engine entries and status precedence
# (aggregate_results never sets `metadata` for non-"review" tools today, and
#  `combine_status` ranks skipped below ok, so mixed ok+skipped stays "ok".)
# --------------------------------------------------------------------------


def test_t16_executed_child_produces_engine_entry() -> None:
    result = aggregate_results(
        "lint",
        [_child("ok", engine="ruff", engines=[{"engine": "ruff", "status": "ok"}])],
    )
    assert result.get("metadata", {}).get("engines") == [
        {"engine": "ruff", "status": "ok"}
    ], (
        "S16.2: aggregate_results must concatenate each child's metadata.engines; "
        f"got metadata={result.get('metadata')!r}"
    )


def test_t16_empty_scope_has_zero_engines() -> None:
    result = aggregate_results("lint", [])
    assert result.get("metadata", {}).get("engines") == [], (
        "S16.2: empty scope must still carry metadata.engines == []; "
        f"got metadata={result.get('metadata')!r}"
    )


def test_t16_missing_engine_records_version_unavailable_reason() -> None:
    child = _child(
        "skipped",
        engine=None,
        engines=[
            {
                "engine": None,
                "status": "skipped",
                "version": None,
                "version_unavailable_reason": "engine_not_installed",
            }
        ],
    )
    result = aggregate_results("lint", [child])
    engines = result.get("metadata", {}).get("engines", [])
    assert (
        engines
        and engines[0].get("version_unavailable_reason") == "engine_not_installed"
    ), f"S16.2: missing-engine entry must survive aggregation; got {engines!r}"


def test_t16_denied_child_engine_entry_records_permission_reason() -> None:
    child = _child(
        "skipped",
        engine="ruff",
        engines=[
            {
                "engine": "ruff",
                "status": "skipped",
                "version_unavailable_reason": "permission_denied",
            }
        ],
    )
    result = aggregate_results("lint", [child])
    engines = result.get("metadata", {}).get("engines", [])
    assert (
        engines and engines[0].get("version_unavailable_reason") == "permission_denied"
    ), f"S16.2: denied-child entry must survive aggregation; got {engines!r}"


def test_t16_timeout_child_engine_entry_records_reason() -> None:
    child = _child(
        "error",
        engine="ruff",
        engines=[{"engine": "ruff", "status": "error", "reason": "timeout"}],
    )
    result = aggregate_results("lint", [child])
    engines = result.get("metadata", {}).get("engines", [])
    assert engines and engines[0].get("reason") == "timeout", (
        f"S16.2: timeout entry must survive aggregation; got {engines!r}"
    )


def test_t16_crash_child_engine_entry_records_reason() -> None:
    child = _child(
        "error",
        engine="ruff",
        engines=[{"engine": "ruff", "status": "error", "reason": "crash"}],
    )
    result = aggregate_results("lint", [child])
    engines = result.get("metadata", {}).get("engines", [])
    assert engines and engines[0].get("reason") == "crash", (
        f"S16.2: crash entry must survive aggregation; got {engines!r}"
    )


def test_t16_mixed_ok_and_skipped_children_become_warn() -> None:
    """S16.3: precedence is error>fail>warn>skipped>ok, and mixed ok+skipped
    becomes warn. Today `_STATUS_RANK` puts skipped(0) below ok(1), so
    `combine_status("ok", "skipped")` returns "ok", not "warn"."""
    result = aggregate_results(
        "lint",
        [
            _child("ok", engine="ruff"),
            _child("skipped", engine=None),
        ],
    )
    assert result["status"] == "warn", (
        f"S16.3: mixed ok+skipped must aggregate to warn; got {result['status']!r} "
        f"(combine_status('ok','skipped')={combine_status('ok', 'skipped')!r})"
    )


def test_t16_cached_result_marks_metadata_execution_cache(tmp_path: Path) -> None:
    """§3 item 4 (executor): on a cache hit, return a copy with
    metadata.execution.cache={"hit": true, "cache_key": key}, never rewrite
    the original. InvocationExecutor.execute currently returns the raw
    cached object unchanged."""
    cached_result: ToolResult = {
        "tool": "lint",
        "engine": "ruff",
        "engine_version": None,
        "status": "ok",
        "duration_ms": 1,
        "summary": "cached",
        "findings": [],
        "raw": None,
    }
    cache = MagicMock()
    cache.get.return_value = cached_result
    executor = InvocationExecutor(cache=cache)
    executor.register(
        "lint", lambda: pytest.fail("must not re-run on a cache hit"), pure=True
    )
    ctx = _context(tmp_path)
    result = executor.execute(ctx)
    assert (
        result.get("metadata", {}).get("execution", {}).get("cache")
        == {
            "hit": True,
        }
        or result.get("metadata", {}).get("execution", {}).get("cache", {}).get("hit")
        is True
    ), (
        "§3 item 4: a cache hit must return a copy carrying "
        f"metadata.execution.cache.hit=True; got metadata={result.get('metadata')!r}"
    )
    assert cached_result.get("metadata") is None, (
        "§3 item 4: the original cached object must never be rewritten in place"
    )


def test_t16_multi_engine_lint_retains_every_child_engine() -> None:
    result = aggregate_results(
        "lint",
        [
            _child("ok", engine="ruff", engines=[{"engine": "ruff", "status": "ok"}]),
            _child(
                "warn",
                engine="eslint",
                engines=[{"engine": "eslint", "status": "warn"}],
            ),
        ],
    )
    assert result.get("metadata", {}).get("engines") == [
        {"engine": "ruff", "status": "ok"},
        {"engine": "eslint", "status": "warn"},
    ], (
        "S16.2: multi-engine lint must retain every child's engine entry in order; "
        f"got metadata={result.get('metadata')!r}"
    )


def test_t16_suite_children_carry_summary_reason_engines_scope_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§3 item 3: suites set metadata.children=[{tool, status, summary,
    reason, engines:[names], scope:{coverage, reason}, execution:{disposition,
    cause}}]. Today suites.run_workflow_suite only records {"tool", "status"}
    per child (suites.py:170-173)."""
    from rush.workflows import suites as suites_module

    canned: ToolResult = {
        "tool": "format",
        "engine": "ruff",
        "engine_version": None,
        "status": "ok",
        "duration_ms": 1,
        "summary": "format: clean",
        "findings": [],
        "raw": None,
        "metadata": {"engines": [{"engine": "ruff", "status": "ok"}]},
    }
    monkeypatch.setattr(InvocationExecutor, "execute", lambda self, ctx: canned)
    target = tmp_path / "src"
    target.mkdir()

    aggregate = suites_module.run_workflow_suite(
        suites_module.CHECK_SUITE, target, permissions=(), fail_fast=False
    )
    child = aggregate["metadata"]["children"][0]
    for key in ("summary", "reason", "engines", "scope", "execution"):
        assert key in child, (
            f"§3 item 3: suite child metadata must carry {key!r}; got keys={sorted(child)}"
        )


def test_t16_scan_aggregate_scope_reports_kind_and_coverage() -> None:
    """§3 item 3: suites and scans set an aggregate scope
    {version:1, kind:"aggregate", coverage:..., requested_targets,
    logical_root}. aggregate_results never builds a "scope" key at all."""
    result = aggregate_results(
        "scan",
        [
            _child("ok", engine="ruff"),
            _child("ok", engine="mypy"),
        ],
    )
    scope = result.get("metadata", {}).get("scope")
    assert scope is not None and scope.get("kind") == "aggregate", (
        f"S16.3/§3 item 3: scan aggregation must build metadata.scope with "
        f"kind='aggregate'; got metadata={result.get('metadata')!r}"
    )


# --------------------------------------------------------------------------
# Group 2: transport plumbing -- CLI/MCP options, no-cache conflict, help text
# --------------------------------------------------------------------------


def test_t16_cli_catalog_command_missing_result_view_options() -> None:
    from rush.cli_support.catalog_commands import build_catalog_path_command
    from rush.tools import ALL_TOOLS

    lint_tool = next(t for t in ALL_TOOLS if t.name == "lint")
    command = build_catalog_path_command(lint_tool)
    names = {p.name for p in command.params}
    missing = {"result_view", "limit", "max_bytes"} - names
    assert not missing, (
        "S16.4/§3 item 6: catalog command factory must add --result-view/--limit/"
        f"--max-bytes; missing params {missing!r} out of {sorted(names)}"
    )


def test_t16_mcp_wrapper_signature_missing_result_view_kwargs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16.4/§3 item 6: the registered `rush_lint` MCP tool (from
    `build_server()`) publishes result_view/limit/max_bytes/no_cache in both
    its wrapper signature and its input schema. (Originally inspected
    `LintTool.__call__`, which R16.5 keeps free of these parameters.)"""
    import asyncio
    import inspect

    from rush.mcp import build_server

    monkeypatch.chdir(tmp_path)
    server = build_server()
    registered = server._tool_manager._tools["rush_lint"]
    params = set(inspect.signature(registered.fn).parameters)
    listed = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    properties = set(listed["rush_lint"].inputSchema["properties"])
    for published in (params, properties):
        missing = {"result_view", "limit", "max_bytes", "no_cache"} - published
        assert not missing, (
            "S16.4/§3 item 6: MCP make_tool_wrapper must publish result_view/limit/"
            f"max_bytes/no_cache; missing {missing!r} out of {sorted(published)}"
        )


def _spawn_spy(
    monkeypatch: pytest.MonkeyPatch, *, block: bool = True
) -> list[tuple[str, ...]]:
    """W2 finding 26: count every child once, at `Popen.__init__` (which also
    catches `subprocess.run`), and patch `subprocess.run` as a pass-through so
    a rebinding cannot bypass the count. `block=False` is the granted
    positive control."""
    import subprocess

    calls: list[tuple[str, ...]] = []
    real_init = subprocess.Popen.__init__
    real_run = subprocess.run

    def _init_spy(self: Any, argv: Any, *args: Any, **kwargs: Any) -> None:
        recorded = tuple(argv) if isinstance(argv, (list, tuple)) else (str(argv),)
        calls.append(tuple(str(part) for part in recorded))
        if block:
            raise AssertionError(f"unexpected subprocess spawn: {recorded!r}")
        real_init(self, argv, *args, **kwargs)

    def _run_spy(*args: Any, **kwargs: Any) -> Any:
        return real_run(*args, **kwargs)

    monkeypatch.setattr(subprocess.Popen, "__init__", _init_spy)
    monkeypatch.setattr(subprocess, "run", _run_spy)
    return calls


def _tree(root: Path) -> dict[str, str]:
    """Every file, directory and symlink under `root` with its content hash."""
    snapshot: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        rel = item.relative_to(root).as_posix()
        if item.is_symlink():
            snapshot[rel] = "link"
        elif item.is_dir():
            snapshot[rel] = "dir"
        else:
            snapshot[rel] = hashlib.sha256(item.read_bytes()).hexdigest()
    return snapshot


def _lint_project(tmp_path: Path, findings: int = 0) -> Path:
    """A project root with one Python file carrying `findings` F401 imports."""
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    body = "".join(f"import os as m{i}\n" for i in range(findings)) or "x = 1\n"
    (root / "a.py").write_text(body, encoding="utf-8")
    return root


def _cli(root: Path, *args: str) -> tuple[int, dict[str, Any]]:
    from click.testing import CliRunner

    from rush.cli import cli

    result = CliRunner().invoke(cli, ["lint", str(root), "--json", *args])
    try:
        payload = json.loads(result.output)
    except json.JSONDecodeError:
        pytest.fail(
            f"CLI output is not JSON (exit {result.exit_code}): {result.output}"
        )
    return result.exit_code, payload


def _mcp_lint(root: Path, **kwargs: Any) -> dict[str, Any]:
    from rush.mcp_support.tool_registry import make_tool_wrapper
    from rush.tools import ALL_TOOLS

    lint_tool = next(t for t in ALL_TOOLS if t.name == "lint")
    wrapper = make_tool_wrapper(lint_tool, anchor_cwd=root)
    result = wrapper(path=".", **kwargs)
    return result.to_dict() if hasattr(result, "to_dict") else dict(result)


_BAD_CLI_VIEW_ARGS = [
    ("--limit", "0"),
    ("--limit", "51"),
    ("--max-bytes", "4095"),
    ("--max-bytes", "65537"),
]
_BAD_MCP_VIEW_ARGS = [
    {"limit": 0},
    {"limit": 51},
    {"limit": True},
    {"max_bytes": 4095},
    {"max_bytes": 65537},
    {"max_bytes": True},
    {"result_view": "tiny"},
]


@pytest.mark.parametrize("flag,value", _BAD_CLI_VIEW_ARGS)
def test_t16_validation_rejects_bad_limit_and_max_bytes_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str, value: str
) -> None:
    """S16.4: limit is an integer 1-50 and max_bytes 4096-65536; a bad value
    is RESULT_VIEW_INVALID, exit 2, before any spawn or write."""
    root = _lint_project(tmp_path)
    before = _tree(tmp_path)
    monkeypatch.chdir(root)
    calls = _spawn_spy(monkeypatch)
    code, payload = _cli(
        root, "--result-view", "compact", "--allow-cache-write", flag, value
    )
    assert code == 2, payload
    assert payload["status"] == "error"
    assert payload["metadata"]["error"]["code"] == "RESULT_VIEW_INVALID", payload
    assert calls == []
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("bad", _BAD_MCP_VIEW_ARGS)
def test_t16_validation_rejects_bad_limit_and_max_bytes_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: dict[str, Any]
) -> None:
    """S16.4 over MCP: the same RESULT_VIEW_INVALID, bool rejected, zero
    spawns and zero writes."""
    root = _lint_project(tmp_path)
    before = _tree(tmp_path)
    calls = _spawn_spy(monkeypatch)
    view = {"result_view": "compact", **bad}
    payload = _mcp_lint(root, allow_cache_write=True, **view)
    assert payload["status"] == "error"
    assert payload["metadata"]["error"]["code"] == "RESULT_VIEW_INVALID", payload
    assert calls == []
    assert _tree(tmp_path) == before


def test_t16_real_mcp_server_rejects_bool_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16.4: bool is rejected on the real FastMCP path too (no pydantic
    coercion of True to 1 before Rush's own validation)."""
    import asyncio

    from rush.mcp import build_server

    root = _lint_project(tmp_path)
    monkeypatch.chdir(root)
    calls = _spawn_spy(monkeypatch)
    server = build_server()
    outcome = asyncio.run(
        server.call_tool(
            "rush_lint",
            {
                "path": ".",
                "result_view": "compact",
                "limit": True,
                "allow_cache_write": True,
            },
        )
    )
    structured = outcome[1] if isinstance(outcome, tuple) else None
    payload = structured or json.loads(outcome[0][0].text)
    assert payload["metadata"]["error"]["code"] == "RESULT_VIEW_INVALID", payload
    assert calls == []


def test_t16_no_cache_and_compact_conflict_reported_before_spawn_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16.5: --no-cache with --result-view compact is
    RESULT_VIEW_CACHE_CONFLICT before any spawn or write, even with
    --allow-cache-write."""
    root = _lint_project(tmp_path)
    before = _tree(tmp_path)
    monkeypatch.chdir(root)
    calls = _spawn_spy(monkeypatch)
    code, payload = _cli(
        root, "--no-cache", "--result-view", "compact", "--allow-cache-write"
    )
    assert code == 2, payload
    assert payload["metadata"]["error"]["code"] == "RESULT_VIEW_CACHE_CONFLICT"
    assert calls == []
    assert _tree(tmp_path) == before


def test_t16_no_cache_and_compact_conflict_reported_before_spawn_mcp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _lint_project(tmp_path)
    before = _tree(tmp_path)
    calls = _spawn_spy(monkeypatch)
    payload = _mcp_lint(
        root, no_cache=True, result_view="compact", allow_cache_write=True
    )
    assert payload["metadata"]["error"]["code"] == "RESULT_VIEW_CACHE_CONFLICT"
    assert calls == []
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("transport", ["cli", "mcp"])
def test_t16_compact_without_cache_write_grant_zero_spawns_zero_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, transport: str
) -> None:
    """§3 item 7.3: compact needs the cache-write grant before any spawn;
    the help names full mode and --allow-cache-write."""
    root = _lint_project(tmp_path)
    before = _tree(tmp_path)
    monkeypatch.chdir(root)
    calls = _spawn_spy(monkeypatch)
    if transport == "cli":
        code, payload = _cli(root, "--result-view", "compact")
        assert code == 2
    else:
        payload = _mcp_lint(root, result_view="compact")
    error = payload["metadata"]["error"]
    assert error["code"] == "RESULT_VIEW_REQUIRES_CACHE_WRITE", payload
    assert "full" in error["help"] and "allow-cache-write" in error["help"]
    assert calls == []
    assert _tree(tmp_path) == before


def test_t16_compact_granted_positive_control_spawns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 26 positive control: the same spy records the engine spawn
    when compact is granted, and the delivery block is present."""
    root = _lint_project(tmp_path, findings=3)
    monkeypatch.chdir(root)
    calls = _spawn_spy(monkeypatch, block=False)
    code, payload = _cli(root, "--result-view", "compact", "--allow-cache-write")
    assert calls, "granted compact run must spawn the engine"
    delivery = payload["metadata"]["delivery"]
    assert delivery["view"] == "compact"
    assert len(delivery["result_handle"]) == 64
    assert code == 1 and payload["status"] == "fail"


def _stored_full(root: Path, handle: str) -> dict[str, Any]:
    db = root / ".rush" / "cache" / "ccr.db"
    with sqlite3.connect(db) as conn:
        (content,) = conn.execute(
            "SELECT content FROM chunks WHERE hash = ?", (handle,)
        ).fetchone()
    stored = json.loads(content)
    assert set(stored) == {"version", "created_at", "full_result", "finding_ids"}
    return stored


def _page_all(root: Path, handle: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    cursor = None
    while True:
        page = _retrieve(
            root,
            handle=handle,
            view="result",
            cursor=cursor,
            offset=None,
            limit=50,
            max_bytes=32768,
        )
        findings.extend(page["findings"])
        cursor = page["metadata"]["delivery"]["next_cursor"]
        if not cursor:
            return findings


def test_t16_compact_cli_mcp_parity_and_full_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R16.9: CLI and MCP compact deliveries agree on status, total, the
    recovered full result and finding-identity order; paging recovers every
    finding of the full result."""
    root = _lint_project(tmp_path, findings=120)
    monkeypatch.chdir(root)
    code, cli_payload = _cli(root, "--result-view", "compact", "--allow-cache-write")
    mcp_payload = _mcp_lint(root, result_view="compact", allow_cache_write=True)
    cli_delivery = cli_payload["metadata"]["delivery"]
    mcp_delivery = mcp_payload["metadata"]["delivery"]
    assert code == 1
    assert cli_payload["status"] == mcp_payload["status"] == "fail"
    assert cli_delivery["total_findings"] == mcp_delivery["total_findings"] == 120
    # Ruff findings carry fix edits, so the 32 KiB budget, not the 50-finding
    # limit, bounds the first page; the cursor carries the rest.
    assert 0 < cli_delivery["returned_findings"] <= 50
    assert cli_delivery["returned_findings"] == len(cli_payload["findings"])
    assert cli_delivery["complete"] is False and cli_delivery["next_cursor"]
    cli_full = _stored_full(root, cli_delivery["result_handle"])
    mcp_full = _stored_full(root, mcp_delivery["result_handle"])
    assert cli_full["finding_ids"] == mcp_full["finding_ids"]
    assert len(cli_full["full_result"]["findings"]) == 120
    recovered = _page_all(root, cli_delivery["result_handle"])
    assert [f["fingerprint"] for f in recovered] == cli_full["finding_ids"]


def test_t16_compact_store_failure_returns_error_without_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16.7: a failed store is RESULT_STORE_FAILED, exit 2, no handle, and
    the analysis status of the full result is still reported."""
    from rush.token_economy.ccr_store import CCRStore

    def _boom(self: Any, content: str) -> str:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr(CCRStore, "store_chunk", _boom)
    root = _lint_project(tmp_path, findings=2)
    monkeypatch.chdir(root)
    code, payload = _cli(root, "--result-view", "compact", "--allow-cache-write")
    assert code == 2
    assert payload["metadata"]["error"]["code"] == "RESULT_STORE_FAILED"
    delivery = payload["metadata"]["delivery"]
    assert delivery["result_handle"] is None and delivery["complete"] is False
    assert delivery["analysis_status"] == "fail"


def test_t16_compact_real_mcp_response_fits_max_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R16.6: the complete serialized MCP CallToolResult (text content plus
    structuredContent) plus the 96-byte JSON-RPC reserve fits max_bytes."""
    import asyncio

    from mcp.types import CallToolResult

    from rush.mcp import build_server

    root = _lint_project(tmp_path, findings=120)
    monkeypatch.chdir(root)
    server = build_server()
    outcome = asyncio.run(
        server.call_tool(
            "rush_lint",
            {
                "path": ".",
                "result_view": "compact",
                "max_bytes": 4096,
                "allow_cache_write": True,
            },
        )
    )
    content, structured = outcome if isinstance(outcome, tuple) else (outcome, None)
    envelope = CallToolResult(content=list(content), structuredContent=structured)
    size = len(envelope.model_dump_json(by_alias=True, exclude_none=True)) + 96
    payload = structured or json.loads(content[0].text)
    assert payload["metadata"]["delivery"]["max_bytes"] == 4096
    assert size <= 4096, size


def test_t16_secret_redacted_before_compact_store(tmp_path: Path) -> None:
    """§3 item 7.6: the full result is redacted with sanitize_value before it
    is stored, so the secret is in neither the CCR row nor the projection."""
    from rush.delivery import compact

    secret = "AKIAABCDEFGHIJKLMNOP"  # AWS-key-shaped secret literal
    root = tmp_path / "proj"
    root.mkdir()
    full = {
        "tool": "lint",
        "status": "warn",
        "duration_ms": 1,
        "summary": f"leaked {secret}",
        "findings": [
            {"path": "a.py", "line": 1, "severity": "warn", "message": secret}
        ],
        "raw": None,
    }
    projection = compact.deliver(
        "lint",
        compact.ViewOptions(result_view="compact"),
        cache_write=True,
        prepare=lambda: (root, lambda: dict(full)),
        serialize=compact.cli_size,
    )
    handle = projection["metadata"]["delivery"]["result_handle"]
    db = root / ".rush" / "cache" / "ccr.db"
    with sqlite3.connect(db) as conn:
        (content,) = conn.execute(
            "SELECT content FROM chunks WHERE hash = ?", (handle,)
        ).fetchone()
    assert secret not in content
    assert secret not in json.dumps(projection)


def test_t16_compact_395_findings_pages_recover_in_identity_order(
    tmp_path: Path,
) -> None:
    from rush.delivery import compact

    root = tmp_path / "proj"
    root.mkdir()
    full = {
        "tool": "lint",
        "status": "warn",
        "duration_ms": 1,
        "summary": "395",
        "findings": [
            {
                "path": f"f{i}.py",
                "line": i,
                "severity": "warn",
                "message": f"issue {i}",
                "fingerprint": hashlib.sha256(str(i).encode()).hexdigest(),
            }
            for i in range(395)
        ],
    }
    projection = compact.deliver(
        "lint",
        compact.ViewOptions(result_view="compact"),
        cache_write=True,
        prepare=lambda: (root, lambda: full),
        serialize=compact.cli_size,
    )
    delivery = projection["metadata"]["delivery"]
    assert delivery["total_findings"] == 395 and delivery["returned_findings"] == 50
    assert compact.cli_size(projection) <= 32768
    recovered = _page_all(root, delivery["result_handle"])
    assert [f["fingerprint"] for f in recovered] == [
        f["fingerprint"] for f in full["findings"]
    ]


# --------------------------------------------------------------------------
# W2 adversarial-review amendments (T16 #1-#9)
# --------------------------------------------------------------------------


class _StatusStandIn:
    """Amendment 1: T23's `StatusTool.__call__` signature from the W1 brief,
    until the real class lands."""

    name = "status"
    mcp_description = "status stand-in"

    def __init__(self) -> None:
        self.seen: dict[str, Any] = {}

    def __call__(
        self,
        path: str | None = None,
        operation: str = "status",
        session_id: str | None = None,
        result_handle: str | None = None,
        view: str | None = None,
        cursor: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        max_bytes: int | None = None,
    ) -> dict[str, Any]:
        self.seen = {"limit": limit, "max_bytes": max_bytes}
        return {
            "tool": "status",
            "status": "ok",
            "duration_ms": 0,
            "summary": "status",
            "findings": [],
        }


_VIEW_PARAMS = ("result_view", "limit", "max_bytes", "no_cache")


def test_t16_registration_publishes_view_params_once_for_all_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 1 (finding 1): build_server() succeeds; every catalog tool
    and the StatusTool stand-in publish each view parameter exactly once."""
    import asyncio
    import inspect

    from rush.mcp import build_server
    from rush.mcp_support.tool_registry import make_tool_wrapper
    from rush.tools import ALL_TOOLS

    monkeypatch.chdir(tmp_path)
    server = build_server()
    listed = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for tool in [*ALL_TOOLS, _StatusStandIn()]:
        wrapper = make_tool_wrapper(tool, anchor_cwd=tmp_path)
        names = list(inspect.signature(wrapper).parameters)
        for param in _VIEW_PARAMS:
            assert names.count(param) == 1, (tool.name, param, names)
        assert names.count("allow_cache_write") == 1, (tool.name, names)
        mcp_name = f"rush_{tool.name.replace('-', '_')}"
        if mcp_name in listed:
            properties = listed[mcp_name].inputSchema["properties"]
            assert set(_VIEW_PARAMS) <= set(properties), (mcp_name, properties)


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": True}, {"max_bytes": 1}])
def test_t16_declared_view_params_validate_identically(
    tmp_path: Path, bad: dict[str, Any]
) -> None:
    """Amendment 1: a tool declaring `limit`/`max_bytes` (StatusTool, the
    continuity tool) gets the identical RESULT_VIEW_INVALID as an injected
    one, and a valid declared value still reaches the tool."""
    from rush.mcp_support.tool_registry import make_tool_wrapper
    from rush.tools.continuity import SessionContinuityTool

    for tool in (_StatusStandIn(), SessionContinuityTool()):
        wrapper = make_tool_wrapper(tool, anchor_cwd=tmp_path)
        result = wrapper(path=".", **bad)
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        assert payload["metadata"]["error"]["code"] == "RESULT_VIEW_INVALID", (
            tool.name,
            payload,
        )
    standin = _StatusStandIn()
    make_tool_wrapper(standin, anchor_cwd=tmp_path)(path=".", limit=5)
    assert standin.seen == {"limit": 5, "max_bytes": None}


def test_t16_declared_view_param_with_different_contract_fails_registration(
    tmp_path: Path,
) -> None:
    from rush.invocation.models import SignatureAdaptationError
    from rush.mcp_support.tool_registry import make_tool_wrapper

    class _Different:
        name = "different"
        mcp_description = "different"

        def __call__(self, path: str = ".", limit: int = 10) -> dict[str, Any]:
            return {}

    with pytest.raises(SignatureAdaptationError):
        make_tool_wrapper(_Different(), anchor_cwd=tmp_path)


def test_t16_review_scope_v1_keeps_mode_and_files(tmp_path: Path) -> None:
    """Amendment 2 (finding 8): review's scope is the §3.2 v1 scope with
    `mode` and `files` kept inside it."""
    from rush.tools.review import ReviewTool

    (tmp_path / "changed.py").write_text("def changed():\n    return 1\n")
    (tmp_path / "other.py").write_text("def other():\n    return 1\n")
    result = ReviewTool().run(tmp_path, changed_files=["changed.py", "notes.txt"])
    scope = result["metadata"]["scope"]
    assert scope["version"] == 1 and scope["kind"] == "file"
    assert scope["mode"] == "explicit-files" and scope["files"] == ["changed.py"]
    assert scope["requested_file_count"] == 2
    assert scope["matched_file_count"] == 1
    assert scope["consumed_file_count"] == 1
    assert scope["coverage"] == "partial"


def _engine_child(tool: str, engine: str, status: str) -> ToolResult:
    child = _child(status, engine=engine)
    child["tool"] = tool
    return child


def test_t16_typecheck_mypy_ok_pyrefly_absent_is_warn() -> None:
    """Amendment 3 under owner decision (A)/finding 9: every engine is
    required, so an absent pyrefly next to an ok mypy is warn, exit 1."""
    from rush.tools.common import exit_code_for

    result = aggregate_results(
        "typecheck",
        [
            _engine_child("typecheck", "mypy", "ok"),
            _engine_child("typecheck", "pyrefly", "skipped"),
        ],
    )
    assert result["status"] == "warn"
    assert exit_code_for(result) == 1


def test_t16_complexity_partial_engines_is_warn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 3: the real ComplexityTool with one engine ok and the rest
    absent is warn, exit 1, and every engine keeps its entry."""
    from rush.tools import complexity as complexity_module
    from rush.tools.common import exit_code_for

    (tmp_path / "a.py").write_text("x = 1\n")

    def _fake_run_engine(engine: Any, path: Path, args: Any, **_: Any) -> ToolResult:
        status = "ok" if engine.name == "radon" else "skipped"
        return _engine_child("complexity", engine.name, status)

    monkeypatch.setattr(complexity_module, "run_engine", _fake_run_engine)
    result = complexity_module.ComplexityTool().run(tmp_path)
    assert result["status"] == "warn"
    assert exit_code_for(result) == 1
    names = [entry["engine"] for entry in result["metadata"]["engines"]]
    assert "radon" in names and len(names) >= 2


def test_t16_format_clean_ruff_stays_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R16.1: format's old `skipped` sentinel must not turn a clean ruff run
    into warn under the new precedence."""
    from rush.tools import format as format_module

    (tmp_path / "a.py").write_text("x = 1\n")

    def _fake_run_engine(engine: Any, path: Path, args: Any, **_: Any) -> ToolResult:
        return _engine_child("format", engine.name, "ok")

    monkeypatch.setattr(format_module, "run_engine", _fake_run_engine)
    result = format_module.FormatTool().run(tmp_path / "a.py")
    assert result["status"] == "ok", result


@pytest.mark.parametrize(
    "config,consumed,coverage",
    [
        ('extend-exclude=["pkg/b.py"]\n', 2, "complete"),
        ('force-exclude=true\nextend-exclude=["pkg/b.py"]\n', 1, "partial"),
    ],
)
def test_t16_lint_ruff_consumed_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: str,
    consumed: int,
    coverage: str,
) -> None:
    """Amendment 4 (finding 24): the consumed count comes from a recorded
    `ruff check --show-files` probe with the identical argv; explicit paths
    bypass extend-exclude unless force-exclude is set; configuration inputs
    are reported separately."""
    from rush.tools.lint import LintTool

    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg" / "a.py").write_text("x = 1\n")
    (root / "pkg" / "b.py").write_text("y = 2\n")
    (root / "pyproject.toml").write_text("[tool.ruff]\n" + config)
    # ruff resolves force-exclude from the invocation cwd's settings; the
    # probe uses the identical cwd, so it reports what the real run consumed.
    monkeypatch.chdir(root)
    result = LintTool().run(root)
    scope = result["metadata"]["scope"]
    assert scope["requested_file_count"] == 2
    assert scope["consumed_file_count"] == consumed, scope
    assert scope["coverage"] == coverage
    assert scope["consumption_source"] == "engine_show_files"
    assert [Path(p).name for p in scope["configuration_files"]] == ["pyproject.toml"]
    excluded = [(Path(e["path"]).name, e["reason"]) for e in scope["excluded_files"]]
    assert excluded == ([] if coverage == "complete" else [("b.py", "engine_excluded")])
    ruff = next(e for e in result["metadata"]["engines"] if e["engine"] == "ruff")
    assert "scope_probe" in [spawn["kind"] for spawn in ruff["spawns"]]


def _seed_row(db: Path, content: str) -> str:
    handle = hashlib.sha256(content.encode("utf-8")).hexdigest()
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chunks (hash TEXT PRIMARY KEY, content TEXT "
            "NOT NULL, byte_size INTEGER NOT NULL, created_at INTEGER NOT NULL, "
            "last_accessed_at INTEGER NOT NULL)"
        )
        conn.execute(
            "INSERT INTO chunks VALUES (?, ?, ?, 0, 0)",
            (handle, content, len(content.encode("utf-8"))),
        )
    return handle


def test_t16_cache_clean_retains_context_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 5 (finding 28): `rush cache clean` purges only T16 storage
    objects from ccr.db, keeps context-pack chunks, and reports all counts."""
    from click.testing import CliRunner

    from rush.cli import cli

    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    ccr = root / ".rush" / "cache" / "ccr.db"
    stored = _seed_row(
        ccr,
        _canonical_json(
            {
                "version": 1,
                "created_at": "2026-01-01T00:00:00Z",
                "full_result": {"tool": "lint"},
                "finding_ids": [],
            }
        ),
    )
    pack = _seed_row(ccr, json.dumps({"outline": "packed context"}))
    lookalike = _seed_row(ccr, json.dumps({"version": 1, "full_result": {}}))
    monkeypatch.chdir(root)
    result = CliRunner().invoke(cli, ["cache", "clean"])
    assert result.exit_code == 0, result.output
    report = json.loads(result.output.splitlines()[-1])
    assert result.output.startswith("Purged 0 cached result(s).")
    assert report == {
        "result_cache": 0,
        "compact_results": 1,
        "context_packs_retained": 2,
    }
    with sqlite3.connect(ccr) as conn:
        remaining = {row[0] for row in conn.execute("SELECT hash FROM chunks")}
    assert remaining == {pack, lookalike} and stored not in remaining
    assert not (root / ".rush" / "cache.db").exists()


def test_t16_cache_clean_never_creates_missing_dbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from click.testing import CliRunner

    from rush.cli import cli

    root = tmp_path / "proj"
    (root / ".git").mkdir(parents=True)
    before = _tree(root)
    monkeypatch.chdir(root)
    result = CliRunner().invoke(cli, ["cache", "clean"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output.splitlines()[-1]) == {
        "result_cache": 0,
        "compact_results": 0,
        "context_packs_retained": 0,
    }
    assert _tree(root) == before


def test_t16_compact_one_call_per_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 7 (finding 11): `_run_tool` and the MCP wrapper each call
    `rush.delivery.compact.deliver` exactly once per request."""
    from rush.delivery import compact

    calls: list[str] = []
    real = compact.deliver

    def _counting(tool_name: str, *args: Any, **kwargs: Any) -> Any:
        calls.append(tool_name)
        return real(tool_name, *args, **kwargs)

    monkeypatch.setattr(compact, "deliver", _counting)
    root = _lint_project(tmp_path)
    monkeypatch.chdir(root)
    _cli(root)
    assert calls == ["lint"]
    _mcp_lint(root, result_view="compact", allow_cache_write=True)
    assert calls == ["lint", "lint"]


def test_t16_retrieve_no_sidefiles(tmp_path: Path) -> None:
    """Amendment 8 (X1): result-view retrieval leaves the `.rush/cache`
    listing and the ccr.db bytes unchanged."""
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {
                "tool": "lint",
                "status": "ok",
                "duration_ms": 1,
                "summary": "ok",
                "findings": [],
            },
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    cache_dir = tmp_path / ".rush" / "cache"
    before = _tree(cache_dir)
    for view in ("result", "bytes"):
        page = _retrieve(
            tmp_path,
            handle=handle,
            view=view,
            cursor=None,
            offset=0,
            limit=None,
            max_bytes=32768,
        )
        assert "error" not in page["metadata"], page
    assert _tree(cache_dir) == before


def test_t16_retrieve_missing_store_zero_spawns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Amendment 9: a missing store is RESULT_MISSING with zero spawns (the
    engine is never rerun) and nothing created."""
    calls = _spawn_spy(monkeypatch)
    before = _tree(tmp_path)
    page = _retrieve(
        tmp_path,
        handle="b" * 64,
        view="result",
        cursor=None,
        offset=None,
        limit=None,
        max_bytes=None,
    )
    assert page["metadata"]["error"]["code"] == "RESULT_MISSING"
    assert calls == [] and _tree(tmp_path) == before


def test_t16_cli_context_retrieve_result_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S16.6: CLI `context retrieve` exposes the result view; the MCP
    `rush_context_retrieve` publishes the same view parameters."""
    import inspect

    from click.testing import CliRunner

    from rush.cli import cli
    from rush.mcp import rush_context_retrieve

    (tmp_path / ".git").mkdir()
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {
                "tool": "lint",
                "status": "warn",
                "duration_ms": 1,
                "summary": "one",
                "findings": [
                    {"path": "a.py", "line": 1, "severity": "warn", "message": "m"}
                ],
            },
            "finding_ids": ["x" * 64],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli, ["context", "retrieve", handle, "--view", "result", "--json"]
    )
    payload = json.loads(result.output)
    assert payload["metadata"]["delivery"]["total_findings"] == 1, payload
    assert payload["findings"][0]["message"] == "m"
    params = set(inspect.signature(rush_context_retrieve).parameters)
    assert {"view", "cursor", "offset", "limit", "max_bytes"} <= params
    mcp_page = rush_context_retrieve(handle, path=str(tmp_path), view="result")
    assert mcp_page["metadata"]["delivery"]["total_findings"] == 1


def test_t16_legacy_retrieve_without_view_stays_full(tmp_path: Path) -> None:
    from rush.tools.continuity import SessionContinuityTool

    (tmp_path / ".git").mkdir()
    handle = _seed_ccr_row(tmp_path, "plain chunk")
    result = SessionContinuityTool().run(
        tmp_path, operation="context_retrieve", context_handle=handle
    )
    assert result["raw"] == {"content": "plain chunk"}


# --------------------------------------------------------------------------
# Real run_engine entries, executor default scope, cache hits
# --------------------------------------------------------------------------


def test_t16_run_engine_executed_entry_records_executable_and_scope(
    tmp_path: Path,
) -> None:
    from rush.engines import ENGINES
    from rush.runtime.binaries import compute_file_sha256
    from rush.tools.common import run_engine

    target = tmp_path / "a.py"
    target.write_text("x = 1\n")
    result = run_engine(ENGINES["ruff"], target, [str(target)], tool_name="lint")
    (entry,) = result["metadata"]["engines"]
    assert entry["engine"] == "ruff" and entry["status"] == "ok"
    executable = entry["executable"]
    assert executable["sha256"] == compute_file_sha256(executable["path"])
    assert entry["version"] and entry["version_unavailable_reason"] is None
    assert entry["config"] == {
        "path": None,
        "sha256": None,
        "reason": "engine_does_not_report_config",
    }
    assert entry["cwd"]
    assert entry["scope"]["consumed_file_count"] == 1
    assert entry["scope"]["consumption_source"] == "explicit_arguments"


def test_t16_run_engine_missing_engine_entry(tmp_path: Path) -> None:
    from rush.engines.ruff import RuffEngine
    from rush.tools.common import run_engine

    class _Absent(RuffEngine):
        name = "absent-engine"
        binary = "rush-t16-definitely-not-installed"

    result = run_engine(_Absent(), tmp_path, [], tool_name="lint")
    (entry,) = result["metadata"]["engines"]
    assert result["status"] == "skipped"
    assert entry["version"] is None
    assert entry["version_unavailable_reason"] == "engine_not_installed"
    assert entry["executable"]["path"] is None
    assert entry["scope"]["consumed_file_count"] == 0


def test_t16_run_engine_denied_entry(tmp_path: Path) -> None:
    from rush.engines import ENGINES
    from rush.permissions import ExecutionPermissions
    from rush.tools.common import run_engine

    result = run_engine(
        ENGINES["ruff"],
        tmp_path,
        [],
        tool_name="lint",
        permissions=ExecutionPermissions(),
        required_permissions=ExecutionPermissions(build=True),
    )
    (entry,) = result["metadata"]["engines"]
    assert entry["reason"] == "permission_denied"
    assert entry["version_unavailable_reason"] == "permission_denied"


def test_t16_executor_default_scope_for_uninstrumented_tool(tmp_path: Path) -> None:
    """R16.2: a catalog tool that reports no scope gets `unavailable` with a
    reason, never a guess; operation-kind tools say `not_file_analysis`."""
    for op, kind, reason in (
        ("dead", "file", "tool_reports_no_file_consumption"),
        ("doctor", "operation", "not_file_analysis"),
    ):
        executor = InvocationExecutor()
        executor.register(
            op,
            lambda op=op: {
                "tool": op,
                "status": "ok",
                "duration_ms": 0,
                "summary": "x",
                "findings": [],
            },
        )
        result = executor.execute(_context(tmp_path, operation_id=op))
        scope = result["metadata"]["scope"]
        assert scope["version"] == 1 and scope["kind"] == kind, scope
        assert scope["coverage"] == "unavailable" and scope["reason"] == reason
        assert scope["requested_targets"] == ["f.py"]
        assert scope["logical_root"] == str(tmp_path)


def test_t16_help_text_names_full_mode() -> None:
    from rush.cli_support.catalog_commands import build_catalog_path_command
    from rush.tools import ALL_TOOLS

    lint_tool = next(t for t in ALL_TOOLS if t.name == "lint")
    command = build_catalog_path_command(lint_tool)
    ctx = command.make_context("lint", ["--help"], resilient_parsing=True)
    help_text = command.get_help(ctx)
    assert "full" in help_text and "compact" in help_text, (
        "§9 (Transport checks): CLI help text must name full mode alongside "
        f"compact; got help text without both: {help_text!r}"
    )


# --------------------------------------------------------------------------
# Group 3: retrieve_result_view -- paging, cursors, store states, recovery
# (continuity/context.py has no retrieve_result_view function today; every
#  case below fails with AttributeError until T16 adds it.)
# --------------------------------------------------------------------------


def test_t16_deleted_store_gives_result_missing_zero_spawns(tmp_path: Path) -> None:
    result = _retrieve(
        tmp_path,
        handle="a" * 64,
        view="result",
        cursor=None,
        offset=0,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["error"]["code"] == "RESULT_MISSING", (
        f"§3 item 10.3: deleted/absent store must give RESULT_MISSING; got {result!r}"
    )


def test_t16_tampered_row_gives_result_corrupt(tmp_path: Path) -> None:
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {"tool": "lint"},
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    db_path = tmp_path / ".rush" / "cache" / "ccr.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE chunks SET content = ? WHERE hash = ?", ("tampered", handle)
        )
        conn.commit()
    result = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor=None,
        offset=0,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["error"]["code"] == "RESULT_CORRUPT", (
        f"§3 item 10.6: sha256(content) != handle must give RESULT_CORRUPT; got {result!r}"
    )


def test_t16_symlinked_cache_directory_rejected(tmp_path: Path) -> None:
    """§3 item 10.2 reuses PhysicalRoot(root).open_contained, which already
    raises ContainmentError for a symlinked path component (physical_paths.py).
    Calling the not-yet-existing retrieve_result_view raises AttributeError
    instead today, so pytest.raises(ContainmentError) correctly does not
    catch it and the test errors -- decisively RED, and specific enough to
    turn genuinely green once retrieve_result_view reuses open_contained."""
    from rush.io.physical_paths import ContainmentError

    real_dir = tmp_path.parent / "outside-cache"
    real_dir.mkdir(exist_ok=True)
    rush_dir = tmp_path / ".rush"
    rush_dir.mkdir()
    (rush_dir / "cache").symlink_to(real_dir, target_is_directory=True)
    with pytest.raises(ContainmentError):
        _retrieve(
            tmp_path,
            handle="a" * 64,
            view="result",
            cursor=None,
            offset=0,
            limit=50,
            max_bytes=32768,
        )


def test_t16_store_failure_gives_error_with_no_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise sqlite3.Error("disk full")

    monkeypatch.setattr(sqlite3, "connect", _boom)
    result = _retrieve(
        tmp_path,
        handle="a" * 64,
        view="result",
        cursor=None,
        offset=0,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["delivery"]["result_handle"] is None, (
        f"§3 item 7 (RESULT_STORE_FAILED): a store failure must never fabricate "
        f"a handle; got {result!r}"
    )


def test_t16_large_result_395_findings_reconstructed_byte_for_byte(
    tmp_path: Path,
) -> None:
    full_result = {
        "tool": "lint",
        "status": "warn",
        "duration_ms": 10,
        "summary": "395 findings",
        "findings": [
            {
                "path": f"f{i}.py",
                "line": i,
                "severity": "warn",
                "message": f"issue {i}",
                "fingerprint": hashlib.sha256(str(i).encode()).hexdigest(),
            }
            for i in range(395)
        ],
    }
    finding_ids = [f["fingerprint"] for f in full_result["findings"]]
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": full_result,
            "finding_ids": finding_ids,
        }
    )
    handle = _seed_ccr_row(tmp_path, content)

    recovered_pages: list[dict[str, Any]] = []
    cursor = None
    while True:
        page = _retrieve(
            tmp_path,
            handle=handle,
            view="result",
            cursor=cursor,
            offset=None,
            limit=50,
            max_bytes=32768,
        )
        recovered_pages.append(page)
        cursor = page["metadata"]["delivery"].get("next_cursor")
        if not cursor:
            break
    total_findings = sum(len(p.get("findings", [])) for p in recovered_pages)
    assert total_findings == 395, (
        f"§6 (Large results): full page replay must recover exactly 395 findings; "
        f"got {total_findings}"
    )


def test_t16_large_result_93kib_bytes_view_hash_equal(tmp_path: Path) -> None:
    payload = "x" * (93 * 1024)
    full_result = {
        "tool": "lint",
        "status": "ok",
        "duration_ms": 1,
        "summary": "large raw",
        "findings": [],
        "raw": payload,
    }
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": full_result,
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    expected_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    recovered = bytearray()
    next_offset = 0
    while True:
        chunk = _retrieve(
            tmp_path,
            handle=handle,
            view="bytes",
            cursor=None,
            offset=next_offset,
            limit=None,
            max_bytes=32768,
        )
        raw = chunk["raw"]
        recovered.extend(raw["content"].encode("utf-8"))
        next_offset = raw.get("next_offset")
        if not next_offset:
            assert raw["sha256"] == expected_hash, (
                "§3 item 10.7 (bytes view): total content hash must equal the "
                f"stored handle's sha256; got {raw['sha256']!r} != {expected_hash!r}"
            )
            break


def test_t16_one_40kib_finding_returned_as_content_omitted_reference(
    tmp_path: Path,
) -> None:
    huge_message = "m" * (40 * 1024)
    full_result = {
        "tool": "lint",
        "status": "warn",
        "duration_ms": 1,
        "summary": "one huge finding",
        "findings": [
            {
                "path": "f.py",
                "line": 1,
                "severity": "warn",
                "message": huge_message,
                "fingerprint": "f" * 64,
            }
        ],
    }
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": full_result,
            "finding_ids": ["f" * 64],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    page = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor=None,
        offset=0,
        limit=50,
        max_bytes=4096,
    )
    finding = page["findings"][0]
    assert finding.get("content_omitted") is True and "identity" in finding, (
        "§3 item 8: an oversized finding must become an explicit "
        f"content_omitted reference; got {finding!r}"
    )


def test_t16_unicode_boundary_slice_is_utf8_safe(tmp_path: Path) -> None:
    """§3 item 10.7: bytes-view pages never split a 4-byte character. With a
    valid 4096-byte budget, 20 KB of 4-byte emoji forces page boundaries
    inside the emoji run; every page decodes, every next_offset is a UTF-8
    boundary, and the pages rejoin to the exact stored bytes. (Originally
    used max_bytes=50, below the 4096 minimum.)"""
    payload = "\U0001f600" * 5000  # 4-byte emoji, must not split mid-codepoint
    full_result = {
        "tool": "lint",
        "status": "ok",
        "duration_ms": 1,
        "summary": "emoji",
        "findings": [],
        "raw": payload,
    }
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": full_result,
            "finding_ids": [],
        }
    )
    data = content.encode("utf-8")
    emoji_start = data.index("\U0001f600".encode())
    emoji_end = emoji_start + len(payload.encode("utf-8"))
    handle = _seed_ccr_row(tmp_path, content)
    recovered = bytearray()
    offset = 0
    boundaries: list[int] = []
    while True:
        chunk = _retrieve(
            tmp_path,
            handle=handle,
            view="bytes",
            cursor=None,
            offset=offset,
            limit=None,
            max_bytes=4096,
        )
        raw = chunk["raw"]
        piece = raw["content"].encode("utf-8")
        assert raw["offset"] == offset and raw["length"] == len(piece)
        recovered.extend(piece)
        offset = raw["next_offset"]
        if offset is None:
            break
        boundaries.append(offset)
        assert data[offset] & 0xC0 != 0x80, f"next_offset {offset} splits a character"
    assert bytes(recovered) == data
    assert any(emoji_start < b < emoji_end for b in boundaries), boundaries


def test_t16_escaping_heavy_content_round_trips(tmp_path: Path) -> None:
    hazard = 'quote:" backslash:\\ control:\x01 newline:\n'
    full_result = {
        "tool": "lint",
        "status": "ok",
        "duration_ms": 1,
        "summary": hazard,
        "findings": [],
        "raw": hazard,
    }
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": full_result,
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    page = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor=None,
        offset=0,
        limit=50,
        max_bytes=32768,
    )
    assert page["summary"] == hazard, (
        f"§6 (content hazards): escaping-heavy content must survive round-trip; "
        f"got {page.get('summary')!r}"
    )


def test_t16_secret_redacted_in_stored_and_returned_content(tmp_path: Path) -> None:
    """S16.4 item 7.6: the full result must be redacted with sanitize_value
    *before* it is stored, so the secret never lands in the CCR chunk nor in
    the returned projection. (The original body asserted on a string the test
    itself built from unredacted input, so no implementation could pass it;
    it now drives the real compact store.)"""
    test_t16_secret_redacted_before_compact_store(tmp_path)


def test_t16_cursor_page_replay_is_deterministic(tmp_path: Path) -> None:
    full_result = {
        "tool": "lint",
        "status": "warn",
        "duration_ms": 1,
        "summary": "replay",
        "findings": [
            {
                "path": f"f{i}.py",
                "line": i,
                "severity": "warn",
                "message": "x",
                "fingerprint": str(i) * 4,
            }
            for i in range(10)
        ],
    }
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": full_result,
            "finding_ids": [str(i) * 4 for i in range(10)],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    kwargs = {
        "handle": handle,
        "view": "result",
        "cursor": None,
        "offset": 0,
        "limit": 5,
        "max_bytes": 32768,
    }
    first = _retrieve(tmp_path, **kwargs)
    second = _retrieve(tmp_path, **kwargs)
    assert first == second, "§6 (Paging): identical requests must replay identically"


def test_t16_malformed_cursor_gives_result_cursor_invalid(tmp_path: Path) -> None:
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {"tool": "lint"},
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    result = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor="not-base64url!!",
        offset=None,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["error"]["code"] == "RESULT_CURSOR_INVALID", (
        f"§3 item 9: a malformed cursor must give RESULT_CURSOR_INVALID; got {result!r}"
    )


def test_t16_cross_root_cursor_gives_result_cursor_invalid(tmp_path: Path) -> None:
    import base64

    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {"tool": "lint"},
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    other_root_hash = hashlib.sha256(str(tmp_path / "other").encode()).hexdigest()
    forged = base64.urlsafe_b64encode(
        _canonical_json(
            {
                "v": 1,
                "root": other_root_hash,
                "handle": handle,
                "view": "result",
                "next": 0,
                "limit": 50,
                "max_bytes": 32768,
            }
        ).encode()
    ).decode()
    result = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor=forged,
        offset=None,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["error"]["code"] == "RESULT_CURSOR_INVALID", (
        f"§3 item 9: a cross-root cursor must give RESULT_CURSOR_INVALID; got {result!r}"
    )


def test_t16_budget_changed_cursor_gives_result_cursor_invalid(tmp_path: Path) -> None:
    import base64

    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {"tool": "lint"},
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    root_hash = hashlib.sha256(str(tmp_path).encode()).hexdigest()
    stale = base64.urlsafe_b64encode(
        _canonical_json(
            {
                "v": 1,
                "root": root_hash,
                "handle": handle,
                "view": "result",
                "next": 0,
                "limit": 50,
                "max_bytes": 4096,
            }
        ).encode()
    ).decode()
    result = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor=stale,
        offset=None,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["error"]["code"] == "RESULT_CURSOR_INVALID", (
        f"§3 item 9: a budget-changed cursor must give RESULT_CURSOR_INVALID; got {result!r}"
    )


def test_t16_view_changed_cursor_gives_result_cursor_invalid(tmp_path: Path) -> None:
    import base64

    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {"tool": "lint"},
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    root_hash = hashlib.sha256(str(tmp_path).encode()).hexdigest()
    switched = base64.urlsafe_b64encode(
        _canonical_json(
            {
                "v": 1,
                "root": root_hash,
                "handle": handle,
                "view": "bytes",
                "next": 0,
                "limit": 50,
                "max_bytes": 32768,
            }
        ).encode()
    ).decode()
    result = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor=switched,
        offset=None,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["error"]["code"] == "RESULT_CURSOR_INVALID", (
        f"§3 item 9: a view-changed cursor must give RESULT_CURSOR_INVALID; got {result!r}"
    )


def test_t16_cursor_and_offset_together_gives_result_view_invalid(
    tmp_path: Path,
) -> None:
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {"tool": "lint"},
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    result = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor="anything",
        offset=0,
        limit=50,
        max_bytes=32768,
    )
    assert result["metadata"]["error"]["code"] == "RESULT_VIEW_INVALID", (
        f"§3 item 9: cursor and offset together must give RESULT_VIEW_INVALID; got {result!r}"
    )


def test_t16_minimum_budget_with_long_root_path(tmp_path: Path) -> None:
    long_root = tmp_path
    for _ in range(4):
        long_root = long_root / "very-long-directory-segment-name"
    long_root.mkdir(parents=True)
    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {
                "tool": "lint",
                "status": "ok",
                "duration_ms": 1,
                "summary": "ok",
                "findings": [],
            },
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(long_root, content)
    page = _retrieve(
        long_root,
        handle=handle,
        view="result",
        cursor=None,
        offset=0,
        limit=50,
        max_bytes=4096,
    )
    # A successful page carries no `metadata.error` at all, so the original
    # `page["metadata"]["error"]["code"]` raised KeyError on success.
    assert (page["metadata"].get("error") or {}).get("code") != (
        "RESULT_BUDGET_TOO_SMALL"
    ), (
        "§6 (Size edges): the minimum 4096-byte budget must fit even with a long "
        f"root path; got {page!r}"
    )
    assert page["metadata"]["delivery"]["complete"] is True, page


def test_t16_mcp_response_fits_under_max_bytes(tmp_path: Path) -> None:
    from mcp.types import CallToolResult, TextContent

    content = _canonical_json(
        {
            "version": 1,
            "created_at": "2026-01-01T00:00:00Z",
            "full_result": {
                "tool": "lint",
                "status": "ok",
                "duration_ms": 1,
                "summary": "ok",
                "findings": [],
            },
            "finding_ids": [],
        }
    )
    handle = _seed_ccr_row(tmp_path, content)
    page = _retrieve(
        tmp_path,
        handle=handle,
        view="result",
        cursor=None,
        offset=0,
        limit=50,
        max_bytes=4096,
    )
    envelope = CallToolResult(content=[TextContent(type="text", text=json.dumps(page))])
    serialized = envelope.model_dump_json(by_alias=True, exclude_none=True).encode()
    assert len(serialized) + 96 <= 4096, (
        "§3 item 8/R16.6: the real serialized MCP response plus the fixed 96-byte "
        f"JSON-RPC reserve must fit under max_bytes; got {len(serialized) + 96} bytes"
    )


def test_t16_strict_v1_roundtrip_preserves_scope_in_extensions() -> None:
    """Keep-green guard: adapt_legacy_tool_result already folds any unknown
    top-level key (e.g. "metadata") into extensions generically. T16 must not
    break this passthrough when it starts populating metadata.scope."""
    legacy = {
        "tool": "lint",
        "status": "ok",
        "duration_ms": 1,
        "summary": "ok",
        "findings": [],
        "metadata": {"scope": {"version": 1, "kind": "file", "coverage": "complete"}},
    }
    v1 = adapt_legacy_tool_result(legacy)
    round_tripped = validate_tool_result(json.loads(json.dumps(v1.to_dict())))
    assert round_tripped.extensions["metadata"]["scope"] == {
        "version": 1,
        "kind": "file",
        "coverage": "complete",
    }
