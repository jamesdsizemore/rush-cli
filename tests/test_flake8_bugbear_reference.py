"""Phase 18 Flake8-Bugbear reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import flake8_bugbear
from rush.engines.flake8_bugbear import Flake8BugbearEngine


def test_flake8_bugbear_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        flake8_bugbear, "resolve_binary", lambda _binary: "C:/bin/flake8"
    )
    monkeypatch.setattr(flake8_bugbear, "run_subprocess", fake_run)

    raw = Flake8BugbearEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/flake8",
            "--select=B,B9",
            "--format=%(path)s:%(row)d:%(col)d:%(code)s:%(text)s",
            str(tmp_path),
        ]
    ]


def test_flake8_bugbear_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = Flake8BugbearEngine()
    monkeypatch.setattr(Flake8BugbearEngine, "version", lambda _self: "24.4.26")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "path": "app.py",
                    "row": 15,
                    "col": 4,
                    "code": "B006",
                    "text": "Do not use mutable data structures for argument defaults",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "bugbear/B006" in failing["findings"][0]["rule"]
