"""Phase 19 RedPen reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import redpen
from rush.engines.redpen import RedpenEngine


def test_redpen_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(redpen, "resolve_binary", lambda _binary: "C:/bin/redpen")
    monkeypatch.setattr(redpen, "run_subprocess", fake_run)

    raw = RedpenEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/redpen",
            "-f",
            "json",
            str(tmp_path),
        ]
    ]


def test_redpen_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = RedpenEngine()
    monkeypatch.setattr(RedpenEngine, "version", lambda _self: "1.10.4")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "document": "docs/architecture.md",
                    "lineNumber": 24,
                    "validator": "SentenceLength",
                    "message": "The length of the sentence (120 words) exceeds the maximum 100 words.",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "redpen/SentenceLength" in failing["findings"][0]["rule"]
