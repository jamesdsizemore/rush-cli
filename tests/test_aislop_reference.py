"""Reference adapter tests for aislop."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import aislop_py
import pytest

from rush.engines import aislop
from rush.engines.aislop import AislopEngine
from rush.tools import common

# The npm package aislop's own Python launcher (aislop_py/cli.py) pins.
PINNED = f"aislop@{aislop_py.__version__}"


def _node_tooling(monkeypatch, **found: str) -> None:
    """`shutil.which` finds only the named Node.js tools, at the given paths."""
    monkeypatch.setattr("shutil.which", lambda name, *_a, **_k: found.get(name))


def _no_launcher(monkeypatch) -> None:
    """Fail the test if anything execs a process (aislop's launcher does)."""

    def execve(*args: object) -> None:
        raise AssertionError(f"os.execve called: {args}")

    monkeypatch.setattr(os, "execve", execve)


def test_aislop_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "C:/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    monkeypatch.delenv("AISLOP_NPM_PACKAGE", raising=False)
    _node_tooling(monkeypatch, npx="C:/node/npx")

    raw = AislopEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/node/npx",
            "--yes",
            "--package",
            PINNED,
            "aislop",
            "scan",
            "--format=json",
            str(tmp_path),
        ]
    ]


def test_aislop_runs_the_pinned_npm_package_without_the_launcher(
    monkeypatch, tmp_path: Path
) -> None:
    """aislop's launcher os.execve()s npx, which cannot run npx.cmd on
    Windows: the engine runs the launcher's pinned npm package itself."""
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "/venv/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    monkeypatch.delenv("AISLOP_NPM_PACKAGE", raising=False)
    _node_tooling(monkeypatch, npx="/usr/local/bin/npx")
    _no_launcher(monkeypatch)
    engine = AislopEngine()

    engine.run(tmp_path, ["--staged"], cwd=tmp_path)
    version = engine.version()

    assert calls == [
        [
            "/usr/local/bin/npx",
            "--yes",
            "--package",
            f"aislop@{aislop_py.__version__}",
            "aislop",
            "scan",
            "--format=json",
            "--staged",
            str(tmp_path),
        ]
    ]
    assert "/venv/bin/aislop" not in calls[0]
    # The version is the pin itself: no `aislop --version` launcher run.
    assert version == aislop_py.__version__
    assert len(calls) == 1


def test_aislop_uses_npx_cmd_on_windows(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    npx_cmd = "C:\\Program Files\\nodejs\\npx.cmd"
    monkeypatch.setattr(
        aislop, "resolve_binary", lambda _binary: "C:\\venv\\Scripts\\aislop.exe"
    )
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    monkeypatch.delenv("AISLOP_NPM_PACKAGE", raising=False)
    _node_tooling(monkeypatch, npx=npx_cmd, npm="C:\\Program Files\\nodejs\\npm.cmd")
    _no_launcher(monkeypatch)

    raw = AislopEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            npx_cmd,
            "--yes",
            "--package",
            PINNED,
            "aislop",
            "scan",
            "--format=json",
            str(tmp_path),
        ]
    ]


def test_aislop_falls_back_to_npm_exec_without_npx(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "/venv/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    monkeypatch.delenv("AISLOP_NPM_PACKAGE", raising=False)
    _node_tooling(monkeypatch, npm="/usr/bin/npm")

    AislopEngine().run(tmp_path, [], cwd=tmp_path)

    assert calls == [
        [
            "/usr/bin/npm",
            "exec",
            "--yes",
            "--package",
            PINNED,
            "--",
            "aislop",
            "scan",
            "--format=json",
            str(tmp_path),
        ]
    ]


def test_aislop_without_node_tooling_is_skipped_not_run(
    monkeypatch, tmp_path: Path
) -> None:
    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"ran {argv}")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "/venv/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    _node_tooling(monkeypatch)
    engine = AislopEngine()

    res = engine.normalize(engine.run(tmp_path, []), tmp_path, "slop")

    assert res["status"] == "skipped"
    assert "npx (Node.js) not on PATH" in res["summary"]


def test_aislop_honors_the_launchers_npm_package_override(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "/venv/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    monkeypatch.setenv("AISLOP_NPM_PACKAGE", "aislop@0.0.9")
    _node_tooling(monkeypatch, npx="/usr/bin/npx")

    AislopEngine().run(tmp_path, [], cwd=tmp_path)

    assert calls[0][:5] == [
        "/usr/bin/npx",
        "--yes",
        "--package",
        "aislop@0.0.9",
        "aislop",
    ]


@pytest.mark.parametrize(
    ("launcher", "site_packages"),
    [
        # A venv / `uv tool` env on POSIX (the uv bin entry is a symlink into it).
        ("env/bin/aislop", "env/lib/python3.12/site-packages"),
        # A venv on Windows.
        ("env/Scripts/aislop.exe", "env/Lib/site-packages"),
        # Rush's provisioned `uv tool install` on Windows: UV_TOOL_BIN_DIR=dest
        # holds a copied shim, UV_TOOL_DIR=dest/tools holds the env.
        ("dest/aislop.exe", "dest/tools/aislop/Lib/site-packages"),
    ],
)
def test_aislop_pins_the_version_of_the_resolved_install(
    monkeypatch, tmp_path: Path, launcher: str, site_packages: str
) -> None:
    """The pin comes from the aislop install the engine resolved (a
    provisioned one is not importable by Rush), not Rush's own interpreter."""
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    binary = tmp_path / launcher
    binary.parent.mkdir(parents=True)
    binary.write_text("")
    package = tmp_path / site_packages / "aislop_py"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        '"""Python launcher package for the aislop CLI."""\n\n__version__ = "9.9.9"\n'
    )
    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: str(binary))
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    monkeypatch.delenv("AISLOP_NPM_PACKAGE", raising=False)
    _node_tooling(monkeypatch, npx="/usr/bin/npx")
    engine = AislopEngine()

    engine.run(tmp_path, [], cwd=tmp_path)

    assert calls[0][:5] == [
        "/usr/bin/npx",
        "--yes",
        "--package",
        "aislop@9.9.9",
        "aislop",
    ]
    assert engine.version() == "9.9.9"


def test_aislop_normalizes_clean(tmp_path: Path) -> None:
    engine = AislopEngine()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/engine_reports/aislop/clean.json").read_text(
            encoding="utf-8"
        )
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture}, tmp_path, "slop"
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_aislop_normalizes_findings(tmp_path: Path) -> None:
    engine = AislopEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/aislop/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture}, tmp_path, "slop"
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["severity"] == "error"
    assert res["findings"][0]["rule"] == "aislop/hallucinated-import"


def test_aislop_normalizes_malformed(tmp_path: Path) -> None:
    engine = AislopEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "slop"
    )
    assert res["status"] == "error"


def test_aislop_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(AislopEngine(), tmp_path)
    assert res["status"] == "skipped"


# -- aislop 0.16.1: directory scan, `diagnostics` report ----------------------

FIXTURE_0161 = (
    Path(__file__).parent / "fixtures/engine_reports/aislop/diagnostics-0.16.1.json"
)
SLOPPY_SOURCE = (
    "import os\n\n\ndef foo(x):\n    # This function returns x\n"
    "    try:\n        return x\n    except:\n        pass\n    return None\n"
)


def _run_and_normalize(
    monkeypatch, target: Path, stdout: str, returncode: int, stderr: str = ""
):
    calls: list[tuple[list[str], object]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs.get("cwd")))
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    monkeypatch.delenv("AISLOP_NPM_PACKAGE", raising=False)
    _node_tooling(monkeypatch, npx="/usr/bin/npx")
    engine = AislopEngine()
    monkeypatch.setattr(engine, "version", lambda **_kw: "0.16.1")
    raw = engine.run(target, [])
    return engine.normalize(raw, target, "slop"), calls


def test_aislop_file_target_scans_parent_with_single_include(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "pkg" / "a.py"
    source.parent.mkdir()
    source.write_text(SLOPPY_SOURCE)

    _res, calls = _run_and_normalize(monkeypatch, source, '{"diagnostics": []}', 0)

    assert calls == [
        (
            [
                "/usr/bin/npx",
                "--yes",
                "--package",
                PINNED,
                "aislop",
                "scan",
                "--format=json",
                "--include",
                "a.py",
                str(source.parent),
            ],
            source.parent,
        )
    ]


def test_aislop_directory_target_runs_in_the_scanned_directory(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text(SLOPPY_SOURCE)

    _res, calls = _run_and_normalize(monkeypatch, tmp_path, '{"diagnostics": []}', 0)

    assert calls == [
        (
            [
                "/usr/bin/npx",
                "--yes",
                "--package",
                PINNED,
                "aislop",
                "scan",
                "--format=json",
                str(tmp_path),
            ],
            tmp_path,
        )
    ]


def test_slop_passes_no_file_positionals_to_the_aislop_binary(
    monkeypatch, tmp_path: Path
) -> None:
    """Fake `aislop` launcher and `npx` on PATH: the real dispatch runs the
    pinned npm package through npx (never the launcher) with exactly one
    positional (the directory) -- aislop 0.16.1 rejects any more."""
    from rush.tools.common import clear_binary_cache
    from rush.tools.slop import SlopTool

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    launcher = bin_dir / "aislop"
    launcher.write_text(f'#!/bin/sh\necho launcher >> "{log}"\nexit 139\n')
    launcher.chmod(0o755)
    fake = bin_dir / "npx"
    fake.write_text(
        "#!/bin/sh\n"
        f'for a in "$@"; do echo "$a" >> "{log}"; done\n'
        "echo '{\"diagnostics\": []}'\n"
    )
    fake.chmod(0o755)
    monkeypatch.delenv("AISLOP_NPM_PACKAGE", raising=False)
    project = tmp_path / "proj"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "a.py").write_text(SLOPPY_SOURCE)
    (project / "b.py").write_text("def ok() -> int:\n    return 1\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    # The runtime venv bin is searched before PATH; CI installs the real
    # aislop there, which would shadow the fake.
    monkeypatch.setattr(common, "_venv_scripts_dir", lambda: None)
    clear_binary_cache()
    try:
        result = SlopTool().run(project)
    finally:
        clear_binary_cache()

    assert result["engine"] == "aislop"
    assert result["status"] == "ok", result["summary"]
    assert log.read_text().splitlines() == [
        "--yes",
        "--package",
        PINNED,
        "aislop",
        "scan",
        "--format=json",
        str(project),
    ]
    metadata = result["metadata"]
    assert metadata is not None
    scope = metadata["engines"][0]["scope"]
    assert scope["reason"] == "engine_discovers_directory_contents"


def test_aislop_parses_recorded_0161_diagnostics(monkeypatch, tmp_path: Path) -> None:
    res, _calls = _run_and_normalize(
        monkeypatch, tmp_path, FIXTURE_0161.read_text(encoding="utf-8"), 1
    )

    source = str(tmp_path / "pkg" / "a.py")
    assert res["status"] == "fail"
    assert res["findings"] == [
        {
            "path": source,
            "line": 1,
            "column": 8,
            "rule": "aislop/lint/ruff/F401",
            "severity": "error",
            "message": "`os` imported but unused",
            "fix": None,
            "remediation": None,
        },
        {
            "path": source,
            "line": 6,
            "column": 0,
            "rule": "aislop/ai-slop/ai-slop/trivial-comment",
            "severity": "warn",
            "message": "Trivial comment that restates the code",
            "fix": None,
            "remediation": "Remove comments that don't add information beyond "
            "what the code already expresses",
        },
        {
            "path": source,
            "line": 9,
            "column": 0,
            "rule": "aislop/ai-slop/ai-slop/swallowed-exception",
            "severity": "error",
            "message": "Bare except with pass swallows errors silently",
            "fix": None,
            "remediation": "Handle errors explicitly: log with context, "
            "rethrow, or return an error value",
        },
    ]


def test_aislop_unbound_pip_audit_preserves_external_findings(
    monkeypatch, tmp_path: Path
) -> None:
    from rush.contracts.results import adapt_legacy_finding, validate_finding

    project = tmp_path / "project"
    project.mkdir()
    (project / "requirements.txt").write_text("requests==2.32.4\n")
    (project / "app.py").write_text("import os\n")
    ambient = tmp_path / "ambient"
    ambient.mkdir()
    (ambient / "requirements.txt").write_text("requests==2.19.1\n")
    vulnerability = {
        "engine": "security",
        "rule": "security/vulnerable-dependency",
        "filePath": "requirements.txt",
        "line": 0,
        "column": 0,
        "severity": "error",
        "message": "requests 2.19.1: PYSEC-2018-28; fixed in 2.20.0",
    }
    source = {
        "engine": "lint",
        "rule": "ruff/F401",
        "filePath": "app.py",
        "line": 1,
        "column": 8,
        "severity": "error",
        "message": "`os` imported but unused",
    }
    report = {"diagnostics": [vulnerability, source]}
    result, calls = _run_and_normalize(monkeypatch, project, json.dumps(report), 1)

    assert calls[0][1] == project
    assert result["status"] == "fail"
    assert result["engine_version"] == "0.16.1"
    assert result["raw"] == report
    external, local = result["findings"]
    assert external["path"] == ""
    assert external["extensions"] == {
        "scope": "external_environment",
        "reported_path": "requirements.txt",
        "attribution_basis": "aislop_0.16.1_unbound_pip_audit",
    }
    assert external["message"] == (
        "External Python environment audit; not an audit of target dependencies. "
        + vulnerability["message"]
    )
    assert external["severity"] == "error"
    assert external["rule"] == "aislop/security/security/vulnerable-dependency"
    assert local["path"] == str(project / "app.py")
    assert local["message"] == source["message"]
    assert "extensions" not in local
    canonical = validate_finding(adapt_legacy_finding(external))
    assert canonical.path == ""
    assert canonical.extensions == external["extensions"]
    assert canonical.severity == "error"
    assert report["diagnostics"][0] == vulnerability


def test_aislop_exit_one_with_warning_diagnostics_is_warn(
    monkeypatch, tmp_path: Path
) -> None:
    report = json.loads(FIXTURE_0161.read_text(encoding="utf-8"))
    report["diagnostics"] = [
        d for d in report["diagnostics"] if d["severity"] == "warning"
    ]

    res, _calls = _run_and_normalize(monkeypatch, tmp_path, json.dumps(report), 1)

    assert res["status"] == "warn"
    assert [f["severity"] for f in res["findings"]] == ["warn"]


@pytest.mark.parametrize("returncode", [0, 1])
def test_aislop_zero_diagnostics_is_ok(
    monkeypatch, tmp_path: Path, returncode: int
) -> None:
    report = json.loads(FIXTURE_0161.read_text(encoding="utf-8"))
    report["diagnostics"] = []

    res, _calls = _run_and_normalize(
        monkeypatch, tmp_path, json.dumps(report), returncode
    )

    assert res["status"] == "ok"
    assert res["findings"] == []


def test_aislop_unparseable_output_is_error_with_stderr(
    monkeypatch, tmp_path: Path
) -> None:
    stderr = "error: too many arguments for 'scan'. Expected 1 argument but got 2."

    res, _calls = _run_and_normalize(monkeypatch, tmp_path, "", 1, stderr)

    assert res["status"] == "error"
    assert "exit 1" in res["summary"]
    assert stderr in res["summary"]


@pytest.mark.needs_aislop
def test_slop_real_aislop_scans_python_project(tmp_path: Path) -> None:
    """Real-engine acceptance against the installed aislop binary. The
    download grant lets npx fetch the aislop package on a cold npm cache (CI)."""
    from rush.permissions import ExecutionPermissions
    from rush.tools.common import clear_binary_cache
    from rush.tools.slop import SlopTool

    grant = ExecutionPermissions(download=True)

    clear_binary_cache()
    (tmp_path / "pkg").mkdir()
    sloppy = tmp_path / "pkg" / "a.py"
    sloppy.write_text(SLOPPY_SOURCE)
    clean = tmp_path / "b.py"
    clean.write_text("def ok() -> int:\n    return 1\n")

    project = SlopTool().run(tmp_path, permissions=grant)
    single_sloppy = SlopTool().run(sloppy, permissions=grant)
    single_clean = SlopTool().run(clean, permissions=grant)

    assert project["engine"] == "aislop"
    assert project["status"] == "fail", project["summary"]
    rules = {f["rule"] for f in project["findings"]}
    assert "aislop/ai-slop/ai-slop/swallowed-exception" in rules
    assert {f["path"] for f in project["findings"]} == {str(sloppy)}
    assert single_sloppy["status"] == "fail", single_sloppy["summary"]
    assert {f["path"] for f in single_sloppy["findings"]} == {str(sloppy)}
    assert single_clean["status"] == "ok", single_clean["summary"]


def _fake_npx_aislop(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """A fake `aislop` launcher plus a fake `npx` on PATH that, like real npx
    on an empty npm cache, fails with ENOTCACHED when npm is offline. npx
    logs the `npm_config_offline` value of every invocation."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "offline.log"
    launcher = bin_dir / "aislop"
    launcher.write_text("#!/bin/sh\nexit 139\n")
    launcher.chmod(0o755)
    fake = bin_dir / "npx"
    fake.write_text(
        "#!/bin/sh\n"
        f'echo "offline=$npm_config_offline" >> "{log}"\n'
        'if [ "$npm_config_offline" = "true" ]; then\n'
        "  echo 'npm error code ENOTCACHED' >&2; exit 1\n"
        "fi\n"
        "echo '{\"diagnostics\": []}'\n"
    )
    fake.chmod(0o755)
    project = tmp_path / "proj"
    project.mkdir()
    (project / "b.py").write_text("def ok() -> int:\n    return 1\n")
    monkeypatch.delenv("npm_config_offline", raising=False)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(common, "_venv_scripts_dir", lambda: None)
    return project, log


def test_slop_without_download_grant_runs_aislop_offline_and_is_permission_denied(
    monkeypatch, tmp_path: Path
) -> None:
    """No download grant: npm runs offline, so an uncached aislop package is
    a not-run step naming --allow-download -- never an error or a fetch."""
    from rush.tools.common import clear_binary_cache
    from rush.tools.slop import SlopTool

    project, log = _fake_npx_aislop(tmp_path, monkeypatch)
    clear_binary_cache()
    try:
        result = SlopTool()(project)
    finally:
        clear_binary_cache()

    assert result["status"] == "skipped", result["summary"]
    assert "--allow-download" in result["summary"]
    execution = result["metadata"]["execution"]
    assert execution["disposition"] == "not_run"
    assert execution["cause"] == "permission_denied"
    assert execution["requested_permissions"]["download"] is True
    lines = log.read_text().splitlines()
    assert lines and set(lines) == {"offline=true"}


def test_slop_with_download_grant_lets_aislop_fetch(
    monkeypatch, tmp_path: Path
) -> None:
    from rush.tools.common import clear_binary_cache
    from rush.tools.slop import SlopTool

    project, log = _fake_npx_aislop(tmp_path, monkeypatch)
    clear_binary_cache()
    try:
        result = SlopTool()(project, allow_download=True)
    finally:
        clear_binary_cache()

    assert result["status"] == "ok", result["summary"]
    lines = log.read_text().splitlines()
    assert lines and set(lines) == {"offline="}


def test_aislop_offline_env_set_only_without_download_grant(
    monkeypatch, tmp_path: Path
) -> None:
    from rush.engines.aislop import aislop_grants
    from rush.permissions import ExecutionPermissions

    seen: list[object] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen.append(kwargs.get("env"))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    _node_tooling(monkeypatch, npx="/usr/bin/npx")
    # The channel is detected from the host env (GitHub runners set PIPX_HOME).
    monkeypatch.delenv("PIPX_HOME", raising=False)
    monkeypatch.delenv("AISLOP_INSTALL_CHANNEL", raising=False)

    AislopEngine().run(tmp_path, [], cwd=tmp_path)
    with aislop_grants(ExecutionPermissions(download=True)):
        AislopEngine().run(tmp_path, [], cwd=tmp_path)

    offline_env, granted_env = seen
    assert isinstance(offline_env, dict)
    assert offline_env["npm_config_offline"] == "true"
    assert isinstance(granted_env, dict)
    assert "npm_config_offline" not in granted_env
    for env in (offline_env, granted_env):
        assert env["AISLOP_NO_TELEMETRY"] == "1"
        assert env["DO_NOT_TRACK"] == "1"
        # aislop's launcher sets its install channel for the npm package.
        assert env["AISLOP_INSTALL_CHANNEL"] == "pip"


@pytest.mark.needs_aislop
def test_ungranted_slop_after_provisioning_runs_offline(
    monkeypatch, tmp_path: Path
) -> None:
    """After the setup engine stage's npm prefetch, a slop run with no
    download grant runs npm offline and still reports aislop's findings."""
    import tempfile

    from rush.setup.provision import prefetch_npm_runtime
    from rush.tools.common import clear_binary_cache, resolve_binary
    from rush.tools.slop import SlopTool

    (tmp_path / "a.py").write_text(SLOPPY_SOURCE)
    with tempfile.TemporaryDirectory() as cache:
        monkeypatch.setenv("npm_config_cache", cache)
        monkeypatch.delenv("npm_config_offline", raising=False)
        clear_binary_cache()
        executable = resolve_binary("aislop")
        assert executable is not None
        assert prefetch_npm_runtime("aislop", Path(executable)) == "fetched"
        result = SlopTool()(tmp_path)
        clear_binary_cache()

    assert result["engine"] == "aislop"
    assert result["status"] == "fail", result["summary"]
    assert (result["metadata"]["execution"].get("cause")) != "permission_denied"


@pytest.mark.needs_aislop
def test_ungranted_slop_without_provisioning_is_permission_denied(
    monkeypatch, tmp_path: Path
) -> None:
    """Real aislop on an empty npm cache with no download grant: not run,
    permission_denied, and nothing fetched."""
    import tempfile

    from rush.tools.common import clear_binary_cache
    from rush.tools.slop import SlopTool

    (tmp_path / "a.py").write_text(SLOPPY_SOURCE)
    with tempfile.TemporaryDirectory() as cache:
        monkeypatch.setenv("npm_config_cache", cache)
        monkeypatch.delenv("npm_config_offline", raising=False)
        clear_binary_cache()
        result = SlopTool()(tmp_path)
        clear_binary_cache()
        fetched = list((Path(cache) / "_npx").glob("*/node_modules/aislop"))

    assert result["status"] == "skipped", result["summary"]
    execution = result["metadata"]["execution"]
    assert (execution["disposition"], execution["cause"]) == (
        "not_run",
        "permission_denied",
    )
    assert fetched == []
