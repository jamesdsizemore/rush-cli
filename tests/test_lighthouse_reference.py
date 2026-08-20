"""Phase 15 Lighthouse reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import lighthouse
from rush.engines.lighthouse import LighthouseEngine


def test_lighthouse_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(
        lighthouse, "resolve_binary", lambda _binary: "C:/bin/lighthouse"
    )
    monkeypatch.setattr(lighthouse, "run_subprocess", fake_run)

    raw = LighthouseEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/lighthouse",
            "http://localhost:3000",
            "--output=json",
            "--output-path=lighthouse-report.json",
            "--chrome-flags=--headless",
        ]
    ]


def test_lighthouse_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = LighthouseEngine()
    monkeypatch.setattr(LighthouseEngine, "version", lambda _self: "12.0.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "visual")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "id": "largest-contentful-paint",
                    "title": "Largest Contentful Paint element takes 4.5s",
                    "score": 0.35,
                }
            ],
        },
        tmp_path,
        "visual",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "lighthouse/largest-contentful-paint" in failing["findings"][0]["rule"]
