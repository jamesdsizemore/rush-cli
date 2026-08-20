"""Phase 07.A3 Pytest reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pytest as pytest_engine
from rush.engines.pytest import PytestEngine
from rush.tools import common


def test_pytest_runs_bounded_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout="5 passed in 0.12s", stderr=""
        )

    monkeypatch.setattr(pytest_engine, "run_subprocess", fake_run)

    raw = PytestEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert "5 passed in 0.12s" in raw["summary"]
    assert calls[0][1:3] == ["-m", "pytest"]


def test_pytest_normalizes_passed_failed_error(monkeypatch, tmp_path: Path) -> None:
    engine = PytestEngine()
    monkeypatch.setattr(PytestEngine, "version", lambda _self: "8.3.2")

    clean = engine.normalize(
        {
            "exit_code": 0,
            "stdout": "1 passed in 0.01s",
            "summary": "1 passed in 0.01s",
            "findings": [],
        },
        tmp_path,
        "test",
    )
    failed = engine.normalize(
        {
            "exit_code": 1,
            "stdout": "1 failed in 0.01s",
            "summary": "1 failed in 0.01s",
            "findings": [],
        },
        tmp_path,
        "test",
    )
    error = engine.normalize(
        {"exit_code": 2, "stdout": "", "summary": "pytest exit 2", "findings": []},
        tmp_path,
        "test",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "test"
    assert failed["status"] == "fail"
    assert len(failed["findings"]) == 1
    assert error["status"] == "error"


def test_pytest_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = PytestEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="test")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        pytest_engine,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("pytest", 300)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="test")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
