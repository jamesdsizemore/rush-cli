"""Phase 19 Safe-Env reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import safe_env
from rush.engines.safe_env import SafeEnvEngine


def test_safe_env_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(safe_env, "resolve_binary", lambda _binary: "C:/bin/safe-env")
    monkeypatch.setattr(safe_env, "run_subprocess", fake_run)

    raw = SafeEnvEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/safe-env",
            "check",
            "--json",
            str(tmp_path),
        ]
    ]


def test_safe_env_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = SafeEnvEngine()
    monkeypatch.setattr(SafeEnvEngine, "version", lambda _self: "0.4.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": ".env.production",
                    "line": 4,
                    "rule": "default-dev-jwt-secret",
                    "severity": "error",
                    "message": "JWT_SECRET contains default dev secret string 'secret123'",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "safe-env/default-dev-jwt-secret" in failing["findings"][0]["rule"]
