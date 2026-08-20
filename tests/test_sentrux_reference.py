"""Reference adapter tests for sentrux."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import sentrux
from rush.engines.sentrux import SentruxEngine
from rush.tools import common


def test_sentrux_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(sentrux, "resolve_binary", lambda _binary: "C:/bin/sentrux")
    monkeypatch.setattr(sentrux, "run_subprocess", fake_run)

    raw = SentruxEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/sentrux", "check", "--json", str(tmp_path)]]


def test_sentrux_normalizes_clean(tmp_path: Path) -> None:
    engine = SentruxEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/sentrux/clean.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture.get("alerts", []), "parsed": fixture},
        tmp_path,
        "complexity",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_sentrux_normalizes_findings(tmp_path: Path) -> None:
    engine = SentruxEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/sentrux/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture.get("alerts", []), "parsed": fixture},
        tmp_path,
        "complexity",
    )
    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "sentrux/cyclomatic-complexity-spike"


def test_sentrux_normalizes_malformed(tmp_path: Path) -> None:
    engine = SentruxEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "complexity"
    )
    assert res["status"] == "error"


def test_sentrux_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(SentruxEngine(), tmp_path)
    assert res["status"] == "skipped"
