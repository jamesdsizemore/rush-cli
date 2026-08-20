"""Phase 15 PageSpeed reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pagespeed
from rush.engines.pagespeed import PagespeedEngine


def test_pagespeed_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(
        pagespeed, "resolve_binary", lambda _binary: "C:/bin/pagespeed-insights"
    )
    monkeypatch.setattr(pagespeed, "run_subprocess", fake_run)

    raw = PagespeedEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/pagespeed-insights",
            "http://localhost:3000",
            "--format",
            "json",
        ]
    ]


def test_pagespeed_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PagespeedEngine()
    monkeypatch.setattr(PagespeedEngine, "version", lambda _self: "5.0.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "visual")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "id": "cumulative-layout-shift",
                    "title": "Cumulative Layout Shift exceeds 0.25",
                    "score": 0.4,
                }
            ],
        },
        tmp_path,
        "visual",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "pagespeed/cumulative-layout-shift" in failing["findings"][0]["rule"]
