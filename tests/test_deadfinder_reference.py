"""Phase 15 Deadfinder reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import deadfinder
from rush.engines.deadfinder import DeadfinderEngine


def test_deadfinder_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        deadfinder, "resolve_binary", lambda _binary: "C:/bin/deadfinder"
    )
    monkeypatch.setattr(deadfinder, "run_subprocess", fake_run)

    raw = DeadfinderEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/deadfinder",
            "http://localhost:3000",
            "--json",
        ]
    ]


def test_deadfinder_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = DeadfinderEngine()
    monkeypatch.setattr(DeadfinderEngine, "version", lambda _self: "0.4.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "url": "http://localhost:3000/api/old-v1-endpoint",
                    "status": 404,
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "deadfinder/broken-link" in failing["findings"][0]["rule"]
