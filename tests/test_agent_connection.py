"""Tests for `rush.integrations.agents` (Phase 65 P65-05, F35).

Every filesystem interaction below points at an isolated tmp_path `home` --
never a real installed client's actual config file. `discover_agents` /
`plan_agent_registration` / `apply_agent_registration` / `probe_agent_
connection` all take an explicit `home` (and, for the native path, PATH is
monkeypatched to a fake script) so nothing here can touch a real Claude
Desktop, Cursor, Windsurf, Zed, or Codex CLI installation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

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

    plan = plan_agent_registration(adapter_id, rush_binary=RUSH_BINARY, home=home)
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

    statuses = discover_agents(home=home, rush_binary=RUSH_BINARY)
    entry = next(s for s in statuses if s.agent_id == adapter_id)
    assert entry.status == "registered"

    # Re-applying (repeated install) must never duplicate the rush entry.
    plan2 = plan_agent_registration(adapter_id, rush_binary=RUSH_BINARY, home=home)
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


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
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
    assert entry == {"command": RUSH_BINARY, "args": ["mcp", "serve"]}
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
        f"mcp add rush --scope user -- {RUSH_BINARY} mcp serve",
        "mcp remove rush --scope user",
        f"mcp add rush --scope user -- {RUSH_BINARY} mcp serve",
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
