"""Phase 19 Markdown-Unfluff reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import markdown_unfluff
from rush.engines.markdown_unfluff import MarkdownUnfluffEngine


def test_markdown_unfluff_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        markdown_unfluff,
        "resolve_binary",
        lambda _binary: "C:/bin/markdown-unfluff",
    )
    monkeypatch.setattr(markdown_unfluff, "run_subprocess", fake_run)

    raw = MarkdownUnfluffEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/markdown-unfluff",
            "--format",
            "json",
            str(tmp_path),
        ]
    ]


def test_markdown_unfluff_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = MarkdownUnfluffEngine()
    monkeypatch.setattr(MarkdownUnfluffEngine, "version", lambda _self: "0.5.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "file": "CHANGELOG.md",
                    "line": 10,
                    "pattern": "repetitive-bullet-summary",
                    "description": "Redundant repetitive summary bullet point",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "unfluff/repetitive-bullet-summary" in failing["findings"][0]["rule"]
