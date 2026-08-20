"""Phase 15 Broken-Link-Checker (blc) reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import blc
from rush.engines.blc import BlcEngine


def test_blc_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(blc, "resolve_binary", lambda _binary: "C:/bin/blc")
    monkeypatch.setattr(blc, "run_subprocess", fake_run)

    raw = BlcEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/blc",
            "http://localhost:3000",
            "-ro",
            "--json",
        ]
    ]


def test_blc_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = BlcEngine()
    monkeypatch.setattr(BlcEngine, "version", lambda _self: "0.7.8")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "url": "http://localhost:3000/docs/removed-section",
                    "broken": True,
                    "brokenReason": "BLC_KEYWORD_NOT_FOUND",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "blc/blc_keyword_not_found" in failing["findings"][0]["rule"]
