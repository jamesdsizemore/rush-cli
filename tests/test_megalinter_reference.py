"""Phase 18 MegaLinter reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import megalinter
from rush.engines.megalinter import MegalinterEngine


def test_megalinter_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"linters": []}', stderr="")

    monkeypatch.setattr(
        megalinter, "resolve_binary", lambda _binary: "C:/bin/megalinter"
    )
    monkeypatch.setattr(megalinter, "run_subprocess", fake_run)

    raw = MegalinterEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/megalinter",
            "--report-format",
            "json",
        ]
    ]


def test_megalinter_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = MegalinterEngine()
    monkeypatch.setattr(MegalinterEngine, "version", lambda _self: "8.0.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "name": "SPELL_CSPELL",
                    "status": "error",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "megalinter/SPELL_CSPELL" in failing["findings"][0]["rule"]
