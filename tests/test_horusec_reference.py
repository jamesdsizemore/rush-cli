"""Phase 10 Horusec reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import horusec
from rush.engines.horusec import HorusecEngine


def test_horusec_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"analysisVulnerabilities": []}', stderr=""
        )

    monkeypatch.setattr(horusec, "resolve_binary", lambda _binary: "C:/bin/horusec")
    monkeypatch.setattr(horusec, "run_subprocess", fake_run)

    raw = HorusecEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/horusec",
            "start",
            "-p",
            str(tmp_path),
            "-o",
            "json",
            "-O",
            "horusec-result.json",
            "-s",
            "LOW",
            "-D",
        ]
    ]


def test_horusec_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = HorusecEngine()
    monkeypatch.setattr(HorusecEngine, "version", lambda _self: "2.8.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "server.go",
                    "line": "33",
                    "column": "5",
                    "rule_id": "HS-GO-1",
                    "severity": "HIGH",
                    "details": "Hardcoded database password",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "HS-GO-1"
