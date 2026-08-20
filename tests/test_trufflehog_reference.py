"""Phase 10 TruffleHog reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import trufflehog
from rush.engines.trufflehog import TruffleHogEngine


def test_trufflehog_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        trufflehog, "resolve_binary", lambda _binary: "C:/bin/trufflehog"
    )
    monkeypatch.setattr(trufflehog, "run_subprocess", fake_run)

    raw = TruffleHogEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/trufflehog",
            "filesystem",
            "--json",
            "--no-verification",
            "--no-update",
            str(tmp_path),
        ]
    ]


def test_trufflehog_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = TruffleHogEngine()
    monkeypatch.setattr(TruffleHogEngine, "version", lambda _self: "3.80.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "secrets")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "DetectorName": "AWS",
                    "SourceMetadata": {
                        "Data": {"Filesystem": {"file": "config.py", "line": 20}}
                    },
                    "Raw": "AKIAIOSFODNN7EXAMPLE",
                    "Verified": False,
                }
            ],
        },
        tmp_path,
        "secrets",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "trufflehog/aws" in failing["findings"][0]["rule"]
