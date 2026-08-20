"""Phase 17 Critical reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import critical
from rush.engines.critical import CriticalEngine


def test_critical_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="/* css */", stderr="")

    monkeypatch.setattr(critical, "resolve_binary", lambda _binary: "C:/bin/critical")
    monkeypatch.setattr(critical, "run_subprocess", fake_run)

    raw = CriticalEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/critical",
            "--base",
            str(tmp_path),
            "--inline",
            "--dry-run",
            str(tmp_path),
        ]
    ]


def test_critical_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = CriticalEngine()
    monkeypatch.setattr(CriticalEngine, "version", lambda _self: "7.1.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "format")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [{"error": "Unable to extract stylesheets from document"}],
        },
        tmp_path,
        "format",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "critical/extraction-error" in failing["findings"][0]["rule"]
