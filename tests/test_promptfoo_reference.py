"""Phase 09 Promptfoo reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import promptfoo
from rush.engines.promptfoo import PromptfooEngine


def test_promptfoo_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"results": {"table": {"body": []}}}', stderr=""
        )

    monkeypatch.setattr(promptfoo, "resolve_binary", lambda _binary: "C:/bin/promptfoo")
    monkeypatch.setattr(promptfoo, "run_subprocess", fake_run)

    raw = PromptfooEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/promptfoo",
            "eval",
            "--output",
            "promptfoo-report.json",
            "--no-table",
            "--no-progress-bars",
        ]
    ]


def test_promptfoo_normalizes_clean_and_failures(monkeypatch, tmp_path: Path) -> None:
    engine = PromptfooEngine()
    monkeypatch.setattr(PromptfooEngine, "version", lambda _self: "0.90.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "ai-eval")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 100,
            "findings": [
                {
                    "description": "Prompt injection test",
                    "gradingResult": {
                        "reason": "Output contained leaked system prompt"
                    },
                }
            ],
        },
        tmp_path,
        "ai-eval",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "promptfoo-assertion"
