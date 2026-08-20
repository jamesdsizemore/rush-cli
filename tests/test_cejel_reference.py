"""Reference adapter tests for cejel."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import cejel
from rush.engines.cejel import CejelEngine
from rush.tools import common


def test_cejel_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(cejel, "resolve_binary", lambda _binary: "C:/bin/cejel")
    monkeypatch.setattr(cejel, "run_subprocess", fake_run)

    raw = CejelEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/cejel", "verify", "--format=json"]]


def test_cejel_normalizes_clean(tmp_path: Path) -> None:
    engine = CejelEngine()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/engine_reports/cejel/clean.json").read_text(
            encoding="utf-8"
        )
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture.get("violations", []), "parsed": fixture},
        tmp_path,
        "release",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_cejel_normalizes_findings(tmp_path: Path) -> None:
    engine = CejelEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/cejel/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture.get("violations", []), "parsed": fixture},
        tmp_path,
        "release",
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "cejel/unattested-mutation"


def test_cejel_normalizes_malformed(tmp_path: Path) -> None:
    engine = CejelEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "release"
    )
    assert res["status"] == "error"


def test_cejel_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(CejelEngine(), tmp_path)
    assert res["status"] == "skipped"
