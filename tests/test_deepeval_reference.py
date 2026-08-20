"""Phase 09 DeepEval reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import deepeval
from rush.engines.deepeval import DeepevalEngine


def test_deepeval_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"test_results": []}', stderr=""
        )

    monkeypatch.setattr(deepeval, "resolve_binary", lambda _binary: "C:/bin/deepeval")
    monkeypatch.setattr(deepeval, "run_subprocess", fake_run)

    raw = DeepevalEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/deepeval",
            "test",
            "run",
            "--json-report=deepeval-results.json",
        ]
    ]


def test_deepeval_normalizes_clean_and_metrics(monkeypatch, tmp_path: Path) -> None:
    engine = DeepevalEngine()
    monkeypatch.setattr(DeepevalEngine, "version", lambda _self: "0.21.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "ai-eval")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "name": "FaithfulnessMetric",
                    "score": 0.4,
                    "reason": "Actual output contains contradictory facts",
                }
            ],
        },
        tmp_path,
        "ai-eval",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "FaithfulnessMetric" in failing["findings"][0]["rule"]
