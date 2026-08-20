"""Phase 15 Pa11y reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pa11y
from rush.engines.pa11y import Pa11yEngine


def test_pa11y_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(pa11y, "resolve_binary", lambda _binary: "C:/bin/pa11y")
    monkeypatch.setattr(pa11y, "run_subprocess", fake_run)

    raw = Pa11yEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/pa11y",
            "--reporter",
            "json",
            str(tmp_path),
        ]
    ]


def test_pa11y_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = Pa11yEngine()
    monkeypatch.setattr(Pa11yEngine, "version", lambda _self: "8.0.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 2,
            "findings": [
                {
                    "code": "WCAG2AA.Principle1.Guideline1_4.1_4_3.G18.Fail",
                    "type": "error",
                    "message": "Contrast ratio is insufficient (2.5:1 vs required 4.5:1)",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "pa11y/WCAG2AA" in failing["findings"][0]["rule"]
