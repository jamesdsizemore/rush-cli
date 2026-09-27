"""RED-phase test matrix for Phase 70 T24 -- setup applies reviewed changes safely.

Binding design: .scratch/phase-70-design-gate/W4-T23-T29.md
  - Section 0 (adversarial findings naming T24: corrupt-registry data loss,
    read-only readers writing files, P1 WAL journal writes, legacy installer
    removal, C901, single-writer order).
  - Section 1 (cross-cutting resolutions X5 strict readers, X8 writer order,
    X9 contract changes).
  - Section "## T24: setup applies reviewed changes safely".
Plan packet: docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md
  "#### T24 -- Setup applies reviewed changes safely".

Nothing here passes yet. `build_setup_review`, `apply_setup_review`,
`ConsentIO`, `read_registry_strict`, `ProjectRegistryCorruptError`, and the
CLI mode-selection/preview contract they describe do not exist in this
worktree. Every test is written against the target design and is expected
to fail today -- either with an ImportError naming the missing symbol, or
with an AssertionError against the current (pre-T24) behavior.

Never touches the real user's Rush data root: the `_isolated_home` fixture
(autouse) redirects `default_data_root()` (which reads `Path.home()` on
this macOS machine) into a per-test temp directory. No test makes a real
network call -- every provisioning path takes an injected `http_get`,
`downloader`, `runner`, `prober`, or `which` fake.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.setup.provision import default_data_root

# --------------------------------------------------------------------------
# Shared fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect default_data_root() away from the real user's Rush data."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    return home


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


@pytest.fixture
def data_root(_isolated_home: Path) -> Path:
    return default_data_root()


def _tracked_paths(project_root: Path, data_root: Path) -> list[Path]:
    """Every file T24 setup can touch. Used for byte-identical snapshots."""
    return [
        project_root / "rush.toml",
        project_root / ".rush" / "project.json",
        data_root / "projects.json",
        data_root / "toolchains.json",
        data_root / "toolchains",
    ]


def _snapshot(paths: list[Path]) -> dict[str, bytes | tuple[str, ...] | None]:
    """Byte-for-byte (or, for a directory, sorted relative listing) state."""
    state: dict[str, bytes | tuple[str, ...] | None] = {}
    for p in paths:
        if p.is_dir():
            state[str(p)] = tuple(sorted(str(c.relative_to(p)) for c in p.rglob("*")))
        elif p.is_file():
            state[str(p)] = p.read_bytes()
        else:
            state[str(p)] = None
    return state


def _no_network_http_get(_url: str) -> bytes:
    raise AssertionError("apply must never call http_get: preview already resolved")


def _no_network_downloader(_url: str) -> bytes:
    raise AssertionError("apply must never download without a resolved identity")


class _RecordingRunner:
    """Fake subprocess runner that records every invocation and never runs one."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], env: dict[str, str] | None = None) -> Any:
        self.calls.append(list(argv))

        class _Proc:
            returncode = 0
            stdout = ""
            stderr = ""

        return _Proc()


def _cursor_key_path(data_root: Path) -> Path:
    return data_root / "cursor.key"


# --------------------------------------------------------------------------
# Mode selection (§ Required behavior: Mode selection)
# --------------------------------------------------------------------------


def test_t24_bare_setup_flag_defaults_to_none_tristate() -> None:
    """The --non-interactive/--interactive pair auto-detects (default None),
    it does not default to True (always non-interactive) as today."""
    setup_cmd = cli.commands["setup"]
    non_interactive_param = next(
        p for p in setup_cmd.params if p.name == "non_interactive"
    )
    assert non_interactive_param.default is None, (
        "expected the tri-state auto-detect default (None); "
        f"got {non_interactive_param.default!r}"
    )


def test_t24_non_tty_previews_only_and_touches_nothing(
    project_root: Path, data_root: Path
) -> None:
    before = _snapshot(_tracked_paths(project_root, data_root))
    runner = CliRunner()
    result = runner.invoke(cli, ["setup", str(project_root), "--json"])
    assert result.exit_code == 0, result.output
    payload = __import__("json").loads(result.output)
    assert payload["status"] == "skipped"
    assert payload["reason"] == "preview_only"
    after = _snapshot(_tracked_paths(project_root, data_root))
    assert after == before


def test_t24_explicit_non_interactive_previews_only(
    project_root: Path, data_root: Path
) -> None:
    before = _snapshot(_tracked_paths(project_root, data_root))
    runner = CliRunner()
    result = runner.invoke(
        cli, ["setup", str(project_root), "--non-interactive", "--json"]
    )
    assert result.exit_code == 0, result.output
    payload = __import__("json").loads(result.output)
    assert payload["status"] == "skipped"
    assert payload["reason"] == "preview_only"
    after = _snapshot(_tracked_paths(project_root, data_root))
    assert after == before


def test_t24_interactive_flag_errors_without_a_tty(
    project_root: Path, data_root: Path
) -> None:
    before = _snapshot(_tracked_paths(project_root, data_root))
    runner = CliRunner()
    result = runner.invoke(cli, ["setup", str(project_root), "--interactive"])
    assert result.exit_code != 0
    assert "tty" in result.output.lower()
    after = _snapshot(_tracked_paths(project_root, data_root))
    assert after == before


# --------------------------------------------------------------------------
# Preview contents (§ Required behavior: Preview contents / Grants required)
# --------------------------------------------------------------------------


def test_t24_preview_config_create_includes_sha256(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    config_stage = review["config"]
    assert config_stage["action"] == "create"
    assert "sha256" in config_stage
    assert len(config_stage["sha256"]) == 64


def test_t24_preview_reuses_valid_existing_config_byte_for_byte(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import build_setup_review

    original = b'[project]\nsrc = ["src"]\n'
    (project_root / "rush.toml").write_bytes(original)
    review = build_setup_review(project_root, data_root, permissions=None)
    assert review["config"]["action"] == "reuse"
    import hashlib

    assert review["config"]["sha256"] == hashlib.sha256(original).hexdigest()


def test_t24_preview_registration_state_is_new_with_no_revision(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    assert review["registration"]["state"] == "new"
    assert review["registration"].get("revision") in (None, 0)


def test_t24_preview_configure_change_matches_empty_settings_plan(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import build_setup_review
    from rush.workflows.projects import compute_settings_plan_id

    review = build_setup_review(project_root, data_root, permissions=None)
    configure = review["configure"]
    assert configure["configured"] is True
    assert configure["settings"] == {}
    assert configure["plan_id"] == compute_settings_plan_id({})


def test_t24_preview_stage_grants_match_spec(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    grants = review["grants"]
    assert grants["config_create"] == ("artifact_write",)
    assert set(grants["register"]) == {"cache_write", "artifact_write"}
    assert grants["configure"] == ("cache_write",)
    assert grants["identity_resolution"] == ("network",)


# --------------------------------------------------------------------------
# Legacy installer removal (§ Required behavior, last bullet)
# --------------------------------------------------------------------------


def test_t24_legacy_install_engine_package_is_removed() -> None:
    import rush.tools.setup_wizard as setup_wizard_module

    assert not hasattr(setup_wizard_module, "install_engine_package"), (
        "install_engine_package (the legacy non_interactive=False per-stack "
        "installer) must be removed; all installs go through "
        "apply_provision_plan"
    )


def test_t24_run_setup_wizard_no_longer_installs_ad_hoc_packages_on_false(
    project_root: Path,
) -> None:
    """The old `non_interactive=False` loop that shelled out to a package
    manager for a bare engine name (bypassing the provision plan entirely)
    must be gone; `install=False` no longer performs any install, even for
    a project with real detected stacks and suggested engines."""
    (project_root / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    from rush.tools.setup_wizard import run_setup_wizard

    result = run_setup_wizard(project_root, non_interactive=False, install=False)
    assert result["stacks"], "fixture must actually detect a stack"
    assert result["installed"] == []


# --------------------------------------------------------------------------
# apply_provision_plan: reviewed-plan freezing (never re-resolve at apply)
# --------------------------------------------------------------------------


def test_t24_apply_requires_reviewed_plan_id(
    project_root: Path, data_root: Path
) -> None:
    """`reviewed_plan_id` is a required keyword once T24 lands; omitting it
    must raise TypeError. It does not today, because the parameter does not
    exist yet, so this call currently succeeds (the RED reason)."""
    from rush.permissions import ExecutionPermissions
    from rush.setup.provision import apply_provision_plan, build_provision_plan

    plan = build_provision_plan(project_root, ["ruff"])
    permissions = ExecutionPermissions(
        network=True, cache_write=True, artifact_write=True
    )
    with pytest.raises(TypeError):
        apply_provision_plan(
            plan,
            permissions,
            project_id="p1",
            data_root=data_root,
            http_get=_no_network_http_get,
            downloader=_no_network_downloader,
        )


def test_t24_apply_never_calls_http_get_when_identity_already_resolved(
    project_root: Path, data_root: Path
) -> None:
    """Identity resolution happens once, in `resolve_provision_identities`,
    before consent. Apply installs the frozen version and makes zero
    resolution network calls, even if upstream 'latest' has since changed."""
    from rush.permissions import ExecutionPermissions
    from rush.setup.provision import (
        apply_provision_plan,
        build_provision_plan,
        resolve_provision_identities,
    )

    plan = build_provision_plan(project_root, ["ruff"])
    permissions = ExecutionPermissions(
        network=True, cache_write=True, artifact_write=True
    )
    resolved_calls: list[str] = []

    def _resolve_http_get(url: str) -> bytes:
        resolved_calls.append(url)
        return b'{"info": {"version": "1.2.3"}}'

    resolved_plan = resolve_provision_identities(
        plan, permissions, http_get=_resolve_http_get
    )
    assert resolved_calls, "resolution must make at least one network call"

    apply_provision_plan(
        resolved_plan,
        permissions,
        project_id="p1",
        data_root=data_root,
        reviewed_plan_id=resolved_plan.plan_id,
        http_get=_no_network_http_get,
        downloader=_no_network_downloader,
        runner=_RecordingRunner(),
        which=lambda _name: None,
    )


def test_t24_tampered_reviewed_plan_id_is_rejected(
    project_root: Path, data_root: Path
) -> None:
    from rush.permissions import ExecutionPermissions
    from rush.setup.provision import apply_provision_plan, build_provision_plan

    plan = build_provision_plan(project_root, ["ruff"])
    permissions = ExecutionPermissions(
        network=True, cache_write=True, artifact_write=True
    )
    result = apply_provision_plan(
        plan,
        permissions,
        project_id="p1",
        data_root=data_root,
        reviewed_plan_id="0" * 64,
        http_get=_no_network_http_get,
        downloader=_no_network_downloader,
        runner=_RecordingRunner(),
        which=lambda _name: None,
    )
    assert result.failed.get("ruff", {}).get("code") == "PLAN_TAMPERED"


# --------------------------------------------------------------------------
# Destination ownership marker (replaces the unconditional rmtree)
# --------------------------------------------------------------------------


def test_t24_foreign_partial_directory_is_preserved_not_deleted(
    project_root: Path, data_root: Path
) -> None:
    from rush.permissions import ExecutionPermissions
    from rush.setup.provision import (
        _destination_for,
        apply_provision_plan,
        build_provision_plan,
        current_os_arch,
    )

    plan = build_provision_plan(project_root, ["ruff"])
    os_name, arch = current_os_arch()
    dest = _destination_for(data_root, "ruff", "1.2.3", os_name, arch)
    dest.mkdir(parents=True)
    (dest / "someone-elses-file.txt").write_text("do not delete me")

    permissions = ExecutionPermissions(
        network=True, cache_write=True, artifact_write=True
    )
    apply_provision_plan(
        plan,
        permissions,
        project_id="p1",
        data_root=data_root,
        reviewed_plan_id=plan.plan_id,
        http_get=lambda _u: b'{"info": {"version": "1.2.3"}}',
        downloader=_no_network_downloader,
        runner=_RecordingRunner(),
        which=lambda _name: None,
    )
    assert (dest / "someone-elses-file.txt").is_file(), (
        "a foreign partial directory with no ownership marker must survive "
        "a failed/blocked apply, per DESTINATION_OCCUPIED semantics"
    )


# --------------------------------------------------------------------------
# Strict registry reads (X5): corrupt registry is never silently wiped
# --------------------------------------------------------------------------


def test_t24_corrupt_registry_raises_and_writes_nothing(
    project_root: Path, data_root: Path
) -> None:
    from rush.workflows.projects import ProjectRegistryCorruptError, register_project

    data_root.mkdir(parents=True, exist_ok=True)
    registry_path = data_root / "projects.json"
    registry_path.write_bytes(b"{not json")
    before = registry_path.read_bytes()

    with pytest.raises(ProjectRegistryCorruptError):
        register_project(project_root, data_root=data_root)

    assert registry_path.read_bytes() == before


def test_t24_read_registry_strict_reports_corrupt_state(
    data_root: Path,
) -> None:
    from rush.workflows.projects import read_registry_strict

    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "projects.json").write_bytes(b"{not json")
    result = read_registry_strict(data_root)
    assert result["state"] == "corrupt"
    assert result["registry"] is None


def test_t24_read_registry_strict_reports_missing_state(data_root: Path) -> None:
    from rush.workflows.projects import read_registry_strict

    result = read_registry_strict(data_root)
    assert result["state"] == "missing"


# --------------------------------------------------------------------------
# Decline / EOF / Ctrl-C / non-TTY / JSON: zero diffs (§6, first bullet)
# --------------------------------------------------------------------------


class _ScriptedConsent:
    """Fake ConsentIO: answers one of "n", EOF, or "interrupt"."""

    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)

    def ask(self, prompt: str) -> str:
        if self.mode == "decline":
            return "n"
        if self.mode == "eof":
            return "eof"
        if self.mode == "interrupt":
            return "interrupt"
        if self.mode == "accept":
            return "y"
        raise AssertionError(f"unscripted consent mode: {self.mode}")


def _full_pypi_http_get(_url: str) -> bytes:
    """A complete PyPI JSON answer (info + releases with a sha256 digest)."""
    return (
        __import__("json")
        .dumps(
            {
                "info": {"version": "1.2.3"},
                "releases": {
                    "1.2.3": [
                        {
                            "packagetype": "bdist_wheel",
                            "url": "https://files.example/x.whl",
                            "digests": {"sha256": "a" * 64},
                        }
                    ]
                },
            }
        )
        .encode()
    )


class _BinaryWritingRunner:
    """Fake manager install: for engines named in `ok`, writes the executable
    where `uv tool install` would (UV_TOOL_BIN_DIR) and exits 0; others fail."""

    def __init__(self, ok: set[str]) -> None:
        self.ok = ok
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str], env: dict[str, str] | None = None) -> Any:
        self.calls.append(list(argv))
        joined = " ".join(argv)
        name = next((e for e in self.ok if f" {e}==" in f" {joined}"), None)
        if name is not None and env and "UV_TOOL_BIN_DIR" in env:
            exe = Path(env["UV_TOOL_BIN_DIR"]) / name
            exe.write_text("#!/bin/sh\necho 1.2.3\n")
            exe.chmod(0o755)
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        return type("P", (), {"returncode": 1, "stdout": "", "stderr": "boom"})()


def _python_project(project_root: Path) -> None:
    """Make the project recommend real engines (ruff, mypy, ...)."""
    (project_root / "pyproject.toml").write_text("[project]\nname = 'x'\n")


def _accepting_fakes() -> dict[str, Any]:
    """Deterministic, no-real-network/no-real-subprocess fakes for a full
    accepted apply: one known engine ("ruff") resolves and "installs"."""
    return {
        "http_get": lambda _u: b'{"info": {"version": "1.2.3"}}',
        "downloader": _no_network_downloader,
        "runner": _RecordingRunner(),
        "prober": lambda _argv: type(
            "P", (), {"returncode": 0, "stdout": "1.2.3", "stderr": ""}
        )(),
        "which": lambda _name: "/usr/bin/true",
    }


@pytest.mark.parametrize(
    "mode,expected_reason,expected_exit",
    [
        ("decline", "declined", 0),
        ("eof", "eof", 0),
        ("interrupt", "interrupt", 130),
    ],
)
def test_t24_setup_preview_apply_recovery(
    project_root: Path,
    data_root: Path,
    mode: str,
    expected_reason: str,
    expected_exit: int,
) -> None:
    """Named deliverable test id (parametrized over the recovery matrix in
    the design-gate brief's T24 section 6). Each parametrized case is its
    own row in the test report."""
    from rush.tools.setup_wizard import (
        ConsentIO,
        apply_setup_review,
        build_setup_review,
    )

    assert issubclass(ConsentIO, object)  # names the type; real contract is duck-typed

    before = _snapshot(_tracked_paths(project_root, data_root))
    review = build_setup_review(project_root, data_root, permissions=None)
    consent = _ScriptedConsent(mode)
    result = apply_setup_review(review, permissions=None, consent=consent)

    assert result["status"] == "skipped"
    assert result["reason"] == expected_reason
    after = _snapshot(_tracked_paths(project_root, data_root))
    assert after == before, f"{mode} must leave project and global state unchanged"


def test_t24_stale_config_between_preview_and_apply_gives_recovery_required(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    # Someone else writes rush.toml after the preview was built but before apply.
    (project_root / "rush.toml").write_bytes(b'[project]\nsrc = ["changed"]\n')
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept")
    )
    assert result["status"] == "recovery_required"
    assert "config" in result["conflict"]


def test_t24_stale_registry_revision_gives_recovery_required(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review
    from rush.workflows.projects import register_project

    review = build_setup_review(project_root, data_root, permissions=None)
    # Someone else registers the project (bumping the registry) before apply.
    register_project(project_root, data_root=data_root)
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept")
    )
    assert result["status"] == "recovery_required"
    assert "registration" in result["conflict"]


def test_t24_unavailable_manager_reported_in_preview_and_apply(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    (project_root / "package.json").write_text('{"name":"x"}')
    review = build_setup_review(
        project_root, data_root, permissions=None, which=lambda _n: None
    )
    engines_preview = review["provision"]["entries"]
    assert any(
        e.get("blocked_reason") == "SYSTEM_PREREQUISITE_REQUIRED"
        for e in engines_preview
    ), "an unavailable manager must be visible in the preview, not only at apply"

    fakes = _accepting_fakes()
    fakes["which"] = lambda _n: None
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept"), **fakes
    )
    assert any(
        f.get("code") == "SYSTEM_PREREQUISITE_REQUIRED"
        for f in result["provision"]["failed"].values()
    )


def test_t24_checksum_mismatch_preserves_prior_verified_manifest(
    project_root: Path, data_root: Path
) -> None:
    from rush.setup.provision import _destination_for, current_os_arch
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    os_name, arch = current_os_arch()
    dest = _destination_for(data_root, "ruff", "1.2.2", os_name, arch)
    dest.mkdir(parents=True)
    prior_manifest = dest / "manifest.json"
    prior_manifest.write_text('{"version": "1.2.2"}')
    prior_bytes = prior_manifest.read_bytes()

    review = build_setup_review(project_root, data_root, permissions=None)
    fakes = _accepting_fakes()
    fakes["downloader"] = lambda _u: b"corrupt-bytes-that-fail-digest-check"
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept"), **fakes
    )
    assert "ruff" not in result["provision"].get("applied", {})
    assert prior_manifest.read_bytes() == prior_bytes


def test_t24_partial_engine_success_reports_applied_and_failed_separately(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    _python_project(project_root)
    review = build_setup_review(
        project_root, data_root, permissions=None, which=lambda _n: "/usr/bin/true"
    )
    fakes = _accepting_fakes()
    fakes["http_get"] = _full_pypi_http_get
    fakes["runner"] = _BinaryWritingRunner({"ruff"})
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept"), **fakes
    )
    provision = result["provision"]
    assert set(provision["applied"]) & set(provision["failed"]) == set()
    assert provision["applied"] or provision["failed"]


def test_t24_malformed_existing_config_stops_with_diagnostic_no_write(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    malformed = b"[project\nsrc = not valid toml"
    (project_root / "rush.toml").write_bytes(malformed)
    review = build_setup_review(project_root, data_root, permissions=None)
    assert review["config"]["action"] == "invalid"
    result = apply_setup_review(
        review,
        permissions=None,
        consent=_ScriptedConsent("accept"),
        **_accepting_fakes(),
    )
    assert result["status"] == "recovery_required"
    assert "diagnostic" in result
    assert (project_root / "rush.toml").read_bytes() == malformed


def test_t24_failed_atomic_registry_write_compensates_created_config(
    project_root: Path, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.workflows.projects as projects_module
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)

    def _raise(*_a: Any, **_k: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(projects_module, "atomic_write_bytes", _raise)
    result = apply_setup_review(
        review,
        permissions=None,
        consent=_ScriptedConsent("accept"),
        **_accepting_fakes(),
    )
    assert result["status"] == "recovery_required"
    assert not (project_root / "rush.toml").exists(), (
        "a config file created by this failed transaction must be "
        "compensated away, not left orphaned"
    )


def test_t24_manifest_plan_id_equals_reviewed_provision_plan_id(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    _python_project(project_root)
    review = build_setup_review(
        project_root, data_root, permissions=None, which=lambda _n: "/usr/bin/true"
    )
    fakes = _accepting_fakes()
    fakes["http_get"] = _full_pypi_http_get
    fakes["runner"] = _BinaryWritingRunner({"ruff"})
    result = apply_setup_review(
        review,
        permissions=None,
        consent=_ScriptedConsent("accept"),
        **fakes,
    )
    # The consented review is the resolved one (second consent); its plan id
    # is the reviewed plan id the manifests must bind.
    reviewed_plan_id = result["provision"]["plan_id"]
    applied = result["provision"]["applied"]
    assert applied, "expected at least one applied engine manifest"
    for manifest in applied.values():
        assert manifest["plan_id"] == reviewed_plan_id


def test_t24_rerun_is_a_noop_on_already_completed_stages(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    apply_setup_review(
        review,
        permissions=None,
        consent=_ScriptedConsent("accept"),
        **_accepting_fakes(),
    )
    config_bytes_after_first = (project_root / "rush.toml").read_bytes()

    second_review = build_setup_review(project_root, data_root, permissions=None)
    assert second_review["config"]["action"] == "reuse"
    assert second_review["registration"]["state"] == "existing"

    second_runner = _RecordingRunner()
    fakes = _accepting_fakes()
    fakes["runner"] = second_runner
    apply_setup_review(
        second_review, permissions=None, consent=_ScriptedConsent("accept"), **fakes
    )
    assert not second_runner.calls, "a completed engine install must not rerun"
    assert (project_root / "rush.toml").read_bytes() == config_bytes_after_first


def test_t24_registry_readback_and_config_bytes_match_after_apply(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review
    from rush.workflows.projects import list_projects

    review = build_setup_review(project_root, data_root, permissions=None)
    apply_setup_review(
        review,
        permissions=None,
        consent=_ScriptedConsent("accept"),
        **_accepting_fakes(),
    )
    projects = list_projects(data_root=data_root)
    matching = [p for p in projects if p["root"] == str(project_root.resolve())]
    assert len(matching) == 1
    assert matching[0]["configured"] is True
    assert (project_root / "rush.toml").is_file()


# --------------------------------------------------------------------------
# Project setup lock (.rush/setup.lock) and concurrent edits in compensation
# --------------------------------------------------------------------------


def test_t24_concurrent_setup_holding_the_lock_blocks_apply(
    project_root: Path, data_root: Path
) -> None:
    import os

    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    lock = project_root / ".rush" / "setup.lock"
    lock.parent.mkdir()
    lock.write_text(str(os.getpid()))  # a live setup owns it
    before = _snapshot(_tracked_paths(project_root, data_root))

    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept")
    )
    assert result["status"] == "recovery_required"
    assert result["conflict"] == "setup_lock"
    assert _snapshot(_tracked_paths(project_root, data_root)) == before
    assert lock.read_text() == str(os.getpid())


def test_t24_stale_setup_lock_from_dead_process_is_reclaimed(
    project_root: Path, data_root: Path
) -> None:
    import subprocess
    import sys

    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = project_root / ".rush" / "setup.lock"
    lock.parent.mkdir()
    lock.write_text(str(dead.pid))

    review = build_setup_review(project_root, data_root, permissions=None)
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept")
    )
    assert result["status"] == "ok"
    assert not lock.exists()


def test_t24_successful_apply_releases_the_setup_lock(
    project_root: Path, data_root: Path
) -> None:
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept")
    )
    assert result["status"] == "ok"
    assert not (project_root / ".rush" / "setup.lock").exists()


def test_t24_concurrent_config_edit_survives_compensation(
    project_root: Path, data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import rush.workflows.projects as projects_module
    from rush.tools.setup_wizard import apply_setup_review, build_setup_review

    review = build_setup_review(project_root, data_root, permissions=None)
    edited = b'[project]\nsrc = ["someone-else"]\n'

    def _edit_then_fail(*_a: Any, **_k: Any) -> None:
        (project_root / "rush.toml").write_bytes(edited)
        raise OSError("disk full")

    monkeypatch.setattr(projects_module, "atomic_write_bytes", _edit_then_fail)
    result = apply_setup_review(
        review, permissions=None, consent=_ScriptedConsent("accept")
    )
    assert result["status"] == "recovery_required"
    assert result["compensation_conflicts"] == ["config"]
    assert (project_root / "rush.toml").read_bytes() == edited


# --------------------------------------------------------------------------
# Recorded deviations / cannot-express notes live in the report, not here.
# --------------------------------------------------------------------------
