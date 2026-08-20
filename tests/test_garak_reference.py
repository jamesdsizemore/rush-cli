"""Phase 09 Garak reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import garak
from rush.engines.garak import GarakEngine


def test_garak_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(garak, "resolve_binary", lambda _binary: "C:/bin/garak")
    monkeypatch.setattr(garak, "run_subprocess", fake_run)

    raw = GarakEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/garak",
            "--report_prefix",
            "garak_report",
        ]
    ]


def test_garak_normalizes_clean_and_vulnerabilities(
    monkeypatch, tmp_path: Path
) -> None:
    engine = GarakEngine()
    monkeypatch.setattr(GarakEngine, "version", lambda _self: "0.10.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "ai-eval")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "probe": "dan.Dan_11_0",
                    "detector": "mitigation.MitigationBypass",
                    "score": 0.2,
                }
            ],
        },
        tmp_path,
        "ai-eval",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "dan.Dan_11_0" in failing["findings"][0]["rule"]
