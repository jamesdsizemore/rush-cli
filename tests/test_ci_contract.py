"""Executable CI prerequisites for source and installed-artifact checks."""

import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from ruamel.yaml import YAML

ROOT = Path(__file__).resolve().parents[1]
SHARDS = 8
SELECTED_MARKERS = (
    "not needs_vulture and not needs_knip and not needs_radon and not needs_jscpd "
    "and not needs_sloppylint and not needs_prettier and not needs_promptfoo "
    "and not needs_tsc"
)


def test_ci_builds_before_artifact_tests() -> None:
    workflow = YAML(typ="safe").load((ROOT / ".github/workflows/ci.yml").read_text())
    for job in ("quality", "tests"):
        steps = workflow["jobs"][job]["steps"]
        commands = [step.get("run", "") for step in steps]
        build = next(i for i, command in enumerate(commands) if command == "uv build")
        native = next(
            i
            for i, command in enumerate(commands)
            if "build_release_archive" in command
        )
        tests = next(
            i for i, command in enumerate(commands) if "pytest tests/" in command
        )
        assert build < native < tests, job


def test_ci_runs_the_whole_suite_once_across_eight_shards() -> None:
    """The full suite is one pytest command, in the `tests` job only, run by a
    matrix of eight shards that together cover every shard index once; the
    shard env, selection expressions, failure summary and the test-id output
    that names a hung test are all on that command."""
    workflow = YAML(typ="safe").load((ROOT / ".github/workflows/ci.yml").read_text())
    whole_suite = [
        (job, step)
        for job, body in workflow["jobs"].items()
        for step in body["steps"]
        if re.search(r"pytest tests/ ", str(step.get("run", "")))
    ]
    assert [job for job, _ in whole_suite] == ["tests"]
    job = workflow["jobs"]["tests"]
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["matrix"]["shard"] == list(range(SHARDS))
    assert job["timeout-minutes"] <= 150
    step = whole_suite[0][1]
    assert step["shell"] == "bash"
    env = step["env"]
    assert env["RUSH_CI_SHARD"] == f"${{{{ matrix.shard }}}}/{SHARDS}"
    assert env["TERM"] == "xterm-256color"
    assert env["RUSH_G8_NATIVE_ARCHIVE"].endswith("/dist/rush-linux-x86_64.tar.gz")
    run = step["run"]
    assert "env -u PYTHONPATH -u NO_COLOR python -m pytest tests/ " in run
    assert '-k "not real_workload"' in run
    assert f'-m "{SELECTED_MARKERS}"' in run
    words = run.split()
    for option in ("-v", "-rfE", "--durations=25"):
        assert option in words, option
    assert any(word.startswith("faulthandler_timeout=") for word in words)
    # The native-TUI test only exists when RUSH_G8_NATIVE_ARCHIVE is set, so
    # only the shard that owns it can assert its receipt.
    assert "def test_installed_native_tui_real_terminal" in (
        ROOT / "tests/test_tui_terminal.py"
    ).read_text(encoding="utf-8")
    assert "test_installed_native_tui_real_terminal" in run
    assert "posix-installed-tui.json" in run
    # Unsharded collection of that one test fails the step when it is missing,
    # with the same selection expressions as the sharded run.
    guard = re.search(r'collected="\$\((.*?)\)"\n', run)
    assert guard, "missing the unsharded collect guard"
    collect = guard.group(1)
    assert "-u RUSH_CI_SHARD" in collect
    assert "tests/test_tui_terminal.py --collect-only -q" in collect
    assert (
        '-k "test_installed_native_tui_real_terminal and not real_workload"' in collect
    )
    assert f'-m "{SELECTED_MARKERS}"' in collect
    assert '[ "$collected" != "$expected" ]' in run
    assert run.index("exit 1") < run.index("posix-installed-tui.json")


_SHARD_CONFTEST = f"""
import importlib.util

_spec = importlib.util.spec_from_file_location("repo_conftest", {str(ROOT / "tests/conftest.py")!r})
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
pytest_collection_modifyitems = _module.pytest_collection_modifyitems
"""
_TINY_TESTS = {
    "test_one.py": "".join(f"def test_{n}():\n    pass\n" for n in range(5)),
    "test_two.py": (
        "import pytest\n@pytest.mark.parametrize('n', range(4))\ndef test_p(n):\n    pass\n"
        "def test_last():\n    pass\n"
    ),
}


def _collect(directory: Path, shard: str | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "RUSH_CI_SHARD"}
    env["PYTHONPATH"] = str(ROOT / "src")
    if shard is not None:
        env["RUSH_CI_SHARD"] = shard
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
        + ["--rootdir", str(directory), str(directory)],
        capture_output=True,
        text=True,
        env=env,
        cwd=directory,
        timeout=60,
        check=False,
    )


def test_ci_shard_hook_partitions_the_collection(tmp_path: Path) -> None:
    for name, source in _TINY_TESTS.items():
        (tmp_path / name).write_text(source)
    (tmp_path / "conftest.py").write_text(_SHARD_CONFTEST)

    def ids(result: subprocess.CompletedProcess[str]) -> list[str]:
        return [line for line in result.stdout.splitlines() if "::" in line]

    full = _collect(tmp_path, None)
    total = ids(full)
    assert len(total) == 10 and full.returncode == 0, full.stdout + full.stderr
    shards = []
    for index in range(3):
        result = _collect(tmp_path, f"{index}/3")
        selected = ids(result)
        assert selected, result.stdout + result.stderr
        # Counts stay honest: every test is either selected or deselected.
        match = re.search(
            r"(\d+)/(\d+) tests collected \((\d+) deselected\)", result.stdout
        )
        assert match is not None, result.stdout
        assert (int(match[1]), int(match[2]), int(match[3])) == (
            len(selected),
            len(total),
            len(total) - len(selected),
        )
        shards.append(selected)
    union = [i for shard in shards for i in shard]
    assert sorted(union) == sorted(total)
    assert len(set(union)) == len(total)
    assert shards[0] == total[0::3] and shards[2] == total[2::3]


@pytest.mark.parametrize("value", ["3/3", "-1/3", "x", "1/0", "1/2/3", ""])
def test_ci_shard_hook_rejects_a_malformed_value(tmp_path: Path, value: str) -> None:
    (tmp_path / "test_one.py").write_text(_TINY_TESTS["test_one.py"])
    (tmp_path / "conftest.py").write_text(_SHARD_CONFTEST)
    result = _collect(tmp_path, value)
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.stdout
    assert "RUSH_CI_SHARD" in result.stderr + result.stdout


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
