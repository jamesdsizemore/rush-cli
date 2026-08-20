"""Phase 19 npm-check-updates (ncu) reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import ncu
from rush.engines.ncu import NcuEngine


def test_ncu_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(ncu, "resolve_binary", lambda _binary: "C:/bin/ncu")
    monkeypatch.setattr(ncu, "run_subprocess", fake_run)

    raw = NcuEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/ncu",
            "--format",
            "json",
        ]
    ]


def test_ncu_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = NcuEngine()
    monkeypatch.setattr(NcuEngine, "version", lambda _self: "16.14.20")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "workflow")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [{"package": "react", "target_version": "^19.0.0"}],
        },
        tmp_path,
        "workflow",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "ncu/outdated-dependency" in failing["findings"][0]["rule"]
