"""Phase 19 PyClean reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pyclean
from rush.engines.pyclean import PycleanEngine


def test_pyclean_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(pyclean, "resolve_binary", lambda _binary: "C:/bin/pyclean")
    monkeypatch.setattr(pyclean, "run_subprocess", fake_run)

    raw = PycleanEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/pyclean",
            "--dry-run",
            "--verbose",
            str(tmp_path),
        ]
    ]


def test_pyclean_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PycleanEngine()
    monkeypatch.setattr(PycleanEngine, "version", lambda _self: "3.0.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "format")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [{"artifact": "src/__pycache__/app.cpython-312.pyc"}],
        },
        tmp_path,
        "format",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "pyclean/stale-bytecode" in failing["findings"][0]["rule"]
