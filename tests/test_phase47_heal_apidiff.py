"""Unit tests for Phase 47 TestHealer, ApiDiffer, and GitSandbox."""

import ast
import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

import rush.tools.test_heal as test_heal_mod
from rush.cli import cli
from rush.permissions import ExecutionPermissions
from rush.tools.api_diff import ApiDiffer
from rush.tools.test_heal import TestHealer


def test_test_healer_diagnose(tmp_path: Path):
    target = tmp_path / "test_dummy.py"
    target.write_text("def test_ok(): assert True\n", encoding="utf-8")
    _commit_fixture(tmp_path)

    healer = TestHealer(project_root=tmp_path)
    res = healer.diagnose_and_heal(
        str(target),
        runs=2,
        permissions=ExecutionPermissions(slow=True, artifact_write=True),
    )
    assert "error" not in res
    assert res["runs"] == 2
    assert res["is_flaky"] is False


def test_heal_default_records_twenty_seeded_observations(tmp_path: Path) -> None:
    target = tmp_path / "test_dummy.py"
    target.write_text("def test_ok(): assert True\n", encoding="utf-8")
    _commit_fixture(tmp_path)

    result = TestHealer(project_root=tmp_path).diagnose_and_heal(
        "test_dummy.py",
        permissions=ExecutionPermissions(slow=True, artifact_write=True),
    )

    assert result["status"] == "ok"
    assert result["diagnosis"] == "Deterministic"
    assert result["runs"] == 20
    assert result["seed"] == 0
    assert len(result["observations"]) == 20
    assert [item["random_seed"] for item in result["observations"]] == list(range(20))


def test_heal_random_repair_scopes_each_function_and_preserves_asserts() -> None:
    source = (
        "import random\n\n"
        "def test_one():\n    assert random.random() > 0.1\n\n"
        "def test_two():\n    assert random.random() < 0.9\n"
    )
    repaired = test_heal_mod._candidate_sources(source, 0)["random"]
    original_asserts = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Assert)
    ]
    repaired_asserts = [
        ast.dump(node, include_attributes=False)
        for node in ast.walk(ast.parse(repaired))
        if isinstance(node, ast.Assert)
    ]

    assert repaired.count("random = _RushRandom(0)") == 2
    assert original_asserts == repaired_asserts


def test_heal_async_future_is_awaited_directly() -> None:
    source = (
        "import asyncio\n\nasync def scenario():\n"
        "    future = asyncio.get_running_loop().create_future()\n"
        "    assert future.done()\n"
    )
    repaired = test_heal_mod._candidate_sources(source, 0)["async"]
    assert "await future\n" in repaired
    assert "future.wait" not in repaired
    assert "assert future.done()" in repaired


def test_heal_rejects_comment_only_candidate() -> None:
    source = "def test_value():\n    assert True\n"
    assert (
        test_heal_mod._is_substantive_repair(source, source + "# proposed repair\n")
        is False
    )


def _commit_fixture(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "rush@example.invalid"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Rush Test"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)


def _heal(root: Path, *, runs: int = 8) -> dict:
    return TestHealer(project_root=root).diagnose_and_heal(
        "test_flaky.py",
        runs=runs,
        seed=0,
        permissions=ExecutionPermissions(slow=True, artifact_write=True),
    )


def test_heal_proves_unseeded_random_state(tmp_path: Path) -> None:
    target = tmp_path / "test_flaky.py"
    target.write_text(
        "import random\n\ndef test_random_value():\n"
        "    value = random.random()\n"
        "    assert value > 0.35\n",
        encoding="utf-8",
    )
    _commit_fixture(tmp_path)

    result = _heal(tmp_path, runs=12)

    assert result["status"] == "ok", result
    assert result["diagnosis"] == "Unseeded Random State"
    assert result["verified"] is True
    assert result["applied"] is False
    assert "random = _RushRandom(0)" in result["patch"]
    assert "assert value > 0.35" in result["patch"]
    assert target.read_text(encoding="utf-8").count("assert value > 0.35") == 1

    applied = TestHealer(project_root=tmp_path).diagnose_and_heal(
        "test_flaky.py",
        runs=2,
        seed=0,
        dry_run=False,
        permissions=ExecutionPermissions(slow=True, artifact_write=True),
    )
    assert applied["status"] == "ok", applied
    assert applied["verified"] is True
    assert applied["applied"] is True
    assert "random = _RushRandom(0)" in target.read_text(encoding="utf-8")
    assert target.read_text(encoding="utf-8").count("assert value > 0.35") == 1
    assert not (tmp_path / "_rush_test_heal_perturb.py").exists()


def test_heal_proves_global_state_leak(tmp_path: Path) -> None:
    target = tmp_path / "test_flaky.py"
    target.write_text(
        "STATE = []\n\n"
        "class TestState:\n"
        "    def test_mutates_state(self):\n"
        "        STATE.append('owned')\n"
        "        assert STATE == ['owned']\n\n"
        "    def test_requires_clean_state(self):\n"
        "        assert STATE == []\n",
        encoding="utf-8",
    )
    _commit_fixture(tmp_path)

    result = _heal(tmp_path, runs=6)

    assert result["status"] == "ok"
    assert result["diagnosis"] == "Global State Leak"
    assert result["verified"] is True
    assert "yield" in result["patch"]
    assert "STATE.clear()" in result["patch"]
    assert "\n-    assert" not in result["patch"]


def test_heal_restores_only_observed_environment_key(tmp_path: Path) -> None:
    target = tmp_path / "test_flaky.py"
    target.write_text(
        "import os\n\n"
        "def test_mutates_owned_key():\n"
        "    os.environ['RUSH_OWNED_KEY'] = 'changed'\n"
        "    assert os.environ['RUSH_OWNED_KEY'] == 'changed'\n\n"
        "def test_requires_clean_key():\n"
        "    assert 'RUSH_OWNED_KEY' not in os.environ\n",
        encoding="utf-8",
    )
    _commit_fixture(tmp_path)

    result = _heal(tmp_path, runs=6)

    assert result["status"] == "ok"
    assert result["diagnosis"] == "Global State Leak"
    assert "RUSH_OWNED_KEY" in result["patch"]
    assert "os.environ.clear" not in result["patch"]


def test_heal_proves_synchronized_async_race(tmp_path: Path) -> None:
    target = tmp_path / "test_flaky.py"
    target.write_text(
        "import asyncio\nimport os\n\n"
        "async def scenario():\n"
        "    event = asyncio.Event()\n"
        "    async def complete():\n"
        "        await asyncio.sleep(0)\n"
        "        event.set()\n"
        "    asyncio.create_task(complete())\n"
        "    future = asyncio.get_running_loop().create_future()\n"
        "    asyncio.get_running_loop().call_soon(future.set_result, True)\n"
        "    if os.environ.get('RUSH_TEST_HEAL_SCHEDULE', 'ready') == 'ready':\n"
        "        await asyncio.sleep(0)\n"
        "        await asyncio.sleep(0)\n"
        "    assert event.is_set()\n\n"
        "    assert future.done()\n\n"
        "def test_completion():\n"
        "    asyncio.run(scenario())\n",
        encoding="utf-8",
    )
    _commit_fixture(tmp_path)

    result = _heal(tmp_path, runs=6)

    assert result["status"] == "ok", result
    assert result["diagnosis"] == "Async Race Condition"
    assert result["verified"] is True
    assert "await event.wait()" in result["patch"]
    assert "await future" in result["patch"]
    assert "future.wait" not in result["patch"]
    assert "assert event.is_set()" in result["patch"]
    assert "assert future.done()" in result["patch"]


def test_heal_rejects_invalid_and_inconclusive_inputs(tmp_path: Path) -> None:
    target = tmp_path / "test_flaky.py"
    target.write_text("def test_failure():\n    assert 1 == 2\n", encoding="utf-8")
    _commit_fixture(tmp_path)
    healer = TestHealer(project_root=tmp_path)

    zero = healer.diagnose_and_heal("test_flaky.py", runs=0)
    assert zero["status"] == "error"

    denied = healer.diagnose_and_heal("test_flaky.py")
    assert denied["status"] == "skipped"
    assert "slow" in denied["summary"]
    assert "artifact" in denied["summary"]

    inconclusive = healer.diagnose_and_heal(
        "test_flaky.py",
        runs=2,
        permissions=ExecutionPermissions(slow=True, artifact_write=True),
    )
    assert inconclusive["status"] == "skipped"
    assert inconclusive["diagnosis"] == "Inconclusive"
    assert inconclusive["patch"] == ""
    assert inconclusive["suggested_fix"] == ""


def test_heal_process_exception_returns_canonical_error(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "test_flaky.py"
    target.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    _commit_fixture(tmp_path)

    def fail(*_args, **_kwargs):
        raise OSError("password=private-heal-secret")

    monkeypatch.setattr(test_heal_mod, "run_subprocess", fail)
    result = TestHealer(project_root=tmp_path).diagnose_and_heal(
        "test_flaky.py",
        permissions=ExecutionPermissions(slow=True, artifact_write=True),
    )
    assert result["status"] == "error"
    assert "private-heal-secret" not in json.dumps(result)


def test_heal_cli_and_mcp_route_exact_options(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_call(self, target, **kwargs):
        calls.append((target, kwargs))
        return {
            "status": "skipped",
            "summary": "inconclusive",
            "diagnosis": "Inconclusive",
        }

    monkeypatch.setattr(TestHealer, "__call__", fake_call, raising=False)
    cli_result = CliRunner().invoke(
        cli,
        [
            "test-heal",
            "--target",
            str(tmp_path / "test_flaky.py"),
            "--runs",
            "7",
            "--seed",
            "11",
            "--apply",
            "--allow-slow",
            "--allow-artifact-write",
        ],
    )
    assert cli_result.exit_code == 0
    assert calls[-1][1] == {
        "runs": 7,
        "seed": 11,
        "dry_run": False,
        "allow_slow": True,
        "allow_artifact_write": True,
        "allow_build": False,
    }

    from rush.mcp import rush_test_heal

    payload = json.loads(rush_test_heal("test_flaky.py"))
    assert payload["status"] == "skipped"
    assert calls[-1][1]["runs"] == 20
    assert calls[-1][1]["seed"] == 0
    assert calls[-1][1]["dry_run"] is True


def test_api_differ_signatures(tmp_path: Path):
    code_old = """
def public_api(arg1: int, arg2: str) -> bool:
    return True

class Service:
    def execute(self, task: str) -> None:
        pass
"""
    differ = ApiDiffer(project_root=tmp_path)
    sigs = differ._extract_public_signatures(code_old)

    assert "public_api" in sigs
    assert sigs["public_api"] == ["arg1", "arg2"]
    assert "Service.execute" in sigs
    assert sigs["Service.execute"] == ["self", "task"]
