"""Phase 10 Secretlint reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import secretlint
from rush.engines.secretlint import SecretlintEngine


def test_secretlint_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        secretlint, "resolve_binary", lambda _binary: "C:/bin/secretlint"
    )
    monkeypatch.setattr(secretlint, "run_subprocess", fake_run)

    raw = SecretlintEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/secretlint",
            "--format",
            "json",
            "**/*",
        ]
    ]


def test_secretlint_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = SecretlintEngine()
    monkeypatch.setattr(SecretlintEngine, "version", lambda _self: "8.2.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "secrets")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "filePath": "src/api.ts",
                    "messages": [
                        {
                            "line": 10,
                            "column": 12,
                            "ruleId": "@secretlint/secretlint-rule-npm-token",
                            "severity": "error",
                            "message": "Found npm token npm_abcdef123456",
                        }
                    ],
                }
            ],
        },
        tmp_path,
        "secrets",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "@secretlint/secretlint-rule-npm-token"
