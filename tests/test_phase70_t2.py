"""Phase 70 T2 -- Native packages for Claude Code and Codex CLI.

Test matrix for `.scratch/phase-70-design-gate/W1-T1-T7-T23.md` (## T2,
sections 1/2/5/6) and the T2 packet in
`docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` (#### T2).

**Owner scope decision (4f1414f, 2026-09-26):** Cursor is removed from
Phase 70. The plan/brief headings still say "all three hosts" / "Cursor,
Codex" -- every Cursor-only case below is dropped; only Claude Code and
Codex CLI are exercised.

Confirmed by reading the real current tree before writing every assertion
below (no repo edits made):
- `src/rush/integrations/agents.py` has `ADAPTERS["claude-code"]` and
  `ADAPTERS["codex"]`, `build_stdio_entry`, `resolve_rush_binary` -- but no
  `agent_assets` package, no materialization function, no native-plugin
  install/upgrade function, and no ownership ledger writer (T3's job).
- `src/rush/tools/install.py` has no `--agent-plugin` support and no
  reference to `agent_assets`.
- `src/rush/cli.py` has no `agent hook` subcommand.
- `.github/workflows/release.yml:91` runs
  `pyinstaller --onefile --name rush --paths src --collect-data
  license_expression rush_entry.py` -- no `--collect-data rush.integrations`
  and no `--add-data` for `agent_assets`.
- `pyproject.toml` `[tool.hatch.build.targets.wheel]` only sets
  `packages = ["src/rush", "scripts"]`; nothing agent_assets-specific.
- `src/rush/integrations/agent_assets/` does not exist anywhere on disk.

Every test below therefore fails today with a real, decisive reason: either
T2's own module/function/CLI surface does not exist yet (`ModuleNotFoundError`/
`ImportError`/`AttributeError`, imported *inside* the test so each case is
its own collection unit and its own failure), or (labelled `RED-via-T1` /
`RED-via-T3` in the docstring) the case is observably blocked on a named
predecessor that this brief runs before T2: T1's canonical skill file, or
T3's ownership ledger. Every one of those still asserts T2's own exact
contract (call shape, retained/removed directories, ledger kind values) --
none of them is satisfied merely by the predecessor landing.

Assumed T2 API surface (T2's own naming choice; not yet real, chosen here
only so the test bodies are runnable and unambiguous about what "pass"
means): `rush.integrations.agents.materialize_agent_plugins(data_root,
rush_version, rush_binary)` returns `{host: plugin_root_path}` for
`host in ("claude", "codex")`; `rush.tools.install.install_native_agent_plugin`
and `..upgrade_native_agent_plugin` take `host`/`plugin_root`/isolated
config-dir kwargs and return a state dict; `rush agent hook HOST` is a CLI
subcommand added to `rush.cli.cli`.

Zero-spawn spies patch both `subprocess.run` and `subprocess.Popen` on the
stdlib `subprocess` module directly (matches `test_phase70_t9.py`), since
every native host CLI call this task makes must route through one of those
two and nothing here should ever fork a real `claude`/`codex` process.
"""

from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.filterwarnings("ignore")

REPO_ROOT = Path(__file__).resolve().parent.parent


def _install_subprocess_spy(monkeypatch: pytest.MonkeyPatch, *, result=None):
    """Record every subprocess call instead of spawning it; never lets a
    real `claude`/`codex` process run."""
    calls: list[tuple[str, ...]] = []
    fake_result = result or subprocess.CompletedProcess(
        args=(), returncode=0, stdout="", stderr=""
    )

    def _spy(argv, *_args, **_kwargs):
        recorded = tuple(argv) if isinstance(argv, (list, tuple)) else (str(argv),)
        calls.append(recorded)
        return fake_result

    monkeypatch.setattr(subprocess, "run", _spy)
    monkeypatch.setattr(subprocess, "Popen", _spy)
    # Host-binary-free (design brief X-HOSTS): report `claude`/`codex` as
    # present so the spied route runs on machines without them (CI). The
    # missing-host test re-patches this to None after installing the spy.
    monkeypatch.setattr("shutil.which", lambda name: f"/fake/bin/{name}")
    return calls


def _isolated_homes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Isolated HOME/CLAUDE_CONFIG_DIR/CODEX_HOME so a test can never touch
    the owner's real `~/.claude` or `~/.codex`."""
    home = tmp_path / "home"
    claude_dir = tmp_path / "claude-config"
    codex_dir = tmp_path / "codex-config"
    home.mkdir()
    claude_dir.mkdir()
    codex_dir.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_dir))
    monkeypatch.setenv("CODEX_HOME", str(codex_dir))
    return {"home": home, "claude": claude_dir, "codex": codex_dir}


# ---------------------------------------------------------------------------
# Group A -- packaged sources parse and close (brief §1.1, §1.7)
# ---------------------------------------------------------------------------


def test_t02_claude_asset_files_exist_and_parse():
    """`src/rush/integrations/agent_assets/claude/` must contain the
    §8.1-corrected file set and every JSON file must parse.
    RED: `agent_assets/` does not exist anywhere in the tree yet."""
    root = REPO_ROOT / "src/rush/integrations/agent_assets/claude"
    required = [
        root / ".claude-plugin/plugin.json",
        root / ".mcp.json",
        root / "skills/rush/SKILL.md",
        root / "hooks/hooks.json",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    assert not missing, f"missing Claude package sources: {missing}"
    for p in required:
        if p.suffix == ".json":
            json.loads(p.read_text())


def test_t02_claude_marketplace_manifest_exists_and_parses():
    """`.claude-plugin/marketplace.json` names the `rush-local` marketplace
    and a `rush` plugin sourced from `./rush`.
    RED: the file does not exist."""
    manifest_path = (
        REPO_ROOT
        / "src/rush/integrations/agent_assets/claude/.claude-plugin/marketplace.json"
    )
    assert manifest_path.is_file(), f"missing {manifest_path}"
    manifest = json.loads(manifest_path.read_text())
    assert manifest.get("name") == "rush-local"
    plugins = manifest.get("plugins", [])
    assert any(
        p.get("name") == "rush" and p.get("source") == "./rush" for p in plugins
    ), f"expected a rush plugin sourced from ./rush, got {plugins!r}"


def test_t02_codex_asset_files_exist_and_parse():
    """`src/rush/integrations/agent_assets/codex/` uses `.codex-plugin/
    plugin.json` (X8 correction), never a root `plugin.json`.
    RED: `agent_assets/` does not exist yet."""
    root = REPO_ROOT / "src/rush/integrations/agent_assets/codex"
    required = [
        root / ".codex-plugin/plugin.json",
        root / "mcp.json",
        root / "skills/rush/SKILL.md",
        root / "hooks/hooks.json",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    assert not missing, f"missing Codex package sources: {missing}"
    for p in required:
        if p.suffix == ".json":
            json.loads(p.read_text())
    assert not (root / "plugin.json").exists(), (
        "root plugin.json is the X8-proven-broken layout; must not exist"
    )


def test_t02_codex_manifest_declares_mcp_skills_and_hooks_explicitly():
    """X8 resolution 1: `.codex-plugin/plugin.json` must explicitly name
    `mcpServers`, `skills`, and `hooks` or Codex 0.155.1 loads none of them.
    RED: the manifest does not exist yet."""
    manifest_path = (
        REPO_ROOT / "src/rush/integrations/agent_assets/codex/.codex-plugin/plugin.json"
    )
    assert manifest_path.is_file(), f"missing {manifest_path}"
    manifest = json.loads(manifest_path.read_text())
    assert manifest.get("mcpServers") == "./mcp.json"
    assert manifest.get("skills") == "./skills/"
    assert manifest.get("hooks") == "./hooks/hooks.json"


@pytest.mark.parametrize("host", ["claude", "codex"])
def test_t02_manifest_referenced_paths_all_resolve(host: str):
    """Every relative path referenced by a host's manifest(s) must exist
    under that host's package root (materialization must never ship a
    manifest pointing at a missing file).
    RED: `agent_assets/` does not exist yet."""
    root = REPO_ROOT / f"src/rush/integrations/agent_assets/{host}"
    assert root.is_dir(), f"missing package root: {root}"
    mcp_file = ".mcp.json" if host == "claude" else "mcp.json"
    hooks_file = root / "hooks/hooks.json"
    skill_file = root / "skills/rush/SKILL.md"
    assert (root / mcp_file).is_file()
    assert hooks_file.is_file()
    assert skill_file.is_file()


# ---------------------------------------------------------------------------
# Group B -- materialization into <data_root>/agent-plugins/<version>/ (brief §1.2)
# ---------------------------------------------------------------------------


def test_t02_materialize_creates_versioned_layout_for_both_hosts(tmp_path: Path):
    """RED: `rush.integrations.agents.materialize_agent_plugins` does not
    exist yet (ModuleNotFoundError/ImportError/AttributeError)."""
    from rush.integrations.agents import materialize_agent_plugins

    data_root = tmp_path / "data"
    result = materialize_agent_plugins(
        data_root=data_root, rush_version="9.9.9", rush_binary="/usr/local/bin/rush"
    )
    assert set(result) == {"claude", "codex"}
    for host, root in result.items():
        root = Path(root)
        assert root == data_root / "agent-plugins" / "9.9.9" / host
        assert root.is_dir()


def test_t02_materialize_substitutes_absolute_rush_binary_path(tmp_path: Path):
    """The verified absolute Rush path is substituted into `.mcp.json`/
    `mcp.json` (`mcp serve --profile core`) and `hooks/hooks.json`
    (`<rush> agent hook <host>`).
    RED: materialization does not exist yet."""
    from rush.integrations.agents import materialize_agent_plugins

    data_root = tmp_path / "data"
    binary = "/opt/verified/rush"
    result = materialize_agent_plugins(
        data_root=data_root, rush_version="1.0.0", rush_binary=binary
    )

    claude_mcp = json.loads((Path(result["claude"]) / "rush/.mcp.json").read_text())
    entry = claude_mcp["mcpServers"]["rush"]
    assert entry["command"] == binary
    assert entry["args"] == ["mcp", "serve", "--profile", "core"]

    codex_mcp = json.loads((Path(result["codex"]) / "rush/mcp.json").read_text())
    entry = codex_mcp["mcpServers"]["rush"]
    assert entry["command"] == binary
    assert entry["args"] == ["mcp", "serve", "--profile", "core"]

    for host in ("claude", "codex"):
        hooks = json.loads((Path(result[host]) / "rush/hooks/hooks.json").read_text())
        rendered = json.dumps(hooks)
        assert f"{binary} agent hook {host}" in rendered


def test_t02_materialize_is_cwd_independent(tmp_path: Path, monkeypatch):
    """Resource resolution must use `importlib.resources`, so running from
    an unrelated cwd produces byte-identical output.
    RED: materialization does not exist yet."""
    from rush.integrations.agents import materialize_agent_plugins

    other_cwd = tmp_path / "elsewhere"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)

    data_root = tmp_path / "data"
    result = materialize_agent_plugins(
        data_root=data_root, rush_version="1.0.0", rush_binary="/bin/rush"
    )
    claude_manifest = Path(result["claude"]) / "rush/.claude-plugin/plugin.json"
    assert claude_manifest.is_file(), (
        "materialize must resolve packaged resources regardless of cwd"
    )


def test_t02_materialize_no_mcp_json_without_manifest_reference(tmp_path: Path):
    """A materialized host root must never contain an `.mcp.json`/`mcp.json`
    that no manifest references.
    RED: materialization does not exist yet."""
    from rush.integrations.agents import materialize_agent_plugins

    data_root = tmp_path / "data"
    result = materialize_agent_plugins(
        data_root=data_root, rush_version="1.0.0", rush_binary="/bin/rush"
    )
    claude_manifest = json.loads(
        (Path(result["claude"]) / "rush/.claude-plugin/plugin.json").read_text()
    )
    rendered = json.dumps(claude_manifest)
    assert ".mcp.json" in rendered or "mcp" in rendered


# ---------------------------------------------------------------------------
# Group C -- routes (brief §1.3)
# ---------------------------------------------------------------------------


def test_t02_claude_install_route_uses_scope_user(tmp_path: Path, monkeypatch):
    """Claude route: `claude plugin marketplace add <root> --scope user`
    then `claude plugin install rush@rush-local --scope user`.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    calls = _install_subprocess_spy(monkeypatch)
    plugin_root = tmp_path / "claude-root"
    plugin_root.mkdir()
    install_native_agent_plugin(host="claude", plugin_root=plugin_root)

    joined = [" ".join(c) for c in calls]
    assert any(
        "plugin" in c
        and "marketplace" in c
        and "add" in c
        and "--scope" in c
        and "user" in c
        for c in calls
    ), joined
    assert any(
        "plugin" in c
        and "install" in c
        and "rush@rush-local" in c
        and "--scope" in c
        and "user" in c
        for c in calls
    ), joined


def test_t02_codex_install_route_uses_real_plugin_cli(tmp_path: Path, monkeypatch):
    """Codex route: `codex plugin marketplace add <root>` then
    `codex plugin add rush@rush-local` (X8: proven real CLI, not invented).
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    calls = _install_subprocess_spy(monkeypatch)
    plugin_root = tmp_path / "codex-root"
    plugin_root.mkdir()
    install_native_agent_plugin(host="codex", plugin_root=plugin_root)

    assert any(
        "codex" in c and "plugin" in c and "marketplace" in c and "add" in c
        for c in calls
    ), calls
    assert any(
        "codex" in c and "plugin" in c and "add" in c and "rush@rush-local" in c
        for c in calls
    ), calls


def test_t02_policy_denial_is_reported_not_faked(tmp_path: Path, monkeypatch):
    """A native-host approval denial (nonzero exit) must surface as an
    explicit denied state, never a faked success.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    # Exact claude 2.1.283 refusal, reproduced in an isolated home with
    # `--managed-settings '{"strictKnownMarketplaces":[]}'`.
    refusal = "Marketplace source 'dir:/x/rush-local' is blocked by enterprise policy."
    denied = subprocess.CompletedProcess(
        args=(),
        returncode=1,
        stdout="",
        stderr=f"✘ Failed to add marketplace: {refusal}",
    )
    _install_subprocess_spy(monkeypatch, result=denied)
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()

    state = install_native_agent_plugin(host="claude", plugin_root=plugin_root)
    assert state["state"] == "denied"
    assert refusal in state.get("detail", "")


def test_t02_missing_host_binary_is_reported_not_faked(tmp_path: Path, monkeypatch):
    """No `claude`/`codex` binary on PATH must be reported as an explicit
    missing-host state with zero subprocess spawns.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    calls = _install_subprocess_spy(monkeypatch)
    monkeypatch.setattr("shutil.which", lambda _name: None)
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()

    state = install_native_agent_plugin(host="claude", plugin_root=plugin_root)
    assert state["state"] == "host_missing"
    assert calls == []


# ---------------------------------------------------------------------------
# Group D -- no double registration (brief §1.4)
# ---------------------------------------------------------------------------


def test_t02_existing_manual_entry_gets_a_preview_before_any_write(
    tmp_path: Path, monkeypatch
):
    """A pre-existing manual Rush MCP entry must be previewed (diff-shaped)
    before any write happens.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    config_path = homes["claude"] / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps(
            {"mcpServers": {"rush": {"command": "/old/rush", "args": ["mcp", "serve"]}}}
        )
    )
    before = config_path.read_text()

    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    result = install_native_agent_plugin(
        host="claude",
        plugin_root=plugin_root,
        manual_config_path=config_path,
        dry_run=True,
    )
    assert "preview" in result
    assert config_path.read_text() == before, "dry_run preview must not write"


def test_t02_manual_entry_removed_before_native_install_runs(
    tmp_path: Path, monkeypatch
):
    """Ordering: the owned manual entry is removed from config before the
    native install command is spawned.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    calls = _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    config_path = homes["claude"] / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps(
            {"mcpServers": {"rush": {"command": "/old/rush", "args": ["mcp", "serve"]}}}
        )
    )

    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    install_native_agent_plugin(
        host="claude",
        plugin_root=plugin_root,
        manual_config_path=config_path,
        consent=True,
    )

    config_after_first_call = json.loads(config_path.read_text())
    assert "rush" not in config_after_first_call.get("mcpServers", {}), (
        "manual entry must be gone before/by the time native install runs"
    )
    assert calls, "expected at least one native install subprocess call"


def test_t02_install_failure_restores_the_manual_entry(tmp_path: Path, monkeypatch):
    """If the native install command fails, the removed manual entry must
    be restored byte-for-byte.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    failing = subprocess.CompletedProcess(
        args=(), returncode=1, stdout="", stderr="boom"
    )
    _install_subprocess_spy(monkeypatch, result=failing)
    homes = _isolated_homes(tmp_path, monkeypatch)
    config_path = homes["claude"] / "claude_desktop_config.json"
    original = {
        "mcpServers": {"rush": {"command": "/old/rush", "args": ["mcp", "serve"]}}
    }
    config_path.write_text(json.dumps(original))

    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    state = install_native_agent_plugin(
        host="claude",
        plugin_root=plugin_root,
        manual_config_path=config_path,
        consent=True,
    )

    assert state["state"] == "failed"
    assert json.loads(config_path.read_text()) == original


def test_t02_never_two_rush_servers_active_after_conversion(
    tmp_path: Path, monkeypatch
):
    """After a successful conversion, exactly one Rush registration is
    active: the manual key gone, the plugin recorded as installed.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    config_path = homes["claude"] / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps(
            {"mcpServers": {"rush": {"command": "/old/rush", "args": ["mcp", "serve"]}}}
        )
    )

    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    state = install_native_agent_plugin(
        host="claude",
        plugin_root=plugin_root,
        manual_config_path=config_path,
        consent=True,
    )
    assert state["state"] == "installed"
    config_after = json.loads(config_path.read_text())
    assert "rush" not in config_after.get("mcpServers", {})


# ---------------------------------------------------------------------------
# Group E -- upgrades (brief §1.5)
# ---------------------------------------------------------------------------


def test_t02_upgrade_creates_new_version_dir_and_retains_old(tmp_path: Path):
    """RED: materialization does not exist yet."""
    from rush.integrations.agents import materialize_agent_plugins

    data_root = tmp_path / "data"
    materialize_agent_plugins(
        data_root=data_root, rush_version="1.0.0", rush_binary="/bin/rush"
    )
    materialize_agent_plugins(
        data_root=data_root, rush_version="2.0.0", rush_binary="/bin/rush"
    )

    plugins_dir = data_root / "agent-plugins"
    assert (plugins_dir / "1.0.0").is_dir(), (
        "old version must be retained, not overwritten"
    )
    assert (plugins_dir / "2.0.0").is_dir()


def test_t02_upgrade_runs_the_documented_host_update_commands(
    tmp_path: Path, monkeypatch
):
    """Claude: `claude plugin marketplace update rush-local` +
    `claude plugin update rush@rush-local`. Codex: re-`plugin add`.
    RED: `upgrade_native_agent_plugin` does not exist yet."""
    from rush.tools.install import upgrade_native_agent_plugin

    calls = _install_subprocess_spy(monkeypatch)
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()

    upgrade_native_agent_plugin(host="claude", plugin_root=plugin_root)
    assert any(
        "marketplace" in c and "update" in c and "rush-local" in c for c in calls
    )
    assert any("update" in c and "rush@rush-local" in c for c in calls)

    calls.clear()
    upgrade_native_agent_plugin(host="codex", plugin_root=plugin_root)
    assert any("plugin" in c and "add" in c and "rush@rush-local" in c for c in calls)


def test_t02_old_version_removed_only_via_ledger_after_host_confirms(tmp_path: Path):
    """RED-via-T3: the old version directory must not be deleted by naive
    cleanup; it is removed only after the T3 ownership ledger
    (`<data_root>/agents/owned.json`, kind `native_plugin`/`file_resource`,
    per the T3 design section) confirms the host reports the new version.
    T3 does not exist in this worktree, so this fails today on the ledger
    import/format -- it still asserts T2's own contract: retain-until-
    confirmed, never eager delete.
    """
    from rush.integrations.agents import materialize_agent_plugins
    from rush.tools.install import finalize_agent_plugin_upgrade

    data_root = tmp_path / "data"
    materialize_agent_plugins(
        data_root=data_root, rush_version="1.0.0", rush_binary="/bin/rush"
    )
    materialize_agent_plugins(
        data_root=data_root, rush_version="2.0.0", rush_binary="/bin/rush"
    )

    old_dir = data_root / "agent-plugins" / "1.0.0"
    assert old_dir.is_dir(), "old version must still exist before finalize"

    finalize_agent_plugin_upgrade(
        data_root=data_root, host="claude", confirmed_version="2.0.0"
    )

    ledger_path = data_root / "agents" / "owned.json"
    assert ledger_path.is_file(), "T3 ownership ledger must record the removal"
    ledger = json.loads(ledger_path.read_text())
    # T3's committed ledger is a CASMapTransaction file:
    # {"schema_version", "version", "data": {entry_id: entry}}.
    kinds = {entry["kind"] for entry in ledger.get("data", {}).values()}
    assert kinds & {"native_plugin", "file_resource"}
    assert not old_dir.exists(), "old version removed only after confirmation"


# ---------------------------------------------------------------------------
# Group F -- hooks are inert until T7 activation (brief §1.6, resolution 3)
# ---------------------------------------------------------------------------


def test_t02_installing_the_package_runs_no_check_and_writes_nothing(
    tmp_path: Path, monkeypatch
):
    """Materializing + installing the package must not execute any Rush
    tool/check and must not write outside the plugin/materialize dirs.
    RED: materialization/install do not exist yet."""
    from rush.integrations.agents import materialize_agent_plugins
    from rush.tools.install import install_native_agent_plugin

    _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    before = {p for p in homes["home"].rglob("*")}

    data_root = tmp_path / "data"
    result = materialize_agent_plugins(
        data_root=data_root, rush_version="1.0.0", rush_binary="/bin/rush"
    )
    install_native_agent_plugin(host="claude", plugin_root=Path(result["claude"]))

    after = {p for p in homes["home"].rglob("*")}
    assert after == before, f"unexpected writes under HOME: {after - before}"


def test_t02_inert_hook_adapter_exits_zero_with_empty_stdout_and_zero_writes(
    tmp_path: Path, monkeypatch
):
    """`rush agent hook <host>` with no T7 activation record must parse
    argv, read the (absent) activation record without writing, and exit 0
    with no output.
    RED: `rush agent hook` does not exist in `rush.cli.cli` yet."""
    from click.testing import CliRunner

    from rush.cli import cli

    homes = _isolated_homes(tmp_path, monkeypatch)
    before = {p for p in homes["home"].rglob("*")}

    runner = CliRunner()
    invocation = runner.invoke(cli, ["agent", "hook", "claude"])

    assert invocation.exit_code == 0
    assert invocation.output == ""
    after = {p for p in homes["home"].rglob("*")}
    assert after == before


def test_t02_inert_hook_adapter_never_creates_project_or_user_state(
    tmp_path: Path, monkeypatch
):
    """X5: read-only callers must `json.loads` the activation record
    directly after an `lstat` existence check, never go through
    `CASMapTransaction` (which creates `<data_root>/user` or
    `<project>/.rush` as a side effect of merely reading).
    RED: `rush agent hook` does not exist yet."""
    from click.testing import CliRunner

    from rush.cli import cli

    homes = _isolated_homes(tmp_path, monkeypatch)
    data_root = homes["home"] / ".rush-data"
    monkeypatch.setenv("RUSH_DATA_ROOT", str(data_root))

    runner = CliRunner()
    invocation = runner.invoke(cli, ["agent", "hook", "codex"])

    assert invocation.exit_code == 0, invocation.output
    assert not (data_root / "user").exists()
    assert not data_root.exists() or not any(data_root.rglob(".rush"))


# ---------------------------------------------------------------------------
# Group G -- packaging: wheel/sdist/frozen executable (brief §1.7)
# ---------------------------------------------------------------------------


def test_t02_wheel_build_contains_dot_dirs_and_agent_assets(tmp_path: Path):
    """`uv build --wheel` into tmp must produce a wheel whose zip contains
    every host's dot-directory manifest and skill file.
    RED: `src/rush/integrations/agent_assets/` does not exist on disk, so
    none of these members can be in the built wheel."""
    out_dir = tmp_path / "dist"
    subprocess_result = subprocess.run(
        ["uv", "build", "--wheel", "-o", str(out_dir)],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert subprocess_result.returncode == 0, subprocess_result.stderr
    wheels = list(out_dir.glob("*.whl"))
    assert wheels, "expected uv build --wheel to produce a .whl"

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())

    required_suffixes = [
        "rush/integrations/agent_assets/claude/.claude-plugin/plugin.json",
        "rush/integrations/agent_assets/claude/.claude-plugin/marketplace.json",
        "rush/integrations/agent_assets/codex/.codex-plugin/plugin.json",
        "rush/integrations/agent_assets/claude/skills/rush/SKILL.md",
        "rush/integrations/agent_assets/codex/skills/rush/SKILL.md",
    ]
    missing = [
        suffix
        for suffix in required_suffixes
        if not any(name.endswith(suffix) for name in names)
    ]
    assert not missing, f"wheel is missing agent package members: {missing}"


def test_t02_release_workflow_collects_agent_integrations_data():
    """`.github/workflows/release.yml`'s pyinstaller step must ship
    `agent_assets` in the frozen executable (line 91 in the design brief).
    RED: today's line only has `--collect-data license_expression`."""
    workflow = REPO_ROOT / ".github/workflows/release.yml"
    text = workflow.read_text()
    assert "pyinstaller" in text
    has_collect = "--collect-data rush.integrations" in text
    has_add_data = "agent_assets" in text and "--add-data" in text
    assert has_collect or has_add_data, (
        "release.yml must package rush.integrations agent_assets into the "
        "frozen binary via --collect-data or --add-data"
    )


# ---------------------------------------------------------------------------
# Group H -- atomic materialization / partial-resource rollback (brief §3)
# ---------------------------------------------------------------------------


def test_t02_partial_materialization_failure_leaves_no_partial_version_dir(
    tmp_path: Path, monkeypatch
):
    """Materialize must stage -> validate -> rename atomically; a failure
    mid-copy must leave zero trace of the new version directory.
    RED: materialization does not exist yet."""
    from rush.integrations.agents import materialize_agent_plugins

    data_root = tmp_path / "data"

    import shutil as shutil_module

    original_copy = shutil_module.copy2
    call_count = {"n": 0}

    def _flaky_copy(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise OSError("simulated disk failure")
        return original_copy(*args, **kwargs)

    monkeypatch.setattr(shutil_module, "copy2", _flaky_copy)

    with pytest.raises(OSError):
        materialize_agent_plugins(
            data_root=data_root, rush_version="3.0.0", rush_binary="/bin/rush"
        )

    assert not (data_root / "agent-plugins" / "3.0.0").exists(), (
        "a failed materialize must never leave a partial version directory"
    )


# ---------------------------------------------------------------------------
# Group I -- fixture homes fresh/existing (brief §6 bullet)
# ---------------------------------------------------------------------------


def test_t02_install_on_fresh_home_with_no_existing_config(tmp_path: Path, monkeypatch):
    """A brand-new isolated home (no prior Claude/Codex config at all)
    must install structurally without crashing on missing parent dirs.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    calls = _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    for d in homes.values():
        for child in d.iterdir():
            child.unlink()

    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    state = install_native_agent_plugin(host="codex", plugin_root=plugin_root)
    assert state["state"] == "installed"
    assert calls


def test_t02_install_preserves_unrelated_existing_config_content(
    tmp_path: Path, monkeypatch
):
    """Pre-existing unrelated config keys survive conversion untouched.
    RED: `install_native_agent_plugin` does not exist yet."""
    from rush.tools.install import install_native_agent_plugin

    _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    config_path = homes["claude"] / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps(
            {"mcpServers": {"other-tool": {"command": "/bin/other"}}, "theme": "dark"}
        )
    )

    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    install_native_agent_plugin(
        host="claude", plugin_root=plugin_root, manual_config_path=config_path
    )

    after = json.loads(config_path.read_text())
    assert after["mcpServers"]["other-tool"] == {"command": "/bin/other"}
    assert after["theme"] == "dark"


# ---------------------------------------------------------------------------
# Group J -- skill semantic-parity check (brief §6 bullet; RED-via-T1)
# ---------------------------------------------------------------------------


def test_t02_packaged_skill_copies_match_canonical_skill_byte_for_byte():
    """RED-via-T1: T1 owns the single canonical skill at
    `src/rush/integrations/agent_assets/skills/rush/SKILL.md`
    (`.scratch/phase-70-design-gate/W1-T1-T7-T23.md` ## T1 section 2). T2
    copies it into each host package "with a semantic-parity check". This
    fails today because T1 has not created the canonical file, so there is
    nothing yet for either host copy to match -- it still asserts T2's own
    contract: both host copies equal the canonical source exactly."""
    canonical = REPO_ROOT / "src/rush/integrations/agent_assets/skills/rush/SKILL.md"
    assert canonical.is_file(), (
        "canonical skill (T1 deliverable) must exist before parity can be checked"
    )
    canonical_text = canonical.read_text()

    for host in ("claude", "codex"):
        host_copy = (
            REPO_ROOT
            / f"src/rush/integrations/agent_assets/{host}/skills/rush/SKILL.md"
        )
        assert host_copy.is_file(), f"missing {host} packaged skill copy"
        assert host_copy.read_text() == canonical_text, (
            f"{host} skill copy diverges from canonical (semantic-parity check)"
        )


def test_t02_codex_skill_namespace_is_rush_rush():
    """X8 (proven): Codex exposes the skill as `rush:rush` in
    `codex debug prompt-input`; the packaged skill directory name must be
    `rush` so that namespace holds without extra renaming logic.
    RED: `agent_assets/codex/skills/` does not exist yet."""
    skill_dir = REPO_ROOT / "src/rush/integrations/agent_assets/codex/skills/rush"
    assert skill_dir.is_dir()
    assert (skill_dir / "SKILL.md").is_file()


# ---------------------------------------------------------------------------
# Group K -- T3 disconnect meets a native plugin (T2 ledger kinds)
# ---------------------------------------------------------------------------


def test_t02_disconnect_uninstalls_native_plugin_before_removing_its_files(
    tmp_path: Path, monkeypatch
):
    """`rush agent disconnect codex` must uninstall the plugin through the
    host's own CLI before deleting the files it runs from, leave the other
    host's package alone, and be a no-op the second time."""
    from rush.integrations.agents import (
        disconnect_agent,
        materialize_agent_plugins,
        record_native_plugin_install,
    )

    calls = _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    data_root = tmp_path / "data"
    roots = materialize_agent_plugins(
        data_root=data_root, rush_version="1.0.0", rush_binary="/bin/rush"
    )
    record_native_plugin_install(
        data_root=data_root, host="codex", plugin_root=roots["codex"]
    )

    result = disconnect_agent(
        "codex", project_root=None, data_root=data_root, home=homes["home"]
    )
    assert result.status == "ok", result.conflicts
    assert calls == [
        ("codex", "plugin", "remove", "rush@rush-local"),
        ("codex", "plugin", "marketplace", "remove", "rush-local"),
    ]
    assert not roots["codex"].exists()
    assert roots["claude"].is_dir()

    again = disconnect_agent(
        "codex", project_root=None, data_root=data_root, home=homes["home"]
    )
    assert again.status == "ok" and again.removed == []
    assert len(calls) == 2


def test_t02_install_tool_agent_plugin_route_replaces_manual_connection(
    tmp_path: Path, monkeypatch
):
    """`rush install --agent-plugin codex`: the verified binary is baked into
    the materialized plugin, the Rush-written manual `[mcp_servers.rush]`
    entry is converted away, the host is not also connected manually, and
    the install is recorded as a `native_plugin` ledger row."""
    import hashlib
    import io
    import platform
    import tarfile

    from rush.permissions import ExecutionPermissions
    from rush.tools.install import InstallTool, select_release_asset

    calls = _install_subprocess_spy(monkeypatch)
    home = tmp_path / "home"
    codex_config = home / ".codex" / "config.toml"
    codex_config.parent.mkdir(parents=True)
    codex_config.write_text(
        '[mcp_servers.rush]\ncommand = "/old/rush"\nargs = ["mcp", "serve"]\n'
    )
    script = b"#!/bin/sh\nexit 0\n"
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="rush")
        info.size, info.mode = len(script), 0o755
        tar.addfile(info, io.BytesIO(script))
    asset = select_release_asset(platform.system(), platform.machine())
    sums = f"{hashlib.sha256(archive.getvalue()).hexdigest()}  {asset}\n".encode()
    assets = {asset: archive.getvalue(), "SHA256SUMS": sums}
    data_root = tmp_path / "data"

    result = InstallTool().run(
        agents="all",
        home=home,
        os_name=platform.system(),
        data_root=data_root,
        install_dir=tmp_path / "bin",
        downloader=lambda url: assets[url.rsplit("/", 1)[-1]],
        prober=lambda argv: subprocess.CompletedProcess(argv, 0, "", ""),
        permissions=ExecutionPermissions(
            network=True, download=True, cache_write=True, artifact_write=True
        ),
        agent_plugins=("codex",),
        convert_manual_entry=True,
    )

    assert result["status"] == "ok", result
    raw = result["raw"]
    assert raw["agent_plugins"]["codex"]["state"] == "installed"
    codex_report = next(a for a in raw["agents"] if a["agent_id"] == "codex")
    assert codex_report["state"] == "native_plugin"
    assert "mcp_servers.rush" not in codex_config.read_text()
    assert ("codex", "plugin", "add", "rush@rush-local") in calls

    plugin_root = Path(raw["agent_plugins"]["codex"]["plugin_root"])
    mcp = json.loads((plugin_root / "rush" / "mcp.json").read_text())
    assert mcp["mcpServers"]["rush"]["command"] == str(
        (tmp_path / "bin" / "rush").resolve()
    )
    ledger = json.loads((data_root / "agents" / "owned.json").read_text())
    assert any(
        row["kind"] == "native_plugin" and row["host"] == "codex"
        for row in ledger["data"].values()
    )


# ---------------------------------------------------------------------------
# Group L -- host exit states: denied only on a real refusal (fix round 1)
# ---------------------------------------------------------------------------


def test_t02_codex_policy_refusal_is_denied(tmp_path: Path, monkeypatch):
    """Exact codex 0.155.1 refusal for a marketplace entry with
    `"policy": {"installation": "NOT_AVAILABLE"}`, reproduced in an isolated
    CODEX_HOME."""
    from rush.tools.install import install_native_agent_plugin

    refusal = "plugin `rush` is not available for install in marketplace `rush-local`"
    _install_subprocess_spy(
        monkeypatch,
        result=subprocess.CompletedProcess(
            args=(), returncode=1, stdout="", stderr=f"Error: {refusal}\n"
        ),
    )
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    state = install_native_agent_plugin(host="codex", plugin_root=plugin_root)
    assert state["state"] == "denied"
    assert refusal in state["detail"]


def test_t02_other_nonzero_host_exit_is_failed_with_code_and_redacted_tail(
    tmp_path: Path, monkeypatch
):
    """A crash or ordinary error is `failed`, never `denied`: exit code kept,
    stderr tail redacted."""
    from rush.tools.install import install_native_agent_plugin

    secret = "ghp_abcdefghijklmnopqrstuvwxyz0123456789AB"
    stderr = "x" * 5000 + (
        "\nError: failed to resolve local marketplace source path: No such file "
        f"or directory (os error 2) token={secret}\n"
    )
    _install_subprocess_spy(
        monkeypatch,
        result=subprocess.CompletedProcess(
            args=(), returncode=101, stdout="", stderr=stderr
        ),
    )
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    state = install_native_agent_plugin(host="codex", plugin_root=plugin_root)
    assert state["state"] == "failed"
    assert state["exit_code"] == 101
    assert "No such file or directory" in state["detail"]
    assert secret not in state["detail"]
    assert len(state["detail"]) <= 2100


# ---------------------------------------------------------------------------
# Group M -- manual-entry ownership is ledger-only (fix round 1)
# ---------------------------------------------------------------------------

_RUSH_SHAPED = {
    "mcpServers": {"rush": {"command": "/old/rush", "args": ["mcp", "serve"]}}
}


def _claude_manual_config(tmp_path: Path, monkeypatch) -> Path:
    homes = _isolated_homes(tmp_path, monkeypatch)
    config_path = homes["claude"] / "claude_desktop_config.json"
    config_path.write_text(json.dumps(_RUSH_SHAPED))
    return config_path


@pytest.mark.parametrize("consent", [False, lambda _removal: False])
def test_t02_unrecorded_rush_shaped_entry_without_consent_is_left_unchanged(
    tmp_path: Path, monkeypatch, consent
):
    """Looking like Rush's own output is not ownership: without consent (no
    flag, or a declined prompt) the bytes stay identical and no host command
    runs, so no second Rush server is registered either."""
    from rush.tools.install import install_native_agent_plugin

    calls = _install_subprocess_spy(monkeypatch)
    config_path = _claude_manual_config(tmp_path, monkeypatch)
    before = config_path.read_bytes()
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()

    state = install_native_agent_plugin(
        host="claude",
        plugin_root=plugin_root,
        manual_config_path=config_path,
        data_root=tmp_path / "data",
        consent=consent,
    )
    assert state["state"] == ("declined" if callable(consent) else "consent_required")
    assert state["preview"]["conversion"]["consent_required"] is True
    assert "-" in state["preview"]["conversion"]["diff"]
    assert config_path.read_bytes() == before
    assert calls == []
    assert not (tmp_path / "data" / "agents" / "owned.json").exists()


def test_t02_accepted_unrecorded_entry_is_converted_and_recorded(
    tmp_path: Path, monkeypatch
):
    """Accepting the shown removal converts the entry and records it in the
    ledger on the `native_plugin` row."""
    from rush.tools.install import install_native_agent_plugin

    _install_subprocess_spy(monkeypatch)
    config_path = _claude_manual_config(tmp_path, monkeypatch)
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()
    shown: list = []
    data_root = tmp_path / "data"

    state = install_native_agent_plugin(
        host="claude",
        plugin_root=plugin_root,
        manual_config_path=config_path,
        data_root=data_root,
        consent=lambda removal: shown.append(removal) or True,
    )
    assert state["state"] == "installed"
    assert shown and shown[0].path == config_path
    assert "rush" not in json.loads(config_path.read_text())["mcpServers"]
    ledger = json.loads((data_root / "agents" / "owned.json").read_text())
    rows = [r for r in ledger["data"].values() if r["kind"] == "native_plugin"]
    assert rows[0]["replaced_entry"] == {
        "path": str(config_path),
        "sha256": shown[0].entry_sha256,
        "owned_before": False,
    }


def test_t02_ledger_recorded_entry_converts_without_prompt(tmp_path: Path, monkeypatch):
    """An entry whose exact digest the T3 ledger records at this path is
    Rush's own and converts with no consent prompt."""
    import hashlib

    from rush.tools.install import install_native_agent_plugin

    _install_subprocess_spy(monkeypatch)
    config_path = _claude_manual_config(tmp_path, monkeypatch)
    entry = _RUSH_SHAPED["mcpServers"]["rush"]
    digest = hashlib.sha256(
        json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    data_root = tmp_path / "data"
    (data_root / "agents").mkdir(parents=True)
    row_id = f"claude-code:mcp_entry:{config_path}:user"
    (data_root / "agents" / "owned.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "version": 1,
                "data": {
                    row_id: {
                        "id": row_id,
                        "kind": "mcp_entry",
                        "host": "claude-code",
                        "project_root": None,
                        "path": str(config_path),
                        "written_sha256": digest,
                        "original_sha256": None,
                    }
                },
            }
        )
    )
    plugin_root = tmp_path / "root"
    plugin_root.mkdir()

    def never_asked(_removal):
        raise AssertionError("a ledger-owned entry must not prompt")

    state = install_native_agent_plugin(
        host="claude",
        plugin_root=plugin_root,
        manual_config_path=config_path,
        data_root=data_root,
        consent=never_asked,
    )
    assert state["state"] == "installed"
    assert "rush" not in json.loads(config_path.read_text())["mcpServers"]
    ledger = json.loads((data_root / "agents" / "owned.json").read_text())
    assert row_id not in ledger["data"]


def test_t02_disconnect_never_touches_an_unrecorded_entry(tmp_path: Path, monkeypatch):
    """A Rush-shaped `[mcp_servers.rush]` the ledger never recorded survives
    `disconnect` byte-for-byte."""
    from rush.integrations.agents import disconnect_agent

    calls = _install_subprocess_spy(monkeypatch)
    homes = _isolated_homes(tmp_path, monkeypatch)
    config_path = homes["home"] / ".codex" / "config.toml"
    config_path.parent.mkdir()
    config_path.write_text(
        '[mcp_servers.rush]\ncommand = "/old/rush"\nargs = ["mcp", "serve"]\n'
    )
    before = config_path.read_bytes()

    result = disconnect_agent(
        "codex", project_root=None, data_root=tmp_path / "data", home=homes["home"]
    )
    assert config_path.read_bytes() == before
    assert "mcp_entry" not in result.removed
    assert calls == []


def demo() -> None:
    """Ponytail self-check: the purely-static assertions, run directly with
    `python -m tests.test_phase70_t2`. Proves the release.yml/asset-path
    checks are live logic, not vacuous."""
    workflow = REPO_ROOT / ".github/workflows/release.yml"
    assert workflow.is_file()
    assert "pyinstaller" in workflow.read_text()
    assert (REPO_ROOT / "src/rush/integrations/agent_assets").is_dir()


if __name__ == "__main__":
    demo()
    print("ok")
