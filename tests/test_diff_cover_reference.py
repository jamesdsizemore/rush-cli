"""Phase 19 Diff-Cover reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import diff_cover
from rush.engines.diff_cover import DiffCoverEngine


def test_diff_cover_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(
        diff_cover, "resolve_binary", lambda _binary: "C:/bin/diff-cover"
    )
    monkeypatch.setattr(diff_cover, "run_subprocess", fake_run)

    raw = DiffCoverEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/diff-cover",
            "coverage.xml",
            "--compare-branch=main",
            "--json-report=diff-cover.json",
        ]
    ]


def test_diff_cover_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = DiffCoverEngine()
    monkeypatch.setattr(DiffCoverEngine, "version", lambda _self: "9.1.1")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "metrics")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "file": "src/rush/cli.py",
                    "percent": 65.5,
                    "missing": [45, 46, 50],
                }
            ],
        },
        tmp_path,
        "metrics",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "diff-cover/under-threshold" in failing["findings"][0]["rule"]
