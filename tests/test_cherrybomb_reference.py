"""Phase 13 Cherrybomb reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import cherrybomb
from rush.engines.cherrybomb import CherrybombEngine


def test_cherrybomb_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"alerts": []}', stderr="")

    monkeypatch.setattr(
        cherrybomb, "resolve_binary", lambda _binary: "C:/bin/cherrybomb"
    )
    monkeypatch.setattr(cherrybomb, "run_subprocess", fake_run)

    raw = CherrybombEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/cherrybomb",
            "--file",
            str(tmp_path),
            "--format",
            "json",
            "--output",
            "cherrybomb-report.json",
        ]
    ]


def test_cherrybomb_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = CherrybombEngine()
    monkeypatch.setattr(CherrybombEngine, "version", lambda _self: "1.1.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "check_id": "API1:2023-BOLA",
                    "level": "high",
                    "description": "Broken Object Level Authorization detected in path param",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "cherrybomb/API1:2023-BOLA" in failing["findings"][0]["rule"]
