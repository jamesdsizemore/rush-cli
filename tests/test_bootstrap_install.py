"""Tests for `rush.tools.install.InstallTool` (Phase 65 P65-10, F35/F42).

Every filesystem interaction points at an isolated tmp_path `home`/`data_root`/
`install_dir` -- never a real installed client's config or the real
production Rush data root. The release archive is a real self-contained
POSIX shell script wrapped in a genuine tar.gz (built the same way P65-01's
`tests/test_release_asset_contract.py` builds its fixtures), so "does the
binary actually start" is a real subprocess probe, not a mocked-until-it-
works stand-in. `select_release_asset` is exercised across all six
OS/architecture pairs the release matrix covers.
"""

from __future__ import annotations

import io
import json
import os
import tarfile
from pathlib import Path

import pytest

from rush.integrations import agents as agents_mod
from rush.integrations.agents import ADAPTERS, read_agent_memory_state
from rush.permissions import ExecutionPermissions
from rush.tools import install as install_mod
from rush.tools.install import InstallTool, select_release_asset
from rush.workflows.projects import list_projects, register_project

_FULL_PERMISSIONS = ExecutionPermissions(
    network=True, download=True, cache_write=True, artifact_write=True
)

# --- Fixtures shared by every InstallTool test ------------------------------

SIX_WAY_MATRIX = [
    ("Darwin", "arm64", "rush-darwin-arm64.tar.gz"),
    ("Darwin", "x86_64", "rush-darwin-x86_64.tar.gz"),
    ("Linux", "x86_64", "rush-linux-x86_64.tar.gz"),
    ("Linux", "aarch64", "rush-linux-arm64.tar.gz"),
    ("Windows", "AMD64", "rush-windows-x86_64.zip"),
    ("Windows", "arm64", "rush-windows-arm64.zip"),
]

_BINARY_SCRIPT = (
    b'#!/bin/sh\nif [ "$1" = "--version" ]; then\n  echo 9.9.9\nfi\nexit 0\n'
)
_FAILING_BINARY_SCRIPT = b"#!/bin/sh\nexit 1\n"


def _build_archive(binary_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="rush")
        info.size = len(binary_bytes)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(binary_bytes))
    return buf.getvalue()


def _sha256sums(digest_bytes: bytes, asset_name: str) -> str:
    import hashlib

    return f"{hashlib.sha256(digest_bytes).hexdigest()}  {asset_name}\n"


def _fake_downloader(assets: dict[str, bytes]):
    def _download(url: str) -> bytes:
        name = url.rsplit("/", 1)[-1]
        return assets[name]

    return _download


def _home_with(tmp_path: Path, adapter_id: str, text: str) -> Path:
    home = tmp_path / "home"
    path = ADAPTERS[adapter_id].config_paths("Darwin", home)[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return home


CURSOR_JSON = json.dumps({"mcpServers": {}}, indent=2)


def _release_fixture(
    binary_bytes: bytes = _BINARY_SCRIPT,
) -> tuple[str, dict[str, bytes]]:
    """Build a valid archive + SHA256SUMS for the current real host's asset name."""
    import platform

    asset_name = select_release_asset(platform.system(), platform.machine())
    archive_bytes = _build_archive(binary_bytes)
    sums_text = _sha256sums(archive_bytes, asset_name)
    return asset_name, {
        asset_name: archive_bytes,
        "SHA256SUMS": sums_text.encode("utf-8"),
    }


# --- Static contract: the streamed shell/PowerShell installers -------------


def test_streamed_installer_has_no_checkout_or_python_dependency() -> None:
    """The curl|sh / irm|iex installers never require a source checkout or Python."""
    repo_root = Path(__file__).resolve().parents[1]
    sh_text = (repo_root / "scripts" / "install.sh").read_text(encoding="utf-8")
    ps1_text = (repo_root / "scripts" / "install.ps1").read_text(encoding="utf-8")

    forbidden_sh = ["uv tool install", "--editable", "dirname", "python", "pip install"]
    for token in forbidden_sh:
        assert token not in sh_text, f"install.sh must not depend on {token!r}"

    forbidden_ps1 = ["python", "uv tool install", "--editable", "$PSScriptRoot"]
    for token in forbidden_ps1:
        assert token not in ps1_text, f"install.ps1 must not depend on {token!r}"

    # Both scripts hand off to the InstallTool-backed CLI command once the
    # verified binary is in place -- never a second download/verify path.
    assert "install --agents all --memory on" in sh_text
    assert "install --agents all --memory on" in ps1_text


# --- Six-way platform asset selection (mirrors P65-01's own matrix) --------


@pytest.mark.parametrize("system,machine,expected_name", SIX_WAY_MATRIX)
def test_platform_asset_selection_covers_six_way_matrix(
    system: str, machine: str, expected_name: str
) -> None:
    assert select_release_asset(system, machine) == expected_name


def test_release_asset_matrix_matches_canonical_probe_matrix() -> None:
    """Guards against install.py's necessarily-duplicated matrix drifting from
    scripts/probe_installed_artifacts.py's (the two can't share one module:
    scripts/ is never bundled into the shipped PyInstaller binary)."""
    from scripts.probe_installed_artifacts import PLATFORM_ASSET_MATRIX

    assert install_mod.RELEASE_ASSET_MATRIX == PLATFORM_ASSET_MATRIX


def test_unsupported_platform_rejected() -> None:
    with pytest.raises(install_mod.UnsupportedPlatformError):
        select_release_asset("Plan9", "riscv64")


# --- Checksum integrity: a bad checksum must never touch a prior install ---


def test_bad_checksum_leaves_previous_install_intact(tmp_path: Path) -> None:
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    previous_binary = install_dir / "rush"
    previous_binary.write_bytes(b"#!/bin/sh\necho old\n")
    previous_binary.chmod(0o755)
    previous_bytes = previous_binary.read_bytes()

    asset_name, assets = _release_fixture()
    # Corrupt the checksum manifest so the (otherwise valid) archive fails
    # verification -- never fabricate a pass.
    assets["SHA256SUMS"] = (("0" * 64) + f"  {asset_name}\n").encode("utf-8")

    result = InstallTool().run(
        agents="none",
        data_root=tmp_path / "data",
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "error"
    assert result["raw"]["code"] == "CHECKSUM_MISMATCH"
    assert previous_binary.read_bytes() == previous_bytes
    # No stray temp/backup artifacts left behind by a refused install.
    assert sorted(p.name for p in install_dir.iterdir()) == ["rush"]


def test_interrupted_upgrade_restores_prior_executable(tmp_path: Path) -> None:
    """A checksum-valid but corrupt/incompatible archive must not clobber the
    executable that was already working."""
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    previous_binary = install_dir / "rush"
    previous_binary.write_bytes(b"#!/bin/sh\necho old\n")
    previous_binary.chmod(0o755)
    previous_bytes = previous_binary.read_bytes()

    asset_name, _ = _release_fixture()
    # A checksum-valid archive that isn't a real tar.gz at all -- extraction
    # itself fails, after the checksum already passed.
    garbage = b"not actually a tarball"
    assets = {
        asset_name: garbage,
        "SHA256SUMS": _sha256sums(garbage, asset_name).encode(),
    }

    result = InstallTool().run(
        agents="none",
        data_root=tmp_path / "data",
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "error"
    assert result["raw"]["code"] == "EXTRACT_FAILED"
    assert previous_binary.read_bytes() == previous_bytes


def test_binary_verify_failure_restores_prior_executable(tmp_path: Path) -> None:
    """Checksum and extraction both succeed, but the new binary refuses to
    start -- the prior working executable must come back, not a broken one."""
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    previous_binary = install_dir / "rush"
    previous_binary.write_bytes(b"#!/bin/sh\necho old\n")
    previous_binary.chmod(0o755)
    previous_bytes = previous_binary.read_bytes()

    _asset_name, assets = _release_fixture(_FAILING_BINARY_SCRIPT)

    result = InstallTool().run(
        agents="none",
        data_root=tmp_path / "data",
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "error"
    assert result["raw"]["code"] == "BINARY_VERIFY_FAILED"
    assert previous_binary.read_bytes() == previous_bytes


# --- Agent + memory setup happens, and never before the binary is verified --


def test_bootstrap_invokes_agent_and_memory_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    home = _home_with(tmp_path, "cursor", CURSOR_JSON)
    data_root = tmp_path / "data"
    install_dir = tmp_path / "bin"
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="all",
        memory="on",
        session_id="sess-1",
        home=home,
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
        permissions=_FULL_PERMISSIONS,
    )

    assert result["status"] == "ok", result
    agent_reports = {a["agent_id"]: a for a in result["raw"]["agents"]}
    # Cursor's adapter requires a client restart to pick up a config-edit --
    # a fresh registration reports restart_required, not a false "active".
    assert agent_reports["cursor"]["state"] == "restart_required"
    assert agent_reports["cursor"]["detected"] is True

    memory_state = read_agent_memory_state(
        "cursor", "sess-1", project_root=None, data_root=data_root
    )
    assert memory_state is not None
    assert memory_state["connected"] is True
    assert memory_state["consent"] is True

    config_path = ADAPTERS["cursor"].config_paths("Darwin", home)[0]
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["mcpServers"]["rush"]["command"] == str(install_dir / "rush")


def test_no_agent_writes_before_verified_binary_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    original_text = CURSOR_JSON
    home = _home_with(tmp_path, "cursor", original_text)
    data_root = tmp_path / "data"
    install_dir = tmp_path / "bin"
    _asset_name, assets = _release_fixture(_FAILING_BINARY_SCRIPT)

    result = InstallTool().run(
        agents="all",
        memory="on",
        session_id="sess-1",
        home=home,
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
        permissions=_FULL_PERMISSIONS,
    )

    assert result["status"] == "error"
    assert result["raw"]["code"] == "BINARY_VERIFY_FAILED"

    config_path = ADAPTERS["cursor"].config_paths("Darwin", home)[0]
    assert config_path.read_text(encoding="utf-8") == original_text
    assert (
        read_agent_memory_state(
            "cursor", "sess-1", project_root=None, data_root=data_root
        )
        is None
    )


def test_second_identical_install_preserves_already_active_agent_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    home = _home_with(tmp_path, "cursor", CURSOR_JSON)
    data_root = tmp_path / "data"
    install_dir = tmp_path / "bin"
    _asset_name, assets = _release_fixture()

    tool = InstallTool()
    first = tool.run(
        agents="all",
        memory="on",
        session_id="sess-1",
        home=home,
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
        permissions=_FULL_PERMISSIONS,
    )
    assert first["status"] == "ok"

    config_path = ADAPTERS["cursor"].config_paths("Darwin", home)[0]
    text_after_first = config_path.read_text(encoding="utf-8")

    second = tool.run(
        agents="all",
        memory="on",
        session_id="sess-1",
        home=home,
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
        permissions=_FULL_PERMISSIONS,
    )

    assert second["status"] == "ok"
    agent_reports = {a["agent_id"]: a for a in second["raw"]["agents"]}
    assert agent_reports["cursor"]["state"] == "active"
    # No duplicate "rush" entry, no re-written config: already-active agents
    # are left completely untouched by a second identical install.
    assert config_path.read_text(encoding="utf-8") == text_after_first
    assert text_after_first.count('"rush"') == 1


def test_second_install_reports_active_when_root_crosses_symlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T211: connect() writes the *resolved* rush binary path into the agent
    config (via resolve_rush_binary), but discover_agents/comparison used to
    receive install.py's *unresolved* binary_path. If the data/install root
    crosses a symlink (real-world case: macOS /var -> /private/var), the two
    values never match, status stays "misconfigured" forever, and an
    already-connected agent is reprocessed (never reports "active") on every
    repeat install."""
    monkeypatch.setattr(agents_mod.shutil, "which", lambda _name: None)
    real_root = tmp_path / "real-root"
    real_root.mkdir()
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(real_root, target_is_directory=True)

    home = _home_with(linked_root, "cursor", CURSOR_JSON)
    data_root = linked_root / "data"
    install_dir = linked_root / "bin"
    _asset_name, assets = _release_fixture()

    tool = InstallTool()
    first = tool.run(
        agents="all",
        memory="on",
        session_id="sess-1",
        home=home,
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
        permissions=_FULL_PERMISSIONS,
    )
    assert first["status"] == "ok", first

    second = tool.run(
        agents="all",
        memory="on",
        session_id="sess-1",
        home=home,
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
        permissions=_FULL_PERMISSIONS,
    )

    assert second["status"] == "ok", second
    agent_reports = {a["agent_id"]: a for a in second["raw"]["agents"]}
    assert agent_reports["cursor"]["state"] == "active"


# --- Project choice: select existing / add folder / create folder / later --


def test_choose_later_is_successful_global_install_with_no_active_project(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        data_root=data_root,
        install_dir=tmp_path / "bin",
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "ok"
    assert result["raw"]["project"] is None
    assert "no active project" in result["summary"]


def test_cwd_is_not_auto_registered_when_no_project_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "current-dir"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    data_root = tmp_path / "data"
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        data_root=data_root,
        install_dir=tmp_path / "bin",
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "ok"
    assert list_projects(data_root=data_root) == []


def test_select_existing_project(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    project_dir = tmp_path / "existing-project"
    project_dir.mkdir()
    record = register_project(project_dir, data_root=data_root)
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        project=record.project_id,
        session_id="sess-select",
        data_root=data_root,
        install_dir=tmp_path / "bin",
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "ok"
    assert result["raw"]["project"]["project_id"] == record.project_id
    assert len(list_projects(data_root=data_root)) == 1


def test_add_folder_registers_and_selects(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    project_dir = tmp_path / "unregistered-project"
    project_dir.mkdir()
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        project=str(project_dir),
        session_id="sess-add",
        data_root=data_root,
        install_dir=tmp_path / "bin",
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "ok"
    projects = list_projects(data_root=data_root)
    assert len(projects) == 1
    assert projects[0]["root"] == str(project_dir.resolve())


def test_create_folder_creates_and_selects(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    parent = tmp_path / "parent"
    parent.mkdir()
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        create_name="brand-new",
        create_parent=parent,
        session_id="sess-create",
        data_root=data_root,
        install_dir=tmp_path / "bin",
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "ok"
    created = parent / "brand-new"
    assert created.is_dir()
    assert result["raw"]["project"]["root"] == str(created.resolve())


def test_one_install_serves_two_isolated_projects(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    install_dir = tmp_path / "bin"
    project_a = tmp_path / "project-a"
    project_a.mkdir()
    project_b = tmp_path / "project-b"
    project_b.mkdir()
    _asset_name, assets = _release_fixture()

    tool = InstallTool()
    first = tool.run(
        agents="none",
        project=str(project_a),
        session_id="sess-a",
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
    )
    second = tool.run(
        agents="none",
        project=str(project_b),
        session_id="sess-b",
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
    )

    assert first["status"] == "ok" and second["status"] == "ok"
    projects = {p["root"]: p for p in list_projects(data_root=data_root)}
    assert str(project_a.resolve()) in projects
    assert str(project_b.resolve()) in projects
    assert (
        first["raw"]["project"]["project_id"] != second["raw"]["project"]["project_id"]
    )


def test_paths_with_spaces_work(tmp_path: Path) -> None:
    data_root = tmp_path / "data root with spaces"
    install_dir = tmp_path / "bin dir with spaces"
    project_dir = tmp_path / "my project with spaces"
    project_dir.mkdir()
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        create_name="child project",
        create_parent=tmp_path,
        session_id="sess-spaces",
        data_root=data_root,
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "ok", result
    binary_path = Path(result["raw"]["binary"]["path"])
    assert binary_path.is_file()
    assert " " in str(binary_path)


def test_non_interactive_install_never_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse_input(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("rush install must never prompt interactively")

    monkeypatch.setattr("builtins.input", _refuse_input)
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        data_root=tmp_path / "data",
        install_dir=tmp_path / "bin",
        downloader=_fake_downloader(assets),
    )

    assert result["status"] == "ok"


# --- The installed executable is genuinely standalone -----------------------


@pytest.mark.skipif(os.name != "posix", reason="fixture binary is a POSIX shell script")
def test_global_executable_runs_from_two_unrelated_directories(tmp_path: Path) -> None:
    import subprocess

    install_dir = tmp_path / "bin"
    _asset_name, assets = _release_fixture()

    result = InstallTool().run(
        agents="none",
        data_root=tmp_path / "data",
        install_dir=install_dir,
        downloader=_fake_downloader(assets),
    )
    assert result["status"] == "ok"
    binary_path = result["raw"]["binary"]["path"]

    dir_a = tmp_path / "unrelated-a"
    dir_b = tmp_path / "somewhere-else-entirely"
    dir_a.mkdir()
    dir_b.mkdir()

    for cwd in (dir_a, dir_b):
        proc = subprocess.run(
            [binary_path, "--version"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        assert proc.returncode == 0
        assert proc.stdout.strip() == "9.9.9"
