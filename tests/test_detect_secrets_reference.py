"""Phase 10 Detect-secrets reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import detect_secrets
from rush.engines.detect_secrets import DetectSecretsEngine


def test_detect_secrets_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"results": {}}', stderr="")

    monkeypatch.setattr(
        detect_secrets, "resolve_binary", lambda _binary: "C:/bin/detect-secrets"
    )
    monkeypatch.setattr(detect_secrets, "run_subprocess", fake_run)

    raw = DetectSecretsEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/detect-secrets",
            "scan",
            "--all-files",
        ]
    ]


def test_detect_secrets_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = DetectSecretsEngine()
    monkeypatch.setattr(DetectSecretsEngine, "version", lambda _self: "1.4.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "secrets")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "file": "deploy.env",
                    "line_number": 8,
                    "type": "Secret Keyword",
                }
            ],
        },
        tmp_path,
        "secrets",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "detect-secrets" in failing["findings"][0]["rule"]
