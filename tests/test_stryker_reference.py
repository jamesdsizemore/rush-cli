"""Phase 16 Stryker Mutator reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import stryker
from rush.engines.stryker import StrykerEngine


def test_stryker_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"files": {}}', stderr="")

    monkeypatch.setattr(stryker, "resolve_binary", lambda _binary: "C:/bin/stryker")
    monkeypatch.setattr(stryker, "run_subprocess", fake_run)

    raw = StrykerEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/stryker",
            "run",
            "--reporters",
            "json",
        ]
    ]


def test_stryker_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = StrykerEngine()
    monkeypatch.setattr(StrykerEngine, "version", lambda _self: "8.2.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "mutation")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "file": "src/math.ts",
                    "mutatorName": "BinaryExpression",
                    "replacement": "a - b",
                    "location": {"start": {"line": 12, "column": 8}},
                }
            ],
        },
        tmp_path,
        "mutation",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "stryker/BinaryExpression" in failing["findings"][0]["rule"]
