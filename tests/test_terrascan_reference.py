"""Phase 12 Terrascan reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import terrascan
from rush.engines.terrascan import TerrascanEngine


def test_terrascan_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"results": {"violations": []}}', stderr=""
        )

    monkeypatch.setattr(terrascan, "resolve_binary", lambda _binary: "C:/bin/terrascan")
    monkeypatch.setattr(terrascan, "run_subprocess", fake_run)

    raw = TerrascanEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/terrascan",
            "scan",
            "-i",
            "terraform",
            "-d",
            str(tmp_path),
            "-o",
            "json",
        ]
    ]


def test_terrascan_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = TerrascanEngine()
    monkeypatch.setattr(TerrascanEngine, "version", lambda _self: "1.18.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "iac")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 3,
            "findings": [
                {
                    "rule_name": "s3EnforceSSL",
                    "file": "main.tf",
                    "line": 14,
                    "severity": "HIGH",
                    "description": "S3 bucket does not enforce TLS requests",
                }
            ],
        },
        tmp_path,
        "iac",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "s3EnforceSSL"
