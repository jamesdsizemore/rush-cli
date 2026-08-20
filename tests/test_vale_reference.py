"""Phase 19 Vale reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import vale
from rush.engines.vale import ValeEngine


def test_vale_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(vale, "resolve_binary", lambda _binary: "C:/bin/vale")
    monkeypatch.setattr(vale, "run_subprocess", fake_run)

    raw = ValeEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/vale",
            "--output=JSON",
            "--no-wrap",
            str(tmp_path),
        ]
    ]


def test_vale_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ValeEngine()
    monkeypatch.setattr(ValeEngine, "version", lambda _self: "3.5.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "README.md",
                    "Line": 12,
                    "Span": [5, 10],
                    "Check": "Google.Passive",
                    "Severity": "suggestion",
                    "Message": "In general, use active voice instead of passive voice.",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "vale/Google.Passive" in failing["findings"][0]["rule"]
