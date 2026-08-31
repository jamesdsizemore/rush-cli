"""Unit tests for ColdStartTool (PR50.9)."""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.cold_start import ColdStartTool


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
