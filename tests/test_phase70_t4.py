"""Phase 70 T4 test matrix: Core MCP profile with full compatibility.

Brief: .scratch/phase-70-design-gate/W1-T1-T7-T23.md ## T4 (also §0 X1, X-HOSTS).
Predecessors T23 (StatusTool/rush_status) and T6 (RushFastMCP/schemas) are not
implemented in this worktree. T17 (CheckTool/rush_check) is also absent and is
called out per-case below since it is not one of the two named predecessors.
No network calls; no dependency on real `claude`/`codex` host binaries
(X-HOSTS pytest ban) -- native calls are simulated via monkeypatched
`shutil.which`/`subprocess.run`. Every filesystem write happens under
`tmp_path`; `Path.home` is monkeypatched so nothing touches the real $HOME.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from rush.cli import cli
from rush.integrations import agents as agents_mod
from rush.integrations.agents import build_stdio_entry, plan_agent_registration
from rush.mcp import build_server, build_server_instructions
from rush.mcp_support import tool_registry as tool_registry_mod
from rush.tools import ALL_TOOLS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUSH_BINARY = "/usr/local/bin/rush"


@pytest.fixture(autouse=True)
def _isolated_home(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Every test (and every stdio child, which inherits this environment)
    runs with HOME and the XDG/host config roots in a temp dir, so no data
    root or host config (`~/.claude.json`, `~/.codex/`) resolves to the real
    home."""
    home = tmp_path_factory.mktemp("isolated-home")
    monkeypatch.setenv("HOME", str(home))
    for name in (
        "XDG_DATA_HOME",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
    ):
        monkeypatch.setenv(name, str(home / name.lower()))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / ".claude"))
    monkeypatch.setenv("CODEX_HOME", str(home / ".codex"))
    return home


CORE_TOOL_NAMES = frozenset(
    {
        "rush_status",
        "rush_check",
        "rush_lint",
        "rush_review",
        "rush_security",
        "rush_test",
        "rush_memory",
    }
)


def _stdio_params(
    *extra_args: str,
    env_overrides: dict[str, str] | None = None,
    cwd: Path = PROJECT_ROOT,
):
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "rush.cli", "mcp", "serve", *extra_args],
        cwd=cwd,
        env={
            **os.environ,
            "PYTHONPATH": str(PROJECT_ROOT / "src"),
            **(env_overrides or {}),
        },
    )


async def _initialize_list_and_call(
    params: StdioServerParameters,
    tool_name: str,
    args: dict[str, object],
    call_timeout: float = 10,
):
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as server_stderr:
        async with (
            stdio_client(params, errlog=server_stderr) as (read, write),
            ClientSession(read, write) as session,
        ):
            await asyncio.wait_for(session.initialize(), timeout=10)
            listed = await asyncio.wait_for(session.list_tools(), timeout=10)
            names = {tool.name for tool in listed.tools}
            response = await asyncio.wait_for(
                session.call_tool(tool_name, args), timeout=call_timeout
            )
            return names, response


# --- Required behavior 1-4: profile validation and exact tool sets --------


def test_build_server_rejects_unknown_profile_before_fastmcp_construction(monkeypatch):
    """`build_server(profile="bogus")` raises ValueError before FastMCP() runs.

    RED: `build_server()` has no `profile` kwarg yet -> TypeError, not ValueError.
    """
    from mcp.server.fastmcp import FastMCP

    constructed: list[bool] = []
    original_init = FastMCP.__init__

    def spy_init(self, *args, **kwargs):
        constructed.append(True)
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(FastMCP, "__init__", spy_init)

    with pytest.raises(ValueError):
        build_server(profile="bogus")
    assert constructed == []


def test_serve_cli_rejects_unknown_profile_with_exit_2_and_valid_values():
    """`mcp serve --profile bogus` -> Click usage error, exit 2, lists "core, full".

    RED: `serve` has no `--profile` option today; Click's own "no such option"
    message never mentions "core, full".
    """
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "serve", "--profile", "bogus"])
    assert result.exit_code == 2
    assert "core, full" in result.output


def test_build_server_default_profile_equals_explicit_full_profile():
    """`build_server()` (default) and `build_server(profile="full")` register the same names.

    RED: `build_server(profile="full")` -> TypeError, no `profile` kwarg.
    """
    default_server = build_server()
    default_names = {tool.name for tool in asyncio.run(default_server.list_tools())}

    full_server = build_server(profile="full")
    full_names = {tool.name for tool in asyncio.run(full_server.list_tools())}

    assert full_names == default_names


def test_build_server_core_profile_registers_exactly_seven_names():
    """`build_server(profile="core")` == exactly the 7 names in CORE_TOOL_NAMES.

    RED: `profile` kwarg doesn't exist -> TypeError. Also depends on rush_status
    (T23, not implemented here) and rush_check (T17/CheckTool, not implemented
    and not built by this brief's other tasks either) actually being
    registered; even once profile-filtering exists, this exact case stays
    RED-via-T23/T17 until those tools are registered somewhere in the catalog.
    """
    core_server = build_server(profile="core")
    names = {tool.name for tool in asyncio.run(core_server.list_tools())}
    assert names == CORE_TOOL_NAMES


def test_build_server_full_profile_is_baseline_plus_status_and_check():
    """Full = today's registered baseline names ∪ {rush_status, rush_check}.

    RED: `profile` kwarg doesn't exist -> TypeError.
    """
    baseline_server = build_server()
    baseline_names = {tool.name for tool in asyncio.run(baseline_server.list_tools())}
    expected_full = baseline_names | {"rush_status", "rush_check"}

    full_server = build_server(profile="full")
    full_names = {tool.name for tool in asyncio.run(full_server.list_tools())}
    assert full_names == expected_full


def test_build_server_instructions_name_set_matches_full_profile_tool_names():
    """Instructions mention exactly the `tools/list` names, for a profile.

    RED: `build_server_instructions()` takes no `profile` argument -> TypeError.
    """
    full_server = build_server(profile="full")
    list_names = {tool.name for tool in asyncio.run(full_server.list_tools())}

    instructions = build_server_instructions(profile="full")
    assert all(name in instructions for name in list_names)


def test_register_all_tools_include_filter_restricts_registered_names():
    """`register_all_tools(..., include=...)` only registers the given tool names.

    RED: `register_all_tools` has no `include` parameter -> TypeError.
    """
    from rush.mcp_support.tool_registry import InvocationExecutor

    class _FakeServer:
        def __init__(self) -> None:
            self.registered: list[str] = []

        def add_tool(self, *, fn, name, **_kwargs) -> None:
            self.registered.append(name)

    server = _FakeServer()
    executor = InvocationExecutor()
    include = frozenset({"rush_lint", "rush_review"})

    tool_registry_mod.register_all_tools(server, executor, ALL_TOOLS, include=include)
    assert set(server.registered) <= include


# --- Required behavior 5: memory-session ignores profile -------------------


def test_stdio_core_profile_lists_exact_tools_and_gates_unlisted_calls():
    """core profile: tools/list == 7 names; rush_scan -> Unknown tool; rush_lint -> ok.

    RED: `--profile` is not a recognized `serve` option today; the child exits
    on a Click usage error before any MCP handshake, so `session.initialize()`
    never completes and the stdio call fails/times out instead of returning
    the exact set and gated-call behavior asserted below.
    """

    async def _run():
        params = _stdio_params("--profile", "core")
        names, response = await _initialize_list_and_call(
            params, "rush_scan", {"request": {"path": "."}}
        )
        assert names == CORE_TOOL_NAMES
        assert response.isError
        assert "Unknown tool: rush_scan" in response.content[0].text

        lint_names, lint_response = await _initialize_list_and_call(
            params, "rush_lint", {"path": "."}
        )
        assert lint_names == CORE_TOOL_NAMES
        assert not lint_response.isError

    asyncio.run(_run())


async def _memory_session_tool_names(profile_args: tuple[str, ...]) -> set[str]:
    params = _stdio_params(
        "--memory-session",
        "session-1",
        *profile_args,
        env_overrides={"RUSH_MEMORY_CAPABILITY": "receive,expand,related,resume"},
    )
    with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as stderr:
        async with (
            stdio_client(params, errlog=stderr) as (read, write),
            ClientSession(read, write) as session,
        ):
            await asyncio.wait_for(session.initialize(), timeout=10)
            listed = await asyncio.wait_for(session.list_tools(), timeout=10)
            return {tool.name for tool in listed.tools}


def test_stdio_memory_session_without_profile_stays_restricted():
    """`--memory-session S` with no `--profile` -> only `rush_memory`.

    Keep-green guard: today's restricted receiver, unchanged by T4.
    """
    assert asyncio.run(_memory_session_tool_names(())) == {"rush_memory"}


def test_stdio_memory_session_ignores_profile_and_stays_restricted(tmp_path):
    """`--memory-session S` + any `--profile` -> only `rush_memory`, unwidened.

    RED: `--profile` is not a recognized `serve` option today, so the child
    process fails to start (Click usage error) before the handshake completes.
    """
    for profile_args in (("--profile", "core"), ("--profile", "full")):
        names = asyncio.run(_memory_session_tool_names(profile_args))
        assert names == {"rush_memory"}


# --- Required behavior 6: new-registration argv defaults to core -----------


def test_build_stdio_entry_default_args_use_core_profile():
    """New config-edit registrations default to `mcp serve --profile core`.

    RED: `build_stdio_entry`'s default is still `("mcp", "serve")`.
    """
    entry = build_stdio_entry("/usr/local/bin/rush")
    assert entry["args"] == ["mcp", "serve", "--profile", "core"]


def test_native_claude_add_argv_uses_core_profile_for_new_registrations(
    monkeypatch, tmp_path
):
    """New native `claude mcp add` registrations append `--profile core`.

    RED: `plan_agent_registration`'s native command still ends in
    `("mcp", "serve")` with no profile flag.
    """
    monkeypatch.setattr(agents_mod.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        agents_mod.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name == "claude" else None,
    )

    plan = plan_agent_registration(
        "claude-code",
        rush_binary="/usr/local/bin/rush",
        home=tmp_path,
        os_name="Darwin",
    )
    assert plan.native_command is not None
    assert plan.native_command[-5:] == (
        "/usr/local/bin/rush",
        "mcp",
        "serve",
        "--profile",
        "core",
    )


# --- Test matrix: existing installations stay unchanged (keep-green) -------


def test_existing_legacy_entry_connect_without_profile_keeps_args_byte_for_byte(
    tmp_path,
):
    """Re-registering over an existing entry never rewrites its `args`.

    Keep-green guard: this is today's real behavior
    (`test_agent_connection.py:214,257`) and must still hold once T4 lands.
    """
    from rush.integrations.agents import (
        ADAPTERS,
        apply_agent_registration,
        discover_agents,
    )

    config_path = ADAPTERS["windsurf"].config_paths("Darwin", tmp_path)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {"mcpServers": {"legacy": {"command": "old-rush", "args": ["serve"]}}}
    config_path.write_text(json.dumps(legacy), encoding="utf-8")

    plan = plan_agent_registration(
        "windsurf", rush_binary="/usr/local/bin/rush", home=tmp_path, os_name="Darwin"
    )
    apply_agent_registration(plan)

    plan2 = plan_agent_registration(
        "windsurf", rush_binary="/usr/local/bin/rush", home=tmp_path, os_name="Darwin"
    )
    apply_agent_registration(plan2)

    final_text = config_path.read_text(encoding="utf-8")
    assert final_text.count('"rush"') == 1
    statuses = discover_agents(
        home=tmp_path, os_name="Darwin", rush_binary="/usr/local/bin/rush"
    )
    windsurf = next(s for s in statuses if s.agent_id == "windsurf")
    assert windsurf.status == "registered"


def test_install_all_agents_over_legacy_entry_does_not_narrow_args(tmp_path):
    """`rush install --agents all` over an existing entry never rewrites its args.

    Keep-green guard: `_process_agents` skips any agent whose memory state is
    already `connected` -- an existing installation is untouched, exactly as
    a bare `agent connect` re-run is untouched above.
    """
    from rush.integrations.agents import (
        ADAPTERS,
        acknowledge_agent_connection,
        apply_agent_registration,
        initialize_agent_memory,
    )
    from rush.tools.install import InstallTool

    config_path = ADAPTERS["windsurf"].config_paths("Darwin", tmp_path)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    plan = plan_agent_registration(
        "windsurf", rush_binary="/usr/local/bin/rush", home=tmp_path, os_name="Darwin"
    )
    apply_agent_registration(plan)
    before_text = config_path.read_text(encoding="utf-8")

    initialize_agent_memory(
        "windsurf", "install", project_root=None, data_root=tmp_path, consent=True
    )
    acknowledge_agent_connection(
        "windsurf", "install", project_root=None, data_root=tmp_path
    )

    InstallTool()._process_agents(
        agents_flag="all",
        memory="on",
        home=tmp_path,
        os_name="Darwin",
        rush_binary="/usr/local/bin/rush",
        session_id="install",
        data_root=tmp_path,
        permissions=None,
    )

    assert config_path.read_text(encoding="utf-8") == before_text


# --- Test matrix: explicit migration CLI (`agent connect --profile --yes`) -


def _connect_args(agent_id: str, *, profile: str | None, yes: bool) -> list[str]:
    args = [
        "agent",
        "connect",
        agent_id,
        "--session",
        "s1",
        "--rush-binary",
        RUSH_BINARY,
        "--allow-cache-write",
        "--allow-artifact-write",
    ]
    if profile is not None:
        args += ["--profile", profile]
    if yes:
        args.append("--yes")
    return args


def test_agent_connect_profile_migration_preview_only_without_yes_leaves_bytes_unchanged(
    monkeypatch, tmp_path
):
    """`agent connect --profile core` (no `--yes`) previews only; file untouched.

    RED: `agent connect` has no `--profile`/`--yes` options today -> Click
    "no such option", exit code 2 instead of a clean preview exit.
    """
    monkeypatch.setattr(agents_mod.Path, "home", staticmethod(lambda: tmp_path))
    config_path = agents_mod.ADAPTERS["cursor"].config_paths("Darwin", tmp_path)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    original = json.dumps({"mcpServers": {}})
    config_path.write_text(original, encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, _connect_args("cursor", profile="core", yes=False))
    assert result.exit_code == 0
    assert config_path.read_text(encoding="utf-8") == original


def test_agent_connect_profile_migration_with_yes_rewrites_config(
    monkeypatch, tmp_path
):
    """`agent connect --profile core --yes` rewrites the entry to the core args.

    RED: `agent connect` has no `--profile`/`--yes` options today.
    """
    monkeypatch.setattr(agents_mod.Path, "home", staticmethod(lambda: tmp_path))
    config_path = agents_mod.ADAPTERS["cursor"].config_paths("Darwin", tmp_path)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(cli, _connect_args("cursor", profile="core", yes=True))
    assert result.exit_code == 0
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["mcpServers"]["rush"]["args"][-2:] == ["--profile", "core"]


def test_agent_connect_concurrent_edit_between_preview_and_apply_is_a_conflict(
    monkeypatch, tmp_path
):
    """A config edit landing between preview and write aborts with no write.

    RED: no digest-recheck mechanism exists (`agent connect` has no
    `--profile`/`--yes` options at all yet), so this cannot be a clean "no
    write, conflict reported" outcome today.
    """
    monkeypatch.setattr(agents_mod.Path, "home", staticmethod(lambda: tmp_path))
    config_path = agents_mod.ADAPTERS["cursor"].config_paths("Darwin", tmp_path)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    concurrent_write = json.dumps({"mcpServers": {"other": {"command": "x"}}})

    original_cas_replace = agents_mod.cas_replace_file
    calls: list[bytes] = []

    def racing_cas_replace(path, data, **kwargs):
        calls.append(data)
        config_path.write_text(concurrent_write, encoding="utf-8")
        return original_cas_replace(path, data, **kwargs)

    monkeypatch.setattr(agents_mod, "cas_replace_file", racing_cas_replace)

    runner = CliRunner()
    result = runner.invoke(cli, _connect_args("cursor", profile="core", yes=True))
    assert result.exit_code == 0
    assert config_path.read_text(encoding="utf-8") == concurrent_write
    assert "conflict" in result.output.lower()


def test_agent_connect_native_add_failure_falls_back_to_add_json(monkeypatch, tmp_path):
    """A failing `claude mcp add` retries via `claude mcp add-json` with the captured JSON.

    RED: no add-json fallback exists in `apply_agent_registration`'s native
    branch today, and `agent connect` has no `--profile`/`--yes` options.
    """
    monkeypatch.setattr(agents_mod.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(
        agents_mod.shutil,
        "which",
        lambda name: f"/usr/bin/{name}" if name == "claude" else None,
    )

    captured = {"type": "stdio", "command": "/old/rush", "args": ["mcp", "serve"]}
    (tmp_path / ".claude.json").write_text(
        json.dumps({"mcpServers": {"rush": captured}}), encoding="utf-8"
    )
    calls: list[list[str]] = []

    def fake_run(command, **_kwargs):
        calls.append(list(command))
        failed = list(command[2:4]) == ["add", "rush"]
        return subprocess.CompletedProcess(
            command, returncode=1 if failed else 0, stdout="", stderr="boom"
        )

    monkeypatch.setattr(agents_mod.subprocess, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(cli, _connect_args("claude-code", profile="core", yes=True))
    assert result.exit_code == 0
    assert any(call and call[2:4] == ["add-json", "rush"] for call in calls)
    [restore] = [call for call in calls if call[2:4] == ["add-json", "rush"]]
    assert json.loads(restore[4]) == captured


# --- Test matrix: schema profile is not an authorization grant --------------


def test_rush_check_on_core_without_allow_build_is_not_run(tmp_path):
    """`rush_check` on the core profile, called with no `allow_build` grant, is skipped/not run.

    RED-via-T17 (CheckTool is unimplemented anywhere in this repo -- it is not
    one of T23/T6, but it is likewise a predecessor this brief does not build)
    plus the missing `--profile` server option: the child never advertises
    `rush_check` at all, so the call fails as "Unknown tool", not as a
    permission-gated skip.
    """

    # A project whose test step would run under a build grant, so a skip is
    # the permission gate and not "no test project found".
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "fx"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )

    async def _run():
        params = _stdio_params("--profile", "core", cwd=tmp_path)
        names, response = await _initialize_list_and_call(
            # The real six-step suite with cold engine caches in the isolated
            # home takes ~30s, well past the 10s used for single tools.
            params,
            "rush_check",
            {"path": "."},
            call_timeout=180,
        )
        assert "rush_check" in names
        payload = json.loads(response.content[0].text)
        [test_step] = [
            child
            for child in payload["metadata"]["children"]
            if child["tool"] == "test"
        ]
        assert test_step["status"] in {"skipped", "not_run"}
        assert "allow-build" in test_step["summary"]

    asyncio.run(_run())


# --- Implementation checks: Codex TOML, args preservation, MCP strict fields --


def test_codex_toml_profile_migration_previews_then_rewrites_only_the_profile(
    monkeypatch, tmp_path
):
    """Codex (TOML): the preview names path, current/new args and digest; with
    `--yes` only the `rush` table's args gain `--profile core`, every other
    byte of the file is kept."""
    import hashlib

    monkeypatch.setattr(agents_mod.Path, "home", staticmethod(lambda: tmp_path))
    config_path = agents_mod.ADAPTERS["codex"].config_paths("Darwin", tmp_path)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    head = '# keep me\nmodel = "o3"\n\n'
    tail = '\n[mcp_servers.other]\ncommand = "npx"\n'
    original = (
        head
        + '[mcp_servers.rush]\ncommand = "/old/rush"\nargs = ["mcp", "serve"]\n'
        + tail
    )
    config_path.write_text(original, encoding="utf-8")
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()

    preview_only = CliRunner().invoke(
        cli, _connect_args("codex", profile="core", yes=False)
    )
    assert preview_only.exit_code == 0, preview_only.output
    assert str(config_path) in preview_only.output
    assert "['mcp', 'serve']" in preview_only.output
    assert "['mcp', 'serve', '--profile', 'core']" in preview_only.output
    assert digest in preview_only.output
    assert config_path.read_text(encoding="utf-8") == original

    applied = CliRunner().invoke(cli, _connect_args("codex", profile="core", yes=True))
    assert applied.exit_code == 0, applied.output
    text = config_path.read_text(encoding="utf-8")
    assert text.startswith(head) and text.endswith(tail)
    assert 'args = ["mcp", "serve", "--profile", "core"]' in text
    assert f'command = "{RUSH_BINARY}"' in text


def test_connect_without_profile_repairs_command_and_keeps_existing_args(tmp_path):
    """No `--profile`: a stale command is repaired, the args stay exactly as
    they were (no silent narrowing to core), and discovery classifies them."""
    from rush.integrations.agents import (
        ADAPTERS,
        apply_agent_registration,
        discover_agents,
    )

    config_path = ADAPTERS["windsurf"].config_paths("Darwin", tmp_path)[0]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    legacy_args = ["mcp", "serve", "--project", "p1"]
    config_path.write_text(
        json.dumps({"mcpServers": {"rush": {"command": "/old", "args": legacy_args}}}),
        encoding="utf-8",
    )

    plan = plan_agent_registration(
        "windsurf", rush_binary=RUSH_BINARY, home=tmp_path, os_name="Darwin"
    )
    assert apply_agent_registration(plan).ok
    entry = json.loads(config_path.read_text(encoding="utf-8"))["mcpServers"]["rush"]
    assert entry == {"command": RUSH_BINARY, "args": legacy_args}

    before = config_path.read_bytes()
    again = plan_agent_registration(
        "windsurf", rush_binary=RUSH_BINARY, home=tmp_path, os_name="Darwin"
    )
    assert again.unchanged
    assert apply_agent_registration(again).ok
    assert config_path.read_bytes() == before

    [windsurf] = [
        status
        for status in discover_agents(
            home=tmp_path, os_name="Darwin", rush_binary=RUSH_BINARY
        )
        if status.agent_id == "windsurf"
    ]
    assert windsurf.profile == "legacy_full"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["mcp", "serve"], "legacy_full"),
        (["mcp", "serve", "--profile", "core"], "core"),
        (["mcp", "serve", "--profile=full"], "full"),
        (["mcp", "serve", "--profile", "bogus"], "unrecognized"),
        (["serve"], "unrecognized"),
        (["mcp", "serve", "--memory-session", "s1"], "unrecognized"),
    ],
)
def test_registration_profile_classification(args, expected):
    assert agents_mod.classify_registration_profile({"args": args}) == expected


@pytest.mark.parametrize(
    "extra",
    [
        {"profile": "bogus"},
        {"profile": 1},
        {"profile": "core", "confirm_profile_migration": "yes"},
        {"confirm_profile_migration": True},
    ],
)
def test_mcp_agent_connection_profile_fields_are_strict(extra):
    """`rush_agent_connection` rejects a bad `profile`/`confirm_profile_migration`
    before anything is planned or written."""
    from rush.tools.agent_connection import AgentConnectionTool

    result = AgentConnectionTool().handle_request(
        {
            "schema_version": 1,
            "operation": "connect",
            "agent_id": "cursor",
            "session_id": "s1",
            "rush_binary": RUSH_BINARY,
            "allow_cache_write": True,
            "allow_artifact_write": True,
            **extra,
        }
    )
    assert result["status"] == "error"
    assert result["raw"]["error"]["code"] == "INVALID_REQUEST"


@pytest.mark.parametrize(
    ("agent", "host"), [("claude-code", "claude"), ("codex", "codex")]
)
def test_native_plugin_profile_preview_migration_and_omission(
    tmp_path, monkeypatch, agent, host
):
    from rush.permissions import ExecutionPermissions
    from rush.setup.provision import default_data_root
    from rush.tools import install as install_mod
    from rush.tools.agent_connection import AgentConnectionTool

    home = Path.home()
    data = default_data_root()
    root = tmp_path / "project"
    root.mkdir()
    config = agents_mod.ADAPTERS[agent].config_paths(sys.platform, home)[0]
    config.parent.mkdir(parents=True, exist_ok=True)
    original = (
        b'{"mcpServers":{}}\n' if host == "claude" else b"# untouched host config\n"
    )
    config.write_bytes(original)
    roots = agents_mod.materialize_agent_plugins(
        rush_binary=RUSH_BINARY, data_root=data
    )
    plugin = roots[host]
    agents_mod.record_native_plugin_install(
        host=host, plugin_root=plugin, data_root=data
    )
    mcp = plugin / "rush" / (".mcp.json" if host == "claude" else "mcp.json")
    extra_args = ["--project", "native-project", "--session", "native-session"]
    value = json.loads(mcp.read_bytes())
    value["mcpServers"]["rush"]["args"].extend(extra_args)
    mcp.write_text(json.dumps(value))
    with agents_mod._ledger_lock(data):
        rows, version = agents_mod._load_ledger(data)
        for row in rows.values():
            if row["path"] == str(plugin):
                row["written_sha256"] = agents_mod.owned_path_digest(plugin)
        agents_mod._save_ledger(data, rows, version)
    before = mcp.read_bytes()
    ledger = agents_mod.ownership_ledger_path(data).read_bytes()
    calls = []

    def refresh(commands):
        calls.append(commands)
        # Native refresh must run after ledger lock release.
        with agents_mod._ledger_lock(data):
            pass

    monkeypatch.setattr(install_mod, "_run_host_commands", refresh)
    tool = AgentConnectionTool()
    options = {
        "action": "connect",
        "session_id": "profile",
        "project_root": root,
        "rush_binary": RUSH_BINARY,
        "home": home,
        "data_root": data,
        "permissions": ExecutionPermissions(cache_write=True, artifact_write=True),
    }
    for consent, state in ((False, "pending"), (lambda preview: False, "declined")):
        result = tool.run(agent, profile="full", confirm_profile=consent, **options)
        assert result["status"] == "skipped"
        assert result["raw"]["migration"]["state"] == state
        assert result["raw"]["migration"]["config_path"] == str(mcp)
        assert mcp.read_bytes() == before
        assert agents_mod.ownership_ledger_path(data).read_bytes() == ledger
        assert not agents_mod.agent_memory_store_path(project_root=root).exists()
        assert calls == []
    result = tool.run(agent, profile="full", confirm_profile=True, **options)
    assert result["status"] == "ok", result
    assert result["raw"]["migration"]["state"] == "applied"
    assert result["raw"]["probe"]["profile"] == "full"
    assert result["raw"]["apply"]["method"] == "native_plugin"
    assert "restart" in result["raw"]["reload"]
    assert json.loads(mcp.read_bytes())["mcpServers"]["rush"]["args"] == [
        "mcp",
        "serve",
        *extra_args,
        "--profile",
        "full",
    ]
    assert calls == [install_mod._plugin_upgrade_commands(host, plugin)]
    full_bytes = mcp.read_bytes()
    omitted = tool.run(agent, **options)
    assert omitted["status"] == "ok"
    assert mcp.read_bytes() == full_bytes
    assert len(calls) == 1
    rows = json.loads(agents_mod.ownership_ledger_path(data).read_bytes())[
        "data"
    ].values()
    assert all(
        row["written_sha256"] == agents_mod.owned_path_digest(plugin)
        for row in rows
        if row["path"] == str(plugin)
    )
    assert config.read_bytes() == original

    core = tool.run(agent, profile="core", confirm_profile=True, **options)
    assert core["status"] == "ok"
    assert json.loads(mcp.read_bytes())["mcpServers"]["rush"]["args"] == [
        "mcp",
        "serve",
        *extra_args,
        "--profile",
        "core",
    ]
    assert calls == [install_mod._plugin_upgrade_commands(host, plugin)] * 2
    assert config.read_bytes() == original
