"""Unit tests for MemProfileTool (PR50.8)."""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.mem_profile import MemProfileTool


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
