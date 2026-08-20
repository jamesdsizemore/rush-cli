"""Phase 11 OpenSSF Scorecard reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import scorecard
from rush.engines.scorecard import ScorecardEngine


def test_scorecard_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"score": 8.5, "checks": []}', stderr=""
        )

    monkeypatch.setattr(scorecard, "resolve_binary", lambda _binary: "C:/bin/scorecard")
    monkeypatch.setattr(scorecard, "run_subprocess", fake_run)

    raw = ScorecardEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/scorecard",
            "--repo=.",
            "--format=json",
        ]
    ]


def test_scorecard_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ScorecardEngine()
    monkeypatch.setattr(ScorecardEngine, "version", lambda _self: "4.12.0")

    clean = engine.normalize(
        {"exit_code": 0, "findings": [], "parsed": {"score": 9.0}}, tmp_path, "ci"
    )
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "parsed": {"score": 4.5},
            "findings": [
                {
                    "name": "Dangerous-Workflow",
                    "score": 0,
                    "reason": "Untrusted checkout in pull_request_target",
                }
            ],
        },
        tmp_path,
        "ci",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "scorecard/dangerous-workflow" in failing["findings"][0]["rule"]
