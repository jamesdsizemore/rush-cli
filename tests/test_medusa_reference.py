"""Reference adapter tests for medusa."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rush.engines import medusa
from rush.engines.medusa import MedusaEngine
from rush.tools import common


def test_medusa_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(medusa, "resolve_binary", lambda _binary: "C:/bin/medusa")
    monkeypatch.setattr(medusa, "run_subprocess", fake_run)

    raw = MedusaEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/medusa", "scan", "--format=json", str(tmp_path)]]


def test_medusa_normalizes_clean(tmp_path: Path) -> None:
    engine = MedusaEngine()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/engine_reports/medusa/clean.json").read_text(
            encoding="utf-8"
        )
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture},
        tmp_path,
        "security",
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_medusa_normalizes_findings(tmp_path: Path) -> None:
    engine = MedusaEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/medusa/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture},
        tmp_path,
        "security",
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "medusa/dangerous-remote-curl"


def test_medusa_normalizes_malformed(tmp_path: Path) -> None:
    engine = MedusaEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "security"
    )
    assert res["status"] == "error"


def test_medusa_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(MedusaEngine(), tmp_path)
    assert res["status"] == "skipped"
