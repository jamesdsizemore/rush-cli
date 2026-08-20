"""Phase 10 Bearer reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import bearer
from rush.engines.bearer import BearerEngine


def test_bearer_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"critical": [], "high": []}', stderr=""
        )

    monkeypatch.setattr(bearer, "resolve_binary", lambda _binary: "C:/bin/bearer")
    monkeypatch.setattr(bearer, "run_subprocess", fake_run)

    raw = BearerEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/bearer",
            "scan",
            "--format",
            "json",
            "--output",
            "bearer-report.json",
            "--quiet",
            "--disable-version-check",
            str(tmp_path),
        ]
    ]


def test_bearer_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = BearerEngine()
    monkeypatch.setattr(BearerEngine, "version", lambda _self: "1.45.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "filename": "src/user.py",
                    "line_number": 45,
                    "column_number": 10,
                    "cwe_ids": ["CWE-359"],
                    "severity": "high",
                    "title": "Unencrypted PII logged to console",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "CWE-359"
