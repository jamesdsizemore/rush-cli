"""Reference adapter tests for undercover."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import undercover
from rush.engines.undercover import UndercoverEngine
from rush.tools import common


def test_undercover_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        undercover, "resolve_binary", lambda _binary: "C:/bin/undercover"
    )
    monkeypatch.setattr(undercover, "run_subprocess", fake_run)

    raw = UndercoverEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/undercover", "--format", "json"]]


def test_undercover_normalizes_clean(tmp_path: Path) -> None:
    engine = UndercoverEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/undercover/clean.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture},
        tmp_path,
        "coverage",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_undercover_normalizes_findings(tmp_path: Path) -> None:
    engine = UndercoverEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/undercover/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture},
        tmp_path,
        "coverage",
    )
    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "undercover/untested-change"


def test_undercover_normalizes_malformed(tmp_path: Path) -> None:
    engine = UndercoverEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "coverage"
    )
    assert res["status"] == "error"


def test_undercover_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(UndercoverEngine(), tmp_path)
    assert res["status"] == "skipped"
