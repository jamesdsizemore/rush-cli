"""Phase 19 Semantic-Release reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import semantic_release
from rush.engines.semantic_release import SemanticReleaseEngine


def test_semantic_release_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(
        semantic_release,
        "resolve_binary",
        lambda _binary: "C:/bin/semantic-release",
    )
    monkeypatch.setattr(semantic_release, "run_subprocess", fake_run)

    raw = SemanticReleaseEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/semantic-release",
            "--dry-run",
            "--no-ci",
        ]
    ]


def test_semantic_release_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = SemanticReleaseEngine()
    monkeypatch.setattr(SemanticReleaseEngine, "version", lambda _self: "24.1.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "workflow")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [{"error": "Git tag v1.0.0 already exists"}],
        },
        tmp_path,
        "workflow",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "semantic-release/execution-error" in failing["findings"][0]["rule"]
