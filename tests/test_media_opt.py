"""Unit tests for MediaOptTool (PR50.10)."""

from __future__ import annotations

from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.media_opt import MediaOptTool


def test_media_opt_skipped_when_no_media(tmp_path: Path) -> None:
    tool = MediaOptTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "media-opt"
    assert res["status"] == "skipped"
    assert "No media or markup files found" in res["summary"]
    assert res["findings"] == []


def test_media_opt_clean_svg(tmp_path: Path) -> None:
    svg_file = tmp_path / "icon.svg"
    svg_file.write_text(
        '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(svg_file)

    assert res["status"] == "ok"
    assert res["findings"] == []


def test_media_opt_detects_svg_script_injection(tmp_path: Path) -> None:
    svg_file = tmp_path / "malicious.svg"
    svg_file.write_text(
        '<svg><script>alert(1)</script><circle cx="10" cy="10" r="5" onload="evil()"/></svg>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(svg_file)

    assert res["status"] == "fail"
    assert len(res["findings"]) >= 1
    rules = [f["rule"] for f in res["findings"]]
    assert "media-opt/svg-script-injection" in rules


def test_media_opt_svg_sanitize_with_permissions(tmp_path: Path) -> None:
    svg_file = tmp_path / "dirty.svg"
    svg_file.write_text(
        '<svg><script>alert("xss")</script><rect width="10" height="10" onclick="hack()"/></svg>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(
        svg_file,
        sanitize=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )

    assert res["status"] == "ok"
    cleaned = svg_file.read_text(encoding="utf-8")
    assert "<script" not in cleaned
    assert "onclick=" not in cleaned
    assert "<rect" in cleaned


def test_media_opt_cls_missing_dimensions(tmp_path: Path) -> None:
    html_file = tmp_path / "page.html"
    html_file.write_text(
        '<html><body><img src="photo.png" alt="photo"></body></html>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(html_file)

    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "media-opt/missing-image-dimensions"
