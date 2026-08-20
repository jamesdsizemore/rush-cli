"""Reference adapter tests for globstar."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import globstar
from rush.engines.globstar import GlobstarEngine
from rush.tools import common


def test_globstar_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(globstar, "resolve_binary", lambda _binary: "C:/bin/globstar")
    monkeypatch.setattr(globstar, "run_subprocess", fake_run)

    raw = GlobstarEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/globstar", "check", "--format=json", str(tmp_path)]]


def test_globstar_normalizes_clean(tmp_path: Path) -> None:
    engine = GlobstarEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/globstar/clean.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture},
        tmp_path,
        "lint",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_globstar_normalizes_findings(tmp_path: Path) -> None:
    engine = GlobstarEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/globstar/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture},
        tmp_path,
        "lint",
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "globstar/unhandled-goroutine-panic"


def test_globstar_normalizes_malformed(tmp_path: Path) -> None:
    engine = GlobstarEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "lint"
    )
    assert res["status"] == "error"


def test_globstar_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(GlobstarEngine(), tmp_path)
    assert res["status"] == "skipped"
