"""Reference adapter tests for aislop."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import aislop
from rush.engines.aislop import AislopEngine
from rush.tools import common


def test_aislop_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "C:/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)

    raw = AislopEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/aislop", "scan", "--format=json", str(tmp_path)]]


def test_aislop_normalizes_clean(tmp_path: Path) -> None:
    engine = AislopEngine()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/engine_reports/aislop/clean.json").read_text(
            encoding="utf-8"
        )
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture}, tmp_path, "slop"
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_aislop_normalizes_findings(tmp_path: Path) -> None:
    engine = AislopEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/aislop/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture}, tmp_path, "slop"
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "aislop/hallucinated-import"


def test_aislop_normalizes_malformed(tmp_path: Path) -> None:
    engine = AislopEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "slop"
    )
    assert res["status"] == "error"


def test_aislop_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(AislopEngine(), tmp_path)
    assert res["status"] == "skipped"
