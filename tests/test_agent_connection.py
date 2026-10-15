"""Tests for `rush.integrations.agents` (Phase 65 P65-05, F35).

Every filesystem interaction below points at an isolated tmp_path `home` --
never a real installed client's actual config file. `discover_agents` /
`plan_agent_registration` / `apply_agent_registration` / `probe_agent_
connection` all take an explicit `home` (and, for the native path, PATH is
monkeypatched to a fake script) so nothing here can touch a real Claude
Desktop, Cursor, Windsurf, Zed, or Codex CLI installation.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import os
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from rush.integrations import agents as agents_mod
from rush.integrations.agents import (
    ADAPTERS,
    AgentConnectionError,
    MalformedConfigError,
    ReadOnlyConfigError,
    UnknownAgentError,
    apply_agent_registration,
    build_stdio_entry,
    discover_agents,
    plan_agent_registration,
    probe_agent_connection,
    resolve_rush_binary,
)

RUSH_BINARY = "/opt/rush/bin/rush"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _home_with(
    tmp_path: Path, adapter_id: str, text: str, *, os_name: str = "Darwin"
) -> Path:
    home = tmp_path / adapter_id
    path = ADAPTERS[adapter_id].config_paths(os_name, home)[0]
    _write(path, text)
    return home


CLAUDE_DESKTOP_JSON = json.dumps(
    {
        "mcpServers": {
            "other-tool": {
                "command": "node",
                "args": ["server.js"],
                "env": {"API_KEY": "sk-secret-value"},
            }
        },
        "theme": "dark",
    },
    indent=2,
)

CLAUDE_CODE_JSON = json.dumps(
    {
        "mcpServers": {"other-tool": {"command": "npx", "args": ["other"]}},
        "userId": "abc123",
    },
    indent=2,
)

CURSOR_JSON = json.dumps({"mcpServers": {}}, indent=2)

WINDSURF_JSON = json.dumps(
    {"mcpServers": {"legacy": {"command": "old-rush", "args": []}}}, indent=2
)

ZED_JSONC = """{
  // user theme -- must survive every edit
  "theme": "one-dark",
  "context_servers": {
    // pre-existing server, must survive
    "other": {
      "command": {"path": "node", "args": ["x.js"]}
    }
  }
}
"""

CODEX_TOML = """# codex config -- comment must survive
model = "o3"

[mcp_servers.other]
command = "npx"
args = ["other-server"]
"""


# --- OS-specific path locations ------------------------------------------------


@pytest.mark.parametrize("os_name", ["Darwin", "Windows", "Linux"])
def test_config_paths_resolve_per_os(os_name: str) -> None:
    home = Path("/fake/home")
    for adapter in ADAPTERS.values():
        candidates = adapter.config_paths(os_name, home)
        assert candidates
        for candidate in candidates:
            assert candidate.is_absolute()
            assert str(home) in str(candidate)


def test_claude_desktop_path_is_platform_specific() -> None:
    home = Path("/fake/home")
    assert "Library" in str(ADAPTERS["claude-desktop"].config_paths("Darwin", home)[0])
    assert "AppData" in str(ADAPTERS["claude-desktop"].config_paths("Windows", home)[0])
    assert ".config" in str(ADAPTERS["claude-desktop"].config_paths("Linux", home)[0])


# --- restart-required state -----------------------------------------------------


def test_restart_required_flags() -> None:
    expected = {
        "claude-desktop": True,
        "claude-code": False,
        "cursor": True,
        "windsurf": True,
        "zed": True,
        "codex": False,
    }
    for agent_id, flag in expected.items():
        assert ADAPTERS[agent_id].restart_required is flag


# --- per-adapter format-preserving registration ----------------------------------


@pytest.mark.parametrize(
    "adapter_id,fixture_text",
    [
        ("claude-desktop", CLAUDE_DESKTOP_JSON),
        ("claude-code", CLAUDE_CODE_JSON),
        ("cursor", CURSOR_JSON),
        ("windsurf", WINDSURF_JSON),
        ("zed", ZED_JSONC),
        ("codex", CODEX_TOML),
    ],
)
def test_adapter_registration_preserves_unrelated_settings(
    tmp_path: Path, adapter_id: str, fixture_text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Force config-edit even for claude-code -- native path has its own test.
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    home = _home_with(tmp_path, adapter_id, fixture_text)

    plan = plan_agent_registration(
        adapter_id, rush_binary=RUSH_BINARY, home=home, os_name="Darwin"
    )
    assert plan.method == "config-edit"
    assert plan.backup_path is not None
    result = apply_agent_registration(plan)
    assert result.ok, result.error
    assert plan.backup_path.exists()
    assert plan.backup_path.read_text(encoding="utf-8") == fixture_text

    assert plan.config_path is not None
    new_text = plan.config_path.read_text(encoding="utf-8")

    if adapter_id == "zed":
        assert "// user theme -- must survive every edit" in new_text
        assert '"theme": "one-dark"' in new_text
        assert '"path": "node"' in new_text
    elif adapter_id == "codex":
        assert "# codex config -- comment must survive" in new_text
        assert 'model = "o3"' in new_text
        assert "[mcp_servers.other]" in new_text
        assert 'command = "npx"' in new_text
    else:
        parsed = json.loads(new_text)
        servers_key = ADAPTERS[adapter_id].servers_key[0]
        assert parsed[servers_key]["rush"] == build_stdio_entry(RUSH_BINARY)
        if adapter_id == "claude-desktop":
            assert parsed["theme"] == "dark"
            assert (
                parsed[servers_key]["other-tool"]["env"]["API_KEY"] == "sk-secret-value"
            )
        if adapter_id == "claude-code":
            assert parsed["userId"] == "abc123"
        if adapter_id == "windsurf":
            assert parsed[servers_key]["legacy"]["command"] == "old-rush"

    statuses = discover_agents(home=home, rush_binary=RUSH_BINARY, os_name="Darwin")
    entry = next(s for s in statuses if s.agent_id == adapter_id)
    assert entry.status == "registered"

    # Re-applying (repeated install) must never duplicate the rush entry.
    plan2 = plan_agent_registration(
        adapter_id, rush_binary=RUSH_BINARY, home=home, os_name="Darwin"
    )
    apply_agent_registration(plan2)
    final_text = plan.config_path.read_text(encoding="utf-8")
    if adapter_id == "codex":
        assert final_text.count("[mcp_servers.rush]") == 1
    else:
        assert final_text.count('"rush"') == 1


def test_existing_rush_registration_detected_and_repaired(tmp_path: Path) -> None:
    stale = json.dumps(
        {
            "mcpServers": {
                "rush": {"command": "/old/dev/checkout/rush", "args": ["mcp", "serve"]}
            }
        },
        indent=2,
    )
    home = _home_with(tmp_path, "cursor", stale)

    before = discover_agents(home=home, rush_binary=RUSH_BINARY)
    cursor_before = next(s for s in before if s.agent_id == "cursor")
    assert cursor_before.status == "misconfigured"

    plan = plan_agent_registration("cursor", rush_binary=RUSH_BINARY, home=home)
    apply_agent_registration(plan)

    after = discover_agents(home=home, rush_binary=RUSH_BINARY)
    cursor_after = next(s for s in after if s.agent_id == "cursor")
    assert cursor_after.status == "registered"
    assert cursor_after.config_path is not None
    assert cursor_after.config_path.read_text(encoding="utf-8").count('"rush"') == 1


# --- exact per-agent status, isolated failures -----------------------------------


def test_discover_agents_reports_exact_per_agent_status(tmp_path: Path) -> None:
    home = tmp_path

    registered = json.dumps(
        {
            "mcpServers": {
                "rush": build_stdio_entry(RUSH_BINARY),
                "other-tool": {"command": "node", "args": []},
            }
        },
        indent=2,
    )
    _write(ADAPTERS["claude-desktop"].config_paths("Darwin", home)[0], registered)
    _write(ADAPTERS["claude-code"].config_paths("Darwin", home)[0], "{")  # malformed
    _write(ADAPTERS["cursor"].config_paths("Darwin", home)[0], CURSOR_JSON)  # detected
    # windsurf: left absent -> not_detected
    misconfigured = ZED_JSONC.replace(
        '"other": {\n      "command": {"path": "node", "args": ["x.js"]}\n    }',
        '"other": {\n      "command": {"path": "node", "args": ["x.js"]}\n    },\n'
        '    "rush": {"command": "/old/wrong/path", "args": ["mcp", "serve"]}',
    )
    _write(ADAPTERS["zed"].config_paths("Darwin", home)[0], misconfigured)
    _write(ADAPTERS["codex"].config_paths("Darwin", home)[0], CODEX_TOML)  # detected

    statuses = {
        s.agent_id: s
        for s in discover_agents(home=home, os_name="Darwin", rush_binary=RUSH_BINARY)
    }

    assert {agent_id: status.status for agent_id, status in statuses.items()} == {
        "claude-desktop": "registered",
        "claude-code": "malformed",
        "cursor": "detected",
        "windsurf": "not_detected",
        "zed": "misconfigured",
        "codex": "detected",
        "zcode": "not_detected",
    }
    assert statuses["claude-code"].error is not None
    # A config failure for one agent never marks another as failed or connected.
    for agent_id in ("claude-desktop", "cursor", "zed", "codex", "windsurf"):
        assert statuses[agent_id].status != "malformed"
    for agent_id in ("claude-code", "cursor", "zed", "codex", "windsurf"):
        assert statuses[agent_id].status != "registered"


def test_malformed_config_untouched_on_plan_attempt(tmp_path: Path) -> None:
    home = _home_with(tmp_path, "cursor", "{ broken")
    path = ADAPTERS["cursor"].config_paths("Darwin", home)[0]
    before = path.read_bytes()
    with pytest.raises(MalformedConfigError):
        plan_agent_registration("cursor", rush_binary=RUSH_BINARY, home=home)
    assert path.read_bytes() == before


def test_malformed_codex_toml_reported(tmp_path: Path) -> None:
    home = _home_with(tmp_path, "codex", "[incomplete")
    statuses = discover_agents(home=home, os_name="Darwin", rush_binary=RUSH_BINARY)
    codex_status = next(s for s in statuses if s.agent_id == "codex")
    assert codex_status.status == "malformed"
    assert codex_status.error is not None


@pytest.mark.posix_only
def test_read_only_config_reported_without_crashing_others(tmp_path: Path) -> None:
    home = _home_with(tmp_path, "windsurf", WINDSURF_JSON)
    path = ADAPTERS["windsurf"].config_paths("Darwin", home)[0]
    path.chmod(0o444)
    try:
        statuses = {
            s.agent_id: s
            for s in discover_agents(
                home=home, os_name="Darwin", rush_binary=RUSH_BINARY
            )
        }
        assert statuses["windsurf"].status == "read_only"
        assert statuses["cursor"].status == "not_detected"

        with pytest.raises(ReadOnlyConfigError):
            plan_agent_registration("windsurf", rush_binary=RUSH_BINARY, home=home)
    finally:
        path.chmod(0o644)


def test_probe_agent_connection_reads_back_after_apply(tmp_path: Path) -> None:
    home = _home_with(tmp_path, "cursor", CURSOR_JSON)
    plan = plan_agent_registration("cursor", rush_binary=RUSH_BINARY, home=home)
    apply_agent_registration(plan)

    status = probe_agent_connection("cursor", home=home, rush_binary=RUSH_BINARY)
    assert status.status == "registered"

    with pytest.raises(UnknownAgentError):
        probe_agent_connection("does-not-exist", home=home)


# --- unknown agent / generic stdio spec ------------------------------------------


def test_unknown_agent_requires_explicit_override(tmp_path: Path) -> None:
    with pytest.raises(UnknownAgentError):
        plan_agent_registration(
            "some-future-editor", rush_binary=RUSH_BINARY, home=tmp_path
        )


def test_generic_stdio_client_registration(tmp_path: Path) -> None:
    custom_path = tmp_path / "custom-editor" / "mcp.json"
    plan = plan_agent_registration(
        "some-future-editor",
        rush_binary=RUSH_BINARY,
        config_path=custom_path,
        config_format="json",
        servers_key=("mcpServers",),
    )
    assert plan.method == "config-edit"
    result = apply_agent_registration(plan)
    assert result.ok, result.error

    parsed = json.loads(custom_path.read_text(encoding="utf-8"))
    assert parsed["mcpServers"]["rush"] == build_stdio_entry(RUSH_BINARY)


def test_build_stdio_entry_generic_spec() -> None:
    entry = build_stdio_entry(RUSH_BINARY)
    assert entry == {
        "command": RUSH_BINARY,
        "args": ["mcp", "serve", "--profile", "core"],
    }
    custom = build_stdio_entry(RUSH_BINARY, args=("mcp", "serve", "--stdio"))
    assert custom["args"] == ["mcp", "serve", "--stdio"]


# --- native registration (Claude Code) -------------------------------------------


def test_native_registration_idempotent_with_fake_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = tmp_path / "claude-calls.log"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_claude = bin_dir / "claude"
    fake_claude.write_text(f'#!/bin/sh\necho "$@" >> "{log_path}"\nexit 0\n')
    fake_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    plan = plan_agent_registration(
        "claude-code", rush_binary=RUSH_BINARY, home=tmp_path
    )
    assert plan.method == "native"
    assert plan.restart_required is False

    first = apply_agent_registration(plan)
    assert first.ok, first.error
    second = apply_agent_registration(plan)
    assert second.ok, second.error

    calls = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert calls == [
        "mcp remove rush --scope user",
        f"mcp add rush --scope user -- {RUSH_BINARY} mcp serve --profile core",
        "mcp remove rush --scope user",
        f"mcp add rush --scope user -- {RUSH_BINARY} mcp serve --profile core",
    ]


def test_native_registration_reports_failure_without_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_claude = bin_dir / "claude"
    fake_claude.write_text("#!/bin/sh\necho boom 1>&2\nexit 1\n")
    fake_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    plan = plan_agent_registration(
        "claude-code", rush_binary=RUSH_BINARY, home=tmp_path
    )
    result = apply_agent_registration(plan)
    assert result.ok is False
    assert result.error


# --- resolve_rush_binary safety ---------------------------------------------------


def test_resolve_rush_binary_rejects_repo_checkout() -> None:
    repo_file = str(Path(__file__).resolve().parents[1] / "src" / "rush" / "cli.py")
    with pytest.raises(AgentConnectionError):
        resolve_rush_binary(repo_file)


def test_resolve_rush_binary_rejects_venv(tmp_path: Path) -> None:
    venv_rush = tmp_path / ".venv" / "bin" / "rush"
    venv_rush.parent.mkdir(parents=True)
    venv_rush.write_text("#!/bin/sh\n")
    with pytest.raises(AgentConnectionError):
        resolve_rush_binary(str(venv_rush))


def test_resolve_rush_binary_accepts_installed_path(tmp_path: Path) -> None:
    installed = tmp_path / "usr-local-bin" / "rush"
    installed.parent.mkdir(parents=True)
    installed.write_text("#!/bin/sh\n")
    resolved = resolve_rush_binary(str(installed))
    assert resolved == str(installed.resolve())


def test_resolve_rush_binary_requires_explicit_or_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    with pytest.raises(AgentConnectionError):
        resolve_rush_binary(None)


@pytest.mark.parametrize(
    ("agent", "host"), [("claude-code", "claude"), ("codex", "codex")]
)
@pytest.mark.parametrize("public", [False, True])
def test_native_connect_preserves_manual_config_with_real_effects(
    tmp_path, monkeypatch, agent, host, public
):
    from click.testing import CliRunner

    from rush.cli import cli
    from rush.integrations import agents as agents_mod
    from rush.permissions import ExecutionPermissions
    from rush.setup.provision import default_data_root
    from rush.tools.agent_connection import AgentConnectionTool

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    data = default_data_root()
    root = tmp_path / "project"
    root.mkdir()
    config = agents_mod.ADAPTERS[agent].config_paths(sys.platform, home)[0]
    config.parent.mkdir(parents=True, exist_ok=True)
    original = (
        b'{"mcpServers":{"other":{"command":"other"}}}\n'
        if host == "claude"
        else b'# other config\n[mcp_servers.other]\ncommand = "other"\n'
    )
    config.write_bytes(original)
    roots = agents_mod.materialize_agent_plugins(
        rush_binary=RUSH_BINARY, data_root=data
    )
    agents_mod.record_native_plugin_install(
        host=host, plugin_root=roots[host], data_root=data
    )
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(args)
        pytest.fail("native connect attempted manual host registration")

    monkeypatch.setattr(agents_mod.subprocess, "run", forbidden)
    if public:
        result = CliRunner().invoke(
            cli,
            [
                "agent",
                "connect",
                agent,
                "--session",
                "native-session",
                "--project",
                str(root),
                "--rush-binary",
                RUSH_BINARY,
                "--install-guidance",
                "--consent",
                "--acknowledge",
                "--allow-cache-write",
                "--allow-artifact-write",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.exception
        payload = json.loads(result.stdout)
    else:
        payload = AgentConnectionTool().run(
            agent,
            action="connect",
            session_id="native-session",
            project_root=root,
            rush_binary=RUSH_BINARY,
            install_guidance=True,
            consent=True,
            acknowledge=True,
            permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
            home=home,
            data_root=data,
            resources=[
                agents_mod.OwnedResource(
                    "file_resource", ".rush/skills/extra.md", b"real resource\n"
                )
            ],
        )
        assert (root / ".rush/skills/extra.md").read_bytes() == b"real resource\n"
    assert payload["status"] == "ok", payload
    assert config.read_bytes() == original
    assert calls == []
    assert payload["raw"]["apply"]["method"] == "native_plugin"
    assert payload["raw"]["probe"]["status"] == "registered"
    assert payload["raw"]["probe"]["restart_required"] is True
    guidance = root / ("CLAUDE.md" if host == "claude" else "AGENTS.md")
    assert "<!-- rush:begin" in guidance.read_text()
    memory = agents_mod.read_agent_memory_state(
        agent, "native-session", project_root=root, data_root=data
    )
    assert memory["consent"] is True and memory["connected"] is True
    rows = json.loads(agents_mod.ownership_ledger_path(data).read_bytes())[
        "data"
    ].values()
    assert not any(row["kind"] == "mcp_entry" and row["host"] == agent for row in rows)


@pytest.mark.parametrize(
    ("agent", "host"), [("claude-code", "claude"), ("codex", "codex")]
)
@pytest.mark.parametrize(
    "problem", ["missing", "mutated", "ambiguous", "restricted", "stale", "unknown"]
)
def test_native_registration_conflicts_never_fall_back_to_manual(
    tmp_path, monkeypatch, agent, host, problem
):
    import shutil

    from rush.permissions import ExecutionPermissions
    from rush.tools.agent_connection import AgentConnectionTool

    home = tmp_path / "home"
    home.mkdir()
    data = tmp_path / "data"
    root = tmp_path / "project"
    root.mkdir()
    config = ADAPTERS[agent].config_paths(sys.platform, home)[0]
    config.parent.mkdir(parents=True, exist_ok=True)
    original = b'{"mcpServers":{}}' if host == "claude" else b"# empty host config\n"
    config.write_bytes(original)
    roots = agents_mod.materialize_agent_plugins(
        rush_binary=RUSH_BINARY, data_root=data
    )
    plugin = roots[host]
    agents_mod.record_native_plugin_install(
        host=host, plugin_root=plugin, data_root=data
    )
    mcp = plugin / "rush" / (".mcp.json" if host == "claude" else "mcp.json")
    if problem == "missing":
        shutil.rmtree(plugin)
    elif problem == "mutated":
        mcp.write_bytes(mcp.read_bytes() + b" ")
    elif problem == "ambiguous":
        other = agents_mod.materialize_agent_plugins(
            rush_binary=RUSH_BINARY, rush_version="9.9.9", data_root=data
        )
        agents_mod.record_native_plugin_install(
            host=host, plugin_root=other[host], data_root=data
        )
    elif problem == "restricted":
        value = json.loads(mcp.read_bytes())
        value["mcpServers"]["rush"]["args"] = [
            "mcp",
            "serve",
            "--memory-session",
            "receiver",
        ]
        mcp.write_text(json.dumps(value))
        with agents_mod._ledger_lock(data):
            ledger, version = agents_mod._load_ledger(data)
            for row in ledger.values():
                if row["path"] == str(plugin):
                    row["written_sha256"] = agents_mod.owned_path_digest(plugin)
            agents_mod._save_ledger(data, ledger, version)
    ledger_bytes = agents_mod.ownership_ledger_path(data).read_bytes()
    consent_calls = []

    def approve(preview):
        consent_calls.append(preview)
        if problem == "stale":
            mcp.write_bytes(mcp.read_bytes() + b" ")
        return True

    result = AgentConnectionTool().run(
        agent,
        action="connect",
        session_id="blocked",
        rush_binary=RUSH_BINARY,
        project_root=root,
        home=home,
        data_root=data,
        profile="invalid" if problem == "unknown" else "full",
        confirm_profile=approve,
        permissions=ExecutionPermissions(cache_write=True, artifact_write=True),
    )
    assert result["status"] == "error", result
    expected = {
        "missing": "ownership conflict",
        "mutated": "ownership conflict",
        "ambiguous": "ambiguous",
        "restricted": "restricted memory-session",
        "stale": "changed since preview",
        "unknown": "unknown MCP profile",
    }[problem]
    assert expected in result["summary"]
    assert config.read_bytes() == original
    assert agents_mod.ownership_ledger_path(data).read_bytes() == ledger_bytes
    assert not agents_mod.agent_memory_store_path(project_root=root).exists()
    assert len(consent_calls) == (1 if problem == "stale" else 0)


# --- 73-T02/BOOTSTRAP-CONSENT: `agent connect --memory-binding` and the disconnect
# memory listing. Every run uses the per-test HOME (conftest `_isolated_home`) and a
# fake, never-executed rush binary; codex registers by editing the HOME config.

BINDING_VIEW_KEYS = {
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
_EXIT_FOR_STATUS = {"ok": 0, "skipped": 0, "warn": 1, "fail": 1, "error": 2}


def _data_root() -> Path:
    from rush.setup.provision import default_data_root

    return default_data_root()


@contextlib.contextmanager
def _forged_principal(grant_id: str) -> Iterator[None]:
    _c_forged_principal = importlib.import_module(
        "tests.test_memory_authorization"
    )._c_forged_principal

    with _c_forged_principal(grant_id):
        yield


def _policy() -> dict[str, Any]:
    from rush.memory import authorization as auth

    return auth.load_policy_readonly(data_root=_data_root())


def _policy_bytes() -> bytes | None:
    from rush.memory import authorization as auth

    path = auth.policy_path(data_root=_data_root())
    return path.read_bytes() if path.exists() else None


def _state(*bases: Path) -> list[tuple[str, ...]]:
    """Every entry under HOME (agent config, ledger, memory state, policy) and each
    base: directories, symlink targets, file sha256."""
    entries: list[tuple[str, ...]] = []
    for base in (Path(os.environ["HOME"]), *bases):
        for path in [base, *sorted(base.rglob("*"))]:
            if path.is_symlink():
                entries.append((str(path), "link", os.readlink(path)))
            elif path.is_dir():
                entries.append((str(path), "dir"))
            elif path.is_file():
                entries.append(
                    (str(path), "file", hashlib.sha256(path.read_bytes()).hexdigest())
                )
    return entries


def _project(tmp_path: Path, name: str = "project") -> Path:
    from rush.workflows.projects import register_project

    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    register_project(root, data_root=_data_root())
    return root.resolve()


def _fake_rush(tmp_path: Path) -> Path:
    fake = tmp_path / "fake-rush"
    if not fake.exists():
        fake.write_text("#!/bin/sh\necho fake-rush\n")
        fake.chmod(0o755)
    return fake


def _grant(root: Path, **extra: Any) -> dict[str, Any]:
    from rush.memory import authorization as auth
    from rush.memory.store import OwnerScope, legacy_owner_scope

    owner = extra.pop("owner", None) or legacy_owner_scope(root)
    assert isinstance(owner, OwnerScope)
    return auth.grant_memory_scope(
        project_root=root,
        owner_scope=owner,
        approved_sources=extra.pop("sources", ["s"]),
        allowed_operations=extra.pop("ops", ["ask", "list"]),
        expected_policy_revision=int(_policy()["policy_revision"]),
        consent=True,
        data_root=_data_root(),
        **extra,
    )


def _connect_args(
    root: Path, fake: Path, *extra: str, session: str = "S1", agent: str = "codex"
) -> list[str]:
    return [
        "agent",
        "connect",
        agent,
        "--session",
        session,
        "--project",
        str(root),
        "--rush-binary",
        str(fake),
        "--allow-cache-write",
        "--allow-artifact-write",
        *extra,
    ]


def _binding_flags(grant_id: str, revision: int, *, approve: bool) -> list[str]:
    flags = [
        "--memory-binding",
        "--memory-grant-id",
        grant_id,
        "--expected-policy-revision",
        str(revision),
    ]
    return [*flags, "--approve-memory-binding"] if approve else flags


def _cli(*args: str) -> tuple[int, Any, str]:
    from click.testing import CliRunner

    from rush.cli import cli

    result = CliRunner().invoke(cli, list(args), catch_exceptions=False)
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        payload = None
    return result.exit_code, payload, result.output


def _connect(args: list[str], *, status: str | None = None) -> dict[str, Any]:
    exit_code, payload, output = _cli(*args, "--json")
    assert payload is not None, output
    assert payload["tool"] == "agent_connection", payload
    if status is not None:
        assert payload["status"] == status, payload
        assert exit_code == _EXIT_FOR_STATUS[status], (exit_code, output)
    return payload


def _usage(args: list[str], message: str) -> None:
    exit_code, payload, output = _cli(*args)
    assert exit_code == 2, (args, output)
    assert payload is None
    assert message in output, (message, output)


@contextlib.contextmanager
def _forbid_connect(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from rush.tools.agent_connection import AgentConnectionTool

    def refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("AgentConnectionTool.run called before the pre-check")

    with monkeypatch.context() as scoped:
        scoped.setattr(AgentConnectionTool, "run", refuse)
        yield


@contextlib.contextmanager
def _after_connect(monkeypatch: pytest.MonkeyPatch, after: Any) -> Iterator[None]:
    """Run `after()` once the real `AgentConnectionTool.run` returned."""
    from rush.tools.agent_connection import AgentConnectionTool

    original = AgentConnectionTool.run

    def run(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        after()
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(AgentConnectionTool, "run", run)
        yield


def _refusal_payload(
    code: str, reason: str, *, state: str | None = None
) -> dict[str, Any]:
    state = state or ("conflict" if code == "E_VERSION" else "refused")
    return {"memory_binding": {"state": state, "code": code, "reason": reason}}


def _assert_refused(
    args: list[str],
    code: str,
    reason: str,
    *roots: Path,
    text_line: str | None = None,
) -> None:
    """A pre-connect refusal: §3 H5 shape, status `_CODE_STATUS[code]`, nothing
    written (HOME, projects and the policy bytes are all identical)."""
    from rush.tools.memory import _CODE_STATUS

    before = _state(*roots)
    policy = _policy_bytes()
    state = "conflict" if code == "E_VERSION" else "refused"
    payload = _connect(args, status=_CODE_STATUS.get(code, "error"))
    assert payload["raw"] == _refusal_payload(code, reason), payload
    assert payload["summary"] == (
        f"agent connect: memory binding {state} ({code}: {reason}); nothing written"
    )
    assert _state(*roots) == before
    assert _policy_bytes() == policy
    if text_line is not None:
        exit_code, _none, output = _cli(*args)
        assert text_line in output, output
        assert exit_code == _EXIT_FOR_STATUS[_CODE_STATUS.get(code, "error")]
        assert _state(*roots) == before


def test_connect_memory_binding_requires_approval(tmp_path: Path) -> None:
    root = _project(tmp_path)
    fake = _fake_rush(tmp_path)
    grant = _grant(root)
    revision = int(_policy()["policy_revision"])
    assert revision == 1
    sealed = _policy_bytes()

    # A5.4: without --approve-memory-binding the connect runs and only previews.
    payload = _connect(
        _connect_args(root, fake, *_binding_flags(grant["grant_id"], 1, approve=False)),
        status="ok",
    )
    assert payload["raw"]["apply"]["ok"] is True
    assert payload["raw"]["memory_binding"] == {
        "state": "preview",
        "grant_id": grant["grant_id"],
        "session_id": "S1",
        "host_id": "codex",
        "expected_policy_revision": 1,
    }
    assert _policy_bytes() == sealed
    assert _policy()["bindings"] == {}

    # A5.5: with it, a successful connect registers the binding and returns its view.
    payload = _connect(
        _connect_args(root, fake, *_binding_flags(grant["grant_id"], 1, approve=True)),
        status="ok",
    )
    view = payload["raw"]["memory_binding"]
    assert set(view) == BINDING_VIEW_KEYS
    loaded = _policy()
    assert loaded["policy_revision"] == 2
    assert loaded["bindings"][view["binding_id"]] == view
    assert (view["grant_id"], view["session_id"], view["host_id"]) == (
        grant["grant_id"],
        "S1",
        "codex",
    )
    assert view["policy_revision"] == 2 and view["revoked"] is False
    bound = _policy_bytes()

    # An identical active binding is returned unchanged (no new revision).
    again = _connect(
        _connect_args(root, fake, *_binding_flags(grant["grant_id"], 2, approve=True)),
        status="ok",
    )
    assert again["raw"]["memory_binding"] == view
    assert _policy_bytes() == bound

    # A5.7: the text mode echoes one line after the guidance line.
    for session, approve, expected in (
        ("S2", False, "memory binding: preview"),
        ("S3", True, None),
    ):
        args = _connect_args(
            root,
            fake,
            *_binding_flags(
                grant["grant_id"], int(_policy()["policy_revision"]), approve=approve
            ),
            session=session,
        )
        exit_code, _none, output = _cli(*args)
        assert exit_code == 0, output
        if expected is None:
            binding = next(
                b for b in _policy()["bindings"].values() if b["session_id"] == session
            )
            expected = f"memory binding: bound {binding['binding_id']}"
        assert expected in output, output
        assert output.index("guidance:") < output.index("memory binding:")


def test_connect_binding_stale_revision_no_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    fake = _fake_rush(tmp_path)
    grant = _grant(root)
    current = int(_policy()["policy_revision"])
    with _forbid_connect(monkeypatch):
        for stale in (0, current + 1, 10**400):
            for approve in (False, True):
                reason = f"expected revision {stale}, found {current}"
                _assert_refused(
                    _connect_args(
                        root,
                        fake,
                        *_binding_flags(grant["grant_id"], stale, approve=approve),
                    ),
                    "E_VERSION",
                    reason,
                    root,
                    text_line="memory binding: conflict E_VERSION",
                )
    assert _policy()["bindings"] == {}


def test_connect_binding_flags_usage_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path)
    fake = _fake_rush(tmp_path)
    grant = _grant(root)
    before = _state(root)
    needs_all = (
        "--memory-binding requires --memory-grant-id, --expected-policy-revision "
        "and --project"
    )
    base = ["agent", "connect", "codex", "--session", "S1"]
    allow = [
        "--rush-binary",
        str(fake),
        "--allow-cache-write",
        "--allow-artifact-write",
    ]
    project = ["--project", str(root)]
    gid = ["--memory-grant-id", grant["grant_id"]]
    rev = ["--expected-policy-revision", "1"]
    with _forbid_connect(monkeypatch):
        for extra, message in (
            (["--memory-binding"], needs_all),
            (["--memory-binding", *project], needs_all),
            (["--memory-binding", *project, *gid], needs_all),
            (["--memory-binding", *project, *rev], needs_all),
            (["--memory-binding", *gid, *rev], needs_all),  # without --project
            (["--memory-binding", "--approve-memory-binding"], needs_all),
            ([*project, *gid], "requires --memory-binding"),
            ([*project, *rev], "requires --memory-binding"),
            ([*project, "--approve-memory-binding"], "requires --memory-binding"),
            (
                [*project, *gid, *rev, "--approve-memory-binding"],
                "requires --memory-binding",
            ),
        ):
            _usage([*base, *allow, *extra], message)
        # Click itself rejects a negative or non-integer revision.
        for bad in ("-1", "abc", "1.5", "true", "", "1\x00", "1\ud800"):
            _usage(
                [
                    *base,
                    *allow,
                    "--memory-binding",
                    *project,
                    *gid,
                    "--expected-policy-revision",
                    bad,
                ],
                "--expected-policy-revision",
            )
    assert _state(root) == before
    assert _policy()["bindings"] == {}


def test_connect_memory_binding_rejects_other_project_and_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import authorization as auth
    from rush.workflows.projects import register_project

    a = _project(tmp_path, "A")
    b = _project(tmp_path, "B")
    fake = _fake_rush(tmp_path)
    grant_a = _grant(a)
    grant_b = _grant(b)
    revision = int(_policy()["policy_revision"])

    # Same-principal grant of another project.
    with _forbid_connect(monkeypatch):
        _assert_refused(
            _connect_args(
                a,
                fake,
                *_binding_flags(grant_b["grant_id"], revision, approve=True),
            ),
            "E_PERMISSION",
            "binding_scope_mismatch",
            a,
            b,
        )

    # A renamed and recreated at the same path: a new inode, so A's earlier grant no
    # longer names this worktree.
    old_inode = os.stat(a).st_ino
    old = a.with_name("A.old")
    a.rename(old)
    a.mkdir()
    assert os.stat(a).st_ino != old_inode
    register_project(a, data_root=_data_root())
    with _forbid_connect(monkeypatch):
        _assert_refused(
            _connect_args(
                a,
                fake,
                *_binding_flags(grant_a["grant_id"], revision, approve=True),
            ),
            "E_PERMISSION",
            "binding_scope_mismatch",
            a,
            b,
            old,
        )

    # A's current grant binds; connect runs.
    current = _grant(a)
    assert current["worktree_id"] != grant_a["worktree_id"]
    revision = int(_policy()["policy_revision"])
    payload = _connect(
        _connect_args(
            a, fake, *_binding_flags(current["grant_id"], revision, approve=True)
        ),
        status="ok",
    )
    assert payload["raw"]["memory_binding"]["grant_id"] == current["grant_id"]

    # An expired grant (patched clock) is refused before connect.
    expiring = _grant(
        b, owner=_owner("user", "expiring"), expires_at=time.time() + 3600
    )
    revision = int(_policy()["policy_revision"])
    with _forbid_connect(monkeypatch), monkeypatch.context() as later:
        later.setattr(auth, "_now", lambda: time.time() + 7200)
        _assert_refused(
            _connect_args(
                b,
                fake,
                *_binding_flags(expiring["grant_id"], revision, approve=True),
                session="S-exp",
            ),
            "E_PERMISSION",
            "expired",
            a,
            b,
        )


def _owner(kind: str, ident: str) -> Any:
    from rush.memory.store import OwnerScope

    return OwnerScope(kind, ident)  # type: ignore[arg-type]


def test_mcp_connect_cannot_bind(tmp_path: Path) -> None:
    """A5.8 (guard): the MCP connect has no binding route; the extra keys are ignored."""
    from rush.mcp import rush_agent_connection

    root = _project(tmp_path)
    fake = _fake_rush(tmp_path)
    grant = _grant(root)
    sealed = _policy_bytes()
    result = rush_agent_connection(
        {
            "schema_version": 1,
            "operation": "connect",
            "agent_id": "codex",
            "session_id": "S1",
            "project_root": str(root),
            "rush_binary": str(fake),
            "allow_cache_write": True,
            "allow_artifact_write": True,
            "memory_binding": True,
            "memory_grant_id": grant["grant_id"],
            "expected_policy_revision": 1,
            "approve_memory_binding": True,
        }
    )
    assert result["status"] == "ok", result
    data = cast("dict[str, Any]", result["raw"])["data"]
    assert data["apply"]["ok"] is True
    assert "memory_binding" not in data
    assert "memory_binding" not in cast("dict[str, Any]", result["raw"])
    assert _policy_bytes() == sealed
    assert _policy()["bindings"] == {}

    # Contrast: the same grant, revision and agent bind through the CLI route, so the
    # unchanged policy above is the absent MCP route, not a missing or stale grant.
    payload = _connect(
        _connect_args(
            root,
            fake,
            *_binding_flags(grant["grant_id"], 1, approve=True),
            session="S2",
        ),
        status="ok",
    )
    view = payload["raw"]["memory_binding"]
    assert set(view) == BINDING_VIEW_KEYS
    loaded = _policy()
    assert loaded["policy_revision"] == 2
    assert loaded["bindings"] == {view["binding_id"]: view}
    assert (view["grant_id"], view["session_id"], view["host_id"]) == (
        grant["grant_id"],
        "S2",
        "codex",
    )


def test_connect_binding_grant_inactive_after_connect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.memory import authorization as auth

    fake = _fake_rush(tmp_path)
    control_root = _project(tmp_path, "control")
    control = _connect(_connect_args(control_root, fake, session="S-ctl"), status="ok")

    root = _project(tmp_path, "project")
    grant = _grant(root)
    revision = int(_policy()["policy_revision"])

    def revoke() -> None:
        auth.revoke_memory_scope(
            grant_id=grant["grant_id"],
            expected_policy_revision=int(_policy()["policy_revision"]),
            consent=True,
            data_root=_data_root(),
        )

    with _after_connect(monkeypatch, revoke):
        payload = _connect(
            _connect_args(
                root, fake, *_binding_flags(grant["grant_id"], revision, approve=True)
            ),
            status="ok",
        )
    # The connect itself is as without the binding flags; the binding is refused.
    assert payload["status"] == control["status"]
    assert payload["summary"] == control["summary"]
    assert payload["raw"]["apply"]["ok"] is True
    assert payload["raw"]["memory_binding"] == {
        "state": "refused",
        "code": "E_GRANT_INACTIVE",
        "reason": "revoked",
    }
    after_revoke = _policy()
    assert after_revoke["grants"][grant["grant_id"]]["revoked"] is True
    assert after_revoke["bindings"] == {}
    assert after_revoke["policy_revision"] == revision + 1

    # A revision race at register time is a conflict (no reason), connect unchanged.
    other = _project(tmp_path, "race")
    race_grant = _grant(other)
    race_revision = int(_policy()["policy_revision"])
    with _after_connect(
        monkeypatch, lambda: _grant(other, owner=_owner("user", "bumper"))
    ):
        payload = _connect(
            _connect_args(
                other,
                fake,
                *_binding_flags(race_grant["grant_id"], race_revision, approve=True),
            ),
            status="ok",
        )
    assert payload["summary"] == control["summary"]
    assert payload["raw"]["memory_binding"] == {
        "state": "conflict",
        "code": "E_VERSION",
    }
    assert [
        b
        for b in _policy()["bindings"].values()
        if b["grant_id"] == race_grant["grant_id"]
    ] == []

    # Any other writer refusal is "refused" with the writer's code and reason.
    third = _project(tmp_path, "principal")
    third_grant = _grant(third)
    third_revision = int(_policy()["policy_revision"])
    real_principal = auth._current_os_principal

    def switch_user() -> None:
        auth._current_os_principal = lambda: "uid:2147483646"  # type: ignore[assignment]

    try:
        with _after_connect(monkeypatch, switch_user):
            payload = _connect(
                _connect_args(
                    third,
                    fake,
                    *_binding_flags(
                        third_grant["grant_id"], third_revision, approve=True
                    ),
                ),
                status="ok",
            )
    finally:
        auth._current_os_principal = real_principal  # type: ignore[assignment]
    # Another OS user cannot even read the policy file: the writer's own refusal.
    assert payload["raw"]["memory_binding"] == {
        "state": "refused",
        "code": "E_POLICY_INVALID",
        "reason": "foreign_owner",
    }


def test_disconnect_lists_memory_readonly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from rush.mcp import rush_agent_connection
    from rush.memory import authorization as auth

    a = _project(tmp_path, "A")
    b = _project(tmp_path, "B")
    fake = _fake_rush(tmp_path)
    data_root = _data_root()

    def bind(grant_id: str, host: str, session: str) -> dict[str, Any]:
        return auth.register_memory_binding(
            grant_id=grant_id,
            session_id=session,
            host_id=host,
            expected_policy_revision=int(_policy()["policy_revision"]),
            consent=True,
            data_root=data_root,
        )

    grant_a = _grant(a)
    grant_a2 = _grant(a, owner=_owner("user", "alice"))
    dead = _grant(a, owner=_owner("user", "dead"))
    soon = _grant(a, owner=_owner("user", "soon"), expires_at=time.time() + 3600)
    grant_b = _grant(b)
    codex_a = bind(grant_a["grant_id"], "codex", "s1")
    bind(grant_a["grant_id"], "claude-code", "s2")
    codex_b = bind(grant_b["grant_id"], "codex", "s3")
    gone = bind(dead["grant_id"], "codex", "s4")
    auth.revoke_memory_scope(
        grant_id=dead["grant_id"],
        expected_policy_revision=int(_policy()["policy_revision"]),
        consent=True,
        data_root=data_root,
    )
    loaded = _policy()
    assert loaded["bindings"][gone["binding_id"]]["revoked"] is True
    sealed = _policy_bytes()

    def active_grants(*, now: float | None = None) -> list[dict[str, Any]]:
        clock = time.time() if now is None else now
        return sorted(
            (
                g
                for g in _policy()["grants"].values()
                if not g["revoked"]
                and (g["expires_at"] is None or clock < g["expires_at"])
                and g["project_id"]
                == loaded["grants"][grant_a["grant_id"]]["project_id"]
                and g["worktree_id"]
                == loaded["grants"][grant_a["grant_id"]]["worktree_id"]
            ),
            key=lambda g: g["grant_id"],
        )

    def host_bindings(host: str) -> list[dict[str, Any]]:
        return sorted(
            (
                v
                for v in _policy()["bindings"].values()
                if v["host_id"] == host and not v["revoked"]
            ),
            key=lambda v: v["binding_id"],
        )

    expected_grants = active_grants()
    assert {g["grant_id"] for g in expected_grants} == {
        grant_a["grant_id"],
        grant_a2["grant_id"],
        soon["grant_id"],
    }
    # A6.1 / A6.2 / A6.3: project disconnect, CLI.
    exit_code, payload, output = _cli(
        "agent", "disconnect", "codex", "--project", str(a), "--json"
    )
    assert exit_code == 0 and payload is not None, output
    assert payload["raw"]["memory"] == {
        "grants": expected_grants,
        "bindings": host_bindings("codex"),
    }
    assert {v["binding_id"] for v in payload["raw"]["memory"]["bindings"]} == {
        codex_a["binding_id"],
        codex_b["binding_id"],
    }
    assert _policy_bytes() == sealed

    # The same listing through the MCP route sits under raw.data.
    result = rush_agent_connection(
        {
            "schema_version": 1,
            "operation": "disconnect",
            "agent_id": "codex",
            "project_root": str(a),
            "allow_cache_write": True,
            "allow_artifact_write": True,
        }
    )
    assert (
        cast("dict[str, Any]", result["raw"])["data"]["memory"]
        == payload["raw"]["memory"]
    )
    assert "memory" not in cast("dict[str, Any]", result["raw"])

    # User scope: no project → no grants; bindings of the agent only.
    exit_code, payload, output = _cli("agent", "disconnect", "claude-code", "--json")
    assert exit_code == 0 and payload is not None, output
    assert payload["raw"]["memory"] == {
        "grants": [],
        "bindings": host_bindings("claude-code"),
    }
    assert len(payload["raw"]["memory"]["bindings"]) == 1

    # The clock decides expiry (the listing reads authorization._now()).
    with monkeypatch.context() as later:
        later.setattr(auth, "_now", lambda: time.time() + 7200)
        exit_code, payload, output = _cli(
            "agent", "disconnect", "codex", "--project", str(a), "--json"
        )
    assert exit_code == 0 and payload is not None, output
    assert soon["grant_id"] not in {
        g["grant_id"] for g in payload["raw"]["memory"]["grants"]
    }

    # A6.4: a missing project root has no identity → no grants.
    exit_code, payload, output = _cli(
        "agent", "disconnect", "codex", "--project", str(tmp_path / "missing"), "--json"
    )
    assert exit_code == 0 and payload is not None, output
    assert payload["raw"]["memory"]["grants"] == []
    assert payload["raw"]["memory"]["bindings"] == host_bindings("codex")

    # A6.4: an identity failure of any kind → no grants.
    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("identity failed")

    with monkeypatch.context() as failing:
        failing.setattr(auth, "project_identity", explode, raising=False)
        exit_code, payload, output = _cli(
            "agent", "disconnect", "codex", "--project", str(a), "--json"
        )
    assert exit_code == 0 and payload is not None, output
    assert payload["raw"]["memory"]["grants"] == []

    # A6.4: policy states other than ok → empty lists; nothing created, nothing revoked.
    policy_file = auth.policy_path(data_root=data_root)
    policy_file.write_bytes(b"{")
    exit_code, payload, output = _cli(
        "agent", "disconnect", "codex", "--project", str(a), "--json"
    )
    assert exit_code == 0 and payload is not None, output
    assert payload["raw"]["memory"] == {"grants": [], "bindings": []}
    assert policy_file.read_bytes() == b"{"
    policy_file.unlink()
    exit_code, payload, output = _cli(
        "agent", "disconnect", "codex", "--project", str(a), "--json"
    )
    assert exit_code == 0 and payload is not None, output
    assert payload["raw"]["memory"] == {"grants": [], "bindings": []}
    assert not policy_file.exists()
    assert fake.exists()


def test_connect_binding_precheck_first_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§3 H5: the pre-check order is revision input, grant ID, session label, host
    label, policy availability, policy revision, grant presence, principal, revoked,
    expired, project/worktree identity; each cell fails two or more checks at once and
    the first one wins. Every refusal happens before `AgentConnectionTool.run`."""
    import shutil

    from rush.memory import authorization as auth

    fake = _fake_rush(tmp_path)
    control = _project(tmp_path, "control")
    ghost = str(uuid.uuid4())
    bad_label = "a\x01b"
    long_label = "x" * (auth._LABEL_MAX + 1)

    def refuse(
        root: Path,
        grant_id: str,
        revision: int,
        code: str,
        reason: str,
        *,
        session: str = "S1",
        agent: str = "codex",
        extra_roots: tuple[Path, ...] = (),
        snapshot_root: bool = True,
        text_line: str | None = None,
    ) -> None:
        args = _connect_args(
            root,
            fake,
            *_binding_flags(grant_id, revision, approve=True),
            session=session,
            agent=agent,
        )
        roots = (root, *extra_roots) if snapshot_root else extra_roots
        with _forbid_connect(monkeypatch):
            _assert_refused(args, code, reason, *roots, text_line=text_line)

    # No policy yet: policy availability precedes the revision and the grant lookup.
    refuse(control, ghost, 7, "E_PERMISSION", "policy_missing")
    refuse(control, ghost, 7, "E_INPUT", "session_id", session=bad_label)
    refuse(control, ghost, 7, "E_INPUT", "host_id", agent=bad_label)

    root = _project(tmp_path, "project")
    grant = _grant(root)
    gid = grant["grant_id"]
    revision = int(_policy()["policy_revision"])

    # Writer-order input checks: grant ID, then session, then host label, all before
    # the policy or the revision is looked at.
    refuse(root, "", revision + 5, "E_INPUT", "grant_id", session=bad_label)
    refuse(
        root,
        gid,
        revision + 5,
        "E_INPUT",
        "session_id",
        session=bad_label,
        agent=bad_label,
    )
    refuse(root, gid, revision + 5, "E_INPUT", "session_id", session=long_label)
    refuse(root, gid, revision + 5, "E_INPUT", "host_id", agent=bad_label)
    refuse(root, gid, revision + 5, "E_INPUT", "host_id", agent=long_label)

    # Revision precedes grant presence; presence precedes the principal.
    refuse(
        root,
        ghost,
        revision + 5,
        "E_VERSION",
        f"expected revision {revision + 5}, found {revision}",
    )
    refuse(root, ghost, revision, "E_PERMISSION", "no_grant")
    real_principal = auth._current_os_principal

    def unavailable_after_load() -> str:
        """The policy loader asks once; the pre-check's own principal check fails."""
        calls["n"] += 1
        if calls["n"] == 1:
            return real_principal()
        raise OSError("no principal")

    calls = {"n": 0}
    with monkeypatch.context() as other:
        other.setattr(auth, "_current_os_principal", unavailable_after_load)
        refuse(root, gid, revision, "E_PERMISSION", "principal_unavailable")
    calls["n"] = 0
    with monkeypatch.context() as other:
        other.setattr(auth, "_current_os_principal", unavailable_after_load)
        refuse(root, ghost, revision, "E_PERMISSION", "no_grant")
    with _forged_principal(gid):
        refuse(root, gid, revision, "E_PERMISSION", "principal_mismatch")
    assert auth._current_os_principal is real_principal

    # Revoked precedes expired precedes identity: a revoked, expired grant of another
    # project is `revoked`; its expired-only sibling is `expired`.
    other_root = _project(tmp_path, "other")
    doomed = _grant(
        other_root, owner=_owner("user", "doomed"), expires_at=time.time() + 3600
    )
    revision = int(_policy()["policy_revision"])
    auth.revoke_memory_scope(
        grant_id=doomed["grant_id"],
        expected_policy_revision=revision,
        consent=True,
        data_root=_data_root(),
    )
    sibling = _grant(
        other_root, owner=_owner("user", "sibling"), expires_at=time.time() + 3600
    )
    revision = int(_policy()["policy_revision"])
    with monkeypatch.context() as later:
        later.setattr(auth, "_now", lambda: time.time() + 7200)
        refuse(
            root,
            doomed["grant_id"],
            revision,
            "E_PERMISSION",
            "revoked",
            text_line="memory binding: refused E_PERMISSION revoked",
        )
        refuse(root, sibling["grant_id"], revision, "E_PERMISSION", "expired")
    # An active grant of another project fails only on identity.
    refuse(
        root,
        sibling["grant_id"],
        revision,
        "E_PERMISSION",
        "binding_scope_mismatch",
        extra_roots=(other_root,),
    )

    # G4: NUL, lone surrogate and format characters in the labels and the grant ID are
    # decided by the writer's own validators, before connect.
    for label in ("a\x00b", "a\ud800b", "a\u202eb"):
        refuse(root, gid, revision, "E_INPUT", "session_id", session=label)
        refuse(root, gid, revision, "E_INPUT", "host_id", agent=label)
        refuse(root, label, revision, "E_PERMISSION", "no_grant")
    # A missing project path has no identity: scope mismatch.
    refuse(
        tmp_path / "missing-project",
        gid,
        revision,
        "E_PERMISSION",
        "binding_scope_mismatch",
        snapshot_root=False,
    )

    # A passing pre-check binds and connects (the control for every cell above).
    payload = _connect(
        _connect_args(root, fake, *_binding_flags(gid, revision, approve=True)),
        status="ok",
    )
    assert payload["raw"]["memory_binding"]["grant_id"] == gid

    # Invalid and unavailable policy files are `policy_invalid`.
    saved = _policy_bytes()
    assert saved is not None
    policy_file = auth.policy_path(data_root=_data_root())
    policy_file.write_bytes(b"{")
    refuse(root, gid, revision, "E_PERMISSION", "policy_invalid", session="S9")
    policy_file.write_bytes(saved)
    data_root = _data_root()
    shutil.rmtree(data_root)
    data_root.write_text("not a directory", encoding="utf-8")
    refuse(root, gid, revision, "E_PERMISSION", "policy_invalid", session="S10")


@contextlib.contextmanager
def _forged_grant_fields(edits: dict[str, dict[str, Any]]) -> Iterator[None]:
    """The stored grants carry the forged raw fields (the policy file itself stays
    valid and owned by the current principal); the original bytes come back on exit."""
    from rush.memory import authorization as auth

    path = auth.policy_path(data_root=_data_root())
    original = path.read_bytes()
    payload = json.loads(original.decode("utf-8"))
    for grant_id, fields in edits.items():
        payload["data"]["grants"][grant_id].update(fields)
    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        assert _policy()["state"] == "ok"
        yield
    finally:
        path.write_bytes(original)


def test_connect_binding_precheck_principal_precedes_later_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A grant of another OS principal is `principal_mismatch` whatever else is wrong
    with it: it is decided before the revoked, expired and identity checks and before
    the resolve, so a foreign grant of another project or a revoked foreign grant is
    never reported under a later check's reason."""
    from rush.memory import authorization as auth

    fake = _fake_rush(tmp_path)
    root = _project(tmp_path, "project")
    other = _project(tmp_path, "other")
    foreign = _grant(other)
    doomed = _grant(root, owner=_owner("user", "doomed"))
    auth.revoke_memory_scope(
        grant_id=doomed["grant_id"],
        expected_policy_revision=int(_policy()["policy_revision"]),
        consent=True,
        data_root=_data_root(),
    )
    revision = int(_policy()["policy_revision"])
    for grant_id in (foreign["grant_id"], doomed["grant_id"]):
        with (
            _forged_grant_fields({grant_id: {"principal": "uid:99999"}}),
            _forbid_connect(monkeypatch),
        ):
            _assert_refused(
                _connect_args(
                    root, fake, *_binding_flags(grant_id, revision, approve=True)
                ),
                "E_PERMISSION",
                "principal_mismatch",
                root,
                other,
            )


def test_connect_binding_precheck_grant_root_must_equal_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same project ID and worktree ID under another recorded root is not this
    project's grant: `binding_scope_mismatch` before connect, nothing written."""
    from rush.memory import authorization as auth

    fake = _fake_rush(tmp_path)
    root = _project(tmp_path, "project")
    grant = _grant(root)
    grant_id = grant["grant_id"]
    revision = int(_policy()["policy_revision"])
    moved = str(tmp_path / "elsewhere").encode("utf-8").hex()
    stored = auth.load_policy_readonly(data_root=_data_root())["grants"][grant_id]
    with (
        _forged_grant_fields({grant_id: {"project_root_hex": moved}}),
        _forbid_connect(monkeypatch),
    ):
        forged = _policy()["grants"][grant_id]
        assert forged["project_root"] != stored["project_root"]
        assert forged["project_id"] == stored["project_id"]
        assert forged["worktree_id"] == stored["worktree_id"]
        _assert_refused(
            _connect_args(
                root, fake, *_binding_flags(grant_id, revision, approve=True)
            ),
            "E_PERMISSION",
            "binding_scope_mismatch",
            root,
        )


def test_connect_binding_precheck_resolve_must_grant_the_named_grant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-check ends on the scope resolve: its denial reason is the refusal, and a
    resolve that names a different grant is `binding_scope_mismatch`. Neither reaches
    connect or writes anything; the unpatched resolve binds."""
    from rush.memory import authorization as auth

    fake = _fake_rush(tmp_path)
    root = _project(tmp_path, "project")
    grant_id = _grant(root)["grant_id"]
    revision = int(_policy()["policy_revision"])
    real = auth.resolve_memory_scope
    args = _connect_args(root, fake, *_binding_flags(grant_id, revision, approve=True))

    def denied(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["operation"] in auth.GRANT_OPERATIONS
        return auth._denied("owner_not_granted", kwargs["operation"], revision)

    def other_grant(**kwargs: Any) -> dict[str, Any]:
        resolved = real(**kwargs)
        assert resolved["access"] != "denied" and resolved["grant_id"] == grant_id
        return {**resolved, "grant_id": str(uuid.uuid4())}

    with monkeypatch.context() as stubbed, _forbid_connect(monkeypatch):
        stubbed.setattr(auth, "resolve_memory_scope", denied)
        _assert_refused(args, "E_PERMISSION", "owner_not_granted", root)
    with monkeypatch.context() as stubbed, _forbid_connect(monkeypatch):
        stubbed.setattr(auth, "resolve_memory_scope", other_grant)
        _assert_refused(args, "E_PERMISSION", "binding_scope_mismatch", root)
    payload = _connect(args, status="ok")
    assert payload["raw"]["memory_binding"]["grant_id"] == grant_id


def test_connect_binding_not_registered_when_connect_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--approve-memory-binding` registers only after a successful connect (status ok
    or warn with an applied `raw.apply`): a failed connect, or one that applied
    nothing, leaves the policy file byte-identical and the binding at `preview`."""
    from rush.tools.agent_connection import AgentConnectionTool

    fake = _fake_rush(tmp_path)
    original = AgentConnectionTool.run

    def failed(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        raw = result["raw"]
        assert raw is not None and isinstance(raw.get("apply"), dict)
        result["status"] = "fail"
        return result

    def unapplied(self: Any, *args: Any, **kwargs: Any) -> Any:
        result = original(self, *args, **kwargs)
        raw = result["raw"]
        assert raw is not None and result["status"] in ("ok", "warn")
        raw.pop("apply", None)
        return result

    for index, stub in enumerate((failed, unapplied)):
        root = _project(tmp_path, f"project-{index}")
        grant_id = _grant(root)["grant_id"]
        revision = int(_policy()["policy_revision"])
        sealed = _policy_bytes()
        with monkeypatch.context() as patched:
            patched.setattr(AgentConnectionTool, "run", stub)
            _exit_code, payload, output = _cli(
                *_connect_args(
                    root,
                    fake,
                    *_binding_flags(grant_id, revision, approve=True),
                    session=f"S-fail-{index}",
                ),
                "--json",
            )
        assert payload is not None, output
        assert payload["raw"]["memory_binding"] == {
            "state": "preview",
            "grant_id": grant_id,
            "session_id": f"S-fail-{index}",
            "host_id": "codex",
            "expected_policy_revision": revision,
        }, payload
        assert _policy_bytes() == sealed
        assert _policy()["bindings"] == {}


def test_disconnect_listing_scope_and_policy_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The disconnect listing shows a grant only when it names this project AND this
    worktree, and nothing at all under a non-`ok` policy state, whatever the
    policy still holds."""
    from rush.memory import authorization as auth

    a = _project(tmp_path, "A")
    b = _project(tmp_path, "B")
    mine = _grant(a)
    strange = _grant(a, owner=_owner("user", "strange"))
    foreign = _grant(b)
    auth.register_memory_binding(
        grant_id=mine["grant_id"],
        session_id="s1",
        host_id="codex",
        expected_policy_revision=int(_policy()["policy_revision"]),
        consent=True,
        data_root=_data_root(),
    )
    grants = _policy()["grants"]
    assert (
        grants[mine["grant_id"]]["project_id"]
        == grants[strange["grant_id"]]["project_id"]
    )
    assert (
        grants[mine["grant_id"]]["project_id"]
        != grants[foreign["grant_id"]]["project_id"]
    )
    worktree = grants[mine["grant_id"]]["worktree_id"]
    sealed = _policy_bytes()

    def listed() -> dict[str, Any]:
        exit_code, payload, output = _cli(
            "agent", "disconnect", "codex", "--project", str(a), "--json"
        )
        assert exit_code == 0 and payload is not None, output
        return cast("dict[str, Any]", payload["raw"]["memory"])

    # The first `disconnect` creates only its ledger lock's `Rush/agents` dir under
    # HOME (the read-only memory listing writes nothing, in this project or any
    # other); run it once so the forged listing below starts from a settled state.
    listed()

    # Another project's grant carrying this worktree ID, and this project's grant
    # carrying another worktree ID, are both left out.
    forged = {
        foreign["grant_id"]: {"worktree_id": worktree},
        strange["grant_id"]: {"worktree_id": "0" * 64},
    }
    with _forged_grant_fields(forged):
        forged_bytes = _policy_bytes()
        before = _state(a, b)
        assert [g["grant_id"] for g in listed()["grants"]] == [mine["grant_id"]]
        assert _policy_bytes() == forged_bytes
        assert _state(a, b) == before
    assert _policy_bytes() == sealed
    assert [g["grant_id"] for g in listed()["grants"]] == sorted(
        [mine["grant_id"], strange["grant_id"]]
    )

    # A non-ok state lists nothing even when the loaded policy still carries rows.
    real = auth.load_policy_readonly
    assert listed()["bindings"]
    with monkeypatch.context() as stubbed:
        stubbed.setattr(
            auth,
            "load_policy_readonly",
            lambda **kwargs: {**real(**kwargs), "state": "invalid"},
        )
        assert listed() == {"grants": [], "bindings": []}
    assert _policy_bytes() == sealed
