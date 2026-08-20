"""Phase 19 Wait-On reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import wait_on
from rush.engines.wait_on import WaitOnEngine


def test_wait_on_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(wait_on, "resolve_binary", lambda _binary: "C:/bin/wait-on")
    monkeypatch.setattr(wait_on, "run_subprocess", fake_run)

    raw = WaitOnEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/wait-on",
            "--timeout",
            "5000",
            "http://localhost:3000",
        ]
    ]


def test_wait_on_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = WaitOnEngine()
    monkeypatch.setattr(WaitOnEngine, "version", lambda _self: "7.2.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "workflow")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "target": "http://localhost:3000",
                    "error": "Timeout waiting for http://localhost:3000",
                }
            ],
        },
        tmp_path,
        "workflow",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "wait-on/readiness-timeout" in failing["findings"][0]["rule"]
