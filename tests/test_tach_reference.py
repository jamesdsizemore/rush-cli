"""Reference adapter tests for tach."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import tach
from rush.engines.tach import TachEngine
from rush.tools import common


def test_tach_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(tach, "resolve_binary", lambda _binary: "C:/bin/tach")
    monkeypatch.setattr(tach, "run_subprocess", fake_run)

    raw = TachEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/tach", "check", "--output=json"]]


def test_tach_normalizes_clean(tmp_path: Path) -> None:
    engine = TachEngine()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/engine_reports/tach/clean.json").read_text(
            encoding="utf-8"
        )
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture},
        tmp_path,
        "complexity",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_tach_normalizes_findings(tmp_path: Path) -> None:
    engine = TachEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/tach/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture},
        tmp_path,
        "complexity",
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "tach/unauthorized-import"


def test_tach_normalizes_malformed(tmp_path: Path) -> None:
    engine = TachEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "complexity"
    )
    assert res["status"] == "error"


def test_tach_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(TachEngine(), tmp_path)
    assert res["status"] == "skipped"
