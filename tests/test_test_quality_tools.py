"""Task 8 test-quality safety contracts."""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

from rush.tools.contract import ContractTool
from rush.tools.coverage import CoverageTool
from rush.tools.e2e import E2eTool
from rush.tools.flaky import FlakyTool
from rush.tools.fuzz import FuzzTool
from rush.tools.load import LoadTool
from rush.tools.mutation import MutationTool
from rush.tools.pbt import PbtTool
from rush.tools.snapshot import SnapshotTool
from rush.tools.visual import VisualTool


@pytest.mark.parametrize(
    "tool, options",
    [
        (MutationTool(), {}),
        (E2eTool(), {}),
        (FuzzTool(), {}),
        (LoadTool(), {}),
    ],
)
def test_expensive_quality_tools_require_explicit_opt_in(
    tmp_path: Path, tool, options: dict[str, object]
) -> None:
    result = tool.run(tmp_path, **options)

    assert result["status"] == "skipped"
    assert result["tool"] == tool.name


@pytest.mark.parametrize("tool", [SnapshotTool(), VisualTool()])
def test_snapshot_tools_never_accept_baselines_by_default(tmp_path: Path, tool) -> None:
    result = tool.run(tmp_path)

    assert result["status"] == "skipped"
    assert "accept" in result["summary"]


@pytest.mark.parametrize(
    "tool", [CoverageTool(), PbtTool(), FlakyTool(), ContractTool()]
)
def test_analysis_quality_tools_are_non_destructive_by_default(
    tmp_path: Path, tool
) -> None:
    before = set(tmp_path.iterdir())

    result = tool.run(tmp_path)

    assert result["status"] == "skipped"
    assert set(tmp_path.iterdir()) == before


def test_quality_report_fixtures_cover_required_exchange_formats() -> None:
    reports = Path(__file__).parent / "fixtures" / "engine_reports"

    assert (
        json.loads((reports / "coverage.json").read_text())["total"]["lines"]["pct"]
        == 80
    )
    assert ElementTree.parse(reports / "junit.xml").getroot().tag == "testsuite"
    assert "SF:src/example.py" in (reports / "coverage.lcov").read_text()
    assert ElementTree.parse(reports / "cobertura.xml").getroot().tag == "coverage"
