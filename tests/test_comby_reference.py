"""Phase 18 Comby reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import comby
from rush.engines.comby import CombyEngine


def test_comby_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(comby, "resolve_binary", lambda _binary: "C:/bin/comby")
    monkeypatch.setattr(comby, "run_subprocess", fake_run)

    raw = CombyEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/comby",
            "-match-only",
            "-json-lines",
        ]
    ]


def test_comby_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = CombyEngine()
    monkeypatch.setattr(CombyEngine, "version", lambda _self: "1.8.1")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "uri": "src/utils.js",
                    "matched": "var foo = 1;",
                    "range": {"start": {"line": 5, "column": 0}},
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "comby/pattern-match" in failing["findings"][0]["rule"]
