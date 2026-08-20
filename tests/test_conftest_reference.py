"""Phase 12 Conftest reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import conftest
from rush.engines.conftest import ConftestEngine


def test_conftest_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(conftest, "resolve_binary", lambda _binary: "C:/bin/conftest")
    monkeypatch.setattr(conftest, "run_subprocess", fake_run)

    raw = ConftestEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/conftest",
            "test",
            "-o",
            "json",
            "--no-color",
            str(tmp_path),
        ]
    ]


def test_conftest_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ConftestEngine()
    monkeypatch.setattr(ConftestEngine, "version", lambda _self: "0.55.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "iac")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "deployment.yaml",
                    "msg": "Containers must not run as root",
                    "severity": "fail",
                    "metadata": {"rule": "deny_root_user"},
                }
            ],
        },
        tmp_path,
        "iac",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "deny_root_user"
