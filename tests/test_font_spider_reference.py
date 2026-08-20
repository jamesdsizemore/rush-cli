"""Phase 17 Font-Spider reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import font_spider
from rush.engines.font_spider import FontSpiderEngine


def test_font_spider_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        font_spider, "resolve_binary", lambda _binary: "C:/bin/font-spider"
    )
    monkeypatch.setattr(font_spider, "run_subprocess", fake_run)

    raw = FontSpiderEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/font-spider",
            "--info",
            str(tmp_path),
        ]
    ]


def test_font_spider_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = FontSpiderEngine()
    monkeypatch.setattr(FontSpiderEngine, "version", lambda _self: "1.3.5")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "format")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {"info": "Font name: Roboto, Original size: 2.4MB, Used glyphs: 45"}
            ],
        },
        tmp_path,
        "format",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "font-spider/font-metric" in failing["findings"][0]["rule"]
