"""Phase 19 Git-Guard reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import git_guard
from rush.engines.git_guard import GitGuardEngine


def test_git_guard_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(git_guard, "resolve_binary", lambda _binary: "C:/bin/git")
    monkeypatch.setattr(git_guard, "run_subprocess", fake_run)

    raw = GitGuardEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/git",
            "status",
            "--porcelain=v2",
            "--branch",
        ]
    ]


def test_git_guard_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = GitGuardEngine()
    monkeypatch.setattr(GitGuardEngine, "version", lambda _self: "2.46.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [{"type": "untracked", "path": "secrets.env"}],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "git-guard/untracked-files" in failing["findings"][0]["rule"]
