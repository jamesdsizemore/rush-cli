"""Phase 16 Infection reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import infection
from rush.engines.infection import InfectionEngine


def test_infection_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(infection, "resolve_binary", lambda _binary: "C:/bin/infection")
    monkeypatch.setattr(infection, "run_subprocess", fake_run)

    raw = InfectionEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/infection",
            "--json=infection-log.json",
            "--no-interaction",
            "--silent",
        ]
    ]


def test_infection_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = InfectionEngine()
    monkeypatch.setattr(InfectionEngine, "version", lambda _self: "0.29.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "mutation")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "sourceFilePath": "src/Order.php",
                    "line": 88,
                    "mutator": "GreaterThanOrEqualTo",
                }
            ],
        },
        tmp_path,
        "mutation",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "infection/GreaterThanOrEqualTo" in failing["findings"][0]["rule"]
