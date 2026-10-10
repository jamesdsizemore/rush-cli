"""Executable CI prerequisites for source and installed-artifact checks."""

import tomllib
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]


def test_ci_builds_before_artifact_tests() -> None:
    workflow = YAML(typ="safe").load((ROOT / ".github/workflows/ci.yml").read_text())
    steps = workflow["jobs"]["quality"]["steps"]
    commands = [step.get("run", "") for step in steps]
    build = next(i for i, command in enumerate(commands) if command == "uv build")
    tests = next(i for i, command in enumerate(commands) if "pytest tests/" in command)
    assert build < tests


def test_ci_typechecker_is_declared_and_locked() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    requirements = project["project"]["optional-dependencies"]["dev"]
    pins = [
        requirement.split("==")[1]
        for requirement in requirements
        if requirement.startswith("mypy==")
    ]
    assert len(pins) == 1
    assert any(
        package["name"] == "mypy" and package["version"] == pins[0]
        for package in lock["package"]
    )


def test_ci_checks_real_documentation_script_after_import_prerequisites() -> None:
    workflow = YAML(typ="safe").load((ROOT / ".github/workflows/ci.yml").read_text())
    commands = [step.get("run", "") for step in workflow["jobs"]["quality"]["steps"]]
    install = next(
        i for i, command in enumerate(commands) if command.startswith("uv sync")
    )
    check = commands.index("uv run python scripts/sync_docs.py --check")
    assert install < check
    assert (ROOT / "scripts/sync_docs.py").is_file()


def test_ci_windows_contracts_build_before_installed_tests() -> None:
    workflow = YAML(typ="safe").load((ROOT / ".github/workflows/ci.yml").read_text())
    job = workflow["jobs"]["windows-contracts"]
    assert job["runs-on"] == "windows-latest"
    commands = [step.get("run", "") for step in job["steps"]]
    test_index = next(
        i
        for i, command in enumerate(commands)
        if "tests/test_phase52_installed_artifacts.py" in command
    )
    assert commands.index("uv build") < test_index
    native_build = next(
        i for i, command in enumerate(commands) if "build_release_archive" in command
    )
    assert native_build < test_index
    lines = [line.strip() for line in commands[test_index].splitlines() if line.strip()]
    assert lines[0].split() == [
        "uv",
        "run",
        "pytest",
        "tests/test_providers.py",
        "tests/test_staged_scan_bytes.py",
        "tests/test_phase52_installed_artifacts.py",
        "tests/test_windows_import_safety.py",
        "tests/test_dashboard_http_contract.py::test_windows_owner_mutex_wait_results_fail_closed",
        "-q",
    ]
    assert lines[1] == "if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }"
    assert job["steps"][test_index]["env"] == {
        "RUSH_G8_NATIVE_ARCHIVE": "${{ github.workspace }}/dist/rush-windows-x86_64.zip",
        "RUSH_G8_NATIVE_SUMS": "${{ github.workspace }}/dist/SHA256SUMS",
        "RUSH_G8_NATIVE_RECEIPT_DIR": "${{ runner.temp }}/rush-native-terminal",
    }
