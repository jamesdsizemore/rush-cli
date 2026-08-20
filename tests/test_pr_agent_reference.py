"""Phase 19 PR-Agent reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pr_agent
from rush.engines.pr_agent import PrAgentEngine


def test_pr_agent_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(pr_agent, "resolve_binary", lambda _binary: "C:/bin/pr-agent")
    monkeypatch.setattr(pr_agent, "run_subprocess", fake_run)

    raw = PrAgentEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/pr-agent",
            "--pr_url=local",
            "--output=json",
        ]
    ]


def test_pr_agent_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PrAgentEngine()
    monkeypatch.setattr(PrAgentEngine, "version", lambda _self: "0.20.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "workflow")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {"error": "PR description is empty, suggested summary generated"}
            ],
        },
        tmp_path,
        "workflow",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "pr-agent/review-alert" in failing["findings"][0]["rule"]
