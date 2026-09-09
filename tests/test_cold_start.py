"""Unit tests for ColdStartTool (PR50.9)."""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.cold_start import ColdStartTool


def _assert_no_secret(value: object, secret: str) -> None:
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_secret(item, secret)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_secret(item, secret)
    else:
        assert secret not in str(value)


def test_cold_start_skipped_on_empty(tmp_path: Path) -> None:
    tool = ColdStartTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "cold-start"
    assert res["status"] == "skipped"
    assert "No Python files found" in res["summary"]
    assert res["findings"] == []


def test_cold_start_clean_light_imports(tmp_path: Path) -> None:
    src_file = tmp_path / "light.py"
    src_file.write_text(
        """import sys\nimport os\nfrom pathlib import Path\n\ndef run():\n    pass\n""",
        encoding="utf-8",
    )

    tool = ColdStartTool()
    res = tool.run(src_file)

    assert res["status"] == "ok"
    assert res["findings"] == []
    assert res["metrics"] is not None
    assert res["metrics"]["heavy_imports_count"] == 0
    assert res["metrics"]["total_imports"] == 3


def test_cold_start_detects_heavy_top_level_import(tmp_path: Path) -> None:
    src_file = tmp_path / "heavy.py"
    src_file.write_text(
        """import pandas as pd\nimport torch\nfrom pathlib import Path\n""",
        encoding="utf-8",
    )

    tool = ColdStartTool()
    res = tool.run(src_file)

    assert res["status"] == "warn"
    assert len(res["findings"]) == 2
    rules = [f["rule"] for f in res["findings"]]
    assert rules == [
        "cold-start/heavy-top-level-import",
        "cold-start/heavy-top-level-import",
    ]
    assert "pandas" in res["findings"][0]["message"]
    assert "torch" in res["findings"][1]["message"]


def test_cold_start_detects_wildcard_import(tmp_path: Path) -> None:
    src_file = tmp_path / "wildcard.py"
    src_file.write_text(
        """from os import *\n""",
        encoding="utf-8",
    )

    tool = ColdStartTool()
    res = tool.run(src_file)

    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "cold-start/wildcard-import"


def test_cold_start_dynamic_requires_allow_slow(tmp_path: Path) -> None:
    src_file = tmp_path / "entry.py"
    src_file.write_text("import json\n", encoding="utf-8")

    tool = ColdStartTool()
    res = tool.run(src_file, dynamic=True, permissions=ExecutionPermissions())

    assert res["status"] == "skipped"
    assert "--allow-slow" in res["summary"]


def test_cold_start_dynamic_with_allow_slow(tmp_path: Path) -> None:
    src_file = tmp_path / "entry.py"
    src_file.write_text("import json\n", encoding="utf-8")

    tool = ColdStartTool()
    res = tool.run(
        src_file,
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )

    assert res["status"] == "ok"
    assert res["metrics"] is not None
    assert "import_time_measured" in res["metrics"]


def test_target_crash_is_error(tmp_path: Path) -> None:
    secret = "RUSH_COLD_SECRET_9f4c"
    src_file = tmp_path / "crash.py"
    src_file.write_text(f"raise RuntimeError({secret!r})\n", encoding="utf-8")
    res = ColdStartTool().run(
        src_file,
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "error"
    assert res["metadata"]["terminal_reason"] == "target_failed"
    assert res["metrics"].get("completed") is not True
    assert res["metadata"]["target_exit_code"] == 1
    _assert_no_secret(res, secret)


def test_timeout_is_error_without_completed_measurement(tmp_path: Path) -> None:
    src_file = tmp_path / "slow.py"
    src_file.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    res = ColdStartTool().run(
        src_file,
        dynamic=True,
        timeout_seconds=1,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "error"
    assert res["metadata"]["terminal_reason"] == "timeout"
    assert res["metrics"].get("completed") is not True


def test_clean_dynamic_profile_completes(tmp_path: Path) -> None:
    src_file = tmp_path / "clean.py"
    src_file.write_text(
        "import json\nvalue = json.dumps({'ok': True})\n", encoding="utf-8"
    )
    res = ColdStartTool().run(
        src_file,
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "ok"
    assert res["metrics"]["completed"] is True
    assert res["metrics"]["import_time_measured"] is True
    assert res["metrics"]["measured_import_count"] > 0


def test_dynamic_cold_start_accepts_nested_quoted_path(
    tmp_path: Path, monkeypatch
) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    src_file = nested / "file's.py"
    src_file.write_text("import json\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    res = ColdStartTool().run(
        src_file.relative_to(tmp_path),
        dynamic=True,
        permissions=ExecutionPermissions(slow=True),
    )
    assert res["status"] == "ok"
    assert res["metrics"]["completed"] is True
    assert res["metrics"]["import_time_measured"] is True
