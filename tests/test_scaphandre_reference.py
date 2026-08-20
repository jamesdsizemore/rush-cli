"""Phase 14 Scaphandre reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import scaphandre
from rush.engines.scaphandre import ScaphandreEngine


def test_scaphandre_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        scaphandre, "resolve_binary", lambda _binary: "C:/bin/scaphandre"
    )
    monkeypatch.setattr(scaphandre, "run_subprocess", fake_run)

    raw = ScaphandreEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/scaphandre",
            "json",
            "-t",
            "5",
            "-s",
            "1",
            "-f",
            "scaphandre-power.json",
        ]
    ]


def test_scaphandre_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ScaphandreEngine()
    monkeypatch.setattr(ScaphandreEngine, "version", lambda _self: "0.5.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "complexity")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [{"consumption_microwatts": 150_000_000}],
        },
        tmp_path,
        "complexity",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "energy/high-power-draw"
