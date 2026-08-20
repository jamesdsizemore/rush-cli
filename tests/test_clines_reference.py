"""Reference adapter tests for clines."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import clines
from rush.engines.clines import ClinesEngine
from rush.tools import common


def test_clines_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(clines, "resolve_binary", lambda _binary: "C:/bin/clines")
    monkeypatch.setattr(clines, "run_subprocess", fake_run)

    raw = ClinesEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/clines", "--json", str(tmp_path)]]


def test_clines_normalizes_clean(tmp_path: Path) -> None:
    engine = ClinesEngine()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/engine_reports/clines/clean.json").read_text(
            encoding="utf-8"
        )
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture.get("warnings", []), "parsed": fixture},
        tmp_path,
        "complexity",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_clines_normalizes_findings(tmp_path: Path) -> None:
    engine = ClinesEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/clines/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture.get("warnings", []), "parsed": fixture},
        tmp_path,
        "complexity",
    )
    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "clines/high-token-density"


def test_clines_normalizes_malformed(tmp_path: Path) -> None:
    engine = ClinesEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "complexity"
    )
    assert res["status"] == "error"


def test_clines_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(ClinesEngine(), tmp_path)
    assert res["status"] == "skipped"
