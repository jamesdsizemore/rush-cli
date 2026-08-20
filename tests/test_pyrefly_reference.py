"""Reference adapter tests for pyrefly."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import pyrefly
from rush.engines.pyrefly import PyreflyEngine
from rush.tools import common


def test_pyrefly_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(pyrefly, "resolve_binary", lambda _binary: "C:/bin/pyrefly")
    monkeypatch.setattr(pyrefly, "run_subprocess", fake_run)

    raw = PyreflyEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/pyrefly", "check", "--output=json", str(tmp_path)]]


def test_pyrefly_normalizes_clean(tmp_path: Path) -> None:
    engine = PyreflyEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/pyrefly/clean.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture},
        tmp_path,
        "typecheck",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_pyrefly_normalizes_findings(tmp_path: Path) -> None:
    engine = PyreflyEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/pyrefly/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture},
        tmp_path,
        "typecheck",
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "pyrefly/incompatible-types"


def test_pyrefly_normalizes_malformed(tmp_path: Path) -> None:
    engine = PyreflyEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "typecheck"
    )
    assert res["status"] == "error"


def test_pyrefly_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(PyreflyEngine(), tmp_path)
    assert res["status"] == "skipped"
