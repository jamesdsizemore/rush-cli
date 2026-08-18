"""v0.2 content and infrastructure tool contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.tools.actions import ActionsTool
from rush.tools.containerfile import ContainerfileTool
from rush.tools.iac import IacTool
from rush.tools.markdown import MarkdownTool
from rush.tools.sql import SqlTool
from rush.tools.templates import TemplatesTool
from rush.tools.yaml import YamlTool


@pytest.mark.parametrize(
    ("tool", "filename"),
    [
        (MarkdownTool(), "README.md"),
        (ActionsTool(), ".github/workflows/ci.yml"),
        (YamlTool(), "openapi.yaml"),
        (SqlTool(), "schema.sql"),
        (TemplatesTool(), "page.html"),
        (ContainerfileTool(), "Dockerfile"),
        (IacTool(), "main.tf"),
    ],
)
def test_content_tools_skip_when_their_discovered_engine_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tool, filename: str
) -> None:
    source = tmp_path / filename
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# fixture\n")
    monkeypatch.setattr("rush.tools.common.resolve_binary", lambda binary: None)

    result = tool.run(source)

    assert result["tool"] == tool.name
    assert result["status"] == "skipped"
    assert result["findings"] == []


def test_markdown_skips_when_no_markdown_sources_exist(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not markdown\n")

    result = MarkdownTool().run(tmp_path)

    assert result["tool"] == "markdown"
    assert result["status"] == "skipped"
