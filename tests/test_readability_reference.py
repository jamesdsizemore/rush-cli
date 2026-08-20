"""Phase 19 Readability reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import readability
from rush.engines.readability import ReadabilityEngine


def test_readability_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(
        readability, "resolve_binary", lambda _binary: "C:/bin/readability-cli"
    )
    monkeypatch.setattr(readability, "run_subprocess", fake_run)

    raw = ReadabilityEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/readability-cli",
            "--json",
            str(tmp_path),
        ]
    ]


def test_readability_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ReadabilityEngine()
    monkeypatch.setattr(ReadabilityEngine, "version", lambda _self: "2.1.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "metrics")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [{"metric": "Flesch-Kincaid", "value": 16.5}],
        },
        tmp_path,
        "metrics",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "readability/high-grade-level" in failing["findings"][0]["rule"]
