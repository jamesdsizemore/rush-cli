"""Unit tests for MemProfileTool (PR50.8)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.permissions import ExecutionPermissions
from rush.tools.mem_profile import MemProfileTool


def _assert_no_secret(value: object, secret: str) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_secret(item, secret)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_secret(item, secret)
    else:
        assert secret not in str(value)


def test_mem_profile_skipped_on_empty(tmp_path: Path) -> None:
    tool = MemProfileTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "mem-profile"
    assert res["status"] == "skipped"
    assert "No Python files found" in res["summary"]
    assert res["findings"] == []


def test_mem_profile_clean_with_context_manager(tmp_path: Path) -> None:
    src_file = tmp_path / "clean_code.py"
    src_file.write_text(
        """def read_data(path):\n    with open(path, 'r') as f:\n        return f.read()\n""",
        encoding="utf-8",
    )

    tool = MemProfileTool()
    res = tool.run(src_file)

    assert res["status"] == "ok"
    assert res["findings"] == []
    assert res["metrics"] is not None
    assert res["metrics"]["unclosed_resources_count"] == 0


def test_mem_profile_detects_unclosed_resource(tmp_path: Path) -> None:
    src_file = tmp_path / "leaky_code.py"
    src_file.write_text(
        """def read_data(path):\n    f = open(path, 'r')\n    data = f.read()\n    return data\n""",
        encoding="utf-8",
    )

    tool = MemProfileTool()
    res = tool.run(src_file)

    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "mem-profile/unclosed-resource"
    assert res["findings"][0]["line"] == 2


def test_mem_profile_dynamic_requires_allow_slow(tmp_path: Path) -> None:
    src_file = tmp_path / "script.py"
    src_file.write_text("x = [i for i in range(1000)]\n", encoding="utf-8")

    tool = MemProfileTool()
    # Explicit dynamic probe without permissions
    res = tool.run(src_file, dynamic=True, permissions=ExecutionPermissions())

    assert res["status"] == "skipped"
    assert "--allow-slow" in res["summary"]


def test_mem_profile_dynamic_with_allow_slow(tmp_path: Path) -> None:
    src_file = tmp_path / "script.py"
    src_file.write_text("x = [i for i in range(1000)]\n", encoding="utf-8")

    tool = MemProfileTool()
    res = tool.run(
        src_file,
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )

    assert res["status"] == "ok"
    assert res["metrics"] is not None
    assert "peak_memory_bytes" in res["metrics"]
    assert res["metrics"]["peak_memory_bytes"] > 0


def test_target_crash_is_error(tmp_path: Path) -> None:
    secret = "RUSH_MEM_SECRET_9f4c"
    src_file = tmp_path / "crash.py"
    src_file.write_text(
        f"raise RuntimeError({secret!r})\n",
        encoding="utf-8",
    )
    res = MemProfileTool().run(
        src_file,
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "error"
    assert res["metadata"]["terminal_reason"] == "target_failed"
    assert res["metrics"].get("completed") is not True
    assert res["metrics"].get("peak_memory_bytes") != 0
    assert res["metadata"]["target_exit_code"] == 1
    _assert_no_secret(res, secret)


def test_timeout_is_error_without_completed_measurement(tmp_path: Path) -> None:
    src_file = tmp_path / "slow.py"
    src_file.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    res = MemProfileTool().run(
        src_file,
        dynamic=True,
        timeout_seconds=1,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "error"
    assert res["metadata"]["terminal_reason"] == "timeout"
    assert res["metrics"].get("completed") is not True


def test_clean_dynamic_profile_measures_retained_allocation(tmp_path: Path) -> None:
    src_file = tmp_path / "allocation.py"
    src_file.write_text(
        "retained = bytearray(1_048_576)\nprint('target output', end='')\n",
        encoding="utf-8",
    )
    res = MemProfileTool().run(
        src_file,
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "ok"
    assert res["metrics"]["completed"] is True
    assert res["metrics"]["peak_memory_bytes"] >= 1_048_576


def test_zero_exit_without_measurement_is_incomplete(tmp_path: Path) -> None:
    src_file = tmp_path / "clean_exit.py"
    src_file.write_text("raise SystemExit(0)\n", encoding="utf-8")
    res = MemProfileTool().run(
        src_file, dynamic=True, permissions=ExecutionPermissions(slow=True)
    )
    assert res["status"] == "error"
    assert res["metadata"]["terminal_reason"] == "incomplete"
    assert res["metrics"]["peak_memory_bytes"] is None


def test_dynamic_profile_accepts_nested_quoted_path(
    tmp_path: Path, monkeypatch
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    src_file = nested / "file's.py"
    src_file.write_text("retained = bytearray(1024)\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    res = MemProfileTool().run(
        src_file.relative_to(tmp_path),
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "ok"
    assert res["metrics"]["completed"] is True


@pytest.mark.parametrize("tool", ["mem-profile", "cold-start"])
def test_cli_configured_runtime_crash_reports_child_exit(
    tmp_path: Path, monkeypatch, tool: str
) -> None:
    src_file = tmp_path / "crash.py"
    src_file.write_text("raise RuntimeError('cli crash')\n", encoding="utf-8")
    (tmp_path / "rush.toml").write_text(
        f"[tools.{tool}]\ndynamic = true\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        [tool, str(src_file), "--json", "--allow-slow"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "error"
    assert payload["metadata"]["target_exit_code"] == 1


@pytest.mark.parametrize(
    "report",
    ["null", "[]", '{"peak_bytes": true}', '{"peak_bytes": -1}', '{"peak_bytes": 0}'],
)
def test_invalid_memory_report_is_incomplete(tmp_path: Path, report: str) -> None:
    target = tmp_path / "invalid_report.py"
    target.write_text(f"print({report!r})\nraise SystemExit(0)\n", encoding="utf-8")
    result = MemProfileTool().run(
        target, dynamic=True, permissions=ExecutionPermissions(slow=True)
    )
    assert result["status"] == "error"
    assert result["metadata"]["terminal_reason"] == "incomplete"
    assert result["metrics"]["completed"] is False
    assert result["metrics"]["peak_memory_bytes"] is None
